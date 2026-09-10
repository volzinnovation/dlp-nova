# DLP Nova language guide

DLP Nova reasons over classes, properties, individuals and their logical
relationships. Its base ontology language uses `.dlp` files with
`Namespace(...)` and `Ontology(...)` declarations. Four progressively stronger
profiles, **L0–L3**, determine which descriptions can be compiled. A separate
versioned `.dlq` language adds query rules and temporal, numeric and geospatial
operations.

This guide describes the implemented base language. Start with the
[user guide](DLP_NOVA_USER_GUIDE.md) for installation and operation, and continue
with the [extensions guide](DLP_NOVA_EXTENSIONS.md) for date arithmetic,
distances, geometry, providers and event windows. The installed Python package
remains `dlp_reasoner` and the command remains `dlp`; “DLP Nova” is the reasoner's
user-facing name.

## A first ontology

The following is the runnable
[base-l0.dlp](../examples/dlp_nova/base-l0.dlp) example:

```dlp
// Classification and property reasoning in L0.
Namespace(ex = <https://example.org/nova#>)

Ontology(<https://example.org/nova/base-l0>
  Annotation(rdfs:label "DLP Nova language tutorial"@en)

  Class(ex:Person partial)
  Class(ex:Musician partial ex:Person)
  Class(ex:Composer partial ex:Musician)
  Class(ex:KnownParent complete
    intersectionOf(ex:Person restriction(ex:hasChild value(ex:lea))))
  SubClassOf(restriction(ex:hasChild someValuesFrom(ex:Musician))
             ex:ParentOfMusician)
  SubClassOf(unionOf(ex:Composer ex:Singer) ex:Performer)
  Class(ex:Parent partial restriction(ex:hasChild allValuesFrom(ex:Person)))

  ObjectProperty(ex:hasChild
    super(ex:ancestorOf) inverseOf(ex:hasParent)
    domain(ex:Person) range(ex:Person))
  ObjectProperty(ex:ancestorOf Transitive)

  Individual(ex:anna type(ex:Composer) value(ex:hasChild ex:lea))
  Individual(ex:lea type(ex:Musician) value(ex:hasChild ex:max))
)
```

Run these commands from the repository root after the setup in the user guide:

```sh
uv run dlp validate examples/dlp_nova/base-l0.dlp --profile L0
uv run dlp instances examples/dlp_nova/base-l0.dlp \
  'https://example.org/nova#Person' --profile L0
uv run dlp values examples/dlp_nova/base-l0.dlp \
  'https://example.org/nova#anna' 'https://example.org/nova#ancestorOf' --profile L0
```

`validate` reports `"complete": true` and `"consistency": "consistent"`.
The instance query returns Anna, Lea and Max as full IRIs. The property query
returns Lea and Max: `hasChild` is a subproperty of `ancestorOf`, and the latter
is transitive. Anna is also inferred to be a `KnownParent`, a
`ParentOfMusician` and a `Performer`.

Two forms of inference occur here. Subclass axioms transfer existing
classifications: every composer is a musician, and every musician is a person.
Restrictions can recognize a pattern or impose a consequence. Having a child
who is a musician recognizes a `ParentOfMusician`; being a `Parent` imposes
`Person` on each child. The universal restriction does not create a child.

## Documents, names and values

A document contains zero or more namespace declarations followed by exactly
one ontology. The ontology may have an IRI identifying it; that IRI is optional.
Namespace declarations must precede the ontology, and content after its closing
parenthesis is an error. Neither namespace IRIs nor the ontology IRI cause a
network request. Imports are unsupported.

```text
Namespace(ex = <https://example.org/nova#>)
Ontology(<https://example.org/my-ontology>
  ...axioms and individual assertions...
)
```

Use these lexical rules:

