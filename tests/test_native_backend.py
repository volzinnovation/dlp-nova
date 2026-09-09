"""Native execution must preserve Python semantics and independent finite oracles."""
from itertools import product
import json
from pathlib import Path
import random
import shutil
from types import SimpleNamespace

import pytest
from rdflib import BNode, Graph, Literal, Namespace, OWL, RDF, RDFS
from rdflib.compare import isomorphic
from rdflib.namespace import XSD

from dlp_reasoner import IncompleteReasoningError, ProfileError, Reasoner
from dlp_reasoner.engine import Engine, _Index, _MISSING
from dlp_reasoner.joins import RelationalPlan
from dlp_reasoner.model import Atom, EQ, NEQ, TOP, Program, Rule, Skolem, Var


EX = Namespace("urn:native-test:")
ROOT = Path(__file__).resolve().parents[1]
X, Y, Z, W = map(Var, "xyzw")


def atom(predicate, *args):
    return Atom(predicate, args)


@pytest.fixture(scope="module", autouse=True)
def native_library():
    # Absence of an optional compiler may skip native tests. A build failure
    # with an available compiler is a failure, never a disguised skip.
    if not any(shutil.which(name) for name in ("clang++", "g++", "c++")):
        pytest.skip("Native backend requires an available C++17 compiler")
    from dlp_reasoner.native import build_native
    return build_native()


def run(rules=(), facts=(), *, backend="native", **options):
    return Engine(Program(list(rules), set(facts)), backend=backend, **options).materialize()


def assert_engine_equivalent(native, python):
    assert native.facts == python.facts
    assert native.asserted == python.asserted
    assert native.complete == python.complete
    assert set(native.violations) == set(python.violations)
    assert native.terms == python.terms
    for term in native.terms | python.terms:
        assert native.equivalents(term) == python.equivalents(term)


def finite_oracle(rules, facts, domain):
    """Exhaust every finite assignment; no production compiler, joins or index.

    This oracle intentionally covers positive, function-free rules only. TOP
    domain seeding and equality are independently tested in dedicated cases.
    """
    closure = set(facts)
    while True:
        following = set(closure)
        for rule in rules:
            variables = sorted({term for item in (*rule.body, rule.head)
                                for term in item.args if isinstance(term, Var)},
                               key=lambda variable: variable.name)
            for values in product(domain, repeat=len(variables)):
                binding = dict(zip(variables, values))

                def ground(item):
                    return Atom(item.predicate, tuple(binding.get(term, term) for term in item.args))

                if all(ground(item) in closure for item in rule.body):
                    following.add(ground(rule.head))
        if following == closure:
            return closure
        closure = following


def plain_facts(engine):
    return {fact for fact in engine.facts if fact.predicate != TOP}


@pytest.mark.parametrize("strategy", ["semi-naive", "naive"])
def test_constants_repeated_variables_zero_and_higher_arities_match_finite_oracle(strategy):
    rules = [
        Rule(atom("reach", X, Y), (atom("edge", X, Y),)),
        Rule(atom("reach", X, Z), (atom("reach", X, Y), atom("edge", Y, Z))),
        Rule(atom("loop", X), (atom("reach", X, X),)),
        Rule(atom("constant", X), (atom("reach", X, 3),)),
        Rule(atom("ready"), (atom("reach", 0, 3),)),
        Rule(atom("wide", X, Y, Z, 3), (atom("edge", X, Y), atom("reach", Y, Z),
                                            atom("ready"))),
        Rule(atom("selected", X), (atom("wide", X, Y, Y, 3),)),
    ]
    facts = {atom("edge", 0, 1), atom("edge", 1, 2), atom("edge", 2, 1), atom("edge", 2, 3)}
    native = run(rules, facts, strategy=strategy)
    assert plain_facts(native) == finite_oracle(rules, facts, range(4))
    assert_engine_equivalent(native, run(rules, facts, backend="python", strategy=strategy))


