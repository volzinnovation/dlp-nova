# Bach benchmark

The Bach benchmark parses and reasons over two examples from Raphael Volz's [*Web Ontology Reasoning with Logic Databases*](Volltext.pdf). It preserves the explicit source assertions and checks complete expected query answers. References below use printed page numbers; add 16 for the one-based PDF page.

| Artifact | Source and role | DLP profile |
| --- | --- | --- |
| [bach.dlp](../examples/bach.dlp) | Table 2.5 in Appendix A concrete syntax, with Chapter 5's L3 forms | L3 |
| [bach.ttl](../examples/bach.ttl) | Table 2.5, p. 35: T1–T17 and A1–A15, with source labels in comments | L3 |
| [bach.owl](../examples/bach.owl) | The same ontology in RDF/XML | L3 |
| [bach-family.ttl](../examples/bach-family.ttl) | Figure 6.2, p. 150; Table 6.1, p. 151; initial assertions in Example 6.3.2, p. 158 | L0 |
| [bach-family.dlp](../examples/bach-family.dlp) | The same independent chapter 6 example in concrete DLP syntax | L0 |
| [bach-queries.json](../examples/bach-queries.json) | Executable query definitions, expected answers, and source references | Per example |

The shared namespace is `http://www.jsbach.org/bach#`, following Example 3.2.1, pp. 46–47. Individual names use readable local names such as `johann-sebastian`. The two ontologies are separate inputs: the chapter 6 example includes genealogy that Table 2.5 does not assert. Table 2.5's A16 is an ellipsis, not additional data.

Regenerate the RDF/XML equivalent with `uv run python scripts/generate_bach_owl.py`.
The generator canonicalizes blank nodes, sorts serialization traversal and checks graph
equivalence before writing the output.

## OWL syntax and DLP scope

Section 5.1.5, p. 119, explicitly permits RDF exchange using the OWL abstract-syntax mapping. The examples therefore use OWL class expressions and property axioms in Turtle and RDF/XML, parsed with RDFLib and compiled to the reasoner's position-sensitive DLP profiles. The `rules` command exposes the resulting Horn program.

The complete Table 2.5 example requires L3 (§5.1.4, p. 118): necessary existential restrictions occur in T3–T6, T12, T14, T15 and A1. Negation in T2 and T15 becomes an integrity constraint. Appendix A, pp. 233–235, describes its grammar as L3, but its literal productions omit existential forms allowed by §5.1.4. The [concrete DLP parser](DLP_SYNTAX.md) accepts these Chapter 5 forms and lowers them to the same compiler as the RDF input. Tests check equivalent axioms and materializations for the `.dlp` and RDF examples. Historical benchmark cases continue reading their original RDF fixtures and retain their original parsing measurement boundaries.

| Table 2.5 axioms | Encoding |
| --- | --- |
| T1–T2 | `Woman ⊑ Person`; `Man ⊑ Person ⊓ ¬Woman` |
| T3–T4 | `Wife ⊑ Woman ⊓ ∃marriedTo.Husband`; `Husband ⊑ Man ⊓ ∃marriedTo.Wife` |
| T5–T6 | `Father ≡ Man ⊓ ∃hasChild.Person`; `Mother ≡ Woman ⊓ ∃hasChild.Person` |
| T7–T9 | `hasChild ⊑ ancestorOf`; transitive `ancestorOf`; symmetric `marriedTo` |
| T10 | `∃livesIn.{leipzig} ⊑ LeipzigInhabitant`, encoded with `owl:hasValue` |
| T11 | `Genius ⊓ Composer ⊑ ∀hasComposed.Masterpiece` |
| T12 | `BirthdayCantata ⊑ (∃forEvent.Birthday) ⊓ Cantata ⊓ Homage` |
| T13 | `Cantata ⊑ VocalComposition ⊓ InstrumentalComposition` |
| T14–T15 | `VocalComposition ⊑ Composition ⊓ ∃forInstrument.Voice`; `InstrumentalComposition ⊑ Composition ⊓ ∃forInstrument.¬Voice` |
| T16–T17 | Symmetric `inDynasty`; `ancestorOf ⊑ inDynasty` |

T12 uses explicit parentheses to resolve the displayed formula's loose scope. A1 preserves Johann Ambrosius's existentially specified child, and A2 preserves Johann Sebastian's conjunction assertion. A3–A15 supply the named people, marriages, Leipzig residence, composition relation and cantata memberships printed in the table.

The supplied ABox reaches a finite materialization. A fresh `Wife` or `Husband` assertion, including one introduced by a satisfiability probe, can activate an unbounded mutual existential chain. Successful benchmark queries establish results for these inputs and terminating probes; they do not establish a decision procedure for all L3 ontologies.

## Parse and query

Run from the repository root:

