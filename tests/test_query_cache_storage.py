"""Storage bounds and RDF mutation routes for the reasoner's answer cache."""
import tracemalloc

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.store import TripleAddedEvent

from dlp_reasoner.model import Skolem
from dlp_reasoner.query_cache import AnswerCache, CACHE_MISS, RevisionMemory


S, P, OBJ = map(URIRef, ("urn:subject", "urn:predicate", "urn:object"))


def test_boolean_false_empty_set_and_miss_are_distinct():
    cache = AnswerCache()
    assert cache.get("absent") is CACHE_MISS
    assert cache.put("false", False)
    assert cache.put("empty", frozenset())
    assert cache.get("false") is False
    assert cache.get("empty") == set()
    assert cache.info()["hits"] == 2
    assert cache.info()["misses"] == 1


def test_answers_and_information_are_defensive_copies():
    cache = AnswerCache()
    original = frozenset({S, OBJ})
    cache.put(("instances", P), original)
    answer = cache.get(("instances", P))
    answer.clear()
    assert cache.get(("instances", P)) == original
    info = cache.info()
    info["hits"] = -1
    assert cache.info()["hits"] == 2
    supplied = {S, OBJ}
    assert cache.put("mutable", supplied)
    supplied.clear()
    assert cache.get("mutable") == {S, OBJ}
    with pytest.raises(TypeError, match="bool, set, or frozenset"):
        cache.put("invalid", [S])


def test_entry_budget_evicts_least_recently_used_including_read_access():
    cache = AnswerCache(max_entries=2)
    cache.put("old", True)
    cache.put("new", False)
    assert cache.get("old") is True
    cache.put("latest", frozenset({S}))
    assert cache.get("new") is CACHE_MISS
    assert cache.get("old") is True
    assert cache.get("latest") == {S}
    assert cache.info()["evictions"] == 1


def test_result_value_budget_and_oversized_replacement_do_not_retain_stale_answers():
    cache = AnswerCache(max_values=3)
    cache.put("first", frozenset({1, 2}))
    cache.put("second", frozenset({3, 4}))
    assert cache.get("first") is CACHE_MISS
    assert cache.info()["values"] == 2
    assert cache.info()["evictions"] == 1
    assert not cache.put("second", frozenset(range(4)))
    assert cache.get("second") is CACHE_MISS
    assert cache.info()["values"] == 0
    assert cache.info()["bypasses"] == 1


def test_estimated_byte_budget_counts_large_keys_and_rdf_literal_values():
    cache = AnswerCache(max_bytes=2048)
    assert cache.put(("instances", S), frozenset({OBJ}))
    assert not cache.put(("instances", URIRef("urn:" + "x" * 4096)), True)
    assert not cache.put("literal", frozenset({Literal("x" * 4096)}))
    assert cache.info()["estimated_bytes"] <= 2048
    assert cache.info()["bypasses"] == 2


def test_byte_budget_evicts_and_shared_nested_terms_do_not_break_estimation():
    cache = AnswerCache(max_bytes=2048)
    witness = Skolem("f", (S,))
    assert cache.put(("pairs", P), frozenset({(S, witness), (OBJ, witness)}))
    for number in range(12):
        assert cache.put(("test", number), frozenset({URIRef("urn:" + "x" * 180)}))
        assert cache.info()["estimated_bytes"] <= 2048
    assert cache.info()["evictions"] > 0


def test_custom_objects_with_unknown_retained_memory_bypass_the_cache():
    class Custom:
        def __init__(self):
            self.payload = "x" * 100_000
    cache = AnswerCache(max_bytes=1024)
    assert not cache.put(("custom", Custom()), True)
    assert cache.info()["entries"] == 0
    assert cache.info()["bypasses"] == 1


def test_scalar_and_container_subclasses_cannot_hide_unbounded_retained_payloads():
    class CustomString(str):
        pass

    class CustomTuple(tuple):
        pass

    cache = AnswerCache(max_bytes=1024)
    for value in (CustomString("short"), CustomTuple(("short",))):
        value.payload = "x" * 100_000
        assert not cache.put(("custom-key", value), True)
        assert not cache.put("custom-value", {value})
    assert cache.info()["entries"] == 0
    assert cache.info()["bypasses"] == 4


