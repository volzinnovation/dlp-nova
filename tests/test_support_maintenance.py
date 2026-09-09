"""Experimental support certificates preserve general DRed transaction semantics."""
from itertools import product
import random

import pytest

from dlp_reasoner.engine import Engine
from dlp_reasoner.model import Atom, EQ, TOP, Program, Rule, Skolem, Var

X, Y, Z = Var("x"), Var("y"), Var("z")


def atom(predicate, *terms):
    return Atom(predicate, terms)


def unary(head, *body):
    return Rule(atom(head, X), tuple(atom(p, X) for p in body))


def run(rules=(), facts=(), *, enabled=True, **options):
    result = Engine(Program(list(rules), set(facts)), **options)
    result._support_certificates_enabled = enabled
    return result.materialize()


def ordinary_facts(engine):
    return {fact for fact in engine.facts if fact.predicate != TOP}


def assert_matches_fresh(engine, rules, facts):
    fresh = run(rules, facts, enabled=False)
    assert engine.complete
    assert engine.asserted == set(facts)
    assert set(engine.rules) == set(rules)
    assert engine.facts == fresh.facts
    assert engine.terms == fresh.terms
    assert set(engine.violations) == set(fresh.violations)


def test_flag_switch_preserves_answers_and_changes_only_protection_work():
    feeder = unary("P", "Old")
    rules = [feeder, unary("P", "Other"), unary("Q", "P"), unary("P", "Q")]
    facts = {atom(p, subject) for subject in range(20) for p in ("Old", "Other")}
    optimized, baseline = run(rules, facts), run(rules, facts, enabled=False)
    for engine in (optimized, baseline):
        engine.update(remove_rules=[feeder])
        assert_matches_fresh(engine, rules[1:], facts)
        assert engine.stats["update_method"] == "dred-rules"
    assert optimized.stats["overdeleted_facts"] == 0
    assert baseline.stats["overdeleted_facts"] == 40
    assert optimized.stats["support_certified"] == 20
    assert optimized.stats["support_contexts"] == 1
    assert baseline.stats.get("support_certified", 0) == 0


def test_fact_retraction_preserves_alternative_support_then_removes_unsupported_cycle():
    rules = [unary("P", "Old"), unary("P", "Other"), unary("Q", "P"), unary("P", "Q")]
    facts = {atom("Old", "a"), atom("Other", "a")}
    engine = run(rules, facts)
    engine.update(remove=[atom("Old", "a")])
    assert engine.stats["overdeleted_facts"] == 1
    assert engine.stats["support_certified"] > 0
    assert_matches_fresh(engine, rules, {atom("Other", "a")})
    engine.update(remove=[atom("Other", "a")])
    assert engine.stats["support_certified"] == 0
    assert not ordinary_facts(engine)
    assert_matches_fresh(engine, rules, set())


def test_removed_rule_is_never_a_certificate_even_when_its_source_remains():
    feeder = unary("P", "Source")
    rules = [feeder, unary("Q", "P"), unary("P", "Q")]
    facts = {atom("Source", "a")}
    engine = run(rules, facts)
    engine.update(remove_rules=[feeder])
    assert ordinary_facts(engine) == facts
    assert engine.stats["support_certified"] == 0
    assert_matches_fresh(engine, rules[1:], facts)


def test_new_proof_through_new_intermediate_does_not_skip_new_downstream_conclusions():
    feeder = unary("P", "Old")
    old_rules = [feeder, unary("Q", "P"),
                 Rule(atom("Pair", X, Y), (atom("Q", X), atom("Link", X, Y)))]
    old_facts = {atom("Old", "a"), atom("Link", "a", "b")}
    engine = run(old_rules, old_facts)
    new_rules = [unary("Intermediate", "New"), unary("P", "Intermediate"),
                 Rule(atom("Result", Y), (atom("Q", X), atom("NewLink", X, Y)))]
    additions = {atom("New", "a"), atom("NewLink", "a", "c")}
    engine.update(add=additions, remove=[atom("Old", "a")],
                  add_rules=new_rules, remove_rules=[feeder])
    assert engine.stats["support_certified"] > 0
    assert atom("Intermediate", "a") in engine.facts
    assert atom("Result", "c") in engine.facts
    assert atom("Pair", "a", "b") in engine.facts
    assert_matches_fresh(engine, old_rules[1:] + new_rules,
                         (old_facts - {atom("Old", "a")}) | additions)


def test_shared_conjunction_certificate_respects_distinct_subject_premises():
    feeder = unary("P", "Old")
    rules = [feeder, unary("P", "A", "B"), unary("Q", "P")]
    facts = {atom("Old", "a"), atom("Old", "b"), atom("A", "a"),
             atom("B", "a"), atom("A", "b"), atom("B", "c")}
    engine = run(rules, facts)
    engine.update(remove_rules=[feeder])
    assert atom("Q", "a") in engine.facts
    assert atom("Q", "b") not in engine.facts
    assert_matches_fresh(engine, rules[1:], facts)


