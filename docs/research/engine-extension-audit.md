# Engine extension audit: typed built-ins, spatial queries, and event streams

Audit date: 2026-09-10. This is a design and source audit, not an implementation or a claim of standards conformance. File references describe the current working tree. Static datasets and live streams are equally important requirements; both appear in each proposed delivery stage.

The subsequent [external provider contract](../EXTERNAL_PROVIDERS.md) makes external computation a first-slice requirement and specifies batched calls, result correlation, provider changes, and failure boundaries. The PostGIS integration stage below is one concrete provider, not a prerequisite for calling an existing distance service.

## Recommendation

Add a typed expression and built-in layer with explicit input/output modes, and keep the current positive Horn reasoner as the semantic core. Treat indexed spatial access and event-window maintenance as versioned relation providers. A traffic-sign radius query should combine the materialized sign-type relation with an indexed spatial candidate lookup and an exact distance test. A live observation stream should update a finite, explicitly defined window and emit additions and retractions against committed snapshots.

This needs more than registering Python callables. The present validator assumes ordinary body atoms supply bindings, the compiled planner assumes every positive atom is stored, and incremental scheduling notices fact predicates rather than clock or external-source changes. A naive built-in registration can therefore produce empty answers, unsafe plans, or stale derivations without raising an error.

## 1. Exact extension points in the repository

| Area | Current behavior and source | Required change or constraint |
| --- | --- | --- |
| Intermediate representation | [model.py:22](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/model.py:22) has `Atom(predicate, args)`; [model.py:28](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/model.py:28) restricts a rule body to atoms. | Introduce an explicit distinction between stored relation atoms, filters, assignments, and table-function calls. Preserve stable structural equality and hashing for rule updates. |
| Syntax boundary | [parser.py:1](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/parser.py:1) parses the thesis's OWL-style concrete syntax into RDF; [parser.py:518](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/parser.py:518) recognizes ontology directives, not general Horn-rule expressions. | Extend a separately versioned rule/query syntax or explicit program API. Do not silently present arbitrary arithmetic rules as an unchanged Appendix A grammar. |
| Literal parsing | [parser.py:238](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/parser.py:238) preserves typed literal lexical forms with `normalize=False`. | Keep lexical identity available while separately validating and decoding typed values. Parsing a literal is not proof that its datatype value is valid. |
| Datatype restriction compilation | [compiler.py:131](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/compiler.py:131) explicitly rejects datatype class/range reasoning while allowing literal facts. | A built-in numeric filter does not automatically implement OWL datatype restrictions. Add these as separate supported capabilities with separate tests. |
| Compiler normalization | [compiler.py:301](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/compiler.py:301) deduplicates body atoms and canonically renames variables; its visitors understand `Var` and `Skolem`. | Expression visitors must participate in renaming, variable discovery, dependency analysis, and rule identity. Deduplication/reordering is valid only for pure, repeatable operators. |
| Rule safety | [engine.py:231](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/engine.py:231) treats non-`EQ`/`NEQ` body atoms as binding every variable; equality then propagates bindings. | Replace this assumption with mode-aware binding closure. A filter binds nothing; an assignment binds only its output after its inputs are available. Unknown built-ins must fail validation. |
| Term visitors | [engine.py:38](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/engine.py:38), [engine.py:46](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/engine.py:46), and [engine.py:543](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/engine.py:543) traverse variables/constants and bind terms. | An arithmetic expression cannot be smuggled in as a hashable opaque constant or as an existential `Skolem`. Add a dedicated expression node and visitor coverage. |
| Specialized plans | [engine.py:292](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/engine.py:292) builds unary intersections and relational plans. [joins.py:122](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/joins.py:122) excludes only `EQ`/`NEQ`. | A new built-in must explicitly disqualify or extend these plans. Otherwise it is interpreted as an empty relation and a valid rule can silently stop deriving results. |
| Generic evaluation | [engine.py:553](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/engine.py:553) chooses the smallest available relation; equality/difference have special eligibility checks. | Generalize eligibility to required-input sets and separate cardinality from evaluation cost. Preserve the generic path as a reference implementation. |
| Semi-naive scheduling | [engine.py:315](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/engine.py:315) records dependencies; [engine.py:804](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/engine.py:804) schedules changed predicate occurrences. | Pure filters do not create delta variants. Versioned external tables and windows need explicit dependency/delta relations. Hidden clock/location reads cannot be maintained correctly here. |
| Resource limits | [engine.py:822](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/engine.py:822) bounds rounds and pending facts; [engine.py:57](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/engine.py:57) measures only Skolem nesting. | Arithmetic can generate infinitely many depth-zero values; large intermediate values and infinite table functions can exhaust resources before a new fact is stored. Add evaluation/value/provider budgets and termination restrictions. |
| Deletion | [engine.py:878](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/engine.py:878) gates DRed; [engine.py:922](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/engine.py:922) evaluates old rules against the old closure, then rederives under new rules. | Built-ins need certified deterministic behavior over old inputs, and providers must retain the old snapshot needed for deletion. The existing eligibility gate does not certify this. |
| Support certificates | [support.py:19](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/support.py:19) is specialized to unary support. | It is not general event provenance or a support counter for arbitrary arithmetic/spatial proofs. Keep it ineligible for unsupported extended rules. |
| Native identity | [native.py:269](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/native.py:269) interns Python terms into opaque IDs. | Never perform arithmetic on IDs. Introduce typed value sidecars and a defined output-interning protocol. |
| Native plan and cursor | [native_store.h:22](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/native_store.h:22) contains only predicate/slot/constant descriptors; [native_store.cpp:213](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/native_store.cpp:213) selects indexed rows. | Extend the ABI by versioned operation descriptors or retain Python execution for unsupported built-ins. Keep bounded `next` batches and explicit ownership. |
| Native lifetime | [native_store.h:4](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/native_store.h:4), [native_store.cpp:481](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/native_store.cpp:481), and [native.py:542](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/native.py:542) invalidate cursors on mutation and retain owned stores. | Geometry trees, prepared geometries, and provider snapshots must follow the same lifetime discipline. Current fail-safe invalidation is not MVCC or concurrent query/update support. |
| Answer caches | [reasoner.py:61](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/reasoner.py:61) guards and caches complete scalar/set answers; [reasoner.py:121](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/reasoner.py:121) tracks graph/engine/profile/options. | Include registry, spatial, event-window, and provider versions and all query parameters. Time passing is currently invisible unless represented as a state change. |
| RDF mutation tracking | [query_cache.py:29](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/query_cache.py:29) tracks owned RDF graph mutations. | It cannot detect movement, expiration, or a remote database commit that does not change this graph. |

