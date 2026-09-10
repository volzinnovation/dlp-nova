# DLP Nova: application-driven priorities and effort

Internal engineering assessment, 10 September 2026. These are conditional
options and effort estimates, not an implementation commitment. No RDFox
benchmark is proposed or required.

## Judgment

The most useful next step is one validated application integration that exposes
a concrete limitation. Standard ontology and query interfaces are strong
candidates: they can let an application reuse its existing data and queries.
The repository currently demonstrates working computations, but does not
establish that a user's ontology is blocked by missing OWL 2 RL support or that
a consumer needs a GeoSPARQL endpoint.

The two directions serve different needs:

- **OWL 2 RL compatibility** matters when required external ontologies cannot
  be accepted, or their required entailments are not supplied by DLP Nova.
- **SPARQL/GeoSPARQL access** matters when an existing consumer needs to query
  DLP Nova through a standard interface and geometry vocabulary.

For the current traffic/OSM scenario, I would investigate the second need first:
classification, WGS84 radius filtering and validity already execute, so a
standard query interface could expose that existing value. For an application
whose supplied ontology fails admission, ontology compatibility takes priority.
For a native mobile application already using `.dlpn` sessions, neither a
network endpoint nor broader OWL support is automatically useful.

## What the current applications establish

| Repository workflow | Demonstrated behavior | Requirement still to establish |
| --- | --- | --- |
| [Traffic signs](../../examples/traffic_signs/README.md) | Inferred categories, finite spatial candidates and exact WGS84 radius answers. | Does an actual consumer have SPARQL/GeoSPARQL queries, required geometry encodings, or an unsupported ontology? |
| [Bach dates](../../examples/bach_temporal/README.md) | Ages over accepted recorded dates, scoped minima and explicit limits on completeness claims. | Are input interoperability or additional date policies actually blocking a historical-data application? |
| [Temporal/geospatial events](../../examples/temporal_geo/README.md) | Validity selection, late-event correction, restoration and explicit expiry. | What are the intended event volumes, lateness, answer deadlines and device requirements? |

These fixtures demonstrate feasibility. They are not evidence of user demand,
field data coverage, or production operating requirements.

## OWL 2 RL: choose the required contract

