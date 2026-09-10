# DLP Nova: geospatial and temporal extensions

This guide documents the implemented extension language and APIs. Start with the
[DLP Nova user guide](DLP_NOVA_USER_GUIDE.md) for installation and the base DLP
profiles. The distribution, import and command names remain `dlp-reasoner`,
`dlp_reasoner` and `dlp`; DLP Nova is the reasoner's user-facing name.

The extension rules are **version 1 `.dlq` programs**. They query a completed DLP
ontology and explicitly supplied finite relations. Write ontology axioms in
`.dlp` and extension rules in `.dlq`; the Appendix A ontology parser does not
interpret `bind`, `filter` or `scan` inside an `Ontology(...)` declaration.

## 1. Run the tutorial

From an installed checkout:

```sh
uv run python examples/dlp_nova/extension-demo.py --backend both
# Also run the optional projected-geometry examples, when GEOS is installed:
uv run python examples/dlp_nova/extension-demo.py --backend both --geos
```

The [tutorial program](../examples/dlp_nova/extension-demo.py) executes the
[core rules](../examples/dlp_nova/extension-core.dlq), checks their answers, and
prints a compact JSON report. It demonstrates:

- Calendar age 20 on 28 February 2021 and 21 on 1 March 2021 for a person born
  on 29 February 2000.
- Date addition across leap day and an exact elapsed time of 1.25 seconds.
- Two WGS84 sign distances, approximately 11.132 m and 111.319 m, and a 50 m
  search restricted to each sign's validity interval.
- An inclusive start and exclusive end of validity, including an answer
  retraction when the query time reaches the end.
- A finite spatial candidate scan followed by the exact distance test.
- Directed road distance, an unreachable reverse direction, and unknown coverage.
- A late event that changes the observed geofence entry, checkpoint recovery
  and expiry while no new events arrive.
- With `--geos`, a boundary point covered by a polygon but not contained in its
  interior, and a projected distance of 50 m.

WGS84 distance uses the bundled native geodesic kernel even with
`--backend python`. It requires a compatible precompiled domain library or local
C/C++ build tools. The native build uses C++17. The GEOS C library is a separate
optional dependency; Python packages such as Shapely are not required by this
provider. Existing project environments may run the same commands with
`.venv/bin/python` in place of `uv run python`.

## 2. Which capabilities are built in?

| Capability | How to enable it | Execution boundary |
| --- | --- | --- |
| Dates, instants, time of day, fixed durations, intervals and calendar ages | Available through `DomainRegistry` and `QueryRuntime` | Python reference or native scalar/query execution |
| WGS84 points, geodesic point distance and radius tests | Built-in `sp:` operations; geodesic library capability must be available | Same packaged GeographicLib-C kernel from either backend |
| Exact arithmetic and selected unit-bearing quantities | Built-in `num:` operations | Python reference or native |
| Indexed WGS84 candidate enumeration | Construct `PointIndex`, register it in `ProviderRegistry` | Python or native resident index; provider scan uses host orchestration |
| Projected geometry distance and topology | Install GEOS, construct and register `GeometryProvider` | Python-owned adapter calling the GEOS C API |
| Shortest distance in a supplied directed road graph | Construct and register `DirectedRoadProvider` | Host provider over a finite resident graph |
| Length of a route selected by OSRM | Configure and register `OSRMRouteProvider` and a compatible host-supplied service | Bounded HTTP provider |
| Event-time windows and predecessors | Construct `WindowStore` or `NativeWindowStore`; explicitly deliver events and advance time | Separate Python or C++ state API; expose its records to query rules |
| OSM snapshots and changes | Use the OSM ingestion/map APIs; PBF needs the optional `osm` extra | Supplies versioned source records, ontology projections and spatial indexes |

Installing DLP Nova does not create a routing service, load a map or register an
application-specific provider. A provider operation becomes available only after
registration. The historical `*.rules.proposed` files and library comparison
documents include design candidates; they are not the executable capability
catalog. Valhalla, Lanelet2, PROJ coordinate transformations, ICU calendars and
IANA timezone resolution are not built-in operations in this release.

The default namespaces used throughout this guide are:

