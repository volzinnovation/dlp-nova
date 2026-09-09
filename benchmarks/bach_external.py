"""Source-backed Bach comparisons: exact OWL answers and positive-family updates.

Prepare and smoke before a quiet, sequential run. Saved results are never replaced.
The baseline package is frozen at b1254c4; current source is archived separately.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import io
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tarfile
import time

from rdflib import Graph, OWL, RDF, RDFS, URIRef
from rdflib.compare import isomorphic

from benchmarks.bach import BACH, PREFIXES, QUERY_FILE, reachability, term
from benchmarks.lubm import BASELINE, require, sha, source_hashes
from benchmarks.owl_bridge import classpath, prepare_runtime
from benchmarks.zodiac import source_snapshot
from benchmarks.zodiac_native import prepare_native

ROOT = Path(__file__).resolve().parents[1]
ARMS = ("b1254c4", "candidate", "hermit", "zodiac-native")
SCENARIOS = ("initial", "fact-replace", "rule-remove", "symmetry-insert")
DRIVERS = ("benchmarks/bach_external.py", "benchmarks/BachOwlBridge.java",
           "benchmarks/bach_zodiac.py", "benchmarks/bach.py", "benchmarks/lubm.py",
           "benchmarks/owl_bridge.py", "benchmarks/zodiac.py", "benchmarks/zodiac_native.py")


class WorkerFailure(ValueError):
    def __init__(self, message, details):
        super().__init__(message)
        self.details = details


def normalized(value):
    """Canonical full-IRI answers; never compare counts alone."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (tuple, list, set, frozenset)):
        def row(v):
            if isinstance(v, (tuple, list)):
                return [row(item) for item in v]
            return str(term(str(v)))
        return sorted((row(v) for v in value), key=lambda v: json.dumps(v))
    return str(term(str(value)))


def changes(scenario):
    old = (BACH["johann-sebastian"], BACH.ancestorOf, BACH["wilhelm-friedemann"])
    new = (BACH["johann-sebastian"], BACH.ancestorOf, BACH["johann-christian"])
    inclusion = (BACH.ancestorOf, RDFS.subPropertyOf, BACH.inDynasty)
    symmetry = (BACH.inDynasty, RDF.type, OWL.SymmetricProperty)
    return {"initial": ([], []), "fact-replace": ([new], [old]),
            "rule-remove": ([], [inclusion]), "symmetry-insert": ([symmetry], [])}[scenario]


def family_graph(scenario):
    graph = Graph().parse(ROOT / "examples/bach-family.ttl")
    add, remove = changes(scenario)
    for triple in remove:
        graph.remove(triple)
    for triple in add:
        graph.add(triple)
    return graph


def family_answers(scenario, queries):
    graph = family_graph(scenario)
    ancestor = reachability(set(graph.subject_objects(BACH.ancestorOf)))
    dynasty = set() if scenario == "rule-remove" else set(ancestor)
    if scenario == "symmetry-insert":
        dynasty |= {(b, a) for a, b in dynasty}
    pairs = {BACH.ancestorOf: ancestor, BACH.inDynasty: dynasty}
    output = {}
    for query in queries:
        args, method = [term(v) for v in query["arguments"]], query["method"]
        if method == "property_pairs":
            value = pairs[args[0]]
        elif method == "property_values":
            value = {b for a, b in pairs[args[1]] if a == args[0]}
        elif method == "entails":
            value = (args[0], args[2]) in pairs[args[1]]
        elif method == "is_symmetric":
            value = args[0] == BACH.inDynasty and scenario == "symmetry-insert"
        elif method == "is_transitive":
            value = args[0] == BACH.ancestorOf
        else:
            raise ValueError("Unsupported family oracle method: " + method)
        output[query["id"]] = normalized(value)
    return output


