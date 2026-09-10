"""Retained query memory has byte/term budgets independent of answer semantics."""
import gc
import weakref

import pytest
from rdflib import Graph, Literal, URIRef

from dlp_reasoner import Reasoner
from dlp_reasoner.domains import DomainError, DomainRegistry, DomainResult, Operation
from dlp_reasoner.engine import _MISSING
from dlp_reasoner.joins import RelationalPlan
from dlp_reasoner.model import Atom, Rule, Var
from dlp_reasoner.query_runtime import QueryExecutionError, QueryRuntime, QueryScope

SOURCE = "version 1 prefix ex: <urn:resource:> ex:answer(?x) :- ex:input(?x)."
INPUT, ANSWER = URIRef("urn:resource:input"), URIRef("urn:resource:answer")
SCOPE = QueryScope("urn:resource:scope", "1")


@pytest.fixture(params=["python", "native"])
def backend(request):
    return request.param


def test_tiny_query_cache_budget_evicts_and_oversized_answers_bypass(backend):
    with QueryRuntime(SOURCE, backend=backend, cache_size=100, max_cache_bytes=80_000) as runtime:
        for value in range(5):
            result = runtime.evaluate({INPUT: {(Literal(value),)}}, scope=SCOPE)
            assert result.rows(ANSWER) == {(Literal(value),)}
            assert runtime.cache_info()["results"]["estimated_bytes"] <= 80_000
        info = runtime.cache_info()["results"]
        assert info["evictions"] >= 1 and 0 < info["entries"] < 5
        before = runtime.cache_hits
        assert runtime.evaluate({INPUT: {(Literal(4),)}}, scope=SCOPE).rows(ANSWER) == {(Literal(4),)}
        assert runtime.cache_hits == before + 1
        huge = Literal("x" * 200_000)
        result = runtime.evaluate({INPUT: {(huge,)}}, scope=SCOPE)
        assert result.rows(ANSWER) == {(huge,)}
        assert runtime.cache_info()["results"]["bypasses"] >= 1
        runtime.evaluate({INPUT: {(huge,)}}, scope=SCOPE)
        assert runtime.cache_hits == before + 1


class EchoDomains:
    def __init__(self):
        self.operation = Operation("urn:resource:echo", "1", ("any",), "any", (0,))
        self.operations = {self.operation.uri: self.operation}
        self.calls = 0

    def get(self, uri):
        return self.operations[str(uri)]

    def evaluate_batch(self, uri, rows):
        self.calls += len(rows)
        return tuple(DomainResult(row[0]) for row in rows)


def test_operation_cache_budgets_keys_results_and_skips_huge_values(backend):
    domains = EchoDomains()
    source = """version 1 prefix ex: <urn:resource:>
        ex:answer(?y) :- ex:input(?x), bind ex:echo(?x) as ?y."""
    with QueryRuntime(source, backend=backend, domains=domains, cache_size=0,
                      operation_cache_size=100, max_operation_cache_bytes=5500) as runtime:
        for number in range(5):
            runtime.evaluate({INPUT: {(Literal(number),)}}, scope=SCOPE)
        info = runtime.cache_info()["operations"]
        assert info["hits"] > 0 and info["evictions"] > 0
        assert info["estimated_bytes"] <= 5500 and info["entries"] < 5
        calls = domains.calls
        runtime.evaluate({INPUT: {(Literal(4),)}}, scope=SCOPE)
        assert domains.calls == calls
        huge = Literal("y" * 30_000)
        for _ in range(2):
            assert runtime.evaluate({INPUT: {(huge,)}}, scope=SCOPE).rows(ANSWER) == {(huge,)}
        assert domains.calls > calls and runtime.cache_info()["operations"]["bypasses"] > 0
        assert runtime.cache_info()["operations"]["estimated_bytes"] <= 5500


def test_cache_zero_bytes_disables_retention_and_clear_preserves_counters(backend):
    with QueryRuntime(SOURCE, backend=backend, max_cache_bytes=0,
                      max_operation_cache_bytes=0) as runtime:
        for _ in range(2):
            assert runtime.evaluate({INPUT: {(Literal(1),)}}, scope=SCOPE).rows(ANSWER) == {(Literal(1),)}
        assert runtime.cache_info()["results"]["entries"] == 0
        assert runtime.cache_info()["results"]["bypasses"] == 2
        runtime.clear_cache()
        assert runtime.cache_info()["results"]["bypasses"] == 2


def test_unknown_hashable_terms_are_executable_but_not_retained_in_caches(backend):
    class Custom:
        def __init__(self):
            self.payload = bytearray(100_000)
    value = Custom()
    with QueryRuntime(SOURCE, backend=backend) as runtime:
        assert runtime.evaluate({INPUT: {(value,)}}, scope=SCOPE).rows(ANSWER) == {(value,)}
        assert runtime.cache_info()["results"]["entries"] == 0
        assert runtime.cache_info()["results"]["bypasses"] == 1


def test_cached_revisions_do_not_pin_old_graph_or_engine_owners(backend):
    graph = Graph().parse(data='@prefix ex: <urn:resource:> . ex:a a ex:input .', format="turtle")
    reasoner = Reasoner(graph, backend=backend)
    with QueryRuntime(SOURCE, reasoner=reasoner, backend=backend) as runtime:
        runtime.evaluate(scope=SCOPE)
        graph_ref, engine_ref, reasoner_ref = weakref.ref(reasoner.graph), weakref.ref(reasoner.engine), weakref.ref(reasoner)
        runtime.reasoner = Reasoner(Graph(), backend=backend)
        del reasoner
        runtime.evaluate(scope=SCOPE)
        gc.collect()
        assert reasoner_ref() is None and engine_ref() is None and graph_ref() is None
        assert runtime.cache_info()["results"]["entries"] == 2


