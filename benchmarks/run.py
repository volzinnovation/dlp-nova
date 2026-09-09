"""Run with: python -m benchmarks.run --suite thesis --repeats 5.

Every case is isolated in a child process. Timings exclude generation, include
separate parse/compile/materialize phases, and preserve every repetition.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
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
from .workloads import (
    EX, cardinality_taxonomy, equality, existential, factored_enumerations, factored_unions,
    maintenance, taxonomy, transitive,
)

MEASUREMENT_PROTOCOL = "phase-timings-v1"


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


def build_cases(suite):
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
    return cases


def case_name(case):
    kind = case["kind"]
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
    counts, shapes, engine_stats, updates = [], [], [], []
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


def compare_baseline(report, baseline, baseline_path):
    def key(case):
        return json.dumps({**{k: v for k, v in case.items() if k != "repeats"},
                           "strategy": case.get("strategy", "semi-naive")}, sort_keys=True)
    prior = {key(r["case"]): r for r in baseline["results"] if "error" not in r}
    comparisons, skipped = [], []
    for result in report["results"]:
        if "error" in result:
            continue
        old = prior.get(key(result["case"]))
        reason = None
        if old is None:
            reason = "no matching case controls"
        elif old["input_sha256"] != result["input_sha256"]:
            reason = "input hash changed"
        elif baseline.get("measurement_protocol", MEASUREMENT_PROTOCOL) != MEASUREMENT_PROTOCOL:
            reason = "measurement boundaries differ"
        elif result["case"]["kind"] == "maintenance" and old["workload"].get(
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
            previous, current = old[phase]["median"], result[phase]["median"]
            phases[phase] = {"before": previous, "after": current,
                             "after_over_before": current / previous if previous else None}
        comparisons.append({"case": result["case"], "input_sha256": result["input_sha256"],
                            "phases": phases})
    return {"baseline_path": str(baseline_path), "baseline_timestamp": baseline["timestamp"],
            "baseline_source_sha256": baseline["environment"]["source_sha256"],
            "current_source_sha256": report["environment"]["source_sha256"],
            "baseline_environment": baseline["environment"],
            "matched": comparisons, "skipped": skipped,
            "caveat": "Matched inputs and timing boundaries; runs are not interleaved or noise controlled."}


def markdown(report):
    raw_name = Path(report.get("output_file", "results.json")).name
    passed = sum(r.get("validation") == "passed" for r in report["results"])
    errors = sum("error" in r for r in report["results"])
    lines = ["# Measured benchmark results", "",
             f"Run: {report['timestamp']}. Python {report['environment']['python']}; "
             f"{report['environment']['platform']}.", "",
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
              "Fresh-rebuild timing excludes recompilation, matching the update API's precompiled inputs.", "",
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
        lines += ["", "## Before/after comparison on unchanged inputs", "",
                  f"Baseline: `{comparison['baseline_path']}`, run {comparison['baseline_timestamp']}. "
                  "Rows require identical case controls, input hashes and timing boundaries. "
                  "Different source hashes are retained in JSON for attribution. Ratios below 1 mean "
                  "a shorter current median; separate runs do not control machine load or timing noise.", "",
                  "| Workload | Engine | Previous materialize ms | Current materialize ms | After / before |",
                  "|---|---|---:|---:|---:|"]
        for matched in comparison["matched"]:
            values = matched["phases"]["materialize_seconds"]
            ratio = values["after_over_before"]
            ratio_text = f"{ratio:.3f}" if ratio is not None else "—"
            lines.append(f"| {case_name(matched['case'])} | "
                         f"{matched['case'].get('strategy', 'semi-naive')} | "
                         f"{values['before'] * 1000:.3f} | {values['after'] * 1000:.3f} | {ratio_text} |")
        lines += ["", f"Matched {len(comparison['matched'])} cases; "
                  f"excluded {len(comparison['skipped'])} new or changed cases. "
                  "The raw report records each exclusion reason. Changed PF targets and the revised "
                  "maintenance populations/operations are excluded from before/after claims."]
    lines += ["", "These are synthetic workloads inspired by thesis chapter 8, not a reproduction of "
              "the 2004 KAON/XSB/Racer measurements. Modern hardware, execution strategies and "
              "measurement boundaries differ. OWL RL includes additional axiomatic/schema triples, "
              "so its total closure count is not directly comparable; the named instance answers are verified.",
              "", "The naive strategy shares the compiler and equality machinery; it is an execution "
              "baseline, not an independent semantic oracle. Unit validation also uses OWL RL and "
              "exhaustive finite models. There is no performance acceptance threshold or claim of "
              "production-scale throughput."]
    return "\n".join(lines) + "\n"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--suite", choices=["quick", "thesis"], default="quick")
    p.add_argument("--repeats", type=int, default=5)
    p.add_argument("--output", default="benchmarks/results.json")
    p.add_argument("--timeout", type=int, default=180)
    p.add_argument("--baseline", help="Prior JSON report for comparisons on unchanged inputs")
    p.add_argument("--worker", help=argparse.SUPPRESS)
    args = p.parse_args()
    if args.worker:
        print(json.dumps(worker(json.loads(args.worker))))
        return
    if args.repeats < 1:
        p.error("--repeats must be positive")
    cases = build_cases(args.suite)
    baseline = json.loads(Path(args.baseline).read_text()) if args.baseline else None
    if args.baseline and Path(args.baseline).resolve() == Path(args.output).resolve():
        p.error("--baseline and --output must be different files")
    report = {"timestamp": datetime.now(timezone.utc).isoformat(),
              "suite": args.suite, "repeats": args.repeats, "planned_cases": len(cases),
              "output_file": args.output, "measurement_protocol": MEASUREMENT_PROTOCOL,
              "environment": {
                  "python": platform.python_version(), "platform": platform.platform(),
                  "machine": platform.machine(), "cpu_count": os.cpu_count(),
                  "cpu": (subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
                          if sys.platform == "darwin" else platform.processor()),
                  "source_sha256": {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                                    for path in sorted([*Path("src/dlp_reasoner").glob("*.py"),
                                                        *Path("benchmarks").glob("*.py")])},
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
        if baseline is not None:
            report["comparison"] = compare_baseline(report, baseline, args.baseline)
        output.write_text(json.dumps(report, indent=2) + "\n")
        output.with_suffix(".md").write_text(markdown(report))
    if any("error" in r for r in report["results"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
