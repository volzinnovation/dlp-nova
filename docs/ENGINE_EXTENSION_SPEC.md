# Engine extension specification: temporal, spatial and mobile execution

Implementation specification · 10 September 2026 · versioned extension interfaces

The next release should answer two concrete questions: **at what age did a
parent have their earliest recorded child, and which signs of an inferred
category are near a location or another sign?** It must preserve the difference
between a partial record and a complete history, between geographic proximity
and road distance, and between a successful empty answer and failed computation.

This specification turns the [research](TEMPORAL_GEOSPATIAL_RESEARCH.md),
[provider contract](EXTERNAL_PROVIDERS.md) and
[mobile design](MOBILE_RUNTIME_PROPOSAL.md) into implementation work and acceptance
criteria. See the [implementation guide](ENGINE_EXTENSION_IMPLEMENTATION.md) for
the implemented APIs, executable `.dlq` examples, validation evidence and remaining
release gates. The `.rules.proposed` files remain unsupported historical design
notation; the reference checkers remain independent calculations.

## 1. Deliverables and compatibility

Preserve the existing Appendix A `.dlp` syntax, L0–L3 meanings and public Python
behavior. Add a separately versioned rule/query language for filters, assignments,
aggregates and external relation access. Require explicitly declared capabilities
instead of silently interpreting unknown operations as empty relations.

The implementation must eventually have three equivalent execution paths:

- Python semantic/reference evaluator with the new operator contract.
- Python API using native execution and resident native values/indexes.
- Standalone C++ runtime, called directly, through Swift, or through Kotlin/JNI.

“Equivalent” means the same declared semantic profile, operation implementations,
data revisions and completeness rules. Desktop Python convenience libraries may
have different bundled versions; matching names alone does not establish parity.
The established native backend supplies the resident relation/join stage; the
implementation guide distinguishes that backend from the standalone native core.

The first feature release includes scoped `MIN` for Bach. This moves that
aggregate ahead of the broader aggregate/temporal-logic exploration in the
original research roadmap. General negation, arbitrary aggregate recursion,
unrestricted arithmetic recursion, uncertain historical-date intervals, arbitrary
geodesic polygon topology and lane-level routing remain separate capabilities.

## 2. Worked acceptance examples

| Example | Runs in the current engine | New computation specified by the example |
| --- | --- | --- |
| [Bach temporal](../examples/bach_temporal/README.md) | Persons, parent links, Father/Mother classification and literal birthdate facts | Validate selected date records; scoped minimum child birthdate; retain ties; completed calendar years; invalidate/retract after corrections |
| [OSM model](../examples/osm/README.md) | Node/Way/Relation vocabulary, imported road-segment/membership facts and inferred road-route/oneway classes | Production import pipeline, versioned geometry construction, spatial indexes and map-update propagation |
| [PROLIX traffic signs](../examples/traffic_signs/README.md) | Curated class hierarchy, exact observed-label/code mapping and sign/node/way/route assertions | WGS84 distance, indexed radius selection, derived sign-pair distances and optional directed road distance |
| [Existing event fixtures](../examples/temporal_geo/README.md) | These remain standalone reference computations | Finite event windows, late corrections, expiration, predecessor retention and result retractions |

Checks must report ontology-engine execution separately from independent date,
distance and stream reference evaluation. Passing a Python or C++ calculation
does not mean the proposed rule language executed.

### Bach result contract

Use the existing Bach IRIs in a separate extension; leave the thesis and benchmark
fixtures unchanged. The selected exact records give Johann Sebastian's earliest
known child age as **23** and Maria Barbara's as **24**. Restricting the input to
Wilhelm Friedemann would instead give **25** and **26**. These values belong to
the selected records, not a claim of complete historical coverage. The example
retains source/calendar provenance and an unknown exact-date case for Anna
Magdalena's family. See its README for the selected claims and disagreements.

`firstKnownChild`, `fatherAtAgeKnown` and `motherAtAgeKnown` range over one named,
versioned dataset scope. `firstChild`, `fatherAtAge` and `motherAtAge` additionally
require an externally supplied, trusted completeness certificate covering that
parent's child/date relation. The engine checks the certificate's scope/revision
and local data validity; it cannot prove real-world completeness from RDF alone.
The historical fixture supplies no such certificate. Separate synthetic cases
show the complete-scope behavior without inventing a complete Bach genealogy.