@pytest.mark.parametrize("seed", [8, 71, 2004])
def test_random_fact_and_rule_transactions_match_independent_oracle_and_fresh_python(seed):
    rules = [Rule(atom("R", X, Y), (atom("E", X, Y),)),
             Rule(atom("R", X, Z), (atom("R", X, Y), atom("E", Y, Z))),
             Rule(atom("Q", X), (atom("P", X),)),
             Rule(atom("P", X), (atom("Q", X),)),
             Rule(atom("Q", X), (atom("S", X),)),
             Rule(atom("diagonal", X), (atom("R", X, X),))]
    pool = [atom("E", *row) for row in product(range(4), repeat=2)]
    pool += [atom(predicate, value) for predicate in ("P", "S") for value in range(4)]
    rng = random.Random(seed)
    facts, active = set(rng.sample(pool, 8)), list(rules)
    native = run(active, facts)
    for _ in range(24):
        additions, removals = set(rng.sample(pool, 3)), set(rng.sample(pool, 4))
        rule_additions, rule_removals = rng.sample(rules, 1), set(rng.sample(rules, 1))
        facts = (facts - removals) | additions
        active = list(dict.fromkeys([rule for rule in active if rule not in rule_removals]
                                    + rule_additions))
        native.update(add=additions, remove=removals, add_rules=rule_additions,
                      remove_rules=rule_removals)
        assert native.complete
        assert plain_facts(native) == finite_oracle(active, facts, range(4))
        assert_engine_equivalent(native, run(active, facts, backend="python", strategy="naive"))


def test_delta_restricts_each_occurrence_of_the_same_predicate():
    rule = Rule(atom("two", X, Z), (atom("edge", X, Y), atom("edge", Y, Z)))
    facts = {atom("edge", 0, 1), atom("edge", 2, 3)}
    native = run([rule], facts)
    native.update(add=[atom("edge", 1, 2)])
    assert {atom("two", 0, 2), atom("two", 1, 3)} <= native.facts
    assert plain_facts(native) == finite_oracle([rule], facts | {atom("edge", 1, 2)}, range(4))


def test_equality_reindexes_constant_joins_and_splits_after_retraction():
    rules = [Rule(atom("both", X), (atom("p", X), atom("q", X))),
             Rule(atom("target", X), (atom("edge", X, EX.b),)),
             Rule(atom("same", X), (atom(EQ, X, EX.a),))]
    facts = {atom("p", EX.a), atom("q", EX.b), atom("edge", EX.c, EX.a)}
    native, python = (run(rules, facts, backend=backend) for backend in ("native", "python"))
    for transaction in ({"add": [atom(EQ, EX.a, EX.b)]},
                        {"remove": [atom(EQ, EX.a, EX.b)]},
                        {"add": [atom(EQ, EX.a, EX.b), atom(NEQ, EX.a, EX.b)]},
                        {"remove": [atom(NEQ, EX.a, EX.b)]}):
        native.update(**transaction)
        python.update(**transaction)
        assert_engine_equivalent(native, python)


def test_literal_dictionary_preserves_supported_values_and_opaque_datatypes():
    literals = [Literal("1", datatype=XSD.integer), Literal("1.0", datatype=XSD.decimal),
                Literal(False), Literal(0), Literal("hello"),
                Literal("hello", datatype=XSD.string), Literal("hello", lang="en"),
                Literal("urn:a", datatype=XSD.anyURI), Literal("urn:a", datatype=XSD.string),
                Literal("1", datatype=XSD.float), Literal("1", datatype=XSD.double)]
    facts = {atom("value", EX[f"a{index}"], value) for index, value in enumerate(literals)}
    rules = [Rule(atom("samevalue", X, Y), (atom("value", X, Z), atom("value", Y, Z)))]
    native, python = (run(rules, facts, backend=backend) for backend in ("native", "python"))
    assert_engine_equivalent(native, python)
    assert atom("samevalue", EX.a0, EX.a1) in native.facts
    assert atom("samevalue", EX.a4, EX.a5) in native.facts
    assert atom("samevalue", EX.a2, EX.a3) not in native.facts
    assert atom("samevalue", EX.a7, EX.a8) not in native.facts
    native.update(remove=[atom("value", EX.a0, literals[0])])
    python.update(remove=[atom("value", EX.a0, literals[0])])
    assert_engine_equivalent(native, python)


def test_late_equality_preserves_nested_skolem_congruence():
    def term(value):
        return Skolem("g", (Skolem("f", (value,)),))
    rules = [Rule(atom("p", term(X)), (atom("left", X),)),
             Rule(atom("q", term(X)), (atom("right", X),)),
             Rule(atom("both", X), (atom("p", X), atom("q", X))),
             Rule(atom(EQ, X, Y), (atom("merge", X, Y),))]
    facts = {atom("left", EX.a), atom("right", EX.b), atom("merge", EX.a, EX.b)}
    native = run(rules, facts)
    assert_engine_equivalent(native, run(rules, facts, backend="python"))
    assert native.normalize(term(EX.a)) == native.normalize(term(EX.b))
    assert atom("both", native.normalize(term(EX.a))) in native.facts


