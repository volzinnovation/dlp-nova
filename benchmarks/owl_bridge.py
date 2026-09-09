"""Matched finite L3 consistency/named-instance tasks against pinned HermiT.

This is an original controlled task, not an established corpus benchmark.
Prepare dependencies and input first; run only in a coordinated quiet window.
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
import statistics
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile

from benchmarks.lubm import BASELINE, digest_rows, require, sha, source_hashes
from benchmarks.zodiac import SWITCHES, source_snapshot

ROOT = Path(__file__).resolve().parents[1]
CONFIGURATIONS = ("b1254c4", "candidate", "hermit")
POPULATIONS = (100, 1000, 10000)
DEPENDENCIES = ROOT / "benchmarks/hermit-dependencies.json"
PHASES = ("load_seconds", "construct_seconds", "consistency_seconds",
          "positive_query_seconds", "negative_query_seconds")


def document(population, omit=None):
    """Deterministic bytes; one fixed TBox, N A instances and one B-only control."""
    require(isinstance(population, int) and population > 0, "population must be positive")
    require(omit in {None, "existential", "bridge"}, "unknown semantic control")
    rows = ['<?xml version="1.0" encoding="UTF-8"?>',
            '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"',
            ' xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"',
            ' xmlns:owl="http://www.w3.org/2002/07/owl#">',
            '<owl:Ontology rdf:about="urn:owl-bridge:ontology"/>']
    for name in "ABCD":
        rows.append(f'<owl:Class rdf:about="urn:owl-bridge:{name}"/>')
    rows += ['<owl:ObjectProperty rdf:about="urn:owl-bridge:R"/>',
             '<owl:Restriction rdf:nodeID="existential">',
             '<owl:onProperty rdf:resource="urn:owl-bridge:R"/>',
             '<owl:someValuesFrom rdf:resource="urn:owl-bridge:B"/>']
    if omit != "bridge":
        rows.append('<rdfs:subClassOf rdf:resource="urn:owl-bridge:C"/>')
    rows.append('</owl:Restriction>')
    if omit != "existential":
        rows += ['<owl:Class rdf:about="urn:owl-bridge:A">',
                 '<rdfs:subClassOf rdf:nodeID="existential"/>', '</owl:Class>']
    for index in range(population):
        rows += [f'<rdf:Description rdf:about="urn:owl-bridge:a{index}">',
                 '<rdf:type rdf:resource="urn:owl-bridge:A"/>', '</rdf:Description>']
    rows += ['<rdf:Description rdf:about="urn:owl-bridge:negative-b">',
             '<rdf:type rdf:resource="urn:owl-bridge:B"/>', '</rdf:Description>', '</rdf:RDF>']
    return ("\n".join(rows) + "\n").encode()


def expected_answers(population):
    return sorted(f"urn:owl-bridge:a{index}" for index in range(population)), []


def prepare_runtime(cache):
    """Pin published bundle bytes and expand their nested jars onto a plain JVM classpath."""
    lock = json.loads(DEPENDENCIES.read_text())
    runtime = cache / "current-hermit"
    runtime.mkdir(parents=True, exist_ok=True)
    paths = []
    for artifact in lock["artifacts"]:
        require(Path(artifact["name"]).name == artifact["name"], "invalid jar filename")
        path = runtime / artifact["name"]
        if not path.exists():
            payload = urllib.request.urlopen(artifact["url"], timeout=60).read()
            require(hashlib.sha256(payload).hexdigest() == artifact["sha256"], "download digest changed")
            path.write_bytes(payload)
        require(sha(path) == artifact["sha256"], "cached jar drift")
        paths.append(path)
    nested = []
    for path in paths:
        with zipfile.ZipFile(path) as archive:
            for member in sorted(archive.namelist()):
                if not member.endswith(".jar") or member in lock["nested_jar_exclusions"]:
                    continue
                payload = archive.read(member)
                destination = runtime / "nested" / path.stem / Path(member).name
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    require(destination.read_bytes() == payload, "nested jar drift")
                else:
                    destination.write_bytes(payload)
                nested.append(destination)
    paths.extend(nested)
    return {"distribution": lock["distribution"], "owlapi_version": lock["owlapi"],
            "dependency_lock_sha256": sha(DEPENDENCIES),
            "classpath": [str(path.relative_to(cache)) for path in paths],
            "classpath_sha256": {str(path.relative_to(cache)): sha(path) for path in paths}}


def classpath(cache, metadata, include_adapter=False):
    paths = ([cache / "classes"] if include_adapter else [])
    return os.pathsep.join(str(path) for path in paths + [cache / name for name in metadata["classpath"]])


def prepare(cache):
    cache.mkdir(parents=True, exist_ok=True)
    runtime = prepare_runtime(cache)
    inputs = {}
    for population in POPULATIONS:
        payload = document(population)
        path = cache / f"bridge-{population}.owl"
        if path.exists():
            require(path.read_bytes() == payload, "generated ontology drift")
        else:
            path.write_bytes(payload)
        inputs[str(population)] = {"sha256": sha(path), "bytes": len(payload),
                                   "expected_positive_sha256": digest_rows(expected_answers(population)[0]),
                                   "expected_positive_count": population, "expected_negative_count": 0}
    return {**runtime, "hermit_version": "1.4.5.519 (OWLAPI-maintained fork)",
            "java": subprocess.run(["java", "-version"], capture_output=True, text=True,
                                   check=True).stderr.strip(),
            "javac": subprocess.run(["javac", "-version"], capture_output=True, text=True,
                                    check=True).stdout.strip(),
            "inputs": inputs, "license": "HermiT LGPL-3.0-or-later; dependencies have their own licenses; "
                                      "published jar license resources retained; jars are not vendored."}


def build_java(cache, metadata):
    destination = cache / "classes"
    destination.mkdir(exist_ok=True)
    command = ["javac", "-cp", classpath(cache, metadata), "-d", str(destination),
               str(ROOT / "benchmarks/OwlBridge.java")]
    subprocess.run(command, capture_output=True, text=True, check=True, timeout=60)
    return sha(destination / "OwlBridge.class")


def candidate_snapshot(cache):
    manifest = json.loads((ROOT / "benchmarks/followup-source-manifest.json").read_text())
    archive_path = ROOT / manifest["archive"]
    require(sha(archive_path) == manifest["archive_sha256"], "measured candidate archive drift")
    destination = cache / "measured-candidate"
    expected = manifest["source_sha256"]
    with tarfile.open(fileobj=io.BytesIO(archive_path.read_bytes()), mode="r:gz") as archive:
        members = archive.getmembers()
        require({member.name for member in members} == set(expected), "candidate file set changed")
        for member in members:
            require(member.isfile() and member.name.startswith("src/dlp_reasoner/")
                    and ".." not in Path(member.name).parts, "unexpected candidate archive member")
            payload = archive.extractfile(member).read()
            require(hashlib.sha256(payload).hexdigest() == expected[member.name], "candidate member drift")
            path = destination / member.name
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                require(path.read_bytes() == payload, "candidate snapshot drift")
            else:
                path.write_bytes(payload)
    require(source_hashes(destination) == expected, "candidate package drift")
    return destination, manifest


def worker(path, configuration):
    from rdflib import Graph, URIRef
    from dlp_reasoner import Reasoner
    from dlp_reasoner.engine import Engine
    import dlp_reasoner
    if configuration == "candidate":
        for switch in SWITCHES:
            require(hasattr(Engine, switch), "candidate switch missing")
            setattr(Engine, switch, True)
        Engine._unary_strategy = "union-first"
        Engine._support_certificates_enabled = False
    started = time.perf_counter()
    graph = Graph().parse(path, format="xml", publicID="urn:owl-bridge:document")
    load = time.perf_counter() - started
    started = time.perf_counter()
    reasoner = Reasoner(graph, profile="L3")
    construct = time.perf_counter() - started
    started = time.perf_counter()
    consistent = reasoner.consistency == "consistent"
    consistency = time.perf_counter() - started
    require(reasoner.complete and consistent, "incomplete/inconsistent bridge materialization")
    started = time.perf_counter()
    positive = [str(value) for value in reasoner.instances(URIRef("urn:owl-bridge:C"))]
    positive_time = time.perf_counter() - started
    started = time.perf_counter()
    negative = [str(value) for value in reasoner.instances(URIRef("urn:owl-bridge:D"))]
    negative_time = time.perf_counter() - started
    return {"configuration": configuration, "consistent": consistent,
            "load_seconds": load, "construct_seconds": construct, "consistency_seconds": consistency,
            "positive_query_seconds": positive_time, "negative_query_seconds": negative_time,
            "positive": sorted(positive), "negative": sorted(negative), "stats": reasoner.stats,
            "python": sys.version, "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
            "source_sha256": source_hashes(Path(dlp_reasoner.__file__).resolve().parents[2])}


def execution_order(block, population_position):
    offset = (block + population_position) % len(CONFIGURATIONS)
    return CONFIGURATIONS[offset:] + CONFIGURATIONS[:offset]


def run(cache, output, blocks=3):
    require(blocks >= 3 and blocks % 3 == 0, "use a multiple of three blocks")
    protocol = output.with_name(output.stem + "-protocol.json")
    require(not any(path.exists() for path in (output, output.with_suffix(".md"), protocol)),
            "refuse to overwrite research evidence")
    metadata = prepare(cache)
    bytecode_hash = build_java(cache, metadata)
    candidate, candidate_manifest = candidate_snapshot(cache)
    baseline = source_snapshot(cache, BASELINE)
    sources = {"candidate": candidate, "b1254c4": baseline}
    hashes = {name: source_hashes(path) for name, path in sources.items()}
    drivers = {name: sha(ROOT / name) for name in ("benchmarks/owl_bridge.py", "benchmarks/OwlBridge.java",
                                                 "benchmarks/hermit-dependencies.json",
                                                 "benchmarks/lubm.py", "benchmarks/zodiac.py")}
    report = {"schema_version": 1, "benchmark": "finite-L3-existential-bridge-v1",
              "started_utc": datetime.now(timezone.utc).isoformat(), "metadata": metadata,
              "candidate_archive_sha256": candidate_manifest["archive_sha256"],
              "source_sha256": hashes, "driver_sha256": drivers, "java_bytecode_sha256": bytecode_hash,
              "baseline_commit": BASELINE, "platform": platform.platform(), "workers": [],
              "protocol": {"blocks": blocks, "populations": POPULATIONS, "configurations": CONFIGURATIONS,
                           "timeout_seconds": 180, "ordering": "rotate by block and population position",
                           "seeds": list(range(9800, 9800 + blocks)), "java_options": ["-Xms64m", "-Xmx2g"],
                           "task": "consistency, all named C instances, all named D instances",
                           "negative_control": "one B-only named individual; D has no entailed instances",
                           "timing": "load/construct/consistency/fully consumed C then D queries; fresh subprocess total",
                           "semantic_limit": "same entailment task; no full-closure or witness-store equivalence",
                           "host_note": "run only after other timed studies release the coordinated quiet window"}}
    output.parent.mkdir(parents=True, exist_ok=True)
    protocol.write_text(json.dumps(report, indent=2) + "\n")
    for block in range(blocks):
        for population_position, population in enumerate(POPULATIONS):
            path = cache / f"bridge-{population}.owl"
            for position, configuration in enumerate(execution_order(block, population_position)):
                require(all(sha(ROOT / name) == value for name, value in drivers.items()), "driver drift")
                require(sha(path) == metadata["inputs"][str(population)]["sha256"], "ontology drift")
                env = {**os.environ, "PYTHONHASHSEED": str(9800 + block)}
                if configuration == "hermit":
                    require(all(sha(cache / name) == value
                                for name, value in metadata["classpath_sha256"].items()), "jar drift")
                    require(sha(cache / "classes/OwlBridge.class") == bytecode_hash, "Java adapter drift")
                    command = ["java", "-Xms64m", "-Xmx2g", "-cp",
                               classpath(cache, metadata, include_adapter=True),
                               "OwlBridge", str(path)]
                else:
                    require(source_hashes(sources[configuration]) == hashes[configuration], "source drift")
                    env["PYTHONPATH"] = os.pathsep.join([str(sources[configuration] / "src"), str(ROOT)])
                    command = [sys.executable, "-m", "benchmarks.owl_bridge", "--worker", configuration,
                               "--ontology", str(path)]
                started = time.perf_counter()
                try:
                    completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True,
                                               timeout=180, check=True)
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                    report["failure"] = {"block": block, "population": population,
                                         "configuration": configuration, "error": str(error),
                                         "stdout": str(error.stdout), "stderr": str(error.stderr)}
                    output.write_text(json.dumps(report, indent=2) + "\n")
                    raise
                process_time = time.perf_counter() - started
                observation = json.loads(completed.stdout)
                positive, negative = expected_answers(population)
                require(observation["consistent"] and observation["positive"] == positive
                        and observation["negative"] == negative, "exact bridge task answer mismatch")
                if configuration != "hermit":
                    require(observation["source_sha256"] == hashes[configuration], "wrong package imported")
                observation.update(block=block, population=population, position=position,
                                   process_seconds=process_time,
                                   task_seconds=sum(observation[key] for key in PHASES),
                                   positive_sha256=digest_rows(observation.pop("positive")),
                                   negative_sha256=digest_rows(observation.pop("negative")),
                                   positive_count=population, negative_count=0, exact_match=True,
                                   command=command, stderr=completed.stderr)
                report["workers"].append(observation)
                print(f"{block + 1}/{blocks} N={population} {configuration}: exact answers; "
                      f"{observation['task_seconds']:.4f}s task", flush=True)
    report["summary"] = {}
    report["paired_ratios"] = {}
    for population in POPULATIONS:
        summary = report["summary"][str(population)] = {}
        for configuration in CONFIGURATIONS:
            selected = [row for row in report["workers"] if row["population"] == population
                        and row["configuration"] == configuration]
            summary[configuration] = {key: {"median": statistics.median(row[key] for row in selected),
                                            "minimum": min(row[key] for row in selected),
                                            "maximum": max(row[key] for row in selected)}
                                      for key in (*PHASES, "task_seconds", "process_seconds")}
        report["paired_ratios"][str(population)] = {}
        for denominator in ("b1254c4", "hermit"):
            ratio = report["paired_ratios"][str(population)]["candidate/" + denominator] = {}
            for key in ("task_seconds", "process_seconds"):
                values = []
                for block in range(blocks):
                    paired = {row["configuration"]: row[key] for row in report["workers"]
                              if row["population"] == population and row["block"] == block}
                    values.append(paired["candidate"] / paired[denominator])
                ratio[key] = {"raw": values, "median": statistics.median(values)}
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    report["protocol_sha256"] = sha(protocol)
    output.write_text(json.dumps(report, indent=2) + "\n")
    lines = ["# Finite L3 existential-bridge task comparison", "",
             "Original controlled workload; consistency and exact named C/D instances on identical ontologies.",
             "No witness-store equivalence or corpus-prevalence claim is made.", "",
             "| N | Configuration | Task median (s) | Process median (s) |", "|---:|---|---:|---:|"]
    for population, summary in report["summary"].items():
        for configuration, values in summary.items():
            lines.append(f"| {population} | {configuration} | {values['task_seconds']['median']:.6f} | "
                         f"{values['process_seconds']['median']:.6f} |")
    lines += ["", "HermiT is the OWLAPI-maintained 1.4.5.519 fork (OWLAPI 5.1.9), "
              "not a claim about the latest upstream full OWL reasoner. Phase timings accommodate eager DLP "
              "materialization and HermiT's normal lazy classification/realization; use the summed task "
              "time for the matched operation. Full process time additionally includes runtime startup, "
              "answer serialization and process exit. The fixed TBox implies A⊑C, so explicit witness "
              "construction is not necessary to answer this query. Both existential axioms are "
              "essential to that entailment; no axiom is removed or rewritten by the adapter.", ""]
    output.with_suffix(".md").write_text("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / "tmp/owl-bridge")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--worker", choices=("b1254c4", "candidate"))
    parser.add_argument("--ontology", type=Path)
    parser.add_argument("--blocks", type=int, default=3)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/owl-bridge-results.json")
    args = parser.parse_args()
    if args.worker:
        require(args.ontology is not None, "worker requires ontology")
        print(json.dumps(worker(args.ontology, args.worker)))
    elif args.prepare or args.build:
        metadata = prepare(args.cache.resolve())
        if args.build:
            metadata["java_bytecode_sha256"] = build_java(args.cache.resolve(), metadata)
        print(json.dumps(metadata, indent=2))
    else:
        run(args.cache.resolve(), args.output.resolve(), args.blocks)


if __name__ == "__main__":
    main()
