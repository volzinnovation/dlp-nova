from dataclasses import replace
from io import BytesIO
import json
from pathlib import Path

import pytest
from rdflib import Literal, RDF, URIRef

from dlp_reasoner import Reasoner
from dlp_reasoner.osm import (Change, DATA, OSM, OSMError, OSMLimits, OSMStore, PyOsmiumReader,
                              iter_osm_xml, parse_element)
from dlp_reasoner.parser import parse_dlp


FIXTURE = Path(__file__).resolve().parents[1] / "examples/osm/fixture.json"


def fixture():
    return json.loads(FIXTURE.read_text())


def node(identifier=1, version=1, longitude=0, **extra):
    return dict(type="node", id=identifier, version=version, lat=0, lon=longitude) | extra


def way(identifier=1, version=1, nodes=None, **extra):
    return dict(type="way", id=identifier, version=version, nodes=nodes or [1, 2], **extra)


@pytest.mark.parametrize("backend", ["python", "native"])
def test_source_mapping_current_engine_preserves_tags_order_and_route_projection(backend):
    payload = fixture()
    store = OSMStore(backend=backend)
    snapshot = store.load_snapshot(payload["elements"], source=payload["source"])
    graph = snapshot.graph()
    schema = FIXTURE.with_name("ontology.dlp")
    graph += parse_dlp(schema.read_text())
    reasoner = Reasoner(graph, profile="L0", backend=backend)
    roads = {URIRef(DATA + "way/" + str(i)) for i in (1, 2, 4)}
    assert reasoner.instances(OSM.RoadSegment) == roads
    assert reasoner.instances(OSM.RoadRoute) == {URIRef(DATA + "relation/1"), URIRef(DATA + "relation/2")}
    assert reasoner.property_values(URIRef(DATA + "way/1"), OSM.partOfRoad) == {
        URIRef(DATA + "relation/1"), URIRef(DATA + "relation/2")}
    assert not reasoner.property_values(URIRef(DATA + "way/2"), OSM.partOfRoad)
    for record in payload["elements"]:
        element = snapshot.elements[(record["type"], record["id"])]
        assert dict(element.tags) == record.get("tags", {})
        assert len(element.references) == len(record.get("nodes", record.get("members", [])))
        tags = graph.subjects(OSM.ownerElement, element.iri)
        assert {(str(graph.value(t, OSM.tagKey)), str(graph.value(t, OSM.tagValue))) for t in tags} == set(element.tags)
    members = snapshot.elements[("relation", 1)].members
    assert [m.key for m in members] == [("way", 1), ("node", 1), ("way", 1)]
    assert [m.role for m in members] == ["backward", "guidepost", "forward"]
    assert snapshot.elements[("way", 4)].nodes == (2, 3, 2)
    snapshot.point_index.close()


def test_node_move_recomputes_dependent_ways_transitive_relations_only_geometry_reused():
    store = OSMStore()
    original = [node(1), node(2), node(3), node(4), way(), way(2, nodes=[3, 4]),
        dict(type="relation", id=1, version=1, members=[dict(type="way", ref=1, role="")]),
        dict(type="relation", id=2, version=1, members=[dict(type="relation", ref=1, role="")])]
    before = store.load_snapshot(original, source="synthetic")
    after = store.apply_changes([Change("modify", node(1, version=2, longitude=1))])
    assert after.affected == {("node", 1), ("way", 1), ("relation", 1), ("relation", 2)}
    assert after.way_geometries[("way", 1)][0].longitude == 1
    assert after.way_geometries[("way", 2)] is before.way_geometries[("way", 2)]
    assert before.elements[("node", 1)].longitude == 0
    assert after.digest != before.digest and after.revision == before.revision + 1
    assert (before.triples - after.retractions) | after.additions == after.triples


