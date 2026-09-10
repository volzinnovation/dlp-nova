# Temporal and spatial engine implementation

The [extension specification](ENGINE_EXTENSION_SPEC.md) now has executable
implementations and acceptance tests. The Appendix A ontology language remains
compatible. New rules use the separately versioned `.dlq` language; historical
`.rules.proposed` files remain design records.

## Run the worked examples

```sh
uv sync --extra dev --extra osm --locked
uv run python examples/bach_temporal/run_queries.py --backend both
uv run python examples/traffic_signs/run_queries.py --backend both
# Optional GEOS C library installed:
uv run python examples/temporal_geo/run_queries.py --backend both
```

These commands execute parsed rules, built-ins, scoped `MIN`, indexed scans and
filters. The Bach answers are Johann Sebastian **23** and Maria Barbara **24**
for their earliest accepted recorded child; unqualified complete-family ages
remain absent. The traffic example executes all four radius cases and six
WGS84 distance cases from the fixture. Directed-road rule execution, unknown
coverage, unreachable routes and cache invalidation have separate acceptance tests.
The event example executes validity/radius rules and geofence entries, verifies a
late-event retraction/addition, restores a checkpoint and expires rows while idle.
Its separate `history.dlq` rules execute both valid-time and recorded-time probes,
including a historical speed correction, with a fully native local execution path.

The original `reference_checks.py` and traffic `check.py` remain independent
reference calculations. Their historical descriptions do not claim to execute
the new rule language.

## Public execution boundary

```python
from pathlib import Path
from dlp_reasoner import Reasoner
from dlp_reasoner.query_runtime import QueryRuntime, QueryScope
from dlp_reasoner.scoped_views import BirthDateView

r = Reasoner.from_file("examples/bach_temporal/bach-temporal.dlp", profile="L0")
bach = "http://www.jsbach.org/bach#"
bt = "https://example.org/bach-temporal#"
scope = QueryScope("urn:dataset:bach", "1")
selection = BirthDateView(
    r, child_property=bach + "hasChild", birth_property=bt + "birthDate",
    accepted_property=bt + "acceptedBirthDate",
    certificate_property=bt + "validatedCompleteChildDates",
).prepare(scope)

with QueryRuntime(Path("examples/bach_temporal/queries.dlq").read_text(),
                  reasoner=r, backend="native") as queries:
    result = queries.evaluate(selection.relations, scope=scope,
                              diagnostics=selection.diagnostics,
                              metadata=selection.metadata)
    print(result.rows("urn:dlp:query:fatherAtAgeKnown"))
    print(queries.explain())
```

`QueryRuntime` consumes a completed ontology and finite named input relations.
Named classes are also exposed through the read-only `rdf:type(person,class)`
relation, allowing a traffic query to bind its desired inferred category. All
local facts and operator inputs use canonical identities from the reasoner.
`Bind` checks an already bound output for agreement; it never overwrites it.
`MIN` orders decoded values after the positive source stratum reaches a fixed
point. The minimum joins back to retain every tied child.
Equal decoded minima choose a deterministic RDF identity representative;
`BirthDateView` canonicalizes accepted dates, so its child join-back preserves
twins. Arbitrary distinct numeric lexical forms still need explicit numeric value
comparison when joining otherwise identity-distinct RDF terms.

Each successful result contains its scope/revision, immutable relations and
additions/retractions from the previous complete result. A failed candidate
leaves `last_complete` available under its original revision and sets
`runtime.complete=False`. Callers must not present that older snapshot as the
failed query's current result. Cancellation, deadlines, provider failures and
source changes all prevent publication, including on a cache hit.

The initial update policy rebuilds derived views against the new snapshot. It
correctly handles nonmonotonic date validation, earlier-child insertion, deletion,
twins, corrected parent dates and equality merges/splits. It does not yet maintain
an ordered per-parent support tree to limit work to individual changed groups.
`BirthDateView` reuses its validated records across queries on the same ontology
revision; an ontology update invalidates that selection before certification.

Completeness certificates are explicit `CompletenessCertificate` values from
configured trusted issuers. They bind the dataset scope/revision, selection
policy and typed child/date/identity evidence digest. They are not inferred from
ordinary RDF assertions or absence of missing dates. The historical Bach dataset
has none. Tests use separately identified synthetic complete families.

## Domains and external computation

`DomainRegistry` declares input/output types, binding modes, operation versions
and determinism. It provides checked signed-64-bit integers, normalized exact
decimals with coefficient/scale bounds, finite binary64 conversion, Gregorian
dates, explicit-offset microsecond instants, time-of-day, fixed durations,
half-open intervals, WGS84 points and selected unit-bearing quantities.