| Element | Accepted spelling |
| --- | --- |
| Keywords | Case-sensitive: `Ontology`, `SubClassOf`, `partial`, `someValuesFrom`. |
| Prefix | One or more Unicode letters, such as `ex`; declare it before use. |
| Prefixed name | `ex:Anna`, `ex:person2`, `ex:johann-sebastian`; the local part begins with a letter and continues with letters, numeric characters, `_` or `-`. |
| Full IRI | `<https://example.org/person/123>` or `<urn:example:123>`; use this form for local names with slashes, periods or a leading digit. |
| Plain string | `"Johann Sebastian Bach"`. |
| Language string | `"Komponist"@de` or `"Composer"@en-us`; the parser requires lowercase language tags. |
| Typed literal | `"1685"^^xsd:integer`, `"true"^^xsd:boolean`, `"1685-03-31"^^xsd:date`. |
| Comments | `//` to end of line, or `/* ... */`. |

`rdf`, `rdfs`, `owl` and `xsd` are predefined prefixes. Use whitespace between
arguments; do not add commas, semicolons or trailing periods. Numeric property
values must be quoted typed literals: `value(ex:age "23"^^xsd:integer)`.
Unquoted integers occur only in cardinality syntax, such as `minCardinality(2)`.
The separate `.dlq` language has different punctuation and accepts bare numeric
constants.

In `.dlp` strings, escape a quote as `\"` and a backslash as `\\`. Other
backslash escapes such as `\n` are rejected. A `#` outside an IRI or string is
not a line comment in this format.

Declarations need not precede all uses of their names inside the ontology.
Explicit property kinds are checked after parsing the whole document, so moving
an incompatible `DatatypeProperty(...)` declaration to the end does not bypass
validation. Undeclared properties are accepted as generic RDF predicates; the
parser is not a complete OWL DL entity-type checker.

### Metadata and declaration order

Use `Annotation(...)` for ontology metadata and lowercase `annotation(...)`
inside declarations:

```text
Annotation(rdfs:label "A family ontology"@en)
Class(ex:Composer partial annotation(rdfs:comment "Writes music"))
Individual(ex:anna
  annotation(rdfs:label "Anna"@en)
  type(ex:Composer)
  value(ex:hasChild ex:lea))
```

Inside an `Individual`, annotations come first, then all `type(...)` clauses,
then all `value(...)` clauses. Placing a type after a value is a syntax error.
Class annotations follow `partial` or `complete`; property annotations precede
property components. An optional `Deprecated` immediately follows a class or
property name and records metadata; it does not disable its logical axioms.

Custom annotation properties are recognized as metadata automatically; they
can also be declared using `AnnotationProperty(ex:note)`. Metadata cannot be
used as an ordinary logical predicate. In particular,
`value(rdfs:label "Anna")` is rejected; use `annotation(rdfs:label "Anna")`
or your own logical data property. Reserved RDF/OWL structural vocabulary must
be expressed through the corresponding axiom directive.

## Classes and descriptions

A *class* is a unary predicate, a *property* is a binary predicate, and an
*individual* is an object that can participate in both. Class and property
declarations do not create instances.

| Axiom | Meaning |
| --- | --- |
| `Class(ex:A partial)` | Declare A without adding a superclass condition. |
| `Class(ex:A partial ex:B ex:C)` | Every A is both B and C. |
| `Class(ex:A complete ex:B ex:C)` | A holds exactly when B and C both hold; the conditions are conjoined. |
| `SubClassOf(ex:A ex:B)` | Every A is B. Both operands can be descriptions. |
| `EquivalentClasses(ex:A ex:B ex:C)` | All listed descriptions have the same extension. |
| `DisjointClasses(ex:A ex:B ex:C)` | Every pair of the descriptions is disjoint; requires L2. |
| `EnumeratedClass(ex:OnlyAnna ex:anna)` | Define the class containing precisely the individual denoted by Anna; requires L1. |

`complete` describes **class equivalence**, not completeness of the dataset. It
does not assert that every child, event or observation has been recorded. Use
`partial` when only one implication is intended. For example,
`Class(ex:Composer partial ex:Person)` does not classify every person as a
composer.

Equivalence compiles in both directions. A class definition using a description
that is legal only on the right of an inclusion may therefore be rejected as a
`complete` definition. `EnumeratedClass` accepts exactly one individual in this
syntax; `oneOf(...)` is the separate general nominal constructor.

### Description constructors

In the following table, `C` and `D` stand for class descriptions, `P` for a
property IRI, and `a` for an individual. Substitute actual prefixed names in a
document.

