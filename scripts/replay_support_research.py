#!/usr/bin/env python3
"""Post-hoc support-certificate robustness replication; run with no other benchmarks.

Eight support workloads, nine independent AB/BA pairs each, no tracemalloc.
The original factorial experiment and its predeclared adoption thresholds remain
unchanged. This script refuses to replace an existing output artifact.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.research import (  # noqa: E402
    HISTORICAL_BASELINE, build_cases, git, paired_summary, protected_output,
    require, sources,
)
from scripts.validate_research_artifacts import HASH_FIELDS, validate_worker  # noqa: E402

CONFIGURATIONS = ("fixed-dred", "fixed-support")
ORIGINAL = ROOT / "benchmarks/research-results.json"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def measured_sources():
    paths = (Path(__file__), ROOT / "scripts/validate_research_artifacts.py")
    return {**sources(), **{str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in paths}}


def atomic_write(path, content):
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, prefix=path.name + ".",
                                     suffix=".partial", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(content)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def markdown(report):
    lines = ["# Supplemental support-certificate replication", "",
             f"Status: **{report['status']}**.", "",
             "This post-hoc robustness check was prompted by a Bach benchmark artifact changing "
             "during the original factorial run. The origin and extent of possible concurrent "
             "host activity were not established. This replication does not replace the original "
             "measurements, alter their adoption thresholds, or change the b1254c4 baseline.", "",
             "Each workload uses nine independently launched process pairs, alternating AB/BA "
             "order with the same explicit hash seed within each pair. Both versions use the "
             "fixed unary plan; only support certificates differ. Memory instrumentation is off.", "",
             "| Case | DRed median ms | Support median ms | Paired median ratio | Interval |",
             "|---|---:|---:|---:|---|"]
    for item in report["cases"]:
        summary = item.get("summary")
        if not summary:
            continue
        interval = summary["descriptive_paired_bootstrap_95_interval"]
        lines.append(f"| {json.dumps(item['case'], sort_keys=True)} | "
                     f"{summary['before_median_seconds'] * 1000:.3f} | "
                     f"{summary['after_median_seconds'] * 1000:.3f} | "
                     f"{summary['median_ratio']:.4g} | [{interval[0]:.4g}, {interval[1]:.4g}] |")
    lines += ["", "Ratios below one favor support certificates. Intervals are descriptive paired "
              "resampling intervals from one host. All observations, process orders, seeds, work "
              "counters and source/driver/protocol digests are retained in JSON. The full actual "
              "initial/final closure hashes must match both the pair and original factorial case. "
              "The assertion/rule hashes identify the expected transaction state. Each worker "
              "also checks its actual updated closure against fresh fixed-plan recomputation."]
    if report.get("error"):
        lines += ["", f"Failure: {report['error']}"]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/research-support-replay.json")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    require(args.timeout > 0, "timeout must be positive")
    output = protected_output(args.output)
    require(not output.exists() and not output.with_suffix(".md").exists(),
            "Output already exists; preserve it and choose a new --output path")
    require(output != ORIGINAL, "Cannot overwrite the original factorial report")
    original_bytes = ORIGINAL.read_bytes()
    original = json.loads(original_bytes)
    require(original["status"] == "passed", "Original factorial experiment must be complete")
    cases = [case for case in build_cases() if case["family"] == "support"]
    require(len(cases) == 8, "Expected exactly eight support workloads")
    originals = {canonical(item["case"]): item for item in original["cases"]}
    require(all(canonical(case) in originals for case in cases), "Original support cases are missing")
    protocol = {
        "name": "post-hoc-support-robustness-v1",
        "registered_utc": datetime.now(timezone.utc).isoformat(),
        "reason": "A separate Bach benchmark artifact was rewritten during the original factorial "
                  "run. The origin is unresolved; possible concurrent host activity motivates "
                  "independent paired replication after other benchmarks have finished.",
        "classification": "Post-hoc robustness replication, not a replacement predeclared experiment",
        "historical_baseline": HISTORICAL_BASELINE,
        "original_factorial_sha256": digest(original_bytes),
        "original_protocol_sha256": original["protocol_sha256"],
        "case_matrix": cases, "pairs_per_case": 9, "configurations": list(CONFIGURATIONS),
        "order": "AB for even pair numbers, BA for odd pair numbers; A=fixed-dred, B=fixed-support",
        "hash_seed": "3000 + zero-based pair number; identical within each independent-process pair",
        "primary_endpoint": "Complete atomic Engine.update wall seconds, including setup and validation",
        "measurement": "One cold worker per observation, no discarded warmup, no memory instrumentation; "
                       "generation, output hashing and fresh-closure validation outside the update timer",
        "correctness": "Initial and updated completeness/consistency, actual full closure hashes, "
                       "input and expected transaction hashes must agree with the original case and "
                       "the paired worker; every worker validates against fresh recomputation",
        "adoption": "No changes to the original promotion thresholds or automatic default changes",
        "uncertainty": "Nine paired observations; raw ratios and descriptive paired bootstrap intervals; "
                       "single-host evidence, no claim that all external host activity is controlled",
    }
    source_hashes = measured_sources()
    source_digest, protocol_digest = digest(canonical(source_hashes)), digest(canonical(protocol))
    driver_digest = source_hashes[str(Path(__file__).relative_to(ROOT))]
    report = {"status": "registered", "protocol": protocol, "protocol_sha256": protocol_digest,
              "source_sha256": source_hashes, "source_manifest_sha256": source_digest,
              "driver_sha256": driver_digest, "git_head": git("rev-parse", "HEAD"),
              "git_dirty": bool(git("status", "--porcelain")), "python": sys.version,
              "platform": platform.platform(), "machine": platform.machine(),
              "cpu_count": os.cpu_count(), "cases": []}

    def save():
        output.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(output, json.dumps(report, indent=2) + "\n")
        atomic_write(output.with_suffix(".md"), markdown(report))

    def verify_frozen():
        require(measured_sources() == source_hashes, "Source or driver changed during replication")
        on_disk = json.loads(output.read_bytes())
        require(digest(canonical(on_disk["protocol"])) == protocol_digest
                and on_disk["protocol_sha256"] == protocol_digest, "Registered protocol changed")
        require(digest(ORIGINAL.read_bytes()) == protocol["original_factorial_sha256"],
                "Original factorial report changed during replication")

    # Persist the complete protocol and source identity before launching workers.
    save()
    report["status"] = "running"
    save()
    try:
        for number, case in enumerate(cases):
            original_case = originals[canonical(case)]
            original_row = original_case["runs"][0]
            expected = {key: original_row[key] for key in (*HASH_FIELDS, "final_facts")}
            item = {"case": case, "pairs": [],
                    "original_factorial_support_only_summary": original_case["summary"]["support-only"]}
            report["cases"].append(item)
            before, after = [], []
            for pair in range(9):
                seed = 3000 + pair
                order = list(CONFIGURATIONS if pair % 2 == 0 else reversed(CONFIGURATIONS))
                pair_result = {"pair": pair, "hash_seed": seed, "order": order, "workers": {}}
                item["pairs"].append(pair_result)
                for position, name in enumerate(order):
                    verify_frozen()
                    env = os.environ.copy()
                    env.update(PYTHONHASHSEED=str(seed), PYTHONOPTIMIZE="0", PYTHONNOUSERSITE="1",
                               PYTHONPATH=os.pathsep.join((str(ROOT / "src"), str(ROOT))))
                    request = {"case": case, "configuration": name, "memory": False}
                    load_before = os.getloadavg() if hasattr(os, "getloadavg") else None
                    start = time.perf_counter()
                    process = subprocess.run([sys.executable, "-m", "benchmarks.research", "--worker",
                                              json.dumps(request)], cwd=ROOT, env=env, text=True,
                                             capture_output=True, timeout=args.timeout)
                    require(process.returncode == 0, f"Worker failed: {process.stderr[-4000:]}")
                    row = json.loads(process.stdout)
                    row["worker_seconds"] = time.perf_counter() - start
                    require(row["configuration"] == name and row["hash_seed"] == str(seed),
                            "Worker configuration or paired seed differs")
                    validate_worker(row, case, memory=False, expected_identity=expected)
                    verify_frozen()
                    row.update(position=position, source_manifest_sha256=source_digest,
                               driver_sha256=driver_digest, protocol_sha256=protocol_digest,
                               host_load_before=load_before,
                               host_load_after=os.getloadavg() if hasattr(os, "getloadavg") else None)
                    pair_result["workers"][name] = row
                    save()
                before.append(pair_result["workers"]["fixed-dred"]["update_seconds"])
                after.append(pair_result["workers"]["fixed-support"]["update_seconds"])
            item["summary"] = paired_summary(before, after)
            save()
            print(f"Validated support replication {number + 1}/8: {case}", flush=True)
        report["status"] = "passed"
        report["validated_workers"] = 144
    except Exception as exc:
        report["status"], report["error"] = "failed", str(exc)
        save()
        raise
    save()


if __name__ == "__main__":
    main()