def test_binary_derived_support_remains_the_general_dred_responsibility():
    feeder = unary("P", "Old")
    projection = Rule(atom("P", X), (atom("Link", X, Y),))
    rules = [feeder, projection, unary("Q", "P")]
    facts = {atom("Old", "a"), atom("Link", "a", "b")}
    engine = run(rules, facts)
    engine.update(remove_rules=[feeder])
    assert engine.stats["support_certified"] == 0
    assert engine.stats["overdeleted_facts"] == 2
    assert engine.stats["rederived_facts"] == 2
    assert_matches_fresh(engine, rules[1:], facts)


def test_constraints_are_rechecked_for_retained_and_deleted_facts():
    feeder = unary("P", "Old")
    constraint = Rule(None, (atom("P", X), atom("Forbidden", X)), "forbidden")
    rules = [feeder, unary("P", "Other"), constraint]
    facts = {atom("Old", "a"), atom("Other", "a"), atom("Forbidden", "a")}
    engine = run(rules, facts)
    assert engine.violations
    engine.update(remove_rules=[feeder])
    assert engine.stats["support_certified"] > 0
    assert engine.violations
    assert_matches_fresh(engine, rules[1:], facts)
    engine.update(remove=[atom("Other", "a")])
    assert not engine.violations
    assert_matches_fresh(engine, rules[1:], facts - {atom("Other", "a")})


def test_added_and_removed_constraints_do_not_invalidate_oracle_support():
    feeder = unary("P", "Old")
    rules = [feeder, unary("P", "Other")]
    facts = {atom("Old", "a"), atom("Other", "a")}
    denial = Rule(None, (atom("P", X),), "no-p")
    engine = run(rules, facts)
    engine.update(remove_rules=[feeder], add_rules=[denial])
    assert engine.violations
    assert_matches_fresh(engine, [rules[1], denial], facts)
    engine.update(remove_rules=[denial])
    assert not engine.violations
    assert_matches_fresh(engine, [rules[1]], facts)


def test_domain_removal_does_not_certify_universal_fact_for_departed_term():
    rules = [unary("Universal", TOP), unary("Next", "Universal")]
    engine = run(rules, [atom("Anchor", "departed"), atom("Anchor", "kept")])
    engine.update(remove=[atom("Anchor", "departed")])
    assert "departed" not in engine.terms
    assert not any("departed" in f.args for f in engine.facts)
    assert atom("Next", "kept") in engine.facts
    assert_matches_fresh(engine, rules, [atom("Anchor", "kept")])


@pytest.mark.parametrize("budget", ["_support_max_contexts", "_support_max_rule_visits"])
def test_zero_proof_budget_retains_complete_general_dred_path(budget):
    feeder = unary("P", "Old")
    rules = [feeder, unary("P", "Other"), unary("Q", "P")]
    facts = {atom("Old", "a"), atom("Other", "a")}
    engine = run(rules, facts)
    setattr(engine, budget, 0)
    engine.update(remove_rules=[feeder])
    assert engine.stats["support_certified"] == 0
    assert engine.stats["overdeleted_facts"] == 2
    assert engine.stats["rederived_facts"] == 2
    assert_matches_fresh(engine, rules[1:], facts)


def test_partial_certificate_budget_cannot_preserve_unsupported_facts():
    feeder = unary("C0", "Old")
    rules = [feeder, unary("C0", "Other")] + [unary(f"C{i+1}", f"C{i}") for i in range(12)]
    facts = {atom("Old", s) for s in ("supported", "unsupported")} | {atom("Other", "supported")}
    engine = run(rules, facts)
    engine._support_max_contexts = 1
    engine._support_max_rule_visits = 2
    engine.update(remove_rules=[feeder])
    assert engine.stats["support_contexts"] <= 1
    assert engine.stats["support_rule_visits"] <= 2
    assert_matches_fresh(engine, rules[1:], facts)


def test_equality_retraction_retains_rematerialization_fallback():
    feeder = unary("P", "Old")
    rules = [feeder, unary("Q", "P")]
    facts = {atom("Old", "a"), atom("Old", "b"), atom(EQ, "a", "b")}
    engine = run(rules, facts)
    engine.update(remove=[atom(EQ, "a", "b")], remove_rules=[feeder])
    assert engine.stats["update_method"] == "rematerialize-rules"
    assert engine.stats.get("support_queries", 0) == 0
    assert engine.normalize("a") != engine.normalize("b")
    assert_matches_fresh(engine, rules[1:], facts - {atom(EQ, "a", "b")})