| Description | Reading |
| --- | --- |
| `intersectionOf(C D ...)` | Both C and D hold. |
| `unionOf(C D ...)` | At least one of C or D holds. |
| `complementOf(C)` | The logical complement of C. |
| `oneOf(a b ...)` | The individuals denoted by the listed names. |
| `restriction(P value(a))` | Has a P edge to a specific known individual. |
| `restriction(P someValuesFrom(C))` | Has at least one P successor in C. |
| `restriction(P allValuesFrom(C))` | Every P successor is in C. |
| `restriction(P minCardinality(n))` | Has at least n distinct P successors. |
| `restriction(P maxCardinality(n))` | Has at most n distinct P successors. |
| `restriction(P cardinality(n))` | Has exactly n distinct P successors. |
| `owl:Thing`, `owl:Nothing` | Universal class and empty class. |

Literal values are allowed in has-value restrictions. Cardinalities are
unqualified: `minCardinality(2 ex:Person)` is not accepted. Counting two
different names is insufficient to establish two distinct individuals; equality
may identify them.

Multiple components in one restriction are a conjunction of independent
restrictions:

```text
Class(ex:SingleContact partial
  restriction(ex:hasContact
    value(ex:anna)
    allValuesFrom(ex:Person)
    maxCardinality(1)))
```

At L1 this asserts an edge to Anna, classifies every contact as a person, and
identifies every contact with Anna. It does not create several alternative
meanings for one restriction. The parser constructs separate restrictions
before compiling their conjunction.

## Choosing L0, L1, L2 or L3

Select a profile with `--profile L0` through `--profile L3`, or
`Reasoner.from_file(path, profile="L0")`. The default is L2. A higher profile
allows additional forms; it does not add axioms that are absent from the input.
Choose the lowest profile that expresses the intended ontology when checking
its fragment membership.

In `SubClassOf(C D)`, **C is the left side (antecedent)** and **D is the right
side (consequent)**. Constructor position matters, including inside nested
descriptions. This is why a checklist saying “supports unions and universals”
is insufficient.

The table gives minimum profiles for the ordinary forms, after simplification.
“Unsupported” describes the general case: a redundant expression can simplify
to something supported.

| Form | Left side | Right side |
| --- | --- | --- |
| Named class | L0 | L0 |
| Nonempty intersection | L0, with legal left components | L0, with legal right components |
| General positive union | L0, with legal left components | Unsupported |
| Has-value restriction | L0 | L0 |
| Existential with an ordinary class filler | L0, with legal left filler | L3, with legal right filler |
| Universal restriction | Unsupported | L0, with legal right filler |
| Singleton nominal `oneOf(a)` | L1 | L1 |
| Nominal with several distinct entries | L1 | Unsupported |
| `owl:Thing` / minimum zero | L1 | L1 |
| Minimum one | L1 | L3 |
| Minimum n > 1 | Unsupported | L3 |
| Maximum one | Unsupported | L1 |
| Maximum zero / exact zero | Unsupported | L2 |
| Exact one | Unsupported | L3: minimum one plus maximum one |
| Maximum or exact n > 1 | Unsupported | Unsupported |
| Atomic complement | Unsupported | L2: denial |
| `owl:Nothing` | L2: empty antecedent | L2: denial |

Property inclusion, equivalence, inverses, symmetry, transitivity, and ordinary
class domains/ranges start in L0. Individual equality, functionality and inverse
functionality require L1. Disjointness and explicit individual inequality
require L2. Domain/range descriptions must themselves compile in their resulting
positions.

### L0: implications, joins and known fillers

L0 can infer from an existing existential pattern:

```text
SubClassOf(restriction(ex:hasChild someValuesFrom(ex:Musician))
           ex:ParentOfMusician)
```

This means: if `hasChild(x,y)` and `Musician(y)` hold, infer
`ParentOfMusician(x)`. It needs no generated individual. Conversely:

```text
SubClassOf(ex:Parent restriction(ex:hasChild someValuesFrom(ex:Person)))
```

requires L3 because it may need a previously unknown child. A has-value
consequent remains L0 because it names the filler:

```text
SubClassOf(ex:ParentOfLea restriction(ex:hasChild value(ex:lea)))
```

Likewise, an antecedent union splits into independent implications:

```text
SubClassOf(unionOf(ex:Composer ex:Singer) ex:Performer)
```

Both composers and singers become performers. Reversing this inclusion would
ask the engine to choose between two positive conclusions, which is outside
the general Horn fragment. Defining `Performer` equivalent to this union also
introduces that unsupported reverse direction.

### L1: equality and maximum one

The runnable [base-l1.dlp](../examples/dlp_nova/base-l1.dlp) demonstrates three
ways to derive equality: a functional property, an inverse-functional property,
and a class-scoped maximum-one restriction. The functional-property part is:

```text
ObjectProperty(ex:hasPrimaryContact Functional)
Individual(ex:office
  value(ex:hasPrimaryContact ex:anna)
  value(ex:hasPrimaryContact ex:annaAlias))
Individual(ex:anna type(ex:Composer))
```

DLP Nova infers that `anna` and `annaAlias` denote the same individual, and both
names answer a query for `Composer`. It does not report a duplicate-value error
merely because the names differ. The full fixture also identifies `thirdName`
with Anna through their shared identifier and identifies Lea with `leaAlias`
through the scoped cardinality restriction.

```sh
uv run dlp instances examples/dlp_nova/base-l1.dlp \
  'https://example.org/nova#Composer' --profile L1
```

The result contains `anna`, `annaAlias` and `thirdName` as full IRIs. These are
three names for the same inferred individual, so the number of returned names
is not a count of distinct real-world entities.

### L2: consistency constraints

L2 adds denials: combinations of facts that cannot all hold. For example:

```text
DisjointClasses(ex:Person ex:Composition)
Class(ex:Childless partial restriction(ex:hasChild maxCardinality(0)))
Class(ex:InstrumentalWork partial complementOf(ex:VocalWork))
DifferentIndividuals(ex:anna ex:lea)
```

An individual belonging to both `Person` and `Composition` violates the first
axiom. A child edge from a known `Childless` individual violates the second.
Membership in both `InstrumentalWork` and `VocalWork` violates the third.
The final axiom prohibits identifying Anna and Lea.

The [base-l2.dlp](../examples/dlp_nova/base-l2.dlp) fixture is consistent. The
[base-l2-inconsistent.dlp](../examples/dlp_nova/base-l2-inconsistent.dlp) fixture
adds both Anna and Lea as primary contacts of a functional property while
requiring them to be different. It is deliberately inconsistent:

```sh
uv run dlp validate examples/dlp_nova/base-l2.dlp --profile L2
# Expected exit code 2 for the next command:
uv run dlp validate examples/dlp_nova/base-l2-inconsistent.dlp --profile L2
```

Inspect `consistency` and `violations` in the JSON response. Ordinary queries
are guarded when an ontology is inconsistent. Constraints detect logical
conflicts; they do not turn a missing assertion into a negative fact.

### L3: existential witnesses

The complete [base-l3.dlp](../examples/dlp_nova/base-l3.dlp) example is:

```dlp
Namespace(ex = <https://example.org/nova#>)
Ontology(
  Class(ex:Parent partial restriction(ex:hasChild someValuesFrom(ex:Person)))
  Class(ex:PairOwner partial restriction(ex:hasPart minCardinality(2)))
  Individual(ex:anna type(ex:Parent))
  Individual(ex:kit type(ex:PairOwner))
)
```

The reasoner creates an anonymous child of Anna and two explicitly different
parts of the kit. These are internal witnesses for required existence, not
newly discovered named people or parts. Repeated applications of the same
normalized restriction reuse its witness for the same subject.

Ordinary instance and value queries hide generated witnesses. Request them
explicitly in Python:

```python
from rdflib import Namespace, OWL, RDF
from dlp_reasoner import Reasoner

ex = Namespace("https://example.org/nova#")
r = Reasoner.from_file("examples/dlp_nova/base-l3.dlp", profile="L3")
assert r.complete and r.consistency == "consistent"
assert r.property_values(ex.anna, ex.hasChild) == set()

child, = r.property_values(ex.anna, ex.hasChild, include_witnesses=True)
assert r.entails(child, RDF.type, ex.Person)
parts = r.property_values(ex.kit, ex.hasPart, include_witnesses=True)
assert len(parts) == 2
left, right = parts
assert r.entails(left, OWL.differentFrom, right)
```

