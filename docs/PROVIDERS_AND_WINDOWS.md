# Provider calls, finite windows and regional road graphs

`providers.py` and `windows.py` implement the Python boundary for external
computation, finite relation scans and explicit event-time state. The query
runtime consumes these interfaces; the old Appendix A materializer does not
start network calls or read a clock implicitly. Native relation joins remain
separate from transport and event ingestion.

## Registering a provider

```python
from dlp_reasoner.providers import FakeProvider, ProviderRegistry

provider = FakeProvider({"urn:example:double": lambda value: value * 2})
registry = ProviderRegistry(max_entries=256, max_bytes=16 * 1024 * 1024)
registry.register("urn:example:double", provider,
                  input_types=("integer",), result_type="integer")
snapshot = registry.snapshot("urn:example:double")
results = registry.evaluate("urn:example:double", [(3,), (3,), (4,)], snapshot=snapshot)
assert [result.value for result in results] == [6, 6, 8]
```

`register` exposes the input/output types, required bound positions, operation
version, scalar/scan cardinality and exact/candidate-superset coverage through
`get(uri)`. All inputs must be bound in this first adapter contract. A scan can
declare `output_types` for its row columns. Optional `output_unit`, `metric` and
`crs` declarations must match the snapshot's advertised dependencies. Quantity
outputs also have their unit checked. Semantic compatibility remains an explicit
adapter obligation; naming two services `distance` cannot establish equivalence.

An adapter implements:

```text
snapshot() -> Snapshot(provider, implementation, dataset, dependencies)
evaluate_batch(operation, tuple[Request(row_id, arguments)], snapshot, control)
    -> BatchReply(snapshot, tuple[Reply(row_id, ProviderResult(status, value))], complete)
open_scan(operation, arguments, snapshot, control) -> cursor
cursor.next_page(limit, control) -> ScanPage(snapshot, tuple[tuple], complete, continuation)
cursor.close()
```

Snapshot dependencies are unique string key/value pairs, for example profile,
traffic revision, metre units or CRS policy. Every changed dataset/algorithm or
relevant option needs a new revision. A timestamp label alone is not evidence of
repeatable reads. The adapter must guarantee its pinned data, and the registry
rejects changed snapshots during a call. `FakeProvider` is a deterministic test
adapter whose caller explicitly advances `revision` when its supplied data or
functions change.

Batches preserve original input order despite reordered replies and deduplicate
equal normalized typed arguments. RDF lexical forms are preserved on the wire;
declared numeric/date domains normalize cache keys through the strict domain
decoder. Generic `any` arguments retain exact typed identity. No process-local
native term IDs cross this boundary. Missing, duplicate or unknown IDs, wrong
types/units, incomplete batches and revision mismatches fail before new results
or memo entries are published.

`OK` with value `False` is a successful false result. Complete `NO_ROUTE` is a
distinct domain result. `DOMAIN_ERROR`, `UNAVAILABLE`, `INCOMPLETE`, `CANCELLED`,
`DEADLINE`, `PROTOCOL_ERROR`, `SNAPSHOT_CHANGED`, `NO_MATCH` and
`RESOURCE_LIMIT` raise `ProviderError` with an inspectable `status`; they do not
become empty answers. The cache stores successful scalars, complete no-route
results and fully exhausted scans, including complete empty scans. It never
caches a partial enumeration. Limits cover entry count, estimated retained bytes,
input/output work bytes, batch/page sizes, row count and page count. Zero cache
entries disables memoization.

`OUT_OF_REGION` is returned as an explicit, noncached coverage-status result;
it does not establish no-route. `StatusProvider().register(registry)` supplies
`urn:dlp:provider:isOK` and `urn:dlp:provider:value` for deliberate query handling
of status carriers. Successful scalar values (including `False`) pass `isOK`;
extracting the value of a non-OK status raises `DOMAIN_ERROR`. This makes a
query's successful-result-only selection explicit while retaining other status
rows for diagnostics or separate output.

