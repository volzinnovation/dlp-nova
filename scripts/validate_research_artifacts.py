#!/usr/bin/env python3
"""Validate the completed v3 factorial report and its exact-source archive offline.

This checks artifact consistency and recomputes statistics; it does not execute
archived code, repeat experiments, or authenticate the physical measurements.
The initial/final closure digests describe actual stored facts. The report's
final_assertions_sha256 and final_rules_sha256 describe the expected transaction
state; these fields do not independently attest to Engine.asserted or rules.
Run after the benchmark has finished, not while it is replacing its report.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.research import (  # noqa: E402
    CONFIGURATIONS, HISTORICAL_BASELINE, build_cases, execution_orders,
    promotion_assessment, summarize,
)

SOURCE_PATHS = {"benchmarks/research.py"} | {
    f"src/dlp_reasoner/{name}.py" for name in
    ("__init__", "__main__", "cli", "compiler", "engine", "model", "reasoner", "schema", "support")
}
PROTOCOL_PATH = "benchmarks/research-protocol-v3.json"
BASE_COMMIT = "8ce254fb011c2a2fa72345e66a25373c0885273a"
HASH_FIELDS = ("input_sha256", "initial_sha256", "final_sha256",
               "final_assertions_sha256", "final_rules_sha256")
MAX_JSON_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024


class ArtifactError(ValueError):
    """A completed research artifact violates its declared evidence contract."""


def require(condition, message):
    if not condition:
        raise ArtifactError(message)


def _bad_constant(value):
    raise ArtifactError(f"Nonfinite JSON number: {value}")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def decode_json(data):
    return json.loads(data, parse_constant=_bad_constant, object_pairs_hook=_unique_object)


def read_json(path):
    require(path.stat().st_size <= MAX_JSON_BYTES, f"JSON artifact too large: {path.name}")
    return decode_json(path.read_bytes())


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def valid_hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def positive(value):
    return (type(value) in (float, int) and math.isfinite(value) and value > 0)


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def same_structure(actual, expected, path="summary"):
    """Compare all fields; permit only tiny floating-point portability error."""
    if type(expected) is bool:
        require(type(actual) is bool and actual is expected, f"Incorrect {path}")
    elif isinstance(expected, dict):
        require(isinstance(actual, dict) and actual.keys() == expected.keys(), f"Fields differ: {path}")
        for key in expected:
            same_structure(actual[key], expected[key], f"{path}.{key}")
    elif isinstance(expected, list):
        require(isinstance(actual, list) and len(actual) == len(expected), f"Length differs: {path}")
        for index, (left, right) in enumerate(zip(actual, expected)):
            same_structure(left, right, f"{path}[{index}]")
    elif type(expected) is float:
        require(type(actual) in (int, float) and math.isfinite(actual)
                and math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-15), f"Incorrect {path}")
    else:
        require(type(actual) is type(expected) and actual == expected, f"Incorrect {path}")


def validate_archive(report, manifest, archive_path):
    require(archive_path.stat().st_size <= MAX_ARCHIVE_BYTES, "Source archive too large")
    archive_bytes = archive_path.read_bytes()
    require(manifest["archive"] == archive_path.name, "Archive filename differs from manifest")
    require(valid_hash(manifest["archive_sha256"]), "Invalid archive SHA-256")
    require(sha256(archive_bytes) == manifest["archive_sha256"], "Source archive SHA-256 mismatch")
    require(manifest["base_commit"] == report["git_head"] == BASE_COMMIT,
            "Source archive base commit differs from measured checkout")
    hashes = report["source_sha256"]
    require(isinstance(hashes, dict) and set(hashes) == SOURCE_PATHS, "Measured source inventory differs")
    require(all(valid_hash(value) for value in hashes.values()), "Invalid measured source SHA-256")
    require(valid_hash(report["protocol_sha256"]), "Invalid protocol SHA-256")
    expected = {**hashes, PROTOCOL_PATH: report["protocol_sha256"]}
    require(manifest["files_sha256"] == expected, "Manifest files differ from measured sources/protocol")
    members = {}
    total = 0
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive:
            name = member.name
            path = PurePosixPath(name)
            require(member.isfile() and not path.is_absolute() and ".." not in path.parts
                    and "\\" not in name and str(path) == name,
                    "Archive contains unsafe/nonregular member")
            require(name in expected and name not in members, "Archive contains unexpected/duplicate member")
            total += member.size
            require(0 <= member.size <= MAX_ARCHIVE_BYTES and total <= MAX_ARCHIVE_BYTES,
                    "Expanded source archive exceeds size bound")
            stream = archive.extractfile(member)
            require(stream is not None, "Archive member has no readable content")
            data = stream.read()
            require(len(data) == member.size and sha256(data) == expected[name],
                    f"Archived content SHA-256 mismatch: {name}")
            members[name] = data
    require(set(members) == set(expected), "Source archive is missing measured files")
    archived_protocol = decode_json(members[PROTOCOL_PATH])
    same_structure(report["protocol"], archived_protocol, "archived protocol")
    return len(members)


def validate_worker(row, case, *, memory, expected_identity=None):
    require(row["case"] == case and row["configuration"] in CONFIGURATIONS,
            "Worker case/configuration mismatch")
    require(row["validation"] == "passed", "Worker validation failed")
    require(all(valid_hash(row[key]) for key in HASH_FIELDS), "Malformed worker outcome hash")
    require(integer(row["final_facts"], 1), "Invalid final fact count")
    identity = {key: row[key] for key in (*HASH_FIELDS, "final_facts")}
    if expected_identity is not None:
        require(identity == expected_identity, "Full outcome differs across workers")
    for name, operation in (("initial_stats", "materialize"), ("update_stats", "update")):
        stats = row[name]
        require(stats["complete"] is True and stats["consistent"] is True,
                f"Incomplete/inconsistent {name}")
        require(stats["operation"] == operation and stats["strategy"] == "semi-naive",
                f"Unexpected operation/strategy in {name}")
        require(positive(stats["seconds"]), f"Invalid seconds in {name}")
        require(integer(stats["materialized_facts"], 1) and integer(stats["asserted_facts"]),
                f"Invalid fact counters in {name}")
        require(stats["asserted_facts"] <= stats["materialized_facts"],
                f"Assertion count exceeds closure in {name}")
    require(row["initial_stats"]["update_method"] == "full", "Initial materialization method differs")
    method = "incremental-insert" if case["family"] == "unary" else "dred-rules"
    require(row["update_stats"]["update_method"] == method, "Update silently changed algorithm")
    require(row["update_stats"]["materialized_facts"] == row["final_facts"], "Final fact counters differ")
    require(positive(row["worker_seconds"]) and integer(row["rss_bytes"], 1), "Invalid process measurements")
    if memory:
        require(row["materialize_seconds"] is None and row["update_seconds"] is None,
                "Instrumented memory timing mixed with ordinary samples")
        measurement = row["memory"]
        require(isinstance(measurement, dict), "Missing separate memory measurement")
        peak, retained = measurement["peak_python_bytes"], measurement["retained_python_bytes"]
        require(integer(peak) and integer(retained) and peak >= retained, "Invalid Python memory counters")
        require(row["hash_seed"] == "2004", "Memory worker hash seed differs")
    else:
        require(row["memory"] is None, "Ordinary timing used memory instrumentation")
        require(positive(row["materialize_seconds"]) and positive(row["update_seconds"]),
                "Nonpositive/nonfinite ordinary timing")
    return identity


def validate_data(report, manifest, archive_path):
    require(report["status"] == "passed" and not report.get("error"), "Research experiment did not finish successfully")
    protocol = report["protocol"]
    require(protocol["protocol"] == "research-factorial-v3", "Unsupported research protocol")
    require(type(protocol["blocks"]) is int and protocol["blocks"] == 9, "Expected nine independent blocks")
    require(protocol["historical_baseline"] == HISTORICAL_BASELINE
            and protocol["pre_research_commit"] == BASE_COMMIT, "Reference commits differ")
    expected_cases = build_cases()
    require(len(expected_cases) == 18, "Predeclared 18-case matrix differs")
    same_structure(protocol["case_matrix"], expected_cases, "predeclared case matrix")
    same_structure(protocol["configurations"],
                   {name: list(flags) for name, flags in CONFIGURATIONS.items()},
                   "factorial configurations")
    archive_files = validate_archive(report, manifest, archive_path)
    controls = report["finite_oracle_checks"]
    small = build_cases(small=True)
    require(len(controls) == len(small) == 9, "Missing/duplicate finite-oracle controls")
    for control, case in zip(controls, small):
        require(control["case"] == case and type(control["configurations"]) is int
                and control["configurations"] == 4
                and control["status"] == "passed", "Finite-oracle validation differs")
    require(len(report["cases"]) == 18, "Missing/duplicate experimental case")
    orders = execution_orders(9)
    for item, case in zip(report["cases"], expected_cases):
        require(item["case"] == case and item["orders"] == orders, "Case/execution order differs")
        rows = item["runs"]
        require(len(rows) == 36, "Missing/duplicate timed worker")
        identity = None
        initial_count = None
        for index, row in enumerate(rows):
            block, position = divmod(index, 4)
            require(type(row["block"]) is int and row["block"] == block
                    and type(row["position"]) is int and row["position"] == position,
                    "Missing/duplicate block-position pair")
            require(row["configuration"] == orders[block][position]
                    and row["hash_seed"] == str(2004 + block), "Worker ordering or paired hash seed differs")
            identity = validate_worker(row, case, memory=False, expected_identity=identity)
            if initial_count is None:
                initial_count = row["initial_stats"]["materialized_facts"]
            require(row["initial_stats"]["materialized_facts"] == initial_count,
                    "Initial closure counts differ across workers")
        memory_rows = item["memory_runs"]
        require(len(memory_rows) == 4
                and [row["configuration"] for row in memory_rows] == list(CONFIGURATIONS),
                "Missing/duplicate memory configuration")
        for row in memory_rows:
            validate_worker(row, case, memory=True, expected_identity=identity)
            require(row["initial_stats"]["materialized_facts"] == initial_count,
                    "Memory-worker initial closure differs")
        same_structure(item["summary"], summarize(rows), "recomputed summary")
    same_structure(report["promotion_assessment"], promotion_assessment(report["cases"]),
                   "recomputed promotion assessment")
    return {"status": "passed", "cases": 18, "timed_workers": 648, "memory_workers": 72,
            "finite_oracle_controls": 36, "archived_files": archive_files,
            "adaptive_threshold_met": report["promotion_assessment"]["adaptive_threshold_met"],
            "support_threshold_met": report["promotion_assessment"]["support_threshold_met"]}


def validate_artifacts(report_path, manifest_path, archive_path):
    try:
        return validate_data(read_json(Path(report_path)), read_json(Path(manifest_path)), Path(archive_path))
    except ArtifactError:
        raise
    except (OSError, KeyError, TypeError, ValueError, OverflowError, EOFError,
            RecursionError, tarfile.TarError) as exc:
        raise ArtifactError(f"Malformed or unreadable research artifact: {exc}") from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / "benchmarks/research-results.json")
    parser.add_argument("--manifest", type=Path, default=ROOT / "benchmarks/research-source.json")
    parser.add_argument("--archive", type=Path, default=ROOT / "benchmarks/research-source.tar.gz")
    args = parser.parse_args()
    try:
        result = validate_artifacts(args.report, args.manifest, args.archive)
    except ArtifactError as exc:
        print(f"Research artifact validation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
