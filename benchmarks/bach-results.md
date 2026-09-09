# Bach benchmark results

Run: 2026-09-09T17:07:00.273135+00:00. Python 3.12.9; macOS-26.5.1-arm64-arm-64bit.

Validated 3/3 cases; 0 errors; 5 repetitions per case. [Raw samples and source hashes](bach-results.json).

The full Table 2.5 ontology uses DLP L3; the chapter 6 family tree uses L0. Both ontologies are sourced from the thesis, with the documented corrections to the maintenance examples. These timings describe the current Python implementation.

## Parsing, compilation, materialization and queries

Times are medians in milliseconds. File reading and graph canonicalization are outside the measured phases. Query time sums every checked query in each repetition. Peak RSS includes the entire worker, inputs, queries and repetitions.

| Case | RDF triples | Closure facts | Parse ms | Compile ms | Materialize ms | Queries ms | Peak MiB |
|---|---:|---:|---:|---:|---:|---:|---:|
| Bach Table 2.5 (Turtle) | 164 | 99 | 2.254 | 2.624 | 1.497 | 43.718 | 43.0 |
| Bach Table 2.5 (RDF/XML) | 164 | 99 | 5.763 | 2.620 | 1.463 | 43.944 | 43.3 |
| Bach family maintenance (Turtle) | 25 | 58 | 0.758 | 0.351 | 0.582 | 3.547 | 37.0 |

## Family maintenance

Each scenario starts from the original 24 ancestor pairs. Updated results must match independent graph traversal and full fresh reconstruction. Both timings include compilation; the fact transaction ends with 25 ancestor pairs.

| Operation | RDF update ms | Fresh rebuild ms | Method |
|---|---:|---:|---|
| facts_update | 1.059 | 1.263 | dred |
| rule_delete | 0.747 | 0.978 | dred-rules |
| symmetry_insert | 0.903 | 1.441 | incremental-rules |

## Bach Table 2.5 (Turtle): checked queries

Source: `examples/bach.ttl`; profile L3. Parsing measures the original document syntax. Query ms in the summary is the total of all queries below.

