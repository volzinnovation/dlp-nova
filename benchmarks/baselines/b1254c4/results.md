# Measured benchmark results

Run: 2026-09-09T11:35:50.349359+00:00. Python 3.12.9; macOS-26.5.1-arm64-arm-64bit.

Recorded: 51 validated cases, 0 errors, 51 planned cases. Repetitions per case: 5.

All times below are medians in milliseconds. Every raw sample is in `results.json`.
Peak RSS is the entire isolated worker (including parser, retained input and repetitions), not incremental reasoner allocation. Compiler and materializer timings are separate.

| Workload | Engine | Input triples | Closure facts | Compile ms | Materialize ms | Query ms | Peak MiB |
|---|---|---:|---:|---:|---:|---:|---:|
| taxonomy d3/i3/P0 | semi-naive | 196 | 541 | 1.859 | 3.089 | 0.179 | 39.0 |
| taxonomy d3/i3/P1 | semi-naive | 275 | 580 | 2.624 | 2.973 | 0.199 | 40.1 |
| taxonomy d3/i3/PF | semi-naive | 513 | 658 | 4.729 | 3.884 | 0.228 | 44.7 |
| taxonomy d3/i9/P0 | semi-naive | 430 | 1621 | 4.004 | 7.731 | 0.540 | 48.1 |
| taxonomy d3/i9/P1 | semi-naive | 587 | 1738 | 5.678 | 8.843 | 0.592 | 49.6 |
| taxonomy d3/i9/PF | semi-naive | 981 | 1972 | 9.401 | 11.003 | 0.667 | 53.7 |
| taxonomy d3/i15/P0 | semi-naive | 664 | 2701 | 6.174 | 12.620 | 0.878 | 46.9 |
| taxonomy d3/i15/P1 | semi-naive | 899 | 2896 | 8.846 | 14.439 | 0.984 | 54.3 |
| taxonomy d3/i15/PF | semi-naive | 1449 | 3286 | 14.557 | 17.561 | 1.109 | 59.6 |
| taxonomy d5/i3/P0 | semi-naive | 1816 | 7102 | 17.418 | 36.123 | 1.998 | 64.9 |
| taxonomy d5/i3/P1 | semi-naive | 2543 | 7465 | 24.735 | 58.334 | 2.403 | 73.5 |
| taxonomy d5/i3/PF | semi-naive | 3105 | 8191 | 32.279 | 60.895 | 2.428 | 77.0 |
| taxonomy d5/i9/P0 | semi-naive | 3994 | 21304 | 36.539 | 141.331 | 6.216 | 99.0 |
| taxonomy d5/i9/P1 | semi-naive | 5447 | 22393 | 53.211 | 137.726 | 6.945 | 118.1 |
| taxonomy d5/i9/PF | semi-naive | 7461 | 24571 | 86.649 | 161.332 | 7.713 | 133.6 |
| taxonomy d5/i15/P0 | semi-naive | 6172 | 35506 | 56.894 | 238.712 | 11.062 | 142.8 |
| taxonomy d5/i15/P1 | semi-naive | 8351 | 37321 | 85.097 | 268.182 | 12.172 | 160.6 |
| taxonomy d5/i15/PF | semi-naive | 11817 | 40951 | 167.828 | 268.046 | 13.354 | 196.1 |
| taxonomy d7/i3/P0 | semi-naive | 16396 | 83647 | 164.006 | 675.359 | 27.909 | 283.0 |
| taxonomy d7/i3/P1 | semi-naive | 22955 | 86926 | 229.462 | 822.431 | 32.476 | 358.8 |
| taxonomy d7/i3/PF | semi-naive | 26433 | 93484 | 301.628 | 914.899 | 35.109 | 393.5 |
| taxonomy d7/i9/P0 | semi-naive | 36070 | 250939 | 399.700 | 2068.547 | 84.207 | 668.2 |
| taxonomy d7/i9/P1 | semi-naive | 49187 | 260776 | 1160.278 | 4044.267 | 148.352 | 782.9 |
| taxonomy d7/i9/PF | semi-naive | 65781 | 280450 | 1196.013 | 3602.462 | 138.176 | 976.4 |
| taxonomy d7/i15/P0 | semi-naive | 55744 | 418231 | 814.767 | 4866.225 | 241.877 | 1096.5 |
| taxonomy d7/i15/P1 | semi-naive | 75419 | 434626 | 1290.508 | 4299.402 | 190.131 | 1246.2 |
| taxonomy d7/i15/PF | semi-naive | 105129 | 467416 | 1242.354 | 4860.310 | 200.764 | 1568.4 |
| taxonomy d3/i3/P0 | naive | 196 | 541 | 2.095 | 3.595 | 0.191 | 38.8 |
| taxonomy d3/i3/P0 | owlrl | 196 | 1105 | 0.000 | 99.400 | 0.075 | 37.5 |
| equality 100 | semi-naive | 302 | 601 | 3.493 | 12.141 | 0.486 | 39.5 |
| equality 1000 | semi-naive | 3002 | 6001 | 35.664 | 137.208 | 5.314 | 73.8 |
| existential 100 | semi-naive | 112 | 1401 | 1.334 | 69.623 | 6.868 | 41.0 |
| transitive 100 | semi-naive | 101 | 5152 | 1.339 | 451.250 | 12.634 | 46.0 |
| cardinality d3/i3 | semi-naive | 560 | 1057 | 7.996 | 20.620 | 0.595 | 43.2 |
| cardinality d5/i3 | semi-naive | 5204 | 13288 | 78.527 | 243.571 | 7.545 | 93.0 |
| cardinality d7/i3 | semi-naive | 47000 | 152527 | 760.432 | 2942.138 | 85.394 | 552.1 |
| cardinality d5/i9 | semi-naive | 10286 | 39862 | 226.737 | 941.582 | 26.488 | 169.6 |
| factored unions 4 pairs/128 subjects | semi-naive | 638 | 1281 | 8.437 | 14.022 | 0.320 | 41.4 |
| factored unions 8 pairs/128 subjects | semi-naive | 1178 | 2305 | 15.791 | 57.850 | 0.674 | 48.9 |
| factored unions 16 pairs/128 subjects | semi-naive | 2258 | 4353 | 36.010 | 301.281 | 0.986 | 58.8 |
| factored unions 32 pairs/128 subjects | semi-naive | 4418 | 8449 | 91.399 | 1663.508 | 1.562 | 73.4 |
| factored unions 64 pairs/128 subjects | semi-naive | 8738 | 16641 | 87.182 | 10406.030 | 2.286 | 105.6 |
| factored enumerations 16 pairs/128 subjects | semi-naive | 258 | 54 | 3.674 | 4.340 | 0.193 | 38.1 |
| factored enumerations 32 pairs/128 subjects | semi-naive | 386 | 102 | 5.644 | 15.561 | 0.238 | 41.2 |
| factored enumerations 64 pairs/128 subjects | semi-naive | 642 | 198 | 9.435 | 95.863 | 0.301 | 42.8 |
| maintenance d3/10% | semi-naive | 1096 | 4331 | 10.703 | 22.419 | 1.339 | 53.0 |
| maintenance d3/15% | semi-naive | 1096 | 4331 | 10.631 | 21.925 | 1.301 | 53.2 |
| maintenance d4/10% | semi-naive | 5471 | 25581 | 80.813 | 167.815 | 8.500 | 116.1 |
| maintenance d4/15% | semi-naive | 5471 | 25581 | 52.740 | 193.323 | 8.639 | 113.7 |
| maintenance d5/10% | semi-naive | 27346 | 147456 | 300.286 | 1281.996 | 57.330 | 493.0 |
| maintenance d5/15% | semi-naive | 27346 | 147456 | 276.383 | 1649.397 | 55.067 | 482.6 |

