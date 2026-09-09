"""Positional join plans retain exact bindings, delta occurrences, and equality."""
from itertools import product
import random

import pytest
from rdflib import URIRef

from dlp_reasoner.engine import Engine, _Index, _MISSING
from dlp_reasoner.model import Atom, EQ, NEQ, Program, Rule, Skolem, Var

X, Y, Z = map(Var, "xyz")


class Generic(Engine):
    _compiled_joins_enabled = False


class Planned(Engine):
    _compiled_joins_enabled = True


def bindings(engine, rule, **kwargs):
    return {frozenset(row.items()) for row in engine._solutions(rule, **kwargs)}


def test_random_positive_bindings_equal_independent_cartesian_join():
    rng = random.Random(7812)
    for _ in range(180):
        rows = {p: {row for row in product(range(3), repeat=arity) if rng.random() < .55}
                for p, arity in (("R", 2), ("S", 2), ("T", 3), ("U", 1))}
        facts = {Atom(p, row) for p, tuples in rows.items() for row in tuples}
        bodies = [(Atom("R", (X, Y)), Atom("S", (Y, Z)), Atom("T", (X, Z, X))),
                  (Atom("R", (X, X)), Atom("S", (X, 1)), Atom("U", (X,))),
                  (Atom("R", (0, X)), Atom("R", (X, Y)), Atom("R", (Y, 2))),
                  (Atom("T", (X, Y, Z)), Atom("U", (Z,)), Atom("S", (X, Y)))]
        body = rng.choice(bodies)
        rule = Rule(None, body)
        engine = Planned(Program([], facts)).materialize()
        used = sorted({term for atom in body for term in atom.args if isinstance(term, Var)},
                      key=lambda v: v.name)
        initial = {} if rng.random() < .5 else {rng.choice(used): rng.randrange(3)}
        initial[Var("extra")] = "preserved"
        # Independent finite substitution, without Engine's joins/indexes.
        expected = set()
        for values in product(range(3), repeat=len(used)):
            assignment = dict(zip(used, values))
            if any(assignment[v] != value for v, value in initial.items() if v in assignment):
                continue
            if all(tuple(assignment.get(t, t) for t in atom.args) in rows[atom.predicate]
                   for atom in body):
                expected.add(frozenset({**initial, **assignment}.items()))
        assert bindings(engine, rule, initial=initial) == expected


@pytest.mark.parametrize("position", range(3))
def test_delta_relation_applies_only_to_designated_body_occurrence(position):
    facts = {Atom("R", row) for row in product(range(3), repeat=2)}
    rule = Rule(None, (Atom("R", (X, Y)), Atom("R", (Y, Z)), Atom("R", (Z, X))))
    delta = _Index([Atom("R", (0, 1))])
    planned = Planned(Program([], facts)).materialize()
    generic = Generic(Program([], facts)).materialize()
    assert bindings(planned, rule, delta_index=delta, delta_position=position) == bindings(
        generic, rule, delta_index=delta, delta_position=position)


@pytest.mark.parametrize("body", [(), (Atom("R", ()),),
                                 (Atom("R", ()), Atom("S", ())),
                                 (Atom(EQ, (X, 1)),),
                                 (Atom("U", (X,)), Atom(NEQ, (X, 2)))])
def test_zero_arity_and_equality_difference_fallback(body):
    facts = {Atom("R", ()), Atom("S", ()), Atom("U", (1,)), Atom(NEQ, (1, 2))}
    rule = Rule(None, body)
    a = Planned(Program([], facts)).materialize()
    b = Generic(Program([], facts)).materialize()
    assert bindings(a, rule) == bindings(b, rule)


def test_cached_ground_constants_are_recanonicalized_after_merge_and_split():
    a, b, c = map(URIRef, ("urn:a", "urn:b", "urn:c"))
    fa, fb = Skolem("f", (a,)), Skolem("f", (b,))
    rules = [Rule(Atom("Q", (X,)), (Atom("R", (fa, X)), Atom("S", (X, c))))]
    facts = {Atom("R", (fb, c)), Atom("S", (c, c))}
    engines = [kind(Program(rules, facts)).materialize() for kind in (Planned, Generic)]
    assert engines[0].facts == engines[1].facts
    for e in engines:
        e.update(add=[Atom(EQ, (a, b))])
    assert engines[0].facts == engines[1].facts
    assert Atom("Q", (c,)) in engines[0].facts
    for e in engines:
        e.update(remove=[Atom(EQ, (a, b))])
    assert engines[0].facts == engines[1].facts
    assert Atom("Q", (c,)) not in engines[0].facts


def test_runtime_switch_and_internal_sentinel_initial_preserve_generic_behavior():
    rule = Rule(None, (Atom("R", (X, Y)), Atom("S", (Y,))))
    engine = Generic(Program([], {Atom("R", (1, 2)), Atom("S", (2,))})).materialize()
    expected = bindings(engine, rule)
    sentinel = bindings(engine, rule, initial={X: _MISSING})
    engine._compiled_joins_enabled = True
    assert bindings(engine, rule) == expected
    assert bindings(engine, rule, initial={X: _MISSING}) == sentinel


def test_rule_changes_refresh_plans_and_new_consequences():
    first = Rule(Atom("Q", (X,)), (Atom("R", (X, Y)), Atom("S", (Y,))))
    second = Rule(Atom("Q", (Y,)), (Atom("R", (X, Y)), Atom("S", (X,))))
    facts = {Atom("R", (1, 2)), Atom("S", (2,))}
    engine = Planned(Program([first], facts)).materialize()
    engine.update(remove_rules=[first], add_rules=[second])
    assert engine.facts == Generic(Program([second], facts)).materialize().facts
    assert first not in engine._relational_plans
