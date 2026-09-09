"""Falsify adaptive-plan algebra independently of wall-clock performance."""

from itertools import product
import random

import pytest

from dlp_reasoner.engine import Engine, _Index, _MISSING
from dlp_reasoner.model import Atom, EQ, Program, Rule, Var


x = Var("x")


class AdaptiveEngine(Engine):
    """Test the candidate independently of the production adoption decision."""

    _unary_strategy = "adaptive"


class UnionFirstEngine(Engine):
    """Execution ablation retaining the fixed plan from commit 8ce254f."""

    _unary_strategy = "union-first"


def atom(predicate, value):
    return Atom(predicate, (value,))


def body_rule(width):
    return Rule(atom("answer", x), tuple(atom(f"p{i}", x) for i in range(width)))


def solve(relations, deltas, *, initial=None, engine_type=AdaptiveEngine):
    rule = body_rule(len(relations))
    facts = {atom(f"p{i}", value) for i, values in enumerate(relations) for value in values}
    engine = engine_type(Program([rule], set())).materialize()
    # Isolate the body evaluator and expose exactly the supplied I and D sets.
    engine._index = _Index(facts)
    delta = _Index(atom(f"p{i}", value) for i, values in enumerate(deltas) for value in values)
    answers = {binding[x] for binding in engine._solutions(rule, delta, initial=initial)}
    return answers, engine.stats


@pytest.mark.parametrize("width,universe", [(2, 3), (3, 2)])
def test_exhaustive_small_relations_and_all_subset_deltas(width, universe):
    # Per term: absent, old, or delta. This covers every D_i subset I_i,
    # including dense/sparse/empty deltas and all correlations among columns.
    for states in product(range(3), repeat=width * universe):
        relations, deltas = [], []
        for i in range(width):
            relation = {j for j in range(universe) if states[i * universe + j]}
            delta = {j for j in range(universe) if states[i * universe + j] == 2}
            relations.append(relation)
            deltas.append(delta)
        expected = set.intersection(*relations) & set.union(*deltas)
        adaptive, _ = solve(relations, deltas)
        fixed, _ = solve(relations, deltas, engine_type=UnionFirstEngine)
        assert adaptive == fixed == expected


def test_full_delta_witness_avoids_union_even_with_many_duplicate_delta_values():
    relations = [set(range(100)) for _ in range(32)]
    adaptive, stats = solve(relations, relations)
    fixed, fixed_stats = solve(relations, relations, engine_type=UnionFirstEngine)
    assert adaptive == fixed == set(range(100))
    assert stats["unary_full_delta_shortcuts"] == 1
    assert stats["unary_delta_union_input_rows"] == 0
    assert fixed_stats["unary_delta_union_input_rows"] == 3200
    assert stats["unary_intersections"] == 31


def test_dense_deltas_intersect_tiny_full_relation_before_delta_filtering():
    relations = [{0, 1, 2}, set(range(1000)), set(range(1000))]
    deltas = [set(), set(range(1, 500)), set(range(2, 700))]
    answers, stats = solve(relations, deltas)
    assert answers == {1, 2}  # Existing match 0 must not be visited again.
    assert stats["unary_full_intersection_plans"] == 1
    assert stats["unary_delta_union_input_rows"] == 0
    assert stats["unary_delta_filter_input_rows"] == 6


def test_disjoint_delta_populations_still_require_every_full_body_relation():
    relations = [{0, 1}, {0, *range(2, 100)}, {1, *range(2, 100)}]
    deltas = [set(), set(range(2, 99)), set(range(2, 99))]
    answers, stats = solve(relations, deltas)
    assert not answers
    assert stats["unary_full_intersection_plans"] == 1
    assert stats["unary_delta_filter_input_rows"] == 0


def test_sparse_disjoint_deltas_form_small_union_before_large_intersection():
    relations = [set(range(1000)) for _ in range(32)]
    deltas = [{998}, {999}, *(set() for _ in range(30))]
    answers, stats = solve(relations, deltas)
    assert answers == {998, 999}
    assert stats["unary_delta_union_input_rows"] == 2
    assert stats["unary_full_intersection_plans"] == 0
    assert stats["unary_intersection_input_rows"] == 64


def test_many_correlated_singleton_deltas_do_not_force_large_full_intersection():
    # Delta input volume alone exceeds the smallest full set, but the union
    # contains only one value. A threshold ignoring rule width picks badly.
    relations = [set(range(32)) for _ in range(64)]
    deltas = [{31} for _ in range(64)]
    answers, stats = solve(relations, deltas)
    assert answers == {31}
    assert stats["unary_delta_union_input_rows"] == 64
    assert stats["unary_full_intersection_plans"] == 0
    assert stats["unary_intersection_input_rows"] == 64