Age here is completed calendar years when the child was born, under the example's
parent/child interpretation. It is not years of guardianship or time since an
adoption. Parent roles come from the declared ontology, not from marriage alone.

### Traffic and map result contract

A sign has an observed type/code, a location node with WGS84 coordinates, and
an explicit road-segment association. The example joins that segment to a road
route relation. In general, a segment can belong to zero or several relations;
the model must not manufacture a route relation for every way.

The PROLIX CSV is a crosswalk, not a hierarchy or an equivalence ontology.
Preserve exact rows, empty cells, duplicates and spelling. Define the category
hierarchy in a separate curated artifact with complete row/label coverage and
an explicit unclassified category. A national-code observation must include its
country. An ambiguous code can establish only categories common to its candidates;
it must not select an arbitrary leaf or assert all candidate leaves as true.
Keep candidate mappings distinct from inferred sign types.

Sign-pair distance is a relation with at least `(fromSign,toSign,metres,metric,
mapRevision)`, not a unary property of one sign. For an RDF export, use a
measurement resource with source, target, value, unit, metric and provenance.
Generate pairs on demand or inside a bounded spatial join; do not materialize an
unbounded all-pairs table merely because a distance function exists.

## 3. Datatypes, functions and errors

Retain RDF term identity and lexical form in the term dictionary. Add immutable
decoded values in side tables indexed by term ID and semantic profile. Numeric
ordering must use decoded values, never the arbitrary integer IDs. New strict
operator validation must not retroactively make all ordinary legacy literal
facts illegal.

| Value domain | Initial operator contract |
| --- | --- |
| Integer | Checked signed 64-bit value for the first native arithmetic capability; larger RDF integer facts remain representable but require an additional arithmetic capability |
| Decimal | Canonical signed 64-bit coefficient and scale 0–18, representing coefficient × 10^(-scale); remove trailing zeros and normalize zero. Reject values/results outside these bounds; no implicit binary-float conversion |
| Float | Finite binary64 for declared geometry/provider operations; reject NaN/infinity inputs unless a future operation explicitly defines them |
| Calendar date | Valid normalized proleptic Gregorian year/month/day without a timezone suffix; initial supported years 1–9999. Preserve original calendar and source separately; conversion is explicit |
| Instant | Checked signed 64-bit Unix/POSIX microseconds with explicit offset or resolved zone; no host-local-time default and no silent precision truncation |
| Time of day | Separate clock-field value; date/context required for cross-midnight instant ordering |
| Duration | Fixed elapsed ticks separate from calendar months/years; never convert years to a fixed day count implicitly |
| Point/geometry | Typed native handle plus CRS, axis order, dimensionality and revision; WGS84 point input declares longitude then latitude |
| Quantity | Value with declared unit/metric; metres, seconds and km/h are not interchangeable naked numbers |

Publish this as a versioned decimal capability in the descriptor and serialized
package. Integer/decimal operations promote to decimal when either input is
decimal; integers do not silently promote to float. A float operation requires
an explicitly selected float signature/conversion. Integer-only addition,
subtraction and multiplication remain checked integers; numeric division returns
decimal and succeeds only when the exact quotient fits the profile, otherwise
`INEXACT` or `OVERFLOW`. Division by zero is `DOMAIN_ERROR`. Rounded division is
a future separately named operation with explicit scale/rounding policy.
Intermediates must be computed without machine overflow; the mathematical result
is then normalized and checked. Python and C++ use the same bounds and errors.

Required initial operations (all names below are proposed custom operations):

