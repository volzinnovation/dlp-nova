"""Reproducible factorial experiments; independent of the frozen thesis suite.

Create the protocol before running measurements:
  python -m benchmarks.research --write-protocol
  python -m benchmarks.research --blocks 9

The two private Engine switches isolate mechanisms, not whole historical commits.
Every configuration executes in a new process. This is an original experiment on
this implementation, not a claim to outperform external state-of-the-art systems.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from itertools import product
import json
import os
from pathlib import Path
import platform
import random
import resource
import shutil
import statistics
import subprocess
import sys
import time

from rdflib import URIRef

from dlp_reasoner.engine import Engine
from dlp_reasoner.model import Atom, Program, Rule, TOP, Var

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = "research-factorial-v3"
HISTORICAL_BASELINE = "b1254c441731ca4fdf32ea83570ff99aaa84ac2a"
PRE_RESEARCH_COMMIT = "8ce254f"
CONFIGURATIONS = {
    "fixed-dred": (False, False),
    "adaptive-dred": (True, False),
    "fixed-support": (False, True),
    "adaptive-support": (True, True),
}
UNARY_MODES = ("sparse-single", "sparse-disjoint", "sparse-overlap",
               "dense-overlap", "dense-selective")
SUPPORT_MODES = ("alternate-support", "unsupported-cycle", "mixed-new-support",
                 "unique-signatures")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def atom(predicate, *args):
    return Atom("urn:research:" + predicate, args)


@dataclass
class Experiment:
    rules: list
    facts: set
    additions: set
    removals: set
    add_rules: list
    remove_rules: list

    def final_program(self):
        removed = set(self.remove_rules)
        return Program(list(dict.fromkeys([rule for rule in self.rules if rule not in removed]
                                          + self.add_rules)),
                       (self.facts - self.removals) | self.additions)


def build_cases(small=False):
    """The complete predeclared grid, not selected after observing timings."""
    size = 8 if small else 2048
    widths = (4,) if small else (8, 64)
    cases = [{"family": "unary", "mode": mode,
              "size": 32 if mode == "sparse-overlap" and not small else size, "width": width}
             for mode in UNARY_MODES for width in widths]
    depths = (4,) if small else (4, 32)
    cases += [{"family": "support", "mode": mode, "size": 8 if small else 256,
               "depth": depth} for mode in SUPPORT_MODES for depth in depths]
    return cases


def make_experiment(case):
    size = case["size"]
    require(isinstance(size, int) and size >= 4, "size must be at least four")
    values = [URIRef(f"urn:research:individual:{i}") for i in range(size)]
    x = Var("x")
    facts, additions, add_rules = set(), set(), []
    if case["family"] == "unary":
        mode, width = case["mode"], case["width"]
        require(mode in UNARY_MODES and width >= 2, "invalid unary controls")
        for position in range(width):
            for number, value in enumerate(values):
                if mode == "sparse-single":
                    changed = position == 0 and number == size - 1
                    present = not changed
                elif mode == "sparse-disjoint":
                    changed = number == position
                    present = not changed
                elif mode == "sparse-overlap":
                    changed = number == size - 1
                    present = not changed
                elif mode == "dense-overlap":
                    changed = number >= size // 2
                    present = not changed
                else:
                    # One tiny unchanged relation makes constructing the union
                    # of large deltas wasteful. All answers appear only now.
                    changed = position < width - 1 and number < size // 2
                    present = (number >= size // 2 if position < width - 1
                               else number < max(1, size // 64))
                if present:
                    facts.add(atom(f"P{position}", value))
                if changed:
                    additions.add(atom(f"P{position}", value))
        rules = [Rule(atom("Answer", x), tuple(atom(f"P{i}", x) for i in range(width)))]
        return Experiment(rules, facts, additions, set(), [], [])
    require(case["family"] == "support", "unknown experimental family")
    mode, depth = case["mode"], case["depth"]
    require(mode in SUPPORT_MODES and depth >= 2, "invalid support controls")
    left = Rule(atom("C0", x), (atom("Left", x),))
    right = Rule(atom("C0", x), (atom("Right", x),))
    rules = [left, right]
    rules += [Rule(atom(f"C{i + 1}", x), (atom(f"C{i}", x),)) for i in range(depth)]
    rules += [Rule(atom("C0", x), (atom(f"C{depth}", x),)),
              Rule(atom("Answer", x), (atom(f"C{depth}", x),))]
    for number, value in enumerate(values):
        facts.add(atom("Left", value))
        if mode in {"alternate-support", "unique-signatures"}:
            facts.add(atom("Right", value))
        elif mode == "mixed-new-support":
            additions.add(atom("Replacement", value))
        if mode == "unique-signatures":
            for bit in range(size.bit_length()):
                if number & (1 << bit):
                    facts.add(atom(f"Noise{bit}", value))
    if mode == "unique-signatures":
        # Keep every signature bit relevant to the eligible proof program;
        # unrelated assertions may correctly be filtered by the implementation.
        rules += [Rule(atom(f"NoiseSink{bit}", x), (atom(f"Noise{bit}", x),))
                  for bit in range(size.bit_length())]
    if mode == "mixed-new-support":
        add_rules.append(Rule(atom("C0", x), (atom("Replacement", x),)))
    return Experiment(rules, facts, additions, set(), add_rules, [left])


def _term(value):
    if isinstance(value, Var):
        return ["variable", value.name]
    # Workload constants are exclusively IRIs. The engine also adds its private
    # nonempty-domain seed; recording its type prevents collision with an IRI.
    return [type(value).__name__, str(value)]


def _atom(value):
    return [_term(value.predicate), [_term(term) for term in value.args]]


def _rule(rule):
    return [None if rule.head is None else _atom(rule.head),
            [_atom(value) for value in rule.body], rule.label]


def digest(values):
    rows = sorted(json.dumps(value, sort_keys=True, separators=(",", ":")) for value in values)
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()


def fact_digest(facts):
    return digest(_atom(value) for value in facts)


def experiment_digest(experiment):
    return digest([
        ["rules", sorted((_rule(value) for value in experiment.rules), key=repr)],
        ["facts", sorted((_atom(value) for value in experiment.facts), key=repr)],
        ["add", sorted((_atom(value) for value in experiment.additions), key=repr)],
        ["remove", sorted((_atom(value) for value in experiment.removals), key=repr)],
        ["add_rules", sorted((_rule(value) for value in experiment.add_rules), key=repr)],
        ["remove_rules", sorted((_rule(value) for value in experiment.remove_rules), key=repr)],
    ])


def finite_oracle(program):
    """Exhaustively ground small finite positive programs, without Engine joins.

    Deliberately limited to this experiment's ordinary relational language. It
    does not implement the OWL compiler, equality, Skolem terms, or builtins.
    """
    domain = set(term for fact in program.facts for term in fact.args)
    for rule in program.rules:
        require(rule.head is not None, "oracle does not support constraints")
        for value in (*rule.body, rule.head):
            require(value.predicate != TOP, "oracle excludes TOP")
            domain.update(term for term in value.args if not isinstance(term, Var))
    instances = []
    for rule in program.rules:
        variables = sorted({term for value in (*rule.body, rule.head) for term in value.args
                            if isinstance(term, Var)}, key=lambda var: var.name)
        for assignment in product(sorted(domain, key=str), repeat=len(variables)):
            binding = dict(zip(variables, assignment))

            def ground(value):
                return Atom(value.predicate, tuple(binding.get(term, term) for term in value.args))

            instances.append((ground(rule.head), frozenset(ground(value) for value in rule.body)))
    result = set(program.facts)
    while True:
        added = {head for head, body in instances if body <= result} - result
        if not added:
            return result
        result.update(added)


def configured_engine(configuration):
    require(configuration in CONFIGURATIONS, "unknown ablation configuration")
    adaptive, support = CONFIGURATIONS[configuration]
    require(hasattr(Engine, "_unary_strategy"), "adaptive ablation hook is absent")
    require(hasattr(Engine, "_support_certificates_enabled"), "support ablation hook is absent")

    class ExperimentalEngine(Engine):
        _unary_strategy = "adaptive" if adaptive else "union-first"
        _support_certificates_enabled = support

    return ExperimentalEngine


def worker(case, configuration, memory=False):
    require(sys.flags.optimize == 0, "validation requires assertions enabled")
    experiment = make_experiment(case)
    engine_type = configured_engine(configuration)
    start = time.perf_counter()
    engine = engine_type(Program(list(experiment.rules), set(experiment.facts))).materialize()
    materialize_seconds = time.perf_counter() - start
    initial_stats = dict(engine.stats)
    initial_digest = fact_digest(engine.facts)
    if memory:
        import tracemalloc
        tracemalloc.start()
    start = time.perf_counter()
    engine.update(add=experiment.additions, remove=experiment.removals,
                  add_rules=experiment.add_rules, remove_rules=experiment.remove_rules)
    update_seconds = time.perf_counter() - start
    update_stats = dict(engine.stats)
    memory_result = None
    if memory:
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        memory_result = {"retained_python_bytes": current, "peak_python_bytes": peak,
                         "scope": "additional traced allocations during update; old store already built"}
    require(engine.complete and not engine.violations, "experimental result incomplete/inconsistent")
    final = experiment.final_program()
    # Validation is outside measured operations. Rebuild uses the plain fixed
    # configuration rather than the tested optimization and compares all facts.
    reference_type = configured_engine("fixed-dred")
    reference = reference_type(Program(list(final.rules), set(final.facts))).materialize()
    require(reference.complete and not reference.violations, "reference closure incomplete")
    require(engine.facts == reference.facts, "update differs from fresh fixed-plan closure")
    result = {
        "case": case, "configuration": configuration, "validation": "passed",
        "input_sha256": experiment_digest(experiment), "initial_sha256": initial_digest,
        "final_sha256": fact_digest(engine.facts), "final_facts": len(engine.facts),
        "final_assertions_sha256": fact_digest(final.facts),
        "final_rules_sha256": digest(_rule(rule) for rule in final.rules),
        "materialize_seconds": None if memory else materialize_seconds,
        "update_seconds": None if memory else update_seconds,
        "initial_stats": initial_stats, "update_stats": update_stats,
        "memory": memory_result, "hash_seed": os.environ.get("PYTHONHASHSEED"),
        "rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        * (1 if sys.platform == "darwin" else 1024),
    }
    if case["size"] <= 8:
        expected = finite_oracle(final)
        actual = {fact for fact in engine.facts if fact.predicate != TOP}
        require(actual == expected, "result differs from independent finite grounding oracle")
        result["finite_oracle"] = "passed"
    return result


def sources():
    paths = [*ROOT.glob("src/dlp_reasoner/*.py"), ROOT / "benchmarks/research.py"]
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths)}


def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True).strip()


def protocol(blocks):
    require(blocks >= 7, "at least seven independent blocks are required")
    return {
        "protocol": PROTOCOL, "historical_baseline": HISTORICAL_BASELINE,
        "pre_research_commit": git("rev-parse", PRE_RESEARCH_COMMIT),
        "blocks": blocks, "case_matrix": build_cases(), "configurations": CONFIGURATIONS,
        "primary_endpoint": "wall seconds for one complete atomic Engine.update transaction",
        "secondary_endpoints": ["initial materialization seconds", "all engine counters",
                                "whole-process peak RSS, including validation"],
        "hypotheses": [
            "H1: adaptive unary planning reduces delta processing when full joins are selective; "
            "sparse updates retain their benefit without dense-delta union allocation.",
            "H2: assertion-seeded support certificates reduce unnecessary overdeletion in "
            "supported cycles, including mixed transactions with newly added support.",
            "H3: unsupported cycles lose all unsupported results; unique signatures expose "
            "certificate preparation and cache overhead rather than hiding it.",
            "H4: the two mechanisms can interact; all four combinations must be measured.",
        ],
        "failure_criteria": [
            "Any full fact-set disagreement or incomplete run invalidates that configuration.",
            "Report every case, including overhead and regressions; no post-hoc case removal.",
            "A speedup against local ablations or historical b1254c4 is not state-of-art evidence.",
        ],
        "promotion_criteria": {
            "adaptive": "All correctness checks pass; geometric mean of paired update ratios "
                        "over the ten unary cases is <=1, and no targeted shape has >10% "
                        "median regression without an explained measurement effect. This is "
                        "an explicit engineering acceptance threshold, not a significance test.",
            "certificates": "Remain experimental if the unsupported-cycle or unique-signature "
                            "cases regress >10%, or benefits in alternate/new-support cases "
                            "are not consistent. Correctness is required irrespective of speed.",
        },
        "design": "Each block uses four independently launched workers with the same explicit "
                  "hash seed. A seeded Latin-square rotation balances execution position over "
                  "groups of four blocks; block and case orders are saved. One cold invocation "
                  "per worker; no discarded warm-up or concurrent experiments.",
        "uncertainty": "Report raw per-block ratios and paired bootstrap intervals (descriptive); "
                       "nine blocks remain limited evidence on one host. Do not pool cases.",
        "correctness": "Every update equals a fresh fixed-plan closure as a full set. Across "
                       "ablations, exact input, final rules/assertions, and entire initial/final "
                       "closure SHA-256 digests must match. Small cases also use an independent "
                       "exhaustively grounded positive Datalog oracle.",
        "memory": "Optional separate tracemalloc workers; their instrumented times are never "
                  "mixed with ordinary timing samples. tracemalloc omits native allocations; "
                  "RSS is whole-process peak and includes the correctness reference.",
        "external_baselines": {name: shutil.which(name) for name in ("souffle", "RDFox", "rdfox")},
        "external_scope": "No native external reasoner currently required. Existing owlrl has "
                          "different schema closure and no equivalent arbitrary rule transaction "
                          "interface. External competitive performance remains unestablished.",
    }


def execution_orders(blocks, seed=2004):
    randomizer = random.Random(seed)
    names = list(CONFIGURATIONS)
    result = []
    for block in range(blocks):
        if block % len(names) == 0:
            randomizer.shuffle(names)
        offset = block % len(names)
        result.append(names[offset:] + names[:offset])
    return result


def paired_summary(before, after):
    require(len(before) == len(after) and before, "paired samples must have equal nonzero length")
    ratios = [new / old for old, new in zip(before, after)]
    rng = random.Random(2004)
    resampled = sorted(statistics.median(rng.choices(ratios, k=len(ratios))) for _ in range(2000))
    return {"median_ratio": statistics.median(ratios), "paired_ratios": ratios,
            "descriptive_paired_bootstrap_95_interval": [resampled[50], resampled[1949]],
            "before_median_seconds": statistics.median(before),
            "after_median_seconds": statistics.median(after)}


def summarize(rows):
    by_name = {name: sorted((row for row in rows if row["configuration"] == name),
                            key=lambda row: row["block"]) for name in CONFIGURATIONS}
    require(len({len(value) for value in by_name.values()}) == 1, "incomplete factorial blocks")
    summaries = {}
    contrasts = [("adaptive-only", "fixed-dred", "adaptive-dred"),
                 ("support-only", "fixed-dred", "fixed-support"),
                 ("combined", "fixed-dred", "adaptive-support"),
                 ("adaptive-with-support", "fixed-support", "adaptive-support"),
                 ("support-with-adaptive", "adaptive-dred", "adaptive-support")]
    for label, before, after in contrasts:
        summaries[label] = paired_summary([row["update_seconds"] for row in by_name[before]],
                                          [row["update_seconds"] for row in by_name[after]])
    interactions = []
    for index in range(len(by_name["fixed-dred"])):
        times = {name: values[index]["update_seconds"] for name, values in by_name.items()}
        interactions.append(times["adaptive-support"] * times["fixed-dred"] /
                            (times["adaptive-dred"] * times["fixed-support"]))
    summaries["multiplicative_interaction"] = {"paired_ratios": interactions,
                                               "median_ratio": statistics.median(interactions)}
    return summaries


def promotion_assessment(cases):
    """Apply predeclared engineering thresholds; this never changes dispatch."""
    unary = [item["summary"]["adaptive-only"]["median_ratio"] for item in cases
             if item["case"]["family"] == "unary"]
    overhead = [item["summary"]["support-only"]["median_ratio"] for item in cases
                if item["case"]["mode"] in {"unsupported-cycle", "unique-signatures"}]
    benefit = [item["summary"][contrast]["median_ratio"] for item in cases
               if item["case"]["mode"] in {"alternate-support", "mixed-new-support"}
               for contrast in ("support-only", "support-with-adaptive")]
    require(len(unary) == 10 and len(overhead) == 4 and len(benefit) == 8,
            "promotion assessment requires the complete predeclared case matrix")
    geometric_mean = statistics.geometric_mean(unary)
    return {
        "adaptive_geometric_mean_ratio": geometric_mean,
        "adaptive_worst_case_ratio": max(unary),
        "adaptive_threshold_met": geometric_mean <= 1 and max(unary) <= 1.1,
        "support_worst_overhead_ratio": max(overhead),
        "support_worst_benefit_case_ratio": max(benefit),
        "support_threshold_met": max(overhead) <= 1.1 and max(benefit) < 1,
        "interpretation": "Predeclared engineering screen on one host, not statistical "
                          "significance or proof of external superiority. No dispatch changes "
                          "are made by the experiment. All outcomes require interpretation.",
    }


def markdown(report):
    lines = ["# Factorial reasoning experiments", "", f"Status: **{report['status']}**.", "",
             "The fixed baseline b1254c4 remains unchanged. These comparisons isolate two "
             "mechanisms in one source tree; they are not historical commit replays or "
             "external state-of-the-art comparisons.", "",
             "| Case | Contrast | Before ms | After ms | Paired median ratio | Interval |",
             "|---|---|---:|---:|---:|---|"]
    for item in report["cases"]:
        label = json.dumps(item["case"], sort_keys=True)
        for name, summary in item.get("summary", {}).items():
            if "before_median_seconds" not in summary:
                continue
            interval = summary["descriptive_paired_bootstrap_95_interval"]
            lines.append(f"| {label} | {name} | {summary['before_median_seconds'] * 1000:.3f} | "
                         f"{summary['after_median_seconds'] * 1000:.3f} | "
                         f"{summary['median_ratio']:.4g} | [{interval[0]:.4g}, {interval[1]:.4g}] |")
    lines += ["", "Ratios below one indicate shorter update times. All raw initial and update "
              "statistics, full outcome hashes, worker order, seed and source provenance are "
              "retained in JSON. Intervals describe these paired samples on one host. "
              "Candidate rows omit C-level set probes; do not interpret them as all CPU work."]
    if report.get("promotion_assessment"):
        lines += ["", "Predeclared engineering screen:", "", "```json",
                  json.dumps(report["promotion_assessment"], indent=2), "```"]
    if report.get("error"):
        lines += ["", f"Failure: {report['error']}"]
    return "\n".join(lines) + "\n"


def protected_output(path):
    path = path.resolve()
    require(path.suffix == ".json", "output must have .json extension")
    require(not path.is_relative_to(ROOT / "benchmarks/baselines"), "cannot overwrite baselines")
    reserved = [ROOT / "benchmarks" / name for name in
                ("results.json", "baseline-results.json", "replay-results.json", "bach-results.json")]
    for target in (path, path.with_suffix(".md")):
        for item in reserved + [item.with_suffix(".md") for item in reserved]:
            require(target != item and not (target.exists() and item.exists() and target.samefile(item)),
                    "cannot overwrite a recorded benchmark")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blocks", type=int, default=9)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/research-results.json")
    parser.add_argument("--protocol", type=Path, default=ROOT / "benchmarks/research-protocol-v3.json")
    parser.add_argument("--write-protocol", action="store_true")
    parser.add_argument("--memory", action="store_true")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        request = json.loads(args.worker)
        print(json.dumps(worker(request["case"], request["configuration"], request.get("memory", False))))
        return
    planned = protocol(args.blocks)
    protocol_path = protected_output(args.protocol)
    if args.write_protocol:
        require(not protocol_path.exists(), "protocol already exists; choose a new path for amendments")
        protocol_path.parent.mkdir(parents=True, exist_ok=True)
        protocol_path.write_text(json.dumps(planned, indent=2) + "\n")
        print(protocol_path)
        return
    require(protocol_path.is_file(), "write the premeasurement protocol before running")
    require(json.loads(protocol_path.read_text()) == json.loads(json.dumps(planned)),
            "premeasurement protocol differs; create a separately named amendment")
    output = protected_output(args.output)
    require(output != protocol_path, "output cannot overwrite the protocol")
    source_hashes = sources()
    report = {"status": "running", "created_utc": datetime.now(timezone.utc).isoformat(),
              "protocol": planned, "protocol_sha256": hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
              "source_sha256": source_hashes, "git_head": git("rev-parse", "HEAD"),
              "git_dirty": bool(git("status", "--porcelain")), "platform": platform.platform(),
              "python": sys.version, "cpu_count": os.cpu_count(), "machine": platform.machine(),
              "rdflib_version": __import__("rdflib").__version__,
              "engine_path": __import__("dlp_reasoner").__file__,
              "cases": [], "finite_oracle_checks": []}

    def save():
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n")
        output.with_suffix(".md").write_text(markdown(report))

    def launch(case, name, seed, memory=False):
        env = os.environ.copy()
        env.update(PYTHONHASHSEED=str(seed), PYTHONOPTIMIZE="0", PYTHONNOUSERSITE="1",
                   PYTHONPATH=os.pathsep.join((str(ROOT / "src"), str(ROOT))))
        command = [sys.executable, "-m", "benchmarks.research", "--worker",
                   json.dumps({"case": case, "configuration": name, "memory": memory})]
        started = time.perf_counter()
        result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True,
                                timeout=args.timeout)
        require(result.returncode == 0, result.stderr[-4000:])
        value = json.loads(result.stdout)
        value["worker_seconds"] = time.perf_counter() - started
        require(value["validation"] == "passed", "worker did not validate")
        require(sources() == source_hashes, "measured source changed during experiment")
        require(hashlib.sha256(protocol_path.read_bytes()).hexdigest() == report["protocol_sha256"],
                "premeasurement protocol changed during experiment")
        return value

    try:
        # These tests are not performance observations and do not warm up workers.
        for case in build_cases(small=True):
            checks = [launch(case, name, 2004) for name in CONFIGURATIONS]
            require(all(value.get("finite_oracle") == "passed" for value in checks), "oracle not run")
            report["finite_oracle_checks"].append({"case": case, "configurations": len(checks),
                                                   "status": "passed"})
        for case_number, case in enumerate(planned["case_matrix"]):
            item = {"case": case, "runs": [], "orders": execution_orders(args.blocks)}
            report["cases"].append(item)
            expected = None
            for block, order in enumerate(item["orders"]):
                for position, name in enumerate(order):
                    result = launch(case, name, 2004 + block)
                    identity = {key: result[key] for key in
                                ("input_sha256", "initial_sha256", "final_sha256", "final_facts",
                                 "final_assertions_sha256", "final_rules_sha256")}
                    if expected is None:
                        expected = identity
                    require(identity == expected, "full outcome differs across configurations/blocks")
                    result.update(block=block, position=position)
                    item["runs"].append(result)
                save()
            item["summary"] = summarize(item["runs"])
            if args.memory:
                item["memory_runs"] = [launch(case, name, 2004, True) for name in CONFIGURATIONS]
            save()
            print(f"Validated {case_number + 1}/{len(planned['case_matrix'])}: {case}", flush=True)
        report["promotion_assessment"] = promotion_assessment(report["cases"])
        report["status"] = "passed"
    except Exception as exc:
        report["status"], report["error"] = "failed", str(exc)
        save()
        raise
    save()


if __name__ == "__main__":
    main()
