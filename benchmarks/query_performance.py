"""Matched cold/warm query timings, with a preserved pre-change source baseline."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import tarfile
import tempfile
import time

from rdflib import Graph, RDF, URIRef, OWL
from rdflib.compare import isomorphic, to_canonical_graph

from dlp_reasoner import Reasoner
from dlp_reasoner.native import build_native
from dlp_reasoner.reasoner import read_graph
from .bach import BACH, PREFIXES, compact, term
from .workloads import EX, taxonomy, transitive


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "benchmarks/query-baseline-source.tar.gz"
DEFAULT_OUTPUT = ROOT / "benchmarks/query-performance-results.json"
SCOPE = "query-caching-and-indexing-before-after-v1"
MODES = ("baseline", "disabled", "cached")
ORDERS = (("baseline", "disabled", "cached"), ("cached", "disabled", "baseline"),
          ("disabled", "baseline", "cached"), ("cached", "baseline", "disabled"),
          ("baseline", "cached", "disabled"))


@dataclass
class Query:
    label: str
    method: str
    args: tuple
    expected: object


@dataclass
class Case:
    name: str
    graph: Graph
    profile: str
    metadata: dict
    queries: list[Query]


def hashes():
    paths = list((ROOT / "src/dlp_reasoner").glob("*.py"))
    paths += list((ROOT / "src/dlp_reasoner").glob("native_store.*"))
    paths += [ROOT / name for name in (
        "benchmarks/query_performance.py", "benchmarks/query-baseline-source.tar.gz",
        "benchmarks/bach.py", "benchmarks/workloads.py", "examples/bach.dlp",
        "examples/bach-family.dlp", "examples/bach-queries.json", "tests/test_query_caching.py",
    )]
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths)}


def digest(graph):
    lines = sorted(to_canonical_graph(graph).serialize(format="nt").splitlines())
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def load_baseline(directory):
    """Read only verified regular package files; never tar.extract arbitrary paths."""
    directory = Path(directory)
    with tarfile.open(BASELINE, "r:gz") as archive:
        for member in archive.getmembers():
            path = Path(member.name)
            allowed = (path.as_posix() == "snapshot.json" or
                       (len(path.parts) == 3 and path.parts[:2] == ("src", "dlp_reasoner")
                        and path.suffix in {".py", ".cpp", ".h"}))
            if not member.isfile() or not allowed or path.is_absolute() or ".." in path.parts:
                raise ValueError(f"Unexpected baseline archive entry: {member.name}")
            target = directory / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.extractfile(member).read())
    manifest = json.loads((directory / "snapshot.json").read_text())
    for name, expected in manifest["source_sha256"].items():
        assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == expected
    package = directory / "src/dlp_reasoner"
    # Relative package imports keep baseline classes/compiler/engine separate
    # from the current implementation while allowing alternating measurements.
    name = "_dlp_query_baseline"
    specification = importlib.util.spec_from_file_location(
        name, package / "__init__.py", submodule_search_locations=[str(package)])
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module.Reasoner, manifest


def bach_case(variant):
    filename = "bach" if variant == "ontology" else "bach-family"
    graph = read_graph(ROOT / "examples" / f"{filename}.dlp")
    manifest = json.loads((ROOT / "examples/bach-queries.json").read_text())
    queries = []
    for query in manifest["queries"]:
        if query["variant"] != variant:
            continue
        expected = query["expected"]
        if isinstance(expected, list):
            expected = sorted(expected, key=json.dumps)
        if query["method"] == "instances_expression":
            prefixes = "\n".join(f"@prefix {prefix}: <{namespace}> ."
                                 for prefix, namespace in PREFIXES.items())
            prefixes += f"\n@prefix : <{BACH}> .\n"
            marker = URIRef("urn:query-performance:expression")
            expression_graph = Graph().parse(
                data=prefixes + f"<{marker}> rdf:value {query['expression']} .", format="turtle")
            node = expression_graph.value(marker, RDF.value)
            expression_graph.remove((marker, RDF.value, node))
            graph += expression_graph
            method, args = "instances", (node,)
        else:
            method, args = query["method"], tuple(term(value) for value in query["arguments"])
        queries.append(Query(query["id"], method, args, expected))
    return Case(filename, graph, "L3" if variant == "ontology" else "L0",
                {"source": f"examples/{filename}.dlp", "queries": "examples/bach-queries.json",
                 "expressions": "parse once into stable anonymous expression nodes; no query definitions asserted"},
                queries)


def cases():
    graph, meta = taxonomy(depth=5, individuals_per_class=9, variant="P1")
    assignments = {(subject, cls) for subject, cls in graph.subject_objects(RDF.type)
                   if str(cls).startswith(str(EX) + "C")}

    def ancestors(cls):
        number = int(str(cls).split("#C")[-1])
        result = {cls}
        while number:
            number = (number - 1) // 3
            result.add(EX[f"C{number}"])
        return result

    queries = []
    for number in (0, 1, 250, 363):
        concept = EX[f"C{number}"]
        expected = {individual for individual, cls in assignments if concept in ancestors(cls)}
        queries.append(Query(f"instances-C{number}", "instances", (concept,), compact(expected)))
    queries += [
        Query("types-i250", "types", (EX.i250_0,), compact(ancestors(EX.C250) | {OWL.Thing})),
        Query("values-p250", "property_values", (EX.i250_2, EX.p250),
              compact(set(graph.objects(EX.i250_2, EX.p250)))),
        Query("pairs-p250", "property_pairs", (EX.p250,), compact(set(graph.subject_objects(EX.p250)))),
        Query("root-inclusion", "subsumes", (EX.C0, EX.C250), True),
    ]
    transitive_queries = [
        Query(f"values-a{start}", "property_values", (EX[f"a{start}"], EX.p),
              compact({EX[f"a{end}"] for end in range(start + 1, 101)}))
        for start in (0, 50, 99, 100)
    ]
    transitive_queries += [
        Query("all-pairs", "property_pairs", (EX.p,),
              compact({(EX[f"a{start}"], EX[f"a{end}"])
                       for start in range(100) for end in range(start + 1, 101)})),
        Query("types-a50", "types", (EX.a50,), compact({OWL.Thing})),
        Query("positive-transitivity", "is_transitive", (EX.p,), True),
        Query("first-to-last", "entails", (EX.a0, EX.p, EX.a100), True),
    ]
    return [bach_case("ontology"), bach_case("family"),
            Case("taxonomy", graph, "L2", meta, queries),
            Case("transitive", transitive(100), "L0", {"edges": 100}, transitive_queries)]


def query_suite(reasoner, queries):
    # Keep validation/serialization outside the measured query operation.
    return [getattr(reasoner, query.method)(*query.args) for query in queries]


def validate_answers(queries, answers):
    for query, actual in zip(queries, answers):
        assert compact(actual) == query.expected, (query.label, compact(actual), query.expected)


def timed_sample(case, reasoner_type, backend, mode, warm_loops):
    options = {"backend": backend, "profile": case.profile}
    if mode != "baseline":
        options["query_cache_size"] = 256 if mode == "cached" else 0
    start = time.perf_counter()
    reasoner = reasoner_type(case.graph, **options)
    construct = time.perf_counter() - start
    assert reasoner.complete and reasoner.consistency == "consistent"
    start = time.perf_counter()
    answers = query_suite(reasoner, case.queries)
    first = time.perf_counter() - start
    validate_answers(case.queries, answers)
    cold_info = dict(reasoner.query_cache_info) if mode != "baseline" else None
    start = time.perf_counter()
    for _ in range(warm_loops):
        answers = query_suite(reasoner, case.queries)
    warm = time.perf_counter() - start
    validate_answers(case.queries, answers)
    return reasoner, {
        "construct_seconds": construct, "first_query_suite_seconds": first,
        "warm_query_block_seconds": warm, "warm_query_suite_seconds": warm / warm_loops,
        "cache_after_first": cold_info,
        "cache_after_warm": dict(reasoner.query_cache_info) if mode != "baseline" else None,
        "closure_facts": len(reasoner.engine.facts),
        "answer_sha256": hashlib.sha256(json.dumps([compact(answer) for answer in answers],
                                                  sort_keys=True).encode()).hexdigest(),
    }


def summary(values):
    return {"samples": values, "median": statistics.median(values),
            "minimum": min(values), "maximum": max(values)}


def measure(case, backend, baseline_type, repeats, warm_loops):
    samples = []
    for repetition in range(repeats):
        order = ORDERS[repetition % len(ORDERS)]
        sample = {"repetition": repetition, "order": list(order)}
        graphs = {}
        for mode in order:
            cls = baseline_type if mode == "baseline" else Reasoner
            reasoner, sample[mode] = timed_sample(case, cls, backend, mode, warm_loops)
            graphs[mode] = reasoner.to_graph(include_witnesses=True)
            del reasoner
        assert isomorphic(graphs["baseline"], graphs["disabled"])
        assert isomorphic(graphs["baseline"], graphs["cached"])
        assert len({sample[mode]["answer_sha256"] for mode in MODES}) == 1
        sample["closure_sha256"] = digest(graphs["baseline"])
        sample["validation"] = "full-source-backed-answers-and-witness-inclusive-closure-isomorphism"
        samples.append(sample)
    metrics = {}
    for phase in ("construct_seconds", "first_query_suite_seconds", "warm_query_suite_seconds"):
        metrics[phase] = {mode: summary([sample[mode][phase] for sample in samples]) for mode in MODES}
        for left, right in (("baseline", "disabled"), ("disabled", "cached"), ("baseline", "cached")):
            metrics[phase][f"{left}_over_{right}_median_ratio"] = (
                metrics[phase][left]["median"] / metrics[phase][right]["median"])
    return {"case": case.name, "backend": backend, "profile": case.profile,
            "metadata": case.metadata, "query_count": len(case.queries),
            "queries": [{"id": query.label, "method": query.method,
                         "answer_items": len(query.expected) if isinstance(query.expected, list) else 1}
                        for query in case.queries],
            "input_sha256": digest(case.graph), "samples": samples, "timings": metrics}


def protect_output(output, overwrite):
    output = Path(output)
    if output.is_symlink() or output.resolve().is_relative_to((ROOT / "benchmarks/baselines").resolve()):
        raise ValueError("Output must not alias another file or enter historical baselines")
    if output.exists():
        if not overwrite or not output.is_file() or output.stat().st_nlink != 1:
            raise ValueError("Use a new output or --overwrite for this harness's own prior report")
        try:
            previous = json.loads(output.read_text())
        except (OSError, ValueError) as exc:
            raise ValueError("Existing output is not this harness's report") from exc
        if not isinstance(previous, dict) or previous.get("scope") != SCOPE:
            raise ValueError("Only this harness's previous report may be overwritten")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, choices=[3, 4, 5], default=5)
    parser.add_argument("--warm-loops", type=int, default=10)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--cases", nargs="+", choices=["bach", "bach-family", "taxonomy", "transitive"])
    args = parser.parse_args(argv)
    if not __debug__ or not 1 <= args.warm_loops <= 100:
        raise ValueError("Use Python without -O and 1–100 warm loops")
    protect_output(args.output, args.overwrite)
    before = hashes()
    build = build_native()
    report = {"scope": SCOPE, "started_utc": datetime.now(timezone.utc).isoformat(),
              "repeats": args.repeats, "warm_loops": args.warm_loops,
              "source_sha256": before,
              "environment": {"python": platform.python_version(),
                              "rdflib": importlib.metadata.version("rdflib"),
                              "platform": platform.platform(), "machine": platform.machine(),
                              "hash_seed": os.environ.get("PYTHONHASHSEED", "random")},
              "native_build": json.loads(build.with_name("build.json").read_text()),
              "method": {
                  "baseline": "preserved pre-change package loaded under isolated relative-import namespace",
                  "disabled": "current implementation, indexed query paths, query_cache_size=0",
                  "cached": "current implementation, indexed queries and query_cache_size=256",
                  "cold": "one first suite on each newly constructed Reasoner; no query-answer warmup",
                  "warm": "immediately repeat the complete suite warm_loops times; per-suite mean within each repetition",
                  "ordering": "recorded rotating three-mode order; each case/backend has independent fresh materializations",
                  "validation": "all source-backed/independent expected answers and full witness-inclusive RDF closure match",
                  "bounds": "materialization, native initial compilation and answer validation outside query timers",
                  "limitations": "single uncontrolled workstation/process; no confidence interval or memory profiler",
              }, "cases": []}
    with tempfile.TemporaryDirectory(prefix="dlp-query-before-") as temporary:
        baseline_type, manifest = load_baseline(temporary)
        report["baseline_manifest"] = manifest
        # Prime native loading for the independent package outside all timers.
        baseline_type(Graph(), backend="native")
        for case in cases():
            if args.cases and case.name not in args.cases:
                continue
            for backend in ("python", "native"):
                report["cases"].append(measure(case, backend, baseline_type,
                                               args.repeats, args.warm_loops))
                print(f"Validated {case.name}/{backend}: {args.repeats} three-mode repetitions", flush=True)
    if hashes() != before:
        raise RuntimeError("Sources changed during measurement; refusing to retain report")
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    report["validation"] = "passed"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"Saved {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
