"""Frozen ZodiacEdge LUBM rule-maintenance experiment.

This executes all 128 rules and the author's two marked rule transactions.
It is a Datalog-program benchmark, separate from full-ontology LUBM evaluation.
Run --prepare first; measurements start only with a separate invocation.
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
import random
import re
import resource
import shutil
import statistics
import subprocess
import sys
import tarfile
import time
import urllib.request

from rdflib import Graph, OWL, RDF, URIRef

from benchmarks.lubm import (BASELINE, ONTOLOGY, digest_rows, require, sha,
                             source_hashes, term_record, validate_inputs)

ROOT = Path(__file__).resolve().parents[1]
AUTHOR_COMMIT = "e15721161d1055f019c4b8f9ac1bd8648417f154"
README_URL = ("https://raw.githubusercontent.com/xwq610728213/zodiac_edge/"
              + AUTHOR_COMMIT + "/README.md")
README_SHA256 = "5f410708840431e4cef28b8a032c5bc8f90c29260f723847c5757bf79bc6042d"
PREVIOUS = "5531be4"
CONFIGURATIONS = ("b1254c4", "5531be4", "current-fixed", "candidate")
SWITCHES = ("_incremental_validation_enabled", "_incremental_index_enabled",
            "_compiled_joins_enabled")
ATOM = re.compile(r"<([A-Za-z][A-Za-z0-9_]*)>\((\?[A-Za-z][A-Za-z0-9_]*"
                  r"(?:\s*,\s*\?[A-Za-z][A-Za-z0-9_]*)?)\)")


def parse_atom(text):
    from dlp_reasoner.model import Atom, Var
    match = ATOM.fullmatch(text.strip())
    require(match is not None, f"unsupported author atom: {text!r}")
    predicate, arguments = match.groups()
    return Atom(predicate, tuple(Var(value.strip()[1:]) for value in arguments.split(",")))


def parse_rule(text):
    from dlp_reasoner.model import Rule
    text = text.replace("\\<", "<").strip()
    require(text.endswith(" .") and text.count(":-") == 1, "unsupported author rule syntax")
    head, body = text[:-2].split(":-")
    rule = Rule(parse_atom(head), tuple(parse_atom(atom) for atom in body.split(" and ")))
    body_variables = {value for atom in rule.body for value in atom.args}
    require(set(rule.head.args) <= body_variables, "unsafe author rule")
    return rule


def parse_marked_program(text, expected=(128, 8, 16)):
    """Parse only the positive, variable-only unary/binary author table.

    Counts, markers, uniqueness and grammar fail closed. In particular, a newly
    introduced aggregate, negation, comparison or constant cannot disappear.
    """
    rules, groups = [], {"*": [], "#": []}
    for line in text.splitlines():
        if not line.startswith("|") or " :- " not in line:
            continue
        columns = [value.strip() for value in line.split("|")[1:-1]]
        require(len(columns) == 3, "unexpected author rule table columns")
        star, hashmark, source = columns
        require(star in {"", "*"} and hashmark in {"", "#"}, "unknown rule marker")
        rule = parse_rule(source)
        require(rule not in rules, "duplicate author rule")
        rules.append(rule)
        if star:
            groups["*"].append(rule)
        if hashmark:
            groups["#"].append(rule)
    require((len(rules), len(groups["*"]), len(groups["#"])) == expected,
            "author rule/transaction counts changed")
    return rules, groups


def prepare(cache, data_cache):
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / "README.author.md"
    if not path.exists():
        payload = urllib.request.urlopen(README_URL, timeout=60).read()
        require(hashlib.sha256(payload).hexdigest() == README_SHA256, "author artifact drift")
        path.write_bytes(payload)
    require(sha(path) == README_SHA256, "cached author artifact drift")
    rules, groups = parse_marked_program(path.read_text())
    require((data_cache / "manifest.json").exists(),
            "first run python -m benchmarks.lubm --prepare with this data cache")
    manifest = json.loads((data_cache / "manifest.json").read_text())
    validate_inputs(data_cache, manifest)
    return {"author_commit": AUTHOR_COMMIT, "author_readme_url": README_URL,
            "author_readme_sha256": README_SHA256, "rules": len(rules),
            "transactions": {key: len(value) for key, value in groups.items()},
            "dataset_manifest_sha256": sha(data_cache / "manifest.json"),
            "dataset_manifest": manifest,
            "license": "No LICENSE file found in the pinned ZodiacEdge repository; "
                       "source is fetched into ignored tmp, not redistributed here."}


def encode_assertions(graph, rules):
    """Preserve each LUBM ABox fact using the author's src_ predicate wrapper."""
    from dlp_reasoner.model import Atom
    sources = {atom.predicate: len(atom.args) for rule in rules for atom in rule.body
               if atom.predicate.startswith("src_")}
    facts = set()
    metadata = {"ontology_declarations": 0, "imports": 0}
    namespace = ONTOLOGY + "#"
    for subject, predicate, obj in graph:
        if predicate == RDF.type and obj == OWL.Ontology:
            metadata["ontology_declarations"] += 1
            continue
        if predicate == OWL.imports:
            require(str(obj) == ONTOLOGY, "unexpected imported ontology")
            metadata["imports"] += 1
            continue
        name = obj if predicate == RDF.type else predicate
        require(isinstance(name, URIRef) and str(name).startswith(namespace),
                f"non-LUBM ABox predicate/class: {name}")
        args = (subject,) if predicate == RDF.type else (subject, obj)
        source = "src_" + str(name)[len(namespace):]
        require(sources.get(source) == len(args), f"author rules do not cover assertion: {source}")
        facts.add(Atom(source, args))
    require(len(facts) + sum(metadata.values()) == len(graph), "ABox transformation lost facts")
    return facts, metadata


