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
import resource
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from rdflib import Graph, RDF

from dlp_reasoner import Reasoner
from dlp_reasoner.compiler import compile_graph
from dlp_reasoner.engine import Engine
from dlp_reasoner.model import Atom
from .workloads import EX, equality, existential, taxonomy, transitive


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


def worker(case):
    kind = case["kind"]
    if kind == "taxonomy":
        graph, meta = taxonomy(case["depth"], case["ipc"], case["variant"])
    elif kind == "equality":
        graph, meta = equality(case["size"]), {"pairs": case["size"]}
    elif kind == "existential":
        graph, meta = existential(case["size"]), {"roots": case["size"], "witness_depth": 4}
    elif kind == "transitive":
        graph, meta = transitive(case["size"]), {"chain_edges": case["size"]}
    else:
        graph, meta = taxonomy(4, 5, "P0", branching=5)
    serialized = graph.serialize(format="nt")
    parse_times, compile_times, materialize_times, query_times = [], [], [], []
    counts, update_times, rebuild_times, insertion_times = [], [], [], []
    property_query_times, subsumption_times, schema_update_times = [], [], []
    profile = "L3" if kind == "existential" else "L2"
    for repetition in range(case["repeats"]):
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
        if kind in {"taxonomy", "maintenance"}:
            answers, elapsed = timed(lambda: r.instances(EX.C0))
            assert len(answers) == meta["individuals"]
            actual = sum(1 for f in r.engine.facts if len(f.args) == 1 and
                         str(f.predicate).startswith(str(EX) + "C"))
            assert actual == meta["expected_class_facts"], (actual, meta)
        elif kind == "equality":
            answers, elapsed = timed(lambda: r.instances(EX.B))
            assert len(answers) == case["size"] * 2
        elif kind == "existential":
            answers, elapsed = timed(lambda: r.instances(EX.C4, include_witnesses=True))
            assert len(answers) == case["size"]
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
            facts = sorted(r.program.facts, key=repr)
            remove = facts[:max(1, len(facts) // 10)]
            _, elapsed = timed(lambda: r.engine.update(remove=remove))
            update_times.append(elapsed)
            expected = set(r.program.facts) - set(remove)
            p = compile_graph(parsed, profile=profile)
            p.facts = expected
            rebuilt, elapsed = timed(lambda: Engine(p).materialize())
            rebuild_times.append(elapsed)
            assert r.engine.facts == rebuilt.facts, "DRed disagrees with fresh closure"
            added = {Atom(EX.C100, (EX[f"new{repetition}_{i}"],)) for i in range(len(remove))}
            _, elapsed = timed(lambda: r.engine.update(add=added))
            insertion_times.append(elapsed)
            p.facts = expected | added
            rebuilt = Engine(p).materialize()
            assert r.engine.facts == rebuilt.facts, "Insertion disagrees with fresh closure"
            from dlp_reasoner.model import Rule, Var
            x = Var("x")
            rule = Rule(Atom(EX.NewRoot, (x,)), (Atom(EX.C0, (x,)),), "benchmark schema addition")
            _, elapsed = timed(lambda: r.engine.update_rules(add=[rule]))
            schema_update_times.append(elapsed)
            p.rules.append(rule)
            rebuilt = Engine(p).materialize()
            assert r.engine.facts == rebuilt.facts, "Rule insertion disagrees with fresh closure"
            r.engine.update_rules(remove=[rule])
            p.rules.remove(rule)
            assert r.engine.facts == Engine(p).materialize().facts
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform != "darwin":
        rss *= 1024
    result = {"case": case, "workload": meta, "input_triples": len(graph),
              "input_sha256": hashlib.sha256("\n".join(sorted(serialized.splitlines())).encode()).hexdigest(),
              "parse_seconds": summary(parse_times), "compile_seconds": summary(compile_times),
              "materialize_seconds": summary(materialize_times), "query_seconds": summary(query_times),
              "materialized_fact_counts": counts, "process_peak_rss_bytes": rss,
              "validation": "passed"}
    if update_times:
        result.update(delete_seconds=summary(update_times), rebuild_seconds=summary(rebuild_times),
                      insert_seconds=summary(insertion_times), rule_insert_seconds=summary(schema_update_times))
    if property_query_times:
        result.update(property_query_seconds=summary(property_query_times),
                      subsumption_seconds=summary(subsumption_times))
    return result


def markdown(report):
    lines = ["# Measured benchmark results", "",
             f"Run: {report['timestamp']}. Python {report['environment']['python']}; "
             f"{report['environment']['platform']}.", "",
             "All times below are medians in milliseconds. Every raw sample is in `results.json`.",
             "Peak RSS is the entire isolated worker (including parser, retained input and repetitions), "
             "not incremental reasoner allocation. Compiler and materializer timings are separate.", "",
             "| Workload | Engine | Input triples | Closure facts | Compile ms | Materialize ms | Query ms | Peak MiB |",
             "|---|---|---:|---:|---:|---:|---:|---:|"]
    for r in report["results"]:
        c = r["case"]
        name = (f"taxonomy d{c['depth']}/i{c['ipc']}/{c['variant']}" if c["kind"] == "taxonomy"
                else f"{c['kind']} {c.get('size', '')}")
        if "error" in r:
            lines.append(f"| {name} | {c.get('strategy', 'semi-naive')} | error: {r['error']} | | | | | |")
            continue
        values = [r[k]["median"] * 1000 for k in
                  ("compile_seconds", "materialize_seconds", "query_seconds")]
        lines.append(f"| {name} | {c.get('strategy', 'semi-naive')} | {r['input_triples']} | "
                     f"{r['materialized_fact_counts'][0]} | " + " | ".join(f"{v:.3f}" for v in values)
                     + f" | {r['process_peak_rss_bytes'] / 2**20:.1f} |")
        if "delete_seconds" in r:
            lines.append(f"\nMaintenance deletion median: {r['delete_seconds']['median'] * 1000:.3f} ms; "
                         f"full rebuild: {r['rebuild_seconds']['median'] * 1000:.3f} ms.\n")
    lines += ["", "## Additional query and maintenance timings", "",
              "| Workload | Property pairs ms | Subsumption ms | Delete ms | Insert ms | Rule insert ms | Rebuild ms |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for r in report["results"]:
        if "error" in r or not any(k in r for k in ["property_query_seconds", "delete_seconds"]):
            continue
        c = r["case"]
        name = (f"d{c['depth']}/i{c['ipc']}/{c['variant']}" if c["kind"] == "taxonomy" else c["kind"])
        cells = [f"{r[k]['median'] * 1000:.3f}" if k in r else "—" for k in
                 ["property_query_seconds", "subsumption_seconds", "delete_seconds", "insert_seconds",
                  "rule_insert_seconds", "rebuild_seconds"]]
        lines.append("| " + name + " | " + " | ".join(cells) + " |")
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
    p.add_argument("--worker", help=argparse.SUPPRESS)
    args = p.parse_args()
    if args.worker:
        print(json.dumps(worker(json.loads(args.worker))))
        return
    if args.repeats < 1:
        p.error("--repeats must be positive")
    cases = []
    for depth in [3, 5, 7]:
        for ipc in ([3, 9, 15] if args.suite == "thesis" else [3]):
            for variant in (["P0", "P1", "PF"] if args.suite == "thesis" else ["P0"]):
                cases.append({"kind": "taxonomy", "depth": depth, "ipc": ipc, "variant": variant})
    cases += [{"kind": "taxonomy", "depth": 3, "ipc": 3, "variant": "P0", "strategy": s}
              for s in ["naive", "owlrl"]]
    cases += [{"kind": "equality", "size": s} for s in [100, 1000]]
    cases += [{"kind": "existential", "size": 100}, {"kind": "transitive", "size": 100},
              {"kind": "maintenance"}]
    report = {"timestamp": datetime.now(timezone.utc).isoformat(),
              "suite": args.suite, "environment": {
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
        output.write_text(json.dumps(report, indent=2) + "\n")
        output.with_suffix(".md").write_text(markdown(report))
    if any("error" in r for r in report["results"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