| Operation | Inputs / output | Required semantics |
| --- | --- | --- |
| `time:before`, `time:after` | Two values from the same supported temporal domain → Boolean | Strict comparison; equal values satisfy neither; no implicit date-to-instant cast |
| `time:completedYears` | Birth date, later date, leap policy → integer | Later date must not precede birth. Count completed calendar anniversaries; default `march1` for 29 February in common years, an explicit product policy rather than a legal-age rule |
| Numeric comparisons | Compatible decoded numbers → Boolean | Type/units checked; stable promotion rules; unrelated RDF value domains are not ordered |
| Add/subtract/multiply/divide | Declared compatible quantities → quantity | Checked bounds, explicit units/promotion and zero-division behavior |
| `sp:wgs84Point` | Longitude, latitude in degrees → point | Validate finite longitude ±180 and latitude ±90; preserve longitude-first input order and the WGS84 metric profile |
| `sp:wgs84Distance` | Two valid points → metres | Ellipsoidal shortest point geodesic using the selected GeographicLib implementation; not a spherical haversine or road route |
| Planar geometry distance / `dwithin` | Compatible projected geometries, optional radius → metres/Boolean | Require metre-based CRS units or an explicit checked length-unit conversion; GEOS returns coordinate units. Inclusive finite nonnegative radius and explicit boundary behavior |
| `contains`, `covers`, `intersects` | Compatible geometries → Boolean | Separate boundary contracts; empty/invalid geometries follow the declared operation policy |
| Interval contains/intersects/meets | Proper `[start,end)` intervals and/or instant → Boolean | Strictly positive length; intersects iff max(starts) < min(ends). Adjacent intervals meet without intersecting; Allen overlaps is a separate future relation |

