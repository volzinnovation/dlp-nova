# Thesis-derived specification

The source is Raphael Volz, *Web Ontology Reasoning with Logic Databases* (2004), [Volltext.pdf](Volltext.pdf). This document records the semantic target and validation obligations, rather than claiming that every possible OWL ontology is supported. The thesis studies Description Logic Programs (DLP), a family of four fragments of OWL, and a database implementation of their reasoning problems.

Page numbers below are the printed thesis page numbers. For chapters 1 onward, add 16 to obtain the one-based PDF page number; for example, printed page 120 is PDF page 136. The PDF has been text-extracted and the problematic property translation table on printed page 122 has also been visually checked.

## Required architecture and source mapping

| Concern | Thesis source | Engineering consequence |
| --- | --- | --- |
| Normalize expressions before determining the fragment | Section 4.3, Tables 4.1-4.2, pp. 83-87 | Simplify and normalize constructors, preserving classical semantics; a superficially unsupported expression can normalize into DLP. |
| Define four fragments by constructor position | Definitions 5.1.1-5.1.24, pp. 115-118; Figure 5.1 | Validate left and right positions recursively. A feature list alone is insufficient. |
| Compile ontology axioms into logic rules | Tables 5.1-5.3, pp. 116, 120, 122; Table 7.1, p. 184 | Translate classes to unary predicates and properties to binary predicates, preserving variable scopes. |
| Use first-order semantics as normative | Definition 5.2.1 and Remark 5.2.1, p. 123 | No unique-name assumption, and no closed-world negative inference. |
| Support ABox and TBox reasoning | Section 5.4, pp. 130-141 | Expose instance checking/retrieval, property fillers, consistency, and fresh-individual tests for supported TBox queries. |
| Keep asserted data separate from derived facts | Section 6.2.3, p. 152 | Removing an assertion must not remove its independent inferred support, or turn prior inferences into assertions. |
| Maintain changing facts | Section 6.3, pp. 152-158; Table 6.2, p. 156 | Implement delete-and-rederive semantics and insertion propagation, with full recomputation as an independently checked reference. |
| Maintain changing rules | Section 6.4, pp. 159-165; Table 6.3, p. 160; Algorithms 6.1-6.2, pp. 163-164 | Both TBox insertion and removal must refresh directly affected predicates and their dependents. |
| Handle equality explicitly | Section 7.4.4.1, p. 186; Section 8.5.2, pp. 215-218 | Equality must propagate through every individual position, including conclusions of functionality. |
| Report benchmark evidence | Chapter 8, pp. 193-223; especially Tables 8.4-8.13 | Measure query, initial inference, equality, existentials, and updates separately on deterministic, parameterized inputs. |

The historical implementation uses Java, an OWL API, KAON, XSB and Racer (chapter 7). These are implementation choices rather than semantic requirements. A modern RDF parser and an indexed rules engine can serve the same architecture. Generic OWL RL closure alone does not reproduce the four DLP languages, particularly the L3 existential rules.

## Language matrix

`L` and `R` below mean the left and right sides of a class inclusion `C ⊑ D`. Class equivalence expands into two inclusions, so both directions must be supported. Filler expressions must themselves be valid for their position; the matrix is not permission to nest every constructor arbitrarily.

| Constructor or axiom | First language | Allowed position and translation |
| --- | --- | --- |
| Atomic class | L0 | L and R: `A(x)` |
| Intersection `C ⊓ D` | L0 | L: join; R: split the consequent into separate rules |
| Has-value `∃R.{a}` | L0 | L and R: `R(x,a)` |
| Union `C ⊔ D` | L0 | L only: split antecedent alternatives |
| Existential `∃R.C` | L0 | L: `R(x,y) ∧ C(y)`, with a fresh variable `y` |
| Universal `∀R.C` | L0 | R: move `R(x,y)` into the antecedent and apply the consequent to `y` |
| Property inclusion, equivalence, inverse, symmetry and transitivity | L0 | Binary rules; inverses reverse the arguments; transitivity composes two edges |
| Property domain and range | L0 | `C(x) ← R(x,y)` and `C(y) ← R(x,y)`; their implicit top antecedent is eliminated |
| Individual equality; functionality and inverse functionality | L1 | Equality in facts or rule heads; functionality merges fillers, inverse functionality merges subjects |
| Singleton nominal `{a}` | L1 | L and R: equality with `a` |
| Enumeration `{a1,…,an}` | L1 | L: a disjunction of equalities; R permits only the singleton case |
| Top `⊤` and minimum cardinality zero | L1 | L and R; `≥0 R` normalizes to top |
| Minimum cardinality one | L1 | L: normalizes to `∃R.⊤` |
| Maximum cardinality one | L1 | R: `y=z ← C(x), R(x,y), R(x,z)` |
| Atomic complement `¬A` | L2 | R: denial `← C(x), A(x)`; does not mean failure to find `A(x)` |
| Bottom `⊥` | L2 | R: denial of its antecedent |
| Maximum cardinality zero | L2 | R: normalizes to `∀R.⊥`, disallowing any filler for a restricted individual |
| Individual inequality | L2 | Symmetric, incompatible with equality, and irreflexive |
| Existential `∃R.C` | L3 | R as well as L: introduce a Skolem witness for the subject and normalized restriction; identical restrictions share witnesses |
| Minimum cardinality one | L3 | R as well as L: existential witness |
| Minimum cardinality `n>1` | L3 | R: `n` witnesses with pairwise explicit inequalities |

