"""Complete C++ query plans, independently compared with finite Python rules."""
import ctypes as c
import random

import pytest
from rdflib import Literal, Namespace, URIRef, XSD

from dlp_reasoner.domains import DomainError, Point, Quantity, IntegerValue
from dlp_reasoner.model import NEQ
from dlp_reasoner.providers import CancellationToken, FakeProvider, ProviderRegistry
from dlp_reasoner.query_native import _Arg, _CONTROL, _Limits, _Node, _Value, _library
from dlp_reasoner.query_runtime import QueryExecutionError, QueryRuntime, QueryScope

EX = Namespace("urn:native-query:")
SCOPE = QueryScope("urn:native-query:scope", "1")
PREFIX = "version 1 prefix ex: <urn:native-query:> prefix n: <urn:dlp:numeric:> "


def differential(source, snapshots, parameters=None, **options):
    with QueryRuntime(source, backend="native", cache_size=0, **options) as native, \
            QueryRuntime(source, backend="python", cache_size=0, **options) as python:
        answers = []
        for rows in snapshots:
            actual = native.evaluate(rows, scope=SCOPE, parameters=parameters)
            expected = python.evaluate(rows, scope=SCOPE, parameters=parameters)
            assert actual.relations == expected.relations
            assert actual.additions == expected.additions and actual.retractions == expected.retractions
            assert native.stats["execution_mode"] == "native"
            answers.append(actual)
        return answers


def test_native_strata_never_call_python_scalar_or_solution_implementations(monkeypatch):
    source = PREFIX + """
        ex:next(?id, ?m) :- ex:input(?id, ?n), bind n:add(?n, 1) as ?m.
        ex:best(?m) :- MIN ?n GROUP_BY() FROM ex:next(?id, ?n) AS ?m.
        ex:answer(?m) :- ex:best(?m), filter n:lessThan(?m, 100).
    """
    def forbidden(*args, **kwargs):
        raise AssertionError("native query called Python scalar/orchestration code")
    with QueryRuntime(source, backend="native") as runtime:
        monkeypatch.setattr(runtime.domains, "evaluate_batch", forbidden)
        monkeypatch.setattr(runtime, "_solutions", forbidden)
        result = runtime.evaluate({EX.input: {(EX.a, Literal(9)), (EX.b, Literal(4))}}, scope=SCOPE)
        assert result.rows(EX.answer) == {(Literal(5),)}
        assert runtime.stats["domain_evaluations"] > 0
        assert runtime.explain()["execution"]["mode"] == "native"


def test_recursive_relations_repeated_variables_constants_zero_and_high_arity():
    source = PREFIX + """
        ex:path(?x, ?y) :- ex:edge(?x, ?y).
        ex:path(?x, ?z) :- ex:path(?x, ?y), ex:edge(?y, ?z).
        ex:self(?x) :- ex:path(?x, ?x).
        ex:high(?x, ?y, ?x, ex:a, ?y) :- ex:path(?x, ?y), ex:enabled().
        ex:exists() :- ex:path(ex:a, ex:b).
    """
    graph = {(EX.a, EX.b), (EX.b, EX.c), (EX.c, EX.a), (EX.d, EX.e)}
    results = differential(source, [{EX.edge: graph, EX.enabled: {()}}, {EX.edge: {(EX.a, EX.b)}}])
    assert results[0].rows(EX.self) == {(EX.a,), (EX.b,), (EX.c,)}
    assert len(results[0].rows(EX.high)) == 10
    assert results[1].rows(EX.exists) == {()} and not results[1].rows(EX.high)


def test_randomized_finite_relation_and_numeric_updates_match_independent_oracle():
    source = PREFIX + """
        ex:joined(?a, ?c, ?sum) :- ex:left(?a, ?b, ?n), ex:right(?b, ?c, ?m),
            bind n:add(?n, ?m) as ?sum, filter n:lessThanOrEqual(?sum, 8).
    """
    rng = random.Random(78612)
    snapshots, expected = [], []
    for _ in range(30):
        left = {(rng.randrange(5), rng.randrange(5), rng.randrange(6)) for _ in range(12)}
        right = {(rng.randrange(5), rng.randrange(5), rng.randrange(6)) for _ in range(12)}
        snapshots.append({EX.left: {tuple(map(Literal, row)) for row in left},
                          EX.right: {tuple(map(Literal, row)) for row in right}})
        expected.append({(Literal(a), Literal(z), Literal(n + m))
                         for a, b, n in left for y, z, m in right if b == y and n + m <= 8})
    actual = differential(source, snapshots)
    assert [set(answer.rows(EX.joined)) for answer in actual] == expected


