# Bach benchmark results

Run: 2026-09-09T12:17:10.422379+00:00. Python 3.12.9; macOS-26.5.1-arm64-arm-64bit.

Validated 3/3 cases; 0 errors; 5 repetitions per case. [Raw samples and source hashes](bach-results.json).

The full Table 2.5 ontology uses DLP L3; the chapter 6 family tree uses L0. Both ontologies are sourced from the thesis, with the documented corrections to the maintenance examples. These timings describe the current Python implementation.

## Parsing, compilation, materialization and queries

Times are medians in milliseconds. File reading and graph canonicalization are outside the measured phases. Query time sums every checked query in each repetition. Peak RSS includes the entire worker, inputs, queries and repetitions.

| Case | RDF triples | Closure facts | Parse ms | Compile ms | Materialize ms | Queries ms | Peak MiB |
|---|---:|---:|---:|---:|---:|---:|---:|
| Bach Table 2.5 (Turtle) | 164 | 99 | 2.290 | 3.294 | 1.522 | 45.321 | 42.7 |
| Bach Table 2.5 (RDF/XML) | 164 | 99 | 8.781 | 3.982 | 1.910 | 46.091 | 43.8 |
| Bach family maintenance (Turtle) | 25 | 58 | 0.660 | 0.268 | 0.704 | 3.455 | 36.8 |

## Family maintenance

Each scenario starts from the original 24 ancestor pairs. Updated results must match independent graph traversal and full fresh reconstruction. Both timings include compilation; the fact transaction ends with 25 ancestor pairs.

| Operation | RDF update ms | Fresh rebuild ms | Method |
|---|---:|---:|---|
| facts_update | 1.048 | 1.228 | dred |
| rule_delete | 0.715 | 0.976 | dred-rules |
| symmetry_insert | 0.866 | 1.441 | incremental-rules |

## Bach Table 2.5 (Turtle): checked queries

Source: `examples/bach.ttl`; profile L3. Parsing measures the original document syntax. Query ms in the summary is the total of all queries below.

| Query | Thesis reference | Answer | Median ms |
|---|---|---|---:|
| fathers | Table 2.5 T5/A1–A4/A7, p. 35; §5.4.2.2, p. 132 | `["johann-ambrosius", "johann-sebastian"]` | 0.030 |
| mothers | Table 2.5 T6, p. 35; §5.4.2.2, p. 132 | `[]` | 0.016 |
| people | Table 2.5 T1/T2/T5, p. 35; §5.4.2.2, p. 132 | `["anna-magdalena", "johann-ambrosius", "johann-sebastian", "maria-barbara", "wilhelm-friedemann"]` | 0.039 |
| masterpieces | Table 2.5 T11/A2/A9/A10, p. 35 | `["BWV248"]` | 0.017 |
| birthday-cantatas | Table 2.5 A14/A15, p. 35 | `["BWV213", "BWV214"]` | 0.017 |
| compositions | Table 2.5 T12–T15/A13–A15, p. 35 | `["BWV213", "BWV214", "BWV248"]` | 0.017 |
| named-birthdays | Table 2.5 T12/A14/A15, p. 35; Example 4.5.2, p. 94 | `[]` | 0.024 |
| leipzig-inhabitants | Table 2.5 T10/A8, p. 35 | `["johann-sebastian"]` | 0.016 |
| wives | Table 2.5 T3/A5/A6/A11/A12, p. 35 | `[]` | 0.014 |
| ambrosius-is-father | Table 2.5 T5/A1/A7, p. 35; §5.4.2.1, p. 132 | `true` | 0.017 |
| ambrosius-named-son-not-entailed | Table 2.5 A1, p. 35; Example 4.5.2, p. 94 | `false` | 0.012 |
| sebastian-known-children | Example 5.4.1, p. 131; §5.4.3, pp. 134–135 | `["wilhelm-friedemann"]` | 0.024 |
| sebastian-marriages | Table 2.5 A6/A12, p. 35; §5.4.3, pp. 134–135 | `["anna-magdalena", "maria-barbara"]` | 0.019 |
| symmetric-marriage | Table 2.5 T9/A6, p. 35; §5.4.3, pp. 134–135 | `["johann-sebastian"]` | 0.016 |
| sebastian-types | §5.4.2.3, p. 134; Table 2.5, p. 35 | `["Composer", "Father", "Genius", "LeipzigInhabitant", "Man", "Person", "owl:Thing"]` | 0.021 |
| male-child-existential | Example 4.5.2, p. 94; §5.4.2, pp. 132–133 | `["johann-ambrosius"]` | 12.520 |
| child-filler-intersection-union | Adapted Example 5.4.2, pp. 133–134; explicit filler scope | `["johann-ambrosius"]` | 13.164 |
| person-subsumes-father | Example 2.4.3, p. 39; §5.4.4.1, p. 135 | `true` | 0.096 |
| father-does-not-subsume-person | §5.4.4.1, pp. 135–136; Table 2.5 T5, p. 35 | `false` | 5.869 |
| composition-subsumes-birthday-cantata | Table 2.5 T12–T15, p. 35; §5.4.4.1, pp. 135–136 | `true` | 0.019 |
| father-satisfiable | Example 2.4.3, p. 39; §5.4.4.4, pp. 137–138 | `true` | 5.840 |
| ancestor-subsumes-child | Table 2.5 T7, p. 35; §5.4.4.5, pp. 138–139 | `true` | 0.016 |
| ancestor-transitive | Table 2.5 T8, p. 35; §5.4.4.6, p. 140 | `true` | 0.007 |
| marriage-symmetric | Table 2.5 T9, p. 35; §5.4.4.6, pp. 139–140 | `true` | 0.005 |
| dynasty-not-transitive | Table 2.5 T16/T17, p. 35; §6.2.2, p. 151 (corrected) | `false` | 6.379 |