```sh
uv run dlp validate examples/bach.dlp --profile L3
uv run dlp validate examples/bach.owl --format xml --profile L3
uv run dlp rules examples/bach.dlp --profile L3
uv run dlp instances examples/bach.dlp 'http://www.jsbach.org/bach#Father' --profile L3
uv run dlp values examples/bach.dlp 'http://www.jsbach.org/bach#johann-sebastian' 'http://www.jsbach.org/bach#marriedTo' --profile L3
uv run dlp subsumes examples/bach.dlp 'http://www.jsbach.org/bach#Person' 'http://www.jsbach.org/bach#Father' --profile L3
uv run dlp values examples/bach-family.dlp 'http://www.jsbach.org/bach#johannes' 'http://www.jsbach.org/bach#ancestorOf' --profile L0
```

The full ontology returns both `johann-ambrosius` and `johann-sebastian` as named Fathers, both `anna-magdalena` and `maria-barbara` as Johann Sebastian's spouses, and `true` for Person subsuming Father (Example 2.4.3, p. 39). Queries follow the class retrieval, type retrieval, property-filler and schema questions in §5.4, pp. 130–140. Named-answer expectations exclude generated witnesses; existential queries can still use those witnesses internally.

The answer checks preserve open-world distinctions. A1 does not identify Johann Ambrosius's anonymous child with Johann Sebastian. The marriages do not imply `Wife` or `Husband` membership, because T3 and T4 are one-way necessary conditions. An absent entailment is not an asserted negation. The introductory question about lyrics reused in the Christmas Oratorio cannot be answered from Table 2.5 alone: it supplies no lyric or reuse assertions, and the benchmark adds none.

## Maintenance example

The L0 input has exactly the two logical axioms from Table 6.1: transitive `ancestorOf`, with `ancestorOf ⊑ inDynasty`. Its nine asserted edges are:

```text
j→h, j→c, h→jc1, jc1→jm, jm→mb, mb→wf, js→wf, ja→js, c→ja
```

Here `j` is Johannes, `h` Heinrich, `c` Christoph, `jc1` Johann Christoph, `jm` Johann Michael, `mb` Maria Barbara, `wf` Wilhelm Friedemann, `js` Johann Sebastian, and `ja` Johann Ambrosius. These are `ancestorOf` assertions, as specified in chapter 6, with no additional parent or gender assertions. Initially each of `ancestorOf` and `inDynasty` contains 24 ordered pairs.

The fact transaction from Example 6.3.2, pp. 158–159, removes `(js,wf)` and inserts `(js,jc2)`, where `jc2` is Johann Christian. Its complete ancestor delta removes `(js,wf)`, `(ja,wf)`, `(c,wf)` and adds `(js,jc2)`, `(ja,jc2)`, `(c,jc2)`, `(j,jc2)`. Johannes remains an ancestor of Wilhelm Friedemann through the maternal branch. The resulting ancestor relation has 25 pairs. The printed insertion `(jc,jc2)` on p. 159 is resolved to `(js,jc2)` by the preceding prose and the displayed output deltas.

The fact transaction and both rule scenarios each start from the original family graph. One rule scenario removes the subproperty axiom, emptying `inDynasty`. The other adds symmetry of `inDynasty`, producing reversed ancestor pairs. In particular, `(jc1,j)` follows, while the cross-branch pair `(jc1,c)` still does not. The thesis's claim that symmetry entails the latter pair is corrected in [THESIS_ERRATA.md](THESIS_ERRATA.md#6-symmetry-alone-does-not-justify-the-bach-family-examples-new-pair).

## Measurement and validation

```sh
uv run python -m benchmarks.run --suite bach --repeats 5 \
  --output benchmarks/bach-results.json
```

The Bach suite contains three cases: the complete ontology parsed from Turtle, the same ontology parsed from RDF/XML, and the L0 family maintenance example. These cases are also included in the quick and thesis suites. [Raw results](../benchmarks/bach-results.json) and the [generated report](../benchmarks/bach-results.md) retain the measured samples and validation outcome.

The pinned historical benchmark has no Bach cases. To compare later implementations against
this run, save the current JSON report and pass its path with `--baseline`, using a different
`--output` path. Bach comparisons require unchanged source-document bytes and query-manifest
hashes, and check the full recorded query answers and family pair sets across repetitions.

The parser receives the actual serialized input bytes; file reading is outside the timed phase. Parsing, compilation and materialization are timed separately. The manifest contains 25 full-ontology queries and seven family queries. Every query is checked against its complete expected answer set or expected Boolean value, with timings retained individually. The summary query time sums all queries per repetition. Complex expression queries include expression parsing, temporary compilation and materialization. Each RDF maintenance transaction is checked against both independent graph reachability and a fresh reasoner on the updated ontology. RDF update and fresh reconstruction timings both include compilation. Fresh reconstruction provides a comparison for incremental maintenance, while reachability independently checks the intended genealogy semantics. See [benchmark methodology](../benchmarks/README.md) for repetition, timing, timeout and machine metadata conventions.

This is a reproducible benchmark built from the thesis's worked examples, with modern implementation measurements. It does not reconstruct historical KAON timings.
