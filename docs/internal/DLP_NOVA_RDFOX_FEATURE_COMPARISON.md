# DLP Nova and RDFox: internal feature comparison

**Internal working assessment — 10 September 2026.** Keep this document separate
from the DLP Nova paper, its submission archive and public-facing documentation.
It compares feature contracts and integration choices; it contains no timing
results or performance ranking.

**Evidence levels:** Nova statements describe inspected implementation and
repository tests. RDFox statements describe official documentation for the
current 7.6 series; **RDFox was not locally executed**. An unverified capability
is marked as such and must not be interpreted as absence. The current public
download is 7.6b, released on 27 July 2026.
([Download](https://www.oxfordsemantic.tech/download),
[release notes](https://docs.oxfordsemantic.tech/release-notes.html).)

The products overlap in rule-based materialization, incremental changes,
calendar computations and spatial queries. Nova currently exposes a focused
thesis-derived reasoner and an application runtime with explicit typed values,
provider revisions and event-source contracts. RDFox documents a broader RDF
database and rule/query platform with persistence, concurrent transactions,
SPARQL and operational administration. These are differences in scope, not a
ranking of implementations.

## Ontology and rule language

Nova evidence: [language guide](../DLP_NOVA_LANGUAGE_GUIDE.md),
[compiler](../../src/dlp_reasoner/compiler.py),
[query planner](../../src/dlp_reasoner/query_ir.py) and
[parser tests](../../tests/test_dlp_parser.py).

| Capability | DLP Nova: implemented / source-tested | RDFox: official documentation | Practical implication |
| --- | --- | --- | --- |
| Ontology input | Thesis-style `.dlp`; RDF inputs share the same compiler. Explicit L0–L3 selection and rejection outside supported forms. | OWL Functional Syntax and OWL axioms extracted from RDF; translation to rules is best effort. [OWL support](https://docs.oxfordsemantic.tech/reasoning.html#owl-2-support-in-rdfox) | Parsing an ontology and supporting every axiom's semantics are separate checks in both integrations. |
| Profile meaning | Position-sensitive L0–L3: positive core, equality, denials, existential consequents. Not a complete OWL 2 DL/RL conformance checker. | No Nova-compatible L0–L3 selector verified. [OWL support](https://docs.oxfordsemantic.tech/reasoning.html#owl-2-support-in-rdfox) | Do not identify these profile labels with RDFox's accepted OWL subset. |
| Positive recursion | Horn materialization and positive recursive `.dlq` relations; query cycles through value-generating operators are rejected. | Recursive Datalog with binding/stratification restrictions. [Rules](https://docs.oxfordsemantic.tech/reasoning.html#the-rule-language-of-rdfox) | Shared positive rules are a substantial area of overlap. |
| Negation | Base complements are classical denials; `.dlq` has no negation-as-failure. | Stratified negation-as-failure. [Rules](https://docs.oxfordsemantic.tech/reasoning.html#the-rule-language-of-rdfox) | RDFox can express absence-based rule conditions that require an explicit host-selected relation in Nova. |
| Aggregates | Scoped, stratified `MIN`; joining back preserves ties. General `COUNT`, `SUM`, `AVG` and `MAX` query operators are absent. | Stratified rule aggregates and broader SPARQL aggregates. [Aggregates](https://docs.oxfordsemantic.tech/querying.html#aggregate-functions) | Nova's aggregate language is materially narrower. |
| Equality | Individual equality and alias expansion; inferred functionality/maximum-one equality; no unique-name assumption. | `off` default; `noUNA` or `UNA` modes. [Equality](https://docs.oxfordsemantic.tech/data-stores.html#equality) | RDFox must be configured to obtain the intended identity semantics. |
| Equality with aggregation | Completed ontology equality can feed scoped queries; the accepted input view must normalize identities. | Aggregate/negation rules rejected when equality mode is enabled. [Equality](https://docs.oxfordsemantic.tech/data-stores.html#equality) | The combination requires architecture-specific treatment; support for each feature alone is insufficient. |
| Existential witnesses | L3 creates restriction/subject-specific witnesses; positive minimum n creates explicitly different witnesses; bounds expose incompletion. | `SKOLEM` constructs stable blank nodes; general Nova-L3 compatibility unverified. [Skolem examples](https://docs.oxfordsemantic.tech/reasoning.html) | An explicit Skolem rule and automatic existential ontology translation are different user interfaces. |
| Inconsistency and constraints | Detects denials/equality conflicts; ordinary queries are guarded on inconsistent ontologies. | `owl:Nothing` remains queryable; `rdfox:ConstraintViolation` prevents commit. [Reasoning](https://docs.oxfordsemantic.tech/reasoning.html), [constraints](https://docs.oxfordsemantic.tech/transactions.html#constraining-data-store-content) | Nova's classical query guard differs from RDFox's configurable data-validation workflow. |
| Fact/rule changes | Insertions propagate; eligible deletions use DRed; equality/existential changes can rebuild. | Incremental materialization after fact/rule changes. [Reasoning](https://docs.oxfordsemantic.tech/reasoning.html) | Both maintain consequences, but update and failure interfaces differ. |

The central semantic distinction is between “not known” and “known false.”
Nova does not infer childlessness from missing child edges. RDFox can express
an absence test through its rule language, but that does not make such a test
equivalent to a classical description-logic complement. An application moving
rules between the engines must preserve this distinction.

## Queries, arithmetic and calendar time

Nova evidence: [query language](../QUERY_LANGUAGE.md),
[domain implementation](../../src/dlp_reasoner/domains.py),
[domain tests](../../tests/test_domains.py) and
[extension guide](../DLP_NOVA_EXTENSIONS.md).

| Capability | DLP Nova: implemented / source-tested | RDFox: official documentation | Practical implication |
| --- | --- | --- | --- |
| Query interface | Instance/property/schema APIs plus versioned `.dlq` rules, named parameters and finite supplemental relations. No general SPARQL endpoint. | SPARQL query/update and RDFox extensions. [Querying](https://docs.oxfordsemantic.tech/querying.html) | Existing SPARQL clients need an adapter or query rewrite for Nova. |
| Query operators | Positive joins, filters, scalar binds, finite scans and scoped `MIN`; safe variables and strata checked before execution. | `FILTER`, `BIND`, subqueries, property paths and aggregates. [Querying](https://docs.oxfordsemantic.tech/querying.html) | RDFox has a broader ready-made query vocabulary. |
| Typed arithmetic | Signed 64-bit integers; bounded exact decimals with scale 0–18; explicit finite binary64 conversion/comparison. | SPARQL/XPath arithmetic, constructors and mathematical functions. [Functions](https://docs.oxfordsemantic.tech/querying.html#built-in-functions) | Numeric range, promotion, overflow and error behavior need explicit mapping. |
| Ontology datatypes | Limited string/integer/decimal/Boolean value identity; other literals are opaque for base entailment. Datatype ranges/facets rejected. | Wider documented XML Schema literal support; `unsignedLong` range limitation. [Datatypes](https://docs.oxfordsemantic.tech/data-stores.html#supported-data-types-for-literals) | Nova's checked extension values do not imply complete OWL datatype reasoning. |
| Calendar dates | Checked Gregorian dates, years 1–9999; local dates kept distinct from instants. | Dates, datetime types and component extraction. [Date/time functions](https://docs.oxfordsemantic.tech/querying.html#date-and-time-functions) | Both can express calendar operations; their accepted value domains need alignment. |
| Completed years | Dedicated `completedYears(birth,event,march1)`; only the March 1 leap-day policy is implemented. | Expressible through `YEAR`/`MONTH`/`DAY` and `IF`; no dedicated equivalent verified. [Date/time functions](https://docs.oxfordsemantic.tech/querying.html#date-and-time-functions) | Nova packages a specific policy; RDFox can express the same valid-input calculation. |
| Instants and durations | UTC-normalized instants at microsecond precision; fixed durations and local time have distinct checked types. | Timezones and fixed/year-month/general durations. [Date/time functions](https://docs.oxfordsemantic.tech/querying.html#date-and-time-functions) | RDFox documents broader duration forms; Nova's fixed-duration rules avoid implicit calendar-month conversion. |
| Interval boundaries | Explicit nonempty intervals with `[start,end)` containment; adjacency does not imply intersection. | Half-open containment is expressible with comparisons. [Operators](https://docs.oxfordsemantic.tech/querying.html#operators) | A boundary policy is part of the query contract, not implied by the presence of timestamps. |
| Invalid inputs | Structured type/domain/policy/provider errors; failures do not become complete empty answers. | Expression and transaction error behavior follows documented interfaces. [Transactions](https://docs.oxfordsemantic.tech/transactions.html#recoverable-and-non-recoverable-errors-within-read-write-transactions) | Matching successful answers does not establish matching failure behavior. |

For valid birth/event dates with event no earlier than birth, Nova's March 1
policy is the year difference minus one when the event's `(month,day)` precedes
the birth's `(month,day)`. This expression can be written using RDFox's documented
functions. February 29, 2000 to February 28, 2021 yields 20 completed years;
to March 1, 2021 it yields 21. That is a policy correspondence derived from the
expression, not a locally executed RDFox result.

Similarly, Nova's half-open validity can be represented as
`start <= at && at < end`, provided the inputs already satisfy `start < end`
and the values use a compatible time domain. Neither that expression nor
calendar extraction supplies source completeness, missing-date resolution or
historical provenance. Nova's scoped birthdate view makes those selection
decisions explicit; equivalent application decisions remain necessary elsewhere.

## Geospatial capabilities

Nova evidence: [domains](../../src/dlp_reasoner/domains.py),
[point indexes](../../src/dlp_reasoner/spatial.py),
[geometry provider](../../src/dlp_reasoner/geometry.py),
[spatial tests](../../tests/test_spatial.py) and
[geometry tests](../../tests/test_geometry_provider.py).

| Capability | DLP Nova: implemented / source-tested | RDFox: official documentation | Practical implication |
| --- | --- | --- | --- |
| Geographic point distance | WGS84 ellipsoidal geodesic through packaged GeographicLib-C in both domain backends. | `GEODIST` uses haversine metres. [Geospatial function](https://docs.oxfordsemantic.tech/querying.html#geospatial-functions) | The metrics are different; radius membership near a boundary can differ. |
| Coordinate order | `wgs84Point(longitude,latitude)`, then distance between typed points. | `GEODIST(latitude1,longitude1,latitude2,longitude2)`. [Geospatial function](https://docs.oxfordsemantic.tech/querying.html#geospatial-functions) | An adapter must reorder coordinates explicitly. |
| Point index | Python/native resident index provides conservative candidates followed by exact ellipsoidal refinement. | Lucene point-distance and geometry tuple-table queries. [Lucene spatial search](https://docs.oxfordsemantic.tech/data-sources.html#geospatial-search-with-lucene-data-sources) | Index ownership and final-predicate semantics differ. |
| Planar geometries | Optional GEOS-backed projected geometry operations; checked CRS/metric ownership and boundary semantics. | Lucene `LatLonShape` relations are documented; equivalent projected GEOS operations unverified. [Lucene spatial search](https://docs.oxfordsemantic.tech/data-sources.html#geospatial-search-with-lucene-data-sources) | Geographic shape indexing should not be presented as the same contract as projected planar geometry. |
| Spatial dependencies | Calendar/geodesic libraries packaged; GEOS optional; Python-coordinated providers may remain hybrid. | Lucene integration uses Lucene libraries and a JVM. [Requirements](https://docs.oxfordsemantic.tech/features-and-requirements.html#third-party-software) | “Native spatial support” does not imply that every operation has the same deployment dependency. |
| Roads and OSM | Bounded OSM ingestion, explicit road associations, configured routing/provider adapters; distinct no-route/out-of-region outcomes. | General data sources; equivalent OSM importer/routing status contract unverified. [Data sources](https://docs.oxfordsemantic.tech/data-sources.html) | Nova provides domain-specific integration pieces; their live source/transport setup still belongs to the host. |

RDFox's 7.6 release added both the direct `GEODIST` function and Lucene
geospatial search. Therefore “RDFox has no geospatial support” would be false.
Nova's concrete distinction is its chosen ellipsoidal metric and explicit
typed/provider/index contracts. The inspected RDFox function documentation does
not specify the sphere radius; its exact numerical policy beyond haversine
should remain unverified here.

Neither engine's spatial feature list alone establishes conformance to the
complete GeoSPARQL standard. We have not verified that conformance for RDFox;
Nova does not claim it. Likewise, calculating geographic distance does not
establish road reachability, legal turn access or traffic-sign applicability.

## Events, updates and recovery

Nova evidence: [provider/window contracts](../PROVIDERS_AND_WINDOWS.md),
[native windows](../../src/dlp_reasoner/native_windows.py),
[application recovery](../APPLICATION_RECOVERY.md) and
[recovery tests](../../tests/test_recovery_session.py).

| Capability | DLP Nova: implemented / source-tested | RDFox: official documentation | Practical implication |
| --- | --- | --- | --- |
| Event-time state | Explicit host APIs admit/revise events, advance watermarks/time, expire idle windows and maintain predecessor relations. No `.dlq WINDOW` syntax. | Equivalent event-watermark/lateness API not verified; transaction-driven answer deltas are documented. [Delta queries](https://docs.oxfordsemantic.tech/transactions.html#delta-queries) | Transaction changes and event-time windows are distinct features. |
| Late/corrected events | Bounded retained history, source offsets/revisions and deterministic ordering support correction and predecessor repair. | Can update timestamped facts; equivalent built-in late-event policy unverified. [Updates](https://docs.oxfordsemantic.tech/apis.html#managing-data-store-content) | Timestamp storage alone does not supply admission or correction policy. |
| Maintained query answers | Reusable snapshots/plans, revision-aware caches and maintained ordered `MIN`; upstream joins can still reevaluate full snapshots. | Registered delta queries record additions/deletions for a restricted SPARQL subset. [Delta queries](https://docs.oxfordsemantic.tech/transactions.html#delta-queries) | RDFox exposes registered answer deltas; Nova exposes complete query results with selected reuse mechanisms. |
| Checkpoint recovery | Portable session/window checkpoints; application envelope validates source context/replay availability; queries rerun before a current answer is exposed. | Persistent database restart/replication; matching external-source replay envelope unverified. [Persistence](https://docs.oxfordsemantic.tech/persistence.html) | Nova explicitly binds application state to source revisions; database durability solves a different part of recovery. |
| Time/history | Valid-time and transaction-time relations can be queried; source/history selection is explicit. | Timestamped data, updates and query functions support authored history models. [Functions](https://docs.oxfordsemantic.tech/querying.html#date-and-time-functions) | Neither comparison establishes a built-in complete bitemporal or stream-processing platform. |

Nova does not autonomously choose authoritative sources, call a routing service,
advance a watermark, guarantee message delivery or eliminate replay gaps. Its
host application owns these actions. Its checkpoint checks detect incompatible
context; they do not prove that a selected relation is complete or authentic.
These limits matter when interpreting the stronger-looking term “recovery.”

## Storage, concurrency and deployment

Nova evidence: [native sessions](../NATIVE_SESSION.md),
[mobile integration](../MOBILE_APP_INTEGRATION.md),
[mobile qualification](../MOBILE_APP_QUALIFICATION.md),
[native package format](../NATIVE_PACKAGE_FORMAT.md) and
[project manifest](../../pyproject.toml).

| Capability | DLP Nova: implemented / source-tested | RDFox: official documentation | Practical implication |
| --- | --- | --- | --- |
| Storage model | In-memory reasoning, serialized compiled packages and explicit application checkpoints; no general persistent database backend. | Main-memory database with configurable disk persistence. [Persistence](https://docs.oxfordsemantic.tech/persistence.html) | Nova's packages/checkpoints do not replace a transactional system of record. |
| Concurrent transactions | One worker serializes a native session; cancellation alone is concurrent. No general multi-client transaction server. | Multiple readers, one writer per store, serializable transactions; no cross-store transaction. [Transactions](https://docs.oxfordsemantic.tech/transactions.html#concurrent-execution-of-transactions) | RDFox directly serves a multi-client database use case absent from Nova's current runtime. |
| Replication/HA | No implemented replicated database service. | File-sequence replication/HA; feature license required, experimental on macOS/Windows. [Persistence](https://docs.oxfordsemantic.tech/persistence.html#file-sequence-persistence) | This is a substantial operational scope difference, with RDFox platform conditions. |
| APIs and embedding | Python, C/C++ session boundary, Swift and Kotlin/JNI wrappers; CLI; compiled `.dlpn` execution without Python. | Shell, REST, Java, C/C++ and static/shared libraries. [Interfaces](https://docs.oxfordsemantic.tech/features-and-requirements.html#interfaces), [APIs](https://docs.oxfordsemantic.tech/apis.html) | Native embedding itself is not unique to Nova. |
| Mobile | Authored packages, AAR/XCFramework recipes, simulator/emulator qualification; physical-phone qualification remains pending. | Vendor explicitly offers smartphone-ready builds outside public downloads; exact platform/wrapper coverage not verified. [Mobile](https://www.oxfordsemantic.tech/rdfox-on-edge-device) | Nova's visible integration artifacts are useful, but do not imply that RDFox lacks mobile deployment. |
| Administration/security | Local library/tooling; no built-in multiuser auth, permissions server, HA control plane or administration console. | Roles/access control, REST endpoint and browser console. [Features](https://docs.oxfordsemantic.tech/features-and-requirements.html) | A Nova network service would require additional application and operational work. |
| Distribution/license | Repository source and vendor notices are available; no root project license or package license declaration was found in the inspected tree. | Public desktop/server binaries require an issued license; mobile distribution is separate. [Download](https://www.oxfordsemantic.tech/download), [license key](https://docs.oxfordsemantic.tech/features-and-requirements.html#license-key) | Do not describe Nova as unrestricted/open-source distribution or assume RDFox entitlements from a public download. |

## Implications for DLP Nova's positioning

Nova can accurately emphasize its inspectable L0–L3 compiler, explicit
incompletion/consistency contract, typed ellipsoidal/calendar operations,
versioned external computations, and source-visible mobile/window/recovery
integration. These are concrete characteristics of this implementation.
They do not establish that each individual capability is absent in RDFox or
novel among rule systems.

RDFox documents capabilities Nova currently lacks: general SPARQL integration,
stratified absence-based rules, broader aggregates/datatypes, persistent
multi-client database operation and administrative facilities. Supporting an
application that depends on those features would require meaningful additional
Nova implementation or host infrastructure.

The principal unresolved RDFox areas are exact mobile build/API availability,
an equivalent event-watermark and source-replay contract, projected GEOS-style
geometry support, and automatic coverage of Nova's entire L3 input fragment.
These remain **unverified**, not negative feature claims. The comparison is
suitable for internal architectural discussion; it should not be converted
into a competitive feature checklist by removing these evidence qualifications.