The empty default result here means that no named or source-anonymous child is
returned; it does not mean that no child exists. Anonymous individuals explicitly
written into the source are distinct from generated witnesses and are retained
by ordinary queries.

Recursive existence requirements need care. This valid L3 document can generate
an unbounded chain:

```dlp
Namespace(ex = <https://example.org/nova#>)
Ontology(
  Class(ex:A partial restriction(ex:next someValuesFrom(ex:A)))
  Individual(ex:a type(ex:A))
)
```

The evaluator uses bounds instead of claiming that an arbitrary finite prefix
is complete. The default CLI limits are 1,000 rounds, 1,000,000 facts and
witness depth 32; adjust them using `--max-rounds`, `--max-facts` and
`--max-depth`. Reaching a limit produces `complete: false` and usually
`consistency: "unknown"` unless an inconsistency has already been established.
Increasing a bound does not guarantee termination.

### Normalization before profile checks

The compiler simplifies descriptions before checking their profile. For
example, double complement becomes its underlying description; minimum zero
becomes `owl:Thing`; an existential with a singleton nominal filler becomes a
has-value restriction. Empty intersection denotes top and empty union denotes
bottom. `Class(ex:Universal complete)` therefore defines top and needs L1;
`Class(ex:Universal partial)` only declares a class.

Some expressions that look disjunctive normalize to Horn implications. At L2:

```text
SubClassOf(ex:A unionOf(complementOf(ex:B) ex:C))
```

compiles to the implication “A and B imply C.” This does not add support for a
general positive union consequent. Use direct, clearly legal forms where
possible; let `validate` decide nontrivial nested cases.

## Property axioms and local scope

Object-property declarations can combine the following components:

| Component | Consequence |
| --- | --- |
| `super(ex:q)` | Every `p(x,y)` also gives `q(x,y)`. |
| `inverseOf(ex:q)` | `p(x,y)` and `q(y,x)` imply one another. |
| `Symmetric` | `p(x,y)` gives `p(y,x)`. |
| `Transitive` | `p(x,y)` together with `p(y,z)` gives `p(x,z)`. |
| `domain(ex:C)` | A p edge classifies its subject as C. |
| `range(ex:C)` | A p edge classifies its object as C. |
| `Functional` | Two p objects for the same subject are equal; L1. |
| `InverseFunctional` | Two p subjects for the same object are equal; L1. |

`SubPropertyOf(ex:p ex:q)` and `EquivalentProperties(ex:p ex:q ...)` provide
standalone hierarchy and equivalence axioms. A domain or range is an inference
rule, not a check that a type assertion was written in advance. Combining
characteristics is accepted by the DLP compiler; this alone does not establish
membership in a W3C OWL profile with its additional global restrictions.

`localdomain` and `localrange` inside a partial class declaration have a more
specific scope. The runnable
[base-local-scope.dlp](../examples/dlp_nova/base-local-scope.dlp) contains:

```dlp
Namespace(ex = <https://example.org/nova#>)
Ontology(
  Class(ex:Student partial
    localdomain(ex:teaches ex:Teacher)
    localrange(ex:enrolledAt ex:School))
  Individual(ex:lea type(ex:Student) value(ex:enrolledAt ex:academy))
  Individual(ex:anna value(ex:teaches ex:lea))
  Individual(ex:other value(ex:teaches ex:unknown))
)
```

Anna becomes a teacher because she teaches a student. Lea's academy becomes
a school because it is an `enrolledAt` filler of a student. `other` does not
become a teacher just because a `teaches` edge exists: its filler is not known
to be a student. In particular, the class being declared constrains the
**filler** of `localdomain`, not the subject.

The exact expansions are:

```text
// Class(ex:A partial localdomain(ex:P ex:D))
SubClassOf(restriction(ex:P someValuesFrom(ex:A)) ex:D)

// Class(ex:A partial localrange(ex:P ex:R))
SubClassOf(ex:A restriction(ex:P allValuesFrom(ex:R)))
```

These convenience forms are only accepted inside `partial` class declarations.

## Individuals, equality and open-world answers