## Additional query timings

| Workload | Property pairs ms | Subsumption ms |
|---|---:|---:|
| taxonomy d3/i3/P0 | 0.062 | 7.130 |
| taxonomy d3/i3/P1 | 0.071 | 8.712 |
| taxonomy d3/i3/PF | 0.083 | 13.080 |
| taxonomy d3/i9/P0 | 0.189 | 17.337 |
| taxonomy d3/i9/P1 | 0.214 | 20.912 |
| taxonomy d3/i9/PF | 0.236 | 30.023 |
| taxonomy d3/i15/P0 | 0.312 | 26.737 |
| taxonomy d3/i15/P1 | 0.354 | 32.686 |
| taxonomy d3/i15/PF | 0.392 | 52.956 |
| taxonomy d5/i3/P0 | 0.864 | 83.211 |
| taxonomy d5/i3/P1 | 0.997 | 103.113 |
| taxonomy d5/i3/PF | 1.023 | 118.737 |
| taxonomy d5/i9/P0 | 2.659 | 223.879 |
| taxonomy d5/i9/P1 | 2.801 | 295.137 |
| taxonomy d5/i9/PF | 3.157 | 368.635 |
| taxonomy d5/i15/P0 | 4.400 | 402.960 |
| taxonomy d5/i15/P1 | 4.848 | 467.671 |
| taxonomy d5/i15/PF | 5.102 | 624.705 |
| taxonomy d7/i3/P0 | 12.851 | 1099.823 |
| taxonomy d7/i3/P1 | 14.183 | 1373.532 |
| taxonomy d7/i3/PF | 19.076 | 1487.098 |
| taxonomy d7/i9/P0 | 47.229 | 3220.993 |
| taxonomy d7/i9/P1 | 88.410 | 6682.962 |
| taxonomy d7/i9/PF | 69.315 | 5910.086 |
| taxonomy d7/i15/P0 | 142.110 | 9245.125 |
| taxonomy d7/i15/P1 | 117.928 | 7663.222 |
| taxonomy d7/i15/PF | 119.607 | 7983.876 |
| taxonomy d3/i3/P0 | 0.064 | 9.144 |