def prepare(cache, hermit_cache, native_cache):
    cache.mkdir(parents=True, exist_ok=True)
    require(isomorphic(Graph().parse(ROOT / "examples/bach.owl"),
                       Graph().parse(ROOT / "examples/bach.ttl")), "Bach RDF syntax mismatch")
    manifest = json.loads(QUERY_FILE.read_text())
    queries = {v: [{k: val for k, val in q.items() if k != "expected"}
                   for q in manifest["queries"] if q["variant"] == v]
               for v in ("ontology", "family")}
    for property_name in ("ancestorOf", "inDynasty"):
        queries["family"].append({"id": "all-" + property_name, "method": "property_pairs",
                                  "arguments": [property_name], "variant": "family"})
    for query in queries["ontology"]:
        if query["method"] != "instances_expression":
            continue
        prefix = "\n".join(f"@prefix {p}: <{ns}> ." for p, ns in PREFIXES.items())
        marker = URIRef("urn:bach:expression:" + query["id"])
        graph = Graph().parse(data=prefix + f"\n@prefix : <{BACH}> .\n"
                              + f"<{marker}> owl:equivalentClass {query['expression']} .",
                              format="turtle")
        path = cache / (query["id"] + ".owl")
        if not path.exists():
            graph.serialize(path, format="xml")
        require(isomorphic(graph, Graph().parse(path)), "Expression helper drift")
        query.update(expression_file=str(path), expression_class=str(marker))
    expected = {"ontology": {q["id"]: normalized(q["expected"]) for q in manifest["queries"]
                              if q["variant"] == "ontology"}}
    inputs = {"ontology": ROOT / "examples/bach.owl"}
    for scenario in SCENARIOS:
        graph = family_graph(scenario)
        path = cache / ("family-" + scenario + ".owl")
        if not path.exists():
            graph.serialize(path, format="xml")
        require(isomorphic(graph, Graph().parse(path)), "Family snapshot drift")
        inputs[scenario] = path
        expected[scenario] = family_answers(scenario, queries["family"])
    runtime = prepare_runtime(hermit_cache)
    classes = hermit_cache / "classes"
    classes.mkdir(exist_ok=True)
    subprocess.run(["javac", "-cp", classpath(hermit_cache, runtime), "-d", str(classes),
                    str(ROOT / "benchmarks/BachOwlBridge.java")], check=True, capture_output=True)
    sources = {"b1254c4": source_snapshot(cache, BASELINE), "candidate": source_snapshot(cache)}
    return {"queries": queries, "expected": expected, "inputs": {k: str(v) for k, v in inputs.items()},
            "runtime": runtime, "native": prepare_native(native_cache),
            "java": subprocess.run(["java", "-version"], capture_output=True, text=True, check=True).stderr.strip(),
            "sources": {k: str(v) for k, v in sources.items()},
            "source_sha256": {k: source_hashes(v) for k, v in sources.items()},
            "java_classes_sha256": {p.name: sha(p) for p in classes.glob("BachOwlBridge*.class")}}


def python_worker(request):
    from dlp_reasoner import Reasoner
    import dlp_reasoner
    package = Path(dlp_reasoner.__file__).resolve().parents[2]
    queries = request["queries"]
    started = time.perf_counter()
    expressions = {}
    for query in queries:
        if query["method"] == "instances_expression":
            helper = Graph().parse(query["expression_file"])
            marker = URIRef(query["expression_class"])
            expression = helper.value(marker, OWL.equivalentClass)
            require(expression is not None, "Missing query expression")
            helper.remove((marker, OWL.equivalentClass, expression))
            expressions[query["id"]] = (helper, expression)
    preparation = time.perf_counter() - started
    started = time.perf_counter()
    graph = Graph().parse(request["ontology"])
    load = time.perf_counter() - started
    started = time.perf_counter()
    reasoner = Reasoner(graph, profile="L3" if request["case"] == "ontology" else "L0")
    construct = time.perf_counter() - started

    def observe(name):
        started = time.perf_counter()
        consistent = reasoner.consistency == "consistent"
        complete = reasoner.complete
        consistency = time.perf_counter() - started
        require(consistent and complete, "Bach reasoning incomplete or inconsistent")
        observations = []
        for query in queries:
            started = time.perf_counter()
            if query["id"] in expressions:
                helper, expression = expressions[query["id"]]
                expanded = Graph()
                expanded += reasoner.graph
                expanded += helper
                probe = Reasoner(expanded, profile=reasoner.profile)
                value = probe.instances(expression)
                require(probe.complete and probe.consistency == "consistent", "Expression incomplete")
            else:
                value = getattr(reasoner, query["method"])(*(term(v) for v in query["arguments"]))
            answer = normalized(value)
            elapsed = time.perf_counter() - started
            observations.append({"id": query["id"], "method": query["method"],
                                 "answer": answer, "seconds": elapsed})
        return {"state": name, "queries": observations, "consistent": consistent,
                "complete": complete, "consistency_seconds": consistency,
                "query_seconds": sum(q["seconds"] for q in observations)}

    initial = observe("initial")
    initial.update(query_preparation_seconds=preparation, load_seconds=load, construct_seconds=construct)
    initial["task_seconds"] = preparation + load + construct + initial["consistency_seconds"] + initial["query_seconds"]
    states = [initial]
    if request["mode"] == "incremental":
        add, remove = changes(request["case"])
        for name, a, r in (("updated", add, remove), ("restored", remove, add)):
            started = time.perf_counter()
            reasoner.update(add=a, remove=r)
            elapsed = time.perf_counter() - started
            state = observe(name)
            state.update(update_seconds=elapsed)
            state["task_seconds"] = elapsed + state["consistency_seconds"] + state["query_seconds"]
            states.append(state)
    return {"states": states, "source_sha256": source_hashes(package), "python": sys.version,
            "pythonhashseed": os.environ.get("PYTHONHASHSEED")}