Numeric operations never silently promote integer/decimal inputs to float. The
traffic rules explicitly use `num:toFloat` and `num:floatLessThanOrEqual` when
comparing the floating-point geodesic output with a radius. Completed years use
calendar anniversaries with an explicit March-1 leap-day policy. No host-local
timezone, fixed days-per-year approximation or implicit Julian conversion is used.

Native operations use the packaged Howard Hinnant `date` header and pinned
GeographicLib-C geodesic source. Full PROJ is not needed for WGS84 point distance.
Both backends use that same native geodesic implementation. Python reference
arithmetic/calendar operations run in Python, but a Python geodesic query still
requires a compatible precompiled domain library or the desktop C/C++ build tools.
The optional GEOS provider retains parsed/prepared projected geometries through
the reentrant GEOS C API. It distinguishes contains/covers boundary behavior,
validates two dimensions and matching declared projected CRS units, and converts
coordinate distances to metres. Empty/invalid geometries fail explicitly.
Arbitrary geodesic polygon topology, named-timezone resolution, rich calendar
arithmetic and general unit algebra are outside the advertised initial capabilities.

See [provider and window APIs](PROVIDERS_AND_WINDOWS.md) for correlated batching,
strict bounded HTTP/JSON transport, finite scans, status handling, revision-aware
memoization and checkpoint/replay. `NO_ROUTE`, `OUT_OF_REGION`, invalid arguments
and operational failure remain distinct. `StatusProvider` allows rules to keep a
road outcome observable while deriving a distance only for successful outcomes.
`DirectedRoadProvider` computes shortest supplied edge lengths over a finite
directed regional graph. It does not replace a map matcher or a turn/lane-aware
Valhalla/OSRM adapter.
`OSRMRouteProvider` additionally implements bounded real HTTP route requests with
explicit revision headers, coverage, profile and snapping policy. Its operation
is named `osrmFastestRouteLength`; the length of OSRM's selected fastest route is
not the shortest-distance metric of the regional graph provider. Protocol tests
use a controlled local HTTP endpoint; a live OSRM deployment remains host supplied.

## OSM and spatial data

[OSM ingestion](OSM_SPATIAL_RUNTIME.md) supports bounded current snapshots,
streaming XML/change documents and an optional concrete PyOsmium PBF reader.
It preserves typed IDs, raw tags, ordered/repeated memberships and roles, and
publishes source records, RDF projections, way geometries and a point index
atomically. Missing references and skipped element versions are explicit errors.
Node/way/relation changes update reverse dependencies and projections. A host
can use `map_runtime.MapRuntime` to publish the corresponding completed ontology
alongside the map revision. It builds the candidate closure before publishing the
pair, rejects incomplete/inconsistent candidates and preserves the last valid
publication on failure. Old snapshots remain coherent until their owner closes
them; a caller-mutated ontology invalidates its publication.

Point indexes retain three Earth-centered coordinate columns in Python or C++.
They select a conservative candidate set, including across the antimeridian and
at poles, then refine with the exact declared ellipsoidal metric. Candidate scans
alone never establish a distance answer. Sign-pair distances are generated only
for requested or spatially selected pairs. Old source-bound indexes refuse use
after their location source changes.

## Query reuse, bounds and measured spatial filtering

Keep the reasoner, query runtime, domain registry and spatial/provider contexts
alive across queries. The query runtime diffs changing inputs against its native
index; unchanged ontology facts stay resident. Successful scalar results are
memoized and repeated arguments within a batch are deduplicated. Native domain
contexts intern immutable values once; later operations pass context-local IDs,
retrieving only new output payloads. These IDs are never a wire/package identity.

`QueryRuntime.cache_info()` reports cache entries/estimated bytes, hits, misses,
bypasses, evictions and native dictionary compactions. Defaults cap whole-query
answers at 16 MiB, operation results at 4 MiB, current distinct terms/predicates at
one million and retained native IDs at two million. Entry limits apply as well;
unknown custom payload sizes bypass caching. Input row limits are enforced while
consuming iterables. Dictionary compaction happens between evaluations, preserving
normal static reuse. Native domain contexts have a separate configurable value
capacity and safe reclamation; `DomainRegistry.native_stats()` exposes transfers
and retained-value counts. Closing an internally owned registry releases it;
callers close registries they share between runtimes.
The full native query interpreter retains source relations but currently reloads
the active typed metadata and copied plan at each uncached evaluation. It reports
that cost as `native_term_metadata_rows`; standalone domain batches have their
own resident value context. Successful native scalar operations survive these
evaluations in a bounded memo, reported under `cache_info()["native_operations"]`.
The ontology input boundary still enumerates the completed facts to construct
each query snapshot, even when the source revision is unchanged. Eliminating that
copy and retaining the prepared plan across parameter changes are further query
optimizations; native storage residency alone does not eliminate this host work.

