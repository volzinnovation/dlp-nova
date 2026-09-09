"""Compare the unmodified author ZodiacEdge engine with the local candidate.

The pinned upstream source is downloaded into ignored tmp/, never redistributed.
Preparation performs no reasoning. Run measurements only in a quiet window.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import resource
import statistics
import subprocess
import sys
import tarfile
import time
import traceback
import urllib.request

from rdflib import RDF

from benchmarks.lubm import digest_rows, require, sha, source_hashes, term_record
from benchmarks import zodiac

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_URL = ("https://codeload.github.com/xwq610728213/zodiac_edge/tar.gz/"
               + zodiac.AUTHOR_COMMIT)
ARCHIVE_SHA256 = "49e371017fa0a4d0602b941f2b4860823836414e7f2439059db81ac1d3e80ebe"
ARMS = ("native", "candidate")


def prepare_native(cache):
    """Verify a pinned archive and extract only unchanged source text."""
    cache.mkdir(parents=True, exist_ok=True)
    archive_path = cache / (zodiac.AUTHOR_COMMIT + ".tar.gz")
    if not archive_path.exists():
        payload = urllib.request.urlopen(ARCHIVE_URL, timeout=30).read()
        require(hashlib.sha256(payload).hexdigest() == ARCHIVE_SHA256,
                "upstream archive digest changed")
        archive_path.write_bytes(payload)
    require(sha(archive_path) == ARCHIVE_SHA256, "cached upstream archive changed")
    destination = cache / "upstream"
    expected = {}
    with tarfile.open(archive_path) as archive:
        for member in archive.getmembers():
            name = PurePosixPath(member.name)
            if not member.isfile() or (name.suffix != ".py" and name.name != "README.md"):
                continue
            require(name.parts[0] == "zodiac_edge-" + zodiac.AUTHOR_COMMIT,
                    "unexpected archive prefix")
            relative = PurePosixPath(*name.parts[1:])
            require(not relative.is_absolute() and ".." not in relative.parts,
                    "unsafe archive path")
            payload = archive.extractfile(member).read()
            path = destination / relative
            if path.exists():
                require(path.read_bytes() == payload, "upstream source was modified: " + str(path))
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
            expected[str(relative)] = hashlib.sha256(payload).hexdigest()
    require(expected["README.md"] == zodiac.README_SHA256, "upstream README changed")
    actual = {str(path.relative_to(destination)) for path in destination.rglob("*.py")}
    require(actual == set(expected) - {"README.md"}, "unexpected upstream Python source")
    manifest = {"commit": zodiac.AUTHOR_COMMIT, "archive_url": ARCHIVE_URL,
                "archive_sha256": ARCHIVE_SHA256, "source_sha256": expected,
                "upstream_modified": False,
                "license": "No LICENSE found; fetched into ignored tmp only."}
    manifest_path = cache / "manifest.json"
    if manifest_path.exists():
        require(json.loads(manifest_path.read_text()) == manifest, "native manifest changed")
    else:
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def verify_native(cache):
    manifest = json.loads((cache / "manifest.json").read_text())
    require(manifest["commit"] == zodiac.AUTHOR_COMMIT, "wrong upstream revision")
    require(manifest["archive_sha256"] == ARCHIVE_SHA256, "wrong upstream archive")
    require(sha(cache / (zodiac.AUTHOR_COMMIT + ".tar.gz")) == ARCHIVE_SHA256,
            "upstream archive changed")
    expected = manifest["source_sha256"]
    root = cache / "upstream"
    require({str(path.relative_to(root)) for path in root.rglob("*.py")}
            == set(expected) - {"README.md"}, "unexpected upstream source set")
    require(all(sha(root / name) == value for name, value in expected.items()),
            "upstream source changed")
    return manifest


def native_api(cache):
    verify_native(cache)
    root = (cache / "upstream").resolve()
    for name in ("classes", "reasoner", "util", "selfDefinedFunc"):
        if name in sys.modules:
            require(Path(sys.modules[name].__file__).resolve().is_relative_to(root),
                    "upstream package name collision")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    # The author's main.py needs an optional profiler and hard-coded data paths.
    # Importing its unchanged Program API requires only stdlib/local modules.
    return {
        "Program": importlib.import_module("reasoner.program").Program,
        "DataStore": importlib.import_module("classes.datastore").DataStore,
        "Term": importlib.import_module("classes.term").Term,
        "parse_rule": importlib.import_module("util.parser").parse_rule,
    }


def encode_constant(term):
    """Injectively preserve RDF term kind, lexical value, datatype and language."""
    serialized = json.dumps(term_record(term), ensure_ascii=False, separators=(",", ":"))
    return "urn:dlp-zodiac:term:" + base64.urlsafe_b64encode(serialized.encode()).decode()


def rule_text(rule):
    from dlp_reasoner.model import Var

    def atom_text(atom):
        require(all(isinstance(value, Var) for value in atom.args),
                "native adapter covers the author's variable-only rules")
        return "<" + atom.predicate + ">(" + ", ".join("?" + v.name for v in atom.args) + ")"

    require(rule.head is not None and rule.body, "unsupported native rule form")
    return atom_text(rule.head) + " :- " + " and ".join(map(atom_text, rule.body)) + " ."


def translated_input(api, rules, facts):
    """Use the author's own unary-to-rdf:type syntax mapping; do no inference."""
    terms = api["Term"]
    constants = {encode_constant(value): value for fact in facts for value in fact.args}
    require(len(constants) == len({value for fact in facts for value in fact.args}),
            "non-injective input term encoding")
    encoded_terms = {key: terms.getTerm(key, "constant") for key in constants}
    arities = {}
    for rule in rules:
        for atom in (rule.head, *rule.body):
            require(arities.setdefault(atom.predicate, len(atom.args)) == len(atom.args),
                    "inconsistent input predicate arity")
    native_rules = {rule: api["parse_rule"](rule_text(rule)) for rule in rules}
    require(len(set(native_rules.values())) == len(rules), "native parser collapsed author rules")
    native_facts = []
    for fact in facts:
        values = tuple(encoded_terms[encode_constant(value)] for value in fact.args)
        require(arities[fact.predicate] == len(values), "unknown input predicate")
        if len(values) == 1:
            native_facts.append((values[0], terms.getTerm(str(RDF.type), "constant"),
                                 terms.getTerm(fact.predicate, "constant")))
        else:
            require(len(values) == 2, "unsupported native arity")
            native_facts.append((values[0], terms.getTerm(fact.predicate, "constant"), values[1]))
    return native_rules, native_facts, constants, arities


