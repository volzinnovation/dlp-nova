"""Independent regression controls for snapshot publication and scope identity."""
import time

import pytest
from rdflib import BNode, Graph, Literal, Namespace, RDF, URIRef
from rdflib.namespace import OWL, XSD

from dlp_reasoner import Reasoner
from dlp_reasoner.domains import DomainRegistry
from dlp_reasoner.query_runtime import QueryExecutionError, QueryRuntime, QueryScope
from dlp_reasoner.scoped_views import BirthDateView, CompletenessCertificate, LocationView

EX = Namespace("urn:review:")
SCOPE = QueryScope("urn:review:scope", "1")


@pytest.mark.parametrize("backend", ["python", "native"])
def test_cache_hit_rechecks_source_revision_after_input_consumption(backend):
    reasoner = Reasoner(Graph().add((EX.a, RDF.type, EX.Input)), backend=backend)
    source = """version 1
    prefix ex: <urn:review:>
    ex:answer(?x) :- ex:Input(?x).
    """
    with QueryRuntime(source, reasoner=reasoner, backend=backend) as runtime:
        first = runtime.evaluate({EX.aux: {(EX.a,)}}, scope=SCOPE)
        assert first.rows(EX.answer) == {(EX.a,)}

        def updating_rows():
            reasoner.update(add=[(EX.b, RDF.type, EX.Input)])
            yield (EX.a,)

        with pytest.raises(QueryExecutionError, match="snapshot changed"):
            runtime.evaluate({EX.aux: updating_rows()}, scope=SCOPE)
        assert not runtime.complete and runtime.last_complete is first
        current = runtime.evaluate({EX.aux: {(EX.a,)}}, scope=SCOPE)
        assert current.rows(EX.answer) == {(EX.a,), (EX.b,)}


def test_final_false_filter_checks_deadline_before_publication(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    registry = DomainRegistry()
    evaluate = registry.evaluate_batch

    def delayed(operation, rows):
        result = evaluate(operation, rows)
        clock[0] = 10.0
        return result

    monkeypatch.setattr(registry, "evaluate_batch", delayed)
    source = """version 1
    prefix ex: <urn:review:>
    prefix num: <urn:dlp:numeric:>
    ex:answer(?x) :- ex:input(?x), filter num:lessThan(1, 0).
    """
    with QueryRuntime(source, domains=registry) as runtime:
        with pytest.raises(QueryExecutionError, match="deadline"):
            runtime.evaluate({EX.input: {(EX.a,)}}, scope=SCOPE, deadline=5.0)
        assert not runtime.complete and runtime.last_complete is None


@pytest.mark.parametrize("backend", ["python", "native"])
def test_equivalent_location_nodes_are_one_selected_location(backend):
    graph = Graph()
    for triple in ((EX.sign, RDF.type, EX.Sign), (EX.sign, EX.location, EX.nodeA),
                   (EX.nodeA, OWL.sameAs, EX.nodeB),
                   (EX.nodeA, EX.latitude, Literal("49.0", datatype=XSD.decimal)),
                   (EX.nodeA, EX.longitude, Literal("8.0", datatype=XSD.decimal))):
        graph.add(triple)
    reasoner = Reasoner(graph, backend=backend)
    view = LocationView(reasoner, sign_class=EX.Sign, location_property=EX.location,
                        latitude_property=EX.latitude, longitude_property=EX.longitude,
                        validated_property=EX.validated)
    result = view.prepare(DomainRegistry(backend=backend))
    assert result.relations[EX.validated] == {(EX.sign, reasoner.engine.normalize(EX.nodeA))}
    assert not result.diagnostics


def test_birth_certificate_fingerprint_preserves_rdf_node_identity():
    child = URIRef("urn:review:child")
    replacement = BNode(str(child))
    parent_date = Literal("1980-01-01", datatype=XSD.date)
    child_date = Literal("2000-01-01", datatype=XSD.date)
    old = [(EX.parent, EX.child, child), (child, EX.birth, child_date)]
    graph = Graph().add((EX.parent, EX.birth, parent_date))
    for triple in old:
        graph.add(triple)
    reasoner = Reasoner(graph)
    view = BirthDateView(reasoner, child_property=EX.child, birth_property=EX.birth,
                         accepted_property=EX.accepted, certificate_property=EX.certificate,
                         trusted_issuers={"review-fixture"})
    digest = view.evidence_digest(EX.parent)
    certificate = CompletenessCertificate(EX.parent, SCOPE, digest, "review-fixture")
    assert view.prepare(SCOPE, certificates=[certificate]).relations[EX.certificate]
    reasoner.update(remove=old, add=[(EX.parent, EX.child, replacement),
                                    (replacement, EX.birth, child_date)])
    assert view.evidence_digest(EX.parent) != digest
    selected = view.prepare(SCOPE, certificates=[certificate])
    assert not selected.relations[EX.certificate]
    assert any(d.code == "stale_certificate" for d in selected.diagnostics)


@pytest.mark.parametrize("backend", ["python", "native"])
def test_explicit_inequality_input_matches_iri_and_engine_internal_keys(backend):
    from dlp_reasoner.model import NEQ
    source = """version 1
    prefix ex: <urn:review:>
    prefix core: <urn:dlp:internal:>
    ex:answer(?x, ?y) :- ex:pair(?x, ?y), core:neq(?x, ?y).
    """
    with QueryRuntime(source, backend=backend) as runtime:
        result = runtime.evaluate({EX.pair: {(EX.a, EX.b)}, URIRef(NEQ): {(EX.a, EX.b)}}, scope=SCOPE)
        assert result.rows(EX.answer) == {(EX.a, EX.b)}


def test_input_row_budget_stops_consumption_early():
    consumed = []

    def rows():
        for index in range(30):
            consumed.append(index)
            yield (Literal(index),)

    source = """version 1
    prefix ex: <urn:review:>
    ex:answer(?x) :- ex:input(?x).
    """
    with QueryRuntime(source, max_rows=3) as runtime:
        with pytest.raises(QueryExecutionError, match="max_rows"):
            runtime.evaluate({EX.input: rows()}, scope=SCOPE)
        assert len(consumed) == 4
