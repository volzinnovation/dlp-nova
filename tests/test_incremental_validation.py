"""An optional insertion fast path preserves validation and transaction semantics."""

import random

import pytest
from rdflib import Literal
from rdflib.namespace import XSD

from benchmarks.research import finite_oracle
from dlp_reasoner.engine import Engine
from dlp_reasoner.model import Atom, EQ, NEQ, TOP, ProfileError, Program, Rule, Skolem, Var

X, Y, Z = Var("x"), Var("y"), Var("z")


def atom(predicate, *terms):
    return Atom(predicate, terms)


class FullValidationEngine(Engine):
    _incremental_validation_enabled = False


class ReusingEngine(Engine):
    _incremental_validation_enabled = True

    def _validate(self, rules, facts, **kwargs):
        self.validation_calls = getattr(self, "validation_calls", [])
        self.validation_calls.append((len(rules), len(facts), bool(kwargs)))
        return super()._validate(rules, facts, **kwargs)


def run(rules=(), facts=(), engine_type=ReusingEngine, **options):
    return engine_type(Program(list(rules), set(facts)), **options).materialize()


def assert_same_state(left, right):
    assert left.asserted == right.asserted
    assert left.rules == right.rules
    assert left.facts == right.facts
    assert left.complete == right.complete
    assert set(left.violations) == set(right.violations)
    assert left.program.facts == right.program.facts
    assert left.program.rules == right.program.rules


def test_pure_insertion_validates_delta_and_reuses_data_independent_plans():
    rules = [Rule(atom("q", X), (atom("p", X), atom("r", X)))]
    old = {atom(p, i) for p in ("p", "r") for i in range(20)}
    engine = run(rules, old)
    plans, dependents = engine._unary_plans, engine._dependents
    engine.update(add=[atom("p", 20), atom("r", 20), atom("p", 0)])
    assert engine.validation_calls[-1] == (0, 2, True)
    assert engine._unary_plans is plans
    assert engine._dependents is dependents
    assert atom("q", 20) in engine.facts
    assert_same_state(engine, run(rules, old | {atom("p", 20), atom("r", 20)}, FullValidationEngine))


@pytest.mark.parametrize("add", [[], [atom("p", "a")]])
def test_empty_and_already_asserted_insertions_preserve_state(add):
    engine = run(facts=[atom("p", "a")])
    old = set(engine.facts)
    plans = engine._unary_plans
    engine.update(add=add)
    assert engine.validation_calls[-1] == (0, 0, True)
    assert engine.facts == old
    assert engine._unary_plans is plans
    assert engine.stats["rounds"] == 0


@pytest.mark.parametrize("bad", [atom("p", "a", "b"), atom("p", X),
                                  atom(EQ, "a"), atom(Var("predicate"), "a")])
def test_invalid_insertion_preserves_assertions_rules_stats_and_validation_cache(bad):
    engine = run(facts=[atom("p", "a")])
    before = (engine.asserted, engine.rules, engine.facts.copy(), engine.stats.copy(),
              engine._validation_snapshot, engine._unary_plans, engine._dependents)
    with pytest.raises(ProfileError):
        engine.update(add=[atom("new", "b"), bad])
    assert engine.asserted is before[0]
    assert engine.rules is before[1]
    assert engine.facts == before[2]
    assert engine.stats == before[3]
    assert engine._validation_snapshot is before[4]
    assert engine._unary_plans is before[5]
    assert engine._dependents is before[6]
    # A partially checked insertion must not reserve the new predicate's arity.
    engine.update(add=[atom("new", "a", "b")])
    assert atom("new", "a", "b") in engine.facts


def test_new_predicate_arity_is_checked_across_one_batch_and_later_insertions():
    engine = run()
    with pytest.raises(ProfileError, match="arity"):
        engine.update(add=[atom("fresh", "a"), atom("fresh", "a", "b")])
    engine.update(add=[atom("fresh", "a", "b")])
    with pytest.raises(ProfileError, match="arity"):
        engine.update(add=[atom("fresh", "a")])