```text
prefix time:   <urn:dlp:temporal:>
prefix policy: <urn:dlp:calendar-policy:>
prefix sp:     <urn:dlp:spatial:>
prefix num:    <urn:dlp:numeric:>
prefix unit:   <urn:dlp:unit:>
```

Prefixes are arbitrary abbreviations; these full operation IRIs determine
behavior. Prefer the current `urn:dlp:` IRIs in new programs.

## 3. Calling an extension from a rule

```text
version 1
prefix ex: <urn:example:age:>
prefix time: <urn:dlp:temporal:>
prefix policy: <urn:dlp:calendar-policy:>

ex:age(?person, ?years) :-
    ex:birth(?person, ?born), ex:asOf(?at),
    bind time:completedYears(?born, ?at, policy:march1) as ?years.
```

Execute a query program using `QueryRuntime`, not `dlp validate`:

```python
from pathlib import Path
from rdflib import Literal, Namespace, XSD
from dlp_reasoner.query_runtime import QueryRuntime, QueryScope

EX = Namespace("urn:example:age:")
inputs = {
    EX.birth: {(EX.alex, Literal("2000-02-29", datatype=XSD.date))},
    EX.asOf: {(Literal("2021-03-01", datatype=XSD.date),)},
}
# Save the rule program above as age.dlq first.
with QueryRuntime(Path("age.dlq").read_text(), backend="python") as runtime:
    result = runtime.evaluate(inputs, scope=QueryScope("urn:example:people", "1"))
    assert result.rows(EX.age) == {(EX.alex, Literal(21))}
```

Pass `reasoner=reasoner` to the constructor to include the completed ontology's
facts. Named class membership is available both as a unary class relation and
through the read-only `rdf:type(?individual, ?class)` view. Input relations use
IRI keys and immutable ground tuples; they need not have been stored as RDF
triples. A four-column observation is an ordinary finite relation.

| Rule form | Input/output mode |
| --- | --- |
| `bind time:elapsedSeconds(?start, ?end) as ?seconds` | Every argument is bound; produces one result or checks agreement with an already bound output. |
| `filter time:before(?first, ?second)` | Every argument is bound; keeps the binding only if the result is Boolean true. |
| `scan sp:pointCandidates(?center, ?radius, ?pointRevision) as ?id` | Every input is bound; enumerates a finite provider relation whose outputs bind `?id`. |

The planner may reorder body clauses to satisfy binding requirements. No scalar
operation solves backwards for an unbound input. `bind` never overwrites a
previous variable binding. The default scope parameters `?scope` and `?revision`
are seeded by `QueryRuntime`; use names such as `?pointRevision` for independent
provider revisions.

Operations are not RDF properties that acquire meaning merely by appearing in a
stored triple. A date literal remains an RDF term until an explicit domain
operation decodes it. For instance, two offset-bearing literals may denote the
same instant while remaining different RDF terms. Use `time:equal` when value
equality is intended; ordinary relation joins use term identity after ontology
equality normalization. A bound `bind` output additionally accepts equal decoded
values in supported comparable domains, and preserves the original binding.

Pure positive recursive rules are supported. Cycles involving a value-producing
`bind`, a provider scan or `MIN` are rejected. This prevents an unbounded chain
of successively generated dates or coordinates. See the
[query language reference](QUERY_LANGUAGE.md) for parameters, recursion,
aggregation, literal syntax and planning diagnostics.

## 4. Temporal values and their lexical syntax

| Value | Example in a `.dlq` program | Supported meaning |
| --- | --- | --- |
| Date | `"2024-02-29"^^xsd:date` | Proleptic Gregorian calendar date, years 0001–9999; no timezone suffix. |
| Instant | `"2026-09-10T10:00:00+02:00"^^xsd:dateTimeStamp` | A date and clock time with `Z` or an explicit numeric offset, normalized to UTC microseconds. `xsd:dateTime` is also accepted with the same offset requirement. |
| Time of day | `"08:30:00.125"^^xsd:time` | A timezone-free clock value in `[00:00,24:00)`, without a date. |
| Fixed duration | `"P1DT2H"^^xsd:dayTimeDuration` | A signed number of microseconds: here exactly 26 hours. `xsd:duration` accepts the same fixed day/time subset. |
| Interval | `bind time:interval(?start, ?end) as ?span` | A structured interval with two date endpoints or two instant endpoints and strictly positive length. |