## 2. Primary-source design lessons

RDFox distinguishes stored/general tuple atoms, `BIND`, and `FILTER`. Its rule assignments and filters require their input variables to be bound; rule expressions exclude argument-independent functions such as `NOW` and `RAND`. This is a useful design precedent for separating an operational mode from a predicate's mathematical meaning. [RDFox reasoning documentation](https://docs.oxfordsemantic.tech/reasoning.html)

RDFox also gives built-in tuple tables binding restrictions: its `SKOLEM` example rejects an unrestricted enumeration that could require infinitely many answers. A spatial provider should similarly declare which inputs are necessary rather than pretending every column is freely enumerable. [RDFox tuple tables](https://docs.oxfordsemantic.tech/tuple-tables.html)

Soufflé's user-defined functors have declared type signatures and C/C++ implementations; implementations must be deterministic for equal inputs and reentrant. Its arithmetic tutorial separately warns that grounded arithmetic expressions can still cause nontermination. These are separate obligations: safe inputs do not prove a finite fixed point. [Soufflé functors](https://souffle-lang.github.io/functors), [Soufflé arithmetic tutorial](https://souffle-lang.github.io/tutorial)

SPARQL distinguishes expression value operations from RDF term comparison. Assignment errors leave a variable unbound, while a `FILTER` retains solutions with true effective Boolean value. `NOW()` is stable within one query execution. These are useful semantic reference points, but copying SPARQL's unbound-result behavior into materialized Horn-rule heads would need an explicit adaptation. [SPARQL 1.1 expressions and assignment](https://www.w3.org/TR/sparql11-query/)

RIF DTB defines datatype-specific value operations, but leaves some out-of-domain results unspecified; notably, some temporal functions require explicit timezones. It is not a complete operational error policy for this engine. [RIF Datatypes and Built-Ins 1.0](https://www.w3.org/TR/rif-dtb/)

SWRL treats built-ins as relations over data values; its specification even allows wrong-arity applications to be unsatisfiable rather than syntax errors. That permissiveness should not be adopted accidentally: this engine should reject unsupported signatures statically. SWRL is a W3C Member Submission, so implementing selected familiar names is not a claim to implement the complete language. [SWRL submission](https://www.w3.org/submissions/SWRL/)

## 3. Proposed operator contract

The following is an architectural proposal, not currently accepted syntax or an existing API.

An immutable `BuiltinSpec` should identify a namespaced operation and semantic version, supported signatures, argument/result type families, valid binding modes, determinism, whether evaluation depends on a snapshot, finite-output guarantees, cardinality/cost estimation, Python reference implementation, optional native implementation, and error policy. Registry changes must invalidate compiled plans and cached answers.

| Operator kind | Required bound inputs | Output behavior | Example |
| --- | --- | --- | --- |
| Filter | All operands | Zero or one surviving binding; introduces no variables | `numeric_less_equal(distance, radius)` |
| Deterministic assignment | All expression inputs | One result on success; if target is already bound, verify agreement under a specified comparison | `distance := distance_m(sign_geometry, position)` |
| Finite table function | A declared mode's required inputs and provider snapshot | Zero or more bindings with explicit exhaustion/cancellation | `nearby_signs(catalog, position, radius; sign, distance)` |
| Query-context input | Bound once by the caller/execution context | Immutable for this execution | evaluation instant, current position, selected map revision |

Recommended safety analysis:

1. Seed a set of bound variables from finite stored relations and explicit query parameters.
2. Repeatedly activate assignments/table-function modes whose inputs are bound and add their declared outputs.
3. Require every head variable, filter operand, and selected operator mode to be supported by that closure. Diagnose unsatisfied dependencies and assignment cycles.
4. Do not infer that an arithmetic relation is an equation solver. `add(a,b;c)` can bind `c`; solving for arbitrary missing operands is a distinct registered mode, with its own type and multiplicity contract.
5. Reject built-ins in asserted facts and rule heads unless they have an explicitly different, supported meaning. Ordinary relation IRIs and built-in identifiers must not collide silently.

Store deterministic query constants in the execution context. A materialized rule must not call an untracked wall clock, GPS service, random generator, or mutable external lookup.

## 4. Datatypes, identity, and errors

The existing equality subsystem is semantic infrastructure, not a convenient comparison helper. [engine.py:61](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/engine.py:61) deliberately keeps a narrow value-identity whitelist; [engine.py:436](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/engine.py:436) can merge literal representatives during registration. Widening that whitelist can alter joins, aliases, inconsistency detection, and whether deletion requires rematerialization.

Keep at least three concepts distinct:

- RDF term identity: datatype, lexical form, language, and the existing RDFLib term semantics.
- OWL equality/representative identity: the engine's union-find and datatype-identity policy.
- Built-in value comparison: numeric promotion, temporal ordering, geometry predicates, or an explicitly selected tolerance.

An equality of distances must not merge sign individuals; a geometry-equivalence test must not assert `owl:sameAs`; and numeric inequality must not become the existing `NEQ` predicate. `NEQ` represents explicit/justified difference, including differences between individuals, rather than arbitrary Python `!=` or negation-as-failure.

For a first arithmetic profile, define exact integer/decimal operations, explicit conversions, result datatype selection, overflow/precision limits, and division-by-zero behavior. Keep binary floating point a declared separate family; do not use Python's `bool`-is-an-`int` relationship as a datatype rule. Specify handling of NaN, infinities, negative zero, and ill-typed literals before compiling comparisons into C++.

For traffic timestamps, require an explicit timezone at the boundary and normalize a decoded instant to UTC while retaining the original RDF term. Distinguish an instant from a local civil time; distinguish day/time durations from year/month durations. Do not silently use the host timezone or translate a calendar month into a fixed millisecond count. Document supported calendar range, fractional precision, and leap-second handling.

Use a structured result status: successful value(s), ordinary predicate mismatch, invalid argument/data error, and evaluation/provider failure. For the proposed extension profile, reject malformed declared typed observations at ingestion by default; preserve existing opaque RDF literal acceptance outside those new input contracts. Statically invalid calls reject the program. An explicitly selected tolerant mode may turn invalid filter data into no match plus a bounded diagnostic; a failed assignment yields no rule match, never a head with an unbound slot. Infrastructure errors/cancellation/exhaustion make evaluation incomplete or fail the operation. Never turn a database timeout or invalid CRS into an empty, supposedly complete radius answer. Never turn a datatype error into logical inconsistency unless the user wrote an explicit validation constraint.

## 5. Planning and native execution

The optimizer should first identify executable operators, then choose among them. Filters that need an unbound operand are unavailable, not empty. Cheap selective numeric filters should run after their operands become available and before expensive geometry calls. Spatial table functions can sometimes supply a much smaller initial binding relation than enumerating every sign and computing every distance. Cost estimates are hints only; a poor estimate must not remove answers.

Preserve the identity of each stored atom occurrence in semi-naive plans. In a self-join, only the designated occurrence reads the delta. Do not assign artificial delta occurrences to pure filters. Pure constant-only rules can run at an epoch's initialization; external-table rules need their own explicit change notifications.

Three implementation paths are viable:

| Path | Advantages | Costs and safe first use |
| --- | --- | --- |
| Python reference operators around native relations | Smallest semantic change; easiest differential oracle | Per-row callback overhead. Initially exclude extended rules from the current compiled/native plan rather than silently miscompile them. |
| Native typed operators and geometry sidecars | Avoid repeated RDF decoding, geometry parsing, and Python crossings | Requires ABI/type/error versioning and output interning. Add pure filters first, then assignments after the value-creation protocol is specified. |
| Versioned external table providers | Reuse PostGIS or another authoritative spatial store; bounded cursor access | Requires a consistent snapshot, explicit source version, remote errors, changed-row delivery, and cancellation. Avoid one SQL request per candidate row. |

The recommended path is a Python reference contract plus native implementations of hot operators and a provider interface shared by in-process and PostGIS implementations. Do not hardwire all rules to a specific database.

Native detail: keep relation columns as the current `uint64` IDs, and cache decoded typed values/parsed immutable geometries by term ID plus semantic/CRS version. A geometry index should return candidate IDs; the exact metric verifies them. Existing IDs are not numeric values, and a C++ arithmetic result cannot invent an ID that collides with `NativeContext`'s Python dictionary. Initially return typed result batches for Python interning; later introduce one explicitly owned shared interner or a negotiated batch protocol. Canonicalize newly produced terms at the current ingestion boundary so equality-induced reindexing cannot invalidate a still-running cursor mid-call.

Keep `open/next/close`, bounded output batches, cancellation, and snapshot ownership for table functions. A batch boundary must not require materializing the whole join. A native relational block followed by a Python filter can still enumerate a huge cross product before filtering, so push each filter to the earliest valid point and measure candidate rows, not just emitted answers.

## 6. Spatial design alternatives

Define the public radius contract independently of the backend: requested sign type, center geometry or longitude/latitude, radius and unit, CRS/axis order, distance model, inclusive/exclusive boundary, and snapshot. A geographic point and a projected point must not become interchangeable because both are represented by two floats. Specify whether altitude is ignored or use a distinct 3D operation.

GEOS operates in planar Cartesian space and does not supply accurate ellipsoidal metrics. An in-process global longitude/latitude solution therefore needs a geodesic implementation, or an explicitly appropriate projection and transformation implementation alongside GEOS. [GEOS spatial-model FAQ](https://libgeos.org/usage/faq/)

GEOS's C API supplies rectangle-based STRtree access and prepared geometry support. Its spatial index retains references to inserted objects, so geometry ownership must outlive every tree/cursor that references it. Candidate lookup still needs an exact test when rectangle overlap is only a coarse filter. [GEOS C API guide](https://libgeos.org/usage/c_api/)

PostGIS `ST_DWithin` has materially different contracts for `geometry` and `geography`: geometry uses CRS units and compatible SRIDs; geography uses metres and defaults to a spheroid calculation. It includes an index-usable bounding-box check. Prefer its indexed distance predicate over retrieving every row and filtering a computed distance afterward. [PostGIS ST_DWithin](https://postgis.net/docs/ST_DWithin.html)

Changing an SRID label is not a coordinate transformation; the PostGIS documentation distinguishes `ST_SetSRID` from `ST_Transform`. This same distinction belongs in the in-process API. [PostGIS projection guidance](https://postgis.net/documentation/tips/st-set-or-transform/)

GeoSPARQL provides an RDF geometry vocabulary, WKT literals, CRS handling, and spatial functions. Use it as the interchange/conformance reference for supported geometry operations. Do not label a simple radius feature as complete GeoSPARQL support, and do not confuse a distance threshold with a topological `within` relation. [OGC GeoSPARQL 1.1](https://docs.ogc.org/is/22-047r1/22-047r1.html)

| Concern | In-process native provider | PostGIS provider |
| --- | --- | --- |
| Static sign catalog | Build and retain a spatial index once per catalog revision; optionally partition/intersect by materialized sign type. | Query an indexed catalog with parameterized geometry/geography inputs and fetch candidate IDs in batches. |
| Moving query point | Query the unchanged sign index for each new position; do not rebuild it per position. | Issue one bounded parameterized query per position or a batched/lateral query over a position batch. |
| Changing sign locations | Use immutable geometry versions, a suitable mutable index or a static-base/delta/rebuild strategy; verify the selected tree's update guarantees. | Consume changed rows/transaction versions; distinguish a catalog revision from a client position revision. |
| Snapshot semantics | Initially serialize update commits and queries; later add immutable provider snapshots if concurrency is needed. | Pin all calls belonging to one evaluation to a stable database snapshot, and reconcile it with the engine's catalog/type revision. |
| Deployment | Additional geometry/projection dependencies inside the optional native package; Python reference fallback remains useful. | Database service and adapter dependency; avoid making it compulsory for local static files or offline replay. |

For a multi-call PostGIS evaluation, a series of default Read Committed queries can see different committed database states; Repeatable Read gives a stable transaction snapshot. This supports a provider design with an explicit snapshot handle rather than unrelated calls. A database snapshot alone does not synchronize the in-memory type closure: use an application catalog version/checkpoint that both sides agree on. [PostgreSQL transaction isolation](https://www.postgresql.org/docs/current/transaction-iso.html)

## 7. Static data and streams share a snapshot contract

Use one immutable evaluation context containing at least program/ontology revision, static catalog revision, provider snapshot IDs, query parameters, evaluation instant, window specification, watermark/stream commit, datatype/built-in semantic version, and CRS/distance-policy version. Static queries can use an explicit instant or omit temporal predicates; stream queries use the same operators against a finite committed window.

Do not implement streams by calling `now()` from each rule firing. Event time, ingestion time, and processing time answer different questions. A timestamped replay should reproduce the same results without depending on machine speed or today's clock. Advancing evaluation time can expire observations even when no new record arrives; that advance is an explicit state transition.

Watermarks are progress information for event-time processing. Flink documents that downstream progress can be held back by idle inputs, and provides explicit idleness handling; its window lifecycle also distinguishes end-of-window from retained state for allowed lateness. These are useful operational requirements, not features obtained automatically by adding timestamp comparisons to Horn rules. [Flink watermarks](https://nightlies.apache.org/flink/flink-docs-release-2.3/docs/dev/datastream/event-time/generating_watermarks/), [Flink window lifecycle](https://nightlies.apache.org/flink/flink-docs-stable/docs/dev/datastream/operators/windows/)

Specify the stream policy before promising continuous results:

- Stable event identity, source identity, correction/retraction semantics, and deduplication.
- Event-time ordering, tie-breaking for a latest-position view, window interval boundaries, allowed lateness, and idle-source behavior.
- Retention/expiration, backpressure, microbatch commit boundaries, and recovery checkpoints.
- Whether published results are provisional, when late data can correct them, and when a window is final under the declared source assumptions.
- A changelog result contract: inserted answers, retracted answers, and updated distances, each attached to an epoch.

The current `complete` flag means a finite materialization reached a fixed point. It must not be reused to imply that a live stream can never produce more events or that a geographic source is complete. A useful result envelope distinguishes reasoning completeness, source coverage, watermark/window status, and any truncation.

For traffic, separate the static type/catalog closure from dynamic observations. A client position update should normally run a parameterized radius query against static signs; it need not insert a global `Nearby(sign)` fact for every device. If continuous derived facts are required, key them by device/session and evaluation/window identity, or explicitly maintain their replacement/retraction.

## 8. DRed, provenance, and deletion hazards

The existing fact set is set-valued. Two observations that justify the same ground assertion do not create two distinguishable assertions. If either observation expires and the adapter blindly retracts that fact, the surviving observation's support is lost. Keep event-level identity and a support/reference count at the stream-to-fact boundary, or represent observations explicitly and derive the entity fact from them.

Pure deterministic filters over immutable bound terms fit positive derivations well. But a mutable external provider is not such a filter. DRed evaluates old rules while tracing consequences of removed facts. If a geometry row has already been overwritten or deleted externally, re-evaluating the old spatial call against the new source can fail to recover the old proof and miss dependent retractions. Keep the old provider snapshot through overdeletion, or materialize versioned provider witness relations and maintain their deltas as ordinary inputs.

Extend `_can_dred` conservatively. Certify deterministic operators, immutable inputs, provider old/new snapshots, and finite modes; otherwise rebuild the affected materialization or reject unsupported incremental mode. Do not let newly introduced operator types fall through the current gate as if they were ordinary safe atoms. Generated datatype values can also trigger equality merging, so an arithmetic-only rule is not automatically eligible for identity-preserving deletion.

For recursion, simple reference counting of derived facts is insufficient: a cycle may appear to support itself after its last external seed disappears. Preserve DRed/rederivation for general positive recursion. Window expiration, correction, and rule changes must remove unsupported cycles just as ordinary fact deletion does. General provenance may later improve precision and explain results, but the existing unary certificate optimization does not supply it.

External database change delivery also needs a replay policy. PostgreSQL documents that logical decoding can resend changes after a crash; consumers must tolerate duplicates. Stable transaction/event identity is therefore part of correctness, not only an optimization. [PostgreSQL logical decoding concepts](https://www.postgresql.org/docs/current/logicaldecoding-explanation.html)

## 9. Cache semantics

Keep distinct caches with explicit dependencies:

| Cache | Reuse criterion |
| --- | --- |
| Parsed/typed literal or geometry | Same immutable term, datatype policy, CRS/transform implementation version |
| Compiled expression/plan | Same rule/query structure, registry semantic version, binding modes, backend capability |
| Static schema closure | Same relevant rules and semantic profile |
| Spatial candidate index | Same catalog/geometry snapshot and indexing configuration |
| Complete query answer | Same full evaluation context, exact position/radius/type parameters, and completion status |
| Stream/window derivation | Same committed window state and policy; expire/retract on state transitions |

A cache key for `nearby_signs(type, position, radius)` must include the actual position value or immutable position-event identity. A changing ambient GPS reading is not covered by an unchanged ontology revision. Likewise, a result using a temporal predicate must include the evaluation instant/window epoch or have an exact expiry rule. A TTL alone is not a correctness guarantee.

Do not round positions or radii solely to improve exact-answer hit rates: two points in the same rounded cell can lie on opposite sides of a threshold. Approximate reuse requires an explicit approximate-result API and conservative error bounds. Provider failures, incomplete native batches, provisional stream results, and results with unknown external revision must not enter the existing complete-answer cache as ordinary complete results.

Cache snapshot handles and geometry objects only with bounded lifetime/size and clear ownership. A query must either pin its epoch or fail/retry on mutation; mixing old native relation rows with newly decoded geometry coordinates is not a valid snapshot.

## 10. Traffic examples and counterexamples

The notation below is proposed explanatory pseudocode, not implemented thesis syntax.

```text
RelevantSign(sign) :- TrafficSign(sign), HasSignType(sign, requested_type).

NearbySign(sign, distance) :-
    RelevantSign(sign), SignGeometry(sign, geometry),
    BIND distance_m(geometry, query_position, distance_model) AS distance,
    FILTER numeric_less_equal(distance, radius_m).
```

An indexed table operator may implement the last three operations together while returning exactly the same answers as the reference rule. For streams, include `PositionEvent(event, device, instant, geometry)` and an explicitly maintained `ActivePositionEvent(window, event)` or `LatestPosition(device, event)` view. Historical observations and current-position state are different relations.

Required counterexamples for the design/test suite:

1. **Unbound filter:** `Allowed(x) :- FILTER(x < 5)` must fail safety validation; it must not enumerate all integers or be mistaken for an empty stored relation.
2. **Assignment dependency cycle:** `p(x) :- BIND(y+1 AS x), BIND(x-1 AS y)` has no initial binding and must be rejected.
3. **Unbounded generation:** `N(0)` and `N(y) :- N(x), BIND(x+1 AS y)` are range-safe operationally but have no finite fixed point over unbounded integers. `max_depth` does not help.
4. **Wrong CRS/units:** longitude/latitude degrees passed to a planar metre threshold must reject or transform explicitly; merely relabeling the CRS does not fix it.
5. **Boundary and date line:** signs exactly at the radius, positions near the antimeridian/poles, and different axis orders must agree with the chosen reference distance model.
6. **Ambient movement:** two consecutive requests with an unchanged ontology but different device positions must not reuse one cached radius answer.
7. **No-arrival expiration:** a detection leaves a ten-second active window when time advances, even if no new event arrives.
8. **Duplicate support:** two active sensor events support the same sign observation; expiring one must not retract the other's consequence.
9. **Late correction:** an accepted late position event changes a previously emitted nearby-sign answer; emit the corresponding correction/retraction under the declared policy.
10. **Old external proof:** a sign moves out of range while a dependent alert exists; deletion must use its old geometry/version to retract that alert.
11. **Malformed measurement:** an invalid numeric literal, missing timezone, negative radius, or invalid geometry follows a documented diagnostic/error path, not a successful empty answer from a failed provider.
12. **Unknown coverage:** zero nearby signs in an incomplete catalog or unfinished event window is not proof that no real sign exists.
13. **Recursive support:** after removing the last observation seed, mutually recursive derived alerts disappear rather than supporting each other forever.
14. **Numeric/identity distinction:** numerically equal literals with different allowed representations compare according to the chosen value policy without an accidental merge of unrelated RDF resources.

For radius semantics, specify `distance <= radius` or `distance < radius` explicitly. A hidden epsilon can change the requested relation; expose accuracy/model choices and use a tested reference implementation for threshold cases.

## 11. Delivery stages and evidence

The order below keeps static and live use cases together rather than postponing all stream semantics until the end.

1. **Semantic vertical slice:** add the operator IR/registry, safe-mode validation, Python reference arithmetic/temporal/point-distance operators, explicit query context, and a stream adapter for finite event windows with deduplication and expiration. Demonstrate one static radius query and one replayable live position/window scenario with identical distance semantics. Keep existing thesis profiles and tests unchanged.
2. **Indexed execution vertical slice:** add an in-process spatial candidate index, native batches for supported filters, typed/geometry sidecars, microbatch snapshot commits, and bounded expiration indexes. Compare static queries and stream corrections against exhaustive/reference recomputation. Measure tail latency and candidate counts as well as throughput.
3. **Provider and maintenance vertical slice:** add a PostGIS provider with snapshot/version mapping and change delivery, certify the supported DRed/built-in combinations, and publish result changelogs with explicit provisional/final metadata. Keep an in-process deployment path. Evaluate whether native assignments or richer geometry operations are the next measured bottleneck.

Initial recursion policy should reject value-generating built-ins in recursive strongly connected components unless a supported finite-domain/range argument is available. Pure filters over already materialized terms can be allowed under the ordinary finite positive rules. A later optional bounded-recursion mode may stop with explicit incompleteness; it must not advertise guaranteed termination merely because limits exist.

In addition to existing `max_rounds`, `max_facts`, and `max_depth`, define candidate/evaluation budgets, maximum generated value size/precision, provider rows/time, and cancellation. Bounds must produce explicit incomplete/error status rather than silent truncation. A function that yields only duplicate answers can otherwise run forever without increasing the fact count.

Acceptance evidence should include backend-differential tests for valid and invalid datatypes, operator reordering and bound-output checks, native cursor mutation/early-close tests, exact spatial results against a selected reference model, static snapshots versus stream replay, duplicate and late-event corrections, expiry with idle inputs, removal of recursive unsupported facts, and cache invalidation for every context component. Report static cold/warm query latency and memory, stream p50/p95/p99 update-to-answer latency, sustained event throughput, bounded state size, correction latency, and behavior under provider failure. Do not infer a whole-engine speedup from a fast distance kernel alone.