def test_rules_pin_arity_even_without_any_current_facts():
    engine = run([Rule(atom("q", X), (atom("p", X),))])
    with pytest.raises(ProfileError, match="arity"):
        engine.update(add=[atom("p", "a", "b")])


def test_deletion_rebuilds_arity_certificate_before_subsequent_insertions():
    engine = run(facts=[atom("p", "a")])
    engine.update(remove=[atom("p", "a")], add=[atom("p", "a", "b")])
    assert engine.validation_calls[-1] == (0, 1, False)
    engine.update(add=[atom("p", "b", "c")])
    assert engine.validation_calls[-1] == (0, 1, True)
    with pytest.raises(ProfileError, match="arity"):
        engine.update(add=[atom("p", "a")])
    assert_same_state(engine, run(facts=[atom("p", "a", "b"), atom("p", "b", "c")],
                                  engine_type=FullValidationEngine))


def test_rule_insertions_validate_delta_and_submitted_noop_removals_validate_all():
    engine = run(facts=[atom("p", "a")])
    rule = Rule(atom("q", X), (atom("p", X),))
    engine.update(add_rules=[rule])
    assert engine.validation_calls[-1] == (1, 0, True)
    engine.update(remove=[atom("p", "absent")])
    assert engine.validation_calls[-1] == (1, 1, False)
    engine.update(add=[atom("p", "b")])
    assert engine.validation_calls[-1] == (0, 1, True)
    assert atom("q", "b") in engine.facts


def test_rule_insertions_rebuild_plans_but_duplicate_rules_reuse_them():
    engine = run(facts=[atom("p", "a")])
    rule = Rule(atom("q", X), (atom("p", X),))
    old_plans = engine._unary_plans
    engine.update(add_rules=[rule, rule], add=[atom("p", "b")])
    assert engine.validation_calls[-1] == (1, 1, True)
    assert engine.rules == [rule]
    assert engine._unary_plans is not old_plans
    assert atom("q", "a") in engine.facts and atom("q", "b") in engine.facts
    new_plans = engine._unary_plans
    engine.update(add_rules=[rule, rule])
    assert engine.validation_calls[-1] == (0, 0, True)
    assert engine._unary_plans is new_plans
    assert_same_state(engine, run([rule], engine.asserted, FullValidationEngine))


@pytest.mark.parametrize("rule", [
    Rule(atom("unsafe", X)),
    Rule(atom("q", X), (atom("p", X, Y),)),
    Rule(atom("q", X), (atom(EQ, X, Y),)),
    Rule(atom("q", X), (atom("new", X, Y),)),
])
def test_invalid_new_rules_are_atomic_with_joint_fact_rule_arity_checks(rule):
    engine = run(facts=[atom("p", "a")])
    before = (engine.asserted, engine.rules, engine.facts.copy(), engine.stats.copy(),
              engine._validation_snapshot, engine._unary_plans)
    with pytest.raises(ProfileError):
        engine.update(add_rules=[rule], add=[atom("new", "b")])
    assert engine.asserted is before[0] and engine.rules is before[1]
    assert engine.facts == before[2] and engine.stats == before[3]
    assert engine._validation_snapshot is before[4]
    assert engine._unary_plans is before[5]
    engine.update(add=[atom("new", "b", "c")])
    assert atom("new", "b", "c") in engine.facts


def test_new_rules_check_joint_arities_and_removal_releases_old_arities():
    engine = run()
    first = Rule(atom("q", X), (atom("p", X),))
    second = Rule(atom("r", X), (atom("p", X, Y),))
    with pytest.raises(ProfileError, match="arity"):
        engine.update(add_rules=[first, second])
    engine.update(add_rules=[first])
    engine.update(remove_rules=[first], add_rules=[second])
    assert engine.validation_calls[-1] == (1, 0, False)
    engine.update(add=[atom("p", "a", "b")])
    assert atom("r", "a") in engine.facts