def test_repeated_predicate_preserves_coalesced_and_individual_delta_variants():
    rule = Rule(atom("answer", x), (atom("p", x), atom("p", x), atom("q", x)))
    facts = {atom(predicate, value) for predicate in ("p", "q") for value in ("a", "b")}
    engine = AdaptiveEngine(Program([rule], facts)).materialize()
    delta = _Index([atom("p", "b")])
    for position in (None, 0, 1):
        assert list(engine._solutions(rule, delta, position)) == [{x: "b"}]
    assert list(engine._solutions(rule, delta, initial={x: "a"})) == []
    extra = Var("unrelated")
    assert list(engine._solutions(rule, delta, initial={x: "b", extra: "kept"})) == [
        {x: "b", extra: "kept"}]


def test_single_delta_uses_its_existing_set_without_union_copy():
    relations = [set(range(100)) for _ in range(12)]
    deltas = [{99}, *(set() for _ in range(11))]
    answers, stats = solve(relations, deltas)
    assert answers == {99}
    assert stats["unary_delta_union_input_rows"] == 0
    assert stats["unary_intersection_input_rows"] == 12


@pytest.mark.parametrize("value,expected", [(0, set()), (1, {1}), (1000, set())])
def test_bound_variable_checks_membership_without_union_or_intersection(value, expected):
    relations = [set(range(1000)) for _ in range(32)]
    deltas = [{1}, *(set() for _ in range(31))]
    answers, stats = solve(relations, deltas, initial={x: value})
    assert answers == expected
    assert stats["unary_delta_union_input_rows"] == 0
    assert stats["unary_intersections"] == 0
    assert stats["unary_bound_membership_tests"] <= 64


def test_adaptive_plans_and_fixed_ablation_agree_across_mixed_transactions():
    rng = random.Random(42103)
    selected = body_rule(4)
    alternate = Rule(atom("answer", x), (atom("other", x),))
    rules = [selected, alternate, Rule(atom("cycle", x), (atom("answer", x),)),
             Rule(atom("answer", x), (atom("cycle", x),))]
    universe = {atom(f"p{i}", j) for i in range(4) for j in range(9)}
    universe.update(atom("other", j) for j in range(9))
    ordered = sorted(universe, key=repr)
    facts = set(ordered[::2])
    adaptive = AdaptiveEngine(Program(rules, facts)).materialize()
    fixed = UnionFirstEngine(Program(rules, facts)).materialize()
    for step in range(30):
        additions = set(rng.sample(ordered, rng.randrange(1, 9)))
        removals = set(rng.sample(ordered, rng.randrange(1, 9)))
        add_rules, remove_rules = [], []
        if step % 5 == 0:
            if alternate in rules:
                remove_rules = [alternate]
                rules.remove(alternate)
            else:
                add_rules = [alternate]
                rules.append(alternate)
        facts = (facts - removals) | additions
        for engine in (adaptive, fixed):
            engine.update(add=additions, remove=removals,
                          add_rules=add_rules, remove_rules=remove_rules)
        oracle = Engine(Program(list(rules), facts), strategy="naive").materialize()
        assert adaptive.complete and fixed.complete and oracle.complete
        assert adaptive.facts == fixed.facts == oracle.facts


def test_delta_subset_invariant_survives_equality_reindex_and_class_splitting():
    rule = body_rule(3)
    facts = {atom("p0", "a"), atom("p1", "b"), atom("p2", "c")}
    equalities = {Atom(EQ, ("a", "b")), Atom(EQ, ("b", "c"))}
    engine = AdaptiveEngine(Program([rule], facts)).materialize()
    engine.update(add=equalities)
    assert atom("answer", engine.normalize("a")) in engine.facts
    assert engine.facts == UnionFirstEngine(Program([rule], facts | equalities)).materialize().facts
    engine.update(remove=equalities)
    assert engine.facts == Engine(Program([rule], facts), strategy="naive").materialize().facts


@pytest.mark.parametrize("arity", [0, 1, 2, 3, 4])
def test_index_arity_fast_paths_match_exact_selection_after_candidate_filtering(arity):
    # None and False must be treated as bound terms, never as missing values.
    terms = (None, False, "a", "absent")
    rows = {row for row in product(terms[:-1], repeat=arity)
            if arity == 0 or row.count("a") % 2 == 0}
    index = _Index(Atom(None, row) for row in rows)
    for values in product((*terms, _MISSING), repeat=arity):
        expected = {row for row in rows
                    if all(value is _MISSING or value == term
                           for value, term in zip(values, row))}
        candidates = index.lookup(None, values)
        actual = {row for row in candidates
                  if all(value is _MISSING or value == term
                         for value, term in zip(values, row))}
        assert actual == expected
        if all(value is not _MISSING for value in values):
            assert len(candidates) <= 1
        assert not index.lookup("absent", values)