def validate_worker(worker, expected):
    require(len(worker["states"]) == len(expected), "Unexpected state count")
    for state, answers in zip(worker["states"], expected, strict=True):
        require(state.get("consistent", True) and state.get("complete", True), "Invalid reasoning status")
        observations = state["queries"]
        require(len(observations) == len(answers), "Missing or duplicate questions")
        actual = {q["id"]: normalized(q["answer"]) for q in observations}
        require(actual == answers, "Wrong Bach answers: " + repr({k: (actual.get(k), v)
                for k, v in answers.items() if actual.get(k) != v}))
        require(math.isfinite(state["task_seconds"]) and state["task_seconds"] > 0, "Invalid timing")
        state["exact_answers_match"] = True


def execute(arm, mode, case, metadata, cache, hermit_cache, native_cache, seed):
    ontology = metadata["inputs"]["initial" if mode == "incremental" else case]
    queries = metadata["queries"]["ontology" if case == "ontology" else "family"]
    request = {"namespace": str(BACH), "ontology": ontology, "queries": queries,
               "case": case, "mode": mode, "native_cache": str(native_cache)}
    path = cache / "worker-request.json"
    path.write_text(json.dumps(request))
    env = dict(os.environ, PYTHONHASHSEED=str(seed))
    if arm == "hermit":
        command = ["java", "-Xms64m", "-Xmx2g", "-cp", classpath(hermit_cache, metadata["runtime"], True),
                   "BachOwlBridge", str(path)]
    else:
        package = metadata["sources"].get(arm, metadata["sources"]["candidate"])
        env["PYTHONPATH"] = str(Path(package) / "src") + os.pathsep + str(ROOT)
        command = [sys.executable, "-m", "benchmarks.bach_external", "worker", "--arm", arm,
                   "--request", str(path)]
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    elapsed = time.perf_counter() - started
    if completed.returncode != 0:
        raise WorkerFailure(f"{arm}/{mode}/{case} exited {completed.returncode}",
                            {"process_seconds": elapsed, "stdout": completed.stdout,
                             "stderr": completed.stderr, "returncode": completed.returncode})
    try:
        result = json.loads(completed.stdout)
    except ValueError as error:
        raise WorkerFailure(str(error), {"process_seconds": elapsed, "stdout": completed.stdout,
                                        "stderr": completed.stderr, "returncode": completed.returncode}) from error
    if arm == "hermit":
        result["states"][0]["task_seconds_excluding_query_preparation"] = result["states"][0]["task_seconds"]
        result["states"][0]["task_seconds"] = result["states"][0]["prepared_task_seconds"]
    keys = [case] if mode == "static" else ["initial", case, "initial"]
    result.update(arm=arm, mode=mode, case=case, process_seconds=elapsed, stderr=completed.stderr)
    try:
        if arm in metadata["source_sha256"]:
            require(result["source_sha256"] == metadata["source_sha256"][arm], "Worker imported wrong source")
        validate_worker(result, [metadata["expected"][key] for key in keys])
    except (ValueError, RuntimeError) as error:
        raise WorkerFailure(str(error), result) from error
    return result


def summaries(workers):
    result = {}
    for mode in ("static", "incremental"):
        for case in ("ontology", *SCENARIOS):
            selected = [w for w in workers if w["mode"] == mode and w["case"] == case]
            if not selected:
                continue
            cells = {}
            for arm in ARMS:
                rows = [w for w in selected if w["arm"] == arm]
                if not rows:
                    continue
                failed = sum(w.get("status") == "failed" for w in rows)
                if failed:
                    cells[arm] = {"n": len(rows), "failed": failed, "performance_ranked": False}
                    continue
                index = 0 if mode == "static" else 1
                values = [w["states"][index]["task_seconds"] for w in rows]
                cells[arm] = {"n": len(values), "median_seconds": statistics.median(values),
                              "min_seconds": min(values), "max_seconds": max(values),
                              "process_median_seconds": statistics.median(w["process_seconds"] for w in rows)}
                if arm != "candidate":
                    candidate = {w["block"]: w for w in selected if w["arm"] == "candidate"}
                    if any(w.get("status") == "failed" for w in candidate.values()):
                        continue
                    ratios = [w["states"][index]["task_seconds"] /
                              candidate[w["block"]]["states"][index]["task_seconds"] for w in rows]
                    cells[arm]["paired_ratio_over_candidate"] = statistics.median(ratios)
            result[mode + "/" + case] = cells
    return result


