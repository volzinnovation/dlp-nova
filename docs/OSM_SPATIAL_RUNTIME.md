# Bounded OSM ingestion and resident point indexes

`dlp_reasoner.osm` provides a current-snapshot store with transactional XML and
ordered change ingestion. `dlp_reasoner.spatial` provides resident WGS84 point
indexes in Python or C++, finite provider scans, and exact radius refinement.
These are separate from the Appendix A ontology parser. The initial mapping
contract and road/tag subset remain documented in [the OSM example](../examples/osm/README.md).

## Current snapshots and changes

```python
from dlp_reasoner.osm import OSMStore, OSMLimits

store = OSMStore(backend="native", limits=OSMLimits(max_elements=100_000))
initial = store.load_xml("extract.osm", source_id="urn:map:extract-2026-09-10")
updated = store.apply_xml("next.osc")

graph = updated.graph()       # independent RDFLib Graph, preserving raw tags
changed = updated.affected    # typed IDs affected by source/dependency changes
added = updated.additions     # RDF additions compared with the prior snapshot
removed = updated.retractions
```

`load_snapshot(records, source=...)` also accepts an iterable of validated
`Element` values or element dictionaries. Each dictionary follows the example
JSON element shape. `apply_changes` accepts `Change("create" | "modify" |
"delete", record)` objects. XML parsing is incremental, including a final drain
after parser closure. The entire input iterator must finish successfully before
the new snapshot is published.

Nodes, ways and relations use distinct positive signed-64-bit ID spaces. A
snapshot contains exactly one record per typed ID, with a positive version.
Subsequent creates require a previously unseen ID at version 1; modifies and
deletes require exactly the current version plus one. A transaction contains at
most one change per typed ID. Deleted IDs retain a bounded version tombstone,
so reusing one as a new create fails. This strict consecutive-change profile
does not silently accept skipped replication versions or merge history files.

All references must resolve in the final candidate snapshot. Creating a node
and changing a way to reference it in the same transaction is valid. Deleting a
referenced node without removing/changing its incoming references fails. The
store performs no network fetch to complete an extract. Raw tag strings,
ordered way-node occurrences, repeated relation members and arbitrary member
roles are preserved. XML duplicate tag keys, unsupported fields, malformed
documents, DTD/entity declarations, UTF-16/32 input and conditional `if-unused`
delete actions fail explicitly. Snapshot extraction bounds are checked as
metadata; they are not asserted as a closed-world geographic coverage guarantee.

The importer projects the documented tag subset and `RoadSegment` classes.
`partOfRoad` requires a direct road-way member of a `type=route`, `route=road`
relation with a recognized road role. The ontology can infer `RoadRoute` from
the normalized relation tags after its schema is loaded. Raw `maxspeed`,
conditional and other unsupported values stay strings; no unit conversion,
default traffic permission or sign applicability is invented.

Every successful publication has an immutable `OSMSnapshot`: current elements,
tombstones, reverse dependencies, ordered way geometries, RDF triples, digest
and resident node point index. Node changes invalidate dependent ways and
transitively containing relations. Relation edits also mark old/new member
targets affected because projected `partOfRoad` facts occur on those targets.
Unchanged way-geometry tuples are reused. Current RDF projections and the point
index are rebuilt conservatively for each changed map snapshot; source-snapshot
provenance causes additional RDF changes. This first version does not claim
per-tile or in-place incremental index maintenance.

`OSMLimits` bounds source bytes, element/tombstone counts, normalized retained
record bytes, changes, tags, string bytes, way nodes, relation members and mapped
triples. Coordinate decimal precision is bounded as well. The record-byte bound
is conservative payload/container accounting, not an operating-system RSS
limit: the old and candidate snapshots coexist during a transaction, and the
XML/PBF libraries have their own bounded decoding buffers. For large regions,
choose limits from measured memory needs or partition before ingestion.

An exception leaves `store.snapshot` exactly unchanged; no incomplete candidate
is published. This atomic boundary covers the store's source, projections,
geometry and index. It does not automatically update a separately owned
`Reasoner`: the host must materialize/validate the corresponding ontology revision
before publishing it alongside the new map snapshot. Returned graphs are copies.
Contexts are serialized by their host, and reentrant store updates fail.

`MapRuntime` implements that combined publication boundary when the source and
ontology belong to one host:

```python
from dlp_reasoner.map_runtime import MapRuntime
from dlp_reasoner.reasoner import read_graph

ontology = read_graph("examples/osm/ontology.dlp")
with MapRuntime(ontology, backend="native") as maps:
    snapshot = maps.load_xml("region.osm", source_id="region-v1")
    # snapshot.reasoner, snapshot.map.point_index and snapshot.scope match.
    snapshot.validate()
```

Pass `Change` records to `maps.apply_changes()` or an XML change document to
`maps.apply_xml()`. It builds a candidate ontology closure before publishing it
with the source/index. Invalid input, incomplete reasoning or inconsistency
leaves `maps.snapshot` at its last valid revision and sets `maps.complete=False`.
No query against that older snapshot should be labeled as the failed revision.
This first adapter rebuilds on map transactions and reuses the published closure
for queries. Old returned publications remain valid until their owner calls
`snapshot.close()`; keep and release them deliberately. Treat their reasoner as
read-only: explicit mutation is detected by `snapshot.validate()`/`.scope`.
Closing `MapRuntime` closes its current publication, not older caller-owned ones.

