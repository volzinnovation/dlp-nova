#!/usr/bin/env python3
"""Supplemental paired replay; never replaces recorded or immutable benchmarks.

Run only after other benchmarks have finished:
  .venv/bin/python scripts/replay_b1254c4.py

Each of seven fixed workloads runs in five baseline/current pairs. Each worker is
an independently launched process with one repetition; AB/BA order alternates
and both workers in a pair use the same explicit Python hash seed. These are new
measurements of the archived implementation, not replacements for its historical
measurements. Five pairs still provide limited evidence about performance noise.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import random
import statistics
import subprocess
import tarfile
import tempfile
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "b1254c441731ca4fdf32ea83570ff99aaa84ac2a"
RECORDED_SHA256 = "6f0bc493cae0fb96b474405eb9496dc9ce2c3155b313f2bcd3de49b3dc8b51e2"
REFERENCE = ROOT / "benchmarks/baselines/b1254c4/results.json"
CASES = [
    {"kind": "transitive", "size": 100},
    {"kind": "cardinality", "depth": 5, "ipc": 3},
    {"kind": "existential", "size": 100},
    {"kind": "factored-unions", "pairs": 64, "size": 128},
    {"kind": "taxonomy", "depth": 5, "ipc": 9, "variant": "PF"},
    {"kind": "maintenance", "depth": 3, "change_percent": 10},
    {"kind": "maintenance", "depth": 5, "change_percent": 10},
]
PHASES = ("parse_seconds", "compile_seconds", "materialize_seconds", "query_seconds",
          "property_query_seconds", "subsumption_seconds")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT, stderr=subprocess.PIPE)


def source_hashes(checkout):
    paths = sorted([*(checkout / "src/dlp_reasoner").glob("*.py"),
                    *(checkout / "benchmarks").glob("*.py")])
    return {str(path.relative_to(checkout)): sha256(path) for path in paths}


def extract_baseline():
    require(sha256(REFERENCE) == RECORDED_SHA256, "Pinned historical report changed")
    recorded = json.loads(REFERENCE.read_text())
    (ROOT / "tmp").mkdir(exist_ok=True)
    checkout = Path(tempfile.mkdtemp(prefix="replay-b1254c4-", dir=ROOT / "tmp"))
    raw = git("archive", "--format=tar", COMMIT, "src", "benchmarks", "pyproject.toml")
    # Copy only regular archived files/directories into a newly owned directory.
    # No shell extraction, Git checkout, branch changes, or package installation.
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for member in archive.getmembers():
            target = checkout / member.name
            require(target.resolve().is_relative_to(checkout), "Unsafe archive path")
            require(member.isfile() or member.isdir(), "Archive contains a nonregular entry")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(member).read())
    baseline_sources = source_hashes(checkout)
    require(baseline_sources == recorded["environment"]["source_sha256"],
            "Archived Python source hashes differ from the pinned recorded run")
    require(sha256(checkout / "benchmarks/results.json") == RECORDED_SHA256,
            "Archived report differs from the immutable reference")
    return checkout, recorded, baseline_sources


def environment(checkout, seed):
    env = os.environ.copy()
    env.update(PYTHONPATH=os.pathsep.join((str(checkout / "src"), str(checkout))),
               PYTHONHASHSEED=str(seed), PYTHONNOUSERSITE="1", PYTHONOPTIMIZE="0")
    return env


def verify_imports(python, checkout):
    code = ("import benchmarks, dlp_reasoner, json, platform, sys; "
            "print(json.dumps({'benchmarks':benchmarks.__file__, "
            "'reasoner':dlp_reasoner.__file__, 'python':sys.version, "
            "'platform':platform.platform(), 'machine':platform.machine()}))")
    result = subprocess.run([str(python), "-c", code], cwd=checkout,
                            env=environment(checkout, 2004), text=True, capture_output=True, check=True)
    locations = json.loads(result.stdout)
    require(Path(locations["benchmarks"]).resolve().is_relative_to(checkout / "benchmarks"),
            "Worker imported the wrong benchmark package")
    require(Path(locations["reasoner"]).resolve().is_relative_to(checkout / "src/dlp_reasoner"),
            "Worker imported the wrong reasoner package")
    return locations


def run_worker(python, checkout, case, seed, timeout):
    started = time.perf_counter()
    process = subprocess.run(
        [str(python), "-m", "benchmarks.run", "--worker", json.dumps(case)],
        cwd=checkout, env=environment(checkout, seed), text=True, capture_output=True, timeout=timeout)
    require(process.returncode == 0, f"Worker failed: {process.stderr[-4000:]}")
    result = json.loads(process.stdout)
    require(result.get("validation") == "passed", "Worker did not validate its result")
    require(result["case"] == case, "Worker case controls changed")
    result["worker_wall_seconds"] = time.perf_counter() - started
    return result


def check_pair(before, after, recorded):
    require(before["input_sha256"] == after["input_sha256"] == recorded["input_sha256"],
            "Worker inputs differ from each other or the recorded case")
    require(before["workload"] == after["workload"] == recorded["workload"],
            "Workload expectations changed")
    require(before["materialized_fact_counts"] == after["materialized_fact_counts"],
            "Initial closure counts differ between implementations")
    require(set(before["materialized_fact_counts"]) == set(recorded["materialized_fact_counts"]),
            "Initial closure counts differ from the recorded case")
    old_operations = before.get("maintenance_operations", {})
    new_operations = after.get("maintenance_operations", {})
    require(old_operations.keys() == new_operations.keys(), "Maintenance operations changed")
    for name, operation in old_operations.items():
        left, right = operation["samples"][0], new_operations[name]["samples"][0]
        for field in ("added_facts", "removed_facts", "added_rules", "removed_rules", "closure_facts"):
            require(left[field] == right[field], f"{name}: {field} changed")
        require(left["validation"] == right["validation"] == "matches-fresh-closure",
                f"{name}: missing fresh-closure verification")
    return {"verified": True, "input_matches_recorded": True, "initial_counts_match": True,
            "query_evidence": "Both workers passed the same workload-specific expected-answer checks; "
                              "the archived worker does not save full answer-set digests.",
            "maintenance_operations_verified": list(old_operations)}


def measurements(result):
    values = {phase: result[phase]["samples"][0] for phase in PHASES if phase in result}
    for name, operation in result.get("maintenance_operations", {}).items():
        values[f"maintenance.{name}.update"] = operation["seconds"]["samples"][0]
        values[f"maintenance.{name}.rebuild"] = operation["rebuild_seconds"]["samples"][0]
    return values


def summarize(pairs):
    old = [measurements(pair["baseline"]) for pair in pairs]
    new = [measurements(pair["current"]) for pair in pairs]
    result = {}
    for phase in old[0]:
        before, after = [row[phase] for row in old], [row[phase] for row in new]
        old_median, new_median = statistics.median(before), statistics.median(after)
        paired = [right / left for left, right in zip(before, after) if left > 0]
        interval = None
        if len(pairs) >= 2 and all(value > 0 for value in before + after):
            rng = random.Random(2004)
            ratios = []
            for _ in range(2000):
                indices = rng.choices(range(len(pairs)), k=len(pairs))
                ratios.append(statistics.median(after[i] for i in indices)
                              / statistics.median(before[i] for i in indices))
            ratios.sort()
            interval = [ratios[round(0.025 * (len(ratios) - 1))],
                        ratios[round(0.975 * (len(ratios) - 1))]]
        result[phase] = {"baseline_samples": before, "current_samples": after,
                         "baseline_median": old_median, "current_median": new_median,
                         "after_over_before": new_median / old_median if old_median else None,
                         "paired_ratios": paired,
                         "median_paired_ratio": statistics.median(paired) if paired else None,
                         "paired_bootstrap_95_percent_interval": interval}
    return result


def markdown(report):
    lines = ["# Supplemental paired replay of b1254c4", "",
             f"Status: **{report['status']}**. Reference commit: `{COMMIT}`.", "",
             "These are new measurements of the archived baseline and current implementation, "
             "not replacements for the pinned historical report. Each pair launches two independent "
             "workers with one repetition and the same explicit hash seed, alternating AB/BA order. "
             "Five pairs give limited evidence about remaining timing noise; intervals are descriptive "
             "paired resampling intervals, not guaranteed confidence coverage.", "",
             f"Current checkout: `{report['current_git']['head']}`; "
             f"dirty: {report['current_git']['dirty']}. Full source hashes, input hashes, "
             "worker outputs, assertions and execution orders are retained in JSON.", "",
             "| Case | Phase | Baseline median ms | Current median ms | Current / baseline | Paired interval |",
             "|---|---|---:|---:|---:|---:|"]
    for case in report["cases"]:
        name = json.dumps(case["case"], sort_keys=True)
        for phase, values in case.get("summary", {}).items():
            ratio, interval = values["after_over_before"], values["paired_bootstrap_95_percent_interval"]
            ratio_text = f"{ratio:.4g}" if ratio is not None else "—"
            interval_text = f"[{interval[0]:.4g}, {interval[1]:.4g}]" if interval else "—"
            lines.append(f"| {name} | {phase} | {values['baseline_median'] * 1000:.3f} | "
                         f"{values['current_median'] * 1000:.3f} | {ratio_text} | {interval_text} |")
    if report.get("error"):
        lines += ["", f"Failure: {report['error']}"]
    lines += ["", "Work counters remain in each raw worker output. Candidate rows measure Python "
              "binding visits, excluding C-level set-intersection probes. Whole worker wall time "
              "includes startup/generation/validation and is separate from the phase timings above."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/replay-results.json")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    output = args.output.resolve()
    protected = [ROOT / "benchmarks/results.json", ROOT / "benchmarks/baseline-results.json", REFERENCE]
    protected += [path.with_suffix(".md") for path in protected]
    for path in (output, output.with_suffix(".md")):
        require(not path.is_relative_to(ROOT / "benchmarks/baselines"), "Output cannot modify baselines")
        require(not any(path == reference or (path.exists() and reference.exists()
                                              and path.samefile(reference)) for reference in protected),
                "Output cannot overwrite a recorded benchmark")
    python = ROOT / ".venv/bin/python"
    require(python.is_file(), "Run with the existing locked .venv Python")
    baseline, recorded, baseline_sources = extract_baseline()
    current_sources = source_hashes(ROOT)
    require(current_sources["benchmarks/workloads.py"] == baseline_sources["benchmarks/workloads.py"],
            "Input generator changed; replay needs matching workloads")
    driver_hash = sha256(__file__)
    status = git("status", "--porcelain=v1", "--untracked-files=all").decode().splitlines()
    report = {"status": "running", "supplemental": True,
              "timestamp": datetime.now(timezone.utc).isoformat(), "baseline_commit": COMMIT,
              "recorded_baseline_sha256": RECORDED_SHA256, "pairs_per_case": 5,
              "measurement_protocol": "phase-timings-v1", "driver_sha256": driver_hash,
              "python_executable": str(python), "baseline_checkout": str(baseline),
              "baseline_source_sha256": baseline_sources, "current_source_sha256": current_sources,
              "baseline_runtime": verify_imports(python, baseline),
              "current_runtime": verify_imports(python, ROOT),
              "current_git": {"head": git("rev-parse", "HEAD").decode().strip(),
                              "dirty": bool(status), "status_porcelain": status}, "cases": []}
    output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        output.write_text(json.dumps(report, indent=2) + "\n")
        output.with_suffix(".md").write_text(markdown(report))

    def check_sources():
        require(source_hashes(ROOT) == current_sources and source_hashes(baseline) == baseline_sources
                and sha256(__file__) == driver_hash, "Code changed during paired replay")
        require(sha256(REFERENCE) == RECORDED_SHA256, "Pinned report changed during replay")

    try:
        for number, controls in enumerate(CASES):
            case = {**controls, "repeats": 1}
            original = next(row for row in recorded["results"]
                            if {key: value for key, value in row["case"].items() if key != "repeats"}
                            == controls)
            entry = {"case": controls, "pairs": []}
            report["cases"].append(entry)
            for pair_number in range(5):
                seed = 2004 + pair_number
                order = ["baseline", "current"] if (number + pair_number) % 2 == 0 else ["current", "baseline"]
                pair = {"pair": pair_number + 1, "hash_seed": seed, "order": order}
                print(json.dumps({"case": controls, "pair": pair_number + 1, "order": order}), flush=True)
                for version in order:
                    check_sources()
                    pair[version] = run_worker(python, baseline if version == "baseline" else ROOT,
                                               case, seed, args.timeout)
                    check_sources()
                pair["correctness"] = check_pair(pair["baseline"], pair["current"], original)
                entry["pairs"].append(pair)
                entry["summary"] = summarize(entry["pairs"])
                save()
        report["status"] = "passed"
    except Exception as exc:
        report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        save()
        raise
    save()
    print(f"Validated {5 * len(CASES)} paired comparisons; supplemental report: {output}")


if __name__ == "__main__":
    main()