def test_monotone_rule_insertion_seeds_only_new_rule_constants(monkeypatch):
    old_rules = [Rule(atom("seen", X), (atom(TOP, X),))]
    optimized = run(old_rules, [atom("p", "a")])
    baseline = run(old_rules, [atom("p", "a")], FullValidationEngine)
    # These include a ground function, constants under a nonground function,
    # a body-only constant, a fact-like rule, and a new asserted constant.
    ground = Skolem("ground", ("inside",))
    inserted = [
        Rule(atom("ground_head", ground)),
        Rule(atom("new_witness", Skolem("mixed", (X, "nested"))), (atom("p", X),)),
        Rule(atom("unused_head", X), (atom("absent", X, "body_only"),)),
        Rule(atom("constant_head", "head_only")),
    ]

    def fail_full_domain_scan():
        pytest.fail("Monotone insertion rescanned the existing domain")

    monkeypatch.setattr(optimized, "_domain_constants", fail_full_domain_scan)
    for engine in (optimized, baseline):
        engine.update(add_rules=inserted, add=[atom("p", "new_assertion")])
    assert_same_state(optimized, baseline)
    assert optimized.terms == baseline.terms
    for term in (ground, "inside", "nested", "body_only", "head_only", "new_assertion"):
        assert atom("seen", term) in optimized.facts


def test_new_rules_preserve_nonempty_domain_and_equality_literal_registration():
    old_rules = [Rule(atom("seen", X), (atom(TOP, X),))]
    optimized, baseline = run(old_rules), run(old_rules, engine_type=FullValidationEngine)
    assert len(optimized.terms) == 1
    new_rules = [
        Rule(atom("q", Literal("1", datatype=XSD.integer))),
        Rule(atom("r", Literal("1.0", datatype=XSD.decimal))),
        Rule(atom("joined", X), (atom("q", X), atom("r", X))),
        Rule(atom("all", X), (atom(TOP, X),)),
    ]
    for engine in (optimized, baseline):
        engine.update(add_rules=new_rules)
    assert_same_state(optimized, baseline)
    assert optimized.terms == baseline.terms
    assert len(optimized._index.rows["joined"]) == 1
    assert optimized._index.rows["all"] == optimized._index.rows[TOP]


def test_new_equality_rule_preserves_reindexing_and_violation_detection():
    facts = [atom("p", "a"), atom("r", "b"), atom(NEQ, "a", "b")]
    old_rules = [Rule(atom("joined", X), (atom("p", X), atom("r", X)))]
    optimized, baseline = run(old_rules, facts), run(old_rules, facts, FullValidationEngine)
    equality_rule = Rule(atom(EQ, X, Y), (atom("p", X), atom("r", Y)))
    for engine in (optimized, baseline):
        engine.update(add_rules=[equality_rule])
    assert_same_state(optimized, baseline)
    assert optimized.violations
    assert optimized._index.rows["joined"]


def test_direct_public_container_mutation_cannot_reuse_stale_validation():
    engine = run(facts=[atom("p", "a")])
    engine.asserted.add(atom("p", "a", "b"))
    with pytest.raises(ProfileError, match="arity"):
        engine.update(add=[atom("unrelated", "a")])
    assert engine.validation_calls[-1][2] is False
    assert atom("unrelated", "a") not in engine.asserted
    engine.asserted.remove(atom("p", "a", "b"))
    engine.rules.append(Rule(atom("unsafe", X)))
    with pytest.raises(ProfileError, match="Unsafe"):
        engine.update(add=[atom("unrelated", "a")])
    assert engine.validation_calls[-1][2] is False


def test_explicit_disabled_and_runtime_enable_bootstraps_full_validation():
    engine = run(facts=[atom("p", "a")], engine_type=FullValidationEngine)
    assert not engine._incremental_validation_enabled
    assert engine._validation_snapshot is None
    engine._incremental_validation_enabled = True
    engine.update(add=[atom("p", "b")])
    assert engine._validation_snapshot is not None
    plans = engine._unary_plans
    engine.update(add=[atom("p", "c")])
    assert engine._unary_plans is plans
    engine._incremental_validation_enabled = False
    engine.update(add=[atom("p", "d")])
    assert engine._validation_snapshot is None


