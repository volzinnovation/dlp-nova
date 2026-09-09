# Concrete DLP input syntax

The `.dlp` format follows **Appendix A, “BNF Grammar for DLP,” printed
pp. 233–236** of [the thesis](Volltext.pdf), referenced by §5.1.5, p. 119.
This is the thesis's `Namespace(...)` / `Ontology(...)` concrete abstract syntax.
The mathematical DL notation in Chapter 5 and the Horn rules printed by
`dlp rules` are separate representations, not accepted input formats.

The parser uses no additional dependencies. It lowers a document to an RDFLib
graph, then the existing compiler checks normalization, constructor positions,
and the requested L0–L3 profile. Parsing alone does not establish profile
legality or consistency. Unsupported logical forms fail explicitly.

## Running and embedding

```sh
uv run dlp validate examples/family.dlp
uv run dlp validate examples/bach.dlp --profile L3
uv run dlp validate examples/bach-family.dlp --profile L0
uv run dlp instances examples/family.dlp 'https://example.org/family#Parent'
uv run dlp rules examples/family.dlp
uv run dlp materialize examples/family.dlp -o /tmp/family-closure.ttl
```

`.dlp` is detected case-insensitively. `--format dlp` overrides detection.
Input is UTF-8 and local; namespace and ontology IRIs do not trigger downloads.
Materialization output remains Turtle, RDF/XML, or N-Triples. CLI query arguments
remain full IRIs.

```python
from dlp_reasoner import Reasoner, parse_dlp

text = """
Namespace(ex = <https://example.org/demo#>)
Ontology(
  Class(ex:Composer partial ex:Person)
  Individual(ex:bach type(ex:Composer))
)
"""
graph = parse_dlp(text, source="demo.dlp")
reasoner = Reasoner.from_dlp(text, profile="L0")
```

Malformed syntax raises `DLPParseError`, a `ProfileError` subclass, with the
source name, line, and column. Unknown prefixes, wrong arities, unclosed
parentheses/comments/strings, and unknown constructors are errors. Semantic
profile errors continue to come from the existing compiler. The CLI retains
exit codes 0 (complete and consistent), 1 (invalid), 2 (inconsistent), and
3 (incomplete).

## Names, axioms, and assertions

Declare namespace prefixes before a single `Ontology(...)`. Its optional first
argument names the ontology. Use `prefix:localname` or `<absolute-IRI>` for names;
`rdf`, `rdfs`, `owl`, and `xsd` are predefined conveniences. Prefixes in the
printed grammar contain letters, and local names begin with a letter followed
by letters, numbers, or underscores. Use full IRIs for names containing hyphens,
as in the Bach examples. Keywords are case-sensitive. Statements need no commas
or trailing periods. Both `//` and `/* ... */` comments are supported.

```text
Namespace(ex = <https://example.org/demo#>)
Ontology(<https://example.org/demo>
  Annotation(rdfs:label "A small family ontology"@en)
  Class(ex:Person partial)
  Class(ex:Composer partial ex:Person)
  Class(ex:Parent complete
    intersectionOf(ex:Person restriction(ex:hasChild value(ex:child))))
  ObjectProperty(ex:hasChild
    super(ex:ancestorOf) inverseOf(ex:hasParent)
    domain(ex:Person) range(ex:Person))
  ObjectProperty(ex:ancestorOf Transitive)
  Individual(ex:bach type(ex:Composer) value(ex:hasChild ex:child))
)
```

| Syntax | Meaning |
| --- | --- |
| `Class(A partial C D)` | Declare A; A is a subclass of both C and D. |
| `Class(A complete C D)` | Declare A equivalent to the intersection of C and D. |
| `SubClassOf(C D)` | C is a subclass of D. |
| `EquivalentClasses(C D ...)` | All listed descriptions are equivalent. |
| `DisjointClasses(C D ...)` | Every pair of listed descriptions is disjoint. |
| `EnumeratedClass(C a)` | C is equivalent to the singleton nominal containing a. |
| `SubPropertyOf(P Q)` | P is a subproperty of Q. |
| `EquivalentProperties(P Q ...)` | All listed properties are equivalent. |
| `Individual(a type(C) value(P b))` | C(a) and P(a,b). Multiple types and values are allowed. |
| `SameIndividual(a b ...)` | All listed individual names denote the same individual. |
| `DifferentIndividuals(a b ...)` | Every listed pair denotes different individuals. |

Names in this table abbreviate declared prefixed names or full IRIs. An
`Individual(...)` without a name is anonymous and can occur as a nested property
value. Individual equality is not equality of class or property predicates.

## Descriptions and restrictions

