# DLP Nova

**DLP Nova** is a runnable implementation of **Description Logic Programs** from Raphael Volz's 2004 PhD thesis, [*Web Ontology Reasoning with Logic Databases*](docs/Volltext.pdf). It reads the thesis's concrete DLP syntax or an OWL ontology, compiles to Horn rules, and materializes their consequences with indexed semi-naive evaluation. Later research results are incorporated into the design leading to a highly performant reasoner for the DLP fragments of OWL.

The desktop API uses Python and RDFLib, with optional resident C++ relation indexes. The package names are (`dlp-reasoner`), Python imports (`dlp_reasoner`) and CLI (`dlp`).

The package provides position-sensitive L0–L3 profiles, equality with congruence, consistency constraints, RDF queries, and materialization maintenance. It is a DLP reasoner, not a complete OWL DL or OWL Full reasoner. Unsupported logical constructs fail explicitly.

Extensions beyond the 2004 thesis add **temporal** and **geospatial** rules, **arithmetic**,
external computation providers and **event windows**. A standalone C++ runtime
executes compiled Horn and local query plans through C, Python, Swift and Kotlin
bindings. 

Native sessions retain query state and support application recovery;
the mobile apps run without Python. See [mobile integration and qualification](#native-sessions-and-mobile)
for the tested targets and remaining physical-device work.

## User documentation

Start with the [DLP Nova user guide](docs/DLP_NOVA_USER_GUIDE.md) for installation,
CLI commands, Python queries, updates and runtime selection. The
[base language guide](docs/DLP_NOVA_LANGUAGE_GUIDE.md) explains the L0–L3
fragments and their syntax with executable examples. The
[extension guide](docs/DLP_NOVA_EXTENSIONS.md) covers `.dlq` rules, temporal
operators, WGS84 distances, projected geometry, routing providers and event
windows. 

Try the [DLP Nova tutorials](examples/dlp_nova/README.md).


## Papers

The systems paper 
**DLP Nova: A Reasoner with Geospatial and Temporal Extensions**, describes specifically the geo-spatial and temporal extensions of the
engine, semantic contracts and first benchmark evidence:
[PDF](output/pdf/dlp-nova.pdf) .

The technical report  **Description Logic Programs Revisited:
The Benefits and Limits of Specialized Ontology Reasoning** (submitted to arXiv in **cs.AI** on **9 September 2026**) discusses the implementation, improvements from related work, further improvements, and corrections to errata in the PhD thesis.

Until the ArXiv identifier is available, use this BibTeX entry, which links to the manuscript in this repository:

```bibtex
@misc{volz2026dlp,
  author       = {Volz, Raphael},
  title        = {{Description Logic Programs Revisited}: The Benefits and Limits of Specialized Ontology Reasoning},
  year         = {2026},
  month        = sep,
  howpublished = {Preprint},
  note         = {Submitted to arXiv on 9 September 2026; submission 8059314, category cs.AI},
  url          = {https://github.com/volzinnovation/my-phd-thesis-gpt-6-astra/blob/main/output/pdf/combined-report.pdf}
}
```


## Run DLP nova on your computer/server

Requires Python 3.11 or later. With [uv](https://docs.astral.sh/uv/):

```sh
uv sync --extra dev --locked
uv run dlp validate examples/family.dlp
uv run dlp instances examples/family.dlp 'https://example.org/family#Parent'
uv run dlp values examples/family.dlp 'https://example.org/family#jsbach' 'https://example.org/family#ancestorOf'
uv run dlp subsumes examples/family.dlp 'https://example.org/family#Person' 'https://example.org/family#Composer'
uv run dlp is-transitive examples/family.dlp 'https://example.org/family#ancestorOf'
uv run dlp rules examples/family.dlp
uv run dlp materialize examples/family.dlp -o /tmp/family-closure.ttl
uv run dlp validate examples/existential.dlp --profile L3
```

Alternatively, create a virtual environment and run `python -m pip install -e '.[dev]'`. The CLI is also available as `python -m dlp_reasoner`. `.dlp` selects the thesis's Appendix A syntax; use `--format dlp` for another extension. Turtle, RDF/XML (`.rdf`/`.owl`), N-Triples and N3 graph syntax remain available through RDFLib; N3 implication rules are not an additional rule language. Files are local. Imports must be explicitly resolved into the input graph and their `owl:imports` triples removed; no imports are fetched automatically.

`validate` prints JSON containing consistency, completeness, elapsed times, rule/fact counts, equality merges, evaluator work and any limit reason. Exit codes are 0 for success, 1 for an invalid input/operation, 2 for inconsistency and 3 for an incomplete materialization. `examples/inconsistent.dlp` intentionally returns 2.

For example, the thesis syntax expresses a subclass and an individual as:

```text
Namespace(f = <https://example.org/family#>)
Ontology(
  Class(f:Composer partial f:Musician)
  Class(f:Musician partial f:Person)
  Individual(f:johann type(f:Composer))
)
```

The [DLP syntax guide](docs/DLP_SYNTAX.md) covers restrictions, properties,
annotations, error locations, and the differences between the printed Appendix A
grammar and Chapter 5's L3 definitions. Parsing feeds the same OWL compiler and
does not change the selected profile's semantics.

The optional [C++ relation/index backend](docs/NATIVE_BACKEND.md) keeps encoded
relations and column indexes in native memory across rule firings. Select it
explicitly; Python remains the default:

```sh
uv run python -m dlp_reasoner.native --build
uv run dlp validate examples/bach.dlp --profile L3 --backend native
```

The first native use builds a cached library with a local C++17 compiler, unless
a precompiled library is configured. No additional Python dependencies are
needed. Both `Reasoner` backends support the same input, query, equality,
constraint and update APIs; this native-index adapter keeps semantic orchestration
in Python. The separate [native session API](docs/NATIVE_SESSION.md) executes
compiled packages in C++. The [matched backend measurements](docs/NATIVE_BACKEND_PERFORMANCE.md)
report actual reasoning and update timings, including workloads that regress.

## Python API

```python
from rdflib import Namespace, RDF, RDFS
from dlp_reasoner import Reasoner

F = Namespace("https://example.org/family#")
r = Reasoner.from_file("examples/family.dlp", profile="L2")
assert r.entails(F.jsbach, RDF.type, F.Composer)
assert r.subsumes(F.Person, F.Composer)  # Composer is a subclass of Person
print(r.instances(F.Parent))
print(r.property_values(F.jsbach, F.ancestorOf))
print(r.types(F.jsbach))
print(r.consistency, r.stats)

r.update(add=[(F.Composer, RDFS.subClassOf, F.Artist)])
assert r.entails(F.jsbach, RDF.type, F.Artist)
r.update(remove=[(F.Composer, RDFS.subClassOf, F.Artist)])
assert not r.entails(F.jsbach, RDF.type, F.Artist)
r.to_graph().serialize(destination="/tmp/family-closure.ttl", format="turtle")
```

`Reasoner(graph, ...)` accepts an RDFLib graph. Construction eagerly compiles and materializes it. `instances`, `types`, `property_values`, `property_pairs`, `entails`, `subsumes`, `equivalent_classes`, `is_satisfiable`, `update` and `to_graph` are available. Anonymous expression queries use the expression's blank node in the input graph, and must be legal on the left of a DLP inclusion. Subsumption first checks a lazy index of positive schema consequences, then uses an isolated fresh-individual probe when that index supplies no proof. Satisfiability uses fresh probes. Accidental overlap of observed instances does not imply subsumption. Subsumption requires an assertable subclass expression and a queryable superclass expression, as in thesis §5.4. Class equivalence establishes its two subsumption directions independently, preventing equality or nominals from contaminating the other direction.

`Reasoner.from_dlp(text, profile="L2")` accepts an in-memory DLP document.
`parse_dlp(text)` returns its RDFLib graph without reasoning; use
`Reasoner(graph, ...)` or `compile_graph(graph, ...)` to validate profile legality.
For reproducible package authoring, `parse_dlp(text, blank_node_prefix="documentA")`
assigns deterministic anonymous-node IDs. Use a different prefix for each merged
document; the default continues to create fresh blank nodes on every parse.
Pass `backend="native"` to `Reasoner`, `Reasoner.from_file`,
`Reasoner.from_dlp`, or the low-level `Engine` to select persistent native indexes.

For a rarely changing ontology, keep one `Reasoner` alive and reuse it for queries.
Completed boolean and set-valued answers use a bounded cache (256 entries by
default); `query_cache_size=4096` increases the entry capacity, and `0` disables
answer caching. Instance/property lookups use relation indexes, and type lookups
reuse a lazy reverse index. Updates invalidate answers; unchanged compiled rules
retain their schema proofs. Use `r.query_cache_info` for cache counters and
`r.clear_query_cache()` to release answers and query views. See the
[query caching guide](docs/QUERY_CACHING.md) and
[first-use/warm measurements](docs/QUERY_PERFORMANCE.md).

Property queries are `property_subsumes(superproperty, subproperty)`, `equivalent_properties(left, right)`, `inverse_properties(left, right)`, `is_symmetric(property)`, `is_transitive(property)`, `has_domain(property, class)` and `has_range(property, class)`. They use sound schema proofs with isolated semantic probes as a fallback; a property's observed finite edges alone do not establish a universal property characteristic. Domain/range queries include inferred superclasses, and exact inverses do not inherit to strict subproperties. The corresponding CLI commands replace underscores with hyphens; `equivalent-classes` exposes class equivalence.

`compiler.compile_graph` exposes the Horn program. Compilation has a fixed 100,000-rule budget and rejects excessive nesting before evaluation. Auxiliary predicates factor conjunctions of unions and enumerations, avoiding explicit exponential DNF expansion. Rule-local variable names are canonical, so unrelated axiom changes preserve unchanged compiled rules. `engine.Engine` executes programs built with the immutable `Atom`, `Var`, `Skolem` and `Rule` dataclasses. A rule whose head is `None` is an integrity constraint. `Engine.update(add=..., remove=..., add_rules=..., remove_rules=...)` applies one validated fact/rule transaction; `Engine.update_rules` is the rule-only wrapper. Additions win when the same item is also removed.

The low-level API's frozen records are shallow. Custom predicate identifiers and
term values must keep stable equality and hashes while stored; RDF terms and
the documented primitive examples meet this requirement. Mutating a custom
value's internals can invalidate ordinary indexes as well as cached validation.

## Supported semantics

| Profile | Adds |
|---|---|
| L0 | Class/property hierarchies; equivalent classes/properties; intersections; union and existential antecedents; universal consequents; has-value; inverse, symmetric and transitive properties; domain/range |
| L1 | Individual equality; functionality and inverse functionality; finite enumeration antecedents and singleton consequents; top; supported zero/one cardinality forms |
| L2 (default) | Disjointness, complement constraints, bottom, max-zero restrictions, explicit inequality and AllDifferent |
| L3 | Existential and positive minimum-cardinality consequents, with Skolem witnesses and explicit distinctness for min-n |

Constructor **position matters**. For example, `∃hasChild.Person ⊑ Parent` is L0, while `Parent ⊑ ∃hasChild.Person` needs L3. A universal restriction does not create an edge. Functional properties can identify two fillers; different IRIs alone do not prove inequality. Negation is represented by integrity constraints, never negation by failure. Equality operates on individual arguments, not class/property predicate identifiers.

L0–L3 are historical implementation modes, not OWL 2 RL conformance labels.
Their accepted syntax overlaps RL and also permits some expressions outside it;
RL in turn includes features this compiler rejects. The [DLP profile assessment](docs/DLP_PROFILE_ASSESSMENT.md)
explains when these restrictions remain useful and why internal optimization
eligibility should be distinguished from a standard ontology-language profile.

A false entailment result means **not entailed**, not an assertion of its negation. Inconsistent ontologies expose their violations and refuse ordinary queries rather than returning a misleading ordinary closure. A private domain representative makes the domain nonempty even with no ABox assertions.

L3 can diverge, for example `A ⊑ ∃p.A`. The engine bounds rounds, facts and witness depth (defaults: 1,000 rounds, 1,000,000 facts, depth 32). On exhaustion, `complete` is false and consistency is `unknown` unless a contradiction has already been proved. Positive facts already derived can still be checked; negative and exhaustive answers raise `IncompleteReasoningError`. Witnesses are hidden from named-instance results unless `include_witnesses=True`. They are existential placeholders, not additional known individuals.

Datatype literals can be stored as values. Automatic value identity is limited to well-typed plain/language strings, `xsd:string`, the integer/decimal family, and booleans. Other literal datatypes are opaque RDF terms for ontology entailment; their OWL value identities and clashes are not decided. The engine detects equality of incompatible values in the supported families. **Datatype ranges, facets, datatype definitions and complete OWL datatype entailment are unsupported** and explicit datatype constraints are rejected. Consistency and entailment results therefore concern this stated datatype interpretation, not complete OWL datatype semantics. Python equality is not used to identify URI/string, decimal/float/double, or binary values across datatype boundaries. See the [W3C datatype specification](https://www.w3.org/TR/owl2-syntax/#Datatype_Maps). General disjunctive consequents, max-cardinality above one, universal antecedents, property chains, keys and unsupported OWL vocabulary are rejected. There is no remote import resolver, full OWL syntax/profile conformance checker, backward-chaining Prolog backend or persistent database backend.

The separate [`.dlq` query layer](#temporal-geospatial-and-stream-rules) explicitly
validates and computes with dates, instants, durations, numbers and geometries.
These built-ins preserve the ontology's stated datatype-entailment boundary.

## Updates and performance

The engine distinguishes asserted facts from its closure. Insertions propagate deltas. Eligible fact and rule deletions use delete-and-rederive (DRed), including removal of unsupported recursive cycles and preservation of alternative supports. Old rules identify affected facts; only current rules may restore them. The RDF API recompiles the complete candidate ontology and applies its fact and rule deltas together. Equality and existential retractions retain a rebuilding fallback so old equivalence classes and witnesses can be reconstructed safely. Both old and candidate programs must satisfy the DRed eligibility checks.

`stats["update_method"]` distinguishes `dred`, `dred-rules`, `incremental-rules`, and rematerialization paths. An interrupted overdeletion rebuilds from the current program before exposing any partial results. The [corrected maintenance algorithm and correctness argument](docs/CORRECTED_MAINTENANCE.md) state the assumptions and explain the replacement for the thesis's faulty rule-deletion procedure.

Execution uses exact hash membership for fully bound atoms and cached set-intersection plans for unary conjunctions over one variable. Eligible semi-naive delta variants are coalesced so each binding fires once per round. General joins and the naive reference evaluator remain available. The lazy schema cache stores positive proofs only and is retained across updates when the compiled rules are unchanged. Query answer caches are invalidated separately on ontology changes. See the [research assessment and correctness arguments](docs/RESEARCH_IMPROVEMENTS.md) for the selected adaptations from 2004–2026 research.

Run validation and benchmarks:

```sh
uv run pytest -q
uv run ruff check src tests benchmarks scripts
uv run python -m benchmarks.run --suite quick --repeats 5 --output /tmp/dlp-quick.json
uv run python -m benchmarks.run --suite thesis --repeats 5 --output /tmp/dlp-thesis.json
uv run python -m benchmarks.run --suite bach --repeats 5 --output benchmarks/bach-results.json
```

The [Bach benchmark](docs/BACH_BENCHMARK.md) adds the complete Table 2.5 knowledge base in
[DLP](examples/bach.dlp), [Turtle](examples/bach.ttl) and [RDF/XML](examples/bach.owl),
requiring `--profile L3`, plus the separate [L0 family tree](examples/bach-family.dlp)
from chapter 6. Historical benchmark runners retain their RDF input files so the
saved parsing measurements stay comparable. The
[32 query definitions](examples/bach-queries.json) check exact thesis-based answers, including
anonymous children and open-world distinctions. Three maintenance scenarios check the thesis's
fact transaction, rule deletion and symmetry insertion against independent reachability and
fresh reconstruction. The three cases also run in the quick and thesis suites.
See the [Bach results](benchmarks/bach-results.md) for measured parsing, reasoning and query timings.
The [external Bach comparison](docs/BACH_EXTERNAL_BENCHMARK.md) additionally
runs the original examples on HermiT and native ZodiacEdge, checking complete
answers and preserving failed update observations alongside valid timings.

[Recorded benchmark results](benchmarks/results.md) and [raw observations](benchmarks/results.json) include separate parsing, compilation, materialization, instance query, property query and subsumption timings, repeats, memory and correctness checks. The thesis suite uses all 27 combinations of its ternary taxonomy depths (3/5/7), individuals per non-root class (3/9/15), and property variants (P0/P1/PF). Additional cases exercise the corrected maximum-one/minimum-zero distribution, factored expressions, equality, acyclic existentials, transitivity, and maintenance across all three five-way taxonomy depths and both change ratios. Rule deletion and mixed updates are checked against fresh recomputation. Small inputs compare semi-naive execution with a naive baseline and RDFLib's OWL RL engine. These synthetic modern measurements are not a reproduction of the 2004 system timings. Commit **b1254c4** is the fixed default baseline for future comparisons; its [exact results and manifest](benchmarks/baselines/b1254c4/README.md) are preserved and verified by the runner. The older [baseline-results.json](benchmarks/baseline-results.json) remains historical evidence. Comparisons require unchanged input hashes and compatible measurement boundaries.

See [validation methodology](docs/VALIDATION.md), [thesis mapping and errata](docs/THESIS_SPEC.md), and [benchmark methodology](benchmarks/README.md) for details and limitations. The test suite combines explicit semantic regressions, independent OWL RL comparison within the shared fragment, exhaustive small models, and randomized update comparisons against fresh closure.

The [combined research preprint](output/pdf/combined-report.pdf) presents
scientific questions and findings for a broader audience, followed by technical
appendices with proofs, detailed methods, and complete experimental tables.
It distinguishes this project's contributions from prior algorithms and cites
the thesis and subsequent work. The [paper documentation](docs/paper/README.md)
provides the single arXiv source archive, submission metadata, and build
instructions; separately readable paper and supplement versions remain available.
The author is Raphael Volz, Pforzheim University.
Its external evaluation includes all fourteen official LUBM answer sets,
the ZodiacEdge author's positive LUBM rule program, and TPC-H-derived join
components. The [benchmark survey](docs/research-target-benchmarks.md) states the
differences from the full published workloads and prevents cross-machine timing
claims from being mistaken for matched comparisons.

The [subsequent research study](docs/RESEARCH_EXPERIMENTS.md) develops adaptive
unary evaluation and bounded proof certificates for mixed fact/rule maintenance.
It includes preservation arguments, a falsified planning heuristic, and an
18-case factorial experiment with four execution configurations. The
[raw experiments](benchmarks/research-results.json) preserve all observations;
the study distinguishes local improvements from unestablished claims of global
novelty or state-of-the-art performance.
Certificates reached 7.45× speedup on a supported-cycle workload but added about
19% on unsupported cycles; adaptive planning was neutral overall. Both remain
experimental after failing the predeclared default-adoption screen. Production
keeps fixed unary planning and ordinary DRed. The follow-up adds positional
positive joins, insertion-validation reuse, and incremental survivor indexes
to the defaults. A separate bounded query-order lookahead remains experimental.
The [follow-up methods](docs/RESEARCH_JOIN_FOLLOWUP_IMPLEMENTATION.md) explain
the guarantees and scope. Actual same-host comparisons with
[ZodiacEdge](benchmarks/zodiac-native-results.md) and
[HermiT](benchmarks/owl-bridge-results.md) report both advantages and limitations.
The [DLP assessment](docs/DLP_PROFILE_ASSESSMENT.md) treats computational value
separately from the practical prevalence of fragment-only ontologies.

## Temporal, geospatial and stream rules

The [extension implementation](docs/ENGINE_EXTENSION_IMPLEMENTATION.md) adds a
versioned `.dlq` query language, checked Python/C++ built-ins, scoped `MIN`,
resident native values and indexes, external computation providers, OSM ingestion,
GEOS geometry operations and bounded event windows. It includes native Horn and
local-query execution and portable compiled packages. The thesis's `.dlp`
ontology syntax remains compatible; new query rules use the separately versioned
`.dlq` language.

Native calendar operations use Howard Hinnant `date`, and WGS84 point distances use
GeographicLib-C in both backends. Optional GEOS handles projected geometries;
road-network computations use explicitly configured providers. Provider results
carry revision and status information, preserving `NO_ROUTE` and `OUT_OF_REGION`
without deriving a distance from either outcome.

```sh
uv run python examples/bach_temporal/run_queries.py --backend both
uv run python examples/traffic_signs/run_queries.py --backend both
# Optional installed GEOS C library required for projected geometry:
uv run python examples/temporal_geo/run_queries.py --backend both
```

These commands execute parsed rules, including calendar ages, hierarchical sign
queries, geodesic distances, validity intervals and corrected geofence entries.
The Bach example derives known-record parental ages of **23** for Johann
Sebastian and **24** for Maria Barbara. Completeness-dependent family answers
remain absent without an explicit validated certificate. Traffic queries combine
the PROLIX sign hierarchy, OSM associations and exact distance refinement.
The older reference commands below remain independent acceptance evidence.

The [temporal/geospatial design study](docs/TEMPORAL_GEOSPATIAL_RESEARCH.md)
investigates typed built-ins, arithmetic, indexed spatial predicates, and
event-time reasoning, with equal priority for static maps and live streams.
It includes current primary sources, code extension points, cache and update
contracts, and a staged implementation proposal. The
[external provider design](docs/EXTERNAL_PROVIDERS.md) covers distance/GIS
services, batch requests, provider versions, and failure handling. The
[shared library selection](docs/NATIVE_DOMAIN_LIBRARIES.md) identifies concrete
date/time, geometry and road-network libraries callable from Python and C++,
with a reproducible shared-library feasibility probe. The
[mobile runtime proposal](docs/MOBILE_RUNTIME_PROPOSAL.md) records the library
selection and portability design; the [mobile integration guide](docs/MOBILE_APP_INTEGRATION.md)
describes the implemented bindings, packages and host responsibilities. The
[traffic examples and reference checks](examples/temporal_geo/README.md)
illustrate radius/validity queries, late events, expiration, and historical
corrections. Their `.rules.proposed` syntax remains a design record; the new
`queries.dlq` files are executable.

The [engine extension specification](docs/ENGINE_EXTENSION_SPEC.md) defines the
implementation work, dependencies and release gates. Three worked examples
provide DLP ontologies, executable extension rules and independent reference
computations:

- [Bach birthdates and age at the earliest known child](examples/bach_temporal/README.md),
  including incomplete records, tied first children and date corrections.
- [OpenStreetMap nodes, ways, relations and tag mappings](examples/osm/README.md),
  with ordered memberships and a deterministic example importer.
- [PROLIX traffic-sign hierarchy and distances](examples/traffic_signs/README.md),
  preserving the supplied crosswalk, ambiguous codes and explicit road associations.

Run their checks with the existing environment:

```sh
.venv/bin/python examples/bach_temporal/reference_checks.py --backend both
.venv/bin/python examples/osm/reference_checks.py --backend both
.venv/bin/python examples/traffic_signs/generate.py --check
.venv/bin/python examples/traffic_signs/check.py --backend both
```

`--backend python` skips the existing optional native compiler requirement. These
checks distinguish engine classification from independent date, aggregate and
distance calculations. Use the `run_queries.py` commands above to execute the
new language itself.

### Reusing queries over a stable ontology

Keep the `Reasoner`, `QueryRuntime` and provider/domain contexts alive across
queries. The runtime reuses immutable ontology snapshots, prepared plans and
unchanged native term metadata as parameters change. Bounded ordered `MIN`
supports update affected groups, including the Bach first-child query, while
preserving ties and handling insertions, deletions and date corrections.
Upstream joins still evaluate complete snapshots; generated-term aggregate
sources retain a rebuild path. Source revisions, limits and cancellation remain
checked before publishing an answer.

The [query reuse measurements](docs/QUERY_OPTIMIZATION.md) compare each backend
with the same backend at commit `521b82a`, with whole-answer caching disabled:

| Measured warm query | Python speedup | Native speedup |
| --- | ---: | ---: |
| Selective lookup | 2.18× | 3.18× |
| Selected arithmetic | 2.20× | 3.11× |
| One changed minimum group | 1.75× | 2.00× |
| Bach child-date correction | 2.19× | 2.88× |

These are macOS arm64 results from five paired repetitions over 500 base
records, with ten changing warm inputs per process. First queries are slower
because they build reusable state. Native timings include the Python
`QueryRuntime` boundary, which remains slower than Python in absolute time on
these small cases; they do not measure standalone mobile sessions. The guide and
[raw observations](benchmarks/query-preparation-results.json) retain timings,
answer checks and source hashes.

## Native sessions and mobile

The [typed native session](docs/NATIVE_SESSION.md) loads a compiled `.dlpn`
package, accepts named parameters and mutable supplemental rows, executes local
queries, and returns bounded pages of typed results. C, Python, Swift and
Kotlin/JNI use the same C++ implementation. Sessions reuse their Horn data, query
plans and metadata, and support cancellation from another thread.

[Application recovery](docs/APPLICATION_RECOVERY.md) groups session inputs,
event-window checkpoints and source-version context. Restore validates every
expected component and checks replay availability when supplied, then requires
query execution before exposing a current answer. Mobile provider callbacks
accept finite typed batches with revision/completion checks. Applications supply
source selection, transport and live routing configuration; the packaged traffic
fixture uses explicitly synthetic road outcomes.

The [mobile build recipes](mobile/README.md) produce an Android AAR/debug APK
and an Apple XCFramework/local Swift package with a simulator app. Runtime
execution uses precompiled libraries and authored packages without Python or a
compiler on the phone. Build requirements and qualification commands are in the
[integration guide](docs/MOBILE_APP_INTEGRATION.md).

| Target | Recorded qualification |
| --- | --- |
| iOS | arm64 device and arm64/x86_64 simulator libraries target iOS 15; Swift 6 app execution passed on an arm64 iOS 26.5 simulator |
| Android | arm64-v8a/x86_64 libraries target API 24; debug APK execution passed on an arm64 API 36 emulator with **16 KiB pages**, including ELF and APK ZIP alignment |
| Physical phones | Qualification remains pending on connected iPhone and Android hardware |

Both apps execute the actual Bach and traffic packages and pass typed-result,
input-update, background/restart, idle-expiration, checkpoint-rejection and
outstanding-query cancellation checks. The
[application qualification record](docs/MOBILE_APP_QUALIFICATION.md) includes
artifact hashes and simulator/emulator memory observations. Physical-device
latency, energy, memory pressure and production routing/delivery remain release
gates. The recorded desktop validation includes **1,569 full-suite tests** and
**172 checks against the combined precompiled library**, with subsequent focused
checks documented in the [implementation guide](docs/ENGINE_EXTENSION_IMPLEMENTATION.md).

## Implementation map

The [native performance experiment](docs/NATIVE_PERFORMANCE.md) profiles the
current Python engine and compares an isolated binary join in Python and C++.
It reports kernel and conversion-inclusive timings separately, and assesses
C++, Go, and assembly without treating a kernel result as a whole-engine speedup.

- `src/dlp_reasoner/parser.py`: thesis Appendix A concrete syntax to an OWL graph, with source locations.
- `src/dlp_reasoner/compiler.py`: OWL graph validation, expression normalization and Horn compilation.
- `src/dlp_reasoner/engine.py`: joins/indexes, delta evaluation, equality, constraints, bounds and updates.
- `src/dlp_reasoner/native.py`, `native_store.cpp`, `native_store.h`: optional persistent C++ indexes, streamed joins, and the Python adapter/build cache.
- `src/dlp_reasoner/joins.py`: positional positive joins and optional bounded ordering estimates.
- `src/dlp_reasoner/reasoner.py`: RDF API, queries, fresh probes and exports.
- `src/dlp_reasoner/query_cache.py`: bounded query-answer caching and source-graph mutation tracking.
- `src/dlp_reasoner/query_ir.py`, `query_parser.py`, `query_runtime.py`: versioned extension rules, binding/stratum planning and scoped result publication.
- `src/dlp_reasoner/query_minimum.py`, `query_native.py`, `native_query.cpp`: ordered minimum supports, retained native plans and local query execution.
- `src/dlp_reasoner/domains.py`, `native_domains.cpp`: checked values and temporal, arithmetic and WGS84 operations.
- `src/dlp_reasoner/providers.py`, `geometry.py`, `spatial.py`, `osm.py`, `windows.py`: external computations, geometry/index ownership, map ingestion and event sources.
- `src/dlp_reasoner/standalone.py`, `native_runtime.cpp`, `packages.py`: standalone compiled Horn execution and portable packages.
- `src/dlp_reasoner/native_session.py`, `native_session.cpp`, `recovery.py`, `native_recovery.cpp`: reusable typed query sessions and transactional application recovery.
- `mobile/`, `examples/mobile_session/`: Swift/Kotlin bindings, app build/qualification scripts and authored Bach/traffic packages.
- `src/dlp_reasoner/schema.py`: lazy positive class/property consequence indexes.
- `src/dlp_reasoner/support.py`: experimental current-proof certificates for DRed.
- `src/dlp_reasoner/cli.py`: executable interface and inspectable rule output.
- `tests/`, `examples/`, `benchmarks/`: executable evidence and reproducible workloads.

The implementation follows the stated description-logic semantics where the thesis contains inconsistent formulas. The [detailed thesis review](docs/THESIS_ERRATA.md) distinguishes confirmed formula errors, counterexamples to some stated procedures, benchmark inconsistencies, and ambiguous notation, with page references and executable checks. Technical references for the modern parser and RDF syntax are the [RDFLib graph documentation](https://rdflib.readthedocs.io/en/latest/apidocs/rdflib.graph/) and [W3C OWL reference](https://www.w3.org/TR/owl-ref/).