@pytest.mark.parametrize("limit", [{"max_rounds": 2}, {"max_depth": 2}, {"max_facts": 12}])
def test_infinite_l3_witness_program_reports_resource_incompleteness(limit):
    rules = [Rule(atom("edge", X, Skolem("f", (X,))), (atom("seed", X),)),
             Rule(atom("seed", Y), (atom("edge", X, Y),))]
    native = run(rules, {atom("seed", EX.a)}, **limit)
    python = run(rules, {atom("seed", EX.a)}, backend="python", **limit)
    assert not native.complete and not python.complete
    assert native.stats["limit_reason"] == python.stats["limit_reason"]
    # Different valid iteration orders may retain a different bounded prefix;
    # every retained edge must nevertheless be a genuine witness derivation.
    for fact in native.facts:
        if fact.predicate == "edge":
            assert fact.args[1] == Skolem("f", (fact.args[0],))


def test_positive_and_empty_constraints_are_not_lost_in_native_execution():
    rules = [Rule(None, (atom("p", X, Y), atom("q", Y, X)), "opposed"),
             Rule(None, (), "always-false")]
    facts = {atom("p", EX.a, EX.b), atom("q", EX.b, EX.a)}
    assert_engine_equivalent(run(rules, facts), run(rules, facts, backend="python"))


def test_rejected_fact_and_rule_transactions_leave_native_state_unchanged():
    rule = Rule(atom("q", X, Y), (atom("p", X, Y),))
    native = run([rule], {atom("p", EX.a, EX.b)})
    for transaction in (
        {"add": [atom("new", EX.c), atom("p", EX.a)]},
        {"add": [atom("p", X, EX.a)]},
        {"add_rules": [Rule(atom("unsafe", X))]},
        {"add": [atom("new", EX.a)],
         "add_rules": [Rule(atom("z", X), (atom("new", X, Y),))]},
    ):
        before = (native.facts.copy(), native.asserted.copy(), list(native.rules),
                  native.stats.copy(), native._index._handle)
        with pytest.raises(ProfileError):
            native.update(**transaction)
        assert (native.facts, native.asserted, native.rules, native.stats,
                native._index._handle) == before
    native.update(add=[atom("new", EX.a, EX.b)])
    assert atom("new", EX.a, EX.b) in native.facts


def test_store_identity_survives_ordinary_insert_and_dred_delete():
    facts = {atom("edge", index, index + 1) for index in range(60)}
    rule = Rule(atom("copy", X, Y), (atom("edge", X, Y),))
    native = run([rule], facts)
    handle = native._index._handle
    native.update(add=[atom("edge", 3, 8)])
    assert native._index._handle == handle
    native.update(remove=[atom("edge", 3, 8)])
    assert native.stats["update_method"] == "dred"
    assert native._index._handle == handle
    assert_engine_equivalent(native, run([rule], facts, backend="python"))


@pytest.mark.parametrize("old,new", [(atom("p", 0), atom("p", 0, 1)),
                                      (atom("p", 0, 1), atom("p", 0)),
                                      (atom("p"), atom("p", 0, 1, 2))])
def test_last_tuple_removal_can_change_predicate_arity_without_replacing_other_relations(old, new):
    facts = {atom("unrelated", value, value + 1) for value in range(100)} | {old}
    native = run(facts=facts)
    handle = native._index._handle
    native.update(remove=[old], add=[new])
    assert native._index._handle == handle
    assert native.stats["update_method"] == "dred"
    assert set(native._index.rows.get("p", ())) == {new.args}
    assert_engine_equivalent(native, run(facts=(facts - {old}) | {new}, backend="python"))


@pytest.mark.parametrize("name,profile", [("family", "L2"), ("existential", "L3"),
                                         ("bach", "L3"), ("bach-family", "L0")])