Profile membership, accepted constructors and RDF entailment are separate
questions. A profile validator can establish whether an input meets the RL
grammar; that does not supply missing entailments. A complete RDF closure also
requires a different graph-facing contract from the current class/property APIs.
The W3C distinguishes profile syntax, applied semantics and tool behavior.
[Profiles](https://www.w3.org/TR/owl2-profiles/#OWL_2_RL),
[conformance](https://www.w3.org/TR/owl2-conformance/).

One concrete local example is `A subClassOf B; B subClassOf C`. The current
`subsumes(C, A)` returns true, while `to_graph()` does not add the transitive
`A subClassOf C` schema triple. Similarly, individual `sameAs` does not replace
class/property interpretations in the way a generalized-triple rule engine
would. An endpoint over the exported graph must therefore describe its actual
entailment regime; it cannot advertise RL/RDF closure by renaming the current
L2 mode. See [entailment/export](../../src/dlp_reasoner/reasoner.py) and
the [existing profile assessment](../DLP_PROFILE_ASSESSMENT.md).

The compiler already has useful Horn, join, equality and denial machinery.
Source-verified gaps include property chains, keys, qualified maximum
cardinality, several property constraints and datatype range reasoning.
The appropriate subset to implement depends on the supplied ontology. Datatype
semantics and a broad triple-based equality/schema layer are likely to dominate
a comprehensive effort. General existential consequents remain a distinct L3
capability. Preserve the historical modes and introduce any new semantic
contract explicitly. [Compiler](../../src/dlp_reasoner/compiler.py),
[semantic tests](../../tests/test_semantic_validation.py).

## GeoSPARQL: expose a real query before expanding coverage

A bounded first integration can reuse RDFLib's SPARQL parser/evaluator and
query one cached RDF publication per completed revision. Reuse the existing
GeographicLib kernel and point index; use the GEOS provider for supported
projected geometry operations. Avoid rebuilding the graph per request and keep
the graph, geometry and index bound to the same publication.
[RDFLib SPARQL](https://rdflib.readthedocs.io/en/latest/intro_to_sparql/),
[map publication](../../src/dlp_reasoner/map_runtime.py).

The necessary adapter work includes geometry vocabulary and WKT literals,
declared coordinate order/units, supported function dispatch and SPARQL error
semantics. For example, CRS84 and EPSG:4326 WKT use different axis conventions;
the current longitude-first point API cannot simply relabel both. Empty
geometry behavior also differs from the current provider's rejection policy.
An implemented function subset is not equivalent to passing a whole GeoSPARQL
conformance class. Those classes must be selected and tested explicitly.
[GeoSPARQL 1.1](https://docs.ogc.org/is/22-047r1/22-047r1.html).

Full OWL 2 RL support is not a prerequisite for the initial spatial query
interface. GeoSPARQL separates its geometry/query requirements and RDFS
entailment class. This allows an application integration to progress without
first completing unrelated ontology features.

SPARQL has different duplicate, scope and expression-error semantics from
`.dlq`; translating the whole language into the existing query engine would
create unnecessary work. Optimize selected spatial query patterns only if the
application's measured latency requires it. A bounded endpoint also needs its
own execution limits and external-access policy; `.dlq` cancellation does not
automatically constrain RDFLib evaluation.
[SPARQL protocol](https://www.w3.org/TR/sparql11-protocol/),
[RDFLib execution considerations](https://rdflib.readthedocs.io/en/latest/security_considerations/).

## Conditional effort estimates

Estimates are person-weeks for one experienced engineer familiar with this
codebase, including focused correctness tests and review. They are judgment
ranges, not measured delivery forecasts. They assume reuse of existing parsers
and domain libraries; writable multiuser services, high availability and broad
standalone-native/mobile parity are outside these estimates.

| Deliverable, if the application requires it | Effort | Scope boundary |
| --- | ---: | --- |
| Audit supplied ontology, queries and update examples | 1–2 weeks | Reproduce blockers and agree exact expected answers, rejection behavior and operating limits. |
| Read-only SPARQL pilot over a completed publication | 1–2 weeks | One declared dataset, cached graph, ordinary results and basic error handling; internal pilot. |
| Add the GeoSPARQL mapping/functions needed by the identified queries | +2–4 weeks | Agreed WKT/CRS/geometry and function subset; additional to the SPARQL pilot. |
| Integrate spatial index access where the measured query plan needs it | +2–3 weeks | Correctness-preserving optimization of those query patterns, with reference answer checks. |
| Add a small required RL constructor group, such as chains plus property constraints | 2–6 weeks | Agreed input corpus and update behavior; not broad RL conformance. |
| Explicit bridge to an existing RL implementation | 4–8 weeks | Input/output, identity, failure and revision mapping; claims limited by the chosen implementation and tested contract. |
| Broad local RL/RDF mode and datatype/semantic validation | 16–28 weeks | A separate major project, justified only by a sufficiently broad requirement; service hardening is additional. |

These rows are alternatives or explicitly marked increments, not a backlog to
sum. A bounded spatial integration is approximately **3–6 person-weeks after
requirements are agreed**; measured need for index integration makes it roughly
5–9. A defensible estimate for broader GeoSPARQL coverage requires the actual
geometry, CRS and query corpus first.

## Acceptance before implementation

Obtain one application's actual ontology/data sample, existing query or API
interaction, representative change sequence, and required answers. Establish
what fails today and why it matters to that application. Choose the smallest
change that resolves that failure, then verify complete answers and updates
against the agreed cases. Measure latency, memory and device behavior only
against requirements the application actually has.

If the present APIs already meet those needs, document that outcome. A standards
feature should earn its priority through demonstrated integration value.
