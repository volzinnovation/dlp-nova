# DLP reasoner

A runnable implementation of **Description Logic Programs** from Raphael Volz's 2004 PhD thesis, [*Web Ontology Reasoning with Logic Databases*](docs/Volltext.pdf). It compiles an OWL ontology to Horn rules and materializes their consequences with indexed semi-naive evaluation. Python and RDFLib replace the historical Java/KAON/XSB components.

The package provides position-sensitive L0–L3 profiles, equality with congruence, consistency constraints, RDF queries, and materialization maintenance. It is a DLP reasoner, not a complete OWL DL or OWL Full reasoner. Unsupported logical constructs fail explicitly.

## Run it

Requires Python 3.11 or later. With [uv](https://docs.astral.sh/uv/):

```sh
uv sync --extra dev --locked
uv run dlp validate examples/family.ttl
uv run dlp instances examples/family.ttl 'https://example.org/family#Parent'
uv run dlp values examples/family.ttl 'https://example.org/family#jsbach' 'https://example.org/family#ancestorOf'
uv run dlp subsumes examples/family.ttl 'https://example.org/family#Person' 'https://example.org/family#Composer'
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

`Reasoner(graph, ...)` accepts an RDFLib graph. Construction eagerly compiles and materializes it. `instances`, `types`, `property_values`, `property_pairs`, `entails`, `subsumes`, `is_satisfiable`, `update` and `to_graph` are available. Anonymous expression queries use the expression's blank node in the input graph, and must be legal on the left of a DLP inclusion. Subsumption and satisfiability use isolated fresh-individual probes, so accidental overlap of observed instances does not imply subsumption. Subsumption requires an assertable subclass expression and a queryable superclass expression, as in thesis §5.4.

`compiler.compile_graph` exposes the Horn program. Compilation has a fixed 100,000-rule budget and rejects excessive nesting before evaluation. `engine.Engine` executes programs built with the immutable `Atom`, `Var`, `Skolem` and `Rule` dataclasses. A rule whose head is `None` is an integrity constraint. `Engine.update` maintains asserted facts; `Engine.update_rules` adds or removes rules.

## Supported semantics

| Profile | Adds |
|---|---|
| L0 | Class/property hierarchies; equivalent classes/properties; intersections; union and existential antecedents; universal consequents; has-value; inverse, symmetric and transitive properties; domain/range |
| L1 | Individual equality; functionality and inverse functionality; finite enumeration antecedents and singleton consequents; top; supported zero/one cardinality forms |
| L2 (default) | Disjointness, complement constraints, bottom, max-zero restrictions, explicit inequality and AllDifferent |
| L3 | Existential and positive minimum-cardinality consequents, with Skolem witnesses and explicit distinctness for min-n |

Constructor **position matters**. For example, `∃hasChild.Person ⊑ Parent` is L0, while `Parent ⊑ ∃hasChild.Person` needs L3. A universal restriction does not create an edge. Functional properties can identify two fillers; different IRIs alone do not prove inequality. Negation is represented by integrity constraints, never negation by failure. Equality operates on individual arguments, not class/property predicate identifiers.

A false entailment result means **not entailed**, not an assertion of its negation. Inconsistent ontologies expose their violations and refuse ordinary queries rather than returning a misleading ordinary closure. A private domain representative makes the domain nonempty even with no ABox assertions.

L3 can diverge, for example `A ⊑ ∃p.A`. The engine bounds rounds, facts and witness depth (defaults: 1,000 rounds, 1,000,000 facts, depth 32). On exhaustion, `complete` is false and consistency is `unknown` unless a contradiction has already been proved. Positive facts already derived can still be checked; negative and exhaustive answers raise `IncompleteReasoningError`. Witnesses are hidden from named-instance results unless `include_witnesses=True`. They are existential placeholders, not additional known individuals.

Datatype literals can be stored as values. Automatic value identity is limited to well-typed plain/language strings, `xsd:string`, the integer/decimal family, and booleans. Other literal datatypes are opaque RDF terms; their OWL value identities and clashes are not decided. The engine detects equality of incompatible values in the supported families. **Datatype ranges, facets, datatype definitions and complete OWL datatype entailment are unsupported** and explicit datatype constraints are rejected. Consistency and entailment results therefore concern this stated datatype interpretation, not complete OWL datatype semantics. Python equality is not used to identify URI/string, decimal/float/double, or binary values across datatype boundaries. See the [W3C datatype specification](https://www.w3.org/TR/owl2-syntax/#Datatype_Maps). General disjunctive consequents, max-cardinality above one, universal antecedents, property chains, keys and unsupported OWL vocabulary are rejected. There is no remote import resolver, full OWL syntax/profile conformance checker, backward-chaining Prolog backend or persistent database backend.

## Updates and performance

The engine distinguishes asserted facts from its closure. Insertions propagate deltas. Equality-free, function-free fact deletions use delete-and-rederive (DRed), including removal of unsupported recursive cycles and preservation of alternative supports. Equality and existential retractions rebuild the materialization so that old equivalence classes can split. Rule insertions can propagate incrementally; rule deletion rebuilds. The RDF API recompiles candidate changes before applying them, uses fact maintenance when compiled rules are unchanged, and rebuilds for schema changes. `stats["update_method"]` reports the path taken. Schema rebuilding is a correctness fallback, not the thesis's optimized incremental rule-removal algorithm.

Run validation and benchmarks:

```sh
uv run pytest -q
uv run ruff check src tests benchmarks
uv run python -m benchmarks.run --suite quick --repeats 5 --output /tmp/dlp-quick.json
uv run python -m benchmarks.run --suite thesis --repeats 5 --output /tmp/dlp-thesis.json
```

[Recorded benchmark results](benchmarks/results.md) and [raw observations](benchmarks/results.json) include separate parsing, compilation, materialization, instance query, property query and subsumption timings, repeats, memory and correctness checks. The thesis suite uses all 27 combinations of its ternary taxonomy depths (3/5/7), individuals per non-root class (3/9/15), and property variants (P0/P1/PF). Additional cases exercise equality, acyclic existentials, transitivity, DRed and rule updates. Small inputs compare semi-naive execution with a naive baseline and RDFLib's OWL RL engine. These synthetic modern measurements are not a reproduction of the 2004 system timings.

See [validation methodology](docs/VALIDATION.md), [thesis mapping and errata](docs/THESIS_SPEC.md), and [benchmark methodology](benchmarks/README.md) for details and limitations. The test suite combines explicit semantic regressions, independent OWL RL comparison within the shared fragment, exhaustive small models, and randomized update comparisons against fresh closure.

## Implementation map

- `src/dlp_reasoner/compiler.py`: OWL graph validation, expression normalization and Horn compilation.
- `src/dlp_reasoner/engine.py`: joins/indexes, delta evaluation, equality, constraints, bounds and updates.
- `src/dlp_reasoner/reasoner.py`: RDF API, queries, fresh probes and exports.
- `src/dlp_reasoner/cli.py`: executable interface and inspectable rule output.
- `tests/`, `examples/`, `benchmarks/`: executable evidence and reproducible workloads.

The thesis's FOL semantics takes precedence over apparent formula slips in its tables; the mapping document records these corrections. Technical references for the modern parser and RDF syntax are the [RDFLib graph documentation](https://rdflib.readthedocs.io/en/latest/apidocs/rdflib.graph/) and [W3C OWL reference](https://www.w3.org/TR/owl-ref/).