@pytest.mark.parametrize("options", [{"max_entries": 0}, {"max_values": 3}, {"max_bytes": 64}])
def test_oversized_or_disabled_mutable_answers_are_not_copied(options):
    cache = AnswerCache(**options)
    answer = set(range(100_000))
    # A frozen copy of this input allocates megabytes. The bypass must allocate
    # only its small accounting objects, regardless of the caller's set size.
    tracemalloc.start()
    try:
        assert not cache.put("large", answer)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 100_000
    assert cache.info()["entries"] == 0


def test_clear_preserves_counters_and_zero_entries_disables_storage():
    cache = AnswerCache()
    cache.put("x", True)
    cache.get("x")
    cache.get("missing")
    cache.clear()
    assert cache.info()["entries"] == cache.info()["values"] == cache.info()["estimated_bytes"] == 0
    assert cache.info()["hits"] == cache.info()["misses"] == 1
    disabled = AnswerCache(max_entries=0)
    assert not disabled.put("x", False)
    assert disabled.get("x") is CACHE_MISS
    assert disabled.info()["entries"] == 0
    assert disabled.info()["bypasses"] == 1


@pytest.mark.parametrize("option", ["max_entries", "max_values", "max_bytes"])
@pytest.mark.parametrize("value", [-1, 1.5, True])
def test_invalid_cache_budgets_are_rejected(option, value):
    with pytest.raises(ValueError, match=option):
        AnswerCache(**{option: value})


def test_revision_changes_for_graph_and_direct_store_writes_including_noops():
    store = RevisionMemory()
    graph = Graph(store=store)
    operations = [lambda: graph.add((S, P, OBJ)), lambda: graph.add((S, P, OBJ)),
                  lambda: graph.set((S, P, Literal("new"))),
                  lambda: graph.remove((S, P, None)),
                  lambda: graph.remove((S, P, None)),
                  lambda: store.add((S, P, OBJ), graph),
                  lambda: store.remove((None, None, None), graph)]
    for operation in operations:
        previous = store.revision
        operation()
        assert store.revision > previous
    assert len(graph) == 0


def test_revision_advances_before_add_event_and_after_actual_insertion():
    store = RevisionMemory()
    graph = Graph(store=store)
    before = store.revision
    observed = []

    def during_add(event):
        observed.append((store.revision, (S, P, OBJ) in graph))

    store.dispatcher.subscribe(TripleAddedEvent, during_add)
    graph.add((S, P, OBJ))
    assert observed[0][0] > before
    assert not observed[0][1]  # RDFLib emits this event before writing indexes.
    assert store.revision > observed[0][0]
    assert (S, P, OBJ) in graph


def test_addn_partial_failure_parse_and_sparql_routes_advance_revision():
    store = RevisionMemory()
    graph = Graph(store=store)

    def broken_quads():
        yield S, P, OBJ, graph
        raise ValueError("partial input")

    before = store.revision
    with pytest.raises(ValueError, match="partial"):
        store.addN(broken_quads())
    assert store.revision > before
    assert (S, P, OBJ) in graph
    before = store.revision
    graph.addN([(S, P, Literal("bulk"), graph)])
    assert store.revision > before
    before = store.revision
    graph.parse(data='<urn:parsed> <urn:predicate> <urn:object> .', format="turtle")
    assert store.revision > before
    before = store.revision
    graph.update('INSERT DATA { <urn:sparql> <urn:predicate> <urn:object> }')
    assert store.revision > before
    assert (URIRef("urn:sparql"), P, OBJ) in graph
    before = store.revision
    graph.update('DELETE WHERE { ?s <urn:predicate> ?o }')
    assert store.revision > before
    assert len(graph) == 0


def test_graph_context_mutations_advance_revision():
    store = RevisionMemory()
    graph = Graph(store=store, identifier=URIRef("urn:context"))
    before = store.revision
    store.add_graph(graph)
    assert store.revision > before
    graph.add((S, P, OBJ))
    before = store.revision
    store.remove_graph(graph)
    assert store.revision > before
    assert len(graph) == 0