def load_program(cache, data_cache):
    require(sha(cache / "README.author.md") == README_SHA256, "author artifact changed")
    rules, groups = parse_marked_program((cache / "README.author.md").read_text())
    manifest = json.loads((data_cache / "manifest.json").read_text())
    validate_inputs(data_cache, manifest)
    graph = Graph()
    paths = sorted((data_cache / "data").glob("University*.owl"))
    require(len(paths) == 15, "expected all 15 LUBM(1,0) department documents")
    for path in paths:
        graph.parse(path, format="xml", publicID="urn:lubm:document:" + path.name)
    facts, metadata = encode_assertions(graph, rules)
    require(len(facts) == 100543, "expected the author's LUBM1 EDB cardinality")
    require(metadata == {"ontology_declarations": 15, "imports": 15}, "metadata count changed")
    return rules, groups, facts, metadata


def closure_record(engine):
    from dlp_reasoner.model import TOP
    require(engine.complete and not engine.violations, "incomplete/inconsistent materialization")
    facts = {fact for fact in engine.facts if fact.predicate != TOP}
    rows = [[term_record(fact.predicate), [term_record(value) for value in fact.args]]
            for fact in facts]
    return {"facts": len(facts), "sha256": digest_rows(rows)}


def configured_engine(configuration):
    from dlp_reasoner.engine import Engine
    require(configuration in CONFIGURATIONS, "unknown benchmark configuration")
    controls = {}
    for switch in SWITCHES:
        if configuration == "candidate":
            require(hasattr(Engine, switch), f"candidate switch absent: {switch}")
        if hasattr(Engine, switch):
            controls[switch] = configuration == "candidate"
    # Preserve the registered fixed strategy and DRed; unrelated experiments
    # cannot enter through a changed default in the imported source snapshot.
    if hasattr(Engine, "_unary_strategy"):
        controls["_unary_strategy"] = "union-first"
    if hasattr(Engine, "_support_certificates_enabled"):
        controls["_support_certificates_enabled"] = False
    return type("ZodiacBenchmarkEngine", (Engine,), controls)