def test_tag_and_membership_edits_retract_importer_projections_atomically():
    payload = fixture()
    store = OSMStore()
    before = store.load_snapshot(payload["elements"], source=payload["source"])
    changed_way = next(e for e in payload["elements"] if e["type"] == "way" and e["id"] == 1)
    changed_way["version"] += 1
    changed_way["tags"]["highway"] = "construction"
    after = store.apply_changes([Change("modify", changed_way)])
    target = URIRef(DATA + "way/1")
    assert (target, RDF.type, OSM.RoadSegment) in before.triples
    assert (target, RDF.type, OSM.RoadSegment) not in after.triples
    assert not any(s == target and p == OSM.partOfRoad for s, p, _ in after.triples)
    changed_way["version"] += 1
    changed_way["tags"]["highway"] = "residential"
    restored = store.apply_changes([Change("modify", changed_way)])
    relation = next(e for e in payload["elements"] if e["type"] == "relation" and e["id"] == 1)
    relation["version"] += 1
    relation["members"] = [dict(type="way", ref=2, role="uninterpreted")]
    final = store.apply_changes([Change("modify", relation)])
    assert (target, OSM.partOfRoad, URIRef(DATA + "relation/1")) in restored.triples
    assert (target, OSM.partOfRoad, URIRef(DATA + "relation/1")) not in final.triples
    assert ("way", 1) in final.affected and ("way", 2) in final.affected
    assert (URIRef(DATA + "way/2"), OSM.partOfRoad, URIRef(DATA + "relation/1")) not in final.triples


@pytest.mark.parametrize("change, code", [
    (Change("modify", node(1, version=1)), "STALE_VERSION"),
    (Change("modify", node(1, version=3)), "STALE_VERSION"),
    (Change("modify", node(9, version=2)), "STALE_VERSION"),
    (Change("create", node(1)), "STALE_VERSION"),
    (Change("create", node(9, version=2)), "STALE_VERSION"),
    (Change("delete", dict(type="node", id=1, version=2)), "MISSING_REFERENCE"),
    (Change("modify", way(version=2, nodes=[1, 99])), "MISSING_REFERENCE"),
])
def test_rejected_changes_leave_exact_prior_snapshot(change, code):
    store = OSMStore()
    before = store.load_snapshot([node(1), node(2), way()], source="v1")
    with pytest.raises(OSMError) as error:
        store.apply_changes([change])
    assert error.value.code == code and store.snapshot is before


def test_create_reference_target_and_delete_references_same_transaction():
    store = OSMStore()
    store.load_snapshot([node(1), node(2), way()], source="v1")
    changed = store.apply_changes([Change("modify", way(version=2, nodes=[1, 3])),
                                   Change("create", node(3)),
                                   Change("delete", dict(type="node", id=2, version=2))])
    assert changed.elements[("way", 1)].nodes == (1, 3)
    assert changed.tombstones[("node", 2)] == 2
    with pytest.raises(OSMError, match="new typed ID"):
        store.apply_changes([Change("create", node(2))])
    assert store.snapshot is changed
    assert store.apply_changes([]) is changed


def test_duplicate_snapshot_and_change_versions_rejected():
    store = OSMStore()
    with pytest.raises(OSMError, match="multiple versions"):
        store.load_snapshot([node(), node(version=2)], source="v1")
    assert store.snapshot is None
    before = store.load_snapshot([node()], source="v1")
    with pytest.raises(OSMError, match="at most one change"):
        store.apply_changes([Change("modify", node(version=2)), Change("modify", node(version=3))])
    assert store.snapshot is before


@pytest.mark.parametrize("record", [node(id=True), node(lat=91), node(lon=float("nan")),
    node(tags={"key": 1}), node(visible=False), node(id=-1), node(id=1 << 63),
    node(lat="0e-1000000"), dict(type=[], id=1, version=1),
    dict(type="relation", id=1, version=1, members=[dict(type=[], ref=1, role="")])])
def test_invalid_source_records_reject_explicitly(record):
    with pytest.raises(OSMError):
        parse_element(record)