Dates, instants, clock times and durations are different domains. Comparing a
date directly with an instant is a type error. A clock time cannot establish
whether an event preceded another event on a different day. Attach the date and
resolve the offset in your input before comparing actual events.

The temporal precision is one microsecond; more than six fractional digits are
rejected rather than rounded. Lexical instant offsets range from `-14:00` to
`+14:00`. UTC storage uses signed 64-bit microseconds relative to 1970-01-01T00:00Z;
lexical date/instant inputs and serialized outputs remain limited to years
0001–9999. Invalid dates, year zero, `24:00:00`, leap seconds, missing instant
offsets and unsupported lexical forms fail explicitly.

`"2026-09-10T10:00:00+02:00"` and `"2026-09-10T08:00:00Z"` denote equal instants
when given the supported instant datatype. Their `before` and `after` tests are
both false. A timezone-free `"2026-09-10T10:00:00"^^xsd:dateTime` is rejected:
the runtime does not borrow the machine's local timezone.

Months and years are not fixed durations. `P1M` and `P1Y` are unsupported;
`PT1M` is one minute. `P1D` is exactly 86,400 seconds, not a request to advance
to the same wall-clock time on the next civil day in a named timezone. Resolve
DST gaps, overlaps and calendar conversions before creating instants. Historical
Julian dates need an explicit upstream conversion; a historical Gregorian
cutover is not inferred from a location or year.

Python callers can also use immutable `DateValue`, `InstantValue`, `TimeValue`,
`DurationValue` and `Interval` objects from `dlp_reasoner.domains`. Scalar results
are returned as RDF literals where a supported literal representation exists.
Intervals remain structured values, suitable for relation cells and subsequent
operations; their Python representation is not a new `.dlq` literal syntax.

## 5. Temporal operation reference

All operations below use `urn:dlp:temporal:`. Each input is required; each
successful call returns one value. Boolean results can be used with either
`filter` or `bind`.

| Operation | Inputs → result | Exact behavior |
| --- | --- | --- |
| `before(a,b)` | temporal, temporal → Boolean | Strict `a < b`; both operands must have the same temporal domain. |
| `after(a,b)` | temporal, temporal → Boolean | Strict `a > b`, with the same domain requirement. |
| `equal(a,b)` | temporal, temporal → Boolean | Equality of decoded values, including normalized instant offsets. |
| `completedYears(start,end,policy)` | date, date, policy → integer | Completed calendar anniversaries; `end` must not precede `start`. Only `policy:march1` is supported. |
| `interval(start,end)` | endpoint, endpoint → interval | Constructs `[start,end)`; both endpoints must be dates or both instants, with `start < end`. |
| `contains(interval,at)` | interval, endpoint → Boolean | `start <= at < end`, with matching endpoint domains. |
| `intersects(a,b)` | interval, interval → Boolean | The intervals share at least one point under the half-open convention. |
| `meets(a,b)` | interval, interval → Boolean | Directional adjacency: `a.end == b.start`. |
| `add(value,duration)` | temporal, fixed duration → temporal | Adds the exact duration and preserves the left input's domain, subject to bounds. |
| `elapsedSeconds(start,end)` | instant, instant → exact decimal | `(end − start)` in seconds; a reverse ordering can produce a negative result. |

For these signatures, `temporal` means date, instant, time of day or fixed
duration; `endpoint` means date or instant. The comparison operations do not
accept whole intervals.

The `march1` anniversary policy counts a leap-day anniversary on 1 March in
non-leap years, and on 29 February in leap years. Thus a 2000-02-29 birth yields
20 completed years at 2021-02-28, 21 at 2021-03-01 and 24 at 2024-02-29.
This operation also works for other calendar-age questions; it makes no claim
about the completeness of a person's recorded family history.

Date addition requires a whole number of days. Adding `P1D` to 2024-02-28 gives
2024-02-29; adding `PT1H` to a date fails. Time-of-day addition does not wrap
through midnight: adding one second to 23:59:59 fails because the result is
outside the supported clock domain. Use an instant when crossing midnight.
Instant and duration arithmetic checks signed-64-bit overflow; exact decimal
results also obey the numeric profile's coefficient and scale limits.