def fact_subsets(facts, samples, size=1000):
    require(samples >= 0 and 0 < size <= len(facts), "invalid fact sampling controls")
    ordered = sorted(facts, key=lambda fact: json.dumps(
        [term_record(fact.predicate), [term_record(value) for value in fact.args]]))
    return [(9100 + sample, set(random.Random(9100 + sample).sample(ordered, size)))
            for sample in range(samples)]


def oracle(cache, data_cache, fact_samples=1):
    """Fresh naive materializations on frozen b1254c4, outside measured workers."""
    from dlp_reasoner.engine import Engine
    from dlp_reasoner.model import Program
    rules, groups, facts, _ = load_program(cache, data_cache)
    results = {}
    for key, removed in [("full", [])] + list(groups.items()):
        subset = [rule for rule in rules if rule not in removed]
        engine = Engine(Program(subset, facts), strategy="naive").materialize()
        results[key] = closure_record(engine)
    for seed, removed in fact_subsets(facts, fact_samples):
        engine = Engine(Program(rules, facts - removed), strategy="naive").materialize()
        results["facts-" + str(seed)] = closure_record(engine)
    return results


def worker(cache, data_cache, configuration, reference, fact_samples=1):
    from dlp_reasoner.model import Program
    import dlp_reasoner
    import rdflib
    rules, groups, facts, metadata = load_program(cache, data_cache)
    engine_type = configured_engine(configuration)
    observations = {}
    for marker, changed in groups.items():
        partial = [rule for rule in rules if rule not in changed]
        start = time.perf_counter()
        engine = engine_type(Program(partial, facts))
        construct = time.perf_counter() - start
        start = time.perf_counter()
        engine.materialize()
        elapsed = time.perf_counter() - start
        initial = closure_record(engine)
        require(initial == reference[marker], f"initial {marker} closure differs from naive oracle")
        observations[marker] = {"removed_rules": len(changed), "construct_seconds": construct,
                                "materialize_seconds": elapsed,
                                "construct_and_materialize_seconds": construct + elapsed,
                                "initial": initial, "materialize_stats": dict(engine.stats)}
        for action in ("insert", "delete"):
            start = time.perf_counter()
            engine.update(**{"add_rules" if action == "insert" else "remove_rules": changed})
            elapsed = time.perf_counter() - start
            record = closure_record(engine)
            require(record == reference["full" if action == "insert" else marker],
                    f"{action} {marker} closure differs from naive oracle")
            observations[marker][action + "_seconds"] = elapsed
            observations[marker][action] = record
            observations[marker][action + "_stats"] = dict(engine.stats)
    supplemental = []
    if fact_samples:
        # Restore the second rule transaction's full program before starting
        # the separate data-maintenance track; this restoration is not timed.
        engine.update(add_rules=groups["#"])
        require(closure_record(engine) == reference["full"], "supplemental initial mismatch")
        for seed, removed in fact_subsets(facts, fact_samples):
            observation = {"seed": seed, "removed_assertions": len(removed)}
            for action in ("delete", "insert"):
                start = time.perf_counter()
                engine.update(**{"remove" if action == "delete" else "add": removed})
                elapsed = time.perf_counter() - start
                record = closure_record(engine)
                require(record == reference["facts-" + str(seed) if action == "delete" else "full"],
                        f"supplemental fact {action} differs from naive oracle")
                observation[action + "_seconds"] = elapsed
                observation[action] = record
                observation[action + "_stats"] = dict(engine.stats)
            supplemental.append(observation)
    package_root = Path(dlp_reasoner.__file__).resolve().parents[2]
    return {"configuration": configuration, "transactions": observations,
            "supplemental_fact_transactions": supplemental, "edb_facts": len(facts),
            "edb_sha256": digest_rows([[term_record(f.predicate), [term_record(a) for a in f.args]]
                                      for f in facts]),
            "removed_document_metadata": metadata, "python": sys.version,
            "pythonhashseed": os.environ.get("PYTHONHASHSEED"), "rdflib": rdflib.__version__,
            "source_sha256": source_hashes(package_root), "package_path": str(package_root),
            "switches": {key: getattr(engine_type, key, None) for key in SWITCHES},
            "all_complete_tuple_digests_match_naive": True,
            "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                              * (1 if sys.platform == "darwin" else 1024)}


def source_snapshot(cache, revision=None):
    """Freeze package bytes before measurement; never switch the user's branch."""
    if revision:
        commit = subprocess.run(["git", "rev-parse", revision], cwd=ROOT,
                                capture_output=True, text=True, check=True).stdout.strip()
        destination = cache / ("source-" + commit)
        payload = subprocess.run(["git", "archive", commit, "src/dlp_reasoner"], cwd=ROOT,
                                 capture_output=True, check=True).stdout
        with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
            expected = {member.name: archive.extractfile(member).read()
                        for member in archive.getmembers() if member.isfile()}
        destination.mkdir(exist_ok=True)
        for name, data in expected.items():
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                require(path.read_bytes() == data, f"frozen source changed: {path}")
            else:
                path.write_bytes(data)
        actual = {str(path.relative_to(destination)) for path in
                  (destination / "src/dlp_reasoner").glob("*.py")}
        require(actual == set(expected), "frozen source file set changed")
        return destination
    hashes = source_hashes(ROOT)
    digest = digest_rows(list(hashes.items()))
    destination = cache / ("source-working-" + digest)
    if not destination.exists():
        (destination / "src/dlp_reasoner").mkdir(parents=True)
        for name in hashes:
            shutil.copyfile(ROOT / name, destination / name)
    require(source_hashes(destination) == hashes, "frozen working source drift")
    return destination


def markdown(report):
    lines = ["# ZodiacEdge LUBM(1) rule-maintenance reproduction", "",
             "All 128 author rules; 100,543 ABox facts; original * (8 rules) and # (16 rules) transactions.",
             "This measures the exact author Datalog program, not full OWL LUBM entailment.", "",
             "| Configuration | Subset | Initial total (s) | Insert (s) | Delete (s) |",
             "|---|---|---:|---:|---:|"]
    for config in CONFIGURATIONS:
        for marker in ("*", "#"):
            summary = report["summary"][config][marker]
            lines.append(f"| {config} | {marker} | " + " | ".join(
                f"{summary[key]['median']:.6f}" for key in
                ("construct_and_materialize_seconds", "insert_seconds", "delete_seconds")) + " |")
    if report["protocol"]["fact_samples"]:
        lines += ["", "Supplemental deterministic 1,000-assertion deletion/reinsertion transactions "
                  "use the same full program. These follow the small-batch idea from materialization "
                  "maintenance research; they are not ZodiacEdge's published rule transactions or "
                  "a reproduction of Motik's original benchmark dataset.", "",
                  "| Configuration | Fact delete median (s) | Fact reinsert median (s) |",
                  "|---|---:|---:|"]
        for config in CONFIGURATIONS:
            values = report["supplemental_summary"][config]
            lines.append(f"| {config} | {values['delete_seconds']['median']:.6f} | "
                         f"{values['insert_seconds']['median']:.6f} |")
    lines += ["", "All complete tuple digests at every stage match a fresh naive materialization "
              "from frozen b1254c4. This reference shares the original engine semantics; "
              "it is not an independent OWL reasoner. Internal TOP facts are excluded from comparisons.",
              "Each block uses fresh processes, identical hash seeds across configurations, and "
              "rotated order. Initial timing includes construction; RDF parsing, artifact parsing, "
              "hashing and validation are outside the timers. Insertion then deletion use the same "
              "already materialized instance, restoring the original partial program.",
              "The author README reports 0.5889/0.2169/0.2525 seconds for * and "
              "0.6037/0.0563/0.0215 seconds for # (initial/insert/delete). Its additional LUBM "
              "test does not specify hardware, seeds, repetitions or timer boundaries. These "
              "published values are context only; no cross-machine speedup is inferred.",
              "The generated UBA1.7 index-0/seed-0 input matches the author's stated EDB count, "
              "but the author's original input hash and generator seed were not published.",
              "The candidate combines positional join plans, delta index maintenance and reusable "
              "validation metadata for monotone fact/rule insertions. The primary track exercises "
              "rule insertion; supplemental transactions also exercise assertion reinsertion.",
              "", f"[Frozen author benchmark]({README_URL})", ""]
    return "\n".join(lines)


def run(cache, data_cache, output, blocks, fact_samples=1):
    require(blocks >= 4 and blocks % 4 == 0, "use a multiple of four balanced blocks")
    protocol_path = output.with_name(output.stem + "-protocol.json")
    require(not any(path.exists() for path in (output, output.with_suffix(".md"), protocol_path)),
            "refuse to overwrite benchmark evidence")
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = prepare(cache, data_cache)
    selected = {"b1254c4": source_snapshot(cache, BASELINE),
                "5531be4": source_snapshot(cache, PREVIOUS)}
    current = source_snapshot(cache)
    selected.update({"current-fixed": current, "candidate": current})
    # Fail before any expensive oracle or timing if a candidate is not ready.
    configured_engine("candidate")
    driver_hashes = {name: sha(ROOT / name) for name in ("benchmarks/zodiac.py", "benchmarks/lubm.py")}
    source_records = {name: source_hashes(path) for name, path in selected.items()}
    report = {"schema_version": 1, "benchmark": "ZodiacEdge-LUBM1-128-rules-v1",
              "started_utc": datetime.now(timezone.utc).isoformat(), "manifest": manifest,
              "baseline_commit": BASELINE,
              "previous_commit": selected["5531be4"].name.removeprefix("source-"),
              "platform": platform.platform(), "machine": platform.machine(),
              "cpu_count": os.cpu_count(), "driver_sha256": driver_hashes,
              "source_sha256": source_records, "workers": [],
              "protocol": {"blocks": blocks, "configurations": CONFIGURATIONS,
                           "fact_samples": fact_samples, "removed_assertions_per_sample": 1000,
                           "fact_sample_seeds": list(range(9100, 9100 + fact_samples)),
                           "ordering": "balanced Latin-square rotations",
                           "seeds": list(range(7300, 7300 + blocks)), "timeout_seconds": 300,
                           "stages": ["materialize R minus marked subset", "insert subset", "delete subset"],
                           "validation": "complete typed tuple digests vs fresh b1254c4 naive closure",
                           "timing": "fresh process per configuration; parsing/validation outside timers",
                           "host_note": "run only in coordinated quiet window; OS caches not flushed"}}
    protocol_path.write_text(json.dumps(report, indent=2) + "\n")

    def invoke(source, arguments, seed):
        require(all(sha(ROOT / name) == value for name, value in driver_hashes.items()),
                "benchmark driver changed during run")
        env = {**os.environ, "PYTHONHASHSEED": str(seed),
               "PYTHONPATH": os.pathsep.join([str(source / "src"), str(ROOT)])}
        command = [sys.executable, "-m", "benchmarks.zodiac", "--cache", str(cache),
                   "--data-cache", str(data_cache), "--fact-samples", str(fact_samples), *arguments]
        completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True,
                                   timeout=300, check=True)
        return json.loads(completed.stdout)

    reference = invoke(selected["b1254c4"], ["--oracle"], 7300)
    reference_path = cache / ("reference-" + digest_rows(list(reference.items())) + ".json")
    reference_path.write_text(json.dumps(reference, indent=2) + "\n")
    report["fresh_naive_reference"] = reference
    for block in range(blocks):
        offset = block % len(CONFIGURATIONS)
        order = CONFIGURATIONS[offset:] + CONFIGURATIONS[:offset]
        for position, config in enumerate(order):
            require(source_hashes(selected[config]) == source_records[config], "source snapshot drift")
            result = invoke(selected[config], ["--worker", config, "--reference", str(reference_path)],
                            7300 + block)
            require(result["source_sha256"] == source_records[config], "wrong source package measured")
            if report["workers"]:
                require(result["edb_sha256"] == report["workers"][0]["edb_sha256"], "EDB drift")
            result.update(block=block, position=position)
            report["workers"].append(result)
            print(f"{block + 1}/{blocks} {config}: both rule transactions validated", flush=True)
    keys = ("construct_seconds", "materialize_seconds", "construct_and_materialize_seconds",
            "insert_seconds", "delete_seconds")
    report["summary"] = {}
    for config in CONFIGURATIONS:
        report["summary"][config] = {}
        for marker in ("*", "#"):
            report["summary"][config][marker] = {}
            for key in keys:
                values = [row["transactions"][marker][key] for row in report["workers"]
                          if row["configuration"] == config]
                report["summary"][config][marker][key] = {
                    "median": statistics.median(values), "minimum": min(values), "maximum": max(values)}
    report["paired_ratios"] = {}
    for denominator in ("b1254c4", "5531be4", "current-fixed"):
        report["paired_ratios"]["candidate/" + denominator] = {}
        for marker in ("*", "#"):
            report["paired_ratios"]["candidate/" + denominator][marker] = {}
            for key in keys:
                ratios = []
                for block in range(blocks):
                    matched = {row["configuration"]: row["transactions"][marker][key]
                               for row in report["workers"] if row["block"] == block}
                    ratios.append(matched["candidate"] / matched[denominator])
                report["paired_ratios"]["candidate/" + denominator][marker][key] = {
                    "raw": ratios, "median": statistics.median(ratios)}
    report["supplemental_summary"] = {}
    for config in CONFIGURATIONS:
        report["supplemental_summary"][config] = {}
        for key in ("delete_seconds", "insert_seconds"):
            values = [sample[key] for row in report["workers"] if row["configuration"] == config
                      for sample in row["supplemental_fact_transactions"]]
            if values:
                report["supplemental_summary"][config][key] = {
                    "median": statistics.median(values), "minimum": min(values), "maximum": max(values)}
    report["supplemental_paired_ratios"] = {}
    for denominator in ("b1254c4", "5531be4", "current-fixed"):
        report["supplemental_paired_ratios"]["candidate/" + denominator] = {}
        for key in ("delete_seconds", "insert_seconds"):
            ratios = []
            for block in range(blocks):
                matched = {row["configuration"]: row for row in report["workers"]
                           if row["block"] == block}
                for sample in range(fact_samples):
                    ratios.append(matched["candidate"]["supplemental_fact_transactions"][sample][key]
                                  / matched[denominator]["supplemental_fact_transactions"][sample][key])
            if ratios:
                report["supplemental_paired_ratios"]["candidate/" + denominator][key] = {
                    "raw": ratios, "median": statistics.median(ratios)}
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    report["protocol_sha256"] = sha(protocol_path)
    output.write_text(json.dumps(report, indent=2) + "\n")
    output.with_suffix(".md").write_text(markdown(report))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / "tmp/zodiac-lubm")
    parser.add_argument("--data-cache", type=Path, default=ROOT / "tmp/lubm-official")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--oracle", action="store_true")
    parser.add_argument("--worker", choices=CONFIGURATIONS)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--blocks", type=int, default=4)
    parser.add_argument("--fact-samples", type=int, default=1)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/zodiac-results.json")
    args = parser.parse_args()
    cache, data_cache = args.cache.resolve(), args.data_cache.resolve()
    if args.prepare:
        print(json.dumps(prepare(cache, data_cache), indent=2))
    elif args.oracle:
        print(json.dumps(oracle(cache, data_cache, args.fact_samples)))
    elif args.worker:
        require(args.reference is not None, "worker requires a frozen reference file")
        print(json.dumps(worker(cache, data_cache, args.worker,
                                json.loads(args.reference.read_text()), args.fact_samples)))
    else:
        run(cache, data_cache, args.output.resolve(), args.blocks, args.fact_samples)


if __name__ == "__main__":
    main()