| Query | Thesis reference | Answer | Median ms |
|---|---|---|---:|
| fathers | Table 2.5 T5/A1–A4/A7, p. 35; §5.4.2.2, p. 132 | `["johann-ambrosius", "johann-sebastian"]` | 0.029 |
| mothers | Table 2.5 T6, p. 35; §5.4.2.2, p. 132 | `[]` | 0.016 |
| people | Table 2.5 T1/T2/T5, p. 35; §5.4.2.2, p. 132 | `["anna-magdalena", "johann-ambrosius", "johann-sebastian", "maria-barbara", "wilhelm-friedemann"]` | 0.038 |
| masterpieces | Table 2.5 T11/A2/A9/A10, p. 35 | `["BWV248"]` | 0.017 |
| birthday-cantatas | Table 2.5 A14/A15, p. 35 | `["BWV213", "BWV214"]` | 0.017 |
| compositions | Table 2.5 T12–T15/A13–A15, p. 35 | `["BWV213", "BWV214", "BWV248"]` | 0.018 |
| named-birthdays | Table 2.5 T12/A14/A15, p. 35; Example 4.5.2, p. 94 | `[]` | 0.024 |
| leipzig-inhabitants | Table 2.5 T10/A8, p. 35 | `["johann-sebastian"]` | 0.016 |
| wives | Table 2.5 T3/A5/A6/A11/A12, p. 35 | `[]` | 0.014 |
| ambrosius-is-father | Table 2.5 T5/A1/A7, p. 35; §5.4.2.1, p. 132 | `true` | 0.018 |
| ambrosius-named-son-not-entailed | Table 2.5 A1, p. 35; Example 4.5.2, p. 94 | `false` | 0.012 |
| sebastian-known-children | Example 5.4.1, p. 131; §5.4.3, pp. 134–135 | `["wilhelm-friedemann"]` | 0.024 |
| sebastian-marriages | Table 2.5 A6/A12, p. 35; §5.4.3, pp. 134–135 | `["anna-magdalena", "maria-barbara"]` | 0.019 |
| symmetric-marriage | Table 2.5 T9/A6, p. 35; §5.4.3, pp. 134–135 | `["johann-sebastian"]` | 0.016 |
| sebastian-types | §5.4.2.3, p. 134; Table 2.5, p. 35 | `["Composer", "Father", "Genius", "LeipzigInhabitant", "Man", "Person", "owl:Thing"]` | 0.021 |
| male-child-existential | Example 4.5.2, p. 94; §5.4.2, pp. 132–133 | `["johann-ambrosius"]` | 12.299 |
| child-filler-intersection-union | Adapted Example 5.4.2, pp. 133–134; explicit filler scope | `["johann-ambrosius"]` | 13.034 |
| person-subsumes-father | Example 2.4.3, p. 39; §5.4.4.1, p. 135 | `true` | 0.088 |
| father-does-not-subsume-person | §5.4.4.1, pp. 135–136; Table 2.5 T5, p. 35 | `false` | 5.652 |
| composition-subsumes-birthday-cantata | Table 2.5 T12–T15, p. 35; §5.4.4.1, pp. 135–136 | `true` | 0.014 |
| father-satisfiable | Example 2.4.3, p. 39; §5.4.4.4, pp. 137–138 | `true` | 5.995 |
| ancestor-subsumes-child | Table 2.5 T7, p. 35; §5.4.4.5, pp. 138–139 | `true` | 0.016 |
| ancestor-transitive | Table 2.5 T8, p. 35; §5.4.4.6, p. 140 | `true` | 0.006 |
| marriage-symmetric | Table 2.5 T9, p. 35; §5.4.4.6, pp. 139–140 | `true` | 0.004 |
| dynasty-not-transitive | Table 2.5 T16/T17, p. 35; §6.2.2, p. 151 (corrected) | `false` | 6.284 |

## Bach Table 2.5 (RDF/XML): checked queries

Source: `examples/bach.owl`; profile L3. Parsing measures the original document syntax. Query ms in the summary is the total of all queries below.