XML = b'''<?xml version="1.0"?><osm version="0.6" generator="synthetic">
 <bounds minlat="-1" minlon="-1" maxlat="1" maxlon="1"/>
 <node id="1" version="2" lat="0" lon="0"><tag k="traffic_sign" v="DE:206;DE:205"/></node>
 <node id="2" version="1" lat="0" lon="0.1"/>
 <way id="1" version="1"><nd ref="1"/><nd ref="2"/><nd ref="1"/><tag k="highway" v="residential"/></way>
 <relation id="1" version="1"><member type="way" ref="1" role="backward"/>
 <member type="way" ref="1" role="forward"/><tag k="type" v="route"/><tag k="route" v="road"/></relation>
 </osm>'''


def test_xml_streaming_order_changes_and_delete():
    class Tiny(BytesIO):
        def read(self, size=-1):
            return super().read(min(size, 19))
    store = OSMStore()
    before = store.load_xml(Tiny(XML), source_id="xml:synthetic")
    assert before.elements[("way", 1)].nodes == (1, 2, 1)
    assert len(before.elements[("relation", 1)].members) == 2
    changed = store.apply_xml(Tiny(b'''<osmChange version="0.6"><modify>
        <node id="1" version="3" lat="0" lon="1"/></modify></osmChange>'''))
    assert changed.way_geometries[("way", 1)][0].longitude == 1
    deleted = store.apply_xml(Tiny(b'''<osmChange version="0.6"><delete>
        <relation id="1" version="2"/><way id="1" version="2"/>
        <node id="1" version="4"/><node id="2" version="2"/>
        </delete></osmChange>'''))
    assert not deleted.elements and len(deleted.tombstones) == 4


@pytest.mark.parametrize("data", [
    XML[:-7], XML + b"garbage", XML.replace(b'version="0.6"', b'version="0.5"', 1),
    XML.replace(b'<nd ref="1"/>', b'<nd ref="1" ignored="yes"/>', 1),
    XML.replace(b'<tag k="highway" v="residential"/>', b'<tag k="a" v="1"/><tag k="a" v="2"/>'),
    b'<!DOCTYPE osm [<!ENTITY x "boom">]><osm version="0.6"/>',
    '<osm version="0.6"/>'.encode("utf-16"),
    b'<osm version="0.6"><node id="1" version="1" lat="0" lon="0">text</node></osm>',
    b'<osm version="0.6"><unknown/></osm>',
])
def test_invalid_or_truncated_xml_never_publishes_partial_input(data):
    store = OSMStore()
    with pytest.raises(OSMError):
        store.load_xml(BytesIO(data), source_id="bad")
    assert store.snapshot is None


def test_limits_and_failed_input_generators_are_atomic():
    for limits, records in [(replace(OSMLimits(), max_elements=1), [node(1), node(2)]),
                            (replace(OSMLimits(), max_triples=1), [node()])]:
        store = OSMStore(limits=limits)
        with pytest.raises(OSMError, match="limit"):
            store.load_snapshot(records, source="bounded")
        assert store.snapshot is None
    with pytest.raises(OSMError, match="byte limit"):
        list(iter_osm_xml(BytesIO(XML), limits=replace(OSMLimits(), max_input_bytes=20)))
    def broken():
        yield node()
        raise RuntimeError("reader interrupted")
    store = OSMStore()
    with pytest.raises(RuntimeError, match="reader interrupted"):
        store.load_snapshot(broken(), source="broken")
    assert store.snapshot is None


def test_optional_pbf_requires_real_decoder_capability(tmp_path):
    store = OSMStore()
    with pytest.raises(OSMError, match="none is configured"):
        store.load_pbf(tmp_path / "missing.pbf", source_id="pbf:fixture")
    assert not store.capabilities["pbf"]
    # This fake checks the adapter boundary, not PBF format conformance.
    class Reader:
        def read(self, path):
            yield node()
    path = tmp_path / "fixture.pbf"
    path.write_bytes(b"adapter-boundary-test")
    store = OSMStore(pbf_reader=Reader())
    result = store.load_pbf(path, source_id="pbf:adapter-test")
    assert store.capabilities["pbf"] and len(result.elements) == 1