## Optional PBF reader

```sh
uv pip install --python .venv/bin/python '.[osm]'
```

```python
from dlp_reasoner.osm import OSMStore, OSMLimits, PyOsmiumReader

limits = OSMLimits(max_elements=100_000)
store = OSMStore(limits=limits, pbf_reader=PyOsmiumReader(limits=limits))
snapshot = store.load_pbf("extract.osm.pbf", source_id="urn:map:extract")
```

PyOsmium is an explicit optional dependency; the default store reports
`capabilities["pbf"] == False`. `PyOsmiumReader` uses the documented streaming
`FileProcessor` API, without enabling a second implicit node-location cache.
The adapter copies tags, node IDs, member IDs/roles, coordinates and metadata
before advancing the reader: PyOsmium objects are borrowed views whose lifetime
does not extend beyond their current iteration. [File processing API](https://docs.osmcode.org/pyosmium/latest/reference/File-Processing/),
[object lifetime](https://docs.osmcode.org/pyosmium/latest/user_manual/01-First-Steps/).

Decoded records pass through the same source validation and transaction boundary.
Default/absent metadata exposed by libosmium as zero UID/changeset, empty user or
epoch timestamp is omitted; the adapter does not claim byte-for-byte retention
of optional-field presence or original timestamp spelling. A source edit time
never becomes a real-world valid-time assertion. The supported PyOsmium object
properties and ordered references are described in its [data-container API](https://docs.osmcode.org/pyosmium/latest/reference/Dataclasses/).

The optional test writes a small real PBF with `SimpleWriter`, reads it after the
writer closes, and verifies owned copied records after reader exhaustion. It
passed locally with PyOsmium 4.3.1. Without the extra, that format roundtrip is
skipped and missing-capability behavior still has a deterministic test. A custom
streaming adapter with `.read(path)` can be supplied explicitly; a fake adapter
test validates that boundary and is not labeled PBF conformance.

## WGS84 candidate selection and exact refinement

```python
from rdflib import URIRef
from dlp_reasoner.domains import Point
from dlp_reasoner.spatial import PointIndex

points = {URIRef("urn:sign:1"): Point(8.0, 48.0)}  # longitude, latitude
with PointIndex(points, revision="map-42", backend="native") as index:
    candidates = tuple(index.candidates(Point(8.001, 48.0), 100))
    exact = index.within(Point(8.001, 48.0), 100)
```

All points are validated WGS84 longitude/latitude in degrees; distance is the
shortest ellipsoidal surface distance in metres without altitude. The candidate
index converts each point once to Earth-centered Cartesian coordinates on the
WGS84 ellipsoid. An axis-aligned box of radius `r` encloses every point whose
Euclidean chord distance is at most `r`; chord distance cannot exceed surface
geodesic length. Thus every actual radius answer survives this candidate test,
including at poles and the antimeridian. A one-micrometre padding covers
binary64 coordinate conversion error and equivalent pole/wrap representations.

Both backends retain three sorted coordinate columns and search the smallest
axis interval. The C++ ABI keeps the index resident and returns bounded cursor
batches; it does not allocate the entire candidate set. `within` refines
candidates in batches through the shared `wgs84Distance` operation, with an
inclusive `distance <= radius` boundary. A candidate set alone is never an exact
radius answer. An unavailable exact geodesic capability or domain error raises
an error instead of returning an empty result. Query statistics separately count
candidates and exact evaluations; tests compare full answers with exhaustive
distance evaluation and verify that selective queries avoid unrelated distances.

`PointIndex.from_location_view(view, revision=...)` builds sign points only from
the accepted location view. It retains that view's diagnostics and a source
revision guard; later Reasoner/graph mutation requires rebuilding the index.
It does not silently retain stale candidates when a newly added point could
change an answer. Directly supplied point mappings are copied and made read-only.

## Provider and native boundaries

`index.register(provider_registry)` registers
`urn:dlp:spatial:pointCandidates` with inputs `(Point, radius, snapshot)` and
single IRI output rows. The explicit snapshot term must identify the index
revision. Its descriptor declares a candidate superset, so an executable query
must apply exact refinement before presenting radius answers. `OSMStore.register_points`
uses a dynamic adapter that follows the store's current snapshot; a map update
invalidates a suspended scan or cached provider revision. `PointProvider` can
also wrap a callback returning another current index.

`native_spatial.h` exposes the small C-compatible opaque-handle interface.
`native_spatial.cpp` needs only C++17. The Python adapter builds it in the native
user cache with source/header/compiler/platform fingerprints, or loads an
ahead-of-time shared library from `DLP_SPATIAL_LIBRARY`. No compilation or
dependency download occurs on import. A mobile host can call this same C ABI,
providing prepared XYZ rows; this is distinct from running Python/PyOsmium on a
phone. Scalar geodesics remain in the shared domain ABI.

Index and cursor ownership is explicit. C++ query handles retain their immutable
index data; Python cursors close on exhaustion, error or explicit early close.
Closing an index rejects resumed Python enumeration. Retain old snapshots only
as long as an application needs them; their resident indexes have a `close()`
method and native finalizers as a fallback.

Run the focused verification with:

```sh
.venv/bin/pytest -q tests/test_osm.py tests/test_spatial.py
```