def test_reasoner_examples_and_query_probes_preserve_backend_and_answers(name, profile):
    path = ROOT / "examples" / f"{name}.dlp"
    native, python = (Reasoner.from_file(path, profile=profile, backend=backend)
                      for backend in ("native", "python"))
    assert native.engine.backend == "native"
    assert isomorphic(native.to_graph(include_witnesses=True),
                      python.to_graph(include_witnesses=True))
    if name == "family":
        ns = Namespace("https://example.org/family#")
        assert native.instances(ns.Parent) == python.instances(ns.Parent)
        assert native.subsumes(ns.Person, ns.Composer)
        assert not native.subsumes(ns.Composer, ns.Person)
        assert native.is_satisfiable(ns.Composer)
        probe = BNode()
        for reasoner in (native, python):
            reasoner.graph.add((probe, OWL.onProperty, ns.hasChild))
            reasoner.graph.add((probe, OWL.someValuesFrom, ns.Person))
        assert native.instances(probe) == python.instances(probe)
        assert native.entails(ns.fresh, RDF.type, OWL.Thing)


def test_reasoner_failed_update_and_incomplete_queries_remain_transactional():
    graph = Graph()
    graph.add((EX.a, RDF.type, EX.A))
    native = Reasoner(graph, backend="native")
    before = set(native.graph), native.engine.facts.copy()
    node = BNode()
    with pytest.raises(ProfileError):
        native.update(add=[(EX.A, RDFS.subClassOf, node), (node, OWL.onProperty, EX.p),
                           (node, OWL.someValuesFrom, EX.A)])
    assert (set(native.graph), native.engine.facts) == before
    graph += Graph().parse(data='''@prefix ex: <urn:native-test:> .
      @prefix owl: <http://www.w3.org/2002/07/owl#> .
      @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
      ex:A rdfs:subClassOf [owl:onProperty ex:p; owl:someValuesFrom ex:A].''', format="turtle")
    limited = Reasoner(graph, profile="L3", max_depth=2, backend="native")
    assert not limited.complete and limited.consistency == "unknown"
    with pytest.raises(IncompleteReasoningError):
        limited.instances(EX.A)


@pytest.mark.parametrize("arity", range(5))
def test_native_index_lookup_add_remove_matches_independent_relation_filter(arity):
    from dlp_reasoner.native import NativeContext, NativeIndex
    rows = set(product(range(3), repeat=arity))
    with NativeContext(_MISSING) as context, NativeIndex(
            context, [Atom("p", row) for row in rows]) as index:
        for values in product((_MISSING, 0, 1, 5), repeat=arity):
            expected = {row for row in rows if all(value is _MISSING or value == actual
                                                   for value, actual in zip(values, row))}
            # Generic lookup may return a smallest column bucket; callers
            # perform the remaining bound-position/repeated-variable filtering.
            actual = {row for row in index.lookup("p", values)
                      if all(value is _MISSING or value == item
                             for value, item in zip(values, row))}
            assert actual == expected
        for row in sorted(rows)[::2]:
            index.discard(Atom("p", row))
            index.discard(Atom("p", row))
            rows.remove(row)
        assert set(index.rows.get("p", ())) == rows
        assert set(index.lookup("missing", (_MISSING,) * arity)) == set()


def test_repeated_native_queries_do_not_retransfer_unchanged_relations():
    from dlp_reasoner.native import NativeContext, NativeIndex
    facts = {atom("p", value, value + 1) for value in range(40)}
    rule = Rule(atom("q", X, Z), (atom("p", X, Y), atom("p", Y, Z)))
    with NativeContext(_MISSING) as context, NativeIndex(context, facts) as index:
        index.flush()
        context.reset_stats()
        engine = SimpleNamespace(_index=index, normalize=lambda value: value,
                                 stats={"body_matches": 0, "candidate_rows": 0})
        for _ in range(5):
            actual = list(index.solutions(RelationalPlan(rule), engine, _MISSING))
            assert len(actual) == 39
        stats = context.stats()
        assert stats["native_rows_inserted"] == 0
        assert stats["native_bulk_calls"] == 0
        assert stats["native_stores_created"] == 0
        assert stats["native_queries"] >= 5
        assert stats["native_active_cursors"] == 0