An individual can have multiple types and values, and repeated declarations
add assertions about the same name:

```text
Individual(ex:anna type(ex:Composer) type(ex:Teacher)
  value(ex:hasChild ex:lea) value(ex:hasChild ex:max))
Individual(ex:anna value(ex:worksAt ex:academy))
```

Omitting the name creates a source-anonymous individual. Such an individual
can also be nested as an object value:

```text
Individual(ex:anna
  value(ex:hasChild Individual(type(ex:Person))))
```

Use `SameIndividual(ex:anna ex:annaAlias)` for explicit equality and
`DifferentIndividuals(ex:anna ex:lea ex:max)` for pairwise inequality. Each
requires at least two names. Equality propagates through individual positions
in classes and properties. It does not rename class or property predicates
merely because they happen to share an IRI with an individual.

DLP Nova follows an **open-world interpretation without a unique-name
assumption**:

* An absent `hasChild` edge does not establish `Childless`.
* A different spelling of an IRI does not establish different individuals.
* A functional property with two fillers ordinarily establishes their equality.
* A universal restriction constrains all fillers; it does not require any.
* A negative query answer means “not entailed,” not “known to be false.”

Use explicit difference when distinct identity is part of the ontology, and
explicit completeness/scoping in extension queries when computing over a
complete finite dataset. `complete` class definitions cannot supply that
dataset guarantee.

## Literals and datatype properties

The runnable [base-literals.dlp](../examples/dlp_nova/base-literals.dlp)
illustrates the supported boundary:

```dlp
Namespace(ex = <https://example.org/nova#>)
Ontology(
  DatatypeProperty(ex:name domain(ex:Person))
  DatatypeProperty(ex:year)
  DatatypeProperty(ex:birthDate)
  Class(ex:BornIn1685 complete restriction(ex:year value("1685"^^xsd:integer)))
  Individual(ex:bach
    annotation(rdfs:label "Johann Sebastian Bach"@en)
    value(ex:name "Johann Sebastian Bach")
    value(ex:year "01685"^^xsd:integer)
    value(ex:birthDate "1685-03-31"^^xsd:date))
)
```

Bach is inferred to be a person through the domain and a `BornIn1685` instance
through the integer value identity. The stored date can later be consumed by
temporal built-ins, but a date literal in `.dlp` does not itself invoke temporal
reasoning.

Ontology value identity covers well-typed plain/language strings, `xsd:string`,
the supported integer/decimal family, and booleans. For example,
`"01685"^^xsd:integer` and `"1685"^^xsd:integer` denote the same supported numeric
value. A forced equality between incompatible values in the supported families
can establish inconsistency. Other literal datatypes are opaque RDF terms for
base ontology entailment; full OWL datatype identity and incompatibility are
not decided for them.

Keep these restrictions in mind when authoring datatype properties:

* Explicit `ObjectProperty` values must be individuals; explicit
  `DatatypeProperty` values must be literals.
* `DatatypeProperty` accepts `Functional`, `super(...)`, `domain(...)` and
  annotations. Its `range(...)` is rejected because datatype-range reasoning
  is unsupported.
* Declared datatype properties cannot use `someValuesFrom` or `allValuesFrom`,
  or positive minimum/exact cardinalities. DLP Nova does not construct literal
  witnesses.
* Literal facts, literal has-value restrictions and supported maximum/zero
  cardinalities remain available. Functionality requires L1, maximum zero L2.
* Datatype facets, datatype definitions, literal enumerations and complete
  OWL datatype entailment are unsupported. A `Datatype(ex:T)` declaration
  records a datatype; it does not enable reasoning over its value range.

Use the separate checked operations in the
[extensions guide](DLP_NOVA_EXTENSIONS.md) for arithmetic, dates, instants,
durations and geometry. Their runtime type checking does not broaden the
ontology compiler's datatype semantics.

## Querying a base ontology

CLI query arguments are **full IRIs**, even if the input uses prefixes. The
commands return JSON; set-valued results are sorted strings.