`benchmarks.extension_queries` compares complete indexed radius answers with an
exhaustive exact calculation over the same preloaded points and same geodesic
kernel. It records construction separately and asserts identical answer sets:

```sh
uv run python -m benchmarks.extension_queries --side 100 --repeats 5 \
  --output /tmp/extension-query-results.json
```

A local macOS arm64 run on 2026-09-10 used 10,000 grid points and a 150 m radius.
Both indexes refined **13** candidates and returned the same **11** answers;
exhaustive evaluation computed **10,000** distances. Median complete answer
times were 79.12 ms exhaustive, 0.253 ms with the Python index and 0.124 ms with
the native index. Index construction took 5.83/19.85 ms respectively, including
the first native index library load. This selective synthetic case demonstrates
the benefit of avoiding unnecessary distance calls; it is not an end-to-end
ontology, routing-service, general workload or mobile performance claim.

## Native runtime, packages and mobile status

`standalone.NativeRuntime` now executes compiled Horn rules entirely in C++:
fixed-point evaluation, equality/congruence, witnesses, constraints, explicit
limits and safe full-rebuild updates. It has a versioned public C ABI. Its Python
adapter supplies term metadata and compiled rules and decodes requested output;
it does not run a Python reasoning callback. Independent C++ tests exercise the
kernel without CPython. Its current indexed full-round algorithm is a correctness
baseline; there is no claim that it outperforms the established semi-naive engine.

`native_query.cpp` executes validated local query plans with relation joins,
filters, binds, grouped minima, explicit EQ/NEQ and stratified fixed points in
C++. Python prepares the plan and RDF boundary metadata; scalar calls and rule
evaluation have no Python callbacks. Its only execution callback checks control
signals. `stats["execution_mode"]` identifies `native`, `hybrid` or `python`, and
`EXPLAIN` reports provider/custom-domain requirements for host orchestration.
Raw Python carriers whose equality aliases distinct types or signed zeros use
the Python index/execution path to preserve their identities. This fallback is
also reported; RDF literals avoid that Python-carrier ambiguity.
Native plan validation rejects unsafe slots, incompatible arities, forbidden
dependency cycles and malformed native plans before exposing a complete result.

`native_windows.NativeWindowStore` owns event records, clocks, revisions,
tombstones, offsets, retention and checkpoints in C++. Its Python adapter mirrors
only retained grouping keys. The native event example uses this store. A separate
binary checkpoint validates checksums, typed context, bounds and retention before
publication; it does not load Python's JSON window format implicitly. See
[native window ownership and recovery](NATIVE_WINDOWS.md).

`packages.py` provides deterministic framed, checksummed UTF-8 packages with
tagged RDF terms, compiled Horn rules, optional query IR, source triples, revisions
and required operation versions. Loaders validate all sections before exposing a
loaded program. No pickle, native pointers or Python hashes are serialized.

```sh
uv run python -m dlp_reasoner.packages compile \
  examples/bach_temporal/bach-temporal.dlp --profile L0 \
  --queries examples/bach_temporal/queries.dlq --data-revision bach-v1 \
  --output /tmp/bach.dlppkg
uv run python -m dlp_reasoner.packages inspect /tmp/bach.dlppkg
```

Loaded desktop packages expose `.engine(backend=...)` and `.native_runtime()` for
the compiled Horn program. A separate native `.dlpn` builder format and C++ loader
preserve typed dictionaries, checked lengths, semantic profiles, Horn/local-query
IR and provenance without a Python or JSON dependency. Query metadata, operation
codes, arities, binding safety and strata are validated before publication.
Use an explicit format; a phone
does not implicitly parse the desktop `.dlppkg` envelope.

```sh
uv run python -m dlp_reasoner.packages compile \
  examples/bach_temporal/bach-temporal.dlp --profile L0 --data-revision bach-v1 \
  --queries examples/bach_temporal/queries.dlq \
  --format native --output /tmp/bach.dlpn
uv run python -m dlp_reasoner.packages run-native /tmp/bach.dlpn
```

`run-native` loads/materializes the Horn snapshot and reports its status. To run
the packaged Bach query with the explicitly selected input view from above:

```python
from rdflib import Literal, URIRef
from dlp_reasoner.packages import load_native

with load_native("/tmp/bach.dlpn") as native:
    with native.prepare_query(
        parameters={"scope": URIRef(scope.name), "revision": Literal(scope.revision)},
        relations=selection.relations,
    ) as query:
        answers = query.run()
        print(answers[URIRef("urn:dlp:query:fatherAtAgeKnown")])
```