For a normalized date pair, completed years starts with `later.year - birth.year`
and subtracts one when the later month/day precedes the applicable anniversary.
Do not use elapsed days divided by 365 or 365.25. Extracting the year component
of a duration is also a different operation.
[W3C date/duration function contracts](https://www.w3.org/TR/xpath-functions-31/)

Missing data normally produces no positive input row. A malformed/conflicting
typed value is a diagnostic, not an arbitrary chosen value. A valid `false`
filter, invalid argument, unavailable capability, cancelled call, incomplete
enumeration and complete `no_route` are distinct outcomes. The strict API must
not publish an ordinary complete answer when required provider evaluation failed.
An explicit partial-results API may return resolved rows with status and scope.

The Bach `Known` queries deliberately select `accepted-exact-records-v1`: omit
persons with missing, malformed or conflicting birthdates from the accepted-date
relation, preserve diagnostics, and compute over the remaining accepted records.
Such a result can be complete for that selected view while incomplete as a family
history. Return both statuses and the selection-policy version. Do not turn it
into an unqualified first-child answer. This named data-selection policy never
licenses silently dropping timed-out provider replies or incomplete scan pages.

## 4. Rule language, IR and planning

Do not encode every built-in as an ordinary `Atom`: the existing evaluator would
treat most names as stored predicates and derive the wrong binding/dependency
semantics. Add explicit body/plan nodes:

- `RelationAtom`: stored relation pattern, with existing EQ/NEQ treatment preserved.
- `Filter`: required input slots and a Boolean expression.
- `Bind`: required input slots, declared result type and output slot; a previously
  bound output is checked for value agreement rather than overwritten.
- `Aggregate`: a named input relation/subplan, group keys, input expression,
  scope, output slots and distinctness policy; a stratum boundary.
- `ProviderScan`: finite indexed enumeration with binding modes, snapshot,
  pagination and coverage contract.
- `WindowSource`: a finite versioned relation maintained by the event subsystem,
  not a scalar function that reads an implicit clock.

The registry records operation URI/version, input/result types, required bound
positions, determinism, snapshot dependencies, output cardinality, error policy,
available implementations and supported batches. Parser errors identify source
location; validation errors identify rule, operation and unbound/mismatched slots.
Syntax in the examples is a design notation to lower to this IR, not a commitment
to implement a general SPARQL or N3 processor.

Plan ordinary atoms freely within legal binding dependencies. Apply selective
bound filters early and use a spatial scan when it can enumerate a complete
candidate superset. A required-input function cannot be scheduled before its
inputs. Expensive routing follows type/radius/direction filtering when that
filter is justified by the requested route metric. `EXPLAIN` must show binding
order, scans/refinement, aggregate strata, capabilities and snapshot dependencies.

Initially allow pure filters in recursive positive rules. Reject aggregate cycles
and unproved value-generating arithmetic/assignment cycles; a rule such as
`n(x+1) :- n(x)` must not become an accidental unlimited generator. Preserve the
existing bounded existential behavior for declared L3 rules independently.

## 5. Scoped minimum and incremental age derivation

The Bach plan has four stages: validate accepted birthdates; form unique
`(parent,child,date)` rows; take `MIN(date)` grouped by canonical parent; join the
minimum back to retain every tied child. Run the aggregate only after its source
positive stratum reaches a fixed point. Empty groups emit no minimum.
Aggregate stratification is also a constraint in established Datalog systems;
the contract here additionally specifies mutable scopes and provenance.
[Soufflé aggregate restrictions](https://souffle-lang.github.io/aggregates)

Maintain group membership keyed by child identity, with an ordered date-to-child
index. Multiple derivations of one input fact must not duplicate the child.
Different children with the same date remain distinct supports. On insertion or
deletion, compare old and new output sets and emit only necessary retractions and
additions. Removing the last minimum exposes the next minimum; removing one twin
retains the other and the shared age. Correcting the parent's date changes the
age even if the child minimum stays unchanged.

For small groups the initial correct implementation may recompute the affected
group and its dependent stratum. It must not reuse ordinary monotonic insertion
logic for `MIN`: adding an earlier child can retract a result. Keep old input
snapshots or complete input/support state needed for removals. Certify incremental
combinations explicitly; use a full affected-view rebuild otherwise.

One person must have one accepted date value in a given selection scope.
Value-equivalent lexical variants can deduplicate, but conflicting dates must
not be resolved by taking the minimum. Unknown/conflicting child dates and
incomplete source closure block the completeness certificate. A certificate
expires on a relevant child/date/identity revision unless renewed in the same
transaction. Equality merges/splits can change groups and require regrouping or
rebuilding; the existing equality-free DRed eligibility is not sufficient proof
for aggregate maintenance.

Accepted-date selection is itself a scoped, nonmonotonic stage: adding a second
conflicting date retracts the formerly accepted row even when the new date is
later. Removing that conflict can restore it. Revalidate on identity merges and
splits. Include validation dependencies in affected-view maintenance and prohibit
recursive cycles through this uniqueness/selection stage just as for `MIN`.

## 6. OSM ingestion and spatial execution

Use the [example OSM model](../examples/osm/README.md) as the initial import
contract. Nodes, ways and relations have separate ID spaces. Preserve ordered
way-node occurrences, ordered relation membership and roles, including repeated
members. A way is not inherently a road or an area; classify a road segment from
the documented tag subset. `type=route` plus `route=road` identifies the example's
road-route relation. These modeling choices follow OSM's element structure.
[OSM elements](https://wiki.openstreetmap.org/wiki/Elements)

The example mapper is deliberately finite and local. Production ingestion must
add streaming PBF/XML/change input, strict one-version snapshot rules, missing
reference handling, resource limits and transactional updates. Preserve raw tags
before projecting `highway`, `name`, `ref`, `oneway`, `maxspeed`, `lanes`, `surface`,
`access`, `bridge`, `tunnel`, `junction` and traffic-sign tags. Conditional,
directional, lane-specific and unit-bearing values require their own parsers;
do not treat `50 mph`, `none`, `walk` or a conditional limit as an unqualified
50 km/h. An unsupported value remains observable as raw data.

Separate a physical sign observation from the OSM node on which it is located:
one node can host several signs. Segment association is explicit map/importer
data, with provenance; it does not follow solely from nearest geometry or imply
the sign governs both travel directions. OSM membership order is not a general
proof of traversability, and shared route membership does not establish a path.

Retain decoded static geometry and a spatial index across queries. WGS84 point
candidate selection must be conservative at the antimeridian/poles and refined
by the exact declared metric. GEOS planar bounding boxes alone are not a complete
ellipsoidal-radius plan. Keep full scans as a finite reference baseline and
compare indexed answer sets against them. Build/prep static geometry once; reuse
it for changing vehicle positions.

Track reverse dependencies from node coordinates to way geometry/index entries,
sign positions, affected route tiles and query caches. Node movement, way-node
order changes, relation changes and sign-code changes can each alter answers.
OSM metadata timestamps describe map edits, not automatically the real-world
validity of a sign or road restriction. Valid-time assertions are separate facts.

Raw-tag or membership/role changes must recompute importer-generated projections
such as `RoadSegment` and `partOfRoad` in the same source transaction. Changing a
raw tag with the current `Engine.update()` cannot execute arbitrary mapper logic;
ordinary DLP consequences of the updated normalized facts are maintained separately.

## 7. External providers, snapshots and failures

Implement the [provider contract](EXTERNAL_PROVIDERS.md) alongside the first
local scalar operations. Supply a deterministic fake provider and loopback
adapter before a vendor-specific routing/GIS integration. Deduplicate exact
argument tuples, batch calls and correlate every result to its inputs. Bound
outstanding calls, retained bytes, retries and deadlines.

Every query pins ontology/data, provider implementation, provider dataset,
traffic/costing and relevant temporal/CRS revisions. A result cache key includes
those dependencies and exact normalized arguments. Negative results are reusable
only for the same complete contract/revision. Approximate geospatial buckets or
time buckets cannot stand in for exact cache keys unless approximation is an
explicit operation policy.

Provider changes need a change feed or explicit invalidation/re-enumeration,
including objects that newly enter a radius or newly become reachable. Old
positive witnesses alone cannot reveal those additions. DRed must not recompute
an old proof against a silently changed remote world. Retain old snapshots/results
or conservatively rebuild the affected view.

Fix the failure boundary before invoking fallible providers: currently
`Engine.materialize()` sets `complete=True` before `_run()`. Introduce an internal
running/stop state distinct from published completeness, or a guaranteed exception
path that marks results incomplete and prevents complete-answer cache writes.
For the new runtime, stage a candidate revision and publish it only on successful
commit; retain a separately identified last complete snapshot when available.
Cancellation or malformed partial batches must not leave a new revision appearing
complete. Do not hold context locks or mutable borrows across asynchronous network
waits; retain owned lifetime and snapshot references for outstanding work.

## 8. Native runtime, serialization and mobile ownership

Add a domain-provider ABI and a runtime ABI alongside the existing store ABI;
version each explicitly. Proposed runtime responsibilities are load program/data,
apply a transaction, prepare/query, read bounded result pages, cancel, inspect
status/provenance, checkpoint and close. Functions take owned/borrowed handles
with documented lifetimes, typed buffers and lengths. Exceptions remain inside
C++; callers receive structured status.

Port authoritative facts, term dictionaries, fixed-point scheduling, equality
and congruence, witness interning, constraints, limits, query semantics and
maintenance into C++. Merely adding JNI or a Swift wrapper around
`native_store.cpp` cannot run the current reasoner independently of Python.
Serialize all operations on a context, including query cursors and close, through
one worker/actor until a separately tested concurrency model exists.

Define a portable rules/data package with format version, semantic profile,
required operation versions, stable typed dictionary entries, rule IR, source
provenance, data revisions and optional precomputed closure/index sections.
Use explicit endian/length encoding; do not serialize pointer-bearing structs,
Python hashes, pickle objects or native unordered containers. Include the state
needed for the promised update capability, or mark a closure package read-only
and rebuild from authoritative assertions for updates. A parser/validator rejects
unknown required capabilities, truncated sections and invalid references before
publishing a loaded context.

Retain `date`/GeographicLib, optional GEOS/PROJ and version-qualified road providers
from the [mobile selection](MOBILE_RUNTIME_PROPOSAL.md). Expose the same runtime
through Python C ABI, iOS Swift/C module and Android JNI. Ship precompiled native
libraries, not the existing runtime compiler. Package timezone/CRS/map resources
separately with explicit versions and offline availability. Device and simulator
builds, Android ABI/page-size requirements and library licensing belong to the
artifact contract.

## 9. Event streams and bounded state

Keep static-map and live-event work in parallel implementation tracks. A finite
window relation needs event identity, event time, accepted revision, explicit
evaluation time/watermark, lateness policy and retention. Use `[start,end)` and
expire rows when progress advances even if no new event arrives. Deduplicate
replayed IDs; preserve distinct events with equal values/timestamps. “First
child” groups are durable dataset aggregates, not sliding windows.

Emit result additions/retractions with stable identity and revision. Keep enough
predecessor state for observed-entry detection; dropping an expired predecessor
must not invent a new entry. Bitemporal facts distinguish valid and recorded
intervals. Never substitute a hidden wall clock for the query's temporal context.

Bound event logs, active windows, group/support indexes, provider work and result
caches under an explicit replay/retention policy. Checkpoints must cover accepted
offsets, progress, active/support state and static-data versions. Mobile suspension
or process death can interrupt execution; resume deterministically or report the
unrecoverable gap. Continuous background execution is not guaranteed merely by
using a native library.

## 10. Implementation backlog and release gates

The table below records the required work and acceptance gates. The
[implementation status](ENGINE_EXTENSION_IMPLEMENTATION.md#remaining-release-work)
identifies completed work and remaining qualification. The examples and contracts establish
reviewable acceptance fixtures; they are not evidence these tasks are implemented.

| ID | Work / current source seam | Dependencies | Completion evidence |
| --- | --- | --- | --- |
| E01 | Typed values and operation registry; `model.py`, new domain module | Contracts above | Cross-language valid/invalid/overflow/precision fixtures; stable decoded-value cache keys |
| E02 | Separate rule/query parser, typed IR and mode/stratum validation; `parser.py` remains compatible, extend `model.py` | E01 | Parse/lower worked rules, precise errors, reject unbound inputs and forbidden cycles |
| E03 | Reference execution and failure state; `Engine._validate/_prepare_rules/_solutions/_run/materialize`, `joins.py` | E01–02 | Bach and sign bound queries execute as rules, failures never produce complete cached answers |
| E04 | Scoped `MIN`, ties, certificates and group maintenance; dependency/update machinery | E03 | Earlier-child insertion/deletion, twins, conflicting/missing dates, parent correction and stale certificate outcomes |
| E05 | Native domain values/providers and batched plan dispatch; `native.py`, new C ABI, native plans | E01–03 | Same rule answers with Python/native backends; no scalar Python callbacks inside native batches; ownership/error checks |
| E06 | OSM production mapper and resident spatial indexes; provider scan planner | E03, E05 | Typed IDs/ordered members/raw tags, exact indexed-versus-exhaustive radius answers, node-move invalidation |
| E07 | External computation/scan adapters and revision-aware cache; `reasoner.py`, `query_cache.py`, provider module | E03 | Reordered/missing/duplicate replies, provider-only changes, newly qualifying rows, cancellation and cache dependencies |
| E08 | Window/replay/late-data runtime and incremental view publication | E03–04, E07 | Existing stream fixtures execute as maintained rules, including idle expiration and suspend/resume |
| E09 | Complete native semantic runtime; port Python engine/reasoner semantics and maintenance | E04–08 | Declared profile parity for equality, constraints, witnesses, updates and incomplete states without CPython |
| E10 | Portable rule/data package, loader, checkpoints and ahead-of-time ontology compiler output | E02, E09 | Round-trip/replay parity, incompatible/truncated package rejection, static package reuse across hosts |
| E11 | iOS/Android bindings and reproducible mobile artifacts | E05, E09–10 | Real Swift/JNI fixture execution on device, resource bundles, memory pressure and 16 KB Android checks |
| E12 | Optional regional road routing / lane-data integration | E06–07; E11 for phones | Pinned-core/data parity, one-way/unreachable/out-of-region cases and measured resource costs |

E03–04 can deliver Bach on desktop while E05–08 develop native geometry and live
events. E09 must preserve safe fallback/rebuild behavior; an incomplete port may
advertise only an explicitly restricted capability set. E11 compilation prototypes
can proceed earlier, but a complete mobile reasoning release depends on E09–10.

Release gates:

1. **Reference feature slice:** actual new-language execution of the Bach
   calculations, traffic hierarchy/radius queries and finite event-window cases;
   strict diagnostics and fake external provider behavior.
2. **Native query slice:** resident values/geometry, native batches, indexed
   enumeration, scoped aggregate updates and identical answers under every
   cache-invalidation fixture. Measure candidate rows, provider calls, decoded
   values, allocations and warm-query latency against the exhaustive baseline.
3. **Standalone/mobile slice:** full declared semantic runtime, versioned packages,
   Swift/JNI execution and deterministic replay. Measure cold/warm latency,
   resident memory, app/data size and energy on actual devices before claiming
   a speedup or mobile resource budget.

No existing thesis benchmark artifact should be regenerated to imply support for
these extensions. Keep new acceptance and performance evidence separately named.