DLP does not support positive union on the right, universal restrictions on the left, general maximum cardinalities above one, or general qualified number restrictions from later OWL editions. A richer surface syntax is allowed only when normalization reduces it to a supported expression (Remark 5.1.2, p. 117). A profile error must identify the offending axiom or constructor; silently dropping it changes the knowledge base.

The core language for equivalence is more restrictive than either inclusion position separately. For example, an equivalence to a general union cannot be compiled merely because a union is legal on the left of an inclusion.

## Semantic details that affect correctness

### Scope and joins

Every existential or universal occurrence introduces a fresh variable. In

```text
A ⊓ ∃R.C ⊑ B ⊓ ∀P.D
```

the rules are

```text
B(x) ← A(x), R(x,y), C(y)
D(z) ← A(x), R(x,y), C(y), P(x,z)
```

The variables `y` and `z` are independent (Example 5.2.1, p. 121). Nested expression compilation must not accidentally reuse either variable or attach a filler condition to the subject.

Normalization is relevant to both correctness and complexity. Section 4.3 assigns fresh predicates to structured expressions. This avoids unnecessarily large rule bodies and expansion of nested conjunctions of unions. The thesis's data-complexity result `O(|ABox|^4)` (Corollary 5.5.1, p. 142) assumes a structurally transformed program with at most three variables per rule. It should not be presented as a measured scaling law, a combined-complexity guarantee, or a proof for an implementation that flattens arbitrary expressions without that transformation.

### Open-world reasoning and equality

Failure to derive a positive assertion means *not entailed*, not that the assertion is false. In particular, the absence of additional property fillers does not establish a maximum-cardinality or universal restriction (Section 5.4.2, pp. 130-132).

Different IRIs may identify one individual. `owl:sameAs`, a singleton nominal consequent, functionality and maximum cardinality one can all establish equality. Equality is reflexive, symmetric, transitive and substitutive in all individual argument positions. Two fillers are not a functionality violation unless their equality conflicts with explicit inequality or incompatible literal values. Class and property IRIs are predicate identifiers in the DL interpretation; individual equality must not silently turn this into unrestricted OWL Full predicate rewriting.

A union-find representation is an appropriate modern optimization, provided querying returns relevant named aliases, joining uses canonical representatives, new equality triggers the required derivations, and updates can split a former equivalence class. A plain union-find structure cannot undo equality: retractions need reconstruction or a proven dynamic-equivalence method.

RDF terms and their datatype values require a stated policy. RDF parsing support does not by itself implement all OWL datatype semantics. The thesis's own benchmarks exclude datatype properties and datatype restrictions (p. 195). Any modern implementation must distinguish that benchmark limitation from its own supported literal entailments, and must reject unsupported semantic dataranges rather than claim full datatype completeness.

### Constraints and inconsistent input

A denial is checked against derived facts, not just explicit assertions. Thus disjointness inherited through a subclass chain or equality can make a knowledge base inconsistent. For example, from `A ⊑ ¬B`, `A(a)`, `B(b)`, and `a=b`, inconsistency follows.

Under the normative first-order semantics, an inconsistent knowledge base has no model and entails every statement (p. 125). A practical reasoner may instead report inconsistency and refuse ordinary entailment queries. It must document that operational policy rather than returning an apparently complete, ordinary set of entailments for inconsistent input.

The interpretation domain is nonempty even for an otherwise empty ABox. `⊤ ⊑ ⊥` is therefore inconsistent. Active-domain evaluation needs a fresh domain representative or an equivalent consistency test to avoid overlooking this case (p. 138).

### Existential witnesses and termination

RHS existentials use Skolem functions (Table 5.2, p. 120). This implementation identifies witnesses by the normalized restriction expression, subject, and witness index, sharing them across identical restrictions and reusing them across rounds. Witnesses must not be confused with named individuals. A newly created RDF blank node is an internal witness, not a globally known name. Minimum cardinality `n` also requires pairwise inequality, so maximum cardinality one together with minimum cardinality two produces inconsistency.

