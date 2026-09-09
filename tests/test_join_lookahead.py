"""Ordering estimates never alter exact positive-query answers or retain state."""
import gc
from itertools import product
import random
import weakref

import pytest

from dlp_reasoner.engine import Engine, _Index
from dlp_reasoner.joins import _Lookahead
from dlp_reasoner.model import Atom, EQ, NEQ, Program, Rule, Var

X, Y, Z = map(Var, "xyz")


class Looking(Engine):
    _join_lookahead_enabled = True


class Generic(Engine):
    _compiled_joins_enabled = False


def answers(engine, rule, **options):
    return {frozenset(row.items()) for row in engine._solutions(rule, **options)}


def independent(rule, facts, domain, initial=None):
    variables = sorted({term for atom in rule.body for term in atom.args
                        if isinstance(term, Var)}, key=lambda value: value.name)
    initial = {} if initial is None else initial
    result = set()
    for values in product(domain, repeat=len(variables)):
        binding = dict(zip(variables, values))
        if any(binding[v] != value for v, value in initial.items() if v in binding):
            continue
        if all(Atom(atom.predicate, tuple(binding.get(t, t) for t in atom.args)) in facts
               for atom in rule.body):
            result.add(frozenset({**initial, **binding}.items()))
    return result


def test_adopted_defaults_and_lookahead_remains_opt_in():
    assert Engine._compiled_joins_enabled
    assert Engine._incremental_index_enabled
    assert Engine._incremental_validation_enabled
    assert not Engine._join_lookahead_enabled
    assert (_Lookahead.MIN_FANOUT, _Lookahead.SIZE_FACTOR,
            _Lookahead.SAMPLE_ROWS, _Lookahead.PROBE_BUDGET) == (32, 4, 4, 1024)


def test_random_repeated_predicates_variables_constants_and_initial_bindings(monkeypatch):
    # Small independent finite grounding exercises the estimator without making
    # the correctness oracle depend on the production fanout activation limit.
    monkeypatch.setattr(_Lookahead, "MIN_FANOUT", 1)
    rng = random.Random(96421)
    bodies = [(Atom("R", (X, Y)), Atom("S", (Y, Z)), Atom("T", (Z, X))),
              (Atom("R", (X, X)), Atom("S", (X, 2))),
              (Atom("R", (0, X)), Atom("R", (X, Y)), Atom("R", (Y, 2))),
              (Atom("R", (X, Y)), Atom("S", (Y, X)), Atom("S", (Y, Y)))]
    for _ in range(80):
        facts = {Atom(p, row) for p in "RST" for row in product(range(4), repeat=2)
                 if rng.random() < .6}
        rule = Rule(None, rng.choice(bodies))
        initial = {Var("extra"): "preserved"}
        if rng.random() < .5:
            initial[X] = rng.randrange(4)
        engine = Looking(Program([], facts)).materialize()
        before = engine.facts.copy()
        assert answers(engine, rule, initial=initial) == independent(rule, facts, range(4), initial)
        assert engine.facts == before
        assert engine.stats["lookahead_probe_lookups"] <= 1024


@pytest.mark.parametrize("offset", [0, 1])
def test_fixed_threshold_activates_and_pairwise_consistent_cycle_stays_exact(offset):
    facts = {Atom(p, (i, i)) for p in ("R", "S") for i in range(64)}
    facts |= {Atom("T", (i, (i + offset) % 64)) for i in range(64)}
    rule = Rule(None, (Atom("R", (X, Y)), Atom("S", (Y, Z)), Atom("T", (Z, X))))
    engine = Looking(Program([], facts)).materialize()
    assert answers(engine, rule) == independent(rule, facts, range(64))
    assert engine.stats["lookahead_decisions"] > 0
    assert 0 < engine.stats["lookahead_probe_lookups"] <= 1024


def test_exhausted_budget_falls_back_without_pruning(monkeypatch):
    monkeypatch.setattr(_Lookahead, "PROBE_BUDGET", 1)
    facts = {Atom(p, (i, i)) for p in "RST" for i in range(64)}
    rule = Rule(None, (Atom("R", (X, Y)), Atom("S", (Y, Z)), Atom("T", (Z, X))))
    engine = Looking(Program([], facts)).materialize()
    assert answers(engine, rule) == answers(Generic(Program([], facts)).materialize(), rule)
    assert engine.stats["lookahead_probe_lookups"] == 1
    assert engine.stats["lookahead_budget_exhaustions"] == 1
    assert engine.stats["lookahead_reorders"] == 0


