"""DRed tuple removal leaves exactly the index of the surviving materialization."""
from itertools import product
import random

import pytest
from rdflib import Literal
from rdflib.namespace import XSD

from dlp_reasoner.engine import Engine, _Index, _MISSING
from dlp_reasoner.model import Atom, EQ, NEQ, Program, Rule, Var


class Indexed(Engine):
    _incremental_index_enabled = True


@pytest.mark.parametrize("arity", range(5))
def test_incremental_index_equals_reconstruction_after_arbitrary_removal(arity):
    rows = list(product(range(3), repeat=arity))
    facts = {Atom("p", row) for row in rows}
    index = _Index(facts)
    rng = random.Random(32 + arity)
    rng.shuffle(rows)
    for row in rows:
        fact = Atom("p", row)
        facts.remove(fact)
        index.discard(fact)
        index.discard(fact)  # Idempotence, including a removed last bucket.
        fresh = _Index(facts)
        assert index.rows == fresh.rows
        assert index.columns == fresh.columns
        for values in product((_MISSING, 0, 1, 2, 5), repeat=arity):
            assert set(index.lookup("p", values)) == set(fresh.lookup("p", values))
    index.add(Atom("p", tuple(range(arity))))
    assert index.rows == _Index([Atom("p", tuple(range(arity)))]).rows


@pytest.mark.parametrize("certificates", [False, True])
def test_random_mixed_updates_match_naive_reconstruction_and_indexes(certificates):
    x, y, z = map(Var, "xyz")
    rules = [Rule(Atom("R", (x, y)), (Atom("E", (x, y)),)),
             Rule(Atom("R", (x, z)), (Atom("R", (x, y)), Atom("E", (y, z)))),
             Rule(Atom("Q", (x,)), (Atom("P", (x,)),)),
             Rule(Atom("P", (x,)), (Atom("Q", (x,)),)),
             Rule(Atom("Q", (x,)), (Atom("S", (x,)),))]
    pool = [Atom("E", row) for row in product(range(4), repeat=2)]
    pool += [Atom(p, (n,)) for p in ("P", "S") for n in range(4)]
    rng = random.Random(8123)
    facts, active = set(pool[:5]), set(rules)
    engine = Indexed(Program(list(active), facts)).materialize()
    engine._support_certificates_enabled = certificates
    for _ in range(70):
        add, remove = set(rng.sample(pool, 3)), set(rng.sample(pool, 4))
        ra, rr = set(rng.sample(rules, 1)), set(rng.sample(rules, 1))
        facts = (facts - remove) | add
        active = (active - rr) | ra
        engine.update(add=add, remove=remove, add_rules=ra, remove_rules=rr)
        fresh = Engine(Program(list(active), facts), strategy="naive").materialize()
        assert engine.complete and engine.facts == fresh.facts
        assert engine.terms == fresh.terms
        assert engine._index.rows == fresh._index.rows
        assert engine._index.columns == fresh._index.columns


def test_explicit_difference_domain_departure_and_literal_identity_fallback():
    facts = {Atom(NEQ, ("a", "b")), Atom("P", ("c",))}
    engine = Indexed(Program([], facts)).materialize()
    engine.update(remove=[Atom(NEQ, ("a", "b"))])
    fresh = Engine(Program([], {Atom("P", ("c",))})).materialize()
    assert engine.facts == fresh.facts
    assert engine._index.columns == fresh._index.columns
    integer = Literal("1", datatype=XSD.integer)
    decimal = Literal("1.0", datatype=XSD.decimal)
    engine.update(add=[Atom("N", (integer,)), Atom("N", (decimal,))])
    engine.update(remove=[Atom("N", (integer,))])
    assert engine.stats["update_method"] == "rematerialize"
    assert engine._index.rows == _Index(engine.facts).rows
    engine.update(add=[Atom(EQ, ("a", "b"))])
    engine.update(remove=[Atom(EQ, ("a", "b"))])
    assert engine.stats["update_method"] == "rematerialize"