Unrestricted L3 evaluation may not terminate. `A ⊑ ∃R.A` plus `A(a)` can produce an unbounded Skolem chain. The thesis explicitly acknowledges nontermination and exponential paths even with blocking (Section 5.5.2, p. 143), and uses acyclic existential benchmarks (p. 218). Bounded execution must return an explicit incomplete/resource-limit result; it cannot advertise a finite prefix as a completed closure or use that prefix to prove non-entailment. Simply connecting a witness back to an ancestor is not a generally sound substitute for a blocking algorithm.

Chapter 6's incremental algorithm explicitly excludes nonconstant function symbols and therefore L3 (p. 165, footnote 5). Full recomputation for L3 updates is consistent with that stated boundary, provided limits remain visible.

## Reasoning operations and validation cases

The thesis's class instance queries use left-position expressions (pp. 130-134). Supported queries include atomic classes, conjunctions, unions, enumerations and existential joins. It explicitly excludes arbitrary negated, universal, and maximum-cardinality membership queries. An API may offer additional queries only with their own justified semantics.

Class subsumption uses a fresh prototypical individual: assert `C(a)`, check `D(a)`, then discard the trial state (p. 135). The asserted description must be valid on the right and the queried description on the left. Class satisfiability asserts a fresh individual and checks consistency (pp. 137-138). Property tests similarly assert fresh pairs or paths (pp. 138-140). Trial operations must not mutate the live ABox, union-find state, or materialization. Empty observed class extensions do not prove subsumption or disjointness.

A regression suite should exercise these independent semantic obligations:

1. Transitive subclass and subproperty propagation, inverse symmetry, domain and range, and property transitivity in their correct direction.
2. Conjunctive antecedents requiring *all* conjuncts; union antecedents accepting either branch; independent existential witnesses in multi-restriction expressions.
3. Universal consequences applied to existing and newly inferred edges, without generating an edge themselves.
4. Has-value recognition and production, finite nominal antecedents, singleton nominal equality, and equality substitutivity across both property argument positions.
5. Functionality and inverse functionality deriving equality, including equality that unlocks another rule or another equality.
6. Explicit inequality, disjointness, complement, bottom and maximum cardinality zero checked after closure, with no closed-world inference.
7. Consistency for an empty ABox under `⊤ ⊑ ⊥` and satisfiability/subsumption probes that leave live state unchanged.
8. Finite acyclic existential consequences, witness reuse, cardinality-distinct witnesses, and incomplete status on recursive existential limits.
9. Parsing RDF/XML, Turtle and N-Triples representations of the same supported ontology with semantically identical answers; malformed RDF lists and unsupported OWL constructs produce useful errors.
10. Deleting one of two independent supports preserves the consequence; deleting the last external support of a cycle removes the whole unsupported cycle.
11. An explicitly asserted fact that is also derivable retains the correct status after either support is removed.
12. Rule insertion and removal update downstream consequences; removing an equality-producing rule or assertion splits old aliases correctly.
13. After every update in seeded randomized update sequences, the maintained result matches fresh recomputation from the asserted facts and current rules.
14. Differential tests against an independent evaluator or external reasoner over the *shared fragment*. Compare semantic answers, not all RDF serialization or axiomatic triples indiscriminately.

## Incremental materialization

Chapter 6 separates extensional assertions from intensional results using bridge rules, such as `C_idb(x) ← C_edb(x)` (p. 152). A fact can be simultaneously asserted and entailed. The authoritative state must retain that distinction across insertions and deletions.

The three DRed stages (p. 153) are overdeletion, rederivation from surviving support, and insertion. Deletion propagates potential loss through old derivations; rederivation restores consequences that still have an external justification. Counting derivations alone is insufficient for recursion: after deleting `A(a)` from rules `B←A` and `A←B`, the two derived facts cannot justify one another forever.

For changed rules, the thesis recomputes extensions of predicates that appear in changed heads and propagates resulting deltas to other predicates (pp. 151-152 and 159-165). Its contribution includes both addition and removal of rules, not just fact updates. A dependency-aware implementation may use a different procedural representation, but the result must equal recomputation. Rebuilding everything is a correct baseline or fallback, although it should not be reported as incremental maintenance.

Updates involving equality are especially important: deleting a same-as assertion can remove an entire equivalence component and all of its propagated consequences. Public metrics should distinguish a targeted update from a fallback rebuild.

## Benchmark protocol

The thesis's old millisecond figures are historical context, not comparable performance targets: its host was a Pentium IV Mobile at 2 GHz, 512 MB RAM, Windows XP and Java 1.4.1 (p. 198). A new report should identify the actual CPU, operating system, runtime/dependency versions, timer, memory-measurement method, dataset seed, and repeat counts. All timed datasets must have correctness assertions independent of the algorithm under test.

