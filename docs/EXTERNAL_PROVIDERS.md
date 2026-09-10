# External computation and relation providers

Design extension · 10 September 2026 · proposed interfaces, not implemented APIs

External systems are a first-class requirement for the
[temporal/geospatial extension](TEMPORAL_GEOSPATIAL_RESEARCH.md). A rule should
name a logical operation; deployment configuration chooses a compatible local
library, database, or remote service. For example, distance computation may run
in an existing GIS service while the engine retains ontology classification,
joins, comparisons, and query planning.

Use one operation registry with separate **computation** and **relation-access**
contracts. Keep transport adapters outside the logic language and network calls
outside the native join loop. This document defines the proposed boundary and
its acceptance criteria; no connection to an external service is configured here.

The [shared native library selection](NATIVE_DOMAIN_LIBRARIES.md) maps these
contracts to ICU/date, GEOS/PROJ, Valhalla/OSRM and Lanelet2, with Python and
C++ binding evidence and packaging constraints.
The [mobile refinement](MOBILE_RUNTIME_PROPOSAL.md) adds Swift/JNI bindings,
on-device providers and offline capability/version requirements.

## Logical operations and physical adapters

| Provider contract | Example | Required behavior |
| --- | --- | --- |
| Bound computation | Distance between two supplied geometries | Required inputs bound; one correlated value or explicit domain/error status per input row |
| Indexed relation access | Enumerate signs within a radius | Declared binding modes, finite cursor, candidate-coverage contract, stable pagination and explicit exhaustion |
| Observation source | Current travel-time estimate from a changing service | Recorded inputs/results with observation identity and time; updates enter as data |

HTTP/JSON, gRPC, a SQL connection, a process boundary, and an in-process C/C++
adapter are possible transports for these contracts. A desktop prototype can use
a Python-managed adapter interface and HTTP/JSON for remote computation. Mobile
uses the shared native boundary with Swift/Kotlin host networking as needed.
Use a PostGIS adapter
when the provider can perform indexed spatial selection. Optimize transport or
move dispatch into native code only after measuring it.