| Command after `dlp` | Question |
| --- | --- |
| `instances FILE CLASS_IRI` | Which known individuals belong to the class? |
| `types FILE INDIVIDUAL_IRI` | Which classes does this individual belong to? |
| `values FILE SUBJECT_IRI PROPERTY_IRI` | Which values fill the property for this subject? |
| `entails FILE SUBJECT_IRI PROPERTY_IRI OBJECT_IRI` | Is this IRI-valued assertion entailed? |
| `subsumes FILE SUPERCLASS_IRI SUBCLASS_IRI` | Is the second class a subclass of the first? |
| `equivalent-classes FILE LEFT_IRI RIGHT_IRI` | Are the classes equivalent? |
| `property-subsumes FILE SUPERPROPERTY_IRI SUBPROPERTY_IRI` | Is the second property a subproperty of the first? |
| `equivalent-properties FILE LEFT_IRI RIGHT_IRI` | Are the properties equivalent? |
| `inverse-properties FILE LEFT_IRI RIGHT_IRI` | Are the properties inverses? |
| `is-symmetric FILE PROPERTY_IRI` | Is symmetry entailed? |
| `is-transitive FILE PROPERTY_IRI` | Is transitivity entailed? |
| `has-domain FILE PROPERTY_IRI CLASS_IRI` | Is the class a domain consequence? |
| `has-range FILE PROPERTY_IRI CLASS_IRI` | Is the class a range consequence? |

Use RDFLib terms in Python for literals, source blank nodes and compound
expression queries. A reusable base session looks like this:

```python
from rdflib import Literal, Namespace, RDF, XSD
from dlp_reasoner import Reasoner

ex = Namespace("https://example.org/nova#")
r = Reasoner.from_file("examples/dlp_nova/base-l0.dlp", profile="L0")
assert r.instances(ex.Person) == {ex.anna, ex.lea, ex.max}
assert r.entails(ex.anna, RDF.type, ex.KnownParent)
assert r.subsumes(ex.Person, ex.Composer)  # superclass first
assert r.property_values(ex.anna, ex.ancestorOf) == {ex.lea, ex.max}
assert (ex.anna, ex.max) in r.property_pairs(ex.ancestorOf)
assert r.is_satisfiable(ex.Composer)

literal_reasoner = Reasoner.from_file(
    "examples/dlp_nova/base-literals.dlp", profile="L0")
assert literal_reasoner.entails(
    ex.bach, ex.year, Literal("1685", datatype=XSD.integer))
```

The CLI `entails` object argument is always an IRI; use the Python method for
literal entailments as above. The CLI instance/value commands do not expose an
`--include-witnesses` flag. Use Python for those queries, or
`dlp materialize ... --include-witnesses` for an RDF export containing witnesses.

Instance queries for compound descriptions use expressions valid on the left
of an inclusion: conjunctions, unions, nominals, existential joins and
has-value restrictions, subject to the selected profile. The API accepts an
RDF blank node identifying such an expression in its source graph. It does
not offer arbitrary negated, universal or maximum-cardinality membership
queries by treating missing facts as evidence. For a reusable positive query
pattern, a legal `complete` named class such as `KnownParent` in the first
example is convenient. Multi-relation query rules and parameterized computations
belong to `.dlq`.

## Validation and troubleshooting

Parsing, profile validation, materialization and querying are separate stages:

1. `parse_dlp(text, source="example.dlp")` builds an RDF graph and checks the
   concrete syntax and explicit declaration restrictions.
2. `compile_graph(graph, profile="L0")` checks supported logical forms and
   constructor positions and produces a Horn program.
3. `Reasoner(graph, profile="L0")` compiles and materializes; inspect `complete`,
   `consistency` and `stats`.
4. Ordinary retrieval queries require a complete, consistent result.

A successful parse alone does not establish profile membership or consistency.
Use `dlp validate` to check both logical acceptance and execution status.
`dlp rules` prints the compiled Horn representation for inspection; that output
is not `.dlp` input syntax, and the command's successful exit is not a
replacement for checking `validate` status.