## Bach Table 2.5 (RDF/XML): checked queries

Source: `examples/bach.owl`; profile L3. Parsing measures the original document syntax. Query ms in the summary is the total of all queries below.

| Query | Thesis reference | Answer | Median ms |
|---|---|---|---:|
| fathers | Table 2.5 T5/A1–A4/A7, p. 35; §5.4.2.2, p. 132 | `["johann-ambrosius", "johann-sebastian"]` | 0.041 |
| mothers | Table 2.5 T6, p. 35; §5.4.2.2, p. 132 | `[]` | 0.020 |
| people | Table 2.5 T1/T2/T5, p. 35; §5.4.2.2, p. 132 | `["anna-magdalena", "johann-ambrosius", "johann-sebastian", "maria-barbara", "wilhelm-friedemann"]` | 0.047 |
| masterpieces | Table 2.5 T11/A2/A9/A10, p. 35 | `["BWV248"]` | 0.020 |
| birthday-cantatas | Table 2.5 A14/A15, p. 35 | `["BWV213", "BWV214"]` | 0.022 |
| compositions | Table 2.5 T12–T15/A13–A15, p. 35 | `["BWV213", "BWV214", "BWV248"]` | 0.021 |
| named-birthdays | Table 2.5 T12/A14/A15, p. 35; Example 4.5.2, p. 94 | `[]` | 0.029 |
| leipzig-inhabitants | Table 2.5 T10/A8, p. 35 | `["johann-sebastian"]` | 0.022 |
| wives | Table 2.5 T3/A5/A6/A11/A12, p. 35 | `[]` | 0.017 |
| ambrosius-is-father | Table 2.5 T5/A1/A7, p. 35; §5.4.2.1, p. 132 | `true` | 0.022 |
| ambrosius-named-son-not-entailed | Table 2.5 A1, p. 35; Example 4.5.2, p. 94 | `false` | 0.015 |
| sebastian-known-children | Example 5.4.1, p. 131; §5.4.3, pp. 134–135 | `["wilhelm-friedemann"]` | 0.033 |
| sebastian-marriages | Table 2.5 A6/A12, p. 35; §5.4.3, pp. 134–135 | `["anna-magdalena", "maria-barbara"]` | 0.023 |
| symmetric-marriage | Table 2.5 T9/A6, p. 35; §5.4.3, pp. 134–135 | `["johann-sebastian"]` | 0.019 |
| sebastian-types | §5.4.2.3, p. 134; Table 2.5, p. 35 | `["Composer", "Father", "Genius", "LeipzigInhabitant", "Man", "Person", "owl:Thing"]` | 0.024 |
| male-child-existential | Example 4.5.2, p. 94; §5.4.2, pp. 132–133 | `["johann-ambrosius"]` | 14.668 |
| child-filler-intersection-union | Adapted Example 5.4.2, pp. 133–134; explicit filler scope | `["johann-ambrosius"]` | 13.186 |
| person-subsumes-father | Example 2.4.3, p. 39; §5.4.4.1, p. 135 | `true` | 0.079 |
| father-does-not-subsume-person | §5.4.4.1, pp. 135–136; Table 2.5 T5, p. 35 | `false` | 6.237 |
| composition-subsumes-birthday-cantata | Table 2.5 T12–T15, p. 35; §5.4.4.1, pp. 135–136 | `true` | 0.014 |
| father-satisfiable | Example 2.4.3, p. 39; §5.4.4.4, pp. 137–138 | `true` | 6.311 |
| ancestor-subsumes-child | Table 2.5 T7, p. 35; §5.4.4.5, pp. 138–139 | `true` | 0.010 |
| ancestor-transitive | Table 2.5 T8, p. 35; §5.4.4.6, p. 140 | `true` | 0.005 |
| marriage-symmetric | Table 2.5 T9, p. 35; §5.4.4.6, pp. 139–140 | `true` | 0.005 |
| dynasty-not-transitive | Table 2.5 T16/T17, p. 35; §6.2.2, p. 151 (corrected) | `false` | 6.032 |

## Bach family maintenance (Turtle): checked queries

Source: `examples/bach-family.ttl`; profile L0. Parsing measures the original document syntax. Query ms in the summary is the total of all queries below.

| Query | Thesis reference | Answer | Median ms |
|---|---|---|---:|
| johannes-descendants | Figure 6.2, p. 150; Example 6.3.2, p. 158 | `["christoph", "heinrich", "johann-ambrosius", "johann-christoph", "johann-michael", "johann-sebastian", "maria-barbara", "wilhelm-friedemann"]` | 0.026 |
| ambrosius-descendants | Figure 6.2; §6.2.1, p. 150 | `["johann-sebastian", "wilhelm-friedemann"]` | 0.016 |
| johannes-reaches-wilhelm | Figure 6.2; §6.2.1, p. 150 | `true` | 0.015 |
| base-dynasty-not-symmetric | Table 6.1; §6.2.2, p. 151 | `false` | 1.920 |
| base-dynasty-not-transitive | Table 6.1; §6.2.2, p. 151 | `false` | 1.475 |
| base-ancestor-transitive | Table 6.1 T1, p. 151 | `true` | 0.006 |
| base-cross-branch-not-entailed | §6.2.2, p. 151; docs/THESIS_ERRATA.md item 6 | `false` | 0.013 |

Bach updates each start from the original family graph. Both RDF update and fresh rebuild timings include compilation. Exact pair sets and the three removed/four added ancestor pairs are checked against independent graph traversal and recorded in JSON.

See [Bach source mapping and commands](../docs/BACH_BENCHMARK.md) for the OWL encodings, query scope, exact maintenance deltas and source ambiguities.