def test_lookahead_can_reduce_intermediates_without_changing_answers():
    facts = {Atom(p, (i,)) for p in "RS" for i in range(64)}
    facts |= {Atom("T", (i, i % 64)) for i in range(1024)}
    rule = Rule(None, (Atom("R", (X,)), Atom("S", (Y,)), Atom("T", (Y, X))))
    looking, generic = [kind(Program([], facts)).materialize() for kind in (Looking, Generic)]
    expected = {frozenset({X: x, Y: y}.items()) for x in range(64) for y in range(64)
                if Atom("T", (y, x)) in facts}
    assert answers(looking, rule) == answers(generic, rule) == expected
    assert looking.stats["lookahead_reorders"] > 0
    assert looking.stats["candidate_rows"] < generic.stats["candidate_rows"]


def test_invalid_samples_cannot_grow_hints_or_sampling_without_bound(monkeypatch):
    monkeypatch.setattr(_Lookahead, "PROBE_BUDGET", 2)
    missing, stats = object(), {}
    atoms = tuple(("R", (0, 0), (missing, missing), None) for _ in range(4))
    planner = _Lookahead(atoms, missing, stats)
    # Every physical row fails R(X,X); no sampled lookup is performed.
    rows = {(i, i + 1) for i in range(32)}
    first, second = (0, (0, 0), (missing, missing), rows), (1, (0, 0), (missing, missing), rows)
    planner.choose(first, second, (0, 1, 2), [missing])
    planner.choose(first, second, (0, 1, 3), [missing])
    assert planner.probes == 0 and len(planner.hints) == 2
    assert planner.choose(first, second, (0, 1, 2, 3), [missing]) is first
    assert len(planner.hints) == 2
    assert stats["lookahead_sample_rows"] == 16
    assert stats["lookahead_budget_exhaustions"] == 1


def test_hints_are_recomputed_on_each_invocation_and_after_update():
    facts = {Atom(p, (i, i)) for p in "RST" for i in range(64)}
    rule = Rule(None, (Atom("R", (X, Y)), Atom("S", (Y, Z)), Atom("T", (Z, X))))
    engine = Looking(Program([], facts)).materialize()
    first = answers(engine, rule)
    probes = engine.stats["lookahead_probe_lookups"]
    assert answers(engine, rule) == first
    assert engine.stats["lookahead_probe_lookups"] == 2 * probes
    engine.update(remove=[Atom("T", (0, 0))])
    assert answers(engine, rule) == independent(rule, engine.asserted, range(64))
    assert engine.stats["lookahead_calls"] == 1


@pytest.mark.parametrize("mode", ["delta", "delta_position", "installed", "headed", "incomplete"])
def test_scope_excludes_delta_installed_rules_heads_and_incomplete_closures(mode):
    facts = {Atom(p, (i, i)) for p in "RS" for i in range(64)}
    body = (Atom("R", (X, Y)), Atom("S", (Y, X)))
    query = Rule(Atom("Q", (X,)) if mode == "headed" else None, body)
    rules = [query] if mode == "installed" else []
    engine = Looking(Program(rules, facts)).materialize()
    if mode == "incomplete":
        engine.complete = False
    options = {}
    if mode == "delta":
        options = dict(delta_index=_Index([Atom("R", (0, 0))]), delta_position=0)
    elif mode == "delta_position":
        options = dict(delta_position=7)
    expected = answers(Generic(Program(rules, facts)).materialize(), query, **options)
    assert answers(engine, query, **options) == expected
    assert engine.stats.get("lookahead_calls", 0) == 0


@pytest.mark.parametrize("predicate", [EQ, NEQ])
def test_builtins_keep_generic_fallback(predicate):
    facts = {Atom("R", (i,)) for i in range(64)} | {Atom(NEQ, (0, 1))}
    query = Rule(None, (Atom("R", (X,)), Atom(predicate, (X, 1))))
    engine = Looking(Program([], facts)).materialize()
    assert answers(engine, query) == answers(Generic(Program([], facts)).materialize(), query)
    assert engine.stats.get("lookahead_calls", 0) == 0


@pytest.mark.parametrize("kind", [Generic, Engine, Looking])
@pytest.mark.parametrize("ending", ["exhaust", "close", "throw"])
def test_query_closures_release_engine_and_index_without_cyclic_gc(kind, ending):
    enabled = gc.isenabled()
    gc.disable()
    try:
        engine = kind(Program([], {Atom("R", (i, i)) for i in range(64)})).materialize()
        engine_ref, index_ref = weakref.ref(engine), weakref.ref(engine._index)
        query = Rule(None, (Atom("R", (X, Y)), Atom("R", (Y, X))))
        stream = engine._solutions(query)
        if ending == "exhaust":
            assert len(list(stream)) == 64
        else:
            next(stream)
            if ending == "close":
                stream.close()
            else:
                with pytest.raises(RuntimeError, match="stop"):
                    stream.throw(RuntimeError("stop"))
        del stream, engine
        # No gc.collect(): recursive closure cleanup must release both objects
        # synchronously even when automatic cyclic collection is disabled.
        assert engine_ref() is None
        assert index_ref() is None
    finally:
        if enabled:
            gc.enable()
