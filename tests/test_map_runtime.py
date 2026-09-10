"""Map/index and ontology publication cannot expose different revisions."""
from pathlib import Path

import pytest
from rdflib import Graph, Literal, RDF, RDFS, URIRef, OWL, XSD

from dlp_reasoner import parse_dlp
from dlp_reasoner.domains import Point
from dlp_reasoner.map_runtime import MapRuntime
from dlp_reasoner.model import InconsistentOntologyError
from dlp_reasoner.osm import OSM, DATA, Change, OSMError


def node(version, longitude):
    return dict(type="node", id=1, version=version, lat=0, lon=longitude)


@pytest.mark.parametrize("backend", ["python", "native"])
def test_map_ontology_and_index_change_together(backend):
    ontology = parse_dlp((Path(__file__).resolve().parents[1] / "examples/osm/ontology.dlp").read_text())
    with MapRuntime(ontology, backend=backend) as runtime:
        old = runtime.load_snapshot([node(1, "0")], source="fixture-v1")
        try:
            identifier = URIRef(DATA + "node/1")
            assert old.reasoner.entails(identifier, RDF.type, OSM.Element)
            assert old.map.point_index.within(Point(0.0, 0.0), 10) == {identifier}
            fresh = runtime.apply_changes([Change("modify", node(2, "0.1"))])
            assert old.scope != fresh.scope
            assert fresh.reasoner.property_values(identifier, OSM.longitude) == {Literal("0.1", datatype=XSD.decimal)}
            assert not fresh.map.point_index.within(Point(0.0, 0.0), 10)
            # The previous publication remains a coherent historical snapshot.
            assert old.map.point_index.within(Point(0.0, 0.0), 10) == {identifier}
            with pytest.raises(OSMError):
                runtime.apply_changes([Change("modify", node(4, "0.2"))])
            assert runtime.snapshot is fresh and not runtime.complete
            fresh.validate()
        finally:
            old.close()


def test_inconsistent_candidate_never_publishes_map_before_ontology():
    # Legal as a schema; asserting any node violates the declared class constraint.
    graph = Graph()
    graph.add((OSM.Node, RDFS.subClassOf, OWL.Nothing))
    with MapRuntime(graph, profile="L2") as runtime:
        old = runtime.load_snapshot([], source="empty")
        with pytest.raises(InconsistentOntologyError):
            runtime.apply_changes([Change("create", node(1, "0"))])
        assert runtime.snapshot is old and not runtime.complete
        assert not old.map.elements
        assert old.validate() is old


def test_input_failure_and_reentrancy_preserve_publication():
    with MapRuntime(Graph()) as runtime:
        old = runtime.load_snapshot([node(1, "0")], source="fixture")

        def changes():
            with pytest.raises(OSMError, match="already running"):
                runtime.apply_changes([])
            yield Change("modify", node(2, "0.1"))
            raise RuntimeError("input interrupted")

        with pytest.raises(RuntimeError, match="interrupted"):
            runtime.apply_changes(changes())
        assert runtime.snapshot is old
        old.validate()


def test_caller_mutation_is_not_a_valid_published_revision():
    with MapRuntime(Graph()) as runtime:
        publication = runtime.load_snapshot([], source="empty")
        publication.reasoner.update(add=[(URIRef("urn:person"), RDF.type, URIRef("urn:Person"))])
        with pytest.raises(OSMError, match="mutated"):
            publication.validate()