For intervals `[08:00,09:00)` and `[09:00,10:00)`, the first `meets` the second,
but they do not `intersect`. The first interval contains 08:00 and excludes
09:00. Reversing `meets` is false. Empty, reversed, mixed-domain and open-ended
interval constructors are unsupported.

## 6. WGS84 point operations

| Operation | Inputs → result | Units and conventions |
| --- | --- | --- |
| `sp:wgs84Point(longitude,latitude)` | numeric coordinate, numeric coordinate → point | Longitude first, latitude second; degrees; EPSG:4326 with the fixed `wgs84-v1` profile. |
| `sp:wgs84Distance(a,b)` | point, point → binary64 | Ellipsoidal surface distance in metres using the bundled GeographicLib-C kernel. |
| `sp:dwithin(a,b,radius)` | point, point, numeric coordinate → Boolean | Inclusive test `distance(a,b) <= radius`; radius is finite, nonnegative metres. |

Coordinates accept checked integer, decimal or finite binary64 values and are
converted to binary64 for the geometry operation. Longitude must be in
`[-180,180]`, latitude in `[-90,90]`; coordinates are not silently clamped or
wrapped. A `Point` holds two coordinates and the supported CRS/profile metadata;
altitude is not part of this distance model. Host construction uses, for example,
`Point(8.7, 48.9)`, with actual Python floats.

```text
version 1
prefix ex: <urn:example:distance:>
prefix sp: <urn:dlp:spatial:>

ex:distance(?id, ?metres) :-
    ex:pair(?id, ?lon1, ?lat1, ?lon2, ?lat2),
    bind sp:wgs84Point(?lon1, ?lat1) as ?a,
    bind sp:wgs84Point(?lon2, ?lat2) as ?b,
    bind sp:wgs84Distance(?a, ?b) as ?metres.
```

For input coordinates `(0,0)` and `(1,0)`, the output is approximately
111,319.490793 m. This is an ellipsoidal distance between two WGS84 points. It
does not describe a driving route, a projected-plane distance, an altitude
difference or arbitrary geodesic polygon topology.

WGS84 radius boundaries are inclusive, including radius zero for coincident
points. Use the returned distance or `sp:dwithin` consistently when checking a
boundary. The result is a finite binary64 approximation to the declared
ellipsoidal metric, not an exact rational distance.

### Indexed searches

For larger point collections, register a `PointIndex` and use
`sp:pointCandidates(center,radius,pointRevision)`. It returns a finite **candidate
superset**, not final radius answers. Follow the scan with a point lookup and
`sp:dwithin`:

```text
version 1
prefix ex: <urn:example:search:>
prefix sp: <urn:dlp:spatial:>

ex:within(?id) :-
    ex:request(?center, ?radius, ?pointRevision),
    scan sp:pointCandidates(?center, ?radius, ?pointRevision) as ?id,
    ex:point(?id, ?point),
    filter sp:dwithin(?center, ?point, ?radius).
```

Construct the index from `{URIRef: Point}` and register it using
`index.register(providers)`, then pass `providers=providers` to `QueryRuntime`.
The requested revision must equal `index.revision`; it is independent of the
query scope revision. The tutorial's `indexed()` function supplies the complete
setup. The convenience API `index.within(center,radius,domains=registry)` performs
both candidate selection and exact refinement itself.

The indexes use Earth-centered coordinates to avoid losing candidates at the
antimeridian or poles. Indexes tied to a reasoner location view reject use after
their source changes. Publish a newly built index and a matching revision after
a location update; merely replaying old positive matches cannot discover newly
nearby objects. Candidate exhaustion, exact refinement and stable revisions are
all needed before publishing a complete spatial answer.

## 7. Combining spatial and temporal conditions

The core tutorial derives a point and distance for each requested sign, then
checks both its radius and validity:

```text
version 1
prefix ex: <urn:example:selection:>
prefix time: <urn:dlp:temporal:>
prefix num: <urn:dlp:numeric:>

ex:nearbyValid(?sign, ?metres) :-
    ex:distance(?sign, ?metres), ex:probe(?radius, ?at),
    ex:validity(?sign, ?start, ?end),
    bind time:interval(?start, ?end) as ?valid,
    filter time:contains(?valid, ?at),
    bind num:toFloat(?radius) as ?radiusFloat,
    filter num:floatLessThanOrEqual(?metres, ?radiusFloat).
```

