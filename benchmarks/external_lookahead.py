"""Post-hoc bounded lookahead study; one fresh process per query component.

Reuses the frozen official-dbgen component definitions and exact SQL oracle
without altering the original experiment. This is not full TPC-H SQL or RPT+.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import io
import json
import os
from pathlib import Path
import platform
import resource
import statistics
import subprocess
import sys
import tarfile
import time

from . import external_tpch as original

ROOT = original.ROOT
CONFIGURATIONS = ("b1254c4", "compiled", "lookahead")
CONTROLS = ("unique", "nonselective", "skewed", "empty-cycle")
PARAMETERS = dict(min_fanout=32, size_factor=4, sample_rows=4, probe_budget=1024)
ORIGINAL_COMPONENTS = dict(original.COMPONENTS)


def control_program(name):
    """Deterministic adverse controls; these are synthetic, not TPC-H data."""
    from dlp_reasoner.model import Atom, Program, Rule, Var
    x, y, z = map(Var, "xyz")
    if name == "nonselective":
        facts = {Atom(p, (i,)) for p in "RS" for i in range(64)}
        facts |= {Atom("T", (i, j)) for i in range(64) for j in range(64)}
        body = (Atom("R", (x,)), Atom("S", (y,)), Atom("T", (x, y)))
        variables = (x, y)
    else:
        body = (Atom("R", (x, y)), Atom("S", (y, z)), Atom("T", (z, x)))
        variables = (x, y, z)
        if name == "skewed":
            facts = {Atom("R", (i, i % 4)) for i in range(64)}
            facts |= {Atom("S", (i, j)) for i in range(4) for j in range(16)}
            facts |= {Atom("T", ((i * 7) % 16, i)) for i in range(64)}
        else:
            original.require(name in {"unique", "empty-cycle"}, "unknown control")
            offset = int(name == "empty-cycle")
            facts = {Atom(p, (i, i)) for p in "RS" for i in range(64)}
            facts |= {Atom("T", (i, (i + offset) % 64)) for i in range(64)}
    return Program([], facts), variables, Rule(None, body)


def independent_control(program, variables, rule):
    """Direct nested join, without production indexes, plans or evaluator."""
    from dlp_reasoner.model import Var
    relations = {}
    for fact in program.facts:
        relations.setdefault(fact.predicate, []).append(fact.args)
    bindings = [{}]
    for atom in rule.body:
        following = []
        for binding in bindings:
            for row in relations.get(atom.predicate, ()):
                extended = binding.copy()
                for term, value in zip(atom.args, row):
                    if isinstance(term, Var):
                        if term in extended and extended[term] != value:
                            break
                        extended[term] = value
                    elif term != value:
                        break
                else:
                    following.append(extended)
        bindings = following
    return [tuple(binding[v] for v in variables) for binding in bindings]


def control_worker(name):
    import dlp_reasoner
    from dlp_reasoner.engine import Engine, _SEED
    from dlp_reasoner.model import Atom, TOP
    started = time.perf_counter()
    program, variables, rule = control_program(name)
    encoding_seconds = time.perf_counter() - started
    started = time.perf_counter()
    engine = Engine(program).materialize()
    index_seconds = time.perf_counter() - started
    expected_facts = program.facts | {Atom(TOP, (term,)) for fact in program.facts for term in fact.args}
    expected_facts.add(Atom(TOP, (_SEED,)))
    original.require(engine.complete and engine.facts == expected_facts, "incorrect control base closure")
    started = time.perf_counter()
    rows = [tuple(binding[v] for v in variables) for binding in engine._solutions(rule)]
    join_seconds = time.perf_counter() - started
    original.require(engine.facts == expected_facts, "control query changed closure")
    expected = independent_control(program, variables, rule)
    original.require(len(rows) == len(set(rows)) and set(rows) == set(expected), "control answer mismatch")
    return {
        "queries": [{"control": name, "answers": len(rows), "answer_sha256": original.digest(rows),
                     "source_facts": len(program.facts), "source_facts_sha256": original.digest(
                         [(str(f.predicate), *f.args) for f in program.facts]),
                     "exact_independent_match": True, "exact_base_closure_match": True,
                     "base_closure_facts": len(engine.facts), "filter_projection_seconds": 0,
                     "encoding_seconds": encoding_seconds, "index_materialization_seconds": index_seconds,
                     "join_seconds": join_seconds,
                     "component_end_to_end_seconds": encoding_seconds + index_seconds + join_seconds,
                     "stats": engine.stats.copy()}],
        "source_sha256": original.source_hashes(Path(dlp_reasoner.__file__).resolve().parents[2]),
        "package_path": str(Path(dlp_reasoner.__file__).resolve()), "python": sys.version,
        "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024),
    }


def worker(cache, configuration, scale, query, control):
    from dlp_reasoner.engine import Engine
    if configuration != "b1254c4":
        from dlp_reasoner.joins import _Lookahead
        actual = dict(min_fanout=_Lookahead.MIN_FANOUT, size_factor=_Lookahead.SIZE_FACTOR,
                      sample_rows=_Lookahead.SAMPLE_ROWS, probe_budget=_Lookahead.PROBE_BUDGET)
        original.require(actual == PARAMETERS, "lookahead parameters changed")
        for option in ("_compiled_joins_enabled", "_incremental_index_enabled", "_incremental_validation_enabled"):
            original.require(getattr(Engine, option), "adopted default changed")
        Engine._join_lookahead_enabled = configuration == "lookahead"
    if control:
        result = control_worker(control)
    else:
        # Restrict the frozen helper in this fresh process. All atom definitions,
        # projections, filters, SQL oracle text and timed intervals are unchanged.
        original.COMPONENTS = {query: ORIGINAL_COMPONENTS[query]}
        result = original.worker(cache, configuration, scale)
        result["original_driver_sha256"] = result.pop("driver_sha256")
    result.update(configuration=configuration, scale_factor=None if control else scale,
                  query_component=query, control=control, driver_sha256=original.sha(__file__))
    result["engine_flags"] = {
        option: getattr(Engine, option, None) for option in (
            "_compiled_joins_enabled", "_incremental_index_enabled", "_incremental_validation_enabled",
            "_join_lookahead_enabled", "_support_certificates_enabled", "_unary_strategy")}
    result["lookahead_parameters"] = PARAMETERS if configuration != "b1254c4" else None
    return result


def archive_source(output, sources, drivers):
    path = output.with_name("external-lookahead-source.tar.gz")
    manifest_path = output.with_name("external-lookahead-source-manifest.json")
    original.require(not path.exists() and not manifest_path.exists(), "refuse to replace source archive")
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name in sorted({**sources, **drivers}):
            contents = (ROOT / name).read_bytes()
            member = tarfile.TarInfo(name)
            member.size, member.mode, member.mtime = len(contents), 0o644, 0
            archive.addfile(member, io.BytesIO(contents))
    path.write_bytes(gzip.compress(payload.getvalue(), mtime=0))
    manifest = {"archive": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
                "archive_sha256": original.sha(path),
                "source_sha256": sources, "driver_sha256": drivers,
                "parameters": PARAMETERS,
                "format": "USTAR sorted files; zero uid/gid/mtime; mode0644; gzip mtime0"}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def run(cache, output, blocks):
    original.require(blocks >= 3, "at least three blocks required")
    protocol_path = output.with_name(output.stem + "-protocol.json")
    original.require(not any(p.exists() for p in (output, output.with_suffix(".md"), protocol_path)),
                     "refuse to replace prior result/protocol")
    baseline_commit, baseline_path = original.checkout(cache, "b1254c4")
    sources = original.source_hashes(ROOT)
    drivers = {str(Path(__file__).relative_to(ROOT)): original.sha(__file__),
               "benchmarks/external_tpch.py": original.sha(original.__file__)}
    archive = archive_source(output, sources, drivers)
    report = {"schema_version": 1, "benchmark": "posthoc-bounded-lookahead-v1",
              "started_utc": datetime.now(timezone.utc).isoformat(),
              "discovery_report": "benchmarks/external-tpch-results.json",
              "discovery_sha256": original.sha(ROOT / "benchmarks/external-tpch-results.json"),
              "baseline_commit": baseline_commit,
              "current_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                             capture_output=True, text=True, check=True).stdout.strip(),
              "source_sha256": sources, "driver_sha256": drivers, "source_archive": archive,
              "manifest": json.loads((cache / "manifest.json").read_text()),
              "platform": platform.platform(), "machine": platform.machine(), "cpu_count": os.cpu_count(),
              "workers": [], "protocol": {
                  "blocks": blocks, "configurations": CONFIGURATIONS, "scale_factors": original.SCALES,
                  "components": [3, 5, 9], "controls": CONTROLS, "parameters": PARAMETERS,
                  "seed_start": 6000, "timeout_seconds": 300, "duckdb_threads": 1,
                  "scope": "positive external headless full-index queries on complete closures; no delta or installed rule",
                  "primary_metric": "join_seconds", "secondary_metric": "component_end_to_end_seconds",
                  "outer_metric": "subprocess_wall_seconds includes startup, hashing, validation, result serialization and teardown",
                  "sampling": "first at most four physical index rows; same PYTHONHASHSEED within each block",
                  "score": "bucket count * (1 + mean sampled smallest next-step bucket count); exact unification; no pruning",
                  "cache": "invocation-local remaining occurrences, binding mask, ordered first/second occurrence IDs and bucket bit-lengths",
                  "budget": "at most 1024 extra lookups and 1024 hint entries per invocation (therefore at most 8192 sampled rows); exhaustion uses greedy order and ignores cached hints",
                  "timing": "one fresh process per single TPC-H or adverse component; complete result consumption and closure cleanup inside join timer",
                  "ordering": "rotate configurations by block+case index; all three positions covered within three blocks",
                  "comparison": "compiled and lookahead share adopted optimizations and recursive-closure cleanup; only lookahead switch differs",
                  "input_cache": "whole database integrity hash precedes timing; filesystem cache warm; OS cache not flushed",
                  "novelty": "post-hoc bounded heuristic adaptation, not RPT+/SYA implementation or guarantee"}}
    protocol_path.write_text(json.dumps(report, indent=2) + "\n")
    cases = [(f"sf{scale}-q{number}", scale, number, None)
             for scale in original.SCALES for number in ORIGINAL_COMPONENTS]
    cases += [("control-" + name, None, None, name) for name in CONTROLS]
    for block in range(blocks):
        for case_index, (case, scale, number, control) in enumerate(cases):
            offset = (block + case_index) % len(CONFIGURATIONS)
            order = CONFIGURATIONS[offset:] + CONFIGURATIONS[:offset]
            for position, configuration in enumerate(order):
                original.require(original.source_hashes(ROOT) == sources, "current source changed")
                original.require(all(original.sha(ROOT / name) == checksum for name, checksum in drivers.items()),
                                 "benchmark driver changed")
                source = baseline_path if configuration == "b1254c4" else ROOT
                env = {**os.environ, "PYTHONHASHSEED": str(6000 + block),
                       "PYTHONPATH": os.pathsep.join((str(source / "src"), str(ROOT)))}
                command = [sys.executable, "-m", "benchmarks.external_lookahead", "--worker", configuration,
                           "--cache", str(cache)]
                command += ["--control", control] if control else ["--scale", str(scale), "--query", str(number)]
                started = time.perf_counter()
                completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                                           text=True, check=True, timeout=300)
                wall = time.perf_counter() - started
                row = json.loads(completed.stdout)
                original.require(row["source_sha256"] == original.source_hashes(source), "wrong imported package")
                original.require(row["driver_sha256"] == original.sha(__file__), "wrong worker driver")
                if not control:
                    original.require(row["original_driver_sha256"] == drivers["benchmarks/external_tpch.py"],
                                     "wrong original helper")
                row.update(case=case, block=block, position=position, command=command, subprocess_wall_seconds=wall)
                observation = row["queries"][0]
                for previous in report["workers"]:
                    if previous["case"] == case:
                        reference = previous["queries"][0]
                        original.require(observation["answer_sha256"] == reference["answer_sha256"], "answer drift")
                        input_key = "source_facts_sha256" if control else "relation_sha256"
                        original.require(observation[input_key] == reference[input_key], "input drift")
                report["workers"].append(row)
                print(f"worker {len(report['workers'])}/{blocks * len(cases) * len(CONFIGURATIONS)} "
                      f"block {block + 1} {case} {configuration}: "
                      f"join {observation['join_seconds']:.6f}s exact; wall {wall:.3f}s", flush=True)
    metrics = ("filter_projection_seconds", "encoding_seconds", "index_materialization_seconds",
               "join_seconds", "component_end_to_end_seconds")
    report["summary"], report["paired_ratios"] = {}, {}
    for case, _, _, _ in cases:
        report["summary"][case], report["paired_ratios"][case] = {}, {}
        for configuration in CONFIGURATIONS:
            workers = [w for w in report["workers"] if w["case"] == case and w["configuration"] == configuration]
            original.require(len(workers) == blocks, "missing observations")
            rows = [w["queries"][0] for w in workers]
            values = {metric: {"median": statistics.median(q[metric] for q in rows),
                               "minimum": min(q[metric] for q in rows),
                               "maximum": max(q[metric] for q in rows)} for metric in metrics}
            values.update(answers=rows[0]["answers"], source_facts=rows[0]["source_facts"],
                          candidate_rows=[q["stats"]["candidate_rows"] for q in rows],
                          lookahead_stats=[{k: v for k, v in q["stats"].items() if k.startswith("lookahead_")} for q in rows],
                          subprocess_wall_seconds={"median": statistics.median(w["subprocess_wall_seconds"] for w in workers),
                                                   "minimum": min(w["subprocess_wall_seconds"] for w in workers),
                                                   "maximum": max(w["subprocess_wall_seconds"] for w in workers)})
            report["summary"][case][configuration] = values
        for reference in ("b1254c4", "compiled"):
            report["paired_ratios"][case][reference] = {}
            for metric in ("join_seconds", "component_end_to_end_seconds", "subprocess_wall_seconds"):
                ratios = []
                for block in range(blocks):
                    pair = {w["configuration"]: w for w in report["workers"]
                            if w["case"] == case and w["block"] == block}
                    def value(w):
                        return w[metric] if metric == "subprocess_wall_seconds" else w["queries"][0][metric]
                    ratios.append(value(pair["lookahead"]) / value(pair[reference]))
                report["paired_ratios"][case][reference][metric] = {
                    "ratios_by_block": ratios, "median": statistics.median(ratios),
                    "minimum": min(ratios), "maximum": max(ratios)}
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    report["protocol_sha256"] = original.sha(protocol_path)
    output.write_text(json.dumps(report, indent=2) + "\n")
    output.with_suffix(".md").write_text(markdown(report))


def markdown(report):
    lines = ["# Post-hoc bounded lookahead evaluation", "",
             "This separately registered follow-up was motivated by the previous Q5 intermediate-count finding. "
             "It retains all six TPC-H-derived components and adds four adverse synthetic controls. "
             "Each observation uses a fresh process for a single component. Original artifacts are unchanged.", "",
             "| Case | Configuration | Answers | Join median(ms) | Component total median(ms) | Process wall median(ms) | Candidate rows by block |",
             "|---|---|---:|---:|---:|---:|---|"]
    for case, configurations in report["summary"].items():
        for name, values in configurations.items():
            lines.append(f"| {case} | {name} | {values['answers']} | "
                         + " | ".join(f"{values[metric]['median'] * 1000:.3f}" for metric in (
                             "join_seconds", "component_end_to_end_seconds", "subprocess_wall_seconds"))
                         + f" | {values['candidate_rows']} |")
    lines += ["", "All results are validated against complete independent SQL/control answers and the complete base closure. "
              "TPC-H SQL bag row identities, filter pushdown and scope are unchanged from `external-tpch-methodology.md`. "
              "Aggregation, ordering, top-k and full TPC-H scores remain outside the experiment.", "",
              "The compiled and lookahead arms share adopted optimizations and recursive-closure cleanup. "
              "The only difference between them is invocation-local ordering lookahead, disabled by default. "
              "It samples up to 4 rows from each of two similarly sized buckets (minimum 32 rows, factor 4), "
              "uses at most 1024 extra lookups, and never prunes rows. Planning, complete answer consumption and cleanup "
              "are included in join time. A fixed work budget provides no bound on a bad ordering choice.", "",
              "The JSON contains every observation, fixed protocol, source archive, original input hashes, "
              "planning counters, paired ratios and observed ranges. Process wall time includes validation, "
              "hashing, startup, serialization and teardown; component total excludes those costs. "
              "Three matched blocks are descriptive. This is an adaptation experiment, not an RPT+/SYA implementation "
              "or a claim of state-of-the-art performance.", "",
              "```sh", "tmp/tpch-python/bin/python -m benchmarks.external_lookahead --blocks 3 --output /tmp/lookahead-reproduction.json",
              "```", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / "tmp/tpch-components")
    parser.add_argument("--worker", choices=CONFIGURATIONS)
    parser.add_argument("--scale", type=float, choices=original.SCALES, default=.01)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--query", type=int, choices=ORIGINAL_COMPONENTS)
    selection.add_argument("--control", choices=CONTROLS)
    parser.add_argument("--blocks", type=int, default=3)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/external-lookahead-results.json")
    args = parser.parse_args()
    if args.worker:
        original.require(args.query is not None or args.control is not None, "select exactly one component")
        print(json.dumps(worker(args.cache.resolve(), args.worker, args.scale, args.query, args.control)))
    else:
        run(args.cache.resolve(), args.output.resolve(), args.blocks)


if __name__ == "__main__":
    main()
