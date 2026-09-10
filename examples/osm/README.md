# A small OpenStreetMap ontology in DLP

This runnable example maps the OSM element model and selected tags to
`https://example.org/osm#`. It is an application vocabulary, not an official OSM
ontology or a complete OSM importer. The schema uses **L0** class inclusions,
literal has-value restrictions, and object/datatype properties. It works with
the existing Python and native backends; no parser or engine extension is needed.

The [fixture](fixture.json) is entirely synthetic. Its IDs, coordinates, names,
versions and tags are test data, not claims about live OpenStreetMap objects.
No OSM data is downloaded by these scripts.

## Run and load

From the repository root, using its existing environment:

```sh
.venv/bin/python examples/osm/reference_checks.py --backend both
.venv/bin/python examples/osm/map_snapshot.py examples/osm/fixture.json /tmp/osm-fixture.dlp
```

The native check uses the project's existing optional C++ compiler/build path;
`--backend python` needs no compiler. The checker verifies the retained generated
fixture, every raw tag and ordered reference, selected inferred classes,
transactional class updates, rejected inputs and complete Python/native output
agreement. It does not test OSM API ingestion or routing correctness.

The schema and instances are separate valid DLP documents. Load their RDF graphs
together; there is no automatic import directive or network fetch:

```python
from pathlib import Path
from rdflib import Graph, Namespace
from dlp_reasoner import Reasoner, parse_dlp

folder = Path("examples/osm")
graph = Graph()
for name in ("ontology.dlp", "fixture.dlp"):
    path = folder / name
    graph += parse_dlp(path.read_text(encoding="utf-8"), source=str(path))
reasoner = Reasoner(graph, profile="L0", backend="python")
osm = Namespace("https://example.org/osm#")
print(sorted(map(str, reasoner.instances(osm.RoadRoute))))
```

Expected road ways: `.../way/1`, `.../way/2`, `.../way/4`. Expected road-route
relations: `.../relation/1`, `.../relation/2`. Way 1 belongs to both routes; way 2
belongs to neither, despite appearing in a bus-route relation. Node 1, way 1
and relation 1 are three different resources.

## Mapping contract