def test_native_generated_literals_preserve_rdf_identity_and_bind_value_agreement():
    source = PREFIX + """
        ex:computed(?y) :- ex:seed(?x), bind n:add(?x, 1) as ?y.
        ex:joined(?y) :- ex:computed(?y), ex:lookup(?y).
        ex:agree(?existing) :- ex:lookup(?existing), bind n:add(1, 1) as ?existing.
    """
    lexical = Literal("02", datatype=XSD.integer, normalize=False)
    decimal = Literal("2.0", datatype=XSD.decimal, normalize=False)
    result = differential(source, [{EX.seed: {(Literal(1),)}, EX.lookup: {(lexical,), (decimal,)}}])[0]
    assert not result.rows(EX.joined)
    assert result.rows(EX.agree) == {(lexical,), (decimal,)}
    assert result.rows(EX.computed) == {(Literal(2),)}


def test_given_params_eq_and_conservative_literal_neq_match():
    source = PREFIX + """prefix core: <urn:dlp:internal:>
        ex:copy(?x, ?seed) given (?seed) :- ex:input(?x), core:eq(?seed, ?copy), core:eq(?seed, ?copy).
        ex:different(?a, ?b) :- ex:pair(?a, ?b), core:neq(?a, ?b).
    """
    pairs = {(EX.a, EX.b), (EX.b, EX.c), (Literal(1), Literal(2)),
             (Literal("01", datatype=XSD.integer, normalize=False), Literal(1)),
             (Literal("a"), Literal("b")), (Literal("a", lang="en"), Literal("a", lang="de")),
             (Literal(True), Literal(1)), (Literal("1.5", datatype=XSD.double), Literal("2.5", datatype=XSD.double))}
    result = differential(source, [{EX.input: {(EX.a,)}, EX.pair: pairs, URIRef(NEQ): {(EX.a, EX.b)}}],
                          {"seed": EX.seed})[0]
    assert (EX.a, EX.b) in result.rows(EX.different) and (EX.b, EX.c) not in result.rows(EX.different)
    assert len(result.rows(EX.different)) == 5
    assert result.rows(EX.copy) == {(EX.a, EX.seed)}


def test_temporal_point_quantity_and_float_operations_use_native_domains():
    source = PREFIX + """prefix t: <urn:dlp:temporal:> prefix s: <urn:dlp:spatial:>
        ex:age(?years) :- ex:dates(?birth, ?child), bind t:completedYears(?birth, ?child, "march1") as ?years.
        ex:point(?point) :- ex:coordinate(?lon, ?lat), bind s:wgs84Point(?lon, ?lat) as ?point.
        ex:distance(?metres) :- ex:point(?point), bind s:wgs84Distance(?point, ?point) as ?metres.
        ex:quantity(?out) :- ex:numeric(?n), bind n:quantity(?n, "metre") as ?q, bind n:quantityAdd(?q, ?q) as ?out.
    """
    result = differential(source, [{EX.dates: {(Literal("1980-02-29", datatype=XSD.date),
                                               Literal("2000-03-01", datatype=XSD.date))},
                                   EX.coordinate: {(Literal(0), Literal(0))}, EX.numeric: {(Literal(3),)}}])[0]
    assert result.rows(EX.age) == {(Literal(20),)}
    assert result.rows(EX.point) == {(Point(0.0, 0.0),)}
    assert result.rows(EX.quantity) == {(Quantity(IntegerValue(6), "urn:dlp:unit:metre"),)}


@pytest.mark.parametrize("literal", [Literal("bad", datatype=XSD.date), Literal(True), Literal("plain")])
def test_min_rejects_unsupported_singleton_without_publishing(literal):
    source = PREFIX + "ex:answer(?m) :- MIN ?x GROUP_BY() FROM ex:input(?x) AS ?m."
    with QueryRuntime(source, backend="native") as runtime:
        first = runtime.evaluate({EX.input: {(Literal(1),)}}, scope=SCOPE)
        with pytest.raises(DomainError):
            runtime.evaluate({EX.input: {(literal,)}}, scope=SCOPE)
        assert runtime.last_complete is first and not runtime.complete


@pytest.mark.parametrize("option,value,match", [("max_bindings", 3, "max_bindings"),
                                                ("max_rows", 8, "max_rows"),
                                                ("max_native_work", 10, "max_native_work")])