## Incremental maintenance

Every operation is checked against a fresh closure from separately tracked facts and rules. Fresh-rebuild timing excludes recompilation, matching the update API's precompiled inputs.

| Workload | Operation | Update ms | Fresh rebuild ms | Observed method |
|---|---|---:|---:|---|
| maintenance d3/10% | fact_delete | 14.815 | 19.822 | dred |
| maintenance d3/10% | fact_insert | 3.595 | 21.679 | incremental-insert |
| maintenance d3/10% | rule_insert | 7.858 | 25.250 | incremental-rules |
| maintenance d3/10% | rule_delete | 10.313 | 24.355 | dred-rules |
| maintenance d3/10% | rule_replace | 11.668 | 25.227 | dred-rules |
| maintenance d3/10% | atomic_mixed | 13.472 | 30.581 | dred-rules |
| maintenance d3/15% | fact_delete | 13.933 | 18.766 | dred |
| maintenance d3/15% | fact_insert | 4.089 | 21.653 | incremental-insert |
| maintenance d3/15% | rule_insert | 7.653 | 24.806 | incremental-rules |
| maintenance d3/15% | rule_delete | 10.047 | 23.663 | dred-rules |
| maintenance d3/15% | rule_replace | 10.962 | 23.915 | dred-rules |
| maintenance d3/15% | atomic_mixed | 13.416 | 20.511 | dred-rules |
| maintenance d4/10% | fact_delete | 115.146 | 151.417 | dred |
| maintenance d4/10% | fact_insert | 19.578 | 214.158 | incremental-insert |
| maintenance d4/10% | rule_insert | 39.179 | 237.009 | incremental-rules |
| maintenance d4/10% | rule_delete | 101.124 | 225.126 | dred-rules |
| maintenance d4/10% | rule_replace | 66.449 | 233.020 | dred-rules |
| maintenance d4/10% | atomic_mixed | 78.822 | 215.536 | dred-rules |
| maintenance d4/15% | fact_delete | 115.920 | 140.611 | dred |
| maintenance d4/15% | fact_insert | 24.074 | 212.981 | incremental-insert |
| maintenance d4/15% | rule_insert | 38.753 | 236.158 | incremental-rules |
| maintenance d4/15% | rule_delete | 60.045 | 222.306 | dred-rules |
| maintenance d4/15% | rule_replace | 104.455 | 183.403 | dred-rules |
| maintenance d4/15% | atomic_mixed | 117.141 | 164.081 | dred-rules |
| maintenance d5/10% | fact_delete | 634.307 | 1204.216 | dred |
| maintenance d5/10% | fact_insert | 290.468 | 1380.158 | incremental-insert |
| maintenance d5/10% | rule_insert | 219.359 | 1616.529 | incremental-rules |
| maintenance d5/10% | rule_delete | 685.817 | 1513.560 | dred-rules |
| maintenance d5/10% | rule_replace | 417.815 | 1465.363 | dred-rules |
| maintenance d5/10% | atomic_mixed | 771.007 | 1513.834 | dred-rules |
| maintenance d5/15% | fact_delete | 569.547 | 1427.176 | dred |
| maintenance d5/15% | fact_insert | 147.132 | 1539.742 | incremental-insert |
| maintenance d5/15% | rule_insert | 219.218 | 1672.142 | incremental-rules |
| maintenance d5/15% | rule_delete | 421.620 | 1688.326 | dred-rules |
| maintenance d5/15% | rule_replace | 749.609 | 1755.865 | dred-rules |
| maintenance d5/15% | atomic_mixed | 817.228 | 1445.472 | dred-rules |

## Corrected cardinality distribution

Counts come from the generated RDF, with maximum-one restrictions twice as numerous as minimum-zero restrictions. Minimum zero normalizes to top; each maximum-one subject has two explicitly named fillers whose equality is checked.

| Workload | Named classes | Universal | Maximum one | Minimum zero | Equality groups |
|---|---:|---:|---:|---:|---:|
| cardinality d3/i3 | 40 | 13 | 26 | 13 | 78 |
| cardinality d5/i3 | 364 | 121 | 242 | 121 | 726 |
| cardinality d7/i3 | 3280 | 1093 | 2186 | 1093 | 6558 |
| cardinality d5/i9 | 364 | 121 | 242 | 121 | 2178 |

