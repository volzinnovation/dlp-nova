# DLP reasoner

A runnable implementation of **Description Logic Programs** from Raphael Volz's 2004 PhD thesis, [*Web Ontology Reasoning with Logic Databases*](docs/Volltext.pdf). It compiles an OWL ontology to Horn rules and materializes their consequences with indexed semi-naive evaluation. Python and RDFLib replace the historical Java/KAON/XSB components.

The package provides position-sensitive L0–L3 profiles, equality with congruence, consistency constraints, RDF queries, and materialization maintenance. It is a DLP reasoner, not a complete OWL DL or OWL Full reasoner. Unsupported logical constructs fail explicitly.

## Paper and citation

Raphael Volz (Pforzheim University), **Description Logic Programs Revisited:
The Benefits and Limits of Specialized Ontology Reasoning**.
Submitted to arXiv in **cs.AI** on **9 September 2026**.
Submission reference: [arXiv:submit/8059314](https://arxiv.org/submit/8059314/view).

Read the [complete paper with technical appendices](output/pdf/combined-report.pdf).
The [paper documentation](docs/paper/README.md) includes the LaTeX source,
submission archive, and reproducible build instructions.

The submission link requires author access. `submit/8059314` is a submission
reference; the [permanent arXiv identifier](https://info.arxiv.org/help/arxiv_identifier.html)
will use the form `YYMM.NNNNN`. Until that identifier is available, use this
BibTeX entry, which links to the manuscript in this repository:

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

Once the paper is announced, replace `url` with its public arXiv abstract URL,
add `eprint`, `archivePrefix = {arXiv}`, and `primaryClass = {cs.AI}`, and remove
the temporary submission note.

## Run it

Requires Python 3.11 or later. With [uv](https://docs.astral.sh/uv/):

```sh
uv sync --extra dev --locked
uv run dlp validate examples/family.ttl
uv run dlp instances examples/family.ttl 'https://example.org/family#Parent'
uv run dlp values examples/family.ttl 'https://example.org/family#jsbach' 'https://example.org/family#ancestorOf'
uv run dlp subsumes examples/family.ttl 'https://example.org/family#Person' 'https://example.org/family#Composer'
uv run dlp is-transitive examples/family.ttl 'https://example.org/family#ancestorOf'
uv run dlp rules examples/family.ttl
uv run dlp materialize examples/family.ttl -o /tmp/family-closure.ttl
uv run dlp validate examples/existential.ttl --profile L3
```

Alternatively, create a virtual environment and run `python -m pip install -e '.[dev]'`. The CLI is also available as `python -m dlp_reasoner`. Turtle, RDF/XML (`.rdf`/`.owl`), N-Triples and N3 graph syntax are parsed with RDFLib; N3 implication rules are not an additional rule language. Files are local. Imports must be explicitly resolved into the input graph and their `owl:imports` triples removed; no imports are fetched automatically.

`validate` prints JSON containing consistency, completeness, elapsed times, rule/fact counts, equality merges, evaluator work and any limit reason. Exit codes are 0 for success, 1 for an invalid input/operation, 2 for inconsistency and 3 for an incomplete materialization. `examples/inconsistent.ttl` intentionally returns 2.

## Python API

```python
from rdflib import Namespace, RDF, RDFS
from dlp_reasoner import Reasoner

F = Namespace("https://example.org/family#")
r = Reasoner.from_file("examples/family.ttl", profile="L2")
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

Datatype literals can be stored as values. Automatic value identity is limited to well-typed plain/language strings, `xsd:string`, the integer/decimal family, and booleans. Other literal datatypes are opaque RDF terms; their OWL value identities and clashes are not decided. The engine detects equality of incompatible values in the supported families. **Datatype ranges, facets, datatype definitions and complete OWL datatype entailment are unsupported** and explicit datatype constraints are rejected. Consistency and entailment results therefore concern this stated datatype interpretation, not complete OWL datatype semantics. Python equality is not used to identify URI/string, decimal/float/double, or binary values across datatype boundaries. See the [W3C datatype specification](https://www.w3.org/TR/owl2-syntax/#Datatype_Maps). General disjunctive consequents, max-cardinality above one, universal antecedents, property chains, keys and unsupported OWL vocabulary are rejected. There is no remote import resolver, full OWL syntax/profile conformance checker, backward-chaining Prolog backend or persistent database backend.

## Updates and performance

The engine distinguishes asserted facts from its closure. Insertions propagate deltas. Eligible fact and rule deletions use delete-and-rederive (DRed), including removal of unsupported recursive cycles and preservation of alternative supports. Old rules identify affected facts; only current rules may restore them. The RDF API recompiles the complete candidate ontology and applies its fact and rule deltas together. Equality and existential retractions retain a rebuilding fallback so old equivalence classes and witnesses can be reconstructed safely. Both old and candidate programs must satisfy the DRed eligibility checks.

`stats["update_method"]` distinguishes `dred`, `dred-rules`, `incremental-rules`, and rematerialization paths. An interrupted overdeletion rebuilds from the current program before exposing any partial results. The [corrected maintenance algorithm and correctness argument](docs/CORRECTED_MAINTENANCE.md) state the assumptions and explain the replacement for the thesis's faulty rule-deletion procedure.

Execution uses exact hash membership for fully bound atoms and cached set-intersection plans for unary conjunctions over one variable. Eligible semi-naive delta variants are coalesced so each binding fires once per round. General joins and the naive reference evaluator remain available. The lazy schema cache stores positive proofs only and is invalidated by ontology updates. See the [research assessment and correctness arguments](docs/RESEARCH_IMPROVEMENTS.md) for the selected adaptations from 2004–2026 research.

Run validation and benchmarks:

```sh
uv run pytest -q
uv run ruff check src tests benchmarks scripts
uv run python -m benchmarks.run --suite quick --repeats 5 --output /tmp/dlp-quick.json
uv run python -m benchmarks.run --suite thesis --repeats 5 --output /tmp/dlp-thesis.json
uv run python -m benchmarks.run --suite bach --repeats 5 --output benchmarks/bach-results.json
```

The [Bach benchmark](docs/BACH_BENCHMARK.md) adds the complete Table 2.5 knowledge base in
[Turtle](examples/bach.ttl) and [RDF/XML](examples/bach.owl), requiring `--profile L3`, plus
the separate [L0 family tree](examples/bach-family.ttl) from chapter 6. Its
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

## Implementation map

- `src/dlp_reasoner/compiler.py`: OWL graph validation, expression normalization and Horn compilation.
- `src/dlp_reasoner/engine.py`: joins/indexes, delta evaluation, equality, constraints, bounds and updates.
- `src/dlp_reasoner/joins.py`: positional positive joins and optional bounded ordering estimates.
- `src/dlp_reasoner/reasoner.py`: RDF API, queries, fresh probes and exports.
- `src/dlp_reasoner/schema.py`: lazy positive class/property consequence indexes.
- `src/dlp_reasoner/support.py`: experimental current-proof certificates for DRed.
- `src/dlp_reasoner/cli.py`: executable interface and inspectable rule output.
- `tests/`, `examples/`, `benchmarks/`: executable evidence and reproducible workloads.

The implementation follows the stated description-logic semantics where the thesis contains inconsistent formulas. The [detailed thesis review](docs/THESIS_ERRATA.md) distinguishes confirmed formula errors, counterexamples to some stated procedures, benchmark inconsistencies, and ambiguous notation, with page references and executable checks. Technical references for the modern parser and RDF syntax are the [RDFLib graph documentation](https://rdflib.readthedocs.io/en/latest/apidocs/rdflib.graph/) and [W3C OWL reference](https://www.w3.org/TR/owl-ref/).