def test_native_work_and_cross_product_limits_are_atomic(option, value, match):
    source = PREFIX + "ex:answer(?x, ?y) :- ex:input(?x), ex:input(?y)."
    with QueryRuntime(source, backend="native", **{option: value}) as runtime:
        good = runtime.evaluate({EX.input: set()}, scope=SCOPE)
        with pytest.raises(QueryExecutionError, match=match):
            runtime.evaluate({EX.input: {(Literal(i),) for i in range(4)}}, scope=SCOPE)
        assert runtime.last_complete is good and not runtime.complete


def test_provider_plans_report_hybrid_mode_explicitly():
    source = PREFIX + "ex:answer(?y) :- ex:input(?x), bind ex:provider(?x) as ?y."
    provider = FakeProvider({str(EX.provider): lambda n: Literal(int(n) + 1)})
    registry = ProviderRegistry()
    registry.register(EX.provider, provider, input_types=("integer",), result_type="integer")
    with QueryRuntime(source, backend="native", providers=registry) as runtime:
        assert runtime.explain()["execution"]["mode"] == "hybrid"
        assert runtime.evaluate({EX.input: {(Literal(1),)}}, scope=SCOPE).rows(EX.answer) == {(Literal(2),)}
        assert runtime.stats["execution_mode"] == "hybrid" and runtime.stats["hybrid_reasons"]


def test_native_source_rows_remain_resident_across_changed_query_inputs():
    source = PREFIX + "ex:answer(?x) :- ex:input(?x)."
    with QueryRuntime(source, backend="native", cache_size=0) as runtime:
        static = {(Literal(i),) for i in range(100)}
        runtime.evaluate({EX.static: static, EX.input: {(EX.a,)}}, scope=SCOPE)
        handle = runtime._native_query.handle.value
        runtime.evaluate({EX.static: static, EX.input: {(EX.b,)}}, scope=SCOPE)
        assert runtime._native_query.handle.value == handle
        assert runtime.stats["input_additions"] == runtime.stats["input_removals"] == 1
        assert runtime.stats["native_term_metadata_rows"] >= 100


def test_c_abi_rejects_unsafe_head_without_host_planner_and_hides_partial_results():
    lib, handle = _library(), c.c_void_p()
    limits = _Limits(100, 100, 20, 100, 1000)
    assert lib.dlp_qx_new(c.byref(limits), c.byref(handle)) == 0
    try:
        assert lib.dlp_qx_begin(handle) == 0
        seed = (c.c_uint64 * 1)(0)
        head = (_Arg * 1)(_Arg(0, 0))
        assert lib.dlp_qx_rule(handle, 0, 1, 1, head, 1, seed, None, 0) == 0
        assert lib.dlp_qx_run(handle, _CONTROL(lambda _: 0), None) == -1
        assert b"unsafe" in lib.dlp_qx_last_error()
        out, count, done = (c.c_uint64 * 1)(), c.c_size_t(), c.c_int()
        assert lib.dlp_qx_result(handle, 1, 1, 0, out, 1, c.byref(count), c.byref(done)) == -1
        assert count.value == 0
    finally:
        lib.dlp_qx_free(handle)


def test_c_abi_rejects_recursive_value_generation_without_host_planner():
    lib, handle = _library(), c.c_void_p()
    assert lib.dlp_qx_new(c.byref(_Limits(100, 100, 20, 100, 1000)), c.byref(handle)) == 0
    try:
        assert lib.dlp_qx_begin(handle) == 0
        assert lib.dlp_qx_term(handle, 1, c.byref(_Value(tag=2, a=1)), 0, 1, 1, 1) == 0
        head, args = (_Arg * 1)(_Arg(1, 0)), (_Arg * 1)(_Arg(0, 0))
        op_args = (_Arg * 2)(_Arg(0, 0), _Arg(-1, 1))
        body = (_Node * 2)(_Node(kind=0, predicate=1, arity=1, args=args),
                          _Node(kind=4, opcode=20, arity=2, args=op_args, output=_Arg(1, 0)))
        assert lib.dlp_qx_rule(handle, 0, 1, 1, head, 2, (c.c_uint64 * 2)(0, 0), body, 2) == 0
        assert lib.dlp_qx_run(handle, _CONTROL(lambda _: 0), None) == -1
        assert b"preceding complete stratum" in lib.dlp_qx_last_error()
    finally:
        lib.dlp_qx_free(handle)