The C loader copies the canonical Horn closure and inferred `rdf:type` rows into
the prepared query natively. The host supplies given parameters and selected
relations; it must validate certificates, locations and window context before
supplying them. The prepared object owns immutable inputs; successful repeated
runs reuse its frozen result after checking snapshot, cancellation and deadline.
Different inputs require a new prepared query. A failed run also requires a fresh
prepared query. Updating/closing the originating Horn runtime invalidates its
packaged query plan; load a newly authored snapshot before querying the updated
package. Inconsistent Horn snapshots remain inspectable but cannot prepare a
query. Provider-dependent plans are rejected by this local native package profile.
The actual Bach and bitemporal example files have round-trip execution tests.
The [native package contract](NATIVE_PACKAGE_FORMAT.md) documents wire records,
validation, C ownership and the Python preparation API.

The root CMake build combines the native store, domain, spatial and Horn runtime
ABIs, query/package loader and event windows into a precompiled library.
Swift and Kotlin/JNI bindings and reproducible
mobile build scripts are in `mobile/`. Their exact tested targets and outstanding
toolchain/device gates are documented there. The desktop convenience compilers
are not the mobile deployment mechanism.

Authoring, RDF compilation, the `.dlq` planner, scoped input selection and provider
transport remain host responsibilities. Local rule execution, native window
maintenance and compiled Horn package loading can run without CPython. Mobile
applications still need host source/transport integration, a declared selection
policy, lifecycle handling and device qualification. Passing a local rule or
simulator smoke does not establish every provider-dependent feature on a phone.

## Remaining release work

| Spec task | Implemented evidence | Still required for the full specification |
| --- | --- | --- |
| E01 | Checked domains, operation descriptors, Python/C++ differential fixtures | Broader explicitly named capabilities remain optional; preserve versioned contracts |
| E02 | Versioned parser, typed IR, legal binding order, recursive/aggregate validation, EXPLAIN and native local-plan loading | Provider-plan packaging requires host capability contracts |
| E03 | Actual Bach/traffic/window rule execution and atomic result publication | Broader planner/cost optimizations after measured workloads |
| E04 | Scoped MIN/ties, certificates and correct retractions after all tested corrections | Ordered affected-group incremental maintenance |
| E05 | C++ batches, resident values/relations/spatial data and full local plan dispatch | Provider-dependent plan orchestration through native/mobile host adapters |
| E06 | Transactional XML/PBF/changes, projections/dependencies, matched map/ontology publication and exact indexed radius answers | Incremental regional geometry/tile optimizations |
| E07 | Local/fake/HTTP/OSRM computations and scans, strict status/correlation and revision caches | Deployment-specific routing configuration and async shared-work scheduling |
| E08 | Python/C++ windows, corrections, idle expiration, predecessor state, offsets and checkpoints | Unified application recovery and physical-device suspension qualification |
| E09 | Standalone compiled Horn core, local query interpreter and transactional updates | Complete high-level query facade and mobile provider/source orchestration |
| E10 | Portable desktop package plus strict native Horn/local-query package loader and actual example parity | Unified application checkpoint/package recovery across external sources |
| E11 | Native aggregate, Swift/JNI bindings, iOS device/simulator and Android arm64/x86_64 cross-builds | Physical-device lifecycle/memory-pressure execution, application packaging and full host-integration parity |
| E12 | Bounded directed regional shortest-length graph provider | Version-qualified map matching, vendor road/lane integration and device resource measurements |

These remaining items are kept visible rather than being inferred from a passing
scalar calculation, native build or ontology-only example. Existing thesis
benchmark artifacts have not been regenerated to imply extension support.

## Validation recorded on 2026-09-10

- Full Python suite: **1,500 passed**. Final native package/domain/standalone
  review: **133 distinct checks passed**, including the subsequently added
  empty-predicate arity tampering regression and actual Bach/history packages.
- Ruff and `git diff --check` passed. The wheel builds and includes the C/C++
  sources, public headers, vendored kernels and license notices.
- All three worked drivers passed on both desktop backends. Local Bach/history
  plans execute natively; provider-based traffic/geometry plans explicitly use
  host orchestration. The native event driver uses C++ window state.
- Independent C++ tests exercised Horn/package/query/window ownership and
  recovery with AddressSanitizer and UndefinedBehaviorSanitizer.
- Mobile builds covered iOS arm64 device plus arm64/x86_64 simulator slices
  targeting iOS 15, and Android arm64-v8a/x86_64 targeting API 24. Execution covered
  Swift on an arm64 iOS 26.5 simulator and native/JNI calls on an arm64 Android
  API 36 emulator, including Horn, temporal queries, windows and compiled packages.
  Android ELF alignment was inspected; the emulator used 4 KiB pages.

See [mobile build evidence](MOBILE_BUILD_VALIDATION.md) for retained source and
artifact hashes, logs and exact execution targets, and the
[mobile instructions](../mobile/README.md) for scripts and the remaining
physical-device, 16 KiB application packaging, lifecycle and host-integration gates.