`scan(...)` returns a closeable/context-managed iterator. Rows are provisional
until exhaustion sets `cursor.complete`; early close preserves `complete=False`
and releases the adapter cursor. A nonfinal page needs an advancing continuation
token. A page or row limit never proves exhaustion. Candidate-superset scans
still require the query's exact refinement predicate.

`revision_key()` covers registry configuration and current provider snapshots.
`invalidate(provider)` conservatively invalidates the whole provider-dependent
view; consumers must re-enumerate, including formerly absent objects. Old positive
witnesses alone cannot detect newly qualifying rows. This implementation does
not promise autonomous change-feed delivery: hosts explicitly observe revisions
or invalidate and re-evaluate their maintained queries.

Calls are synchronous and the owning runtime serializes registry access. Work
is not coalesced across independent callers with different ownership/deadlines.
Pass `CancellationToken` and an absolute `time.monotonic()` deadline. Checks
bracket calls and pages; cooperative adapters check `Control` during work. A
noncooperative blocking function cannot be forcibly interrupted, but a result
returned after cancellation/deadline is rejected.

## HTTP loopback and real transport

`HTTPJSONAdapter(endpoint, timeout=5, max_bytes=...)` makes actual bounded HTTP
POST requests to a host-configured endpoint. No server threads or credentials
are created by the production adapter. Its tagged JSON protocol transports
exact integers/decimals, RDF terms, structured domain values, correlated replies
and explicit snapshot/status/page metadata. Malformed tags, nonfinite floats and
wrong primitive types are rejected; arbitrary object or pickle decoding is not
supported. Socket timeout and cancellation checks bound acceptance of results;
cancellation does not claim to preempt an OS socket immediately.

`LoopbackEndpoint(adapter)` dispatches the same protocol for a local server
owned by the host/test. It limits cursor, batch and page counts and closes retained
cursors when shut down. Tests run it behind an actual localhost `HTTPServer`,
close the server and join its thread. A deployed service additionally needs its
own authentication, request limits and cursor leases. The wire protocol is this
project's adapter contract, not an existing vendor API.

## Direct OSRM integration

