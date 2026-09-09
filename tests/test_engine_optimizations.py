"""Execution-plan semantics and work counters, independent of wall-clock noise."""

import pytest
from rdflib import URIRef

from dlp_reasoner.engine import Engine, _Index, _MISSING
from dlp_reasoner.model import Atom, EQ, NEQ, TOP, Program, Rule, Skolem, Var


x, y = Var("x"), Var("y")
a, b, c = (URIRef(f"urn:optimization:{letter}") for letter in "abc")


def atom(predicate, *args):
    return Atom(predicate, args)


def execute(rules, facts, strategy="semi-naive", **options):
    return Engine(Program(list(rules), set(facts)), strategy=strategy, **options).materialize()


def test_fully_bound_index_uses_exact_membership_instead_of_a_skewed_column_bucket():
    facts = [atom("r", i // 20, i % 20, i) for i in range(200)]
    index = _Index(facts)
    assert index.lookup("r", (3, 7, 67)) == ((3, 7, 67),)
    # Each individual column has matching rows, but their conjunction does not.
    assert index.lookup("r", (3, 7, 68)) == ()
    assert len(index.lookup("r", (3, _MISSING, _MISSING))) == 20
    assert index.lookup("absent", (a,)) == ()
    index.add(atom("flag"))
    assert index.lookup("flag", ()) == ((),)


def test_long_unary_conjunction_uses_one_delta_plan_and_preserves_naive_reference():
    width, population = 32, 80
    rule = Rule(atom("selected", x), tuple(atom(f"p{i}", x) for i in range(width)))
    facts = {atom(f"p{i}", URIRef(f"urn:member:{j}"))
             for i in range(width) for j in range(population)
             if j % 4 != 0 or i != width - 1}
    fast = execute([rule], facts)
    naive = execute([rule], facts, strategy="naive")
    expected = {atom("selected", URIRef(f"urn:member:{j}"))
                for j in range(population) if j % 4 != 0}
    assert {fact for fact in fast.facts if fact.predicate == "selected"} == expected
    assert fast.facts == naive.facts
    assert fast.stats["rule_evaluations"] == 1
    assert fast.stats["body_matches"] == len(expected)
    assert fast.stats["candidate_rows"] == len(expected)
    assert fast.stats["coalesced_delta_variants"] == width - 1
    assert fast.stats["unary_intersections"] == width
    assert naive.stats["unary_plan_evaluations"] == 0
    assert naive.stats["coalesced_delta_variants"] == 0
    assert naive.stats["candidate_rows"] >= width * len(expected)


def test_unary_incremental_delta_union_does_not_revisit_old_bindings():
    rule = Rule(atom("selected", x), (atom("p", x), atom("q", x)))
    engine = execute([rule], [atom("p", a), atom("q", a), atom("p", b)])
    engine.update(add=[atom("q", b)])
    assert atom("selected", b) in engine.facts
    assert engine.stats["body_matches"] == 1
    engine.update(add=[atom("p", c), atom("q", c)])
    assert atom("selected", c) in engine.facts
    assert engine.stats["body_matches"] == 1
    assert engine.stats["coalesced_delta_variants"] == 1


def test_repeated_unary_atoms_and_initial_bindings():
    rule = Rule(atom("selected", x), (atom("p", x), atom("p", x), atom("q", x)))
    engine = execute([rule], [atom("p", a), atom("q", a), atom("p", b), atom("q", b)])
    assert list(engine._solutions(rule, initial={x: a})) == [{x: a}]
    assert list(engine._solutions(rule, initial={x: c})) == []
    assert engine.facts == execute([rule], engine.asserted, strategy="naive").facts


def test_unary_plan_supports_general_hashable_predicates():
    rule = Rule(atom("selected", x), (atom(None, x), atom("q", x)))
    engine = execute([rule], [atom(None, a), atom("q", a)])
    assert atom("selected", a) in engine.facts
    assert list(engine._solutions(rule)) == [{x: a}]


@pytest.mark.parametrize("rule,facts", [
    (Rule(atom("pairs", x, y), (atom("p", x), atom("q", y))),
     [atom("p", a), atom("p", b), atom("q", c)]),
    (Rule(atom("selected", x), (atom("p", a), atom("q", x))),
     [atom("p", a), atom("q", b)]),
    (Rule(atom("selected", x), (atom("p", x), atom("q", x), atom(EQ, x, a))),
     [atom("p", a), atom("q", b), atom(EQ, a, b)]),
    (Rule(atom("different", x, y), (atom("p", x), atom("q", y), atom(NEQ, x, y))),
     [atom("p", a), atom("q", b), atom(NEQ, a, b)]),
])
def test_non_unary_join_shapes_keep_generic_solver(rule, facts):
    fast = execute([rule], facts)
    naive = execute([rule], facts, strategy="naive")
    assert fast.facts == naive.facts
    assert fast.stats["unary_plan_evaluations"] == 0


def test_unary_ground_heads_constraints_and_top_keep_binding_semantics():
    rules = [Rule(atom("ground", c), (atom("p", x), atom(TOP, x))),
             Rule(None, (atom("p", x), atom("q", x)), "overlap")]
    facts = [atom("p", a), atom("q", a), atom("p", b)]
    fast = execute(rules, facts)
    naive = execute(rules, facts, strategy="naive")
    assert fast.facts == naive.facts
    assert fast.violations == naive.violations
    assert atom("ground", c) in fast.facts
    assert fast.violations == ["overlap violated: x=rdflib.term.URIRef('urn:optimization:a')"]


def test_unary_plans_use_current_relations_after_equality_reindexing():
    rule = Rule(atom("selected", x), (atom("p", x), atom("q", x)))
    facts = [atom("p", a), atom("q", b)]
    engine = execute([rule], facts)
    assert not any(f.predicate == "selected" for f in engine.facts)
    engine.update(add=[atom(EQ, a, b)])
    assert atom("selected", engine.normalize(a)) in engine.facts
    assert engine.facts == execute([rule], [*facts, atom(EQ, a, b)], strategy="naive").facts
    engine.update(remove=[atom(EQ, a, b)])
    assert engine.facts == execute([rule], facts, strategy="naive").facts


def test_unary_equalities_in_rule_heads_still_propagate():
    rules = [Rule(atom(EQ, x, c), (atom("p", x), atom("q", x))),
             Rule(atom("selected", x), (atom("r", x), atom("s", x)))]
    facts = [atom("p", a), atom("q", a), atom("r", a), atom("s", c)]
    fast = execute(rules, facts)
    naive = execute(rules, facts, strategy="naive")
    assert fast.facts == naive.facts
    assert atom("selected", fast.normalize(a)) in fast.facts


def test_unary_plans_preserve_dred_fact_and_rule_delta_semantics():
    selected = Rule(atom("selected", x), (atom("p", x), atom("q", x)))
    alternate = Rule(atom("selected", x), (atom("alternative", x),))
    recursive = [Rule(atom("cycle", x), (atom("selected", x),)),
                 Rule(atom("selected", x), (atom("cycle", x),))]
    rules = [selected, alternate, *recursive]
    facts = {atom("p", a), atom("q", a), atom("p", b), atom("q", b)}
    engine = execute(rules, facts)
    removed = {atom("p", a), atom("q", b)}
    engine.update(remove=removed)
    facts -= removed
    assert engine.facts == execute(rules, facts, strategy="naive").facts
    assert not any(f.predicate in {"selected", "cycle"} for f in engine.facts)
    engine.update(add=removed)
    facts |= removed
    engine.update(remove_rules=[selected], add=[atom("alternative", b)])
    facts.add(atom("alternative", b))
    rules.remove(selected)
    assert engine.facts == execute(rules, facts, strategy="naive").facts
    assert atom("cycle", a) not in engine.facts
    assert atom("cycle", b) in engine.facts


def test_unary_removed_rule_with_constant_head_drops_last_proof_and_domain_constant():
    rule = Rule(atom("ground", c), (atom("p", x), atom("q", x)))
    engine = execute([rule], [atom("p", a), atom("q", a)])
    engine.update_rules(remove=[rule])
    assert atom("ground", c) not in engine.facts
    assert c not in engine.terms
    assert engine.facts == execute([], engine.asserted, strategy="naive").facts


def test_unary_plan_fact_and_witness_limits_leave_sound_partial_results():
    rule = Rule(atom("selected", x), (atom("p", x), atom("q", x)))
    facts = [atom(predicate, URIRef(f"urn:member:{i}"))
             for predicate in ("p", "q") for i in range(30)]
    engine = execute([], facts)
    engine.max_facts = len(engine.facts) + 3
    engine.update_rules(add=[rule])
    assert not engine.complete
    assert "max_facts" in engine.stats["limit_reason"]
    assert len(engine.facts) <= engine.max_facts
    assert engine.facts <= execute([rule], facts).facts
    witness = Rule(atom("witness", Skolem("f", (x,))), (atom("p", x), atom("q", x)))
    engine = execute([witness], facts, max_depth=0)
    assert not engine.complete
    assert "max_depth" in engine.stats["limit_reason"]
    assert engine.facts <= execute([witness], facts).facts
