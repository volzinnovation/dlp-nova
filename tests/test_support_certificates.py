"""Current-state certificates must be sound even when proof search is bounded."""
import random

import pytest

from dlp_reasoner.model import Atom, Rule, Skolem, TOP, Var
from dlp_reasoner.support import UnarySupport

X, Y = Var("x"), Var("y")


def fact(predicate, subject="a"):
    return Atom(predicate, (subject,))


def rule(head, *premises):
    return Rule(Atom(head, (X,)), tuple(Atom(p, (X,)) for p in premises))


def closure(rules, seeds):
    """Deliberately plain independent propositional fixed-point evaluator."""
    known = set(seeds)
    while True:
        following = {r.head.predicate for r in rules
                     if all(atom.predicate in known for atom in r.body)}
        if following <= known:
            return known
        known |= following


def test_cycle_requires_a_current_external_seed():
    rules = [rule("A", "B"), rule("B", "A"), rule("B", "Source")]
    supported = UnarySupport(rules, {fact("Source")}, {"a"})
    assert supported.proves(fact("A"))
    assert supported.proves(fact("B"))
    unsupported = UnarySupport(rules, set(), {"a"})
    assert not unsupported.proves(fact("A"))
    assert not unsupported.proves(fact("B"))


def test_conjunction_never_combines_different_subjects_and_deduplicates_premises():
    rules = [rule("Result", "A", "B", "B")]
    proofs = UnarySupport(rules, {fact("A"), fact("B", "b")}, {"a", "b"})
    assert not proofs.proves(fact("Result"))
    assert not proofs.proves(fact("Result", "b"))
    current = UnarySupport(rules, {fact("A"), fact("B")}, {"a"})
    assert current.proves(fact("Result"))


def test_equal_subject_signatures_reuse_one_proof_context():
    rules = [rule("A", "Seed"), rule("B", "A")]
    asserted = {fact("Seed", subject) for subject in range(100)}
    proofs = UnarySupport(rules, asserted, set(range(100)))
    assert all(proofs.proves(fact("B", subject)) for subject in range(100))
    assert proofs.stats["contexts"] == 1
    assert proofs.stats["cache_hits"] == 99
    assert proofs.stats["rule_visits"] == 2


def test_duplicate_source_labels_do_not_duplicate_certificate_work():
    first = rule("Result", "A", "B")
    second = Rule(first.head, tuple(reversed(first.body)), label="other-source")
    proofs = UnarySupport([first, second], {fact("A"), fact("B")}, {"a"})
    assert proofs.proves(fact("Result"))
    assert proofs.stats["rule_visits"] == 2


def test_rule_and_fact_transaction_uses_only_current_support():
    old_rules = [rule("Goal", "OldSource"), rule("Other", "Goal")]
    current_rules = [rule("Goal", "NewSource"), rule("Other", "Goal")]
    current_facts = {fact("NewSource")}
    current = UnarySupport(current_rules, current_facts, {"a"})
    assert current.proves(fact("Goal"))
    assert current.proves(fact("Other"))
    stale_rules = UnarySupport(old_rules, current_facts, {"a"})
    assert not stale_rules.proves(fact("Goal"))
    stale_facts = UnarySupport(current_rules, {fact("OldSource")}, {"a"})
    assert not stale_facts.proves(fact("Goal"))


def test_departed_domain_term_cannot_use_top_as_a_premise():
    rules = [rule("Universal", TOP)]
    proofs = UnarySupport(rules, set(), {"current"})
    assert proofs.proves(fact("Universal", "current"))
    assert not proofs.proves(fact("Universal", "departed"))


def test_outside_fragment_rules_do_not_create_certificates():
    rules = [
        Rule(fact("Ground"), (fact("Seed", X),)),
        Rule(fact("ConstantBody", X), (fact("Seed"), fact("Seed", X))),
        Rule(fact("OtherVariable", X), (fact("Seed", X), fact("Seed", Y))),
        Rule(fact("BinaryBody", X), (Atom("Edge", (X, Y)),)),
        Rule(fact("Witness", Skolem("f", (X,))), (fact("Seed", X),)),
        Rule(fact("EmptyBody")),
        Rule(None, (fact("Seed", X),)),
    ]
    proofs = UnarySupport(rules, {fact("Seed"), Atom("Edge", ("a", "a"))}, {"a"})
    assert not any(proofs.proves(fact(p)) for p in
                   ("Ground", "ConstantBody", "OtherVariable", "BinaryBody", "Witness", "EmptyBody"))
    assert not proofs.proves(Atom("Edge", ("a", "a")))


def test_context_cap_falls_back_and_keeps_cached_positive_proofs():
    rules = [rule("Goal", f"S{i}") for i in range(20)]
    asserted = {fact(f"S{i}", i) for i in range(20)}
    proofs = UnarySupport(rules, asserted, set(range(20)), max_contexts=3)
    assert all(proofs.proves(fact("Goal", i)) for i in range(3))
    assert not any(proofs.proves(fact("Goal", i)) for i in range(3, 20))
    assert proofs.proves(fact("Goal", 0))
    assert proofs.stats["contexts"] == 3
    assert proofs.stats["budget_misses"] == 17


def test_work_budget_retains_only_sound_partial_proofs():
    rules = [rule(f"C{i+1}", f"C{i}") for i in range(20)]
    proofs = UnarySupport(rules, {fact("C0")}, {"a"}, max_rule_visits=3)
    assert not proofs.proves(fact("C20"))
    assert proofs.proves(fact("C3"))
    assert not proofs.proves(fact("C4"))
    assert proofs.stats["rule_visits"] == 3
    assert proofs.stats["contexts"] == 1


@pytest.mark.parametrize("budget", [{"max_contexts": 0}, {"max_rule_visits": 0}])
def test_zero_budget_returns_unknown(budget):
    proofs = UnarySupport([rule("Goal", "Seed")], {fact("Seed")}, {"a"}, **budget)
    assert not proofs.proves(fact("Goal"))
    assert proofs.stats["contexts"] == 0
    assert proofs.stats["rule_visits"] == 0


@pytest.mark.parametrize("budget", [{"max_contexts": -1}, {"max_rule_visits": -1}])
def test_negative_budget_is_rejected(budget):
    with pytest.raises(ValueError, match="nonnegative"):
        UnarySupport([], set(), set(), **budget)


@pytest.mark.parametrize("seed", range(40))
def test_randomized_certificates_against_independent_least_model(seed):
    rng = random.Random(seed)
    predicates = list(range(9))
    rules = [rule(rng.choice(predicates), *rng.sample(predicates, rng.randint(1, 4)))
             for _ in range(30)]
    asserted = {fact(p, subject) for p in predicates for subject in range(4)
                if rng.random() < .25}
    subjects = set(range(4))
    snapshots = list(rules), set(asserted), set(subjects)
    proofs = UnarySupport(rules, asserted, subjects)
    bounded = UnarySupport(rules, asserted, subjects, max_rule_visits=15, max_contexts=2)
    heads = {r.head.predicate for r in rules}
    for subject in subjects:
        seeds = {f.predicate for f in asserted if f.args == (subject,)} | {TOP}
        expected = closure(rules, seeds)
        for predicate in predicates:
            query = fact(predicate, subject)
            assert proofs.proves(query) == (predicate in heads and predicate in expected)
            if bounded.proves(query):
                assert predicate in expected
    assert bounded.stats["rule_visits"] <= 15
    assert bounded.stats["contexts"] <= 2
    assert snapshots == (rules, asserted, subjects)