Do not treat every service as an interchangeable implementation of `distance`.
The semantic contract includes metric, dimensionality, units, CRS/axis order,
snapping, and approximation. Distinguish ellipsoidal distance, projected-plane
distance, shortest network distance, length of the fastest route, and travel
duration. For example, OSRM's documented table service returns lengths of
fastest routes, which need not be shortest-distance routes. Its API also defines
unreachable cells and optional estimated fallbacks; an adapter must preserve
those distinctions. [OSRM 5.24 API, table service](https://project-osrm.org/docs/v5.24.0/api/#table-service)

The following rule notation remains a proposal:

```text
query NearbyStops(?sign, ?metres) given (?position, ?at, ?radius) :-
    ex:StopSign(?sign), ex:geometry(?sign, ?geometry),
    ex:validDuring(?sign, ?valid), filter time:contains(?valid, ?at),
    bind sp:distance(?position, ?geometry, unit:metre) as ?metres,
    filter num:lessEqual(?metres, ?radius).
```

Here the execution context selects an explicit metric, and the registered
`sp:distance` implementation can call an external service supporting that exact
contract. The rule contains neither an endpoint nor credentials. A route query
would instead call a distinct custom operation such as
`route:fastestRouteLength(?from, ?to, ?profile, unit:metre)`; configuring a routing
service must not silently replace the metric of the first query. These names
are project extension names, not claims about GeoSPARQL standard functions.

If the provider supports indexed `dwithin` with equivalent semantics, the planner
may push selection into that provider. A scalar distance service alone does not
provide an index: it still needs a locally or externally generated finite set
of pairs. PostGIS documents an index-assisted distance predicate that is useful
for this second contract. [PostGIS ST_DWithin](https://postgis.net/docs/ST_DWithin.html)

## Proposed adapter contract

The operation registry owns types and logical meaning. A provider advertises
which contracts it implements and the modes in which it can execute them.

```text
capabilities()
  -> operations, semantic versions, input/output types and modes,
     metric/CRS/unit support, consistency class, batch/page limits

prepare(operation, bound_columns, options)
  -> access path and cost/cardinality hints; no remote computation

begin(context, required_revision)
  -> evaluation handle and verified consistency metadata

evaluate_batch(handle, operation, rows_with_ids, deadline)
  -> one status/result per submitted row, possibly out of order

open_scan(handle, operation, input_rows_with_ids, deadline)
  -> cursor
next_page(cursor)
  -> correlated output rows, per-input completion, continuation

changes(from_revision, to_revision)  [optional capability]
  -> complete changed keys/deltas, or explicit whole-revision invalidation

cancel(handle_or_cursor)
close(handle_or_cursor)
```

A provider implements the computation or scan methods appropriate to its
capabilities; it need not implement both. Capability discovery can be cached
from configuration or explicit setup. Planning/estimation must not issue a
distance request while considering hypothetical join orders. The current
`Index.lookup`/relational planner interface does not supply this separation.
See the [engine audit](research/engine-extension-audit.md).

For computations, every submitted row must receive exactly one terminal status.
Unknown IDs, duplicate terminal replies, incompatible value types, wrong units,
revision mismatches, or missing rows at completion are protocol failures. For
scans, zero results are meaningful only after explicit completion for that input.
A page limit is not proof of exhaustion. Candidate-only providers must advertise
their no-false-negative coverage and required refinement; exact providers must
advertise the predicate they actually evaluate.

This is an illustrative project-level request/reply shape, **not an existing
service's API**. An adapter translates it to a provider's actual protocol.

```json
{
  "request_id": "batch-17",
  "operation": "sp:distance",
  "semantic_version": "1",
  "metric": "wgs84-ellipsoidal-2d",
  "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
  "axis_order": ["longitude", "latitude"],
  "output_unit": "metre",
  "required_algorithm_revision": "distance-model-4",
  "rows": [
    {"row_id": "r1", "from": [8.4, 49.0], "to": [8.4, 49.0]}
  ]
}
```

```json
{
  "request_id": "batch-17",
  "operation": "sp:distance",
  "semantic_version": "1",
  "algorithm_revision": "distance-model-4",
  "metric": "wgs84-ellipsoidal-2d",
  "output_unit": "metre",
  "complete": true,
  "rows": [
    {"row_id": "r1", "status": "ok", "value": 0.0}
  ]
}
```

The zero distance is a synthetic coincident-point example. For exact integers
and decimals, use tagged lexical values rather than a JSON float that can lose
precision. Remote systems receive typed values or agreed stable external
identifiers, never the native store's process-local integer term IDs. The
adapter retains the row-ID-to-binding mapping and interns validated results
through the engine's value boundary.

## Batching and query execution

For bound computations, use this path. An indexed relation provider may instead
lead or interleave the join once its required inputs are bound; it need not wait
for a full local relation scan.

1. Evaluate selective local class/property joins and cheap bound filters.
2. Collect a bounded batch of required argument tuples, retaining every original
   binding for the later join. Deduplicate equal calls within the batch.
3. Reuse eligible cached results and coalesce concurrent identical requests.
4. Dispatch cache misses with bounded concurrency, provider limits, deadline,
   cancellation, and backpressure. Native work yields at an explicit batch
   boundary; it does not make blocking callbacks for every joined row.
5. Validate replies and expand each result back to all its original bindings.
   Resume arithmetic filters/joins and publish only under the query's stated
   completeness contract.

Coalesce requests only when their full semantic and consistency keys match.
Shared work needs explicit ownership and compatible execution deadlines; each
consumer retains its own deadline/cancellation state. Cancelling or closing one
query must not cancel or free work still required by another.

The consistency handle covers every batch and scan page belonging to the query.
Current native cursors do not provide snapshot isolation: initially serialize
the relevant commits or use a verified generation/retry protocol. An external
snapshot does not by itself pin the local relation index.
Copy the bounded input bindings and release native context locks before network
I/O. Before accepting returned values, verify that the local and provider
generations still meet the execution contract.

A local prefilter is legal only if it cannot remove a qualifying external result.
For network metrics, a straight-line bound needs a proof under the declared
snapping and route contract; a guessed radius is not an exact optimization.
Never optimize a shortest-route query by evaluating only an arbitrary nearest-k
set without proving that the omitted candidates cannot win.

## Consistency, caching, and live services

| Consistency class | Required evidence | Permitted reuse |
| --- | --- | --- |
| Pure, versioned computation | Same immutable arguments and pinned algorithm/options | Memoization across queries by the complete computation key |
| Snapshot-dependent computation/access | Provider guarantees a fixed dataset revision and repeatable reads | Reuse within that revision; old revisions or witnesses retained for maintenance |
| Live, unversioned computation | No reproducible source revision available | Record an observation; do not assert snapshot-pure semantics |

Computation keys contain operation semantic version, implementation revision,
exact typed arguments, metric/CRS/units/options, and applicable dataset/profile
revision and access scope. Use symmetry to reorder arguments only if the
operation declares it: directed route computations generally require ordered
endpoints. Distance calculation over two immutable geometries need not depend
on the whole ontology revision, while a query selecting their IDs does.

A returned timestamp or version label is not necessarily a snapshot guarantee.
The adapter must establish what can be pinned and reproduced. Per-query
memoization stabilizes repeated identical calls, but cannot make different
inputs observe one external state. Retry idempotency likewise does not imply
repeatable values. If strict snapshot semantics are requested and the provider
cannot meet them, reject that execution mode.

For live traffic estimates, record source, operation, exact inputs/options,
returned value/status, observation ID/time, effective/departure time where
available, and provider revision if known. Rules consume these finite observation
records. A newer observation produces explicit additions/retractions; replay
uses the recorded result. Observation times alone must not be used to claim a
provider-supported validity period. A freshness TTL can select recent
observations, but cannot prove that a route estimate is still current.

For incremental reasoning, provider-only changes need their own input deltas.
They are invisible to the current local predicate scheduler otherwise. Maintain
versioned external witness relations, or retain old/new provider snapshots so
deletion can recover old proofs. Cache eviction must not erase proof history
still required by maintenance or replay.

Discover changes through a declared notification/change-feed contract, or
explicitly check revisions and rerun every dependent maintained view on
invalidation. Complete change delivery must include newly qualifying rows that
were absent from old witnesses. Keeping snapshots or previous results alone
cannot discover those additions. If the provider has no reliable change
contract, the subscription must declare refresh/observation semantics rather
than promise continuously current answers.

## Failures and fallback

Distinguish a valid `false` filter, a defined domain result such as `no_route`,
invalid input, unavailable service, and incomplete enumeration. A complete
`no_route` may be cached for its declared revision/domain; it is not evidence
that no real-world route or traffic sign exists. Transport errors and missing
responses must not become successful empty answers or infinity-valued distances.

Default to explicit query failure/incompleteness when required rows are missing.
An optional partial-result API must mark unresolved work and completeness;
partial pages do not enter the complete-answer cache. Bound retries to the same
consistency context and deadline, and retry only where the contract permits.
Use cancellation, concurrency caps, and backoff to keep a slow provider from
blocking all live event processing.

Integration needs an explicit transaction/failure boundary in the engine.
Currently `Engine.materialize` sets `complete=True` before `_run`; simply allowing
a new provider exception to escape could leave partial state with that flag.
Stage results until a successful commit, or ensure every failure marks the
operation incomplete and suppresses complete-answer publication. This is a
required extension point, not a claim that the current engine executes remote
calls. See [engine.py](../src/dlp_reasoner/engine.py).

Fallback is allowed only between equivalent semantic contracts, including
precision/quality and revisions. Replacing a road-distance failure with
straight-line distance changes the question. Estimated or stale results require
an explicitly selected result policy and corresponding provenance.

Configure providers and credential references in the host application; rules
select registered operations, not arbitrary network destinations. Keep query
logs and cache metadata free of credentials. The initial interface is for reads
and computation; an action that writes to an external system needs a separate
effectful API outside fixed-point rule evaluation.

## First implementation milestone

Move the external boundary into the first temporal/geospatial slice, alongside
local implementations. Start with a fake deterministic provider and a loopback
HTTP adapter for point distance; this makes batching, correlation, deadlines,
and version validation testable without a particular vendor. Then connect the
chosen real GIS/distance system through that interface. Its concrete endpoint
and contract can be supplied independently of rule syntax.

Acceptance must include reordered replies, duplicate argument fan-out, missing
and duplicate reply IDs, mixed per-row outcomes, wrong units/revisions,
cancellation, page exhaustion, network failure, no local mutations during a
provider-only change, cache invalidation, and replay after the service changes.
Include newly qualifying remote rows and cancellation of one consumer of a
shared request while another consumer remains active.
Compare local and remote implementations on equal contracts; measure remote
requests, batch sizes, cache hits, transmitted bytes, and p95/p99 latency.

Keep this distinct from a full federated query language or distributed stream
runtime. RDFox's externally backed tuple tables provide a relevant precedent
for exposing external relations to a reasoner, while the contract here also
supports bound computation services.
[RDFox tuple tables](https://docs.oxfordsemantic.tech/tuple-tables.html)
