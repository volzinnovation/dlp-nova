"""Stable ontology selection reuse and failure boundaries before querying."""
import pytest
from rdflib import Graph, Literal, Namespace, RDF, XSD

from dlp_reasoner import Reasoner
from dlp_reasoner.domains import DomainError, DomainRegistry
from dlp_reasoner.query_runtime import QueryScope
from dlp_reasoner.scoped_views import BirthDateView, LocationView


EX = Namespace("urn:selection:")


def test_birth_selection_reuses_one_revision_and_retracts_conflicting_date():
    graph = Graph().add((EX.parent, EX.child, EX.child1))
    graph.add((EX.parent, EX.birth, Literal("1980-01-01", datatype=XSD.date)))
    graph.add((EX.child1, EX.birth, Literal("2000-01-01", datatype=XSD.date)))
    reasoner = Reasoner(graph)
    view = BirthDateView(reasoner, child_property=EX.child, birth_property=EX.birth,
                         accepted_property=EX.accepted, certificate_property=EX.certificate)
    scope = QueryScope("urn:selection:scope", "1")
    assert len(view.prepare(scope).relations[EX.accepted]) == 2
    for revision in range(10):
        assert len(view.prepare(QueryScope(scope.name, str(revision))).relations[EX.accepted]) == 2
    assert view.stats == {"selection_builds": 1, "selection_cache_hits": 10}
    conflict = (EX.child1, EX.birth, Literal("2001-01-01", datatype=XSD.date))
    reasoner.update(add=[conflict])
    selected = view.prepare(scope)
    assert len(selected.relations[EX.accepted]) == 1
    assert view.stats["selection_builds"] == 2
    reasoner.update(remove=[conflict])
    assert len(view.prepare(scope).relations[EX.accepted]) == 2
    assert view.stats["selection_builds"] == 3


def test_unavailable_geometry_operation_is_not_missing_location_data():
    graph = Graph().add((EX.sign, RDF.type, EX.Sign)).add((EX.sign, EX.location, EX.node))
    graph.add((EX.node, EX.lat, Literal(0))).add((EX.node, EX.lon, Literal(0)))
    view = LocationView(Reasoner(graph), sign_class=EX.Sign, location_property=EX.location,
                        latitude_property=EX.lat, longitude_property=EX.lon,
                        validated_property=EX.validated)
    registry = DomainRegistry()
    registry.close()
    with pytest.raises(DomainError, match="closed"):
        view.prepare(registry)