def test_native_cancel_callback_runs_during_join_work_and_keeps_old_answer(monkeypatch):
    source = PREFIX + "ex:answer(?x, ?y) :- ex:input(?x), ex:input(?y)."
    token = CancellationToken()
    with QueryRuntime(source, backend="native", cache_size=0) as runtime:
        first = runtime.evaluate({EX.input: set()}, scope=SCOPE)
        original, calls = runtime._check_budget, []
        def check(count):
            calls.append(None)
            # Input consumption accounts for100 calls. Subsequent checks enter
            # compiled execution and then its periodic control callback.
            if len(calls) > 110:
                token.cancel()
            return original(count)
        monkeypatch.setattr(runtime, "_check_budget", check)
        with pytest.raises(QueryExecutionError, match="cancel"):
            runtime.evaluate({EX.input: {(Literal(i),) for i in range(100)}}, scope=SCOPE, cancel=token)
        assert runtime.last_complete is first and not runtime.complete


def test_equal_minimum_values_choose_deterministic_original_rdf_identity():
    source = PREFIX + "ex:answer(?m) :- MIN ?x GROUP_BY() FROM ex:input(?x) AS ?m."
    plain = Literal("1", datatype=XSD.integer, normalize=False)
    decimal = Literal("1.0", datatype=XSD.decimal, normalize=False)
    alternate = Literal("01.00", datatype=XSD.decimal, normalize=False)
    result = differential(source, [{EX.input: {(plain,), (decimal,), (alternate,)}}])[0]
    assert result.rows(EX.answer) == {(alternate,)}


def test_generated_minimum_ties_with_noncanonical_rdf_input():
    source = PREFIX + """
        ex:values(?y) :- ex:seed(?x), bind n:add(?x, 1) as ?y.
        ex:values(?x) :- ex:input(?x).
        ex:answer(?m) :- MIN ?x GROUP_BY() FROM ex:values(?x) AS ?m.
    """
    alternate = Literal("02", datatype=XSD.integer, normalize=False)
    result = differential(source, [{EX.seed: {(Literal(1),)}, EX.input: {(alternate,)}}])[0]
    assert result.rows(EX.answer) == {(alternate,)}


@pytest.mark.parametrize("backend", ["python", "native"])
def test_explicit_negative_relation_is_symmetric(backend):
    source = PREFIX + """prefix core: <urn:dlp:internal:>
        ex:answer(?x, ?y) :- ex:pair(?x, ?y), core:neq(?x, ?y)."""
    with QueryRuntime(source, backend=backend) as runtime:
        result = runtime.evaluate({EX.pair: {(EX.b, EX.a)}, URIRef(NEQ): {(EX.a, EX.b)}}, scope=SCOPE)
        assert result.rows(EX.answer) == {(EX.b, EX.a)}


def test_c_abi_reentrant_run_rejection_does_not_clear_outer_candidate():
    lib, handle = _library(), c.c_void_p()
    assert lib.dlp_qx_new(c.byref(_Limits(100, 100, 20, 100, 1000)), c.byref(handle)) == 0
    callbacks = []
    @_CONTROL
    def control(_):
        callbacks.append(lib.dlp_qx_run(handle, _CONTROL(lambda _: 0), None))
        return 0
    try:
        assert lib.dlp_qx_begin(handle) == 0
        assert lib.dlp_qx_run(handle, control, None) == 0
        assert callbacks and all(code == -1 for code in callbacks)
        output, count, done = (c.c_uint64 * 1)(), c.c_size_t(), c.c_int()
        assert lib.dlp_qx_result(handle, 1, 1, 0, output, 1, c.byref(count), c.byref(done)) == 0
    finally:
        lib.dlp_qx_free(handle)


def test_c_abi_failed_source_mutation_is_poisoned_until_rebuilt():
    lib, handle = _library(), c.c_void_p()
    assert lib.dlp_qx_new(c.byref(_Limits(100, 100, 20, 100, 1000)), c.byref(handle)) == 0
    try:
        assert lib.dlp_qx_rows(handle, 1, 1, (c.c_uint64 * 2)(1, 0), 2, 1) == -1
        assert lib.dlp_qx_begin(handle) == -1
        assert b"poisoned" in lib.dlp_qx_last_error()
    finally:
        lib.dlp_qx_free(handle)