`?metres` is the binary64 result of the geodesic operation. The explicit
`num:toFloat` is needed because exact integer/decimal comparisons do not
implicitly promote to binary64. When the numeric distance need not appear in
the answer, use `filter sp:dwithin(?a,?b,?radius)` directly instead.

With a 50 m radius and a validity `[08:00,09:00)`, a sign at 11.132 m qualifies at
08:00 and stops qualifying at 09:00. A sign at 111.319 m fails the radius test.
These rules establish proximity during declared validity. Road side, direction,
lane and legal applicability require their own supplied relations and rules;
proximity alone cannot establish them.

### Valid time and recorded time

For historical corrections, model two independent intervals: when a record is
valid in the world and when that record is present in the recorded history. Use
two probes and two `time:contains` tests. The executable
[history rules](../examples/temporal_geo/history.dlq) show this pattern with a
corrected speed limit.

An explicitly open recorded interval is represented by a separate input
relation and a start-time comparison. A missing endpoint is not automatically
infinity. DLP Nova has no implicit bitemporal storage or history generation:
the application must retain and select the version records it wants to query.

## 8. Projected geometries with the optional GEOS provider

`GeometryProvider` owns parsed and prepared GEOS objects. Rules reference them
using stable IRIs, not native pointers or WKT literals. Register the provider
before constructing a query runtime that calls its operations.

```python
from rdflib import Namespace
from dlp_reasoner.geometry import GeometryProvider, ProjectedCRS
from dlp_reasoner.providers import ProviderRegistry

EX = Namespace("urn:example:geometry:")
providers = ProviderRegistry()
# A synthetic local projected grid, whose coordinate units are metres.
crs = ProjectedCRS("urn:example:local-metre-grid", metres_per_unit=1.0)
with GeometryProvider(revision="geometry-1") as geos:
    geos.put(EX.origin, "POINT (0 0)", crs=crs)
    geos.put(EX.point, "POINT (30 40)", crs=crs)
    geos.register(providers)
    answer = providers.evaluate("urn:dlp:spatial:planarDistance",
                                [(EX.origin, EX.point)])[0]
    assert float(answer.value) == 50.0
```

The provider registers these `urn:dlp:spatial:` operations:

| Operation | Inputs → result | Meaning |
| --- | --- | --- |
| `planarDistance(a,b)` | geometry IRI, geometry IRI → binary64 | Minimum planar geometry distance, converted to metres. |
| `planarDwithin(a,b,radius)` | geometry IRI, geometry IRI, number → Boolean | Inclusive planar distance test in metres. |
| `contains(a,b)` | geometry IRI, geometry IRI → Boolean | GEOS contains relation; a point solely on a polygon boundary is not contained. |
| `covers(a,b)` | geometry IRI, geometry IRI → Boolean | GEOS covers relation; includes the polygon-boundary point case. |
| `intersects(a,b)` | geometry IRI, geometry IRI → Boolean | The geometries share any point, including boundary contact. |

For polygon `POLYGON ((0 0,10 0,10 10,0 10,0 0))` and point `POINT (0 5)`,
`contains` is false while `covers` and `intersects` are true. Choose the predicate
that matches the application's boundary policy. This point example is not a
replacement for the full GEOS topology definitions for compound geometries.

Both geometries must have identical `ProjectedCRS` declarations, including the
unit conversion. A grid in feet with `metres_per_unit=0.3048` converts a distance
of 100 coordinate units to 30.48 m. The radius remains metres. The CRS
declaration supplies a contract; it does not perform reprojection or validate
arbitrary CRS identifiers against a CRS database. The caller is responsible
for supplying truly projected coordinates with suitable distortion for the
application. Known geographic identifiers such as EPSG:4326 are rejected.

Ingestion rejects invalid WKT, empty geometries, invalid topology and
three-dimensional geometry. Unknown geometry IRIs and mismatched CRS/units also
fail explicitly. Replacing a geometry advances the provider snapshot and
invalidates dependent memoized answers. Keep the provider open for the lifetime
of its queries, then close it to release its GEOS objects.

## 9. Road distance and provider outcomes

