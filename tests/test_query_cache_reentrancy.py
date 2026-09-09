"""Queries observed during an update must not survive its success or failure."""

import shutil

import pytest
from rdflib import Graph, Namespace, OWL, RDF

from dlp_reasoner import Reasoner
from dlp_reasoner.model import Atom


EX = Namespace("urn:query-cache-reentrancy:")


@pytest.fixture(params=["python", "native"])
def reasoner(request):
    if request.param == "native" and not any(
            shutil.which(name) for name in ("clang++", "g++", "c++")):
        pytest.skip("Native backend requires an available C++17 compiler")
    graph = Graph()
    graph.add((EX.A, RDF.type, OWL.Class))
    graph.add((EX.a, RDF.type, OWL.NamedIndividual))
    result = Reasoner(graph, backend=request.param)
    try:
        yield result
    finally:
        if result.engine._native_context is not None:
            result.engine._native_context.close()


def test_successful_update_discards_reentrant_answers_and_views(reasoner, monkeypatch):
    original = reasoner.engine.update
    observations = []

    def observed_update(*args, **kwargs):
        # This callback runs after Reasoner.update's initial cache clear but
        # before the engine applies the new assertion.
        observations.append(reasoner.instances(EX.A))
        assert EX.A not in reasoner.types(EX.a)
        return original(*args, **kwargs)

    monkeypatch.setattr(reasoner.engine, "update", observed_update)
    reasoner.update(add=[(EX.a, RDF.type, EX.A)])

    assert observations == [set()]
    assert reasoner.instances(EX.A) == {EX.a}
    assert EX.A in reasoner.types(EX.a)
    assert reasoner.entails(EX.a, RDF.type, EX.A)


def test_failed_update_discards_answers_from_before_partial_mutation(reasoner, monkeypatch):
    original = reasoner.engine._store
    observations = []

    def failing_store(fact, delta):
        if fact == Atom(EX.A, (EX.a,)):
            # Cache the old answer after the engine has entered its new
            # revision, then fail after changing the corresponding relation.
            observations.append(reasoner.instances(EX.A))
            assert EX.A not in reasoner.types(EX.a)
            original(fact, delta)
            raise RuntimeError("injected failure after storing a new assertion")
        return original(fact, delta)

    monkeypatch.setattr(reasoner.engine, "_store", failing_store)
    with pytest.raises(RuntimeError, match="injected failure"):
        reasoner.update(add=[(EX.a, RDF.type, EX.A)])

    assert observations == [set()]
    assert Atom(EX.A, (EX.a,)) in reasoner.engine.facts
    # The cache must agree with the surviving engine state even though the
    # interrupted operation did not commit the RDF source graph.
    assert (EX.a, RDF.type, EX.A) not in reasoner.graph
    assert reasoner.instances(EX.A) == {EX.a}
    assert EX.A in reasoner.types(EX.a)
    assert reasoner.entails(EX.a, RDF.type, EX.A)
