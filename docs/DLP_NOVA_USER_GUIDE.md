# DLP Nova user documentation

DLP Nova is a reasoner for **Description Logic Programs (DLP)** with explicit
temporal, geospatial and numerical query extensions. It derives class membership
and relationships from an ontology, then evaluates application queries over the
completed knowledge and finite input data. Use it for tasks such as classifying
traffic signs before a distance search, selecting observations valid at a given
instant, or calculating ages from accepted historical records.

This documentation describes the repository implementation as of **10 September
2026**. DLP Nova is the product name used here; installation and programming
identifiers remain `dlp-reasoner`, `dlp_reasoner`, and `dlp`. There is no separate
`nova` command or package to install.

## Reading map

| Start here when you want to… | Documentation |
| --- | --- |
| Install, run, query and update an ontology | This user guide |
| Write `.dlp` and choose among the L0–L3 fragments | [Base language guide](DLP_NOVA_LANGUAGE_GUIDE.md) |
| Write `.dlq`, calculate with dates, search points, or process windows | [Temporal and geospatial extensions](DLP_NOVA_EXTENSIONS.md) |
| Try small complete examples | [DLP Nova examples](../examples/dlp_nova/README.md) |
| Understand the design and evidence | [DLP Nova paper](paper/dlp-nova.tex), [PDF](../output/pdf/dlp-nova.pdf), [build instructions](paper/README.md#dlp-nova-systems-paper) |

The older focused documents remain useful API references. This manual connects
them into an application workflow; the executable source and examples define the
current implementation when a historical design proposal differs.

## 1. What the two languages do

**Ontology documents (`.dlp`)** declare classes, properties, individuals and
axioms using the thesis's Appendix A notation. The selected L0–L3 profile controls
which positions and constructors the compiler accepts. Parsing produces an RDF
graph; compilation produces Horn rules, equality rules, constraints and, in L3,
possibly existential witnesses. Construction of a `Reasoner` materializes those
consequences immediately.

**Extension programs (`.dlq`)** start with `version 1`. They query a completed
ontology and explicitly supplied finite relations with joins, scalar `bind`,
Boolean `filter`, provider `scan` and stratified `MIN`. Dates and distances are
computed by these operators. They do not change the interpretation of `.dlp`
axioms, and their outputs are not automatically asserted into the ontology.

```text
ontology.dlp / local RDF graph
             |
        DLP compilation
             |
     completed ontology   +   selected records / map data / window rows
             |                            |
             +----- version 1 .dlq -------+
                          |
                complete scoped result
```

The languages use different notation. For example, `Individual(ex:a type(ex:A))`
is an ontology assertion; `ex:A(?x)` is a query relation. The `dlp rules` command
prints a diagnostic Horn listing, which is not an alternative `.dlp` input file.
There is currently no `dlp query` CLI command: execute `.dlq` with `QueryRuntime`
or load an authored native package in a native session.

## 2. Install and run

Run these commands from the repository root. Python **3.11 or later** is required.

```sh
uv sync --extra dev --locked
uv run dlp validate examples/dlp_nova/base-l0.dlp --profile L0
uv run dlp instances examples/dlp_nova/base-l0.dlp \
  'https://example.org/nova#KnownParent' --profile L0
```

The instance query returns `["https://example.org/nova#anna"]`. Validation prints
JSON with `complete: true` and `consistency: "consistent"`, alongside work counts
and timing information. Durations and internal counts can change across builds.

Without `uv`, use an isolated environment:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
python -m dlp_reasoner validate examples/dlp_nova/base-l0.dlp --profile L0
```

The editable install follows the current checkout. The `uv --locked` workflow
uses the checked-in dependency lock; the pip alternative does not promise the
same dependency resolution.

### Native and optional libraries

The default ontology backend is Python. To use resident C++ relation indexes:

```sh
uv run python -m dlp_reasoner.native --build
uv run dlp validate examples/dlp_nova/base-l0.dlp --profile L0 --backend native
```

A local C++17 compiler is needed for a first native build unless a compatible
precompiled library is configured. WGS84 point distance uses the packaged native
GeographicLib kernel **even with the Python query backend**. The native domain
library therefore needs desktop build tools or a configured precompiled library.
See [native backend setup](NATIVE_BACKEND.md) and the
[extension guide](DLP_NOVA_EXTENSIONS.md).

Projected geometry operators require the optional GEOS C library. OSM PBF reading
requires the optional `osm` extra, which installs `osmium`
(`uv sync --extra dev --extra osm --locked`).
Neither is required for ordinary DLP classification or the arithmetic-only query
below. Remote routing additionally requires a host-configured service.

## 3. Write your first ontology

```text
Namespace(ex = <https://example.org/nova#>)
Ontology(
  Class(ex:Musician partial ex:Person)
  Class(ex:Composer partial ex:Musician)
  Individual(ex:anna type(ex:Composer))
)
```

Save this as `hello.dlp`, then run:

```sh
uv run dlp instances hello.dlp 'https://example.org/nova#Person' --profile L0
uv run dlp subsumes hello.dlp 'https://example.org/nova#Person' \
  'https://example.org/nova#Composer' --profile L0
uv run dlp materialize hello.dlp --profile L0 -o /tmp/nova-closure.ttl
```

The first command returns Anna; the second returns `true`. `subsumes` takes the
**superclass first**, then the subclass. `partial` supplies necessary conditions:
every composer is a musician. A `complete` class definition adds the reverse
inclusion, so both directions must be legal under the profile.

Start with L0 for positive, function-free examples. L1 adds equality; L2 adds
consistency constraints; L3 permits existential consequents that can create
witnesses. The default is L2. These are constructor-position ceilings, not OWL
profile certificates or guarantees of inexpensive evaluation. The
[language guide's profile matrix](DLP_NOVA_LANGUAGE_GUIDE.md) explains the exact
restrictions and includes an executable example for every layer.

### Input formats and imports

File suffixes select `.dlp`, Turtle (`.ttl`), RDF/XML (`.rdf`, `.owl`, `.xml`),
N-Triples (`.nt`) or N3 graph syntax (`.n3`). For an unusual suffix, pass
`--format dlp`, `turtle`, `xml`, `nt` or `n3`. An `.owl` suffix selects RDF/XML;
use `--format turtle` if its content is Turtle. N3 implication rules are not
an additional rule language.

The input must be local. Imports are not downloaded automatically. Resolve
required imports into the graph before reasoning and remove the `owl:imports`
triples after resolution. Unsupported logical constructs fail explicitly rather
than silently becoming supported through RDF parsing.

## 4. Command-line reference

Every command takes an ontology file. Class, property and individual arguments
are full IRIs; file-local prefixes are not expanded in shell arguments.

| Command after `dlp` | Arguments after the file | Result |
| --- | --- | --- |
| `validate` | — | Consistency/completeness and statistics |
| `instances` | `class_iri` | Individuals entailed to belong to the class |
| `types` | `subject` | Entailed named classes |
| `values` | `subject property` | Entailed property values |
| `entails` | `subject property object` | Entailment test; CLI object must be an IRI |
| `subsumes` | `superclass subclass` | Whether the subclass implies the superclass |
| `equivalent-classes` | `left_class right_class` | Both subsumption directions |
| `property-subsumes` | `superproperty subproperty` | Property inclusion |
| `equivalent-properties` | `left_property right_property` | Property equivalence |
| `inverse-properties` | `left_property right_property` | Entailed inverse relationship |
| `is-symmetric` / `is-transitive` | `property` | Entailed property characteristic |
| `has-domain` / `has-range` | `property class_iri` | Entailed domain/range condition |
| `rules` | — | Compiled diagnostic Horn listing |
| `materialize` | `-o path` | Exported RDF closure, plus statistics |

Common options are `--profile L0|L1|L2|L3`, `--backend python|native`,
`--strategy semi-naive|naive`, `--format`, `--max-rounds` (default 1,000),
`--max-facts` (1,000,000), and `--max-depth` (32). Semi-naive is the default
ontology evaluation strategy. Materialization also accepts
`--output-format turtle|nt|xml` and `--include-witnesses`.

For ordinary execution, exit status **0** means success, **1** invalid input or
operation, **2** detected inconsistency, and **3** incomplete reasoning. `rules`
is a diagnostic exception: it returns 0 after producing its listing even when
materialization is inconsistent or incomplete. Use `validate` for a status gate.

Witnesses are hidden by default in exports and individual/property answer APIs.
Enable their documented `include_witnesses` option when inspecting L3 results;
an exported witness identifier is not a newly discovered real-world name.

## 5. Use Python and maintain an ontology

```python
from rdflib import Namespace, RDF, RDFS
from dlp_reasoner import Reasoner

EX = Namespace("https://example.org/nova#")
reasoner = Reasoner.from_file("examples/dlp_nova/base-l0.dlp", profile="L0")
assert reasoner.complete and reasoner.consistency == "consistent"
assert reasoner.entails(EX.anna, RDF.type, EX.KnownParent)
assert reasoner.subsumes(EX.Person, EX.Musician)
print(sorted(map(str, reasoner.property_values(EX.anna, EX.ancestorOf))))

axiom = (EX.Musician, RDFS.subClassOf, EX.Artist)
reasoner.update(add=[axiom])
assert reasoner.entails(EX.anna, RDF.type, EX.Artist)
reasoner.update(remove=[axiom])
assert not reasoner.entails(EX.anna, RDF.type, EX.Artist)
reasoner.to_graph().serialize(destination="/tmp/nova-closure.ttl", format="turtle")
```

Use RDFLib `URIRef`/`Namespace` for IRIs and `Literal` for RDF values. For literal
objects, use `reasoner.entails(subject, property, Literal(...))` instead of the
CLI's IRI-only form. `Reasoner.from_dlp(text, profile=...)` accepts an in-memory
document; `Reasoner(graph, profile=...)` accepts an RDFLib graph.

Keep a reasoner alive for repeated queries. Its bounded answer cache defaults
to 256 entries; `query_cache_size=0` disables it. Inspect `query_cache_info` or
call `clear_query_cache()`. Updates invalidate affected reusable state and
answers. Use `update(add=..., remove=...)` for explicit RDF changes; direct
mutation of `reasoner.graph` does not perform a reasoning update. Removing an
assertion does not remove a conclusion that still follows from another support.

Updates compile the candidate graph before changing the engine, so a rejected
compilation preserves the previous state. Evaluation then updates the live
engine: an execution failure can invalidate it, and an inconsistent candidate
can become the new state. Inspect `complete`, `consistency` and failure
diagnostics after an update. If your application must preserve
only consistent publications, validate a separate candidate before replacing
the application's owner. See [maintenance semantics](CORRECTED_MAINTENANCE.md)
and [map publication](OSM_SPATIAL_RUNTIME.md) for the stronger map-runtime gate.

### Interpret answers correctly

An absent answer means **not entailed**, not known false. DLP ontology reasoning
uses an open-world reading. Different individual names do not assert inequality;
equality and functional properties may identify them. A constraint violation
means inconsistency, not a request to delete one inconvenient fact.

Exhaustive query APIs require consistent, completed reasoning. On an
incomplete materialization, `entails` can still return a sound positive fact;
when it cannot establish the fact it raises `IncompleteReasoningError`, rather
than returning a false negative. Inconsistent inputs raise
`InconsistentOntologyError` for ordinary query APIs. Check `stats` for
`violations`, warnings and the limit/failure reason.

## 6. Execute an extension query

This self-contained arithmetic example requires no spatial provider:

```python
from rdflib import Literal, Namespace
from dlp_reasoner.query_runtime import QueryRuntime, QueryScope

EX = Namespace("https://example.org/nova#")
program = """
version 1
prefix ex: <https://example.org/nova#>
prefix num: <urn:dlp:numeric:>
query incremented(?person, ?next) given (?minimum) :-
    ex:age(?person, ?age),
    bind num:add(?age, 1) as ?next,
    filter num:greaterThanOrEqual(?next, ?minimum).
"""
with QueryRuntime(program) as queries:
    result = queries.evaluate(
        {EX.age: {(EX.anna, Literal(23)), (EX.max, Literal(17))}},
        parameters={"minimum": Literal(20)},
        scope=QueryScope("urn:example:nova-ages", "1"),
    )
    rows = result.rows("urn:dlp:query:incremented")
    assert {(str(person), int(age)) for person, age in rows} == {(str(EX.anna), 24)}
    print(queries.explain())
```

Pass `reasoner=reasoner` to expose a completed ontology as query relations.
Named classes are unary predicates and named properties are binary predicates;
`rdf:type(?individual, ?class)` exposes inferred named-class memberships.
Supplemental relations may have other arities. Load a `.dlq` with
`Path("queries.dlq").read_text()` and pass its text as `program`.

`parameters` binds the names declared by `given`. `scope` labels the selected
dataset and its revision. The runtime also seeds `?scope` and `?revision` with
those values, including when they are not listed in `given`; reserve those names
for this context. Use another name, such as `?pointRevision`, for a separate
index revision. Scope does not itself filter data, validate a source's
completeness, or populate other given parameters. Supply those explicitly.

Returned relations are immutable. `additions` and `retractions` compare the new
complete result with the previous complete result. A failed candidate raises an
error and sets `queries.complete=False`; `last_complete` can still identify an
older successful result under its original revision. Keep revision labels with
answers so that older results are not presented as current.

The [extension guide](DLP_NOVA_EXTENSIONS.md) develops this pattern into calendar
arithmetic, interval validity, exact WGS84 radius queries, projected topology,
directed routing, finite event windows and bitemporal history. It includes a
reference for the installed operations and the complete inputs for each example.

## 7. Choose an execution path

| Path | Appropriate use and execution boundary |
| --- | --- |
| `Reasoner(..., backend="python")` | Desktop ontology API; Python semi-naive materialization by default |
| `Reasoner(..., backend="native")` | Same ontology API with resident C++ relations/indexes; Python still orchestrates reasoning |
| `QueryRuntime(..., backend="native")` | Local supported query plans execute in C++; provider/custom-operation plans can use hybrid host orchestration |
| `standalone.NativeRuntime` | Separate C++ Horn runtime; bounded indexed full-round evaluation and safe rebuild updates |
| `NativeSession` / Swift / Kotlin session wrappers | Load authored `.dlpn` packages, supply typed inputs, query and checkpoint without Python on the device |

Setting `backend="native"` on the desktop reasoner does not turn the whole
application into a standalone native executable. Inspect query
`stats["execution_mode"]` and `explain()` when the actual path matters.
Do not assume a GEOS or network provider is packaged into a mobile application.

For native applications, start with [session lifecycle](NATIVE_SESSION.md),
[package authoring](NATIVE_PACKAGE_FORMAT.md),
[mobile integration](MOBILE_APP_INTEGRATION.md) and
[application recovery](APPLICATION_RECOVERY.md). A checkpoint restores explicit
inputs; execution and validation of the restored application context are still
required before publishing answers. Native IDs belong to one live owner and
must be resolved again after restoration.

## 8. Troubleshooting and boundaries

| Symptom | Explanation and next step |
| --- | --- |
| Parser reports a source line/column | Check capitalization, parentheses, declaration ordering and the appropriate `.dlp`/`.dlq` notation. |
| `ProfileError` after successful RDF parsing | The axiom or constructor position is unsupported. Check the language matrix; a higher profile helps only when it actually admits that feature. |
| Inconsistency / exit 2 | Inspect `stats["violations"]`; examine disjointness, explicit inequality, equality and cardinality constraints. |
| Incomplete / exit 3 | Inspect the bound that stopped execution. Recursive L3 witnesses may not terminate; increasing a limit does not establish termination. |
| An empty answer | Verify full IRIs, relation arities, source selection and scope. Absence is not a completeness certificate or negative ontology fact. |
| Domain type/overflow error | Use the declared types and finite ranges; convert exact numbers to binary64 explicitly before floating-point comparisons. |
| A date/time is rejected | Follow the domain profile's Gregorian, explicit-offset and microsecond rules. Host-local time is not an implicit timezone. |
| A scan operation is unknown | Register its provider explicitly. Names in historical `.rules.proposed` files are not capability declarations. |
| Native build/library failure | Check the appropriate configured library or compiler, and match architecture/ABI to the current host. |
| A source/provider revision changes | Rebuild or rebind the matching snapshot/index/context and reevaluate. Cached data cannot certify a new source revision. |

DLP Nova does not claim complete OWL DL/Full or OWL 2 RL conformance, arbitrary
existential termination, unrestricted recursive arithmetic, negation-as-failure,
automatic named-timezone resolution, global geodesic polygon topology, or a
complete turn/lane-aware road engine. The current extensions expose specific
checked operations. See the [profile assessment](DLP_PROFILE_ASSESSMENT.md) and
[extension support reference](DLP_NOVA_EXTENSIONS.md) for their precise scope.

## 9. Run the worked applications

```sh
uv run python examples/bach_temporal/run_queries.py --backend both
uv run python examples/traffic_signs/run_queries.py --backend both
# Requires the optional GEOS C library:
uv run python examples/temporal_geo/run_queries.py --backend both
```

These examples assert their expected answers. The Bach example returns completed
ages 23 and 24 for the earliest accepted **recorded** child; unqualified complete
family-history ages remain absent. Traffic-sign rules classify candidates and
refine ellipsoidal distances. The event example checks validity boundaries,
recorded-time corrections, a late-event entry retraction, checkpoint recovery
and expiration after explicit clock advancement.

They are executable tutorials and regression evidence, not performance promises.
The separate [DLP Nova paper](paper/dlp-nova.tex) reports its own scoped evidence;
the [earlier DLP paper](paper/README.md) retains its original research question
and submission identity.