@pytest.mark.parametrize("facts,add", [
    ([atom("p", "a"), atom("r", "b")], [atom(EQ, "a", "b")]),
    ([atom("p", Literal("1", datatype=XSD.integer))],
     [atom("r", Literal("1.0", datatype=XSD.decimal))]),
    ([atom("p", "a"), atom(NEQ, "a", "b")], [atom(EQ, "a", "b")]),
])
def test_equality_datatype_and_consistency_paths_are_unchanged(facts, add):
    rules = [Rule(atom("q", X), (atom("p", X), atom("r", X)))]
    optimized, baseline = run(rules, facts), run(rules, facts, FullValidationEngine)
    optimized.update(add=add)
    baseline.update(add=add)
    assert optimized.validation_calls[-1][2] is True
    assert_same_state(optimized, baseline)


def test_incomplete_materialization_keeps_rebuild_policy():
    recursive = Rule(atom("p", Skolem("f", (X,))), (atom("p", X),))
    optimized = run([recursive], [atom("p", "a")], max_depth=1)
    baseline = run([recursive], [atom("p", "a")], FullValidationEngine, max_depth=1)
    assert not optimized.complete
    for engine in (optimized, baseline):
        engine.update(add=[atom("p", "b")])
        assert engine.stats["update_method"] == "rematerialize"
        assert not engine.complete
    assert_same_state(optimized, baseline)


@pytest.mark.parametrize("seed", range(20))
def test_random_insertion_batches_match_independent_finite_grounding(seed):
    rng = random.Random(seed)
    rules = [Rule(atom(rng.randrange(5), X),
                  tuple(atom(p, X) for p in rng.sample(range(5), rng.randrange(1, 4))))
             for _ in range(10)] + [
        Rule(atom("reach", X, Y), (atom("edge", X, Y),)),
        Rule(atom("reach", X, Z), (atom("reach", X, Y), atom("edge", Y, Z))),
        Rule(atom(0, Y), (atom(1, X), atom("reach", X, Y))),
    ]
    universe = [atom(p, term) for p in range(5) for term in "abc"]
    universe += [atom("edge", left, right) for left in "abc" for right in "abc"]
    facts = set(rng.sample(universe, 3))
    engine = run(rules, facts)
    for _ in range(15):
        batch = set(rng.sample(universe, rng.randrange(5)))
        facts |= batch
        engine.update(add=batch)
        assert engine.asserted == facts
        assert engine.complete
        actual = {fact for fact in engine.facts if fact.predicate != TOP}
        assert actual == finite_oracle(Program(rules, facts))
        assert_same_state(engine, run(rules, facts, FullValidationEngine))


@pytest.mark.parametrize("seed", range(10))
def test_random_joint_rule_fact_insertions_match_independent_finite_grounding(seed):
    rng = random.Random(seed)
    candidates = [Rule(atom(rng.randrange(5), X),
                       tuple(atom(p, X) for p in rng.sample(range(5), rng.randrange(1, 4))))
                  for _ in range(15)] + [
        Rule(atom("reach", X, Y), (atom("edge", X, Y),)),
        Rule(atom("reach", X, Z), (atom("reach", X, Y), atom("edge", Y, Z))),
        Rule(atom(0, Y), (atom(1, X), atom("reach", X, Y))),
    ]
    universe = [atom(p, term) for p in range(5) for term in "abc"]
    universe += [atom("edge", left, right) for left in "abc" for right in "abc"]
    facts, rules = set(), []
    engine = run()
    for _ in range(12):
        batch = set(rng.sample(universe, rng.randrange(5)))
        rule_batch = rng.sample(candidates, rng.randrange(4))
        facts |= batch
        rules = list(dict.fromkeys(rules + rule_batch))
        engine.update(add=batch, add_rules=rule_batch)
        assert engine.complete
        actual = {fact for fact in engine.facts if fact.predicate != TOP}
        assert actual == finite_oracle(Program(rules, facts))
        assert_same_state(engine, run(rules, facts, FullValidationEngine))