| Syntax | DL reading |
| --- | --- |
| `intersectionOf(C D ...)` | Conjunction C ⊓ D ⊓ … |
| `unionOf(C D ...)` | Disjunction C ⊔ D ⊔ … |
| `complementOf(C)` | Complement ¬C |
| `oneOf(a b ...)` | Nominal enumeration {a,b,…} |
| `restriction(P someValuesFrom(C))` | Existential ∃P.C |
| `restriction(P allValuesFrom(C))` | Universal ∀P.C |
| `restriction(P value(a))` | Has-value ∃P.{a} |
| `restriction(P minCardinality(n))` | Minimum cardinality ≥n P |
| `restriction(P maxCardinality(n))` | Maximum cardinality ≤n P |
| `restriction(P cardinality(n))` | Exact cardinality, normalized by the compiler |
| `owl:Thing`, `owl:Nothing` | Top ⊤, bottom ⊥ |

Multiple components in one restriction mean their conjunction, e.g.
`restriction(ex:p allValuesFrom(ex:C) maxCardinality(1))`. Nested fillers are
supported. An existential antecedent is available in L0; an ordinary existential
consequent requires L3. Universal antecedents and positive union consequents
remain unsupported. See the [profile matrix](THESIS_SPEC.md#language-matrix).

Object properties accept `super`, `inverseOf`, `domain`, `range`, and the
`Symmetric`, `Functional`, `InverseFunctional`, and `Transitive` characteristics.
Annotations use `Annotation(...)` at ontology level and `annotation(...)` inside
declarations. Literal values may be plain, language-tagged, or typed, such as
`"Bach"`, `"Komponist"@de`, and `"1685"^^xsd:integer`. The compiler's existing
limited datatype semantics apply. Declared object properties require individual
values and declared datatype properties require literals, including declarations
that appear after their uses. Conflicting declarations and direct links between
declared object and datatype properties are rejected. Undeclared properties
remain generic RDF predicates; this is not a complete OWL DL vocabulary checker.

Datatype range clauses and declared datatype `someValuesFrom`/`allValuesFrom`
restrictions are rejected. Positive minimum/exact cardinalities on declared
datatype properties are also rejected, because the evaluator does not construct
literal witnesses. Literal facts, literal has-value restrictions, and supported
maximum/zero-cardinality forms remain available. `Datatype(...)` declarations
do not enable datatype range reasoning.

Custom annotation properties are declared as metadata automatically and cannot
also be used as logical properties. Reserved RDF/OWL structural vocabulary
cannot be repurposed as ordinary property or class assertions: for example,
`value(rdfs:subClassOf ...)` and `type(owl:FunctionalProperty)` are rejected.
Use the corresponding axiom directives instead. This prevents an input
assertion from being silently ignored or reinterpreted by RDF lowering.

The thesis's convenience forms have the exact Table 5.4 (p. 126) directions:

```text
Class(ex:A partial
  localdomain(ex:P ex:D)  // SubClassOf(restriction(ex:P someValuesFrom(ex:A)) ex:D)
  localrange(ex:P ex:R)   // SubClassOf(ex:A restriction(ex:P allValuesFrom(ex:R)))
)
```

In particular, the local domain form infers D for a subject linked by P to an A.
It does not create a global domain restriction on P.

## Deliberate differences from the printed BNF

Appendix A describes itself as L3 but its `descriptionRight` production omits
existential and minimum-cardinality consequents, its common `description`
omits existential restrictions, and `cardNr` allows only 0 or 1. These exclusions
conflict with Chapter 5, Definitions 5.1.19–5.1.20 (p. 118). The input parser
accepts those Chapter 5 forms and nonnegative cardinalities; the compiler still
rejects combinations outside the selected profile. This is required to express
the thesis's complete Bach example.

The parser also accepts combinations of object-property characteristics rather
than enforcing the printed mutually exclusive characteristic production.
Predefined namespaces are a convenience. The semantic target remains the
[thesis-derived specification](THESIS_SPEC.md), including its documented errata;
this is not a claim of byte-for-byte conformance to every Appendix A production,
OWL Functional Syntax, or OWL DL support. Imports are never fetched automatically.

## Rewritten examples and validation

| DLP document | Corresponding RDF fixture | Profile |
| --- | --- | --- |
| [family.dlp](../examples/family.dlp) | `family.ttl` | L2 |
| [existential.dlp](../examples/existential.dlp) | `existential.ttl` | L3 |
| [inconsistent.dlp](../examples/inconsistent.dlp) | `inconsistent.ttl` | L2; intentionally inconsistent |
| [bach.dlp](../examples/bach.dlp) | `bach.ttl`, `bach.owl` | L3 |
| [bach-family.dlp](../examples/bach-family.dlp) | `bach-family.ttl` | L0 |

The chapter 2 Bach knowledge base and chapter 6 maintenance tree remain separate
examples. The original RDF fixtures and historical benchmark reports are
retained. Parser, CLI, and example-equivalence tests exercise the new input path
without changing the meaning or measurement boundaries of historical runs.

```sh
uv run pytest -q tests/test_dlp_parser.py tests/test_dlp_examples.py tests/test_dlp_cli.py
```