def test_snapshot_maps_are_immutable_graph_is_fresh():
    result = OSMStore().load_snapshot([node()], source="one")
    with pytest.raises(TypeError):
        result.elements[("node", 2)] = parse_element(node(2))
    graph = result.graph()
    graph.add((URIRef("urn:x"), OSM.name, Literal("mutated")))
    assert len(result.graph()) + 1 == len(graph)


def test_actual_pyosmium_pbf_roundtrip_copies_owned_records(tmp_path):
    osmium = pytest.importorskip("osmium", reason="Optional osm extra is not installed")
    path = tmp_path / "snapshot.osm.pbf"
    with osmium.SimpleWriter(str(path)) as writer:
        for identifier, longitude in [(1, 8.1), (2, 8.2)]:
            writer.add_node(osmium.osm.mutable.Node(id=identifier, version=1,
                location=(longitude, 48.0), tags={"traffic_sign": "DE:206;DE:205"},
                timestamp="2026-09-10T08:00:00Z", changeset=42, uid=7, user="synthetic"))
        writer.add_way(osmium.osm.mutable.Way(id=1, version=3, nodes=[1, 2, 1],
                                            tags={"highway": "residential", "maxspeed": "30 mph"}))
        writer.add_relation(osmium.osm.mutable.Relation(id=1, version=2,
            members=[("w", 1, "backward"), ("w", 1, "forward")],
            tags={"type": "route", "route": "road"}))
    store = OSMStore(pbf_reader=PyOsmiumReader())
    result = store.load_pbf(path, source_id="urn:synthetic:pbf")
    assert result.elements[("node", 1)].longitude == parse_element(node(longitude=8.1)).longitude
    assert dict(result.elements[("node", 1)].metadata)["uid"] == 7
    assert dict(result.elements[("way", 1)].tags)["maxspeed"] == "30 mph"
    assert result.elements[("way", 1)].nodes == (1, 2, 1)
    assert [m.role for m in result.elements[("relation", 1)].members] == ["backward", "forward"]
    # FileProcessor and its borrowed memory views have been exhausted/closed.
    assert result.graph().value(URIRef(DATA + "way/1"), OSM.partOfRoad) == URIRef(DATA + "relation/1")


def test_pbf_missing_capability_and_bounded_copy(monkeypatch):
    import sys
    from types import SimpleNamespace
    monkeypatch.setitem(sys.modules, "osmium", None)
    with pytest.raises(OSMError, match="optional PyOsmium"):
        PyOsmiumReader()
    monkeypatch.setitem(sys.modules, "osmium", SimpleNamespace(FileProcessor=object))
    reader = PyOsmiumReader(limits=replace(OSMLimits(), max_tags=1))
    fake = SimpleNamespace(type_str=lambda: "n", id=1, version=1, visible=True,
                           tags=[("a", "1"), ("b", "2")])
    with pytest.raises(OSMError, match="tag count"):
        reader._copy(fake)


def test_record_payload_limits_and_reader_close_on_failure():
    store = OSMStore(limits=replace(OSMLimits(), max_retained_bytes=600))
    closed = []
    def records():
        try:
            yield node(tags={"large": "x" * 100})
        finally:
            closed.append(True)
    with pytest.raises(OSMError, match="retained byte"):
        store.load_snapshot(records(), source="bounded")
    assert closed and store.snapshot is None


def test_reader_close_failure_prevents_publication():
    class Records:
        def __init__(self):
            self.iterator = iter([node()])
        def __iter__(self):
            return self
        def __next__(self):
            return next(self.iterator)
        def close(self):
            raise RuntimeError("decoder final validation failed")
    store = OSMStore()
    with pytest.raises(RuntimeError, match="final validation"):
        store.load_snapshot(Records(), source="one")
    assert store.snapshot is None and not store._running


def test_manual_element_ir_cannot_hide_duplicate_tags_or_incompatible_fields():
    item = parse_element(node())
    for malformed in [replace(item, tags=(("a", "one"), ("a", "two"))),
                      replace(item, metadata=(("type", "way"),)),
                      replace(item, nodes=(1, 2))]:
        with pytest.raises(OSMError):
            parse_element(malformed)