OSM nodes, ways and relations have separate numeric ID spaces. Nodes supply
latitude/longitude; ways contain ordered node references; relations contain
ordered, typed members with roles. Repeated references are meaningful and must
not collapse into an unordered binary membership set.
[OSM elements](https://wiki.openstreetmap.org/wiki/Elements),
[ways](https://wiki.openstreetmap.org/wiki/Way),
[relations](https://wiki.openstreetmap.org/wiki/Relation).

| OSM field/key | DLP representation | Interpretation in this example |
| --- | --- | --- |
| Element type and ID | `Node`, `Way`, `Relation`; `osmId` as integer; IRI `https://example.org/osm/data/{type}/{id}` | Type-scoped identity, with one current version per element in an import. |
| `version`, `timestamp`, `changeset` | `version`, `timestamp`, `changeset` | Version/changeset are integers; timestamp is preserved lexical metadata, not interpreted event or valid time. |
| Node `lat`, `lon` | `latitude`, `longitude` as `xsd:decimal` | Validated finite degree values within latitude ±90 and longitude ±180. |
| Way `nodes` | One `WayNode` per occurrence: `ownerWay`, `memberNode`, zero-based `position` | Includes a repeated closing node and any repeated intermediate node. |
| Relation `members` | One `RelationMembership` per occurrence: `ownerRelation`, `memberElement`, `memberType`, `position`, `role` | Repeated member IDs with different/same roles remain separate records; empty roles remain empty strings. |
| Every tag | `Tag` with `ownerElement`, `tagKey`, `tagValue`, `sourceSnapshot` | Preserves unknown keys, exact values, multiple-code strings and source/version association. |
| `highway` | `highway` literal; importer may assert `RoadSegment` | Explicit road-value allowlist below, on ways only; no blanket `Way ⊑ RoadSegment`. |
| `name`, `ref`, `lanes`, `surface`, `access`, `bridge`, `tunnel`, `junction` | Same-named literal properties | Key names normalized; values unchanged. `lanes` stays lexical, and access is not converted into a permission. |
| `oneway` | `oneway` literal; has-value classes `ForwardOnewayTag`, `ReverseOnewayTag`, `TwoWayTag` | Only literal `yes`, `-1`, `no` receive those classes; absent/other values remain unclassified. |
| `maxspeed`, `maxspeed:conditional` | `maxspeedRaw`, `maxspeedConditionalRaw` | Units, symbolic values and conditions remain lexical; no inferred legal speed or unit conversion. |
| `traffic_sign` | `trafficSignRaw` | The node fixture's `DE:205;DE:206` remains intact; code taxonomy and physical sign attachment are separate. |
| Relation `type=route` and `route=road` | `relationType`, `route`; `RoadRoute` equivalent-class definition | Requires both tags and `Relation`; `route=road` alone and bus routes do not qualify. |
| Direct road-way member of qualifying road route | `partOfRoad(way, relation)` | Importer convenience projection for the listed roles; never an existential requirement, inferred transitive closure, or sole source of member ordering. |

The `RoadSegment` name means an OSM way representing a linear road in this
bounded import profile. A way may span several routing edges or junctions; the
importer does not split it. Its allowlist is `motorway`, `motorway_link`, `trunk`,
`trunk_link`, `primary`, `primary_link`, `secondary`, `secondary_link`, `tertiary`,
`tertiary_link`, `unclassified`, `residential`, `living_street`, `service`, `road`,
and `track`, excluding `area=yes`. This is an explicit application mapping,
not an assertion that every listed way permits a given vehicle. Footways,
cycleways, construction/proposed roads, other highway values, and area features
retain their tags and `Way` type for later profiles.
[Highway key](https://wiki.openstreetmap.org/wiki/Key:highway),
[OSM way/area distinction](https://wiki.openstreetmap.org/wiki/Way).

`partOfRoad` is emitted only for directly referenced, imported `RoadSegment`
ways in `type=route` + `route=road` relations, with roles empty, `forward`,
`backward`, `north`, `south`, `east`, or `west`. Other roles and nested relation
members are preserved but not projected. Neither geometric adjacency, matching
`name`/`ref`, nor being a road creates a route membership. The binary projection
collapses duplicates intentionally; the occurrence records retain their order
and roles. A route relation is not itself a legal vehicle routing graph.
[Route relations and roles](https://wiki.openstreetmap.org/wiki/Relation:route),
[road routes](https://wiki.openstreetmap.org/wiki/Tag:route%3Droad).

`oneway=-1` is relative to way-node order; `no` is explicit two-way tagging, not
universal vehicle permission. Defaults, roundabout implications, mode-specific
exceptions and conditional one-way tags are deferred. Speed values such as
`30 mph`, `none`, `signals` and conditional expressions need their own checked
interpretation. `source:maxspeed`, directional keys, and all unrecognized tags
remain available in raw records. The OSM timestamp is not the time a sign became
legally effective.
[Oneway](https://wiki.openstreetmap.org/wiki/Key:oneway),
[maxspeed](https://wiki.openstreetmap.org/wiki/Key:maxspeed),
[conditional restrictions](https://wiki.openstreetmap.org/wiki/Conditional_restrictions),
[access](https://wiki.openstreetmap.org/wiki/Key:access).

Traffic signs may be recorded on nodes or ways, and a value can represent
multiple codes. This importer preserves the source element and raw value. It
does not create a sign-to-road link from proximity, node order, or membership,
and does not infer applicability to a vehicle. The separate traffic-sign example
can use explicit `sign:locatedAtNode` and `sign:onRoadSegment` assertions while
sharing this vocabulary.
[Traffic-sign tagging](https://wiki.openstreetmap.org/wiki/Key:traffic_sign).

## Import boundary and provenance

`map_snapshot.py` is a deterministic adapter for the documented JSON subset,
not a general Overpass response reader. The input has exactly `source` (a string)
and `elements` (a list). Each element needs positive integer `id` and `version`;
nodes need coordinates, ways need 2–2000 node refs, and relations need a members
list (possibly empty). Optional fields are `tags`, `timestamp`, `changeset`, and
`visible=true`. Members require exactly `type`, positive integer `ref`, and a
string `role`. All tag keys/values are strings. Unsupported fields, missing
references, invisible elements, invalid coordinates and duplicate type/ID
records fail before output is written. Adapt XML/PBF or Overpass responses
explicitly; metadata is never silently dropped by this adapter.

One immutable `Snapshot` records the caller-supplied source identifier, a
canonical content SHA-256, and `mappingVersion`. Every imported element, tag and
occurrence links to it. Occurrence IRIs include the owning element version and
index; the tag index is based on sorted keys. Snapshot hashes are stable under
element-order changes. Tags remain exact Unicode strings, including quote and
backslash characters. The source identifier is recorded, never fetched.

This is **one current snapshot per graph**, not a history dataset: stable element
IRIs intentionally reuse the object identity across versions. Do not union old
and new imports without retracting the old assertions, occurrence records and
derived projections. A later incremental importer must diff authoritative source
records and update normalized properties, `RoadSegment`, and `partOfRoad`
together. Merely changing a raw tag triple does not update importer-generated
facts. DLP updates do maintain consequences of the normalized schema rules.

No functionality, keys, property chains or datatype ranges are asserted.
Identity/sequence validation belongs to the importer; adding OWL functionality
would merge conflicting fillers rather than act as a database uniqueness check.
The schema does not impose a unique-name assumption. Routing, legal defaults,
sign-code parsing, time conditions, spatial metrics, history/diffs, incomplete
extracts and relation expansion are deliberately outside this small example.

Sources above are OSM's own community documentation, checked 10 September 2026.
They document mapping conventions; this example does not turn community tags
into authoritative traffic regulations.
