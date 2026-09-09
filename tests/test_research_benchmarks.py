"""Independent safeguards for the factorial research experiment and its evidence."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmarks.research import (  # noqa: E402
    CONFIGURATIONS, ROOT, SUPPORT_MODES, UNARY_MODES, atom, build_cases,
    configured_engine, execution_orders, experiment_digest, fact_digest, finite_oracle,
    make_experiment, paired_summary, promotion_assessment, protected_output, summarize, worker,
)
from dlp_reasoner.model import Program, Rule, TOP, Var  # noqa: E402


def test_predeclared_grid_covers_gain_and_overhead_regimes():
    cases = build_cases()
    assert len(cases) == 18
    assert {case["mode"] for case in cases} == set(UNARY_MODES) | set(SUPPORT_MODES)
    assert {case["width"] for case in cases if case["family"] == "unary"} == {8, 64}
    assert {case["depth"] for case in cases if case["family"] == "support"} == {4, 32}
    assert len({json.dumps(case, sort_keys=True) for case in cases}) == len(cases)


@pytest.mark.parametrize("case", build_cases(small=True))
def test_generators_and_transaction_digest_are_deterministic(case):
    left, right = make_experiment(case), make_experiment(deepcopy(case))
    assert left == right
    assert experiment_digest(left) == experiment_digest(right)
    right.additions.add(atom("Other", "urn:new"))
    assert experiment_digest(left) != experiment_digest(right)


@pytest.mark.parametrize("case", build_cases(small=True))
def test_ground_oracle_proves_expected_answers_and_unsupported_cycle_loss(case):
    experiment = make_experiment(case)
    result = finite_oracle(experiment.final_program())
    answers = {fact for fact in result if fact.predicate == "urn:research:Answer"}
    expected = 0 if case["mode"] == "unsupported-cycle" else (
        1 if case["mode"] == "dense-selective" else case["size"])
    assert len(answers) == expected
    if case["mode"] == "unsupported-cycle":
        assert not any(fact.predicate.startswith("urn:research:C") for fact in result)


def test_independent_oracle_handles_multivariable_repeated_premises_and_cycles():
    x, y, z = Var("x"), Var("y"), Var("z")
    a, b, c = "a", "b", "c"
    rules = [Rule(atom("reach", x, y), (atom("edge", x, y),)),
             Rule(atom("reach", x, z), (atom("reach", x, y), atom("edge", y, z))),
             Rule(atom("ghost", x), (atom("ghost", x),))]
    result = finite_oracle(Program(rules, {atom("edge", a, b), atom("edge", b, c)}))
    assert atom("reach", a, c) in result
    assert not any(fact.predicate == "urn:research:ghost" for fact in result)


@pytest.mark.parametrize("case", build_cases(small=True))
@pytest.mark.parametrize("configuration", CONFIGURATIONS)
def test_each_ablation_matches_ground_oracle_and_fresh_closure(case, configuration):
    result = worker(case, configuration)
    assert result["validation"] == result["finite_oracle"] == "passed"
    assert len(result["initial_sha256"]) == len(result["final_sha256"]) == 64
    assert result["materialize_seconds"] > 0
    assert result["update_seconds"] > 0
    assert result["memory"] is None


def test_configuration_switches_are_independent_private_subclass_controls():
    for name, (adaptive, support) in CONFIGURATIONS.items():
        engine = configured_engine(name)
        assert engine._unary_strategy == ("adaptive" if adaptive else "union-first")
        assert engine._support_certificates_enabled is support


@pytest.mark.parametrize("configuration", CONFIGURATIONS)
def test_bound_unary_probe_and_already_saturated_update_are_invariant(configuration):
    experiment = make_experiment(build_cases(small=True)[0])
    engine_type = configured_engine(configuration)
    final = experiment.final_program()
    engine = engine_type(Program(list(final.rules), set(final.facts))).materialize()
    expected = finite_oracle(final)
    assert {fact for fact in engine.facts if fact.predicate != TOP} == expected
    chosen = next(iter(final.facts)).args[0]
    rule = final.rules[0]
    assert list(engine._solutions(rule, initial={Var("x"): chosen})) == [{Var("x"): chosen}]
    before = fact_digest(engine.facts)
    engine.update(add=final.facts, add_rules=final.rules)
    assert engine.complete and fact_digest(engine.facts) == before
    assert engine.stats["derived_facts"] == 0


def test_memory_instrumentation_is_separate_from_timing_samples():
    result = worker(build_cases(small=True)[0], "adaptive-support", memory=True)
    assert result["update_seconds"] is None
    assert result["materialize_seconds"] is None
    assert result["memory"]["peak_python_bytes"] >= result["memory"]["retained_python_bytes"]


def test_balanced_randomized_rotations_are_reproducible_and_position_balanced():
    orders = execution_orders(9)
    assert orders == execution_orders(9)
    assert orders != execution_orders(9, seed=777)
    for begin in (0, 4):
        for position in range(4):
            assert {order[position] for order in orders[begin:begin + 4]} == set(CONFIGURATIONS)


def test_paired_summary_and_factorial_interactions_do_not_pool_unrelated_cases():
    summary = paired_summary([1, 10, 100], [0.5, 5, 50])
    assert summary["median_ratio"] == 0.5
    assert summary["descriptive_paired_bootstrap_95_interval"] == [0.5, 0.5]
    rows = []
    for block in range(3):
        for name, multiplier in zip(CONFIGURATIONS, (1, 0.5, 0.5, 0.25)):
            rows.append({"block": block, "configuration": name,
                         "update_seconds": (block + 1) * multiplier})
    result = summarize(rows)
    assert result["combined"]["median_ratio"] == 0.25
    assert result["multiplicative_interaction"]["median_ratio"] == 1.0
    with pytest.raises(RuntimeError, match="incomplete"):
        summarize(rows[:-1])


def test_full_fact_hash_distinguishes_equal_count_different_answers():
    assert fact_digest({atom("P", "a")}) != fact_digest({atom("P", "b")})
    assert fact_digest({atom("P", "a"), atom("P", "b")}) == fact_digest(
        {atom("P", "b"), atom("P", "a")})
    assert fact_digest({atom("P", "a")}) != fact_digest({atom("Q", "a")})


def test_predeclared_promotion_threshold_detects_overhead_and_missing_cases():
    cases = [{"case": case, "summary": {
        "adaptive-only": {"median_ratio": 0.9},
        "support-only": {"median_ratio": 0.8},
        "support-with-adaptive": {"median_ratio": 0.8},
    }} for case in build_cases()]
    assessment = promotion_assessment(cases)
    assert assessment["adaptive_threshold_met"]
    assert assessment["support_threshold_met"]
    next(item for item in cases if item["case"]["mode"] == "unsupported-cycle")["summary"][
        "support-only"]["median_ratio"] = 1.2
    assert not promotion_assessment(cases)["support_threshold_met"]
    with pytest.raises(RuntimeError, match="complete"):
        promotion_assessment(cases[:-1])


@pytest.mark.parametrize("relative", ["benchmarks/results.json", "benchmarks/replay-results.json",
                                     "benchmarks/baselines/b1254c4/results.json"])
def test_experiments_cannot_overwrite_frozen_or_recorded_benchmarks(relative):
    with pytest.raises(RuntimeError, match="overwrite"):
        protected_output(ROOT / relative)


def test_independent_ground_oracle_rejects_unimplemented_top_semantics():
    from dlp_reasoner.model import Atom
    with pytest.raises(RuntimeError, match="TOP"):
        finite_oracle(Program([Rule(atom("P", Var("x")), (Atom(TOP, (Var("x"),)),))]))
