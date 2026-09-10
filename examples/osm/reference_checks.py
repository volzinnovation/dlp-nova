"""Check the example import contract and actual L0 reasoning on either backend."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path

from rdflib import Graph, Literal, Namespace, RDF, URIRef, XSD

from dlp_reasoner import Reasoner, parse_dlp
from map_snapshot import DATA, element_iri, literal, map_snapshot

HERE = Path(__file__).resolve().parent
OSM = Namespace("https://example.org/osm#")


def iri(kind, identifier):
    return URIRef(element_iri(kind, identifier))


def check_mapping(payload, graph):
    """Compare every source tag/reference with its independently decoded record."""
    snapshots = set(graph.subjects(RDF.type, OSM.Snapshot))
    assert len(snapshots) == 1
    snapshot = snapshots.pop()
    assert graph.value(snapshot, OSM.source) == Literal(payload["source"])
    for element in payload["elements"]:
        owner = iri(element["type"], element["id"])
        assert graph.value(owner, OSM.osmId) == Literal(element["id"], datatype=XSD.integer)
        assert graph.value(owner, OSM.version) == Literal(element["version"], datatype=XSD.integer)
        assert graph.value(owner, OSM.sourceSnapshot) == snapshot
        tags = {}
        for record in graph.subjects(OSM.ownerElement, owner):
            key, value = graph.value(record, OSM.tagKey), graph.value(record, OSM.tagValue)
            assert str(key) not in tags
            tags[str(key)] = str(value)
            assert graph.value(record, OSM.sourceSnapshot) == snapshot
        assert tags == element.get("tags", {})
        if element["type"] == "way":
            records = list(graph.subjects(OSM.ownerWay, owner))
            actual = sorted((int(graph.value(rec, OSM.position)), graph.value(rec, OSM.memberNode))
                            for rec in records)
            assert actual == [(i, iri("node", ref)) for i, ref in enumerate(element["nodes"])]
        elif element["type"] == "relation":
            records = list(graph.subjects(OSM.ownerRelation, owner))
            actual = sorted((int(graph.value(rec, OSM.position)),
                             str(graph.value(rec, OSM.memberType)),
                             graph.value(rec, OSM.memberElement), str(graph.value(rec, OSM.role)))
                            for rec in records)
            assert actual == [(i, member["type"], iri(member["type"], member["ref"]), member["role"])
                              for i, member in enumerate(element["members"])]
    assert len({iri(kind, 1) for kind in ("node", "way", "relation")}) == 3
    assert graph.value(iri("node", 1), OSM.trafficSignRaw) == Literal("DE:205;DE:206")
    assert graph.value(iri("way", 1), OSM.maxspeedRaw) == Literal("30 mph")
    assert graph.value(iri("way", 2), OSM.maxspeedRaw) == Literal("none")
    assert graph.value(iri("way", 1), OSM.maxspeedConditionalRaw) == Literal(
        "20 @ (Mo-Fr 07:00-09:00)")
    assert not any(str(p).startswith("https://example.org/traffic-sign") for _, p, _ in graph)


def check_rejections(payload):
    invalid = []
    changed = deepcopy(payload)
    changed["elements"].append(deepcopy(changed["elements"][0]))
    invalid.append(changed)  # Even an identical duplicate is not silently merged.
    changed = deepcopy(payload)
    changed["elements"][4]["nodes"].append(999)
    invalid.append(changed)
    changed = deepcopy(payload)
    changed["elements"][0]["lat"] = 91
    invalid.append(changed)
    changed = deepcopy(payload)
    changed["elements"][0]["lon"] = "NaN"
    invalid.append(changed)
    changed = deepcopy(payload)
    changed["elements"][0]["id"] = True
    invalid.append(changed)
    changed = deepcopy(payload)
    changed["elements"][0]["visible"] = False
    invalid.append(changed)
    changed = deepcopy(payload)
    changed["elements"][0]["tags"]["numeric"] = 30
    invalid.append(changed)
    changed = deepcopy(payload)
    changed["elements"][0]["unexpected"] = "not silently dropped"
    invalid.append(changed)
    for candidate in invalid:
        try:
            map_snapshot(candidate)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid snapshot accepted")
    return len(invalid)


def check_reasoner(graph, backend):
    reasoner = Reasoner(graph, profile="L0", backend=backend)
    assert reasoner.complete and reasoner.consistency == "consistent"
    assert reasoner.instances(OSM.RoadSegment) == {iri("way", n) for n in (1, 2, 4)}
    assert reasoner.instances(OSM.RoadRoute) == {iri("relation", n) for n in (1, 2)}
    assert reasoner.instances(OSM.ReverseOnewayTag) == {iri("way", 1)}
    assert reasoner.instances(OSM.TwoWayTag) == {iri("way", 2)}
    assert reasoner.instances(OSM.ForwardOnewayTag) == {iri("way", 4)}
    assert reasoner.property_pairs(OSM.partOfRoad) == {
        (iri("way", 1), iri("relation", 1)), (iri("way", 1), iri("relation", 2)),
    }
    assert reasoner.property_values(iri("way", 2), OSM.partOfRoad) == set()
    assert reasoner.instances(OSM.Node) == {iri("node", n) for n in (1, 2, 3, 4)}
    assert reasoner.instances(OSM.Way) == {iri("way", n) for n in range(1, 7)}
    assert reasoner.instances(OSM.Relation) == {iri("relation", n) for n in range(1, 5)}
    # Direct membership shortcuts are importer assertions, not a property chain:
    # editing a raw tag requires reimport, not just modifying its projection.
    route3 = iri("relation", 3)
    reasoner.update(remove=[(route3, OSM.route, Literal("bus"))],
                    add=[(route3, OSM.route, Literal("road"))])
    assert reasoner.instances(OSM.RoadRoute) == {iri("relation", n) for n in (1, 2, 3)}
    reasoner.update(remove=[(route3, OSM.route, Literal("road"))])
    assert reasoner.instances(OSM.RoadRoute) == {iri("relation", n) for n in (1, 2)}
    return set(reasoner.to_graph(include_schema=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("python", "native", "both"), default="both")
    args = parser.parse_args()
    payload = json.loads((HERE / "fixture.json").read_text(encoding="utf-8"))
    generated = map_snapshot(payload)
    assert generated == (HERE / "fixture.dlp").read_text(encoding="utf-8")
    reordered = deepcopy(payload)
    reordered["elements"].reverse()
    assert map_snapshot(reordered) == generated
    text = "line one\nline two\\\"quoted\" Straße"
    probe = parse_dlp(f'Ontology(Individual(<{DATA}literal> value(<{OSM}name> {literal(text)})))')
    assert probe.value(URIRef(DATA + "literal"), OSM.name) == Literal(text)
    data = parse_dlp(generated, source="fixture.dlp")
    check_mapping(payload, data)
    rejected = check_rejections(payload)
    schema = parse_dlp((HERE / "ontology.dlp").read_text(), source="ontology.dlp")
    graph = Graph()
    graph += schema
    graph += data
    backends = ("python", "native") if args.backend == "both" else (args.backend,)
    results = [check_reasoner(graph, backend) for backend in backends]
    assert all(result == results[0] for result in results)
    print(f"OSM snapshot checks passed: {len(payload['elements'])} elements, all tags and ordered "
          f"references preserved, {rejected} invalid inputs rejected; L0 {', '.join(backends)}.")


if __name__ == "__main__":
    main()
