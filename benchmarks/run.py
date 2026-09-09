"""Run with: python -m benchmarks.run --suite thesis --repeats 5.

Every case is isolated in a child process. Timings exclude generation, include
separate parse/compile/materialize phases, and preserve every repetition.
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import random
import resource
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from rdflib import Graph, OWL, RDF

from dlp_reasoner import Reasoner
from dlp_reasoner.engine import Engine
from dlp_reasoner.model import Atom, Program, Rule, Skolem, Var
from . import bach
from .workloads import (
    EX, cardinality_taxonomy, equality, existential, factored_enumerations, factored_unions,
    maintenance, taxonomy, transitive,
)

MEASUREMENT_PROTOCOL = "phase-timings-v1"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BASELINE_COMMIT = "b1254c441731ca4fdf32ea83570ff99aaa84ac2a"
BASELINE_RESULTS_SHA256 = "6f0bc493cae0fb96b474405eb9496dc9ce2c3155b313f2bcd3de49b3dc8b51e2"
DEFAULT_BASELINE = REPOSITORY_ROOT / "benchmarks/baselines/b1254c4/results.json"
IMMUTABLE_BASELINES = REPOSITORY_ROOT / "benchmarks/baselines"
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 2004
WORK_COUNTERS = (
    "rounds", "rule_evaluations", "candidate_rows", "body_matches", "derived_facts",
    "equality_merges", "overdeleted_facts", "rederived_facts",
    "unary_plan_evaluations", "unary_intersections", "coalesced_delta_variants",
)


def source_hashes():
    paths = sorted([*(REPOSITORY_ROOT / "src/dlp_reasoner").glob("*.py"),
                    *(REPOSITORY_ROOT / "benchmarks").glob("*.py")])
    return {str(path.relative_to(REPOSITORY_ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths}


def git_provenance():
    """Record checkout identity separately from the bytes actually measured."""
    def git(*arguments):
        return subprocess.check_output(["git", *arguments], cwd=REPOSITORY_ROOT,
                                       stderr=subprocess.DEVNULL, text=True).strip()
    try:
        head = git("rev-parse", "HEAD")
        status = git("status", "--porcelain=v1", "--untracked-files=all")
        return {"head": head, "dirty": bool(status), "status_porcelain": status.splitlines()}
    except (OSError, subprocess.CalledProcessError):
        return {"head": None, "dirty": None, "status_porcelain": [], "available": False}


def load_baseline(path=DEFAULT_BASELINE):
    """Validate the pinned reference before accepting its historical measurements."""
    path = Path(path).resolve()
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    report = json.loads(raw)
    manifest_path = path.with_name("manifest.json")
    pinned = path == DEFAULT_BASELINE.resolve()
    provenance = {"path": str(path), "results_sha256": digest, "verified": False}
    if pinned or path.is_relative_to(IMMUTABLE_BASELINES.resolve()):
        if not manifest_path.is_file():
            raise ValueError(f"Immutable baseline requires {manifest_path}")
        manifest = json.loads(manifest_path.read_text())
        commit = manifest["baseline_commit"]
        if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
            raise ValueError("Baseline manifest requires a full lowercase Git commit SHA")
        if manifest["results_sha256"] != digest:
            raise ValueError("Baseline results do not match their manifest SHA-256")
        if pinned and (commit != BASELINE_COMMIT or digest != BASELINE_RESULTS_SHA256):
            raise ValueError("Default baseline differs from pinned commit b1254c4")
        recorded = report["environment"]["source_sha256"]
        if manifest["source_sha256"] != recorded:
            raise ValueError("Baseline manifest and report record different source hashes")
        if (manifest["case_count"] != len(report["results"])
                or manifest["measurement_protocol"] != report["measurement_protocol"]
                or any(result["case"]["repeats"] != manifest["repeats"]
                       or result.get("validation") != "passed" for result in report["results"])):
            raise ValueError("Baseline report does not match validated manifest controls")
        # This comparison ties the saved report and its measured sources to the
        # named commit, rather than treating the mutable checkout as provenance.
        git_verified = False
        try:
            subprocess.check_output(["git", "cat-file", "-e", f"{commit}^{{commit}}"],
                                    cwd=REPOSITORY_ROOT, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.CalledProcessError):
            if not pinned:
                raise ValueError("Cannot verify custom immutable baseline commit") from None
        else:
            for source, expected in {**recorded, "benchmarks/results.json": digest}.items():
                content = subprocess.check_output(["git", "show", f"{commit}:{source}"],
                                                  cwd=REPOSITORY_ROOT, stderr=subprocess.DEVNULL)
                if hashlib.sha256(content).hexdigest() != expected:
                    raise ValueError(f"Baseline source/hash mismatch for {source} at {commit}")
            git_verified = True
        provenance.update(verified=True, baseline_commit=commit, manifest=str(manifest_path),
                          git_objects_verified=git_verified,
                          verification="pinned-digest-and-manifest" if pinned else "git-and-manifest")
    return report, provenance


def protect_output(output, baseline_path):
    """Never let a report overwrite an immutable reference, even through aliases."""
    baseline_path = Path(baseline_path).resolve() if baseline_path is not None else None
    for target in (Path(output), Path(output).with_suffix(".md")):
        resolved = target.resolve()
        if resolved.is_relative_to(IMMUTABLE_BASELINES.resolve()):
            raise ValueError("Benchmark outputs cannot be written inside immutable baselines")
        if baseline_path is not None and (resolved == baseline_path or (
                target.exists() and baseline_path.exists() and target.samefile(baseline_path))):
            raise ValueError("Benchmark output must not overwrite its baseline")


def summary(values):
    ordered = sorted(values)
    return {"samples": values, "median": statistics.median(values),
            "mean": statistics.mean(values), "min": min(values), "max": max(values),
            "stdev": statistics.stdev(values) if len(values) > 1 else 0,
            "p25": ordered[(len(ordered) - 1) // 4],
            "p75": ordered[3 * (len(ordered) - 1) // 4]}


def timed(fn):
    started = time.perf_counter()
    value = fn()
    return value, time.perf_counter() - started


@functools.lru_cache(maxsize=8192)
def bootstrap_ratio(before, after):
    """Descriptive resampling of recorded medians, not an independent-run CI.

    The historical five samples share a worker process. Resampling cannot
    recover process/run variability or correct drift between historical runs.
    """
    if len(before) < 2 or len(after) < 2 or any(
            not math.isfinite(value) or value <= 0 for value in (*before, *after)):
        return None
    rng = random.Random(BOOTSTRAP_SEED)
    ratios = sorted(
        statistics.median(rng.choices(after, k=len(after)))
        / statistics.median(rng.choices(before, k=len(before)))
        for _ in range(BOOTSTRAP_RESAMPLES)
    )
    return (ratios[round(0.025 * (len(ratios) - 1))],
            ratios[round(0.975 * (len(ratios) - 1))])


def compare_timing(before, after):
    previous, current = before["median"], after["median"]
    old_samples, new_samples = tuple(before.get("samples", [])), tuple(after.get("samples", []))
    interval = bootstrap_ratio(old_samples, new_samples)
    result = {"before": previous, "after": current,
              "after_over_before": current / previous if previous else None,
              "samples_before": len(old_samples), "samples_after": len(new_samples),
              "bootstrap_95_percent_interval": list(interval) if interval else None}
    if old_samples and new_samples:
        result["observed_range_before"] = [min(old_samples), max(old_samples)]
        result["observed_range_after"] = [min(new_samples), max(new_samples)]
    return result


def compare_counters(before, after):
    counters = {}
    if not before or not after:
        return counters
    for field in WORK_COUNTERS:
        previous = [row[field] for row in before] if all(field in row for row in before) else None
        current = [row[field] for row in after] if all(field in row for row in after) else None
        if previous is None and current is None:
            continue
        old_median = statistics.median(previous) if previous else None
        new_median = statistics.median(current) if current else None
        counters[field] = {"before": old_median, "after": new_median,
                           "after_over_before": new_median / old_median
                           if old_median and new_median is not None else None,
                           "samples_before": previous, "samples_after": current,
                           "baseline_available": previous is not None,
                           "current_available": current is not None}
    return counters


def operation_controls(operation):
    fields = ("added_facts", "removed_facts", "added_rules", "removed_rules")
    return {("rdf", sample["added_triples"], sample["removed_triples"])
            if "added_triples" in sample else tuple(sample.get(field) for field in fields)
            for sample in operation.get("samples", [])}


def build_cases(suite):
    if suite == "bach":
        return bach.build_bach_cases()
    cases = [
        {"kind": "taxonomy", "depth": depth, "ipc": ipc, "variant": variant}
        for depth in [3, 5, 7]
        for ipc in ([3, 9, 15] if suite == "thesis" else [3])
        for variant in (["P0", "P1", "PF"] if suite == "thesis" else ["P0"])
    ]
    cases += [{"kind": "taxonomy", "depth": 3, "ipc": 3, "variant": "P0", "strategy": s}
              for s in ["naive", "owlrl"]]
    cases += [{"kind": "equality", "size": s} for s in [100, 1000]]
    cases += [{"kind": "existential", "size": 100}, {"kind": "transitive", "size": 100}]
    cases += [{"kind": "cardinality", "depth": depth, "ipc": ipc}
              for depth, ipc in ([(3, 3), (5, 3), (7, 3), (5, 9)] if suite == "thesis"
                                 else [(3, 3)])]
    cases += [{"kind": "factored-unions", "pairs": pairs, "size": 128}
              for pairs in ([4, 8, 16, 32, 64] if suite == "thesis" else [4, 32])]
    cases += [{"kind": "factored-enumerations", "pairs": pairs, "size": 128}
              for pairs in ([16, 32, 64] if suite == "thesis" else [32])]
    cases += [{"kind": "maintenance", "depth": depth, "change_percent": ratio}
              for depth in ([3, 4, 5] if suite == "thesis" else [3])
              for ratio in ([10, 15] if suite == "thesis" else [10])]
    return cases + bach.build_bach_cases()


def case_name(case):
    kind = case["kind"]
    if kind == "bach":
        return bach.case_name(case)
    if kind == "taxonomy":
        return f"taxonomy d{case['depth']}/i{case['ipc']}/{case['variant']}"
    if kind == "cardinality":
        return f"cardinality d{case['depth']}/i{case['ipc']}"
    if kind == "maintenance":
        return f"maintenance d{case.get('depth', 4)}/{case.get('change_percent', 10)}%"
    if kind in {"factored-unions", "factored-enumerations"}:
        return f"{kind.replace('-', ' ')} {case['pairs']} pairs/{case['size']} subjects"
    return f"{kind} {case.get('size', '')}".strip()


def program_shape(program):
    def variables(term):
        if isinstance(term, Var):
            return {term}
        if isinstance(term, Skolem):
            return set().union(*(variables(arg) for arg in term.args))
        return set()
    maximum = 0
    for rule in program.rules:
        atoms = (*rule.body, *((rule.head,) if rule.head is not None else ()))
        maximum = max(maximum, len(set().union(*(variables(t) for a in atoms for t in a.args))))
    return {"compiled_rules": len(program.rules), "maximum_rule_variables": maximum}


def benchmark_maintenance(reasoner, meta):
    """Compare every update with a fresh closure of independently tracked inputs."""
    engine = reasoner.engine
    expected_facts, expected_rules = set(engine.asserted), list(engine.rules)
    rng = random.Random(meta["seed"])
    removed = set(rng.sample(sorted(expected_facts, key=repr), meta["changed_assertions"]))
    added = {Atom(EX[f"C{meta['classes'] - 1}"], (EX[f"new_{i}"],))
             for i in range(len(removed))}
    x = Var("x")
    new_root = Rule(Atom(EX.MaintExtra, (x,)), (Atom(EX.C0, (x,)),), "benchmark addition")
    c1_rule = next(rule for rule in expected_rules if rule.head is not None
                   and rule.head.predicate == EX.MaintShared
                   and len(rule.body) == 1 and rule.body[0].predicate == EX.C1)
    c2_rule = next(rule for rule in expected_rules if rule.head is not None
                   and rule.head.predicate == EX.MaintShared
                   and len(rule.body) == 1 and rule.body[0].predicate == EX.C2)
    c3_rule = Rule(Atom(EX.MaintShared, (x,)), (Atom(EX.C3, (x,)),), "replacement support")
    replacement_root = Rule(Atom(EX.MaintExtra, (x,)), (Atom(EX.C1, (x,)),), "replacement root")
    mixed_removed = set(sorted(added, key=repr)[:max(1, len(added) // 2)])
    mixed_added = {Atom(EX.C2, (EX[f"mixed_{i}"],)) for i in range(len(mixed_removed))}
    operations = [
        ("fact_delete", set(), removed, [], []),
        ("fact_insert", added, set(), [], []),
        ("rule_insert", set(), set(), [new_root], []),
        ("rule_delete", set(), set(), [], [c1_rule]),
        ("rule_replace", set(), set(), [c3_rule], [c2_rule]),
        ("atomic_mixed", mixed_added, mixed_removed, [replacement_root], [new_root]),
    ]
    results = {}
    for name, add_facts, remove_facts, add_rules, remove_rules in operations:
        if name.startswith("rule_"):
            _, elapsed = timed(lambda: engine.update_rules(add=add_rules, remove=remove_rules))
        elif name == "atomic_mixed":
            _, elapsed = timed(lambda: engine.update(add=add_facts, remove=remove_facts,
                                                    add_rules=add_rules, remove_rules=remove_rules))
        else:
            _, elapsed = timed(lambda: engine.update(add=add_facts, remove=remove_facts))
        stats = dict(engine.stats)
        expected_facts = (expected_facts - remove_facts) | add_facts
        expected_rules = list(dict.fromkeys(
            [rule for rule in expected_rules if rule not in remove_rules] + add_rules))
        fresh_program = Program(rules=list(expected_rules), facts=set(expected_facts), profile="L2")
        fresh, rebuild_elapsed = timed(lambda: Engine(fresh_program).materialize())
        assert engine.complete and fresh.complete, (name, stats)
        assert not engine.violations and not fresh.violations, (name, stats)
        assert engine.facts == fresh.facts, f"{name} disagrees with fresh closure"
        expected_method = ("dred-rules" if remove_rules else "incremental-rules" if add_rules
                           else "dred" if remove_facts else "incremental-insert")
        assert stats["update_method"] == expected_method, (name, stats)
        if name in {"rule_delete", "rule_replace"}:
            source = EX.C2 if name == "rule_delete" else EX.C3
            source_members = {f.args for f in engine.facts if f.predicate == source}
            shared_members = {f.args for f in engine.facts if f.predicate == EX.MaintShared}
            assert shared_members == source_members, "Unsupported recursive support survived"
        results[name] = {
            "seconds": elapsed, "rebuild_seconds": rebuild_elapsed, "stats": stats,
            "added_facts": len(add_facts), "removed_facts": len(remove_facts),
            "added_rules": len(add_rules), "removed_rules": len(remove_rules),
            "closure_facts": len(engine.facts), "validation": "matches-fresh-closure",
        }
    return results


def worker(case):
    if sys.flags.optimize:
        raise RuntimeError("Benchmark validation requires Python assertions; omit -O")
    kind = case["kind"]
    if kind == "bach":
        return bach.worker(case)
    if kind == "taxonomy":
        graph, meta = taxonomy(case["depth"], case["ipc"], case["variant"])
    elif kind == "equality":
        graph, meta = equality(case["size"]), {"pairs": case["size"]}
    elif kind == "existential":
        graph, meta = existential(case["size"]), {"roots": case["size"], "witness_depth": 4}
    elif kind == "transitive":
        graph, meta = transitive(case["size"]), {"chain_edges": case["size"]}
    elif kind == "cardinality":
        graph, meta = cardinality_taxonomy(case["depth"], case["ipc"])
        for predicate, field in [(OWL.allValuesFrom, "universal_restrictions"),
                                 (OWL.maxCardinality, "maximum_one_restrictions"),
                                 (OWL.minCardinality, "minimum_zero_restrictions")]:
            assert sum(1 for _ in graph.triples((None, predicate, None))) == meta[field]
    elif kind == "factored-unions":
        graph, meta = factored_unions(case["pairs"], case["size"])
    elif kind == "factored-enumerations":
        graph, meta = factored_enumerations(case["pairs"], case["size"])
    elif kind == "maintenance":
        graph, meta = maintenance(case["depth"], case["change_percent"])
    else:
        raise ValueError(f"Unknown workload {kind}")
    serialized = graph.serialize(format="nt")
    parse_times, compile_times, materialize_times, query_times = [], [], [], []
    counts, answer_counts, shapes, engine_stats, updates = [], [], [], [], []
    property_query_times, subsumption_times = [], []
    profile = "L3" if kind == "existential" else "L2"
    for _ in range(case["repeats"]):
        parsed, elapsed = timed(lambda: Graph().parse(data=serialized, format="nt"))
        parse_times.append(elapsed)
        if case.get("strategy") == "owlrl":
            from owlrl import DeductiveClosure, OWLRL_Semantics
            closure = DeductiveClosure(OWLRL_Semantics)
            _, elapsed = timed(lambda: closure.expand(parsed))
            compile_times.append(0)
            materialize_times.append(elapsed)
            answers, elapsed = timed(lambda: set(parsed.subjects(RDF.type, EX.C0)))
            query_times.append(elapsed)
            assert len(answers) == meta["individuals"]
            answer_counts.append(len(answers))
            counts.append(len(parsed))
            continue
        r = Reasoner(parsed, profile=profile, strategy=case.get("strategy", "semi-naive"))
        compile_times.append(r.compile_seconds)
        materialize_times.append(r.materialize_seconds)
        assert r.consistency == "consistent", r.stats
        shapes.append(program_shape(r.program))
        engine_stats.append(dict(r.engine.stats))
        if kind in {"taxonomy", "maintenance", "cardinality"}:
            answers, elapsed = timed(lambda: r.instances(EX.C0))
            assert len(answers) == meta.get("expected_root_answers", meta["individuals"])
            actual = sum(1 for f in r.engine.facts if len(f.args) == 1 and
                         str(f.predicate).startswith(str(EX) + "C"))
            assert actual == meta["expected_class_facts"], (actual, meta)
            if kind == "cardinality":
                assert r.engine.stats["equality_merges"] == meta["expected_equality_merges"]
        elif kind == "equality":
            answers, elapsed = timed(lambda: r.instances(EX.B))
            assert len(answers) == case["size"] * 2
        elif kind == "existential":
            answers, elapsed = timed(lambda: r.instances(EX.C4, include_witnesses=True))
            assert len(answers) == case["size"]
        elif kind in {"factored-unions", "factored-enumerations"}:
            target = EX.Selected if kind == "factored-unions" else EX.SelectedNominal
            answers, elapsed = timed(lambda: r.instances(target))
            if kind == "factored-unions":
                expected = {EX[f"union_subject_{j}"] for j in range(case["size"]) if j % 4 != 0}
            else:
                expected = ({EX.nominal_common}
                            | {EX[f"nominal_A{i}"] for i in range(case["pairs"])}
                            | {EX[f"nominal_alias_{j}"] for j in range(case["size"]) if j % 2 == 0})
                assert r.engine.stats["equality_merges"] == meta["expected_equality_merges"]
            assert answers == expected
            # Count the actual normalized program, not the exponential DNF it avoids.
            assert shapes[-1]["compiled_rules"] <= 6 * case["pairs"] + 5, shapes[-1]
            assert shapes[-1]["maximum_rule_variables"] <= 3, shapes[-1]
        else:
            answers, elapsed = timed(lambda: r.property_pairs(EX.p))
            assert len(answers) == case["size"] * (case["size"] + 1) // 2
        query_times.append(elapsed)
        answer_counts.append(len(answers))
        counts.append(len(r.engine.facts))
        if kind == "taxonomy":
            property_answers, property_time = timed(lambda: r.property_pairs(EX.p1))
            assert property_answers == set(parsed.subject_objects(EX.p1))
            property_query_times.append(property_time)
            answer, subsumption_time = timed(lambda: r.subsumes(EX.C0, EX[f"C{meta['classes'] - 1}"]))
            assert answer
            subsumption_times.append(subsumption_time)
        if kind == "maintenance":
            updates.append(benchmark_maintenance(r, meta))
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform != "darwin":
        rss *= 1024
    result = {"case": case, "workload": meta, "input_triples": len(graph),
              "input_sha256": hashlib.sha256("\n".join(sorted(serialized.splitlines())).encode()).hexdigest(),
              "parse_seconds": summary(parse_times), "compile_seconds": summary(compile_times),
              "materialize_seconds": summary(materialize_times), "query_seconds": summary(query_times),
              "query_answer_counts": answer_counts,
              "materialized_fact_counts": counts, "process_peak_rss_bytes": rss,
              "validation": "passed"}
    if shapes:
        result.update(program_shapes=shapes, engine_stats=engine_stats)
    if updates:
        result["maintenance_operations"] = {
            name: {"seconds": summary([run[name]["seconds"] for run in updates]),
                   "rebuild_seconds": summary([run[name]["rebuild_seconds"] for run in updates]),
                   "samples": [run[name] for run in updates]}
            for name in updates[0]
        }
    if property_query_times:
        result.update(property_query_seconds=summary(property_query_times),
                      subsumption_seconds=summary(subsumption_times))
    return result


def expected_answer_count(case, workload):
    kind = case["kind"]
    if kind in {"taxonomy", "maintenance"}:
        return workload.get("individuals")
    if kind == "cardinality":
        return workload.get("expected_root_answers")
    if kind in {"factored-unions", "factored-enumerations"}:
        return workload.get("expected_answers")
    if kind == "equality":
        return 2 * case["size"]
    if kind == "existential":
        return case["size"]
    if kind == "transitive":
        return case["size"] * (case["size"] + 1) // 2
    return None


def correctness_comparison(before, after):
    if after["case"]["kind"] == "bach":
        return bach.correctness_comparison(before, after)
    def same_counts(left, right):
        return bool(left and right) and set(left) == set(right)
    expected_before = expected_answer_count(before["case"], before.get("workload", {}))
    expected_after = expected_answer_count(after["case"], after.get("workload", {}))
    initial_counts_match = same_counts(before.get("materialized_fact_counts"),
                                      after.get("materialized_fact_counts"))
    expected_match = expected_before is not None and expected_before == expected_after
    # Older reports preserve assertions plus expectations, but not answer counts.
    recorded_answers_match = all(
        "query_answer_counts" not in row or set(row["query_answer_counts"]) == {expected}
        for row, expected in ((before, expected_before), (after, expected_after))
    )
    maintenance_counts, maintenance_controls = {}, {}
    for name in set(before.get("maintenance_operations", {})) | set(after.get("maintenance_operations", {})):
        old = before.get("maintenance_operations", {}).get(name, {})
        new = after.get("maintenance_operations", {}).get(name, {})
        maintenance_counts[name] = same_counts(
            [sample["closure_facts"] for sample in old.get("samples", [])],
            [sample["closure_facts"] for sample in new.get("samples", [])])
        maintenance_controls[name] = bool(operation_controls(old)) and (
            operation_controls(old) == operation_controls(new))
    both_validated = before.get("validation") == after.get("validation") == "passed"
    return {
        "verified": both_validated and initial_counts_match and expected_match
                    and recorded_answers_match and all(maintenance_counts.values())
                    and all(maintenance_controls.values()),
        "maintenance_controls_match": maintenance_controls,
        "both_runs_validated": both_validated,
        "initial_fact_counts_match": initial_counts_match,
        "expected_query_answer_count_before": expected_before,
        "expected_query_answer_count_after": expected_after,
        "expected_query_answers_match": expected_match and recorded_answers_match,
        "maintenance_closure_counts_match": maintenance_counts,
        "query_evidence": "Workload-specific expected-answer checks passed in both runs; "
                          "the historical report does not contain full answer-set digests.",
    }


def compare_baseline(report, baseline, baseline_path, provenance=None):
    def key(case):
        return json.dumps({**{k: v for k, v in case.items() if k != "repeats"},
                           "strategy": case.get("strategy", "semi-naive")}, sort_keys=True)
    prior = {key(r["case"]): r for r in baseline["results"] if "error" not in r}
    comparisons, skipped = [], []
    for result in report["results"]:
        if "error" in result or result.get("validation") != "passed":
            skipped.append({"case": result["case"], "reason": "current case did not validate"})
            continue
        old = prior.get(key(result["case"]))
        reason = None
        if old is None:
            reason = "no matching case controls"
        elif old.get("validation") != "passed":
            reason = "baseline case did not validate"
        elif old["input_sha256"] != result["input_sha256"]:
            reason = "input hash changed"
        elif result["case"]["kind"] == "bach" and (
                old.get("input_file_sha256") != result.get("input_file_sha256")
                or old.get("measurement_protocol") != result.get("measurement_protocol")
                or old["workload"].get("query_manifest_sha256") !=
                result["workload"].get("query_manifest_sha256")):
            reason = "Bach source bytes, query manifest or measurement boundaries changed"
        elif (baseline.get("measurement_protocol", MEASUREMENT_PROTOCOL) != MEASUREMENT_PROTOCOL
              or report.get("measurement_protocol") != MEASUREMENT_PROTOCOL):
            reason = "measurement boundaries differ"
        elif result["case"]["kind"] in {"maintenance", "bach"} and old["workload"].get(
                "operation_protocol") != result["workload"].get("operation_protocol"):
            reason = "maintenance operation protocol changed"
        if reason:
            skipped.append({"case": result["case"], "reason": reason})
            continue
        phases = {}
        for phase in ("parse_seconds", "compile_seconds", "materialize_seconds", "query_seconds",
                      "property_query_seconds", "subsumption_seconds"):
            if phase not in old or phase not in result:
                continue
            phases[phase] = compare_timing(old[phase], result[phase])
        maintenance_comparisons, maintenance_skipped = {}, {}
        for operation, current in result.get("maintenance_operations", {}).items():
            previous = old.get("maintenance_operations", {}).get(operation)
            if previous is None:
                maintenance_skipped[operation] = "no matching baseline operation"
                continue
            if not operation_controls(current) or operation_controls(previous) != operation_controls(current):
                maintenance_skipped[operation] = "operation fact/rule counts changed"
                continue
            expected_validation = ("matches-reachability-and-fresh-closure"
                                   if result["case"]["kind"] == "bach" else "matches-fresh-closure")
            if not all(sample.get("validation") == expected_validation
                       for sample in (*previous["samples"], *current["samples"])):
                maintenance_skipped[operation] = "operation did not validate"
                continue
            before_stats = [sample["stats"] for sample in previous["samples"]]
            after_stats = [sample["stats"] for sample in current["samples"]]
            maintenance_comparisons[operation] = {
                "update_seconds": compare_timing(previous["seconds"], current["seconds"]),
                "rebuild_seconds": compare_timing(previous["rebuild_seconds"], current["rebuild_seconds"]),
                "work_counters": compare_counters(before_stats, after_stats),
                "methods_before": sorted({row["update_method"] for row in before_stats}),
                "methods_after": sorted({row["update_method"] for row in after_stats}),
                "controls": list(next(iter(operation_controls(current)))),
            }
        comparisons.append({"case": result["case"], "input_sha256": result["input_sha256"],
                            "phases": phases,
                            "correctness": correctness_comparison(old, result),
                            "materialization_counters": compare_counters(
                                old.get("engine_stats", []), result.get("engine_stats", [])),
                            "maintenance_operations": maintenance_comparisons,
                            "maintenance_skipped": maintenance_skipped})
    return {"baseline_path": str(baseline_path), "baseline_timestamp": baseline["timestamp"],
            "baseline_provenance": provenance or {"verified": False},
            "baseline_source_sha256": baseline["environment"]["source_sha256"],
            "current_source_sha256": report["environment"]["source_sha256"],
            "baseline_environment": baseline["environment"],
            "matched": comparisons, "skipped": skipped,
            "uncertainty": {"method": "independent percentile resampling of each recorded sample list",
                            "statistic": "ratio of medians (after/before)",
                            "resamples": BOOTSTRAP_RESAMPLES, "seed": BOOTSTRAP_SEED,
                            "coverage_label": "95% descriptive bootstrap interval",
                            "caveat": "Small within-worker samples; not a guarantee of repeated-run coverage. "
                                      "Does not model run-to-run drift or machine-load differences."},
            "caveat": "Matched inputs and timing boundaries; runs are not interleaved or noise controlled."}


def markdown(report):
    if report.get("suite") == "bach":
        return bach.markdown_report(report)
    raw_name = Path(report.get("output_file", "results.json")).name
    passed = sum(r.get("validation") == "passed" for r in report["results"])
    errors = sum("error" in r for r in report["results"])
    checkout = report["environment"].get("git", {})
    lines = ["# Measured benchmark results", "",
             f"Run: {report['timestamp']}. Python {report['environment']['python']}; "
             f"{report['environment']['platform']}.", "",
             f"Measured checkout: `{checkout.get('head', 'not recorded')}`; "
             f"dirty: {checkout.get('dirty', 'not recorded')}. "
             "Exact measured source hashes and checkout status are in the raw report.", "",
             f"Recorded: {passed} validated cases, {errors} errors, "
             f"{report.get('planned_cases', len(report['results']))} planned cases. "
             f"Repetitions per case: {report.get('repeats', 'see raw case controls')}.", "",
             f"All times below are medians in milliseconds. Every raw sample is in `{raw_name}`.",
             "Peak RSS is the entire isolated worker (including parser, retained input and repetitions), "
             "not incremental reasoner allocation. Compiler and materializer timings are separate.", "",
             "| Workload | Engine | Input triples | Closure facts | Compile ms | Materialize ms | Query ms | Peak MiB |",
             "|---|---|---:|---:|---:|---:|---:|---:|"]
    for r in report["results"]:
        c = r["case"]
        name = case_name(c)
        if "error" in r:
            error = str(r["error"]).replace("\n", " ").replace("|", "/")
            lines.append(f"| {name} | {c.get('strategy', 'semi-naive')} | error: {error} | | | | | |")
            continue
        values = [r[k]["median"] * 1000 for k in
                  ("compile_seconds", "materialize_seconds", "query_seconds")]
        lines.append(f"| {name} | {c.get('strategy', 'semi-naive')} | {r['input_triples']} | "
                     f"{r['materialized_fact_counts'][0]} | " + " | ".join(f"{v:.3f}" for v in values)
                     + f" | {r['process_peak_rss_bytes'] / 2**20:.1f} |")
    lines += ["", "## Additional query timings", "",
              "| Workload | Property pairs ms | Subsumption ms |",
              "|---|---:|---:|"]
    for r in report["results"]:
        if "error" in r or "property_query_seconds" not in r:
            continue
        name = case_name(r["case"])
        cells = [f"{r[k]['median'] * 1000:.3f}" if k in r else "—" for k in
                 ["property_query_seconds", "subsumption_seconds"]]
        lines.append("| " + name + " | " + " | ".join(cells) + " |")
    lines += ["", "## Incremental maintenance", "",
              "Every operation is checked against a fresh closure from separately tracked facts and rules. "
              "Synthetic maintenance uses precompiled Engine inputs, excluding recompilation from "
              "both timings. Bach uses RDF updates and includes compilation in both timings.", "",
              "| Workload | Operation | Update ms | Fresh rebuild ms | Observed method |",
              "|---|---|---:|---:|---|"]
    for r in report["results"]:
        for name, measurement in r.get("maintenance_operations", {}).items():
            methods = sorted({s["stats"]["update_method"] for s in measurement["samples"]})
            lines.append(f"| {case_name(r['case'])} | {name} | "
                         f"{measurement['seconds']['median'] * 1000:.3f} | "
                         f"{measurement['rebuild_seconds']['median'] * 1000:.3f} | "
                         f"{', '.join(methods)} |")
    lines += ["", "## Corrected cardinality distribution", "",
              "Counts come from the generated RDF, with maximum-one restrictions twice as numerous "
              "as minimum-zero restrictions. Minimum zero normalizes to top; each maximum-one "
              "subject has two explicitly named fillers whose equality is checked.", "",
              "| Workload | Named classes | Universal | Maximum one | Minimum zero | Equality groups |",
              "|---|---:|---:|---:|---:|---:|"]
    for r in report["results"]:
        if r["case"]["kind"] == "cardinality" and "error" not in r:
            m = r["workload"]
            values = [m[k] for k in ["classes", "universal_restrictions", "maximum_one_restrictions",
                                     "minimum_zero_restrictions", "equality_groups"]]
            lines.append(f"| {case_name(r['case'])} | " + " | ".join(map(str, values)) + " |")
    lines += ["", "## Factored conjunctions of unions and enumerations", "",
              "The DNF branch count is the size of the expansion avoided, not a measured materialization. "
              "Union cases have 128 subjects and 96 expected answers. Enumeration cases have "
              "128 query aliases, with positive and negative membership checked after equality merges. "
              "The enumeration cases directly exercise the corrected oneOf translation.", "",
              "| Constructor | Pairs | Explicit DNF branches | Actual compiled rules | Max variables | Compile ms |",
              "|---|---:|---:|---:|---:|---:|"]
    for r in report["results"]:
        if r["case"]["kind"] in {"factored-unions", "factored-enumerations"} and "error" not in r:
            shape = r["program_shapes"][0]
            constructor = "unionOf" if r["case"]["kind"] == "factored-unions" else "oneOf"
            lines.append(f"| {constructor} | {r['case']['pairs']} | "
                         f"{r['workload']['unfactored_dnf_branches']} | "
                         f"{shape['compiled_rules']} | {shape['maximum_rule_variables']} | "
                         f"{r['compile_seconds']['median'] * 1000:.3f} |")
    if "comparison" in report:
        comparison = report["comparison"]
        provenance = comparison.get("baseline_provenance", {})
        reference = provenance.get("baseline_commit", "custom report, commit not verified")
        verified = sum(row.get("correctness", {}).get("verified", False)
                       for row in comparison["matched"])

        def ratio_text(values):
            ratio = values["after_over_before"]
            text = f"{ratio:.4g}" if ratio is not None else "—"
            interval = values.get("bootstrap_95_percent_interval")
            if interval:
                text += f" [{interval[0]:.4g}, {interval[1]:.4g}]"
            return text

        def counter_change(counters, field):
            value = counters.get(field)
            return f"{value['before']:g} → {value['after']:g}" if value else "—"

        lines += ["", "## Before/after comparison on unchanged inputs", "",
                  f"Baseline: `{comparison['baseline_path']}`, run {comparison['baseline_timestamp']}. "
                  f"Reference commit: `{reference}`. "
                  "Rows require identical case controls, input hashes and timing boundaries. "
                  "Different source hashes are retained in JSON for attribution. Ratios below 1 mean "
                  "a shorter current median. Brackets show deterministic 95% percentile bootstrap "
                  "intervals for the ratio of medians, resampling the recorded observations. "
                  "With five repetitions in one worker per case, these are descriptive sensitivity "
                  "intervals, not guarantees of independent-run coverage or causal speedup. "
                  "They omit between-run machine-load/drift effects.", "",
                  f"Cross-version correctness checks passed for {verified}/{len(comparison['matched'])} "
                  "matched cases: initial fact counts, expected query-answer checks, and maintenance "
                  "closure counts. The historical report does not store full answer-set digests.", "",
                  "| Workload | Engine | Previous materialize ms | Current materialize ms | Ratio [interval] | Candidate rows before → after |",
                  "|---|---|---:|---:|---:|---:|"]
        for matched in comparison["matched"]:
            values = matched["phases"]["materialize_seconds"]
            lines.append(f"| {case_name(matched['case'])} | "
                         f"{matched['case'].get('strategy', 'semi-naive')} | "
                         f"{values['before'] * 1000:.3f} | {values['after'] * 1000:.3f} | "
                         f"{ratio_text(values)} | "
                         f"{counter_change(matched['materialization_counters'], 'candidate_rows')} |")
        lines += ["", "### Parsing, compilation and public query calls", "",
                  "Subsumption still times the complete first public call on each fresh reasoner. "
                  "A lazy schema index or fast path built inside that call remains inside the timing. "
                  "It is not silently excluded as setup. All phase samples remain available in JSON.", "",
                  "| Workload / engine | Phase | Previous ms | Current ms | Ratio [interval] |",
                  "|---|---|---:|---:|---:|"]
        for matched in comparison["matched"]:
            for phase, values in matched["phases"].items():
                if phase == "materialize_seconds":
                    continue
                lines.append(f"| {case_name(matched['case'])} / "
                             f"{matched['case'].get('strategy', 'semi-naive')} | "
                             f"{phase.removesuffix('_seconds')} | {values['before'] * 1000:.3f} | "
                             f"{values['after'] * 1000:.3f} | {ratio_text(values)} |")
        lines += ["", "### Maintenance compared with the pinned implementation", "",
                  "These rows compare the same operation across versions. The separate fresh-rebuild "
                  "ratio compares each version's recomputation cost. Input mutation counts and "
                  "fresh-closure validation must agree before an operation is compared. "
                  "All common evaluation counters and raw operation samples are retained in JSON.", "",
                  "| Workload | Operation | Previous ms | Current ms | Update ratio [interval] | Rebuild ratio [interval] | Overdeleted before → after |",
                  "|---|---|---:|---:|---:|---:|---:|"]
        for matched in comparison["matched"]:
            for name, operation in matched["maintenance_operations"].items():
                values = operation["update_seconds"]
                lines.append(f"| {case_name(matched['case'])} | {name} | "
                             f"{values['before'] * 1000:.3f} | {values['after'] * 1000:.3f} | "
                             f"{ratio_text(values)} | {ratio_text(operation['rebuild_seconds'])} | "
                             f"{counter_change(operation['work_counters'], 'overdeleted_facts')} |")
        lines += ["", f"Matched {len(comparison['matched'])} cases; "
                  f"excluded {len(comparison['skipped'])} new or changed cases. "
                  "The raw report records each exclusion reason. No workload or reference timing "
                  "is rewritten to obtain a match."]
    lines += ["", "These workloads use the Bach worked examples and synthetic inputs inspired by "
              "thesis chapter 8, not a reproduction of "
              "the 2004 KAON/XSB/Racer measurements. Modern hardware, execution strategies and "
              "measurement boundaries differ. OWL RL includes additional axiomatic/schema triples, "
              "so its total closure count is not directly comparable; the named instance answers are verified.",
              "", "The naive strategy shares the compiler and equality machinery; it is an execution "
              "baseline, not an independent semantic oracle. Unit validation also uses OWL RL and "
              "exhaustive finite models. There is no performance acceptance threshold or claim of "
              "production-scale throughput."]
    lines += bach.markdown_queries(report["results"])
    return "\n".join(lines) + "\n"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--suite", choices=["quick", "thesis", "bach"], default="quick")
    p.add_argument("--repeats", type=int, default=5)
    p.add_argument("--output", help="JSON report (default: benchmarks/<suite results>.json)")
    p.add_argument("--timeout", type=int, default=180)
    references = p.add_mutually_exclusive_group()
    references.add_argument("--baseline", default=str(DEFAULT_BASELINE),
                            help="Prior JSON report (default: immutable b1254c4 reference)")
    references.add_argument("--no-baseline", action="store_true", help="Explicitly omit comparisons")
    p.add_argument("--worker", help=argparse.SUPPRESS)
    args = p.parse_args()
    if args.output is None:
        args.output = "benchmarks/bach-results.json" if args.suite == "bach" else "benchmarks/results.json"
    if args.worker:
        print(json.dumps(worker(json.loads(args.worker))))
        return
    if args.repeats < 1:
        p.error("--repeats must be positive")
    cases = build_cases(args.suite)
    baseline_path = None if args.no_baseline else args.baseline
    try:
        protect_output(args.output, baseline_path)
        baseline, provenance = load_baseline(baseline_path) if baseline_path else (None, None)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        p.error(f"Baseline/output validation failed: {exc}")
    measured_sources = source_hashes()
    report = {"timestamp": datetime.now(timezone.utc).isoformat(),
              "suite": args.suite, "repeats": args.repeats, "planned_cases": len(cases),
              "output_file": args.output, "measurement_protocol": MEASUREMENT_PROTOCOL,
              "source_integrity": {"verified": True},
              "environment": {
                  "python": platform.python_version(), "platform": platform.platform(),
                  "machine": platform.machine(), "cpu_count": os.cpu_count(),
                  "git": git_provenance(), "python_hash_seed": os.environ.get("PYTHONHASHSEED", "random"),
                  "cpu": (subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
                          if sys.platform == "darwin" else platform.processor()),
                  "source_sha256": measured_sources,
                  "packages": {name: importlib.metadata.version(name) for name in
                               ["rdflib", "owlrl", "dlp-reasoner"]}}, "results": []}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    for case in cases:
        case["repeats"] = args.repeats
        print("Running " + json.dumps(case), flush=True)
        try:
            completed = subprocess.run([sys.executable, "-m", "benchmarks.run", "--worker",
                                        json.dumps(case)], text=True, capture_output=True,
                                       timeout=args.timeout)
            if completed.returncode:
                raise RuntimeError(completed.stderr[-4000:])
            report["results"].append(json.loads(completed.stdout))
        except (subprocess.TimeoutExpired, RuntimeError, json.JSONDecodeError) as exc:
            report["results"].append({"case": case, "error": str(exc)})
        if source_hashes() != measured_sources:
            report["source_integrity"] = {"verified": False, "reason": "Source files changed during run"}
            report["results"][-1] = {"case": case, "error": "Source files changed during run"}
        if baseline is not None:
            report["comparison"] = compare_baseline(report, baseline, baseline_path, provenance)
        output.write_text(json.dumps(report, indent=2) + "\n")
        output.with_suffix(".md").write_text(markdown(report))
        if not report["source_integrity"]["verified"]:
            break
    if any("error" in r for r in report["results"]) or any(
            not row["correctness"]["verified"] for row in report.get("comparison", {}).get("matched", [])):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