def test_native_plan_initial_binding_and_delta_occurrence_match_python_plan():
    from dlp_reasoner.native import NativeContext, NativeIndex
    facts = {atom("p", a, b) for a, b in ((0, 1), (1, 2), (1, 3), (2, 3), (3, 3))}
    delta = {atom("p", 1, 2), atom("p", 3, 3)}
    rule = Rule(atom("q", X, Z), (atom("p", X, Y), atom("p", Y, Z)))
    plan = RelationalPlan(rule)
    with NativeContext(_MISSING) as context, NativeIndex(context, facts) as index, NativeIndex(
            context, delta) as changed:
        native_engine = SimpleNamespace(_index=index, normalize=lambda value: value,
                                        stats={"body_matches": 0, "candidate_rows": 0})
        python_engine = SimpleNamespace(_index=_Index(facts), normalize=lambda value: value,
                                        stats={"body_matches": 0, "candidate_rows": 0})
        for position in (0, 1):
            for initial in ({}, {X: 1}, {Z: 3}, {W: 99}):
                expected = {tuple(sorted(binding.items(), key=lambda item: item[0].name))
                            for binding in plan.solutions(python_engine, _MISSING,
                                                          _Index(delta), position, initial)}
                actual = {tuple(sorted(binding.items(), key=lambda item: item[0].name))
                          for binding in index.solutions(plan, native_engine, _MISSING,
                                                         changed, position, initial)}
                assert actual == expected


def test_streaming_native_join_early_close_and_mutation_are_safe_and_bounded():
    from dlp_reasoner.native import NativeBackendError, NativeContext, NativeIndex
    # A full result would have 25 million bindings. Only one is requested.
    facts = {atom(predicate, value) for predicate in ("left", "right") for value in range(5000)}
    rule = Rule(atom("cross", X, Y), (atom("left", X), atom("right", Y)))
    with NativeContext(_MISSING) as context, NativeIndex(context, facts) as index:
        engine = SimpleNamespace(_index=index, normalize=lambda value: value,
                                 stats={"body_matches": 0, "candidate_rows": 0})
        cursor = index.solutions(RelationalPlan(rule), engine, _MISSING)
        assert set(next(cursor)) == {X, Y}
        assert context.stats()["native_bindings"] <= 4096
        cursor.close()
        assert context.stats()["native_active_cursors"] == 0

        cursor = index.solutions(RelationalPlan(rule), engine, _MISSING)
        next(cursor)
        index.add(atom("left", 5001))
        with pytest.raises(NativeBackendError, match="[Mm]utat|[Cc]hang|invalid"):
            next(cursor)
        cursor.close()
        assert context.stats()["native_active_cursors"] == 0


def test_engine_fact_limit_stops_stream_before_allocating_cartesian_result():
    facts = {atom(predicate, value) for predicate in ("left", "right") for value in range(2000)}
    rule = Rule(atom("cross", X, Y), (atom("left", X), atom("right", Y)))
    # 4,000 input tuples plus 2,001 TOP facts leave room for only a few outputs.
    native = run([rule], facts, max_facts=6020)
    assert not native.complete
    assert len(native.facts) <= 6021
    assert native.stats["native_bindings"] <= 4096
    assert native.stats["native_active_cursors"] == 0


def test_engine_rematerialization_invalidates_an_external_suspended_query():
    from dlp_reasoner.native import NativeBackendError
    rule = Rule(atom("q", X, Z), (atom("p", X, Y), atom("p", Y, Z)))
    native = run([rule], {atom("p", index, index + 1) for index in range(8)})
    cursor = native._solutions(rule)
    next(cursor)
    native.materialize()
    with pytest.raises(NativeBackendError):
        next(cursor)
    cursor.close()
    assert native._native_context.stats()["native_active_cursors"] == 0


def test_explicit_context_close_releases_a_live_cursor():
    from dlp_reasoner.native import NativeBackendError, NativeContext, NativeIndex
    context = NativeContext(_MISSING)
    index = NativeIndex(context, [atom("p", index, index + 1) for index in range(10)])
    rule = Rule(atom("q", X, Z), (atom("p", X, Y), atom("p", Y, Z)))
    engine = SimpleNamespace(_index=index, normalize=lambda value: value,
                             stats={"body_matches": 0, "candidate_rows": 0})
    cursor = index.solutions(RelationalPlan(rule), engine, _MISSING)
    next(cursor)
    context.close()
    with pytest.raises((NativeBackendError, StopIteration)):
        next(cursor)
    cursor.close()
    index.close()
    context.close()  # Closing released owners twice is harmless.


