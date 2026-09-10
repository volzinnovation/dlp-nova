"""Map a bounded current OSM JSON snapshot to thesis DLP syntax; no network access.

This example adapter accepts the documented subset in README.md. It is not an
OSM XML/PBF reader, history merger, permission evaluator or routing graph builder.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path

OSM = "https://example.org/osm#"
DATA = "https://example.org/osm/data/"
MAPPING_VERSION = "osm-example-v1"
KINDS = {"node": "Node", "way": "Way", "relation": "Relation"}
ROAD_HIGHWAYS = frozenset({
    "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
    "secondary", "secondary_link", "tertiary", "tertiary_link", "unclassified",
    "residential", "living_street", "service", "road", "track",
})
KEY_PROPERTIES = {
    "highway": "highway", "name": "name", "ref": "ref", "oneway": "oneway",
    "maxspeed": "maxspeedRaw", "maxspeed:conditional": "maxspeedConditionalRaw",
    "lanes": "lanes", "surface": "surface", "access": "access", "bridge": "bridge",
    "tunnel": "tunnel", "junction": "junction", "traffic_sign": "trafficSignRaw",
    "type": "relationType", "route": "route",
}
# Only direct way members with these conventional route roles get the convenience
# property. Other roles remain fully represented in RelationMembership records.
ROAD_ROLES = frozenset({"", "forward", "backward", "north", "south", "east", "west"})


def integer(value, label):
    if type(value) is not int or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def literal(value, datatype=None):
    """Appendix A defines only quote/backslash escapes; keep Unicode literal."""
    if not isinstance(value, str) or "\x00" in value:
        raise ValueError("literal must be a string without NUL")
    quoted = '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return quoted if datatype is None else quoted + "^^xsd:" + datatype


def coordinate(value, bound):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("coordinate must be a finite decimal number")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("coordinate must be a finite decimal number") from exc
    if not number.is_finite() or not -bound <= number <= bound:
        raise ValueError(f"coordinate outside [-{bound}, {bound}]")
    return literal(format(number, "f"), "decimal")


def element_iri(kind, identifier):
    return f"{DATA}{kind}/{identifier}"


def is_road(element):
    tags = element.get("tags", {})
    return (element["type"] == "way" and tags.get("highway") in ROAD_HIGHWAYS
            and tags.get("area") != "yes")


def is_road_route(element):
    tags = element.get("tags", {})
    return (element["type"] == "relation" and tags.get("type") == "route"
            and tags.get("route") == "road")


def validate(payload):
    """Validate the entire supported snapshot before producing any output."""
    if not isinstance(payload, dict) or set(payload) != {"source", "elements"}:
        raise ValueError("snapshot requires exactly source and elements fields")
    literal(payload["source"])
    if not isinstance(payload["elements"], list):
        raise ValueError("elements must be a list")
    elements = {}
    for element in payload["elements"]:
        if not isinstance(element, dict):
            raise ValueError("each element must be an object")
        kind = element.get("type")
        if kind not in KINDS:
            raise ValueError("element type must be node, way or relation")
        allowed = {"type", "id", "version", "tags", "timestamp", "changeset", "visible"}
        allowed |= {"node": {"lat", "lon"}, "way": {"nodes"}, "relation": {"members"}}[kind]
        if set(element) - allowed:
            raise ValueError(f"unsupported element fields: {sorted(set(element) - allowed)}")
        identifier = integer(element.get("id"), "id")
        integer(element.get("version"), "version")
        key = (kind, identifier)
        if key in elements:
            raise ValueError(f"multiple records for {key}; history merging is unsupported")
        if element.get("visible", True) is not True:
            raise ValueError("deleted/invisible elements are outside the snapshot subset")
        if "timestamp" in element:
            literal(element["timestamp"])  # Preserved lexical metadata, not parsed event time.
        if "changeset" in element:
            integer(element["changeset"], "changeset")
        tags = element.get("tags", {})
        if not isinstance(tags, dict):
            raise ValueError("tags must be a key/value object")
        for tag_key, tag_value in tags.items():
            literal(tag_key)
            literal(tag_value)
        if kind == "node":
            coordinate(element.get("lat"), 90)
            coordinate(element.get("lon"), 180)
        elif kind == "way":
            refs = element.get("nodes")
            if not isinstance(refs, list) or not 2 <= len(refs) <= 2000:
                raise ValueError("way requires 2..2000 ordered node references")
            for ref in refs:
                integer(ref, "node reference")
        else:
            members = element.get("members")
            if not isinstance(members, list):
                raise ValueError("relation requires an ordered members list")
            for member in members:
                if not isinstance(member, dict) or set(member) != {"type", "ref", "role"}:
                    raise ValueError("member requires exactly type, ref and role")
                if member["type"] not in KINDS:
                    raise ValueError("member type must be node, way or relation")
                integer(member["ref"], "member reference")
                literal(member["role"])
        elements[key] = element
    for element in elements.values():
        if element["type"] == "way":
            refs = [("node", ref) for ref in element["nodes"]]
        elif element["type"] == "relation":
            refs = [(member["type"], member["ref"]) for member in element["members"]]
        else:
            refs = []
        for ref in refs:
            if ref not in elements:
                raise ValueError(f"unresolved reference {ref}; provide a complete snapshot")
    return elements


def map_snapshot(payload):
    elements = validate(payload)
    ordered = [elements[key] for key in sorted(elements)]
    canonical = json.dumps({"source": payload["source"], "elements": ordered},
                           sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    snapshot = f"{DATA}snapshot/{digest}"
    lines = ["// Generated from the synthetic/current snapshot by map_snapshot.py.",
             f"Namespace(osm = <{OSM}>)", "", "Ontology("]

    def record(iri, classes, values):
        lines.append(f"    Individual(<{iri}>")
        for name in classes:
            lines.append(f"        type(osm:{name})")
        for name, value in values:
            lines.append(f"        value(osm:{name} {value})")
        lines.append("    )")

    def provenance():
        return [("sourceSnapshot", f"<{snapshot}>")]

    record(snapshot, ["Snapshot"], [("source", literal(payload["source"])),
           ("contentSha256", literal(digest)), ("mappingVersion", literal(MAPPING_VERSION))])
    route_memberships = {}
    for element in ordered:
        if is_road_route(element):
            for member in element["members"]:
                key = (member["type"], member["ref"])
                if (member["type"] == "way" and member["role"] in ROAD_ROLES
                        and is_road(elements[key])):
                    route_memberships.setdefault(key, set()).add(element["id"])
    for element in ordered:
        kind, identifier = element["type"], element["id"]
        iri = element_iri(kind, identifier)
        version = element["version"]
        occurrence_base = f"{iri}/v{version}"
        tags = element.get("tags", {})
        classes = [KINDS[kind]] + (["RoadSegment"] if is_road(element) else [])
        values = provenance() + [("osmId", literal(str(identifier), "integer")),
                                 ("version", literal(str(version), "integer"))]
        for field in ("timestamp", "changeset"):
            if field in element:
                datatype = "integer" if field == "changeset" else None
                values.append((field, literal(str(element[field]), datatype)))
        if kind == "node":
            values += [("latitude", coordinate(element["lat"], 90)),
                       ("longitude", coordinate(element["lon"], 180))]
        values += [(KEY_PROPERTIES[key], literal(value)) for key, value in sorted(tags.items())
                   if key in KEY_PROPERTIES]
        values += [("partOfRoad", f"<{element_iri('relation', route)}>")
                   for route in sorted(route_memberships.get((kind, identifier), set()))]
        record(iri, classes, values)
        for index, (key, value) in enumerate(sorted(tags.items())):
            record(f"{occurrence_base}/tag/{index}", ["Tag"], provenance() + [
                ("ownerElement", f"<{iri}>"), ("tagKey", literal(key)),
                ("tagValue", literal(value))])
        if kind == "way":
            for index, ref in enumerate(element["nodes"]):
                record(f"{occurrence_base}/node/{index}", ["WayNode"], provenance() + [
                    ("ownerWay", f"<{iri}>"), ("position", literal(str(index), "integer")),
                    ("memberNode", f"<{element_iri('node', ref)}>")])
        elif kind == "relation":
            for index, member in enumerate(element["members"]):
                record(f"{occurrence_base}/member/{index}", ["RelationMembership"],
                       provenance() + [("ownerRelation", f"<{iri}>"),
                       ("position", literal(str(index), "integer")),
                       ("memberElement", f"<{element_iri(member['type'], member['ref'])}>"),
                       ("memberType", literal(member["type"])), ("role", literal(member["role"]))])
    return "\n".join(lines + [")", ""])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        result = map_snapshot(json.loads(args.input.read_text(encoding="utf-8")))
    except (ValueError, UnicodeError) as exc:
        parser.error(str(exc))
    args.output.write_text(result, encoding="utf-8")


if __name__ == "__main__":
    main()