| Query | Thesis reference | Answer | Median ms |
|---|---|---|---:|
| fathers | Table 2.5 T5/A1–A4/A7, p. 35; §5.4.2.2, p. 132 | `["johann-ambrosius", "johann-sebastian"]` | 0.030 |
| mothers | Table 2.5 T6, p. 35; §5.4.2.2, p. 132 | `[]` | 0.016 |
| people | Table 2.5 T1/T2/T5, p. 35; §5.4.2.2, p. 132 | `["anna-magdalena", "johann-ambrosius", "johann-sebastian", "maria-barbara", "wilhelm-friedemann"]` | 0.036 |
| masterpieces | Table 2.5 T11/A2/A9/A10, p. 35 | `["BWV248"]` | 0.017 |
| birthday-cantatas | Table 2.5 A14/A15, p. 35 | `["BWV213", "BWV214"]` | 0.017 |
| compositions | Table 2.5 T12–T15/A13–A15, p. 35 | `["BWV213", "BWV214", "BWV248"]` | 0.017 |
| named-birthdays | Table 2.5 T12/A14/A15, p. 35; Example 4.5.2, p. 94 | `[]` | 0.024 |
| leipzig-inhabitants | Table 2.5 T10/A8, p. 35 | `["johann-sebastian"]` | 0.016 |
| wives | Table 2.5 T3/A5/A6/A11/A12, p. 35 | `[]` | 0.014 |
| ambrosius-is-father | Table 2.5 T5/A1/A7, p. 35; §5.4.2.1, p. 132 | `true` | 0.016 |
| ambrosius-named-son-not-entailed | Table 2.5 A1, p. 35; Example 4.5.2, p. 94 | `false` | 0.012 |
| sebastian-known-children | Example 5.4.1, p. 131; §5.4.3, pp. 134–135 | `["wilhelm-friedemann"]` | 0.023 |
| sebastian-marriages | Table 2.5 A6/A12, p. 35; §5.4.3, pp. 134–135 | `["anna-magdalena", "maria-barbara"]` | 0.019 |
| symmetric-marriage | Table 2.5 T9/A6, p. 35; §5.4.3, pp. 134–135 | `["johann-sebastian"]` | 0.016 |
| sebastian-types | §5.4.2.3, p. 134; Table 2.5, p. 35 | `["Composer", "Father", "Genius", "LeipzigInhabitant", "Man", "Person", "owl:Thing"]` | 0.020 |
| male-child-existential | Example 4.5.2, p. 94; §5.4.2, pp. 132–133 | `["johann-ambrosius"]` | 12.372 |
| child-filler-intersection-union | Adapted Example 5.4.2, pp. 133–134; explicit filler scope | `["johann-ambrosius"]` | 12.850 |
| person-subsumes-father | Example 2.4.3, p. 39; §5.4.4.1, p. 135 | `true` | 0.091 |
| father-does-not-subsume-person | §5.4.4.1, pp. 135–136; Table 2.5 T5, p. 35 | `false` | 5.603 |
| composition-subsumes-birthday-cantata | Table 2.5 T12–T15, p. 35; §5.4.4.1, pp. 135–136 | `true` | 0.015 |
| father-satisfiable | Example 2.4.3, p. 39; §5.4.4.4, pp. 137–138 | `true` | 5.847 |
| ancestor-subsumes-child | Table 2.5 T7, p. 35; §5.4.4.5, pp. 138–139 | `true` | 0.012 |
| ancestor-transitive | Table 2.5 T8, p. 35; §5.4.4.6, p. 140 | `true` | 0.005 |
| marriage-symmetric | Table 2.5 T9, p. 35; §5.4.4.6, pp. 139–140 | `true` | 0.004 |
| dynasty-not-transitive | Table 2.5 T16/T17, p. 35; §6.2.2, p. 151 (corrected) | `false` | 6.008 |

## Bach family maintenance (Turtle): checked queries

Source: `examples/bach-family.ttl`; profile L0. Parsing measures the original document syntax. Query ms in the summary is the total of all queries below.

| Query | Thesis reference | Answer | Median ms |
|---|---|---|---:|
| johannes-descendants | Figure 6.2, p. 150; Example 6.3.2, p. 158 | `["christoph", "heinrich", "johann-ambrosius", "johann-christoph", "johann-michael", "johann-sebastian", "maria-barbara", "wilhelm-friedemann"]` | 0.035 |
| ambrosius-descendants | Figure 6.2; §6.2.1, p. 150 | `["johann-sebastian", "wilhelm-friedemann"]` | 0.018 |
| johannes-reaches-wilhelm | Figure 6.2; §6.2.1, p. 150 | `true` | 0.015 |
| base-dynasty-not-symmetric | Table 6.1; §6.2.2, p. 151 | `false` | 2.023 |
| base-dynasty-not-transitive | Table 6.1; §6.2.2, p. 151 | `false` | 1.463 |
| base-ancestor-transitive | Table 6.1 T1, p. 151 | `true` | 0.008 |
| base-cross-branch-not-entailed | §6.2.2, p. 151; docs/THESIS_ERRATA.md item 6 | `false` | 0.014 |

Bach updates each start from the original family graph. Both RDF update and fresh rebuild timings include compilation. Exact pair sets and the three removed/four added ancestor pairs are checked against independent graph traversal and recorded in JSON.

See [Bach source mapping and commands](../docs/BACH_BENCHMARK.md) for the OWL encodings, query scope, exact maintenance deltas and source ambiguities.
