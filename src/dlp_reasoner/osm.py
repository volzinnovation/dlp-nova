"""Bounded, transactional current OSM snapshots and ordered versioned changes.

The adapter preserves raw source data, then recomputes the documented road/tag
projections. It does not infer traffic permission, sign applicability or routes.
XML streams are decoded incrementally; PBF requires an explicit decoder adapter.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import hashlib
from itertools import chain
import json
from pathlib import Path
from types import MappingProxyType
import xml.etree.ElementTree as ET

from rdflib import Graph, Literal, Namespace, RDF, URIRef, XSD

from .domains import Point
from .spatial import PointIndex, PointProvider, POINT_CANDIDATES

OSM = Namespace("https://example.org/osm#")
DATA = "https://example.org/osm/data/"
MAPPING_VERSION = "osm-current-v1"
KINDS = {"node": "Node", "way": "Way", "relation": "Relation"}
ROAD_HIGHWAYS = frozenset({"motorway", "motorway_link", "trunk", "trunk_link", "primary",
    "primary_link", "secondary", "secondary_link", "tertiary", "tertiary_link", "unclassified",
    "residential", "living_street", "service", "road", "track"})
ROAD_ROLES = frozenset({"", "forward", "backward", "north", "south", "east", "west"})
KEY_PROPERTIES = {"highway": "highway", "name": "name", "ref": "ref", "oneway": "oneway",
    "maxspeed": "maxspeedRaw", "maxspeed:conditional": "maxspeedConditionalRaw", "lanes": "lanes",
    "surface": "surface", "access": "access", "bridge": "bridge", "tunnel": "tunnel",
    "junction": "junction", "traffic_sign": "trafficSignRaw", "type": "relationType", "route": "route"}


class OSMError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def _fail(code, message):
    raise OSMError(code, message)


@dataclass(frozen=True)
class OSMLimits:
    max_elements: int = 100_000
    max_input_bytes: int = 64 * 1024 * 1024
    max_retained_bytes: int = 128 * 1024 * 1024
    max_changes: int = 100_000
    max_way_nodes: int = 2000
    max_members: int = 20_000
    max_tags: int = 1000
    max_string_bytes: int = 8192
    max_triples: int = 3_000_000

    def __post_init__(self):
        if any(type(value) is not int or value < 1 for value in vars(self).values()):
            raise ValueError("OSM resource limits must be positive integers")


def _integer(value, label):
    if type(value) is not int or not 0 < value < 1 << 63:
        _fail("INVALID_RECORD", f"{label} must be a positive signed-64-bit integer")
    return value


def _string(value, label, limits):
    if not isinstance(value, str) or "\x00" in value:
        _fail("INVALID_RECORD", f"{label} must be a string without NUL")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError:
        _fail("INVALID_RECORD", f"{label} has invalid Unicode")
    if size > limits.max_string_bytes:
        _fail("RESOURCE_LIMIT", f"{label} exceeds string byte limit")
    return value


def _coordinate(value, bound):
    if type(value) not in (str, int, float, Decimal):
        _fail("INVALID_RECORD", "Coordinate must be a finite decimal")
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        _fail("INVALID_RECORD", "Coordinate must be a finite decimal")
    if not result.is_finite() or not -bound <= result <= bound:
        _fail("INVALID_RECORD", f"Coordinate outside [-{bound}, {bound}]")
    # A source lexical with a huge exponent/coefficient must not allocate a huge
    # decimal RDF serialization despite being numerically small or zero.
    if len(result.as_tuple().digits) > 32 or abs(result.as_tuple().exponent) > 18:
        _fail("INVALID_RECORD", "Coordinate precision exceeds the bounded decimal profile")
    return result


@dataclass(frozen=True)
class Member:
    type: str
    ref: int
    role: str

    @property
    def key(self):
        return self.type, self.ref


@dataclass(frozen=True)
class Element:
    type: str
    id: int
    version: int
    tags: tuple = ()
    nodes: tuple = ()
    members: tuple[Member, ...] = ()
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    metadata: tuple = ()

    @property
    def key(self):
        return self.type, self.id

    @property
    def iri(self):
        return URIRef(f"{DATA}{self.type}/{self.id}")

    @property
    def references(self):
        return tuple(("node", ref) for ref in self.nodes) if self.type == "way" else tuple(
            member.key for member in self.members)


@dataclass(frozen=True)
class Change:
    action: str
    element: object


def parse_element(record, *, limits=None, deleted=False):
    limits = limits or OSMLimits()
    if isinstance(record, Element):
        # Validate manually constructed IR by round-tripping through the same
        # public boundary; frozen annotations alone are not a validation proof.
        if type(record.type) is not str or record.type not in KINDS:
            _fail("INVALID_RECORD", "Invalid Element type")
        for entries, label in ((record.tags, "tags"), (record.metadata, "metadata")):
            if (type(entries) is not tuple or any(type(pair) is not tuple or len(pair) != 2
                    or type(pair[0]) is not str for pair in entries)
                    or len({pair[0] for pair in entries}) != len(entries)):
                _fail("INVALID_RECORD", f"Element {label} requires unique immutable pairs")
        if set(dict(record.metadata)) - {"timestamp", "changeset", "user", "uid"}:
            _fail("INVALID_RECORD", "Invalid Element metadata fields")
        if (type(record.nodes) is not tuple or type(record.members) is not tuple
                or any(type(member) is not Member for member in record.members)
                or (record.type != "way" and record.nodes)
                or (record.type != "relation" and record.members)
                or (record.type != "node" and (record.latitude is not None or record.longitude is not None))):
            _fail("INVALID_RECORD", "Element contains incompatible geometry/member fields")
        value = {"type": record.type, "id": record.id, "version": record.version,
                 "tags": dict(record.tags), **dict(record.metadata)}
        if record.type == "node" and (not deleted or record.latitude is not None or record.longitude is not None):
            value.update(lat=record.latitude, lon=record.longitude)
        elif record.type == "way" and (not deleted or record.nodes):
            value["nodes"] = list(record.nodes)
        elif record.type == "relation" and (not deleted or record.members):
            value["members"] = [vars(member) for member in record.members]
        record = value
    if type(record) is not dict:
        _fail("INVALID_RECORD", "OSM element must be an object")
    kind = record.get("type")
    if type(kind) is not str or kind not in KINDS:
        _fail("INVALID_RECORD", "Element type must be node, way or relation")
    allowed = {"type", "id", "version", "tags", "timestamp", "changeset", "visible", "user", "uid"}
    allowed |= {"node": {"lat", "lon"}, "way": {"nodes"}, "relation": {"members"}}[kind]
    if set(record) - allowed:
        _fail("UNSUPPORTED", "Unsupported OSM element fields")
    identifier = _integer(record.get("id"), "id")
    version = _integer(record.get("version"), "version")
    if type(record.get("visible", True)) is not bool or (not deleted and not record.get("visible", True)):
        _fail("INVALID_RECORD", "Invisible records require an explicit delete action")
    tags = record.get("tags", {})
    if type(tags) is not dict:
        _fail("INVALID_RECORD", "Tags must be a key/value object")
    if len(tags) > limits.max_tags:
        _fail("RESOURCE_LIMIT", "Tag count limit exceeded")
    for key, value in tags.items():
        _string(key, "Tag key", limits)
        _string(value, "Tag value", limits)
    metadata = []
    for name in ("timestamp", "changeset", "user", "uid"):
        if name in record:
            value = (_integer(record[name], name) if name in {"changeset", "uid"}
                     else _string(record[name], name, limits))
            metadata.append((name, value))
    nodes, members, latitude, longitude = (), (), None, None
    if kind == "node" and (not deleted or "lat" in record or "lon" in record):
        latitude = _coordinate(record.get("lat"), 90)
        longitude = _coordinate(record.get("lon"), 180)
    elif kind == "way" and (not deleted or "nodes" in record):
        refs = record.get("nodes")
        if type(refs) is not list or not (0 if deleted else 2) <= len(refs) <= limits.max_way_nodes:
            _fail("INVALID_RECORD", "Way requires 2..max_way_nodes ordered node references")
        nodes = tuple(_integer(ref, "Node reference") for ref in refs)
    elif kind == "relation" and (not deleted or "members" in record):
        refs = record.get("members")
        if type(refs) is not list:
            _fail("INVALID_RECORD", "Relation requires ordered members")
        if len(refs) > limits.max_members:
            _fail("RESOURCE_LIMIT", "Relation member limit exceeded")
        result = []
        for member in refs:
            if type(member) is not dict or set(member) != {"type", "ref", "role"}:
                _fail("INVALID_RECORD", "Member requires type, ref and role")
            if type(member["type"]) is not str or member["type"] not in KINDS:
                _fail("INVALID_RECORD", "Invalid relation member type")
            result.append(Member(member["type"], _integer(member["ref"], "Member reference"),
                                 _string(member["role"], "Member role", limits)))
        members = tuple(result)
    return Element(kind, identifier, version, tuple(sorted(tags.items())), nodes, members,
                   latitude, longitude, tuple(metadata))


def _xml_record(element, limits):
    attributes = dict(element.attrib)
    for key in ("id", "version", "changeset", "uid"):
        if key in attributes:
            try:
                attributes[key] = int(attributes[key])
            except ValueError:
                _fail("INVALID_XML", f"Invalid integer attribute {key}")
    if "visible" in attributes:
        if attributes["visible"] not in {"true", "false"}:
            _fail("INVALID_XML", "Invalid visible attribute")
        attributes["visible"] = attributes["visible"] == "true"
    result = {"type": element.tag, **attributes, "tags": {}}
    if element.tag == "way":
        result["nodes"] = []
    elif element.tag == "relation":
        result["members"] = []
    for child in element:
        if len(child) or (child.text and child.text.strip()):
            _fail("INVALID_XML", "Nested or text-bearing element children are unsupported")
        if child.tag == "tag" and set(child.attrib) == {"k", "v"}:
            key = child.attrib["k"]
            if key in result["tags"]:
                _fail("INVALID_XML", "Duplicate raw tag key")
            result["tags"][key] = child.attrib["v"]
        elif child.tag == "nd" and element.tag == "way" and set(child.attrib) == {"ref"}:
            try:
                result["nodes"].append(int(child.attrib["ref"]))
            except ValueError:
                _fail("INVALID_XML", "Invalid way node reference")
        elif child.tag == "member" and element.tag == "relation" and set(child.attrib) == {"type", "ref", "role"}:
            try:
                result["members"].append({**child.attrib, "ref": int(child.attrib["ref"])})
            except ValueError:
                _fail("INVALID_XML", "Invalid relation member reference")
        else:
            _fail("UNSUPPORTED", f"Unsupported OSM XML child {child.tag}")
    return result


def iter_osm_xml(source, *, changes=False, limits=None):
    """Yield validated records from a binary stream/path, bounded by byte count.

    DTD/entity declarations, history documents, unsupported fields and duplicate
    keys are rejected. Root bounds are recognized as extraction metadata only.
    The consumer must exhaust the iterator before publishing any record.
    """
    limits = limits or OSMLimits()
    owned = not hasattr(source, "read")
    stream = Path(source).open("rb") if owned else source
    parser = ET.XMLPullParser(events=("start", "end"))
    stack, total, count, tail, root_seen = [], 0, 0, b"", False
    try:
        while True:
            chunk = stream.read(65536)
            if type(chunk) is not bytes:
                _fail("INVALID_XML", "XML input must be a binary stream")
            total += len(chunk)
            if total > limits.max_input_bytes:
                _fail("RESOURCE_LIMIT", "XML input byte limit exceeded")
            probe = (tail + chunk).upper()
            # UTF-16/32 would bypass this byte-level DTD guard. Restrict the
            # reader to UTF-8/ASCII XML instead of weakening the guard.
            if b"\x00" in chunk or b"<!DOCTYPE" in probe or b"<!ENTITY" in probe:
                _fail("UNSUPPORTED", "XML DTD/entities and UTF-16/32 encodings are unsupported")
            tail = probe[-16:]
            if chunk:
                parser.feed(chunk)
            else:
                # Expat may defer parsing small chunks until close(). Drain the
                # final events too, or a complete change file could look empty.
                parser.close()
            for event, element in parser.read_events():
                if event == "start":
                    stack.append(element)
                    if len(stack) > 4:
                        _fail("INVALID_XML", "Unexpected XML nesting")
                    if len(stack) == 1:
                        expected = "osmChange" if changes else "osm"
                        if root_seen or element.tag != expected or element.attrib.get("version") != "0.6":
                            _fail("INVALID_XML", f"Expected one {expected} version 0.6 document")
                        if set(element.attrib) - {"version", "generator", "copyright", "attribution", "license"}:
                            _fail("UNSUPPORTED", "Unsupported OSM root metadata")
                        root_seen = True
                    elif changes and len(stack) == 2:
                        if element.tag not in {"create", "modify", "delete"} or element.attrib:
                            _fail("UNSUPPORTED", "Expected unconditional create/modify/delete action")
                    continue
                record_depth = 3 if changes else 2
                if element.text and element.text.strip():
                    _fail("INVALID_XML", "Unexpected XML text")
                if element.tail and element.tail.strip():
                    _fail("INVALID_XML", "Unexpected XML tail text")
                if len(stack) == record_depth:
                    if element.tag in KINDS:
                        count += 1
                        if count > (limits.max_changes if changes else limits.max_elements):
                            _fail("RESOURCE_LIMIT", "XML record count limit exceeded")
                        action = stack[-2].tag if changes else None
                        record = parse_element(_xml_record(element, limits), limits=limits,
                                               deleted=action == "delete")
                        yield Change(action, record) if changes else record
                    elif not changes and element.tag == "bounds":
                        if len(element) or set(element.attrib) != {"minlat", "minlon", "maxlat", "maxlon"}:
                            _fail("INVALID_XML", "Invalid extraction bounds")
                        for name, value in element.attrib.items():
                            _coordinate(value, 90 if "lat" in name else 180)
                    else:
                        _fail("UNSUPPORTED", f"Unsupported XML element {element.tag}")
                    stack[-2].remove(element)
                    element.clear()
                elif changes and len(stack) == 2:
                    stack[-2].remove(element)
                    element.clear()
                stack.pop()
            if not chunk:
                break
        if not root_seen:
            _fail("INVALID_XML", "Empty XML document")
    except ET.ParseError as exc:
        raise OSMError("INVALID_XML", str(exc)) from exc
    finally:
        if owned:
            stream.close()


def _reverse(elements):
    reverse = defaultdict(set)
    for key, element in elements.items():
        for reference in element.references:
            if reference not in elements:
                _fail("MISSING_REFERENCE", f"Unresolved OSM reference {reference} from {key}")
            reverse[reference].add(key)
    return {key: frozenset(value) for key, value in reverse.items()}


def _affected(changed, old_reverse, new_reverse):
    affected, queue = set(changed), list(changed)
    while queue:
        key = queue.pop()
        for owner in old_reverse.get(key, frozenset()) | new_reverse.get(key, frozenset()):
            if owner not in affected:
                affected.add(owner)
                queue.append(owner)
    return frozenset(affected)


def _is_road(element):
    tags = dict(element.tags)
    return element.type == "way" and tags.get("highway") in ROAD_HIGHWAYS and tags.get("area") != "yes"


def _is_route(element):
    tags = dict(element.tags)
    return element.type == "relation" and tags.get("type") == "route" and tags.get("route") == "road"


def _digest(elements, tombstones, source):
    def record(element):
        return (element.type, element.id, element.version, element.tags, element.nodes,
                [tuple(vars(member).values()) for member in element.members],
                str(element.latitude), str(element.longitude), element.metadata)
    digest = hashlib.sha256()
    for value in chain(((source, MAPPING_VERSION),),
                       (record(elements[key]) for key in sorted(elements)), sorted(tombstones.items())):
        serialized = json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode()
        digest.update(len(serialized).to_bytes(8, "big"))
        digest.update(serialized)
    return digest.hexdigest()


def _record_size(element):
    # Conservative normalized payload/container accounting, not a promise about
    # Python/libosmium RSS. RDF triples and old/candidate revisions have limits too.
    strings = (*element.tags, *element.metadata,
               *(("role", member.role) for member in element.members))
    return (512 + 32 * len(element.nodes) + 96 * len(element.members) +
            sum(128 + len(str(key).encode()) * 4 + len(str(value).encode()) * 4
                for key, value in strings))


def _triples(elements, source, digest, limits):
    result = set()
    snapshot = URIRef(DATA + "snapshot/" + digest)

    def add(subject, predicate, value):
        result.add((subject, predicate, value))
        if len(result) > limits.max_triples:
            _fail("RESOURCE_LIMIT", "Mapped RDF triple limit exceeded")

    def record(subject, cls, values):
        add(subject, RDF.type, OSM[cls])
        add(subject, OSM.sourceSnapshot, snapshot)
        for predicate, value in values:
            add(subject, OSM[predicate], value)

    add(snapshot, RDF.type, OSM.Snapshot)
    for name, value in (("source", source), ("contentSha256", digest), ("mappingVersion", MAPPING_VERSION)):
        add(snapshot, OSM[name], Literal(value))
    for element in elements.values():
        iri = element.iri
        values = [("osmId", Literal(element.id)), ("version", Literal(element.version))]
        values.extend((name, Literal(value)) for name, value in element.metadata)
        if element.type == "node":
            values += [("latitude", Literal(element.latitude, datatype=XSD.decimal)),
                       ("longitude", Literal(element.longitude, datatype=XSD.decimal))]
        values.extend((KEY_PROPERTIES[key], Literal(value)) for key, value in element.tags
                      if key in KEY_PROPERTIES)
        record(iri, KINDS[element.type], values)
        if _is_road(element):
            add(iri, RDF.type, OSM.RoadSegment)
        occurrence = f"{iri}/v{element.version}"
        for index, (key, value) in enumerate(element.tags):
            record(URIRef(f"{occurrence}/tag/{index}"), "Tag", [
                ("ownerElement", iri), ("tagKey", Literal(key)), ("tagValue", Literal(value))])
        for index, ref in enumerate(element.nodes):
            record(URIRef(f"{occurrence}/node/{index}"), "WayNode", [
                ("ownerWay", iri), ("position", Literal(index)),
                ("memberNode", URIRef(f"{DATA}node/{ref}"))])
        for index, member in enumerate(element.members):
            target = elements[member.key]
            record(URIRef(f"{occurrence}/member/{index}"), "RelationMembership", [
                ("ownerRelation", iri), ("position", Literal(index)), ("memberElement", target.iri),
                ("memberType", Literal(member.type)), ("role", Literal(member.role))])
            if _is_route(element) and member.role in ROAD_ROLES and _is_road(target):
                add(target.iri, OSM.partOfRoad, iri)
    return frozenset(result)


@dataclass(frozen=True)
class OSMSnapshot:
    source: str
    revision: int
    digest: str
    elements: object
    tombstones: object
    reverse_dependencies: object
    way_geometries: object
    triples: frozenset
    point_index: PointIndex
    affected: frozenset = field(default_factory=frozenset)
    additions: frozenset = field(default_factory=frozenset)
    retractions: frozenset = field(default_factory=frozenset)

    def graph(self):
        result = Graph()
        result.bind("osm", OSM)
        for triple in self.triples:
            result.add(triple)
        return result


class OSMStore:
    """Publish all source/projection/index changes together, or keep the old state.

    A context is serialized by its host; reentrant updates fail. Missing references
    are an error, never silently completed by external fetches. Full snapshots may
    contain any positive version; subsequent changes require exactly version+1.
    """
    def __init__(self, *, limits=None, backend="python", pbf_reader=None):
        self.limits, self.backend, self.pbf_reader = limits or OSMLimits(), backend, pbf_reader
        self.snapshot, self._running = None, False

    @property
    def capabilities(self):
        return {"xml_snapshot": True, "xml_change": True, "pbf": self.pbf_reader is not None,
                "pbf_reader": None if self.pbf_reader is None else type(self.pbf_reader).__name__,
                "history": False, "missing_references": "reject", "mapping": MAPPING_VERSION}

    def _publish(self, elements, tombstones, source, changed):
        reverse = _reverse(elements)
        old = self.snapshot
        projection_inputs = set(changed)
        for key in changed:
            for element in (elements.get(key), None if old is None else old.elements.get(key)):
                if element is not None and element.type == "relation":
                    # partOfRoad is projected onto members, so relation edits
                    # invalidate both old and new member targets as well.
                    projection_inputs.update(element.references)
        affected = _affected(projection_inputs, {} if old is None else old.reverse_dependencies, reverse)
        digest = _digest(elements, tombstones, source)
        geometries = {} if old is None else dict(old.way_geometries)
        for key in list(geometries):
            if key not in elements:
                del geometries[key]
        for key in affected:
            element = elements.get(key)
            if element is not None and element.type == "way":
                geometries[key] = tuple(Point(float(elements[("node", ref)].longitude),
                                              float(elements[("node", ref)].latitude))
                                        for ref in element.nodes)
        triples = _triples(elements, source, digest, self.limits)
        points = {element.iri: Point(float(element.longitude), float(element.latitude))
                  for element in elements.values() if element.type == "node"}
        index = PointIndex(points, revision=digest, backend=self.backend,
                           max_points=self.limits.max_elements)
        previous = frozenset() if old is None else old.triples
        try:
            candidate = OSMSnapshot(source, 1 if old is None else old.revision + 1, digest,
                MappingProxyType(elements), MappingProxyType(tombstones), MappingProxyType(reverse),
                MappingProxyType(geometries), triples, index, affected,
                triples - previous, previous - triples)
        except BaseException:
            index.close()
            raise
        self.snapshot = candidate
        return candidate

    def load_snapshot(self, records, *, source):
        if self._running:
            _fail("REENTRANT", "OSM transaction is already running")
        if self.snapshot is not None:
            _fail("INVALID_STATE", "Initial snapshot already loaded; use changes or a new store")
        _string(source, "Source", self.limits)
        records = iter(records)
        closed = False
        self._running = True
        try:
            elements = {}
            retained_bytes = 0
            for record in records:
                if len(elements) >= self.limits.max_elements:
                    _fail("RESOURCE_LIMIT", "Snapshot element count limit exceeded")
                element = parse_element(record, limits=self.limits)
                if element.key in elements:
                    _fail("DUPLICATE_VERSION", "Snapshot contains multiple versions/records of an element")
                retained_bytes += _record_size(element)
                if retained_bytes > self.limits.max_retained_bytes:
                    _fail("RESOURCE_LIMIT", "Snapshot retained byte limit exceeded")
                elements[element.key] = element
            closed = True
            if hasattr(records, "close"):
                records.close()
            return self._publish(elements, {}, source, set(elements))
        finally:
            try:
                if not closed and hasattr(records, "close"):
                    records.close()
            finally:
                self._running = False

    def apply_changes(self, changes):
        if self._running:
            _fail("REENTRANT", "OSM transaction is already running")
        if self.snapshot is None:
            _fail("INVALID_STATE", "Load an initial OSM snapshot before changes")
        changes = iter(changes)
        closed = False
        self._running = True
        try:
            elements, tombstones = dict(self.snapshot.elements), dict(self.snapshot.tombstones)
            retained_bytes = sum(map(_record_size, elements.values())) + 64 * len(tombstones)
            changed = set()
            for change in changes:
                if len(changed) >= self.limits.max_changes:
                    _fail("RESOURCE_LIMIT", "Change record count limit exceeded")
                if (not isinstance(change, Change) or type(change.action) is not str
                        or change.action not in {"create", "modify", "delete"}):
                    _fail("INVALID_RECORD", "Expected a create/modify/delete Change")
                element = parse_element(change.element, limits=self.limits, deleted=change.action == "delete")
                key = element.key
                if key in changed:
                    _fail("DUPLICATE_VERSION", "One transaction must contain at most one change per element")
                previous = elements.get(key)
                retained_bytes -= 0 if previous is None else _record_size(previous)
                retained_bytes += 64 if change.action == "delete" else _record_size(element)
                if retained_bytes > self.limits.max_retained_bytes:
                    _fail("RESOURCE_LIMIT", "Changed snapshot retained byte limit exceeded")
                if change.action == "create":
                    if previous is not None or key in tombstones or element.version != 1:
                        _fail("STALE_VERSION", "Create requires a new typed ID and version 1")
                    elements[key] = element
                else:
                    if previous is None or element.version != previous.version + 1:
                        _fail("STALE_VERSION", "Modify/delete requires an existing record and exactly version+1")
                    if change.action == "delete":
                        del elements[key]
                        tombstones[key] = element.version
                    else:
                        elements[key] = element
                changed.add(key)
                if len(elements) + len(tombstones) > self.limits.max_elements:
                    _fail("RESOURCE_LIMIT", "Retained element/tombstone count limit exceeded")
            closed = True
            if hasattr(changes, "close"):
                changes.close()
            if not changed:
                return self.snapshot
            return self._publish(elements, tombstones, self.snapshot.source, changed)
        finally:
            try:
                if not closed and hasattr(changes, "close"):
                    changes.close()
            finally:
                self._running = False

    def load_xml(self, source, *, source_id):
        return self.load_snapshot(iter_osm_xml(source, limits=self.limits), source=source_id)

    def apply_xml(self, source):
        return self.apply_changes(iter_osm_xml(source, changes=True, limits=self.limits))

    def load_pbf(self, path, *, source_id):
        if self.pbf_reader is None:
            _fail("UNAVAILABLE", "PBF decoding requires an explicit streaming pbf_reader adapter; none is configured")
        if Path(path).stat().st_size > self.limits.max_input_bytes:
            _fail("RESOURCE_LIMIT", "PBF input byte limit exceeded")
        return self.load_snapshot(self.pbf_reader.read(path), source=source_id)

    def register_points(self, registry, *, operation=POINT_CANDIDATES):
        def current():
            if self.snapshot is None:
                _fail("INVALID_STATE", "OSM point snapshot is not loaded")
            return self.snapshot.point_index
        adapter = PointProvider(current)
        registry.register(operation, adapter, input_types=("point", "number", "any"),
                          cardinality="many", output_types=("iri",), coverage="candidate_superset")
        return adapter


class PyOsmiumReader:
    """Optional libosmium-backed streaming decoder, copying all borrowed data.

    Install the ``osm`` extra explicitly. This reads current snapshots, not
    histories/change actions. Metadata absent/defaulted by libosmium is omitted
    (zero uid/changeset, empty user and epoch timestamp); no validity time follows
    from an OSM edit timestamp. No implicit node-location cache is enabled.
    """
    def __init__(self, *, limits=None):
        try:
            import osmium
        except ImportError as exc:
            raise OSMError("UNAVAILABLE", "PBF reading requires optional PyOsmium: install dlp-reasoner[osm]") from exc
        if not hasattr(osmium, "FileProcessor"):
            _fail("UNAVAILABLE", "PBF reading requires PyOsmium 4 with FileProcessor")
        self.osmium, self.limits = osmium, limits or OSMLimits()

    def _copy(self, obj):
        kinds = {"n": "node", "w": "way", "r": "relation"}
        kind = kinds.get(obj.type_str())
        if kind is None:
            _fail("UNSUPPORTED", "PBF stream contains a non-element object")
        record = dict(type=kind, id=obj.id, version=obj.version, visible=obj.visible, tags={})
        for key, value in obj.tags:
            if len(record["tags"]) >= self.limits.max_tags:
                _fail("RESOURCE_LIMIT", "PBF tag count limit exceeded")
            key = _string(key, "Tag key", self.limits)
            if key in record["tags"]:
                _fail("INVALID_RECORD", "PBF element has duplicate raw tag keys")
            record["tags"][key] = _string(value, "Tag value", self.limits)
        for name in ("uid", "changeset", "user"):
            value = getattr(obj, name)
            if value:
                record[name] = value
        timestamp = obj.timestamp
        if timestamp is not None and timestamp.timestamp() != 0:
            record["timestamp"] = timestamp.isoformat()
        if kind == "node":
            if not obj.location.valid():
                _fail("INVALID_RECORD", "PBF node has invalid/missing coordinates")
            record.update(lon=obj.lon, lat=obj.lat)
        elif kind == "way":
            record["nodes"] = []
            for reference in obj.nodes:
                if len(record["nodes"]) >= self.limits.max_way_nodes:
                    _fail("RESOURCE_LIMIT", "PBF way node limit exceeded")
                record["nodes"].append(reference.ref)
        else:
            record["members"] = []
            for member in obj.members:
                if len(record["members"]) >= self.limits.max_members:
                    _fail("RESOURCE_LIMIT", "PBF member limit exceeded")
                if member.type not in kinds:
                    _fail("INVALID_RECORD", "Invalid PBF member type")
                record["members"].append(dict(type=kinds[member.type], ref=member.ref,
                    role=_string(member.role, "Member role", self.limits)))
        return parse_element(record, limits=self.limits)

    def read(self, path):
        if Path(path).stat().st_size > self.limits.max_input_bytes:
            _fail("RESOURCE_LIMIT", "PBF input byte limit exceeded")
        iterator = iter(self.osmium.FileProcessor(path))
        count = 0
        try:
            for obj in iterator:
                if count >= self.limits.max_elements:
                    _fail("RESOURCE_LIMIT", "PBF element count limit exceeded")
                count += 1
                yield self._copy(obj)
        except OSMError:
            raise
        except (RuntimeError, ValueError, OSError) as exc:
            raise OSMError("INVALID_PBF", f"Cannot decode current PBF snapshot: {exc}") from exc
        finally:
            if hasattr(iterator, "close"):
                iterator.close()