def test_warmed_build_and_context_do_not_probe_the_compiler_again(monkeypatch):
    from dlp_reasoner import native
    expected = native.build_native()

    def unexpected_subprocess(*args, **kwargs):
        raise AssertionError("A warmed, unchanged native library must not invoke the compiler")

    monkeypatch.setattr(native.subprocess, "run", unexpected_subprocess)
    assert native.build_native() == expected
    with native.NativeContext(_MISSING):
        pass


def test_explicit_missing_compiler_is_actionable_and_never_falls_back(tmp_path):
    from dlp_reasoner.native import NativeBackendError, build_native
    with pytest.raises(NativeBackendError, match="[Cc]ompil|not found|unavailable"):
        build_native(compiler=str(tmp_path / "no-cxx"), cache_dir=tmp_path / "cache")


def test_requested_native_initialization_failure_propagates_and_cli_reports_it(monkeypatch, capsys):
    from dlp_reasoner import native
    from dlp_reasoner.cli import main

    def unavailable(*args, **kwargs):
        raise native.NativeBackendError("Native C++17 compiler unavailable; select backend='python'.")

    monkeypatch.setattr(native, "NativeContext", unavailable)
    with pytest.raises(native.NativeBackendError, match="compiler unavailable"):
        Engine(Program(), backend="native")
    assert main(["validate", str(ROOT / "examples/family.dlp"), "--backend", "native"]) == 1
    error = json.loads(capsys.readouterr().err)
    assert error["type"] == "NativeBackendError"
    assert "compiler unavailable" in error["error"]
    assert Engine(Program()).backend == "python"


def test_unknown_backend_is_rejected_and_python_remains_default():
    assert Engine(Program()).backend == "python"
    with pytest.raises(ValueError, match="backend"):
        Engine(Program(), backend="not-a-backend")


def test_cli_native_selection_answers_status_and_materialization(tmp_path, capsys):
    from dlp_reasoner.cli import main
    source = ROOT / "examples/family.dlp"
    assert main(["validate", str(source), "--backend", "native"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["backend"] == "native" and result["complete"]
    assert result["native_stores_created"] > 0
    assert main(["instances", str(source), "https://example.org/family#Parent",
                 "--backend", "native"]) == 0
    assert set(json.loads(capsys.readouterr().out)) == {
        "https://example.org/family#johann", "https://example.org/family#jsbach"}
    output = tmp_path / "native.ttl"
    assert main(["materialize", str(source), "--backend", "native", "-o", str(output)]) == 0
    capsys.readouterr()
    assert Reasoner.from_file(output).consistency == "consistent"
    assert main(["validate", str(ROOT / "examples/inconsistent.dlp"),
                 "--backend", "native"]) == 2
    assert json.loads(capsys.readouterr().out)["consistency"] == "inconsistent"


def test_bach_graph_fact_and_rule_updates_match_independent_reachability():
    BACH = Namespace("http://www.jsbach.org/bach#")

    def reachability(edges):
        closure = set(edges)
        while True:
            following = closure | {(a, d) for a, b in closure for c, d in closure if b == c}
            if following == closure:
                return closure
            closure = following

    source = ROOT / "examples/bach-family.dlp"
    native, python = (Reasoner.from_file(source, profile="L0", backend=backend)
                      for backend in ("native", "python"))
    js, wf, jc = (BACH[name] for name in
                  ("johann-sebastian", "wilhelm-friedemann", "johann-christian"))
    edges = set(native.graph.subject_objects(BACH.ancestorOf))
    transactions = [
        {"remove": [(js, BACH.ancestorOf, wf)], "add": [(js, BACH.ancestorOf, jc)]},
        {"remove": [(BACH.ancestorOf, RDFS.subPropertyOf, BACH.inDynasty)]},
        {"add": [(BACH.ancestorOf, RDFS.subPropertyOf, BACH.inDynasty),
                 (BACH.inDynasty, RDF.type, OWL.SymmetricProperty)]},
        {"remove": [(BACH.inDynasty, RDF.type, OWL.SymmetricProperty)]},
    ]
    for index, transaction in enumerate(transactions):
        native.update(**transaction)
        python.update(**transaction)
        assert_engine_equivalent(native.engine, python.engine)
        if index == 0:
            edges = (edges - {(js, wf)}) | {(js, jc)}
        expected = reachability(edges)
        assert native.property_pairs(BACH.ancestorOf) == expected
        expected_dynasty = set() if index == 1 else (
            expected | {(b, a) for a, b in expected} if index == 2 else expected)
        assert native.property_pairs(BACH.inDynasty) == expected_dynasty