### Baseline family from Section 8.4

Tables 8.4-8.7 (pp. 206-208) define a balanced ternary class taxonomy and three sizes:

| Name | Depth | Classes, including root | Individuals per non-root class | Total individuals |
| --- | ---: | ---: | --- | --- |
| TS | 3 | 40 | 3 / 9 / 15 | 117 / 351 / 585 |
| TM | 5 | 364 | 3 / 9 / 15 | 1,089 / 3,267 / 5,445 |
| TL | 7 | 3,280 | 3 / 9 / 15 | 9,837 / 29,511 / 49,185 |

For each taxonomy/ABox combination, the thesis uses P0 (no properties), P1 (one property per class, filled for every third individual), and PF (200 properties, one uniformly selected property filler per individual), yielding 27 configurations. It measures instance retrieval, property filler retrieval and class subsumption. Five repetitions use the same knowledge base but different query classes/properties; each historical test has a 30-minute timeout (p. 198).

A practical current run can include a compact matrix and a documented full mode. It must accurately name deviations from the original generator and avoid claiming that a shortened run reproduces all 405 historical tests.

### Expressivity from Section 8.5

Measure a taxonomy-only baseline, universal restrictions, equality-producing maximum-cardinality restrictions, and acyclic RHS existentials separately (pp. 213-219). The equality workload is essential because equality causes the major slowdown reported by the thesis. Use inferred equality, rather than only explicit same-as chains: several fillers subject to `≤1 R` trigger the equality rules.

The L3 setup on p. 218 places existential and minimum-cardinality restrictions on fresh properties/classes so the generated Skolem program terminates. A cyclic-existential limit test belongs in robustness validation, not in a successful finite-closure timing row.

### Maintenance from Section 8.6

The maintenance benchmark uses a balanced five-way taxonomy at depths 3, 4 and 5, with five individuals per class and fact-change ratios of 10% and 15% (pp. 220-221). There are respectively 156, 781 and 3,906 classes. Measure seven operations separately: query with fresh reasoning, materialization setup, rule removal, rule addition, fact removal, fact addition, and query against materialized data. Compare maintained closures with a fresh rebuild after every update.

For each implemented benchmark family, save machine-readable raw observations and a readable report. Report warm-up policy, separate parse/compile/materialize/query durations, median and spread, result counts and closure sizes. Memory and throughput are useful modern additions. State whether comparison timing includes parsing, ontology compilation, equality expansion, or result serialization. Never call a timed-out, partial, or mismatched run a successful speedup.

## Source ambiguities and errata handled deliberately

The intended DL/FOL semantics and correct formulations elsewhere in the thesis resolve several inconsistent formulas. Each correction needs specific evidence; p. 123 alone is not a blanket rule for changing the specification. The [detailed review](THESIS_ERRATA.md) records page references, counterexamples, procedural issues, and benchmark inconsistencies.

- Table 5.3 (p. 122, visually verified) prints the direction of property inclusion backwards and writes transitivity as decomposing an edge. Correct rules are `Q(x,y) ← P(x,y)` for `P ⊑ Q`, and `P(x,z) ← P(x,y), P(y,z)` for transitivity. Table 6.1 (p. 151) independently shows the correct directions.
- Table 7.1 (p. 184) repeats the left conjunct `C` where the second conjunct must be `D`. An implementation must require both conjuncts.
- Example 5.2.1's intermediate formula (p. 121) misplaces the atomic conclusion inside an implication, while the final two rules correctly distinguish its scope.
- The printed distributivity identity on p. 133 is malformed. The valid DNF identity is `F ∧ (G ∨ H) ≡ (F ∧ G) ∨ (F ∧ H)`. Example 5.4.2's nearby restriction scope is ambiguous because of missing parentheses; similar notation on p. 86 prevents treating its variable placement as a separately confirmed semantic error.
- Table 8.9 (p. 216) labels absolute max-one/min-zero counts inconsistently with the surrounding text and relative counts. The preceding construction says first and third subclasses receive max-one, so max-one appears twice as often as min-zero. A generator should follow that construction and record it explicitly.

The subsequent review also finds counterexamples to the combined equivalence probe (p. 136), inverse inheritance (Eq. 5.13, p. 140), and the printed rule-deletion maintenance algorithm (p. 163). The corrected implementation provides independent class-equivalence probes and semantic property-characteristic queries. It replaces the faulty rule-deletion procedure with old-rule overdeletion followed by current-rule rederivation; [CORRECTED_MAINTENANCE.md](CORRECTED_MAINTENANCE.md) gives the algorithm, eligibility conditions, and correctness argument. The report distinguishes these procedural defects from local formula slips and from errors in complexity parameters; it does not claim to refute the thesis's central fixed-TBox data-complexity result.