def test_witness_retraction_retains_rematerialization_fallback():
    witness = Rule(atom("Witness", Skolem("f", (X,))), (atom("Seed", X),))
    rules = [witness, unary("Result", "Witness")]
    engine = run(rules, [atom("Seed", "a")])
    engine.update(remove=[atom("Seed", "a")])
    assert engine.stats["update_method"] == "rematerialize"
    assert engine.stats.get("support_queries", 0) == 0
    assert_matches_fresh(engine, rules, set())


def test_interrupted_overdeletion_never_publishes_unsupported_old_facts():
    feeder = unary("C0", "Old")
    rules = [feeder] + [unary(f"C{i+1}", f"C{i}") for i in range(8)]
    facts = {atom("Old", "a")}
    engine = run(rules, facts)
    engine.max_rounds = 1
    engine.update(remove_rules=[feeder])
    assert engine.stats["update_method"] == "rematerialize-rules-after-dred-limit"
    assert ordinary_facts(engine) == facts
    assert_matches_fresh(engine, rules[1:], facts)


def test_incomplete_witness_old_state_rebuilds_to_sound_current_prefix():
    looping = Rule(atom("Seed", Skolem("f", (X,))), (atom("Seed", X),))
    engine = run([looping], [atom("Seed", "a")], max_depth=2)
    assert not engine.complete
    engine.update(remove=[atom("Seed", "a")], add=[atom("Seed", "b")])
    assert engine.stats["update_method"] == "rematerialize"
    assert not engine.complete
    assert engine.stats.get("support_queries", 0) == 0
    fresh = run([looping], [atom("Seed", "b")], enabled=False, max_depth=4)
    assert engine.facts <= fresh.facts


def independent_closure(rules, facts):
    """Ground and saturate the finite positive program without engine internals."""
    templates = [*facts, *(a for r in rules for a in (*r.body, r.head))]
    domain = {t for a in templates for t in a.args if not isinstance(t, Var)}
    ground_rules = []
    for rule in rules:
        variables = sorted({t for a in (*rule.body, rule.head) for t in a.args
                            if isinstance(t, Var)}, key=lambda variable: variable.name)
        for terms in product(domain, repeat=len(variables)):
            binding = dict(zip(variables, terms))

            def substitute(a):
                return Atom(a.predicate, tuple(binding.get(t, t) for t in a.args))

            ground_rules.append((substitute(rule.head), {substitute(a) for a in rule.body}))
    known = set(facts)
    while True:
        following = {head for head, body in ground_rules if body <= known}
        if following <= known:
            return known
        known |= following


@pytest.mark.parametrize("seed", range(20))
@pytest.mark.parametrize("bounded", [False, True])
def test_random_atomic_transactions_match_independent_grounding(seed, bounded):
    rng = random.Random(seed)
    domain = ["a", "b", "c"]
    candidates = [unary(rng.choice(range(6)), *rng.sample(range(6), rng.randint(1, 3)))
                  for _ in range(15)] + [
        Rule(atom("Reach", X, Y), (atom("Edge", X, Y),)),
        Rule(atom("Reach", X, Z), (atom("Reach", X, Y), atom("Edge", Y, Z))),
        Rule(atom(0, Y), (atom(1, X), atom("Reach", X, Y))),
        Rule(atom(2, X), (atom("Reach", X, X),)),
        Rule(atom(3, "a")),
        Rule(atom("Flag"), (atom(4, "a"),)),
        Rule(atom(5, "b"), (atom("Flag"),)),
    ]
    universe = [atom(p, s) for p in range(6) for s in domain]
    universe += [atom("Edge", s, o) for s in domain for o in domain]
    rules, facts = set(rng.sample(candidates, 10)), set(rng.sample(universe, 10))
    engine = run(rules, facts)
    if bounded:
        engine._support_max_contexts = 2
        engine._support_max_rule_visits = 10
    for _ in range(25):
        add = set(rng.sample(universe, rng.randrange(4)))
        remove = set(rng.sample(universe, rng.randrange(4)))
        add_rules = set(rng.sample(candidates, rng.randrange(4)))
        remove_rules = set(rng.sample(candidates, rng.randrange(4)))
        facts, rules = (facts - remove) | add, (rules - remove_rules) | add_rules
        engine.update(add, remove, add_rules=add_rules, remove_rules=remove_rules)
        assert_matches_fresh(engine, rules, facts)
        assert ordinary_facts(engine) == independent_closure(rules, facts)
        if bounded:
            assert engine.stats.get("support_contexts", 0) <= 2
            assert engine.stats.get("support_rule_visits", 0) <= 10
