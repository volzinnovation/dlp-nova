# Geospatial reasoning: evidence and proposed architecture

Research date: **10 September 2026**. This is a design/evidence note, not an
implemented extension or a performance result. It gives equal architectural
weight to static spatial data and live event streams. The 20 references below
are standards-owner, project-maintainer, or original implementation sources;
undated documentation is identified as such rather than assigned an inferred
publication date.

## Recommendation for this reasoner

Keep description-logic classification and geometric computation separate but
joinable. Materialize stable ontology consequences, including traffic-sign
subclasses, once. Add a native spatial access path over geometry identifiers,
then evaluate distance, direction and applicability at query time. Continuously
changing vehicle positions should ordinarily be query parameters or event
records, rather than triggers to materialize all possible nearby-object pairs.
This is an architectural recommendation, not a claim made by a standard.

For the first spatial profile, support **point proximity on WGS84** and
**planar point/line/polygon operations in explicitly supported projected CRSs**.
Use GeographicLib for ellipsoidal point distances, GEOS through its stable C API
for planar geometry operations, and PROJ for declared transformations. An R-tree
over conservative envelopes supplies candidates; the selected distance model
supplies the final decision. S2 is a useful global indexing alternative. H3 is
useful for partitioning and aggregation; its cells must not substitute for the
requested metric predicate. These choices are inferred from [S03](#s03),
[S06](#s06), [S07](#s07), [S09](#s09), [S10](#s10), [S12](#s12), and [S13](#s13).

Do not claim arbitrary ellipsoidal polygon distance merely because a point
geodesic routine is present. A global polygon/line profile needs separately
validated algorithms and reference answers, or a spatial database execution
path. PostGIS is a strong independent comparison implementation; it need not
become a required service. No dependency is added by this proposal.

## Standard and implementation status

The OGC catalog currently lists **GeoSPARQL 1.1** as its latest approved
GeoSPARQL version. Its specification was published **29 January 2024**.
Conformance is modular and must be stated by conformance class. Relevant
standard terms include `geo:hasGeometry`, `geo:asWKT`, `geo:wktLiteral`,
`geof:distance`, and `geof:metricDistance`. The latter returns metres; the former
takes a unit IRI. The approved function inventory has no `geof:dWithin`.
Therefore an indexed `distance <= radius` operation should be a documented
planner rewrite or project built-in, not an invented standard function.
GeoSPARQL geometric operations ignore Z/M values; road-network distances require
a separate capability. [OGC catalog](https://www.ogc.org/standards/geosparql/),
[GeoSPARQL 1.1](https://docs.ogc.org/is/22-047r1/22-047r1.html)

Apache Jena's GeoSPARQL page describes an implementation of **1.0**, not a claim
of complete 1.1 conformance. It demonstrates useful implementation patterns:
bounded caches for parsed geometry, transformed geometry, and spatial query
rewrites. Its documented spatial index is tied to one dataset and one SRS and
does not accept additional items once built. Those restrictions matter for a
live stream design. Its reported cache speedup is a result of its own tests,
not evidence of a speedup for this repository.
[Jena GeoSPARQL](https://jena.apache.org/documentation/geosparql/)

ASAM's catalog identifies **OpenDRIVE 1.9.0**, released **19 May 2026**, as the
current version. The specification itself bears the document date 8 May 2026.
It models static road networks; dynamic simulation content is complementary.
These dates and scopes should not be confused with a claim that OpenDRIVE
specifies a production event-stream processor.
[OpenDRIVE catalog](https://www.asam.net/standards/detail/opendrive/)

## Query semantics and planning

The following are proposed operation contracts, not existing parser syntax.

| Operation | Required meaning | Suitable execution |
| --- | --- | --- |
| `distance_le(g, anchor, radius, unit, model)` | Inclusive threshold under a declared distance model; finite nonnegative radius | Spatial candidate iterator when anchor/radius are bound, followed by exact refinement |
| `distance(g1, g2, unit, model)` | Numeric value under the same model | Compute only for retained candidates or when the number itself is requested |
| `intersects` / `covers` | Declared topology and boundary treatment | Envelope candidates plus a full predicate; prepare repeatedly tested fixed regions |
| `bearing` / `heading_difference` | Defined reference frame, angle units and wrap convention | Numeric filter over candidates; define coincident-point and zero-velocity behavior |
| `along_road_distance` | Directed lane/road-network distance, including connectivity and allowed movements | Dedicated routing/linear-reference access path |
| `applicable_sign` | Type, road/lane association, direction, valid time and domain policy | Join geometry candidates with ontology and temporal facts |

An index-aware distance predicate is preferable to an opaque scalar call over
every sign. PostGIS documents exactly this distinction: `ST_DWithin` includes
an index-compatible bounding-box test, while the final distance can then order
the reduced candidate set. Its geometry overload uses CRS units; geography uses
metres and defaults to spheroidal calculations.
[ST_DWithin](https://postgis.net/docs/manual-dev/en/ST_DWithin.html)

The proposed planner should compare two finite alternatives:

1. Start from inferred membership in the requested sign class, then fetch its
   geometry and refine distance.
2. Start from a spatial radius search, then intersect candidate feature IDs with
   the inferred class-membership set.

Neither order is universally best. Retain per-class counts, spatial population
statistics and actual candidate/refinement counts. The spatial iterator should
produce the same opaque term IDs used by the existing native relations, keeping
coordinates and decoded geometries in native memory. Return bindings/results
in batches. This avoids a Python callback or WKT parse for every pair.

Every pruning step needs a **no-false-negative** contract. An envelope hit is
not the final answer. PostGIS documents spatial indexes as pre-filters; S2 and
H3 expose different spatial approximations. These systems are evidence for the
pattern, not interchangeable definitions of distance.
[PostGIS index guidance](https://postgis.net/documentation/faq/spatial-indexes/),
[S2 nearby-edge queries](https://s2geometry.io/devguide/s2closestedgequery.html),
[H3 indexing](https://h3geo.org/docs/highlights/indexing/)

## Static data and live streams

The proposed native spatial store has two equally important paths:

| Component | Static/map path | Live/event path |
| --- | --- | --- |
| Geometry ownership | Immutable versioned geometry records keyed by RDF term IDs | Versioned observations keyed by entity and event ID; retain event time separately from ingestion time |
| Spatial index | Bulk-loaded R-tree or a packed static tree | Mutable R-tree, or a small mutable delta plus tombstones over the static base |
| Updates | Build a replacement index and atomically publish its version | Delete an object's old envelope before inserting its replacement; expiration/retraction removes its membership |
| Queries | Reuse parsed geometries, prepared regions and query plans | Read one consistent event/map snapshot; join only eligible observations/windows |
| Compaction | Infrequent rebuild on map publication | Merge base and delta when a measured size/latency threshold is reached |

This base/delta design is a project proposal, not a requirement of GeoSPARQL.
Boost.Geometry documents both packing and mutable insertion/removal; the
published performance tradeoff depends on the data and parameters. Its old
illustrative timing table must not be presented as a current benchmark.
[R-tree introduction](https://www.boost.org/doc/libs/latest/libs/geometry/doc/html/geometry/spatial_indexes/introduction.html),
[R-tree API](https://www.boost.org/doc/libs/latest/libs/geometry/doc/html/geometry/reference/spatial_indexes/boost__geometry__index__rtree.html)

Tombstones must be keyed by object **and version**, so a late deletion cannot
erase a newer observation. Replaying an event must be idempotent. A query must
deduplicate a moved object's obsolete base entry against its current delta
entry. The temporal layer must decide whether a late event changes an earlier
window; the spatial layer should consume that explicit decision rather than
infer freshness from arrival order. Ordinary native cursor invalidation is
useful today, but shared concurrent streaming will eventually need pinned
snapshots or a clearly documented single-writer protocol.

A moving query point does not require rebuilding the static sign index. Moving
hazards or vehicles that are themselves indexed do require updates to the live
index. Distinguish latest-state proximity from trajectory questions: observing
two endpoints outside a geofence does not prove that travel between them avoided
it. Interpolation must be an explicit trajectory model with its own error and
gap policy.

## Reusable computation and cache validity

For stable maps, cache parsed geometry, its CRS metadata, supported transformed
representations, and prepared polygon structures. GEOS documents prepared
geometry as an optimization for repeated predicates. Its C interface supplies
explicit ownership and thread-local reentrant contexts, matching the existing
opaque-handle C ABI design well.
[GEOS C API](https://libgeos.org/usage/c_api/)

Recommended cache keys and invalidation rules are design proposals:

- Parsed geometry: original literal identity, datatype, declared CRS, parser
  profile/version; never let geometric coincidence imply RDF `owl:sameAs`.
- Transformed geometry: source geometry version, source/target CRS, chosen
  operation, grid/data versions, axis policy and relevant coordinate epoch.
- Prepared geometry: immutable decoded-geometry version plus operation family.
- Query plan: predicate/class pattern and built-in contracts, independent of a
  particular current vehicle coordinate.
- Exact answers: map/ontology epoch, live-data/window revision, all bound query
  parameters, metric/units, topology/boundary and uncertainty policy.

Do not round positions into cell keys and reuse an exact answer unchanged.
Cell-based candidate reuse can be valid if it deliberately over-covers all
positions in the cell and always performs the current point's final test.
Likewise, a time-to-live is a memory policy, not a correctness proof for a late
event correction.

## Geographic correctness requirements

| Issue | Required design choice / test |
| --- | --- |
| Axis order | GeoSPARQL's omitted-CRS WKT defaults to CRS84 longitude/latitude. Explicit EPSG:4326 follows its authority's latitude/longitude order. Normalize at an explicit boundary; preserve original metadata. |
| Units | Distinguish angular coordinates, projected coordinate units, metres, and road-network distance. A radius labelled metres must not be compared to raw degrees. |
| Projection/model | GEOS is planar. Select an appropriate projected domain, or use an ellipsoidal point routine. Document projection validity/accuracy and error behavior outside it. |
| Transform quality | Select transformations by area/accuracy; decide whether absent datum grids or ballpark operations are errors. Record transformation resources for reproducibility. |
| Antimeridian/poles | Use a sphere-aware covering or split wrapped envelopes; naive longitude min/max is not a safe general proximity plan. Include polar, dateline-crossing and nearly antipodal fixtures. |
| Boundary | Specify inclusive distance thresholds. For region membership decide whether touching the boundary counts; `covers` and `contains` differ. Test equality at the threshold. |
| Invalid/empty input | Validate finite coordinates, supported CRS, dimension and geometry validity. Reject or explicitly report invalid/unsupported input; do not turn execution errors into negative entailments. Give empty geometry an explicit contract. |
| Height | Treat stacked roads/lane topology separately; do not assume a 2D match proves applicability on an overpass. A future 3D operation needs a separate contract. |
| Precision | Separate floating-point calculation error from positional uncertainty. Never silently enlarge the radius to conceal a numeric or sensor error. |

The axis contract follows GeoSPARQL and PROJ; PROJ's operation API also exposes
accuracy, ballpark and best-available-operation controls.
[GeoSPARQL 1.1](https://docs.ogc.org/is/22-047r1/22-047r1.html),
[PROJ FAQ](https://proj.org/en/stable/faq.html),
[PROJ functions](https://proj.org/en/stable/development/reference/functions.html)
The planar/finite-precision limitations are explicit in the
[GEOS FAQ](https://libgeos.org/usage/faq/).
Boundary inclusion and invalid-geometry cautions are documented by
[ST_Covers](https://postgis.net/docs/manual-dev/en/ST_Covers.html).

For the proposed WGS84 point profile, GeographicLib's C++ implementation returns
ellipsoidal distance and azimuth, documents polar/antipodal cases, and includes a
fallback when its Newton iteration does not converge. Its numerical accuracy
claim concerns the chosen ellipsoid and algorithm, not centimetre-accurate input
observations.
[GeographicLib Geodesic](https://raw.githubusercontent.com/geographiclib/geographiclib/main/include/GeographicLib/Geodesic.hpp)

S2 documents spherical modelling error of up to **0.56%** relative to an
ellipsoid. Recomputing only the single spherical-nearest result is not a general
proof of an exact ellipsoidal nearest result. Radius and nearest-neighbour plans
need conservative candidate bounds followed by the required metric.
[S2 modelling accuracy](https://s2geometry.io/devguide/s2closestedgequery.html)
H3's ordinary polygon fill uses cell centres; its experimental variants offer
overlap modes. A centre-based fill can miss boundary cells containing qualifying
objects. The project should validate any selected cover as an over-approximation
before using it for pruning.
[H3 region functions](https://h3geo.org/docs/api/regions/)

## Traffic-sign examples to implement and test

These are proposed query scenarios, not accepted syntax or verified legal rules:

1. **Static search:** find objects inferred to be stop signs within 50 metres of
   a supplied vehicle position. Return measured distance and the chosen metric.
2. **Applicable sign at event time:** additionally require the mapped lane,
   permitted travel direction, forward position along the road, and the sign's
   validity at the observation time. Temporary signs and variable signs use the
   live-event path.
3. **Geofence stream:** join a moving object's eligible observations with fixed
   work-zone regions, producing entry/exit or proximity events under an explicit
   temporal/window contract. A corrected late observation may retract a prior
   result; it must not mutate the static geometry cache.

For each scenario, include negative controls: a nearby sign for the opposite
carriageway, one behind the vehicle, one on an overpass, a geometrically close
but network-unreachable sign, and a temporary sign outside its validity window.
OpenDRIVE associates signals with roads, direction and lane validity and records
country-specific type identifiers. Therefore the mapping into ontology classes
must preserve country/revision and applicability metadata.
[OpenDRIVE signals](https://publications.pages.asam.net/standards/ASAM_OpenDRIVE/ASAM_OpenDRIVE_Specification/v1.9.0/specification/14_signals/14_01_introduction.html)

Geodesic distance, Euclidean distance and directed road-network distance are
different query quantities. pgRouting's maintained implementation documents
shortest-path queries over directed/undirected graphs with forward/reverse
costs. A road-distance extension should preserve that distinction rather than
renaming straight-line distance.
[pgRouting Dijkstra documentation source](https://raw.githubusercontent.com/pgRouting/pgrouting/main/doc/dijkstra/pgr_dijkstra.rst)

## Evaluation and adoption gates

Proposed correctness checks: full-scan versus indexed answer equality; both
type-first and spatial-first plans; exact radius boundaries; CRS-axis swaps;
metres versus degrees; anti-meridian/poles; invalid/empty geometries; holes and
polygon boundaries; duplicate feature geometries; equivalent individual IDs;
map replacement; move/remove/expire/replay events; late corrections; pinned
snapshots; and cache invalidation under all these operations.

Benchmark static load, cold/warm query latency, candidate counts, exact
refinements, memory, stream updates per second, expiration/retraction latency,
and tail latency during compaction separately. Vary class selectivity, radius,
density, geometry complexity, number of moving entities and out-of-order rate.
Use PostGIS and simple exhaustive fixtures as independent checks. None of the
sources below establishes speedup or completeness for this proposed extension.

## Primary-source register

Each entry identifies the exact inspected URL, status/date and evidentiary
limits. No source's age is inferred from a search engine's crawl timestamp.

### S01

[OGC — GeoSPARQL standard catalog](https://www.ogc.org/standards/geosparql/).
Current official catalog; no page publication date supplied. Lists versions
1.1 and 1.0 as implementation standards. Establishes the latest published
standard listed at the research date, not future draft adoption.

### S02

[OGC GeoSPARQL 1.1, 22-047r1](https://docs.ogc.org/is/22-047r1/22-047r1.html).
Approved OGC standard; publication date 2024-01-29. Consulted clauses 2,
10.2–10.4, 10.8.1, 10.9.14–15 and Annex B. Provides the normative vocabulary,
function/CRS contracts and conformance requirements; does not certify this
project or supply its planner.

### S03

[PostGIS — ST_DWithin](https://postgis.net/docs/manual-dev/en/ST_DWithin.html).
Maintainer reference documentation, development-manual URL; no page release
date. Documents indexed threshold evaluation, geometry/geography units and
spheroidal defaults. These are PostGIS contracts, not a native-backend benchmark.

### S04

[PostGIS — How do I use spatial indexes?](https://postgis.net/documentation/faq/spatial-indexes/).
Maintainer documentation; undated. Describes GiST/R-tree setup and index-aware
predicates as pre-filters. Does not imply that an arbitrary scalar function is
automatically indexable.

### S05

[PostGIS — ST_Covers](https://postgis.net/docs/manual-dev/en/ST_Covers.html).
Maintainer reference documentation, development-manual URL; undated. Includes
boundary semantics, index use and invalid-geometry warning. The page explicitly
does not present ST_Covers itself as an OGC-standard function name.

### S06

[GEOS — C API Programming](https://libgeos.org/usage/c_api/).
Maintainer documentation; undated. Covers stable C ABI, explicit ownership,
reentrant contexts, prepared geometry and STRtree access. Does not by itself
provide application snapshot isolation or a streaming update policy.

### S07

[GEOS — FAQ](https://libgeos.org/usage/faq/).
Maintainer documentation; undated. Explicitly limits GEOS to Cartesian planar
geometry and explains floating-point robustness issues. Transformation followed
by planar evaluation is not automatically an exact ellipsoidal operation.

### S08

[PROJ — FAQ](https://proj.org/en/stable/faq.html).
Stable documentation labelled 9.8.1 when inspected; page undated. Explains
authority-defined axis order, including EPSG:4326. This is documentation state,
not a separately verified binary release date.

### S09

[PROJ — Functions](https://proj.org/en/stable/development/reference/functions.html).
Stable API documentation labelled 9.8.1; page undated. Covers CRS pipelines,
area/accuracy selection, coordinate epochs, `ALLOW_BALLPARK`, and `ONLY_BEST`.
Available accuracy depends on transformation resources and the data's CRS.

### S10

[GeographicLib — Geodesic.hpp](https://raw.githubusercontent.com/geographiclib/geographiclib/main/include/GeographicLib/Geodesic.hpp).
Maintainer C++ source/API documentation on the moving main branch; header
copyright 2009–2024 is not a release date. Describes ellipsoidal inverse/direct
geodesics, azimuth conventions, polar/antipodal cases and iteration fallback.
A future implementation must pin a released library rather than this branch.

### S11

[S2 Geometry — S2 Cells](https://s2geometry.io/devguide/s2cell_hierarchy).
Maintainer documentation; undated. Describes the spherical cell hierarchy,
64-bit identifiers, cell unions and region approximation. Cell membership does
not itself implement an arbitrary ellipsoidal metric threshold.

### S12

[S2 Geometry — Finding Nearby Edges](https://s2geometry.io/devguide/s2closestedgequery.html).
Maintainer documentation; undated. Documents indexed distance/nearest searches,
strict versus inclusive threshold methods, spherical modelling and refinement
limitations. Index/query ownership and thread-use constraints are explicit.

### S13

[H3 — Indexing](https://h3geo.org/docs/highlights/indexing/).
Maintainer documentation; undated. Distinguishes exact logical hierarchy from
approximate geometric parent/child containment. Supports a partitioning/indexing
role, not treating hierarchy relations as exact spatial entailments.

### S14

[H3 — Region functions](https://h3geo.org/docs/api/regions/).
Maintainer API documentation labelled 4.x; page undated. Distinguishes centroid
fill from experimental full/overlapping/bounding-box modes. Experimental API
status and cover semantics must be pinned and tested before adoption.

### S15

[Apache Jena — GeoSPARQL](https://jena.apache.org/documentation/geosparql/).
Maintainer documentation; undated; explicitly describes GeoSPARQL 1.0. Provides
concrete cache categories and spatial-index restrictions. Its explanatory
planar-model discussion is not used to override GeoSPARQL 1.1's CRS contract.

### S16

[Boost.Geometry — Spatial index introduction](https://www.boost.org/doc/libs/latest/libs/geometry/doc/html/geometry/spatial_indexes/introduction.html).
Maintainer documentation, latest alias; footer copyright through 2024, page
undated. Discusses packed loading and R-tree balancing tradeoffs. The historic
machine-specific timing table is not current performance evidence.

### S17

[Boost.Geometry — rtree reference](https://www.boost.org/doc/libs/latest/libs/geometry/doc/html/geometry/reference/spatial_indexes/boost__geometry__index__rtree.html).
Maintainer API documentation, latest alias; undated. Explicitly provides
insertion, removal, spatial/nearest queries and query iterators. It does not
establish thread safety for our mutable store or choose a distance model.

### S18

[ASAM — OpenDRIVE catalog](https://www.asam.net/standards/detail/opendrive/).
Official standards catalog; identifies current release 1.9.0, 2026-05-19.
Describes static road networks and connections to complementary dynamic
simulation standards. It is not a jurisdiction's traffic-law source.

### S19

[ASAM OpenDRIVE 1.9.0 — Introduction to signals](https://publications.pages.asam.net/standards/ASAM_OpenDRIVE/ASAM_OpenDRIVE_Specification/v1.9.0/specification/14_signals/14_01_introduction.html).
Official specification; document date 2026-05-08. Defines road-relative
placement, direction, static/dynamic signals and temporary/invalidated
attributes. Country/revision are part of interpreting sign types. These data
contracts support the applicability model; they do not prove a legal decision.

### S20

[pgRouting — pgr_dijkstra documentation source](https://raw.githubusercontent.com/pgRouting/pgrouting/main/doc/dijkstra/pgr_dijkstra.rst).
Maintainer documentation on main; copyright through 2026, no page release date.
Describes directed/undirected shortest-path signatures and cost/reverse-cost
examples. Supports distinguishing network distance from geometric proximity;
does not supply a complete road-sign applicability model.
