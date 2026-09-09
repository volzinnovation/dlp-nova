"""Official LUBM(1,0) reproduction with exact reference-answer validation.

Download/generate: python -m benchmarks.lubm --prepare
Measure: python -m benchmarks.lubm --blocks 3 --output benchmarks/lubm-results.json
The benchmark downloads upstream artifacts into ignored tmp/, with pinned SHA256.
It never edits the preserved b1254c4 baseline or production reasoner sources.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import resource
import shutil
import statistics
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile

from rdflib import Graph, Literal, OWL, RDF, URIRef, Variable
from rdflib.compare import to_canonical_graph
from rdflib.plugins.sparql import prepareQuery

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "b1254c441731ca4fdf32ea83570ff99aaa84ac2a"
ONTOLOGY = "http://swat.cse.lehigh.edu/onto/univ-bench.owl"
OLD_NAMESPACE = "http://www.lehigh.edu/~zhp2/2004/0401/univ-bench.owl#"
CONFIGURATIONS = ("b1254c4", "current-fixed", "current-adaptive")
ARTIFACTS = {
    "uba1.7.zip": ("https://swat.cse.lehigh.edu/projects/lubm/uba1.7.zip",
                   "3d44f468e36b7f3cd532f0f5693a019d020877846397b1fa657367cbd53f380a"),
    "univ-bench.owl": ("https://swat.cse.lehigh.edu/onto/univ-bench.owl",
                       "e6eca926fcb7d6c7925ea0c48f7c5d79abc2818f89e7432fd16561aafeb3f67a"),
    "queries-sparql.txt": ("https://swat.cse.lehigh.edu/projects/lubm/queries-sparql.txt",
                           "c34fd26ecb6fb9f0a2f185d73b72505ef0abf25705d831e6eed3c896557cd104"),
    "answers.zip": ("https://swat.cse.lehigh.edu/projects/lubm/answers.zip",
                    "aedb3d6c36d1f80fb3708e04b5720afe24ac5ac5d2c8e700021f3eed2f1b3307"),
}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest_rows(rows):
    return hashlib.sha256("\n".join(sorted(
        json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in rows
    )).encode()).hexdigest()


def term_record(term):
    # Import inside worker, after selecting the measured package via PYTHONPATH.
    from dlp_reasoner.model import Skolem
    if isinstance(term, Skolem):
        return ["Skolem", term.symbol, [term_record(a) for a in term.args]]
    if isinstance(term, Literal):
        return ["Literal", str(term), str(term.datatype or ""), term.language or ""]
    return [type(term).__name__, str(term)]


def source_hashes(source):
    return {str(path.relative_to(source)): sha(path)
            for path in sorted((source / "src/dlp_reasoner").glob("*.py"))}


def normalized_queries(raw):
    """Repair only published SPARQL punctuation and align the ontology namespace.

    The official text has comma-separated SELECT variables, commas in Q7's
    final triple, and bare absolute IRIs in Q1/Q3. No atoms/projections change.
    """
    result = {}
    blocks = re.split(r"(?m)^# Query(\d+)\s*$", raw)
    require(len(blocks) == 29, "expected precisely 14 official query blocks")
    for index in range(1, len(blocks), 2):
        number, block = int(blocks[index]), blocks[index + 1]
        lines = [line for line in block.splitlines() if not line.lstrip().startswith("#")]
        query = "\n".join(lines).strip().replace(OLD_NAMESPACE, ONTOLOGY + "#")
        query = query.replace(",", "")
        query = re.sub(r"(?<!<)(http://www\.Department[^\s}>]+)", r"<\1>", query)
        require(number not in result, "duplicate official query")
        prepareQuery(query)
        result[number] = query
    require(set(result) == set(range(1, 15)), "missing official query")
    return result


def read_answers(archive):
    result = {}
    with zipfile.ZipFile(archive) as zf:
        for number in range(1, 15):
            lines = zf.read(f"answers_query{number}.txt").decode().splitlines()
            if lines == ["NO ANSWERS."]:
                result[number] = ((), set())
                continue
            columns = tuple(lines[0].split())
            rows = [tuple(line.split()) for line in lines[1:] if line.strip()]
            require(all(len(row) == len(columns) for row in rows), "invalid reference tuple")
            require(len(set(rows)) == len(rows), "duplicate reference tuple")
            result[number] = (columns, set(rows))
    return result


def download_inputs(cache):
    cache.mkdir(parents=True, exist_ok=True)
    for name, (url, expected) in ARTIFACTS.items():
        target = cache / name
        if not target.exists():
            with urllib.request.urlopen(url, timeout=60) as response:
                payload = response.read()
            require(hashlib.sha256(payload).hexdigest() == expected,
                    f"upstream digest changed: {name}")
            target.write_bytes(payload)
        require(sha(target) == expected, f"cached artifact mismatch: {name}")


def prepare(cache):
    download_inputs(cache)
    generator = cache / "uba"
    if not (generator / "classes").is_dir():
        with zipfile.ZipFile(cache / "uba1.7.zip") as archive:
            archive.extractall(generator)  # Archive bytes are pinned above.
    data = cache / "data"
    data.mkdir(exist_ok=True)
    generation = cache / "generation"
    generation.mkdir(exist_ok=True)
    command = ["java", "-cp", str(generator / "classes"),
               "edu.lehigh.swat.bench.uba.Generator", "-univ", "1", "-index", "0",
               "-seed", "0", "-onto", ONTOLOGY]
    if not list(data.glob("University*.owl")):
        run = subprocess.run(command, cwd=generation, capture_output=True, text=True, check=True)
        (cache / "generator-output.txt").write_text(run.stdout + run.stderr)
        # The original UBA bytecode writes Windows separators. Move the resulting
        # files on POSIX; no change to Java source, bytecode, seed or graph bytes.
        created = sorted(cache.glob("generation\\University*.owl"))
        created += sorted(generation.glob("University*.owl"))
        for path in created:
            name = path.name.split("\\")[-1]
            shutil.move(path, data / name)
    files = sorted(data.glob("University*.owl"))
    require(len(files) == 15, "UBA1.7(1,0) must produce 15 department documents")
    queries = normalized_queries((cache / "queries-sparql.txt").read_text())
    (cache / "queries-normalized.json").write_text(json.dumps(queries, indent=2) + "\n")
    answers = read_answers(cache / "answers.zip")
    manifest = {
        "dataset": "LUBM(1,0)", "generator": "Official UBA1.7, unchanged bundled bytecode",
        "generation_command": command, "generator_cwd": str(generation),
        "java": subprocess.run(["java", "-version"], capture_output=True, text=True,
                               check=True).stderr.strip(),
        "artifacts": {name: {"url": url, "sha256": expected}
                      for name, (url, expected) in ARTIFACTS.items()},
        "department_files": {path.name: sha(path) for path in files},
        "query_sha256": {str(k): hashlib.sha256(v.encode()).hexdigest()
                         for k, v in queries.items()},
        "reference_answers": {str(k): {"variables": list(cols), "count": len(rows),
                                       "sha256": digest_rows(rows)}
                              for k, (cols, rows) in answers.items()},
        "normalizations": [
            "Move POSIX filenames containing the original UBA Windows separator; bytes unchanged.",
            "Use the current official ontology namespace in generated data and all 14 queries.",
            "Remove SELECT commas and Q7 triple commas; enclose Q1/Q3 bare IRIs in angle brackets.",
            "Resolve ontology locally, remove owl:imports triples, retain all logical axioms.",
            "Canonicalize ontology blank-node labels; give generated RDF documents stable public IDs.",
        ],
    }
    (cache / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def validate_inputs(cache, manifest):
    for name, expected in manifest["artifacts"].items():
        require(sha(cache / name) == expected["sha256"], f"input changed: {name}")
    for name, expected in manifest["department_files"].items():
        require(sha(cache / "data" / name) == expected, f"dataset changed: {name}")


def load_graph(cache):
    ontology = Graph().parse(cache / "univ-bench.owl", format="xml")
    graph = Graph()
    graph += to_canonical_graph(ontology)
    for path in sorted((cache / "data").glob("University*.owl")):
        graph.parse(path, format="xml", publicID="urn:lubm:document:" + path.name)
    original_count = len(graph)
    imports = list(graph.triples((None, OWL.imports, None)))
    require(len(imports) == 15 and all(str(t[2]) == ONTOLOGY for t in imports),
            "unexpected imports: refuse to remove unresolved ontology references")
    for triple in imports:
        graph.remove(triple)
    return graph, original_count, len(ontology), len(imports)


def prepare_native_query(query):
    """Translate only SELECT basic graph patterns to the existing join evaluator.

    This is an external benchmark adapter, not a general SPARQL implementation.
    RDFLib validates/parses the official query syntax. No additional reasoner
    rule is installed, and queries neither derive nor delete facts.
    """
    from dlp_reasoner.model import Atom, Rule, Var
    algebra = prepareQuery(query).algebra
    require(algebra.name == "SelectQuery" and algebra.p.name == "Project"
            and algebra.p.p.name == "BGP", "only SELECT BGPs are supported")
    def term(value):
        return Var(str(value)) if isinstance(value, Variable) else value
    body = []
    for subject, predicate, obj in algebra.p.p.triples:
        require(isinstance(predicate, URIRef), "variable predicates are unsupported")
        if predicate == RDF.type:
            require(isinstance(obj, URIRef), "variable class names are unsupported")
            body.append(Atom(obj, (term(subject),)))
        else:
            body.append(Atom(predicate, (term(subject), term(obj))))
    return tuple(Var(str(value)) for value in algebra.PV), Rule(None, tuple(body))


def native_answers(engine, variables, rule):
    result = set()
    for binding in engine._solutions(rule):
        row = tuple(binding[value] for value in variables)
        if all(isinstance(value, (URIRef, Literal)) for value in row):
            result.add(tuple(str(value) for value in row))
    return result


def worker(cache, configuration):
    from dlp_reasoner import Reasoner
    from dlp_reasoner.engine import Engine
    from dlp_reasoner.model import ProfileError
    import dlp_reasoner
    import rdflib

    manifest = json.loads((cache / "manifest.json").read_text())
    validate_inputs(cache, manifest)
    if configuration == "current-adaptive":
        require(hasattr(Engine, "_unary_strategy"), "adaptive strategy absent from selected code")
        Engine._unary_strategy = "adaptive"
    queries = normalized_queries((cache / "queries-sparql.txt").read_text())
    prepared = {k: prepare_native_query(q) for k, q in queries.items()}
    references = read_answers(cache / "answers.zip")
    started = time.perf_counter()
    graph, raw_count, ontology_count, import_count = load_graph(cache)
    parse_seconds = time.perf_counter() - started
    started = time.perf_counter()
    reasoner = Reasoner(graph, profile="L3")
    reasoner_seconds = time.perf_counter() - started
    require(reasoner.complete and reasoner.consistency == "consistent", "incomplete/inconsistent")
    # Full input graph is retained. This L3 test is not an RDFS/OWL RL projection.
    from dlp_reasoner.compiler import compile_graph
    try:
        compile_graph(Graph().parse(cache / "univ-bench.owl", format="xml"), profile="L2")
    except ProfileError as exc:
        l2_rejection = str(exc)
    else:
        raise RuntimeError("the full LUBM ontology unexpectedly passed L2")
    started = time.perf_counter()
    closure = reasoner.to_graph(include_schema=False, include_witnesses=True,
                               expand_equality=False)
    export_seconds = time.perf_counter() - started
    # There are no equalities in this ontology/data; verify rather than assume.
    require(reasoner.stats["equality_merges"] == 0, "unexpected equality requires alias expansion")
    materialization_stats = reasoner.stats.copy()
    observations = []
    for number, (variables, rule) in prepared.items():
        columns, expected = references[number]
        require(not columns or tuple(v.name for v in variables) == columns,
                "reference variable mismatch")
        started = time.perf_counter()
        rows = native_answers(reasoner.engine, variables, rule)
        elapsed = time.perf_counter() - started
        missing, extra = expected - rows, rows - expected
        observations.append({"query": number, "seconds": elapsed, "answers": len(rows),
                             "reference_answers": len(expected), "sha256": digest_rows(rows),
                             "missing": len(missing), "unexpected": len(extra),
                             "exact_match": not missing and not extra,
                             "missing_examples": sorted(missing)[:3],
                             "unexpected_examples": sorted(extra)[:3]})
    facts = reasoner.engine.facts
    fact_rows = [[term_record(f.predicate), [term_record(a) for a in f.args]] for f in facts]
    named_rows = [[term_record(f.predicate), [term_record(a) for a in f.args]] for f in facts
                  if str(f.predicate).startswith(ONTOLOGY + "#")
                  and all(isinstance(a, (URIRef, Literal)) for a in f.args)]
    full_closure_digest, named_closure_digest = digest_rows(fact_rows), digest_rows(named_rows)
    result = {
        "configuration": configuration, "python": sys.version, "rdflib": rdflib.__version__,
        "package_path": str(Path(dlp_reasoner.__file__).resolve()),
        "source_sha256": source_hashes(Path(dlp_reasoner.__file__).resolve().parents[2]),
        "driver_sha256": sha(__file__), "input_manifest_sha256": sha(cache / "manifest.json"),
        "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
        "raw_graph_triples": raw_count, "ontology_triples": ontology_count,
        "resolved_imports": import_count, "input_triples": len(graph),
        "input_sha256": digest_rows([[term_record(t) for t in triple] for triple in graph]),
        "parse_seconds": parse_seconds, "reasoner_seconds": reasoner_seconds,
        "parse_and_reasoner_seconds": parse_seconds + reasoner_seconds,
        "compile_seconds": reasoner.compile_seconds,
        "materialize_seconds": reasoner.materialize_seconds,
        "rdf_export_seconds": export_seconds, "query_seconds": sum(q["seconds"] for q in observations),
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                          * (1 if sys.platform == "darwin" else 1024),
        "full_closure_sha256": full_closure_digest, "named_ub_facts": len(named_rows),
        "named_ub_closure_sha256": named_closure_digest, "exported_triples": len(closure),
        "l2_rejection": l2_rejection, "stats": materialization_stats, "queries": observations,
        "all_reference_answers_match": all(q["exact_match"] for q in observations),
    }
    return result


def baseline_checkout(cache):
    destination = cache / "baseline-b1254c4"
    if not destination.exists():
        archive = subprocess.run(["git", "archive", BASELINE, "src/dlp_reasoner"], cwd=ROOT,
                                 capture_output=True, check=True).stdout
        destination.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as tf:
            tf.extractall(destination, filter="data")
    # Never trust an old cache silently: compare every byte to the immutable commit.
    for path in sorted((destination / "src/dlp_reasoner").glob("*.py")):
        relative = str(path.relative_to(destination))
        expected = subprocess.run(["git", "show", BASELINE + ":" + relative], cwd=ROOT,
                                  capture_output=True, check=True).stdout
        require(path.read_bytes() == expected, f"baseline checkout drift: {relative}")
    return destination


def markdown(report):
    rows = ["# Official LUBM(1,0) evaluation", "",
            "UBA1.7, index 0, seed 0; full official ontology under L3; all 14 official reference answer sets.",
            "", "These are new same-host measurements, separate from the frozen b1254c4 thesis suite.",
            "Queries use RDFLib parsing plus the existing DLP indexed BGP join evaluator; this adapter is not a general SPARQL frontend.",
            "", "| Configuration | Parse + reasoner(s) | Compile(s) | Materialize(s) | Export(s) | All queries(s) | PeakRSS(MiB) |", "|---|---:|---:|---:|---:|---:|---:|"]
    for name, summary in report["summary"].items():
        values = [summary[k]["median"] for k in (
            "parse_and_reasoner_seconds", "compile_seconds", "materialize_seconds",
            "rdf_export_seconds", "query_seconds", "peak_rss_bytes")]
        rows.append(f"| {name} | " + " | ".join(f"{v:.3f}" for v in values[:-1])
                    + f" | {values[-1] / 2**20:.1f} |")
    rows += ["", "| Query | Official answers | Exact match(all workers) | Baseline(ms) | Current fixed(ms) | Adaptive(ms) |",
             "|---|---:|---|---:|---:|---:|"]
    for number in range(1, 15):
        query = [w["queries"][number - 1] for w in report["workers"]]
        medians = [statistics.median(w["queries"][number - 1]["seconds"] for w in report["workers"]
                                    if w["configuration"] == config) * 1000
                   for config in CONFIGURATIONS]
        rows.append(f"| Q{number} | {query[0]['reference_answers']} | "
                    f"{'yes' if all(q['exact_match'] for q in query) else 'NO'} | "
                    + " | ".join(f"{v:.3f}" for v in medians) + " |")
    rows += ["", "## Interpretation and limits", "",
             f"{len(report['workers'])} fresh processes; balanced configuration order; three repeats per configuration by default. "
             "Raw observations, process/source hashes, upstream artifact hashes and generated-file hashes are in the JSON.",
             "The ontology's existential consequents require L3. No logical axioms are removed; imports are resolved locally. "
             "Query bindings include only named individuals/literal values, as in the official extensional answer files. "
             "Skolem witnesses are still present throughout full materialization.",
             "Official query punctuation errors and the old namespace are normalized without changing atoms/projections. "
             "Reference files use lexical strings; full typed RDF-term digests separately validate closure stability.",
             "All14 query answer sets, not just cardinalities, are compared with the official reference files. "
             "Repeated workers additionally compare full internal closures within each configuration and named UB closures across configurations; "
             "this is not an independent proof of every unqueried consequence.",
             "The two experimental certificate switches concern deletions and are inactive in this static workload. "
             "The adaptive unary candidate is compared with the current fixed default. "
             "Three repeats and one small university qualify correctness/performance; they do not establish scalability or statistical superiority.",
             "Cold means fresh Python process; OS filesystem caches are not flushed. Query preparation is outside timing; "
             "each BGP is run once per worker through Engine._solutions and fully consumed inside its timer. Parse, reasoner, RDF export and query times are separated. "
             "Peak RSS includes loading, materialization, export, queries and validation in that process.",
             "Absolute wall times cannot be ranked against published systems on different hardware, software, storage, entailment regimes or query pipelines.",
             "", "## Reproduce", "", "```sh", "python -m benchmarks.lubm --prepare",
             "python -m benchmarks.lubm --blocks 3 --output /tmp/lubm-reproduction.json", "```", "",
             "Sources: [official LUBM project](https://swat.cse.lehigh.edu/projects/lubm/), "
             "[official reference answers](https://swat.cse.lehigh.edu/projects/lubm/answers.htm), "
             "[official ontology](https://swat.cse.lehigh.edu/onto/univ-bench.owl), "
             "[official query text](https://swat.cse.lehigh.edu/projects/lubm/queries-sparql.txt).", ""]
    return "\n".join(rows)


def run(cache, output, blocks):
    require(blocks >= 3 and blocks % 3 == 0, "use a multiple of 3 blocks for balanced order")
    require(not output.exists() and not output.with_suffix(".md").exists(), "refuse to overwrite results")
    manifest = prepare(cache)
    baseline = baseline_checkout(cache)
    current_sources = source_hashes(ROOT)
    driver_hash = sha(__file__)
    report = {
        "schema_version": 1, "benchmark": "official-LUBM-1-0-L3-v1",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_commit": BASELINE,
        "current_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                         capture_output=True, text=True, check=True).stdout.strip(),
        "driver_sha256": driver_hash, "platform": platform.platform(),
        "machine": platform.machine(), "cpu_count": os.cpu_count(), "manifest": manifest,
        "protocol": {"blocks": blocks, "timeout_seconds": 180, "profile": "L3",
                     "configurations": list(CONFIGURATIONS), "seeds": list(range(4000, 4000 + blocks)),
                     "ordering": "rotate configurations by block index; balanced Latin square",
                     "timing": "fresh process per configuration; perf_counter; no instrumentation",
                     "query_timing": "RDFLib-parsed BGP via Engine._solutions; full result materialization; named bindings",
                     "validation": "exact 14 official answers; full repeat closure hashes; cross-config named closure",
                     "host_note": "coordinated quiet measurement window; OS caches not flushed"},
        "workers": [],
    }
    protocol_path = output.with_name(output.stem + "-protocol.json")
    require(not protocol_path.exists(), "refuse to overwrite protocol")
    protocol_path.write_text(json.dumps(report, indent=2) + "\n")
    for block in range(blocks):
        order = CONFIGURATIONS[block % 3:] + CONFIGURATIONS[:block % 3]
        for position, config in enumerate(order):
            require(source_hashes(ROOT) == current_sources and sha(__file__) == driver_hash,
                    "source changed during measurement")
            selected = baseline if config == "b1254c4" else ROOT
            env = {**os.environ, "PYTHONHASHSEED": str(4000 + block),
                   "PYTHONPATH": os.pathsep.join([str(selected / "src"), str(ROOT)])}
            command = [sys.executable, "-m", "benchmarks.lubm", "--worker", config,
                       "--cache", str(cache)]
            completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                                       text=True, timeout=180, check=True)
            observation = json.loads(completed.stdout)
            observation.update(block=block, position=position, command=command)
            require(observation["source_sha256"] == source_hashes(selected), "wrong measured source")
            require(observation["all_reference_answers_match"], "official reference answer mismatch")
            if report["workers"]:
                prior = report["workers"][0]
                require(observation["input_sha256"] == prior["input_sha256"], "input graph drift")
                require(observation["named_ub_closure_sha256"] == prior["named_ub_closure_sha256"],
                        "named logical closure mismatch across configurations")
            for prior in report["workers"]:
                if prior["configuration"] == config:
                    require(observation["full_closure_sha256"] == prior["full_closure_sha256"],
                            "full closure mismatch across repeats")
            report["workers"].append(observation)
            print(f"{block + 1}/{blocks} {config}: {observation['materialize_seconds']:.3f}s "
                  f"materialization;14/14 exact answer sets", flush=True)
    keys = ("parse_seconds", "reasoner_seconds", "parse_and_reasoner_seconds", "compile_seconds",
            "materialize_seconds", "rdf_export_seconds", "query_seconds", "peak_rss_bytes")
    report["summary"] = {config: {key: {
        "median": statistics.median(w[key] for w in report["workers"] if w["configuration"] == config),
        "minimum": min(w[key] for w in report["workers"] if w["configuration"] == config),
        "maximum": max(w[key] for w in report["workers"] if w["configuration"] == config),
    } for key in keys} for config in CONFIGURATIONS}
    report["paired_ratios"] = {}
    for config in CONFIGURATIONS[1:]:
        report["paired_ratios"][config + "/b1254c4"] = {}
        for key in ("parse_and_reasoner_seconds", "materialize_seconds", "query_seconds"):
            ratios = []
            for block in range(blocks):
                matched = {w["configuration"]: w for w in report["workers"] if w["block"] == block}
                ratios.append(matched[config][key] / matched["b1254c4"][key])
            report["paired_ratios"][config + "/b1254c4"][key] = {
                "raw": ratios, "median": statistics.median(ratios),
                "minimum": min(ratios), "maximum": max(ratios)}
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    report["all_reference_answers_match"] = True
    report["protocol_sha256"] = sha(protocol_path)
    output.write_text(json.dumps(report, indent=2) + "\n")
    output.with_suffix(".md").write_text(markdown(report))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / "tmp/lubm-official")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--worker", choices=CONFIGURATIONS)
    parser.add_argument("--blocks", type=int, default=3)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/lubm-results.json")
    args = parser.parse_args()
    cache = args.cache.resolve()
    if args.worker:
        print(json.dumps(worker(cache, args.worker)))
    elif args.prepare:
        print(json.dumps(prepare(cache), indent=2))
    else:
        run(cache, args.output.resolve(), args.blocks)


if __name__ == "__main__":
    main()