## Factored conjunctions of unions and enumerations

The DNF branch count is the size of the expansion avoided, not a measured materialization. Union cases have 128 subjects and 96 expected answers. Enumeration cases have 128 query aliases, with positive and negative membership checked after equality merges. The enumeration cases directly exercise the corrected oneOf translation.

| Constructor | Pairs | Explicit DNF branches | Actual compiled rules | Max variables | Compile ms |
|---|---:|---:|---:|---:|---:|
| unionOf | 4 | 16 | 10 | 1 | 8.437 |
| unionOf | 8 | 256 | 18 | 1 | 15.791 |
| unionOf | 16 | 65536 | 34 | 1 | 36.010 |
| unionOf | 32 | 4294967296 | 66 | 1 | 91.399 |
| unionOf | 64 | 18446744073709551616 | 130 | 1 | 87.182 |
| oneOf | 16 | 65536 | 34 | 1 | 3.674 |
| oneOf | 32 | 4294967296 | 66 | 1 | 5.644 |
| oneOf | 64 | 18446744073709551616 | 130 | 1 | 9.435 |

## Before/after comparison on unchanged inputs

Baseline: `benchmarks/baseline-results.json`, run 2026-09-09T10:50:18.777091+00:00. Rows require identical case controls, input hashes and timing boundaries. Different source hashes are retained in JSON for attribution. Ratios below 1 mean a shorter current median; separate runs do not control machine load or timing noise.

| Workload | Engine | Previous materialize ms | Current materialize ms | After / before |
|---|---|---:|---:|---:|
| taxonomy d3/i3/P0 | semi-naive | 2.869 | 3.089 | 1.077 |
| taxonomy d3/i3/P1 | semi-naive | 3.077 | 2.973 | 0.966 |
| taxonomy d3/i9/P0 | semi-naive | 7.892 | 7.731 | 0.980 |
| taxonomy d3/i9/P1 | semi-naive | 9.059 | 8.843 | 0.976 |
| taxonomy d3/i15/P0 | semi-naive | 12.698 | 12.620 | 0.994 |
| taxonomy d3/i15/P1 | semi-naive | 14.447 | 14.439 | 0.999 |
| taxonomy d5/i3/P0 | semi-naive | 41.022 | 36.123 | 0.881 |
| taxonomy d5/i3/P1 | semi-naive | 62.341 | 58.334 | 0.936 |
| taxonomy d5/i9/P0 | semi-naive | 123.021 | 141.331 | 1.149 |
| taxonomy d5/i9/P1 | semi-naive | 143.101 | 137.726 | 0.962 |
| taxonomy d5/i15/P0 | semi-naive | 237.871 | 238.712 | 1.004 |
| taxonomy d5/i15/P1 | semi-naive | 281.924 | 268.182 | 0.951 |
| taxonomy d7/i3/P0 | semi-naive | 633.873 | 675.359 | 1.065 |
| taxonomy d7/i3/P1 | semi-naive | 804.882 | 822.431 | 1.022 |
| taxonomy d7/i9/P0 | semi-naive | 2050.202 | 2068.547 | 1.009 |
| taxonomy d7/i9/P1 | semi-naive | 2298.690 | 4044.267 | 1.759 |
| taxonomy d7/i15/P0 | semi-naive | 3557.792 | 4866.225 | 1.368 |
| taxonomy d7/i15/P1 | semi-naive | 3801.796 | 4299.402 | 1.131 |
| taxonomy d3/i3/P0 | naive | 3.908 | 3.595 | 0.920 |
| taxonomy d3/i3/P0 | owlrl | 93.754 | 99.400 | 1.060 |
| equality 100 | semi-naive | 11.538 | 12.141 | 1.052 |
| equality 1000 | semi-naive | 129.228 | 137.208 | 1.062 |
| existential 100 | semi-naive | 66.283 | 69.623 | 1.050 |
| transitive 100 | semi-naive | 444.733 | 451.250 | 1.015 |

Matched 24 cases; excluded 27 new or changed cases. The raw report records each exclusion reason. Changed PF targets and the revised maintenance populations/operations are excluded from before/after claims.

These are synthetic workloads inspired by thesis chapter 8, not a reproduction of the 2004 KAON/XSB/Racer measurements. Modern hardware, execution strategies and measurement boundaries differ. OWL RL includes additional axiomatic/schema triples, so its total closure count is not directly comparable; the named instance answers are verified.

The naive strategy shares the compiler and equality machinery; it is an execution baseline, not an independent semantic oracle. Unit validation also uses OWL RL and exhaustive finite models. There is no performance acceptance threshold or claim of production-scale throughput.