`DirectedRoadProvider` exposes
`road:shortestDistance(fromIRI,toIRI,profile)`. Supply a finite graph of directed
edges with nonnegative lengths in metres. The operation minimizes the sum of
those supplied lengths. A reverse route exists only if the graph provides one.
This provider does not infer turn restrictions, traffic, lane permissions or
map matching from the graph.

`OSRMRouteProvider` exposes
`road:osrmFastestRouteLength(fromPoint,toPoint)`: metres along the route selected
by OSRM's fastest-route service. These two operation names intentionally state
different optimization objectives. The OSRM adapter requires an endpoint,
implementation/map revisions, profile, bounded snapping policy and a revision
header supplied by the deployment or proxy. See
[provider configuration](PROVIDERS_AND_WINDOWS.md#direct-osrm-integration) for
its HTTP contract. No public OSRM server is assumed to satisfy that contract.

To retain observable road outcomes in rules, register both the road provider
and `StatusProvider`, then use this pattern:

```text
version 1
prefix ex: <urn:example:road:>
prefix road: <urn:dlp:road:>
prefix provider: <urn:dlp:provider:>

ex:outcome(?from, ?to, ?result) :-
    ex:request(?from, ?to, ?profile),
    bind road:shortestDistance(?from, ?to, ?profile) as ?result.

ex:distance(?from, ?to, ?metres) :-
    ex:outcome(?from, ?to, ?result),
    filter provider:isOK(?result),
    bind provider:value(?result) as ?metres.
```

| Outcome | What it means |
| --- | --- |
| `OK`, including Boolean false | A completed successful computation. False is an ordinary value. |
| `NO_ROUTE` | A completed no-route result inside the declared graph coverage. |
| `OUT_OF_REGION` | Coverage is unavailable for the requested object; it does not prove no route. This outcome is not cached. |
| `DOMAIN_ERROR`, `UNAVAILABLE`, `NO_MATCH` | Invalid domain input, unavailable capability/service or failed matching; query publication fails. |
| `INCOMPLETE`, `CANCELLED`, `DEADLINE`, `PROTOCOL_ERROR`, `SNAPSHOT_CHANGED`, `RESOURCE_LIMIT` | A complete answer could not be established; query publication fails. |

Never substitute zero distance for an unsuccessful route. Inspect
`result.rows(EX.outcome)` to preserve complete non-success outcomes; use
`provider:isOK` and `provider:value` to derive a numeric relation only for
successful calls. A service failure is not converted into an empty route set.

The provider registry pins snapshots, batches correlated calls, deduplicates
arguments and validates returned types and completeness. Finite scans need
complete exhaustion, not just a row/page limit. Hosts must observe revision
changes and reevaluate their views; registering an adapter does not start a
background change feed.

## 10. Event-time windows and geofence entry

Windows are explicit state APIs. The `.dlq` language has no `WINDOW`, watermark
or implicit current-time operator. Applications deliver identified events,
advance the evaluation time, then pass the resulting finite active/predecessor
relations to query rules.

```python
from dlp_reasoner.windows import Event, WindowStore

window = WindowStore(width=10_000_000, allowed_lateness=20_000_000)
window.upsert(Event("outside", 1_000_000, "car", (False,)))
window.upsert(Event("inside", 5_000_000, "car", (True,)))
window.advance(10_000_000, watermark=0)
assert {row[0] for row in window.entry_rows(lambda e: e.values[0])} == {"inside"}

# A late observation changes the observed entry to an earlier event.
window.upsert(Event("late-inside", 3_000_000, "car", (True,)))
assert {row[0] for row in window.entry_rows(lambda e: e.values[0])} == {"late-inside"}

restored = WindowStore.restore(window.checkpoint())
expired = restored.advance(30_000_000)
assert len(expired.removed) == 3 and not restored.rows()
```

Event time, window width, evaluation time, watermark and allowed lateness use
signed-64-bit microseconds. These integer API values are not `xsd:dateTime`
literals. To use a returned event timestamp in `time:before`, pass it into the
query relation as `InstantValue(event_time)` or serialize a supported instant
literal. A plain integer literal remains numeric.

The active window at evaluation time `end` is `[end-width,end)`. The lower
endpoint is included and the upper endpoint excluded. Time and watermark may
only advance; the watermark cannot exceed evaluation time. Omitting the
watermark sets it to `end`. Explicitly advancing time expires rows even while
the input stream is idle. Future events may be buffered within resource limits.

Each active row is `(event_id,event_time,key,*values)`. Distinct IDs preserve
equal-valued observations. An identical event/revision retry is a no-op; changing
an existing event needs a larger revision. A removal also records a revision,
and reinsertion needs a later one. Events or corrections older than
`watermark-allowed_lateness` raise `LateEventError`. Keep this policy separate
from window width: a time window determines visibility, while lateness controls
which deliveries can still change the maintained history.

### Entry requires predecessor evidence

`predecessor(event_id)` retrieves the accepted earlier observation of the same
key, ordered by `(event_time,event_id)`. With predecessor retention enabled,
`rows(include_predecessors=True)` also exposes the latest retained pre-window
observation per key. This supports a false-to-true entry test at a window edge.
An observation inside a fence with no predecessor is not proof that the object
entered it. Missing history does not mean outside.

`entry_rows(pure_predicate)` applies a host-supplied Boolean predicate to those
observations. The tutorial uses explicitly supplied Boolean state. For geometry
derived in rules, the existing [event example](../examples/temporal_geo/run_queries.py)
exposes active rows and predecessor geometry IRIs, then the
[event rules](../examples/temporal_geo/queries.dlq) evaluate the actual geofence.
An explicit successful false predicate on the predecessor establishes outside.
The application observes sampled transitions; it does not infer the exact
physical crossing instant between observations.

### Updates, bounds and recovery

Window mutations return immutable additions/removals for active and retained
predecessor relations. Publish these deltas or reevaluate dependent queries.
Accepted late events can retract a previously observed entry and introduce a
different one. Configure event/byte/key limits, retain the required predecessor
history, and use `forget_key` only when intentionally discarding that key's
history. Deduplication covers retained history, not every event ever seen.

Optional source names and offsets support replay checks. Subsequent gaps or
inconsistent replays fail unless offset gaps were explicitly permitted. Add a
`context` tuple for map/model revisions and pass `expected_context` during
restore when recovery must use the same context. Checkpoint integrity checks
detect corruption; they do not authenticate an untrusted checkpoint.

`NativeWindowStore` offers the corresponding API with C++ resident records and
explicit `close()`/context-manager ownership. Python `WindowStore` checkpoints
are versioned JSON envelopes; native checkpoints use `DLPWIN01` binary frames.
Restore using the matching class: automatic migration between these formats is
not provided. Neither backend guarantees continuous background execution of a
mobile app. See [native windows](NATIVE_WINDOWS.md) and
[application recovery](APPLICATION_RECOVERY.md) for host integration.

## 11. Numeric and quantity helpers

Exact numeric operations accept checked integers and decimals. Integers are
signed 64-bit; normalized decimals have a signed-64-bit coefficient and a scale
of at most 18. Booleans are not numbers in this domain. Unsupported precision,
overflow, division by zero and nonterminating exact decimal quotients fail;
`num:divide(1,8)` yields `0.125`, whereas `num:divide(1,3)` raises `INEXACT`.

| Operations in `urn:dlp:numeric:` | Inputs → result |
| --- | --- |
| `add`, `subtract`, `multiply` | Two exact numbers → exact number; integer/integer preserves integer where valid. |
| `divide` | Two exact numbers → exact decimal. |
| `equal`, `lessThan`, `lessThanOrEqual`, `greaterThan`, `greaterThanOrEqual` | Two exact numbers → Boolean. |
| `toFloat` | Integer, decimal or finite binary64 → finite binary64; conversion can lose decimal precision. |
| `floatLessThanOrEqual` | Two finite binary64 values → Boolean. |
| `quantity(value,unit)` | Exact number and supported unit IRI → quantity. |
| `quantityAdd`, `quantitySubtract` | Two quantities of the same unit → quantity. |
| `quantityEqual`, `quantityLessThanOrEqual` | Two quantities of the same unit → Boolean. |
| `quantityDivide` | Two quantities of the same unit → dimensionless exact decimal. |

The quantity units are `unit:metre`, `unit:second` and `unit:kmh`. A metre quantity
cannot be added to a second quantity. There is no implicit unit conversion,
general unit algebra or quantity multiplication. Geodesic/planar distances are
binary64 metre values, not `Quantity` objects; the exact quantity constructor
does not accept them without an application-chosen conversion policy.

In `.dlq`, `1` is an integer, `1.0` a decimal and `1e0` a double. Do not assume
that the decimal literal `50.0` already satisfies a binary64 argument. `NaN`,
infinity and `xsd:float` binary32 decoding are unsupported in the advertised
binary64 capability.

## 12. Backends, failures and complete answers

Selecting `QueryRuntime(..., backend="native")` allows local plans to execute
in the native query runtime. Inspect `runtime.explain()["execution"]` before
evaluation and `runtime.stats["execution_mode"]` afterward. Provider-dependent
plans report `hybrid`: their relation/index and scalar work may be native, but
the host still controls provider calls/scans. The tutorial reports `native` for
its core temporal/geodesic rules and `hybrid` for its candidate-scan and GEOS
queries under native selection. A host input identity corner case can also
require Python relation indexes.

The separate standalone C++ runtime and native session packages can execute
supported compiled local plans without Python. This does not automatically
package Python-owned GEOS, HTTP or road-provider objects. Mobile native windows
retain their records in C++; a Python `entry_rows` predicate is still a host
callback, not code compiled into C++. See
[native session integration](NATIVE_SESSION.md) for the local package boundary.

The domain library loader accepts `DLP_DOMAIN_LIBRARY` for a precompiled
library. A source build normally includes GeographicLib; setting
`DLP_DOMAIN_GEODESIC=0` explicitly omits that capability, so distance operations
then fail as unavailable. `domain_native.native_capabilities()` reports the
loaded capability. Keep domain registries, indexes and provider contexts alive
for repeated queries, then close owned native resources explicitly.

| Symptom | Likely cause and action |
| --- | --- |
| Unknown operation / `UNAVAILABLE` | Check its full IRI, provider registration and installed capability. A proposed name is not evidence of an implemented operator. |
| `TYPE_ERROR` | Check typed literals, matching temporal domains, explicit binary64 conversion and matching quantity units. |
| `DOMAIN_ERROR` | Check lexical date/time validity, interval ordering, coordinate/radius bounds, known geometry IDs and CRS declarations. |
| `INEXACT` / `OVERFLOW` | Input or result exceeds the exact numeric/temporal profile; choose an explicit upstream precision policy. |
| No match at a boundary | Check `[start,end)` for intervals/windows and inclusive `<= radius` for spatial tests; check `contains` versus `covers`. |
| Unexpected empty relation | Check input predicate IRIs, complete tuples, bindings, reserved `?scope`/`?revision` names and provider revision parameters. |
| `SNAPSHOT_CHANGED` / stale source | Rebuild or repin the dependent view/index and reevaluate against coherent revisions. |
| Query failure after a previous success | `last_complete` retains the older answer; inspect its original scope/revision and `runtime.complete`. |

A successful `QueryResult` is immutable, has a scope/revision, and contains
additions/retractions relative to the previous completed result. A failed
candidate never publishes a new complete answer. The old `last_complete` is
available under its old revision, with `runtime.complete=False`; do not label it
as the answer for the failed current request.

Completeness refers to the declared finite input and pinned computation. It does
not establish real-world completeness, complete family records, exhaustive map
coverage or absence of missing events. For a minimum birth date, say **earliest
known recorded birth** unless the relevant child/date relation has a validated
completeness certificate. The [Bach example](../examples/bach_temporal/README.md)
shows the distinction and preserves all tied children at the minimum.

Implementation details and further worked examples are available in
[the query language reference](QUERY_LANGUAGE.md),
[provider and window APIs](PROVIDERS_AND_WINDOWS.md),
[OSM spatial runtime](OSM_SPATIAL_RUNTIME.md) and
[extension implementation notes](ENGINE_EXTENSION_IMPLEMENTATION.md).
The operation reference above is grounded in
[`domains.py`](../src/dlp_reasoner/domains.py),
[`geometry.py`](../src/dlp_reasoner/geometry.py),
[`spatial.py`](../src/dlp_reasoner/spatial.py) and
[`windows.py`](../src/dlp_reasoner/windows.py).