`osrm.OSRMRouteProvider` implements the OSRM HTTP route protocol through the same
provider registry. It requires an endpoint, explicit implementation/map revision,
profile, bounded snapping radius and optional geographic coverage rectangle.
It returns `urn:dlp:road:osrmFastestRouteLength(point1,point2)` in metres. OSRM's
route service selects a fastest route; this value does not establish the
shortest-distance route. See the [OSRM route API](https://github.com/Project-OSRM/osrm-backend/blob/master/docs/http.md#route-service).

```python
from dlp_reasoner.osrm import OSRMRouteProvider

router = OSRMRouteProvider(
    "http://localhost:5000", implementation="my-osrm-build-2026-09",
    revision="region-2026-09-10", profile="driving", max_snapping_metres=25,
    coverage=(8.0, 48.0, 10.0, 50.0),
)
router.register(registry)
```

The endpoint/proxy must attach `X-DLP-Data-Revision` matching that configured
revision to every response, including errors; `revision_header` can rename it.
This is this project's snapshot contract, **not a standard OSRM header**.
Use immutable versioned deployments or advance the adapter revision when the
host changes map/profile data. Public demonstration servers do not establish
this contract automatically. The adapter performs no download or server startup.

Finite pair requests set an explicit snapping radius and check reported snapping
distances. `NoRoute` is a complete no-route outcome; `NoSegment` raises `NO_MATCH`.
Declared outside coverage yields noncached `OUT_OF_REGION`. Missing/changed
revision headers, invalid distances, excess response sizes or malformed JSON
prevent publication. Controlled local HTTP tests verify real request construction,
both query backends and failure/cache behavior; no live OSRM deployment or routing
dataset was contacted by those tests.
Response bodies are read incrementally with deadline/cancellation checks and a
remaining-time socket timeout, including when a server drips small chunks.
Connection establishment, DNS and initial response headers retain the standard
library's blocking/socket-timeout behavior; this adapter does not promise hard
preemption of those OS operations. Truncated bodies are protocol failures.

## Event-time state and changes

```python
from dlp_reasoner.windows import Event, WindowStore

window = WindowStore(width=10_000_000, allowed_lateness=20_000_000)
window.upsert(Event("sample-1", 1_000_000, "car", (False,)))
window.upsert(Event("sample-2", 5_000_000, "car", (True,)))
change = window.advance(10_000_000)
assert len(change.added) == 2
checkpoint = window.checkpoint()
resumed = WindowStore.restore(checkpoint)
assert resumed.rows() == window.rows()
```

Time, width and lateness use explicit signed-64-bit microseconds. The active
relation is `[evaluation_time-width, evaluation_time)`. `advance(end, watermark=...)`
advances both monotonically, with watermark at most the evaluation time. Omitted
watermark means `end`. Advancing expires rows even when no event arrives. Future
events may be buffered within the same resource limits.

Rows are hashable `(event_id,event_time,key,*values)` tuples. Distinct IDs retain
equal-valued observations. An identical event/revision retry is a no-op; changed
records require a larger event revision. `remove(id, revision=...)` records a
bounded tombstone, and re-insertion needs a later revision. Events/corrections
older than `watermark-allowed_lateness` raise `LateEventError`, including changes
to an already finalized old timestamp. Late accepted corrections can retract a
previous observed entry and introduce a different entry.

`rows(include_predecessors=True)` additionally exposes the latest accepted
pre-window event per key. `predecessor(id)` and `entry_rows(pure_predicate)` retain
false-to-true transition semantics without treating missing predecessors as
outside. Equal times use event-ID order. One retained predecessor per quiet key
is bounded by `max_keys`; `forget_key(key)` explicitly releases history and resets
that key's predecessor knowledge. There is no silently invented outside state.

Every mutation returns immutable `WindowChange(revision,added,removed,
history_added,history_removed)`. The caller publishes these changes or recomputes
its dependent view. No unbounded change log is retained. Event/tombstone count,
estimated bytes, keys and accepted source offsets are bounded; failed capacity
checks leave the previous state unchanged. Deduplication is guaranteed within
retained history, not for all event IDs forever.

Optional `source` and `offset` on `upsert` persist accepted offsets. The first
offset establishes a source's starting position; subsequent gaps or inconsistent
replays raise `ReplayGapError`. `allow_offset_gaps=True` explicitly permits a
filtered source and is recorded in the checkpoint. Checkpoints include the static
`context` version tuple, clocks, event revisions, predecessors, tombstones, offsets
and retention policies. Restore validates a versioned checksummed JSON envelope,
strict value types and host resource caps; use `expected_context` to reject an
incompatible map/ontology revision. Larger-than-default restore limits require
explicit host configuration. No pickle, implicit replay clock or uninterrupted
background execution is assumed.

## Optional directed road graph

`DirectedRoadProvider` executes `urn:dlp:road:shortestDistance(fromIRI,toIRI,profile)`
over a finite, bounded, resident directed graph. Edge weights are supplied finite
nonnegative metres; the operation minimizes their sum, rather than the length of
a fastest-time route. `provider.register(registry)` declares the operation.
Unknown nodes produce `OUT_OF_REGION`; known disconnected nodes yield complete
`NO_ROUTE`; reverse travel requires explicit reverse edges. Replacing a graph is
atomic and requires a different revision, invalidating both positive and negative
route caches. Node/edge/estimated-byte limits are explicit.

This capability is not a Valhalla/OSRM integration, OSM-to-routing conversion,
map matcher, turn-restriction engine, traffic cost model or sign-applicability
proof. It provides a useful real local provider and reproducible regional graph
contract while those richer adapters remain separately qualified work.

```sh
.venv/bin/python -m pytest -q tests/test_providers.py tests/test_windows.py tests/test_query_runtime.py
```
