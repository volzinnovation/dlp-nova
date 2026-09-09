"""Paired public-Reasoner timings for the optional persistent native backend.

This measures actual construction, materialization, queries and RDF updates.
It does not reuse or reinterpret the earlier isolated binary-join experiment.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import gc
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import time

from rdflib import Graph, OWL, RDF, RDFS, URIRef
from rdflib.compare import isomorphic, to_canonical_graph

from dlp_reasoner import Reasoner
from dlp_reasoner.native import build_native
from dlp_reasoner.reasoner import read_graph
from .bach import BACH, compact, evaluate_query, reachability
from .workloads import EX, equality, taxonomy, transitive


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "benchmarks/native-backend-results.json"
SCOPE = "paired-public-reasoner-persistent-native-backend-v1"


@dataclass
class Case:
    name: str
    graph: Graph
    profile: str
    metadata: dict
    updates: list
    queries: list


def source_hashes():
    sources = list((ROOT / "src/dlp_reasoner").glob("*.py"))
    sources += list((ROOT / "src/dlp_reasoner").glob("native_store.*"))
    sources += [ROOT / name for name in (
        "benchmarks/native_backend.py", "benchmarks/workloads.py", "benchmarks/bach.py",
        "examples/bach.dlp", "examples/bach-family.dlp", "examples/bach-queries.json",
        "tests/test_native_backend.py",
    )]
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(sources)}


def graph_digest(graph):
    canonical = to_canonical_graph(graph)
    lines = sorted(canonical.serialize(format="nt").splitlines())
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def summary(values):
    return {"samples": values, "median": statistics.median(values),
            "minimum": min(values), "maximum": max(values)}


def paired_summary(samples, key):
    grouped = {backend: summary([sample[backend][key] for sample in samples])
               for backend in ("python", "native")}
    grouped["python_over_native_median_ratio"] = (grouped["python"]["median"] /
                                                  grouped["native"]["median"])
    grouped["paired_python_over_native_ratios"] = [
        sample["python"][key] / sample["native"][key] for sample in samples]
    return grouped


def cases():
    taxonomy_graph, taxonomy_meta = taxonomy(depth=5, individuals_per_class=9, variant="P1")
    manifest = json.loads((ROOT / "examples/bach-queries.json").read_text())
    js, wf, jc = (BACH[name] for name in
                  ("johann-sebastian", "wilhelm-friedemann", "johann-christian"))
    return [
        Case("taxonomy", taxonomy_graph, "L2", taxonomy_meta,
             [("type_move", [(EX.i1_0, RDF.type, EX.C2)], [(EX.i1_0, RDF.type, EX.C1)]),
              ("rule_delete", [], [(EX.C1, RDFS.subClassOf, EX.C0)])], []),
        Case("transitive", transitive(100), "L0", {"edges": 100},
             [("edge_replace", [(EX.a50, EX.p, EX.a52)], [(EX.a50, EX.p, EX.a51)]),
              ("rule_delete", [], [(EX.p, RDF.type, OWL.TransitiveProperty)])], []),
        Case("equality", equality(300), "L1", {"groups": 300},
             [("alias_split", [], [(EX.alias0, EX.key, EX.k0)]),
              ("rule_delete", [], [(EX.key, RDF.type, OWL.InverseFunctionalProperty)])], []),
        Case("bach", read_graph(ROOT / "examples/bach.dlp"), "L3",
             {"source": "examples/bach.dlp", "thesis": "Table 2.5, page 35"},
             [("genius_retract", [], [(js, RDF.type, BACH.Genius)]),
              ("rule_delete", [], [(BACH.ancestorOf, RDFS.subPropertyOf, BACH.inDynasty)])],
             [query for query in manifest["queries"] if query["variant"] == "ontology"]),
        Case("bach-family", read_graph(ROOT / "examples/bach-family.dlp"), "L0",
             {"source": "examples/bach-family.dlp",
              "thesis": "Figure 6.2 / Table 6.1, pages 150-151; Example 6.3.2, page 158"},
             [("facts_update", [(js, BACH.ancestorOf, jc)], [(js, BACH.ancestorOf, wf)]),
              ("rule_delete", [], [(BACH.ancestorOf, RDFS.subPropertyOf, BACH.inDynasty)]),
              ("symmetry_insert", [(BACH.inDynasty, RDF.type, OWL.SymmetricProperty)], [])],
             [query for query in manifest["queries"] if query["variant"] == "family"]),
    ]


def candidate_graph(graph, additions, removals):
    result = Graph()
    result += graph
    for triple in removals:
        result.remove(triple)
    for triple in additions:
        result.add(triple)
    return result


def validate_independent(case, reasoner, graph):
    """Use graph traversal or the fixed published-query manifest, outside timing."""
    assert reasoner.complete and reasoner.consistency == "consistent", reasoner.stats
    if case.name == "taxonomy":
        supers = reachability(set(graph.subject_objects(RDFS.subClassOf)))
        asserted = {(subject, cls) for subject, cls in graph.subject_objects(RDF.type)
                    if str(cls).startswith(str(EX) + "C")}
        expected = asserted | {(individual, parent) for individual, cls in asserted
                               for child, parent in supers if cls == child}
        actual = {(fact.args[0], fact.predicate) for fact in reasoner.engine.facts
                  if len(fact.args) == 1 and isinstance(fact.predicate, URIRef)
                  and str(fact.predicate).startswith(str(EX) + "C")}
        assert actual == expected
    elif case.name == "transitive":
        edges = set(graph.subject_objects(EX.p))
        expected = reachability(edges) if (EX.p, RDF.type, OWL.TransitiveProperty) in graph else edges
        assert reasoner.property_pairs(EX.p) == expected
    elif case.name == "equality":
        for number in range(case.metadata["groups"]):
            original, alias, key = (EX[f"a{number}"], EX[f"alias{number}"], EX[f"k{number}"])
            expected_merge = ((EX.key, RDF.type, OWL.InverseFunctionalProperty) in graph
                              and (alias, EX.key, key) in graph)
            assert (reasoner.engine.normalize(original) ==
                    reasoner.engine.normalize(alias)) == expected_merge
            assert reasoner.entails(original, RDF.type, EX.B)
    elif case.name == "bach-family":
        ancestors = reachability(set(graph.subject_objects(BACH.ancestorOf)))
        assert reasoner.property_pairs(BACH.ancestorOf) == ancestors
        expected = set()
        if (BACH.ancestorOf, RDFS.subPropertyOf, BACH.inDynasty) in graph:
            expected = ancestors
        if (BACH.inDynasty, RDF.type, OWL.SymmetricProperty) in graph:
            expected = expected | {(target, source) for source, target in expected}
        assert reasoner.property_pairs(BACH.inDynasty) == expected


def query(case, reasoner):
    if case.queries:
        return {item["id"]: compact(evaluate_query(reasoner, item)) for item in case.queries}
    if case.name == "taxonomy":
        return {"root_instances": sorted(map(str, reasoner.instances(EX.C0)))}
    if case.name == "transitive":
        return {"from_first": sorted(map(str, reasoner.property_values(EX.a0, EX.p)))}
    return {"instances_B": sorted(map(str, reasoner.instances(EX.B))),
            "alias_type": reasoner.entails(EX.alias0, RDF.type, EX.B)}


def validate_query(case, answer):
    for item in case.queries:
        expected = item["expected"]
        if isinstance(expected, list):
            expected = sorted(expected, key=json.dumps)
        assert answer[item["id"]] == expected, (case.name, item["id"], answer[item["id"]], expected)


def timed_reasoner(case, backend):
    start = time.perf_counter()
    reasoner = Reasoner(case.graph, profile=case.profile, backend=backend)
    construct_seconds = time.perf_counter() - start
    phases = {"construct_seconds": construct_seconds,
              "compile_seconds": reasoner.compile_seconds,
              # Reasoner.materialize_seconds includes Engine construction and
              # native context/cache load, as in the ordinary public API.
              "engine_materialize_seconds": reasoner.materialize_seconds,
              "facts": len(reasoner.engine.facts), "engine_stats": dict(reasoner.engine.stats)}
    start = time.perf_counter()
    answer = query(case, reasoner)
    phases["query_seconds"] = time.perf_counter() - start
    validate_query(case, answer)
    validate_independent(case, reasoner, case.graph)
    phases["answers"] = answer
    return reasoner, phases


def compare_complete(left, right):
    assert left.complete and right.complete
    assert left.consistency == right.consistency == "consistent"
    # Include schema and witnesses; differing unnamed witness IDs are not facts
    # about named individuals. Isomorphism retains their full relational shape.
    left_graph = left.to_graph(include_witnesses=True)
    right_graph = right.to_graph(include_witnesses=True)
    assert isomorphic(left_graph, right_graph)
    return graph_digest(left_graph)


def run_case(case, repeats):
    # Explicitly discarded, validated warm-up on each actual public API path.
    warmups = {backend: timed_reasoner(case, backend)[0] for backend in ("python", "native")}
    compare_complete(warmups["python"], warmups["native"])
    del warmups
    samples, updates = [], {name: [] for name, _, _ in case.updates}
    input_digest = graph_digest(case.graph)
    for repetition in range(repeats):
        order = ("python", "native") if repetition % 2 == 0 else ("native", "python")
        sample, instances = {"repetition": repetition, "order": list(order)}, {}
        for backend in order:
            instances[backend], sample[backend] = timed_reasoner(case, backend)
        assert sample["python"]["answers"] == sample["native"]["answers"]
        sample["closure_sha256"] = compare_complete(instances["python"], instances["native"])
        sample["validation"] = "complete-rdf-isomorphism-and-independent-case-oracle"
        samples.append(sample)
        del instances
        for name, additions, removals in case.updates:
            changed = candidate_graph(case.graph, additions, removals)
            update_sample = {"repetition": repetition, "order": list(order)}
            results = {}
            for backend in order:
                # Each transaction starts from the same original graph. Initial
                # construction is setup and excluded from the update timer.
                result = Reasoner(case.graph, profile=case.profile, backend=backend)
                start = time.perf_counter()
                result.update(add=additions, remove=removals)
                elapsed = time.perf_counter() - start
                results[backend] = result
                update_sample[backend] = {"update_seconds": elapsed,
                                          "engine_stats": dict(result.engine.stats),
                                          "facts": len(result.engine.facts)}
                validate_independent(case, result, changed)
            update_sample["closure_sha256"] = compare_complete(results["python"], results["native"])
            fresh = Reasoner(changed, profile=case.profile, backend="python")
            compare_complete(results["native"], fresh)
            update_sample["validation"] = "paired-complete-closure-and-fresh-python-rebuild"
            updates[name].append(update_sample)
            del results, fresh
    assert graph_digest(case.graph) == input_digest
    return {"name": case.name, "profile": case.profile, "metadata": case.metadata,
            "input_triples": len(case.graph), "input_sha256": input_digest,
            "samples": samples,
            "timings": {key: paired_summary(samples, key) for key in (
                "construct_seconds", "compile_seconds", "engine_materialize_seconds", "query_seconds")},
            "updates": {name: {"samples": values,
                               "timings": paired_summary(values, "update_seconds")}
                        for name, values in updates.items()}}


def protect_output(output, overwrite):
    output = Path(output)
    if output.is_symlink() or output.resolve().is_relative_to((ROOT / "benchmarks/baselines").resolve()):
        raise ValueError("Output must not alias a file or modify immutable baseline evidence")
    if output.exists():
        if not overwrite or not output.is_file() or output.stat().st_nlink != 1:
            raise ValueError("Use a new report path, or --overwrite for this harness's previous report")
        try:
            previous = json.loads(output.read_text())
        except (OSError, ValueError) as exc:
            raise ValueError("Existing output is not a native-backend report") from exc
        if not isinstance(previous, dict) or previous.get("scope") != SCOPE:
            raise ValueError("Only a previous report from this harness may be overwritten")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, choices=[3, 4, 5], default=5)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--cases", nargs="+", choices=["taxonomy", "transitive", "equality",
                                                      "bach", "bach-family"])
    args = parser.parse_args(argv)
    if not __debug__:
        raise RuntimeError("Validation requires Python assertions; do not run with -O")
    protect_output(args.output, args.overwrite)
    before = source_hashes()
    start = datetime.now(timezone.utc).isoformat()
    library = build_native()
    build = json.loads(library.with_name("build.json").read_text())
    try:
        cpu = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"],
                                      text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.SubprocessError):
        cpu = platform.processor()
    report = {
        "scope": SCOPE, "started_utc": start, "repeats": args.repeats,
        "environment": {"python": platform.python_version(),
                        "rdflib": importlib.metadata.version("rdflib"),
                        "os": platform.platform(), "machine": platform.machine(), "cpu": cpu,
                        "hash_seed": os.environ.get("PYTHONHASHSEED", "random"),
                        "gc_enabled": gc.isenabled(), "gc_threshold": list(gc.get_threshold())},
        "native_build": build, "library_sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
        "source_sha256": before,
        "method": {
            "warmup": "one discarded validated public-Reasoner construction/query per backend per case",
            "ordering": "python first on even repetitions; native first on odd; same order for updates",
            "construction": "Reasoner(graph) wall time; graph loading outside timing",
            "engine_materialize": "Reasoner.materialize_seconds includes Engine construction/context load",
            "compile": "Reasoner.compile_seconds; same unmodified OWL compiler",
            "query": "fixed public queries; includes temporary probe reasoning where requested",
            "update": "Reasoner.update wall time including graph copy/recompile/maintenance; fresh original setup excluded",
            "validation": "complete witness-inclusive RDF graph isomorphism every pair; independent traversal/manifest and fresh rebuilds",
            "limitations": "one process and uncontrolled workstation; no memory measurement or independent-run confidence interval",
        },
        "cases": [],
    }
    for case in cases():
        if args.cases and case.name not in args.cases:
            continue
        report["cases"].append(run_case(case, args.repeats))
        print(f"Validated {case.name}: {args.repeats} paired repetitions", flush=True)
    if source_hashes() != before:
        raise RuntimeError("Measured sources changed during benchmark; refusing to retain report")
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    report["validation"] = "passed"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"Saved {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