def test_native_dictionary_compacts_across_revisions_old_answers_stay_frozen():
    static = URIRef("urn:resource:static")
    common = {(URIRef(f"urn:fixed:{i}"),) for i in range(10)}
    snapshots = []
    with QueryRuntime(SOURCE, backend="native", max_terms=24, max_native_terms=48,
                      cache_size=2) as native, QueryRuntime(SOURCE, backend="python") as python:
        initial_context = None
        initial_handle = None
        for number in range(90):
            rows = {INPUT: {(Literal(number),)}, static: common}
            actual = native.evaluate(rows, scope=SCOPE)
            expected = python.evaluate(rows, scope=SCOPE)
            assert actual.relations == expected.relations
            snapshots.append(actual)
            info = native.cache_info()
            assert info["native_dictionary_entries"] <= 48
            if number == 0:
                initial_context, initial_handle = native._native, native._index._handle.value
            if number == 1:
                assert native._native is initial_context
                assert native._index._handle.value == initial_handle
                assert native.stats["index_additions"] == 1
                assert native.stats["index_removals"] == 2
        assert native.cache_info()["native_compactions"] > 0
        assert all(snapshot.rows(ANSWER) == {(Literal(i),)} for i, snapshot in enumerate(snapshots))


def test_current_term_limit_fails_before_publication_and_recovers(backend):
    with QueryRuntime(SOURCE, backend=backend, max_terms=8, max_native_terms=16) as runtime:
        first = runtime.evaluate({INPUT: {(Literal(1),)}}, scope=SCOPE)
        with pytest.raises(QueryExecutionError, match="max_terms"):
            runtime.evaluate({INPUT: {(Literal(i),) for i in range(20)}}, scope=SCOPE)
        assert not runtime.complete and runtime.last_complete is first
        assert len(runtime._current_terms) + len(runtime._current_predicates) <= 8
        assert runtime.evaluate({INPUT: {(Literal(1),)}}, scope=SCOPE).relations == first.relations


def test_generated_terms_cannot_bypass_current_term_budget(backend):
    source = """version 1 prefix ex: <urn:resource:> prefix n: <urn:dlp:numeric:>
        ex:answer(?y) :- ex:input(?x), bind n:add(?x, 1000) as ?y."""
    with QueryRuntime(source, backend=backend, max_terms=10, max_native_terms=20) as runtime:
        first = runtime.evaluate({INPUT: {(Literal(1),)}}, scope=SCOPE)
        with pytest.raises(QueryExecutionError, match="max_terms"):
            runtime.evaluate({INPUT: {(Literal(i),) for i in range(4)}}, scope=SCOPE)
        assert not runtime.complete and runtime.last_complete is first
        assert runtime.cache_info()["native_dictionary_entries"] <= 20


def test_compaction_never_closes_a_context_with_an_active_query_cursor():
    with QueryRuntime(SOURCE, backend="native", max_terms=8, max_native_terms=8,
                      cache_size=0) as runtime:
        runtime.evaluate({INPUT: {(Literal(1),)}}, scope=SCOPE)
        context = runtime._native
        plan = RelationalPlan(Rule(None, (Atom(INPUT, (Var("x"),)),)))
        cursor = runtime._index.solutions(plan, runtime, _MISSING)
        next(cursor)
        try:
            with pytest.raises(QueryExecutionError, match="active cursors"):
                runtime.evaluate({INPUT: {(Literal(2),)}}, scope=SCOPE)
            assert runtime._native is context and not context._closed
        finally:
            cursor.close()
        assert runtime.evaluate({INPUT: {(Literal(2),)}}, scope=SCOPE).rows(ANSWER) == {(Literal(2),)}


@pytest.mark.parametrize("options", [{"max_cache_bytes": -1}, {"max_operation_cache_bytes": True},
                                     {"max_terms": 0}, {"max_native_terms": False}])
def test_invalid_resource_settings(options):
    with pytest.raises(ValueError):
        QueryRuntime(SOURCE, **options)


def test_duplicate_input_stream_has_an_independent_consumption_budget(backend):
    consumed = []
    def rows():
        while True:
            consumed.append(None)
            yield (Literal(1),)
    with QueryRuntime(SOURCE, backend=backend, max_input_rows=7) as runtime:
        with pytest.raises(QueryExecutionError, match="max_input_rows"):
            runtime.evaluate({INPUT: rows()}, scope=SCOPE)
        assert len(consumed) == 8 and runtime.last_complete is None


def test_closed_shared_domain_registry_cannot_reuse_a_warm_query_answer(backend):
    domains = DomainRegistry(backend=backend)
    source = """version 1 prefix ex: <urn:resource:> prefix n: <urn:dlp:numeric:>
        ex:answer(?y) :- ex:input(?x), bind n:add(?x, 1) as ?y."""
    with QueryRuntime(source, backend=backend, domains=domains) as runtime:
        first = runtime.evaluate({INPUT: {(Literal(1),)}}, scope=SCOPE)
        domains.close()
        with pytest.raises(DomainError, match="closed"):
            runtime.evaluate({INPUT: {(Literal(1),)}}, scope=SCOPE)
        assert runtime.last_complete is first and not runtime.complete


def test_runtime_closes_only_its_owned_domain_registry(backend):
    owned = QueryRuntime(SOURCE, backend=backend)
    owned.close()
    assert owned.domains._closed
    domains = DomainRegistry(backend=backend)
    shared = QueryRuntime(SOURCE, backend=backend, domains=domains)
    shared.close()
    assert not domains._closed
    domains.close()