| Symptom | Meaning and action |
| --- | --- |
| `DLPParseError` with file, line and column | Fix the concrete syntax at that location: a missing parenthesis, unknown prefix/keyword or misplaced declaration component. |
| `requires L1`, `requires L2` or `requires L3` | The selected profile is too low for an encountered form. Raise it if that logical feature is intended. |
| `Union on the right ... is not Horn-expressible` | A general positive disjunction would be required. Raising the profile cannot enable it; reconsider the intended axiom. |
| `all class expression is unsupported on the left` | A general universal restriction appears in an antecedent, often through the reverse direction of equivalence. Use only an intended legal implication. |
| `Maximum cardinality above one is not Horn-expressible` | Maximum/exact values above one are outside all four supported profiles. |
| `Datatype range reasoning is unsupported` | Remove the unsupported datarange axiom and model the intended checked computation with an extension operation if appropriate. |
| `ObjectProperty ... requires an individual value` / `DatatypeProperty ... requires a literal value` | The value conflicts with an explicit property declaration, including one later in the document. |
| `complete: false` | Reasoning did not finish within its bounds. Inspect the limit/failure information; do not use absence as non-entailment. |
| `consistency: "inconsistent"` | Inspect `violations` and the responsible assertions/axioms. Ordinary queries cannot supply meaningful classical answers for the inconsistent ontology. |
| Empty value result for an L3 property | A filler may be a generated witness; use `include_witnesses=True` to inspect it. |

For `validate`, exit codes are **0** for complete and consistent, **1** for
invalid input or an execution error, **2** for inconsistency, and **3** for
incomplete reasoning. Syntax/profile errors use JSON diagnostics on stderr;
validation status is JSON on stdout. Python raises `DLPParseError` or
`ProfileError` for invalid input, `IncompleteReasoningError` for a guarded
incomplete answer and `InconsistentOntologyError` for an ordinary query over
an inconsistent ontology.

The Python `entails` method can return a proven positive fact from some
resource-limited runs. It does not return an unsupported negative answer from
an incomplete closure. Retrieval methods, schema queries and exports require
completion. A recorded evaluation failure is guarded even for positive
entailment checks.

Unsupported constructs also include property chains, keys, general qualified
number restrictions and automatic imports. The L0–L3 names refer to the
thesis-derived fragments implemented here; acceptance is not a certificate of
OWL 2 RL or OWL 2 DL conformance.

## Runnable example index and implementation references

| Example | Profile | Expected result |
| --- | --- | --- |
| [base-l0.dlp](../examples/dlp_nova/base-l0.dlp) | L0 | Person hierarchy, known-parent recognition and transitive ancestors. |
| [base-local-scope.dlp](../examples/dlp_nova/base-local-scope.dlp) | L0 | Anna is a teacher; the academy is a school; unrelated edges do not gain the local domain. |
| [base-literals.dlp](../examples/dlp_nova/base-literals.dlp) | L0 | Bach is a person born in 1685; integer lexical variants share a value. |
| [base-l1.dlp](../examples/dlp_nova/base-l1.dlp) | L1 | Functionality, inverse functionality, scoped maximum one and nominal membership. |
| [base-l2.dlp](../examples/dlp_nova/base-l2.dlp) | L2 | Complete, consistent ontology with explicit constraints and inequality. |
| [base-l2-inconsistent.dlp](../examples/dlp_nova/base-l2-inconsistent.dlp) | L2 | Deliberate equality/inequality conflict; validation exit code 2. |
| [base-l3.dlp](../examples/dlp_nova/base-l3.dlp) | L3 | One child witness and two pairwise-different part witnesses. |

The examples and asserted answers were checked against both the Python and
native relation/index backends. The recursive L3 example was separately
checked with a depth limit to verify that it reports an incomplete result.

For exact implementation behavior, see the [concrete parser](../src/dlp_reasoner/parser.py),
[profile compiler](../src/dlp_reasoner/compiler.py),
[Reasoner API](../src/dlp_reasoner/reasoner.py) and
[CLI](../src/dlp_reasoner/cli.py). The [parser tests](../tests/test_dlp_parser.py)
exercise declaration order, expression positions, property kinds, local scope
and located diagnostics. The [thesis mapping](THESIS_SPEC.md),
[syntax compatibility notes](DLP_SYNTAX.md) and
[profile assessment](DLP_PROFILE_ASSESSMENT.md) explain the historical basis,
the Chapter 5 forms added to the printed Appendix A grammar, and the
relationship to later OWL profiles.