def native_closure(program, constants, arities):
    """Decode and union the engine's EDB/IDB stores, retaining every tuple."""
    from dlp_reasoner.model import Atom
    result = set()

    def visit(store):
        if hasattr(store, "data_store_bag"):
            for child in store.data_store_bag:
                visit(child)
            return
        for predicate, rows in store.predicate_tuples.items():
            for left, right in rows:
                if predicate.name == str(RDF.type):
                    name = right.name
                    require(arities.get(name) == 1, "unknown native unary predicate")
                    values = (constants[left.name],)
                else:
                    name = predicate.name
                    require(arities.get(name) == 2, "unknown native binary predicate")
                    values = (constants[left.name], constants[right.name])
                result.add(Atom(name, values))

    visit(program.edb)
    visit(program.idb)
    return result


def tuple_record(facts):
    return {"facts": len(facts), "sha256": digest_rows([
        [term_record(f.predicate), [term_record(a) for a in f.args]] for f in facts])}


def native_worker(cache, data_cache, native_cache, reference):
    rules, groups, facts, metadata = zodiac.load_program(cache, data_cache)
    api = native_api(native_cache)
    observations = {}
    for marker, changed in groups.items():
        # Fresh rule objects avoid carrying mutable author join orders between
        # the two initial programs; conversion is outside compute timing.
        started = time.perf_counter()
        native_rules, native_facts, constants, arities = translated_input(api, rules, facts)
        conversion = time.perf_counter() - started
        partial = {native for rule, native in native_rules.items() if rule not in changed}
        native_changed = {native_rules[rule] for rule in changed}
        started = time.perf_counter()
        data = api["DataStore"]()
        for triple in native_facts:
            data.add(*triple)
        index_seconds = time.perf_counter() - started
        require(len(data) == len(facts), "native DataStore lost input facts")
        started = time.perf_counter()
        program = api["Program"](data=data, rules=partial)
        program_seconds = time.perf_counter() - started
        initial = tuple_record(native_closure(program, constants, arities))
        require(initial == reference[marker], "native initial closure mismatch for " + marker)
        observation = {"removed_rules": len(changed), "conversion_seconds": conversion,
                       "input_index_build_seconds": index_seconds,
                       "program_construct_and_materialize_seconds": program_seconds,
                       "construct_and_materialize_seconds": index_seconds + program_seconds,
                       "initial": initial}
        for action in ("insert", "delete"):
            started = time.perf_counter()
            (program.add_rules if action == "insert" else program.delete_rules)(native_changed)
            elapsed = time.perf_counter() - started
            record = tuple_record(native_closure(program, constants, arities))
            require(record == reference["full" if action == "insert" else marker],
                    "native " + action + " closure mismatch for " + marker)
            observation[action + "_seconds"] = elapsed
            observation[action] = record
        observations[marker] = observation
    return {"arm": "native", "transactions": observations, "edb_facts": len(facts),
            "edb_sha256": tuple_record(facts)["sha256"], "removed_document_metadata": metadata,
            "python": sys.version, "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
            "upstream": verify_native(native_cache), "all_closures_match": True,
            "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                              * (1 if sys.platform == "darwin" else 1024)}


def markdown(report):
    lines = ["# Native ZodiacEdge comparison on the same host", "",
             "Pinned unmodified upstream engine and local candidate; the exact author 128-rule "
             "program on official LUBM(1,0), with its marked eight- and sixteen-rule transactions.", ""]
    if report.get("failure"):
        lines += ["**The comparison did not complete successfully. No speedup is claimed.**", "",
                  "```json", json.dumps(report["failure"], indent=2), "```", ""]
    else:
        lines += ["| Subset | Engine | Initial compute(s) | Insert(s) | Delete(s) |",
                  "|---|---|---:|---:|---:|"]
        for marker in ("*", "#"):
            for arm in ARMS:
                row = report["summary"][arm][marker]
                lines.append(f"| {marker} | {arm} | " + " | ".join(
                    f"{row[key]['median']:.6f}" for key in report["timed_keys"]) + " |")
    lines += ["", "Each block runs both arms in fresh processes with the same hash seed; their "
              "order alternates. All six complete tuple sets per worker must match frozen naive "
              "references. No author engine code is changed. Only positive variable-only rules "
              "are evaluated; no claim about negation, aggregation, or full OWL conformance follows.",
              "", "The author's Program constructor performs reasoning. Native initial compute "
              "therefore includes indexed DataStore construction plus Program construction; "
              "both components are also recorded separately. Local initial compute includes "
              "Engine construction plus materialization. RDF parsing, representation conversion, "
              "rule parsing, and result validation are outside compute timing; native conversion "
              "is recorded separately. Peak RSS includes parsing, representation conversion, "
              "and validation; it is not isolated engine storage usage.",
              "", "Native unary atoms retain the author's rdf:type encoding. RDF constants are "
              "injectively tagged by type, lexical form, datatype and language before entering "
              "the author's opaque constant model; output is decoded before comparison. These "
              "representation differences are part of the systems, not a common physical plan.",
              "", "This small same-host execution does not reproduce the unspecified hardware "
              "or original data bytes of the author's published LUBM timing table.", ""]
    return "\n".join(lines)


def run(cache, data_cache, native_cache, reference_path, output, blocks, candidate_source=None):
    require(blocks >= 4 and blocks % 2 == 0, "use at least four balanced paired blocks")
    protocol_path = output.with_name(output.stem + "-protocol.json")
    require(not any(path.exists() for path in (output, protocol_path, output.with_suffix(".md"))),
            "refuse to overwrite benchmark evidence")
    manifest = verify_native(native_cache)
    inputs = zodiac.prepare(cache, data_cache)
    reference = json.loads(reference_path.read_text())
    require(set(reference) >= {"full", "*", "#"}, "missing naive reference states")
    source = (candidate_source.resolve() if candidate_source is not None
              else zodiac.source_snapshot(cache))
    source_record = source_hashes(source)
    require(source_record and (source / "src/dlp_reasoner/engine.py").is_file(),
            "invalid candidate source snapshot")
    driver_hashes = {name: sha(ROOT / name) for name in
                     ("benchmarks/zodiac_native.py", "benchmarks/zodiac.py", "benchmarks/lubm.py")}
    report = {"schema_version": 1, "benchmark": "native-ZodiacEdge-LUBM1-paired-v1",
              "started_utc": datetime.now(timezone.utc).isoformat(),
              "platform": platform.platform(), "machine": platform.machine(),
              "cpu_count": os.cpu_count(), "python": sys.version,
              "upstream": manifest, "input_manifest": inputs,
              "candidate_source_sha256": source_record,
              "candidate_source_path": str(source), "driver_sha256": driver_hashes,
              "reference": reference, "reference_sha256": sha(reference_path),
              "protocol": {"blocks": blocks, "arms": ARMS, "timeout_seconds": 300,
                           "ordering": "alternating native/candidate paired blocks",
                           "seeds": list(range(7300, 7300 + blocks)),
                           "no_warmup": True, "os_caches_flushed": False}, "workers": []}
    output.parent.mkdir(parents=True, exist_ok=True)
    protocol_path.write_text(json.dumps(report, indent=2) + "\n")
    for block in range(blocks):
        order = ARMS if block % 2 == 0 else ARMS[::-1]
        for position, arm in enumerate(order):
            require(all(sha(ROOT / name) == value for name, value in driver_hashes.items()),
                    "benchmark driver changed during run")
            require(source_hashes(source) == source_record, "candidate source changed")
            require(sha(reference_path) == report["reference_sha256"], "reference changed")
            env = {**os.environ, "PYTHONHASHSEED": str(7300 + block),
                   "PYTHONDONTWRITEBYTECODE": "1",
                   "PYTHONPATH": os.pathsep.join([str(source / "src"), str(ROOT)])}
            command = [sys.executable, "-m", "benchmarks.zodiac_native", "--worker", arm,
                       "--cache", str(cache), "--data-cache", str(data_cache),
                       "--native-cache", str(native_cache), "--reference", str(reference_path)]
            try:
                completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                                           text=True, timeout=300, check=False)
                require(completed.returncode == 0,
                        "worker failed: " + completed.stdout[-5000:] + completed.stderr[-5000:])
                result = json.loads(completed.stdout)
                require(not result.get("failure"), "worker failed: " + str(result.get("failure")))
                if arm == "candidate":
                    require(result["source_sha256"] == source_record, "wrong candidate source")
                else:
                    require(result["upstream"] == manifest, "upstream source changed during run")
                if report["workers"]:
                    require(result["edb_sha256"] == report["workers"][0]["edb_sha256"], "EDB drift")
            except Exception as exc:
                report["failure"] = {"block": block, "arm": arm, "type": type(exc).__name__,
                                     "message": str(exc)}
                break
            result.update(block=block, position=position)
            report["workers"].append(result)
            print(f"{block + 1}/{blocks} {arm}: both complete rule transactions validated", flush=True)
        if report.get("failure"):
            break
    if not report.get("failure"):
        keys = ("construct_and_materialize_seconds", "insert_seconds", "delete_seconds")
        report["timed_keys"] = keys
        report["summary"] = {}
        for arm in ARMS:
            report["summary"][arm] = {}
            for marker in ("*", "#"):
                report["summary"][arm][marker] = {}
                for key in keys:
                    values = [row["transactions"][marker][key] for row in report["workers"]
                              if row["arm"] == arm]
                    report["summary"][arm][marker][key] = {
                        "median": statistics.median(values), "minimum": min(values), "maximum": max(values)}
        report["paired_candidate_over_native"] = {}
        for marker in ("*", "#"):
            report["paired_candidate_over_native"][marker] = {}
            for key in keys:
                ratios = []
                for block in range(blocks):
                    pair = {row["arm"]: row["transactions"][marker][key]
                            for row in report["workers"] if row["block"] == block}
                    ratios.append(pair["candidate"] / pair["native"])
                report["paired_candidate_over_native"][marker][key] = {
                    "raw": ratios, "median": statistics.median(ratios)}
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    report["protocol_sha256"] = sha(protocol_path)
    output.write_text(json.dumps(report, indent=2) + "\n")
    output.with_suffix(".md").write_text(markdown(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / "tmp/zodiac-lubm")
    parser.add_argument("--data-cache", type=Path, default=ROOT / "tmp/lubm-official")
    parser.add_argument("--native-cache", type=Path, default=ROOT / "tmp/zodiac-native")
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--candidate-source", type=Path,
                        help="reuse an immutable source snapshot from the primary study")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--worker", choices=ARMS)
    parser.add_argument("--blocks", type=int, default=4)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/zodiac-native-results.json")
    args = parser.parse_args()
    if args.prepare:
        print(json.dumps(prepare_native(args.native_cache), indent=2))
    elif args.worker:
        require(args.reference is not None, "worker needs --reference")
        try:
            reference = json.loads(args.reference.read_text())
            if args.worker == "native":
                result = native_worker(args.cache, args.data_cache, args.native_cache, reference)
            else:
                result = zodiac.worker(args.cache, args.data_cache, "candidate", reference, fact_samples=0)
                result["arm"] = "candidate"
                result["all_closures_match"] = result["all_complete_tuple_digests_match_naive"]
        except Exception as exc:
            result = {"failure": {"type": type(exc).__name__, "message": str(exc),
                                  "traceback": traceback.format_exc()}}
        print(json.dumps(result))
    else:
        require(args.reference is not None, "measurement needs --reference")
        report = run(args.cache, args.data_cache, args.native_cache, args.reference, args.output,
                     args.blocks, args.candidate_source)
        if report.get("failure"):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