def markdown(report):
    lines = ["# Bach comparisons with HermiT and ZodiacEdge", "",
             "Original-scale dissertation examples. Exact answers are checked in every completed state.", "",
             "Times include input preparation, reasoning and all requested answers; milliseconds.",
             "Incremental times include the change and nine updated answers; setup is separate.", "",
             "| Task | b1254c4 | Current | HermiT | ZodiacEdge |", "|---|---:|---:|---:|---:|"]
    for name, cells in report["summary"].items():
        values = [(f"FAILED ({cells[a]['failed']}/{cells[a]['n']})" if cells[a].get("failed") else
                   f"{1000*cells[a]['median_seconds']:.3f}") if a in cells else "N/A" for a in ARMS]
        lines.append("| " + name + " | " + " | ".join(values) + " |")
    lines += ["", f"{report['blocks']} repeated blocks; {len(report['workers'])} fresh processes, executed sequentially.",
              "HermiT reconstructs each static state. No HermiT incremental timing is claimed.",
              "ZodiacEdge executes the complete positive family rules; the full existential OWL ontology is unsupported.",
              "The 25 full-ontology questions and nine family questions include exact complete pair sets.",
              "Each incremental scenario starts from the original input and attempts to return to it; all completed states are checked.",
              "Any failed worker disqualifies its entire configuration/task from timing rankings; all failures remain in the raw data.",
              "ZodiacEdge's mixed fact replacement uses deletion then insertion, with both calls timed.",
              "Schema questions use native fresh-instance probes; they are not inferred from observed pairs.",
              "The preserved b1254c4 package is newly measured here; its historical saved baseline has no Bach results.",
              "These tiny examples establish source fidelity and illustrate overheads, not large-scale superiority.",
              "Raw JSON retains every phase, question, exact answer, process duration and paired ratio.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "smoke", "run", "worker"))
    parser.add_argument("--cache", type=Path, default=ROOT / "tmp/bach-external")
    parser.add_argument("--hermit-cache", type=Path, default=ROOT / "tmp/owl-bridge")
    parser.add_argument("--native-cache", type=Path, default=ROOT / "tmp/zodiac-native")
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/bach-external-results.json")
    parser.add_argument("--blocks", type=int, default=12)
    parser.add_argument("--arm", choices=ARMS)
    parser.add_argument("--request", type=Path)
    args = parser.parse_args()
    if args.command == "worker":
        request = json.loads(args.request.read_text())
        if args.arm == "zodiac-native":
            from benchmarks.bach_zodiac import incremental_worker, static_worker
            if request["mode"] == "static":
                result = static_worker(request["native_cache"], request["ontology"], request["queries"])
            else:
                result = incremental_worker(request["native_cache"], request["ontology"],
                                            request["case"], request["queries"])
        else:
            result = python_worker(request)
        print(json.dumps(result))
        return
    metadata = prepare(args.cache, args.hermit_cache, args.native_cache)
    if args.command == "prepare":
        print(json.dumps(metadata, indent=2))
        return
    jobs = [("static", c, ARMS[:3] if c == "ontology" else ARMS) for c in ("ontology", *SCENARIOS)]
    jobs += [("incremental", c, ("b1254c4", "candidate", "zodiac-native")) for c in SCENARIOS[1:]]
    blocks = 1 if args.command == "smoke" else args.blocks
    require(blocks > 0, "Positive block count required")
    report = {"created_utc": datetime.now(timezone.utc).isoformat(), "blocks": blocks,
              "baseline_commit": BASELINE, "metadata": metadata, "workers": [],
              "platform": platform.platform(), "processor": platform.processor(), "python": sys.version,
              "driver_sha256": {p: sha(ROOT / p) for p in DRIVERS},
              "source_inputs_sha256": {p: sha(ROOT / p) for p in ("docs/Volltext.pdf", "examples/bach.owl",
                                         "examples/bach.ttl", "examples/bach-family.ttl", "examples/bach-queries.json",
                                         "benchmarks/bach-native-deletion-diagnostic.json")},
              "baseline_saved_sha256": sha(ROOT / "benchmarks/baselines/b1254c4/results.json"),
              "input_sha256": {p: sha(Path(p)) for p in [*metadata["inputs"].values(),
                               *(q["expression_file"] for q in metadata["queries"]["ontology"] if "expression_file" in q)]},
              "protocol": {"order": "Rotate arm order by block plus job index; jobs in listed order",
                           "jobs": jobs, "hashseeds": list(range(7100, 7100 + blocks)),
                           "task": "Input/query preparation, conversion/indexing, construction or update, consistency when supplied, complete sorted answers; phase sum",
                           "process": "Fresh process including module/runtime startup, native bootstrap, validation, serialization and shutdown; caches not purged",
                           "schema_queries": "Native Zodiac uses fresh canonical facts with active rules; all preparation and probe reasoning charged to query",
                           "expressions": "Helpers parsed before input; Python API requires query-specific graph copy/reconstruction, included in query time",
                           "incremental": "Original, one change, inverse change. Native fact replacement is sequential delete+insert. HermiT static rebuild only.",
                           "unsupported": "ZodiacEdge full Table2.5 OWL ontology",
                           "prior_correctness_finding": "Untimed direct-native deletion checks already exposed intermittent loss of surviving ancestry; retained diagnostic is hashed; formal seeds not selected by outcomes",
                           "scale": "Unmodified original ontology/family; no synthetic replicas"}}
    output = args.output if args.command == "run" else args.cache / "smoke.json"
    if args.command == "run":
        output.parent.mkdir(parents=True, exist_ok=True)
        protocol_path = output.with_name(output.stem + "-protocol.json")
        require(not output.exists() and not protocol_path.exists(), "Refusing to replace saved evidence")
        archive_path = output.with_name("bach-external-source.tar.gz")
        require(not archive_path.exists(), "Refusing to replace source archive")
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            for name in sorted(metadata["source_sha256"]["candidate"]):
                data = (Path(metadata["sources"]["candidate"]) / name).read_bytes()
                item = tarfile.TarInfo(name)
                item.size, item.mtime, item.mode = len(data), 0, 0o644
                archive.addfile(item, io.BytesIO(data))
        with archive_path.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
                stream.write(buffer.getvalue())
        report.update(candidate_archive=str(archive_path.relative_to(ROOT) if archive_path.is_relative_to(ROOT) else archive_path),
                      candidate_archive_sha256=sha(archive_path))
        inputs_archive = output.with_name("bach-external-inputs.tar.gz")
        require(not inputs_archive.exists(), "Refusing to replace input archive")
        with tarfile.open(inputs_archive, "w:gz") as archive:
            for filename in sorted(report["input_sha256"]):
                archive.add(filename, arcname=Path(filename).name)
        report.update(inputs_archive=str(inputs_archive.relative_to(ROOT) if inputs_archive.is_relative_to(ROOT) else inputs_archive),
                      inputs_archive_sha256=sha(inputs_archive))
        protocol_path.write_text(json.dumps(report, indent=2) + "\n")
        report["protocol_sha256"] = sha(protocol_path)
    for block in range(blocks):
        for index, (mode, case, arms) in enumerate(jobs):
            offset = (block + index) % len(arms)
            for position, arm in enumerate(arms[offset:] + arms[:offset]):
                try:
                    result = execute(arm, mode, case, metadata, args.cache, args.hermit_cache,
                                     args.native_cache, 7100 + block)
                    result.update(block=block, position=position, status="validated")
                    report["workers"].append(result)
                except Exception as error:
                    report["workers"].append({"block": block, "position": position, "arm": arm,
                                               "mode": mode, "case": case, **getattr(error, "details", {}),
                                               "status": "failed", "error": str(error)})
                output.write_text(json.dumps(report, indent=2) + "\n")
        failures = sum(w["status"] == "failed" for w in report["workers"])
        print(f"Completed block {block + 1}/{blocks}: {len(report['workers'])} processes, {failures} failures", flush=True)
    require(report["driver_sha256"] == {p: sha(ROOT / p) for p in DRIVERS}, "Driver changed during run")
    require(report["input_sha256"] == {p: sha(Path(p)) for p in report["input_sha256"]}, "Input drift")
    require(report["source_inputs_sha256"] == {p: sha(ROOT / p) for p in report["source_inputs_sha256"]}, "Source input drift")
    require(report["baseline_saved_sha256"] == sha(ROOT / "benchmarks/baselines/b1254c4/results.json"), "Saved baseline drift")
    require(metadata["source_sha256"] == {k: source_hashes(Path(v)) for k, v in metadata["sources"].items()}, "Frozen package drift")
    report["summary"] = summaries(report["workers"])
    output.write_text(json.dumps(report, indent=2) + "\n")
    output.with_suffix(".md").write_text(markdown(report))


if __name__ == "__main__":
    main()