@pytest.mark.parametrize("backend", ["python", "native"])
def test_raw_equal_values_do_not_alias_query_cache_or_scalar_type_checks(backend):
    source = PREFIX + "ex:answer(?y) :- ex:input(?x), bind n:add(?x, 1) as ?y."
    with QueryRuntime(source, backend=backend) as runtime:
        good = runtime.evaluate({EX.input: {(1,)}}, scope=SCOPE)
        assert good.rows(EX.answer) == {(Literal(2),)}
        with pytest.raises(DomainError):
            runtime.evaluate({EX.input: {(True,)}}, scope=SCOPE)
        assert runtime.last_complete is good and not runtime.complete
        assert runtime.cache_hits == 0


def test_mixed_equal_raw_carriers_use_python_indexes_and_report_fallback():
    source = PREFIX + "ex:answer(?y) :- ex:input(?x), bind n:add(?x, 1) as ?y."
    with QueryRuntime(source, backend="native", cache_size=0) as runtime:
        actual = runtime.evaluate({EX.aux: {(True,)}, EX.input: {(1,)}}, scope=SCOPE)
        assert actual.rows(EX.answer) == {(Literal(2),)}
        assert runtime.stats["execution_mode"] == "hybrid"
        assert "Python relation indexes" in runtime.stats["hybrid_reasons"][0]
        assert runtime._index_mode == "python"


def test_native_pod_memo_reuses_across_rounds_and_queries_with_byte_budget():
    source = PREFIX + "ex:answer(?y) :- ex:input(?x), bind n:add(?x, 1) as ?y."
    with QueryRuntime(source, backend="native", cache_size=0,
                      max_operation_cache_bytes=1500) as runtime:
        inputs = {EX.input: {(Literal(1),)}}
        runtime.evaluate(inputs, scope=SCOPE)
        assert runtime.stats["domain_evaluations"] == 1 and runtime.stats["memo_hits"] == 1
        runtime.evaluate(inputs, scope=SCOPE)
        assert runtime.stats["domain_evaluations"] == 0 and runtime.stats["memo_hits"] == 2
        for number in range(10):
            runtime.evaluate({EX.input: {(Literal(number),)}}, scope=SCOPE)
            assert runtime.cache_info()["native_operations"]["estimated_bytes"] <= 1500
        assert runtime.stats["memo_evictions"] > 0
        assert runtime.cache_info()["operations"]["entries"] == 0
        runtime.clear_cache()
        assert runtime.cache_info()["native_operations"]["entries"] == 0


def test_tiny_native_memo_budget_bypasses_without_truncating_answers():
    source = PREFIX + "ex:answer(?y) :- ex:input(?x), bind n:add(?x, 1) as ?y."
    with QueryRuntime(source, backend="native", cache_size=0, max_operation_cache_bytes=1) as runtime:
        assert runtime.evaluate({EX.input: {(Literal(1),)}}, scope=SCOPE).rows(EX.answer) == {(Literal(2),)}
        assert runtime.stats["memo_entries"] == 0 and runtime.stats["memo_bypasses"] == 2


@pytest.mark.parametrize("unit,code", [("unknown", "UNAVAILABLE"), (3, "TYPE_ERROR"),
                                        (Literal(3), "UNAVAILABLE")])
def test_native_quantity_unit_failure_codes_match_reference(unit, code):
    source = PREFIX + "ex:answer(?q) :- ex:input(?u), bind n:quantity(1, ?u) as ?q."
    for backend in ("python", "native"):
        with QueryRuntime(source, backend=backend) as runtime:
            with pytest.raises(DomainError) as failure:
                runtime.evaluate({EX.input: {(unit,)}}, scope=SCOPE)
            assert failure.value.code == code


def test_unit_lexical_coercion_does_not_replace_generic_literal_decoding():
    malformed = Literal("metre", datatype=XSD.integer, normalize=False)
    quantity = PREFIX + "ex:answer(?q) :- ex:input(?u), bind n:quantity(1, ?u) as ?q."
    assert differential(quantity, [{EX.input: {(malformed,)}}])[0].rows(EX.answer)
    numeric = PREFIX + "ex:answer(?q) :- ex:input(?u), bind n:add(1, ?u) as ?q."
    for backend in ("python", "native"):
        with QueryRuntime(numeric, backend=backend) as runtime:
            with pytest.raises(DomainError) as failure:
                runtime.evaluate({EX.input: {(malformed,)}}, scope=SCOPE)
            assert failure.value.code == "DOMAIN_ERROR"
