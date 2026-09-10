"""Run DLP Nova's executable examples and preserve their assertions and provenance.

Requires the development environment, native build tools/libraries and GEOS.
This is correctness evidence for the fixtures, not a timing benchmark. Earlier
paper artifacts are not modified. Run spatial timings separately with
python -m benchmarks.extension_queries.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = (
    ("examples/bach_temporal/run_queries.py", "--backend", "both"),
    ("examples/traffic_signs/run_queries.py", "--backend", "both"),
    ("examples/temporal_geo/run_queries.py", "--backend", "both"),
    ("examples/dlp_nova/extension-demo.py", "--backend", "both", "--geos"),
)


def source_hashes():
    paths = {ROOT / "pyproject.toml", ROOT / "uv.lock", Path(__file__).resolve(),
             ROOT / "benchmarks/extension_queries.py"}
    suffixes = {".py", ".cpp", ".c", ".h", ".hpp", ".dlp", ".dlq", ".json", ".ttl"}
    for directory in ("src/dlp_reasoner", "examples/bach_temporal", "examples/traffic_signs",
                      "examples/temporal_geo", "examples/dlp_nova"):
        paths.update(path for path in (ROOT / directory).rglob("*")
                     if path.is_file() and path.suffix in suffixes
                     and "__pycache__" not in path.parts)
    return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "benchmarks/dlp-nova-example-results.json")
    args = parser.parse_args()
    before = source_hashes()
    report = {
        "purpose": "asserted example correctness; not performance or universal conformance",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(), "platform": platform.platform(),
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                            text=True).strip(),
        "working_tree_dirty": bool(subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()),
        "source_files_sha256": before,
        "runs": [],
    }
    for command in COMMANDS:
        completed = subprocess.run([sys.executable, *command], cwd=ROOT,
                                   text=True, capture_output=True, check=True)
        report["runs"].append({"command": ["python", *command], "exit_code": 0,
                               "results": json.loads(completed.stdout),
                               "stderr": completed.stderr})
        print(f"Passed: {' '.join(command)}", flush=True)
    if source_hashes() != before:
        raise RuntimeError("Evidence inputs changed during collection; rerun on stable sources")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
