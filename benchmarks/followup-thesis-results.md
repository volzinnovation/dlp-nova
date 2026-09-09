# Measured benchmark results

Run: 2026-09-09T18:32:53.074707+00:00. Python 3.12.9; macOS-26.5.1-arm64-arm-64bit.

Measured checkout: `5531be4010538bef47db069cd40b8550d4ef7702`; dirty: True. Exact measured source hashes and checkout status are in the raw report.

Recorded: 54 validated cases, 0 errors, 54 planned cases. Repetitions per case: 5.

All times below are medians in milliseconds. Every raw sample is in `followup-thesis-results.json`.
Peak RSS is the entire isolated worker (including parser, retained input and repetitions), not incremental reasoner allocation. Compiler and materializer timings are separate.

| Workload | Engine | Input triples | Closure facts | Compile ms | Materialize ms | Query ms | Peak MiB |
|---|---|---:|---:|---:|---:|---:|---:|
| taxonomy d3/i3/P0 | semi-naive | 196 | 541 | 1.409 | 2.016 | 0.134 | 37.5 |
| taxonomy d3/i3/P1 | semi-naive | 275 | 580 | 1.922 | 2.476 | 0.154 | 38.9 |
| taxonomy d3/i3/PF | semi-naive | 513 | 658 | 3.526 | 2.772 | 0.163 | 42.5 |
| taxonomy d3/i9/P0 | semi-naive | 430 | 1621 | 2.883 | 5.441 | 0.371 | 41.5 |
| taxonomy d3/i9/P1 | semi-naive | 587 | 1738 | 4.269 | 6.337 | 0.443 | 43.3 |
| taxonomy d3/i9/PF | semi-naive | 981 | 1972 | 7.171 | 7.557 | 0.485 | 50.2 |
| taxonomy d3/i15/P0 | semi-naive | 664 | 2701 | 4.674 | 8.846 | 0.655 | 44.4 |
| taxonomy d3/i15/P1 | semi-naive | 899 | 2896 | 6.393 | 10.023 | 0.739 | 49.2 |
| taxonomy d3/i15/PF | semi-naive | 1449 | 3286 | 10.654 | 12.679 | 0.847 | 56.1 |
| taxonomy d5/i3/P0 | semi-naive | 1816 | 7102 | 12.596 | 29.250 | 1.492 | 59.8 |
| taxonomy d5/i3/P1 | semi-naive | 2543 | 7465 | 17.705 | 38.327 | 1.763 | 64.3 |
| taxonomy d5/i3/PF | semi-naive | 3105 | 8191 | 23.859 | 33.380 | 1.946 | 75.8 |
| taxonomy d5/i9/P0 | semi-naive | 3994 | 21304 | 28.114 | 93.044 | 5.696 | 86.1 |
| taxonomy d5/i9/P1 | semi-naive | 5447 | 22393 | 39.509 | 105.466 | 6.103 | 101.7 |
| taxonomy d5/i9/PF | semi-naive | 7461 | 24571 | 66.043 | 125.551 | 6.916 | 127.7 |
| taxonomy d5/i15/P0 | semi-naive | 6172 | 35506 | 64.436 | 183.459 | 9.514 | 124.4 |
| taxonomy d5/i15/P1 | semi-naive | 8351 | 37321 | 90.647 | 185.850 | 10.813 | 144.7 |
| taxonomy d5/i15/PF | semi-naive | 11817 | 40951 | 103.738 | 216.423 | 11.941 | 184.4 |
| taxonomy d7/i3/P0 | semi-naive | 16396 | 83647 | 178.918 | 475.330 | 22.876 | 261.2 |
| taxonomy d7/i3/P1 | semi-naive | 22955 | 86926 | 170.852 | 551.089 | 25.322 | 332.5 |
| taxonomy d7/i3/PF | semi-naive | 26433 | 93484 | 215.647 | 641.267 | 28.016 | 361.1 |
| taxonomy d7/i9/P0 | semi-naive | 36070 | 250939 | 263.451 | 1604.144 | 68.316 | 612.0 |
| taxonomy d7/i9/P1 | semi-naive | 49187 | 260776 | 369.301 | 1632.504 | 73.586 | 704.5 |
| taxonomy d7/i9/PF | semi-naive | 65781 | 280450 | 785.015 | 1989.522 | 83.303 | 839.7 |
| taxonomy d7/i15/P0 | semi-naive | 55744 | 418231 | 399.176 | 2690.423 | 125.605 | 890.4 |
| taxonomy d7/i15/P1 | semi-naive | 75419 | 434626 | 648.100 | 2869.147 | 136.864 | 1025.0 |
| taxonomy d7/i15/PF | semi-naive | 105129 | 467416 | 873.841 | 3336.927 | 154.165 | 1290.7 |
| taxonomy d3/i3/P0 | naive | 196 | 541 | 1.367 | 2.589 | 0.132 | 37.3 |
| taxonomy d3/i3/P0 | owlrl | 196 | 1105 | 0.000 | 67.622 | 0.051 | 38.0 |
| equality 100 | semi-naive | 302 | 601 | 2.406 | 7.984 | 0.326 | 39.7 |
| equality 1000 | semi-naive | 3002 | 6001 | 23.184 | 92.988 | 3.434 | 73.1 |
| existential 100 | semi-naive | 112 | 1401 | 0.982 | 47.248 | 4.580 | 39.0 |
| transitive 100 | semi-naive | 101 | 5152 | 0.882 | 317.792 | 8.398 | 46.8 |
| cardinality d3/i3 | semi-naive | 560 | 1057 | 5.572 | 13.359 | 0.416 | 42.4 |
| cardinality d5/i3 | semi-naive | 5204 | 13288 | 54.742 | 166.633 | 4.708 | 91.8 |
| cardinality d7/i3 | semi-naive | 47000 | 152527 | 560.498 | 2128.684 | 63.828 | 564.8 |
| cardinality d5/i9 | semi-naive | 10286 | 39862 | 128.639 | 499.754 | 15.720 | 177.8 |
| factored unions 4 pairs/128 subjects | semi-naive | 638 | 1281 | 4.444 | 4.571 | 0.190 | 41.6 |
| factored unions 8 pairs/128 subjects | semi-naive | 1178 | 2305 | 7.966 | 7.951 | 0.267 | 46.3 |
| factored unions 16 pairs/128 subjects | semi-naive | 2258 | 4353 | 15.595 | 19.608 | 0.417 | 55.5 |
| factored unions 32 pairs/128 subjects | semi-naive | 4418 | 8449 | 31.533 | 30.891 | 0.839 | 68.4 |
| factored unions 64 pairs/128 subjects | semi-naive | 8738 | 16641 | 76.281 | 82.267 | 1.528 | 109.7 |
| factored enumerations 16 pairs/128 subjects | semi-naive | 258 | 54 | 2.458 | 2.039 | 0.143 | 38.0 |
| factored enumerations 32 pairs/128 subjects | semi-naive | 386 | 102 | 3.768 | 2.738 | 0.160 | 40.8 |
| factored enumerations 64 pairs/128 subjects | semi-naive | 642 | 198 | 6.689 | 4.358 | 0.194 | 43.4 |
| maintenance d3/10% | semi-naive | 1096 | 4331 | 7.558 | 15.295 | 0.944 | 49.4 |
| maintenance d3/15% | semi-naive | 1096 | 4331 | 7.489 | 15.150 | 0.936 | 49.3 |
| maintenance d4/10% | semi-naive | 5471 | 25581 | 38.909 | 133.021 | 7.263 | 132.2 |
| maintenance d4/15% | semi-naive | 5471 | 25581 | 38.277 | 148.352 | 6.537 | 136.8 |
| maintenance d5/10% | semi-naive | 27346 | 147456 | 304.792 | 933.409 | 43.817 | 515.8 |
| maintenance d5/15% | semi-naive | 27346 | 147456 | 222.030 | 985.348 | 44.239 | 510.7 |
| Bach Table 2.5 (Turtle) | semi-naive | 164 | 99 | 1.907 | 1.180 | 30.667 | 40.9 |
| Bach Table 2.5 (RDF/XML) | semi-naive | 164 | 99 | 1.940 | 1.192 | 30.686 | 42.4 |
| Bach family maintenance (Turtle) | semi-naive | 25 | 58 | 0.188 | 0.466 | 2.204 | 37.0 |

## Additional query timings

| Workload | Property pairs ms | Subsumption ms |
|---|---:|---:|
| taxonomy d3/i3/P0 | 0.044 | 0.053 |
| taxonomy d3/i3/P1 | 0.055 | 0.052 |
| taxonomy d3/i3/PF | 0.060 | 0.048 |
| taxonomy d3/i9/P0 | 0.135 | 0.052 |
| taxonomy d3/i9/P1 | 0.157 | 0.058 |
| taxonomy d3/i9/PF | 0.169 | 0.050 |
| taxonomy d3/i15/P0 | 0.228 | 0.052 |
| taxonomy d3/i15/P1 | 0.263 | 0.056 |
| taxonomy d3/i15/PF | 0.304 | 0.061 |
| taxonomy d5/i3/P0 | 0.644 | 0.444 |
| taxonomy d5/i3/P1 | 0.670 | 0.490 |
| taxonomy d5/i3/PF | 0.756 | 0.479 |
| taxonomy d5/i9/P0 | 2.064 | 0.627 |
| taxonomy d5/i9/P1 | 2.167 | 0.633 |
| taxonomy d5/i9/PF | 2.410 | 0.628 |
| taxonomy d5/i15/P0 | 3.942 | 0.607 |
| taxonomy d5/i15/P1 | 3.954 | 0.721 |
| taxonomy d5/i15/PF | 4.378 | 0.797 |
| taxonomy d7/i3/P0 | 12.937 | 4.647 |
| taxonomy d7/i3/P1 | 14.170 | 4.887 |
| taxonomy d7/i3/PF | 15.569 | 5.211 |
| taxonomy d7/i9/P0 | 38.577 | 6.341 |
| taxonomy d7/i9/P1 | 39.677 | 6.866 |
| taxonomy d7/i9/PF | 44.995 | 7.488 |
| taxonomy d7/i15/P0 | 73.148 | 7.635 |
| taxonomy d7/i15/P1 | 75.690 | 8.253 |
| taxonomy d7/i15/PF | 85.331 | 9.338 |
| taxonomy d3/i3/P0 | 0.045 | 0.048 |

## Incremental maintenance

Every operation is checked against a fresh closure from separately tracked facts and rules. Synthetic maintenance uses precompiled Engine inputs, excluding recompilation from both timings. Bach uses RDF updates and includes compilation in both timings.

| Workload | Operation | Update ms | Fresh rebuild ms | Observed method |
|---|---|---:|---:|---|
| maintenance d3/10% | fact_delete | 7.259 | 13.983 | dred |
| maintenance d3/10% | fact_insert | 1.295 | 14.735 | incremental-insert |
| maintenance d3/10% | rule_insert | 3.297 | 17.628 | incremental-rules |
| maintenance d3/10% | rule_delete | 4.933 | 16.384 | dred-rules |
| maintenance d3/10% | rule_replace | 5.824 | 16.264 | dred-rules |
| maintenance d3/10% | atomic_mixed | 8.122 | 14.326 | dred-rules |
| maintenance d3/15% | fact_delete | 7.492 | 12.801 | dred |
| maintenance d3/15% | fact_insert | 1.841 | 14.609 | incremental-insert |
| maintenance d3/15% | rule_insert | 3.284 | 17.281 | incremental-rules |
| maintenance d3/15% | rule_delete | 4.876 | 16.257 | dred-rules |
| maintenance d3/15% | rule_replace | 5.630 | 16.189 | dred-rules |
| maintenance d3/15% | atomic_mixed | 8.006 | 13.920 | dred-rules |
| maintenance d4/10% | fact_delete | 45.338 | 110.238 | dred |
| maintenance d4/10% | fact_insert | 9.133 | 123.916 | incremental-insert |
| maintenance d4/10% | rule_insert | 17.210 | 162.779 | incremental-rules |
| maintenance d4/10% | rule_delete | 27.662 | 151.092 | dred-rules |
| maintenance d4/10% | rule_replace | 32.144 | 167.713 | dred-rules |
| maintenance d4/10% | atomic_mixed | 44.268 | 153.854 | dred-rules |
| maintenance d4/15% | fact_delete | 47.382 | 105.958 | dred |
| maintenance d4/15% | fact_insert | 30.287 | 125.346 | incremental-insert |
| maintenance d4/15% | rule_insert | 17.273 | 169.920 | incremental-rules |
| maintenance d4/15% | rule_delete | 27.598 | 171.205 | dred-rules |
| maintenance d4/15% | rule_replace | 30.632 | 158.250 | dred-rules |
| maintenance d4/15% | atomic_mixed | 47.976 | 143.806 | dred-rules |
| maintenance d5/10% | fact_delete | 300.636 | 911.877 | dred |
| maintenance d5/10% | fact_insert | 50.445 | 973.178 | incremental-insert |
| maintenance d5/10% | rule_insert | 225.281 | 1122.367 | incremental-rules |
| maintenance d5/10% | rule_delete | 181.603 | 1075.355 | dred-rules |
| maintenance d5/10% | rule_replace | 200.632 | 1053.562 | dred-rules |
| maintenance d5/10% | atomic_mixed | 284.407 | 986.666 | dred-rules |
| maintenance d5/15% | fact_delete | 323.807 | 846.287 | dred |
| maintenance d5/15% | fact_insert | 73.498 | 990.107 | incremental-insert |
| maintenance d5/15% | rule_insert | 102.014 | 1104.246 | incremental-rules |
| maintenance d5/15% | rule_delete | 184.084 | 1067.953 | dred-rules |
| maintenance d5/15% | rule_replace | 202.974 | 1136.407 | dred-rules |
| maintenance d5/15% | atomic_mixed | 303.521 | 1036.824 | dred-rules |
| Bach family maintenance (Turtle) | facts_update | 0.728 | 0.876 | dred |
| Bach family maintenance (Turtle) | rule_delete | 0.502 | 0.718 | dred-rules |
| Bach family maintenance (Turtle) | symmetry_insert | 0.608 | 1.107 | incremental-rules |

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
| unionOf | 4 | 16 | 10 | 1 | 4.444 |
| unionOf | 8 | 256 | 18 | 1 | 7.966 |
| unionOf | 16 | 65536 | 34 | 1 | 15.595 |
| unionOf | 32 | 4294967296 | 66 | 1 | 31.533 |
| unionOf | 64 | 18446744073709551616 | 130 | 1 | 76.281 |
| oneOf | 16 | 65536 | 34 | 1 | 2.458 |
| oneOf | 32 | 4294967296 | 66 | 1 | 3.768 |
| oneOf | 64 | 18446744073709551616 | 130 | 1 | 6.689 |

## Before/after comparison on unchanged inputs

Baseline: `/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/benchmarks/baselines/b1254c4/results.json`, run 2026-09-09T11:35:50.349359+00:00. Reference commit: `b1254c441731ca4fdf32ea83570ff99aaa84ac2a`. Rows require identical case controls, input hashes and timing boundaries. Different source hashes are retained in JSON for attribution. Ratios below 1 mean a shorter current median. Brackets show deterministic 95% percentile bootstrap intervals for the ratio of medians, resampling the recorded observations. With five repetitions in one worker per case, these are descriptive sensitivity intervals, not guarantees of independent-run coverage or causal speedup. They omit between-run machine-load/drift effects.

Cross-version correctness checks passed for 51/51 matched cases: initial fact counts, expected query-answer checks, and maintenance closure counts. The historical report does not store full answer-set digests.

| Workload | Engine | Previous materialize ms | Current materialize ms | Ratio [interval] | Candidate rows before → after |
|---|---|---:|---:|---:|---:|
| taxonomy d3/i3/P0 | semi-naive | 3.089 | 2.016 | 0.6525 [0.5739, 0.8392] | 306 → 306 |
| taxonomy d3/i3/P1 | semi-naive | 2.973 | 2.476 | 0.8326 [0.6999, 0.8499] | 306 → 306 |
| taxonomy d3/i3/PF | semi-naive | 3.884 | 2.772 | 0.7137 [0.656, 0.763] | 306 → 306 |
| taxonomy d3/i9/P0 | semi-naive | 7.731 | 5.441 | 0.7038 [0.6682, 1.168] | 918 → 918 |
| taxonomy d3/i9/P1 | semi-naive | 8.843 | 6.337 | 0.7166 [0.4404, 1.112] | 918 → 918 |
| taxonomy d3/i9/PF | semi-naive | 11.003 | 7.557 | 0.6868 [0.334, 1.047] | 918 → 918 |
| taxonomy d3/i15/P0 | semi-naive | 12.620 | 8.846 | 0.7009 [0.6898, 0.7242] | 1530 → 1530 |
| taxonomy d3/i15/P1 | semi-naive | 14.439 | 10.023 | 0.6941 [0.3822, 0.9869] | 1530 → 1530 |
| taxonomy d3/i15/PF | semi-naive | 17.561 | 12.679 | 0.722 [0.6864, 0.7335] | 1530 → 1530 |
| taxonomy d5/i3/P0 | semi-naive | 36.123 | 29.250 | 0.8097 [0.5618, 0.9274] | 4923 → 4923 |
| taxonomy d5/i3/P1 | semi-naive | 58.334 | 38.327 | 0.657 [0.4573, 0.9647] | 4923 → 4923 |
| taxonomy d5/i3/PF | semi-naive | 60.895 | 33.380 | 0.5482 [0.4643, 0.9687] | 4923 → 4923 |
| taxonomy d5/i9/P0 | semi-naive | 141.331 | 93.044 | 0.6583 [0.5757, 0.8397] | 14769 → 14769 |
| taxonomy d5/i9/P1 | semi-naive | 137.726 | 105.466 | 0.7658 [0.6389, 0.8897] | 14769 → 14769 |
| taxonomy d5/i9/PF | semi-naive | 161.332 | 125.551 | 0.7782 [0.6225, 1.032] | 14769 → 14769 |
| taxonomy d5/i15/P0 | semi-naive | 238.712 | 183.459 | 0.7685 [0.6507, 0.8555] | 24615 → 24615 |
| taxonomy d5/i15/P1 | semi-naive | 268.182 | 185.850 | 0.693 [0.641, 0.8201] | 24615 → 24615 |
| taxonomy d5/i15/PF | semi-naive | 268.046 | 216.423 | 0.8074 [0.6632, 0.9551] | 24615 → 24615 |
| taxonomy d7/i3/P0 | semi-naive | 675.359 | 475.330 | 0.7038 [0.6018, 0.7833] | 63972 → 63972 |
| taxonomy d7/i3/P1 | semi-naive | 822.431 | 551.089 | 0.6701 [0.5659, 0.8682] | 63972 → 63972 |
| taxonomy d7/i3/PF | semi-naive | 914.899 | 641.267 | 0.7009 [0.638, 0.802] | 63972 → 63972 |
| taxonomy d7/i9/P0 | semi-naive | 2068.547 | 1604.144 | 0.7755 [0.6383, 0.849] | 191916 → 191916 |
| taxonomy d7/i9/P1 | semi-naive | 4044.267 | 1632.504 | 0.4037 [0.134, 0.4726] | 191916 → 191916 |
| taxonomy d7/i9/PF | semi-naive | 3602.462 | 1989.522 | 0.5523 [0.4798, 0.6263] | 191916 → 191916 |
| taxonomy d7/i15/P0 | semi-naive | 4866.225 | 2690.423 | 0.5529 [0.2503, 0.6461] | 319860 → 319860 |
| taxonomy d7/i15/P1 | semi-naive | 4299.402 | 2869.147 | 0.6673 [0.5593, 0.7347] | 319860 → 319860 |
| taxonomy d7/i15/PF | semi-naive | 4860.310 | 3336.927 | 0.6866 [0.4373, 0.7567] | 319860 → 319860 |
| taxonomy d3/i3/P0 | naive | 3.595 | 2.589 | 0.7201 [0.3343, 0.7513] | 954 → 954 |
| taxonomy d3/i3/P0 | owlrl | 99.400 | 67.622 | 0.6803 [0.659, 0.7017] | — |
| equality 100 | semi-naive | 12.141 | 7.984 | 0.6576 [0.4748, 0.6797] | 1800 → 1800 |
| equality 1000 | semi-naive | 137.208 | 92.988 | 0.6777 [0.6156, 0.6978] | 18000 → 18000 |
| existential 100 | semi-naive | 69.623 | 47.248 | 0.6786 [0.6295, 0.721] | 800 → 800 |
| transitive 100 | semi-naive | 451.250 | 317.792 | 0.7042 [0.6927, 0.7257] | 204656 → 204656 |
| cardinality d3/i3 | semi-naive | 20.620 | 13.359 | 0.6478 [0.6072, 0.8604] | 3900 → 3900 |
| cardinality d5/i3 | semi-naive | 243.571 | 166.633 | 0.6841 [0.6126, 0.7518] | 41250 → 41250 |
| cardinality d7/i3 | semi-naive | 2942.138 | 2128.684 | 0.7235 [0.6611, 0.8154] | 416424 → 416424 |
| cardinality d5/i9 | semi-naive | 941.582 | 499.754 | 0.5308 [0.353, 0.7115] | 123750 → 123750 |
| factored unions 4 pairs/128 subjects | semi-naive | 14.022 | 4.571 | 0.3259 [0.2569, 0.442] | 2112 → 672 |
| factored unions 8 pairs/128 subjects | semi-naive | 57.850 | 7.951 | 0.1374 [0.1338, 0.1794] | 7232 → 1184 |
| factored unions 16 pairs/128 subjects | semi-naive | 301.281 | 19.608 | 0.06508 [0.04943, 0.08406] | 26688 → 2208 |
| factored unions 32 pairs/128 subjects | semi-naive | 1663.508 | 30.891 | 0.01857 [0.01256, 0.02168] | 102464 → 4256 |
| factored unions 64 pairs/128 subjects | semi-naive | 10406.030 | 82.267 | 0.007906 [0.006577, 0.008491] | 401472 → 8352 |
| factored enumerations 16 pairs/128 subjects | semi-naive | 4.340 | 2.039 | 0.4699 [0.4454, 0.4979] | 305 → 34 |
| factored enumerations 32 pairs/128 subjects | semi-naive | 15.561 | 2.738 | 0.1759 [0.1734, 0.1851] | 1121 → 66 |
| factored enumerations 64 pairs/128 subjects | semi-naive | 95.863 | 4.358 | 0.04546 [0.04276, 0.04635] | 4289 → 130 |
| maintenance d3/10% | semi-naive | 22.419 | 15.295 | 0.6822 [0.4656, 0.9044] | 3080 → 3080 |
| maintenance d3/15% | semi-naive | 21.925 | 15.150 | 0.691 [0.4222, 0.9163] | 3080 → 3080 |
| maintenance d4/10% | semi-naive | 167.815 | 133.021 | 0.7927 [0.6729, 0.9002] | 19330 → 19330 |
| maintenance d4/15% | semi-naive | 193.323 | 148.352 | 0.7674 [0.5648, 0.9433] | 19330 → 19330 |
| maintenance d5/10% | semi-naive | 1281.996 | 933.409 | 0.7281 [0.4435, 0.8891] | 116205 → 116205 |
| maintenance d5/15% | semi-naive | 1649.397 | 985.348 | 0.5974 [0.496, 0.883] | 116205 → 116205 |

### Parsing, compilation and public query calls

Subsumption still times the complete first public call on each fresh reasoner. A lazy schema index or fast path built inside that call remains inside the timing. It is not silently excluded as setup. All phase samples remain available in JSON.

| Workload / engine | Phase | Previous ms | Current ms | Ratio [interval] |
|---|---|---:|---:|---:|
| taxonomy d3/i3/P0 / semi-naive | parse | 1.756 | 1.285 | 0.7317 [0.4792, 1.11] |
| taxonomy d3/i3/P0 / semi-naive | compile | 1.859 | 1.409 | 0.7582 [0.6964, 0.8589] |
| taxonomy d3/i3/P0 / semi-naive | query | 0.179 | 0.134 | 0.7496 [0.6962, 0.7799] |
| taxonomy d3/i3/P0 / semi-naive | property_query | 0.062 | 0.044 | 0.7186 [0.6555, 0.861] |
| taxonomy d3/i3/P0 / semi-naive | subsumption | 7.130 | 0.053 | 0.007457 [0.004935, 0.00838] |
| taxonomy d3/i3/P1 / semi-naive | parse | 2.391 | 1.745 | 0.7298 [0.5451, 1.134] |
| taxonomy d3/i3/P1 / semi-naive | compile | 2.624 | 1.922 | 0.7323 [0.6154, 0.7932] |
| taxonomy d3/i3/P1 / semi-naive | query | 0.199 | 0.154 | 0.7768 [0.716, 0.8532] |
| taxonomy d3/i3/P1 / semi-naive | property_query | 0.071 | 0.055 | 0.775 [0.6547, 0.8989] |
| taxonomy d3/i3/P1 / semi-naive | subsumption | 8.712 | 0.052 | 0.005983 [0.003844, 0.008896] |
| taxonomy d3/i3/PF / semi-naive | parse | 5.054 | 3.099 | 0.6131 [0.5614, 0.7854] |
| taxonomy d3/i3/PF / semi-naive | compile | 4.729 | 3.526 | 0.7456 [0.3473, 1.595] |
| taxonomy d3/i3/PF / semi-naive | query | 0.228 | 0.163 | 0.7169 [0.69, 0.7473] |
| taxonomy d3/i3/PF / semi-naive | property_query | 0.083 | 0.060 | 0.7203 [0.6965, 0.7357] |
| taxonomy d3/i3/PF / semi-naive | subsumption | 13.080 | 0.048 | 0.003651 [0.003399, 0.004457] |
| taxonomy d3/i9/P0 / semi-naive | parse | 4.173 | 2.641 | 0.633 [0.5846, 0.8109] |
| taxonomy d3/i9/P0 / semi-naive | compile | 4.004 | 2.883 | 0.7199 [0.6538, 0.7706] |
| taxonomy d3/i9/P0 / semi-naive | query | 0.540 | 0.371 | 0.6877 [0.6351, 0.7734] |
| taxonomy d3/i9/P0 / semi-naive | property_query | 0.189 | 0.135 | 0.7141 [0.585, 0.8766] |
| taxonomy d3/i9/P0 / semi-naive | subsumption | 17.337 | 0.052 | 0.003019 [0.002043, 0.003307] |
| taxonomy d3/i9/P1 / semi-naive | parse | 4.942 | 3.630 | 0.7345 [0.5926, 0.8983] |
| taxonomy d3/i9/P1 / semi-naive | compile | 5.678 | 4.269 | 0.7518 [0.721, 0.7968] |
| taxonomy d3/i9/P1 / semi-naive | query | 0.592 | 0.443 | 0.7491 [0.7026, 0.8111] |
| taxonomy d3/i9/P1 / semi-naive | property_query | 0.214 | 0.157 | 0.7346 [0.6358, 0.8743] |
| taxonomy d3/i9/P1 / semi-naive | subsumption | 20.912 | 0.058 | 0.002777 [0.001876, 0.003572] |
| taxonomy d3/i9/PF / semi-naive | parse | 8.767 | 6.139 | 0.7003 [0.6579, 0.7825] |
| taxonomy d3/i9/PF / semi-naive | compile | 9.401 | 7.171 | 0.7628 [0.7392, 0.7802] |
| taxonomy d3/i9/PF / semi-naive | query | 0.667 | 0.485 | 0.7267 [0.6982, 0.8102] |
| taxonomy d3/i9/PF / semi-naive | property_query | 0.236 | 0.169 | 0.7161 [0.7096, 0.7256] |
| taxonomy d3/i9/PF / semi-naive | subsumption | 30.023 | 0.050 | 0.001657 [0.001273, 0.001889] |
| taxonomy d3/i15/P0 / semi-naive | parse | 5.568 | 4.111 | 0.7383 [0.5973, 0.9638] |
| taxonomy d3/i15/P0 / semi-naive | compile | 6.174 | 4.674 | 0.7571 [0.6808, 1.333] |
| taxonomy d3/i15/P0 / semi-naive | query | 0.878 | 0.655 | 0.7461 [0.7053, 0.8481] |
| taxonomy d3/i15/P0 / semi-naive | property_query | 0.312 | 0.228 | 0.7315 [0.6458, 0.7818] |
| taxonomy d3/i15/P0 / semi-naive | subsumption | 26.737 | 0.052 | 0.001957 [0.001784, 0.002104] |
| taxonomy d3/i15/P1 / semi-naive | parse | 8.245 | 5.683 | 0.6893 [0.6333, 0.765] |
| taxonomy d3/i15/P1 / semi-naive | compile | 8.846 | 6.393 | 0.7227 [0.6937, 0.75] |
| taxonomy d3/i15/P1 / semi-naive | query | 0.984 | 0.739 | 0.7516 [0.6995, 0.8037] |
| taxonomy d3/i15/P1 / semi-naive | property_query | 0.354 | 0.263 | 0.744 [0.6379, 0.8125] |
| taxonomy d3/i15/P1 / semi-naive | subsumption | 32.686 | 0.056 | 0.001709 [0.001429, 0.001797] |
| taxonomy d3/i15/PF / semi-naive | parse | 13.417 | 9.315 | 0.6943 [0.3012, 1.014] |
| taxonomy d3/i15/PF / semi-naive | compile | 14.557 | 10.654 | 0.7319 [0.6835, 1.285] |
| taxonomy d3/i15/PF / semi-naive | query | 1.109 | 0.847 | 0.7635 [0.7239, 0.8334] |
| taxonomy d3/i15/PF / semi-naive | property_query | 0.392 | 0.304 | 0.7759 [0.7082, 0.8108] |
| taxonomy d3/i15/PF / semi-naive | subsumption | 52.956 | 0.061 | 0.001144 [0.0009238, 0.001467] |
| taxonomy d5/i3/P0 / semi-naive | parse | 16.283 | 11.153 | 0.6849 [0.6643, 0.7165] |
| taxonomy d5/i3/P0 / semi-naive | compile | 17.418 | 12.596 | 0.7231 [0.6966, 0.747] |
| taxonomy d5/i3/P0 / semi-naive | query | 1.998 | 1.492 | 0.7467 [0.6883, 0.7811] |
| taxonomy d5/i3/P0 / semi-naive | property_query | 0.864 | 0.644 | 0.7456 [0.6943, 0.8025] |
| taxonomy d5/i3/P0 / semi-naive | subsumption | 83.211 | 0.444 | 0.005333 [0.004917, 0.00742] |
| taxonomy d5/i3/P1 / semi-naive | parse | 23.173 | 15.910 | 0.6866 [0.6741, 0.7312] |
| taxonomy d5/i3/P1 / semi-naive | compile | 24.735 | 17.705 | 0.7158 [0.5994, 0.8716] |
| taxonomy d5/i3/P1 / semi-naive | query | 2.403 | 1.763 | 0.7338 [0.6739, 0.8016] |
| taxonomy d5/i3/P1 / semi-naive | property_query | 0.997 | 0.670 | 0.6716 [0.4913, 0.7379] |
| taxonomy d5/i3/P1 / semi-naive | subsumption | 103.113 | 0.490 | 0.004756 [0.004364, 0.007109] |
| taxonomy d5/i3/PF / semi-naive | parse | 27.847 | 21.358 | 0.767 [0.4816, 1.06] |
| taxonomy d5/i3/PF / semi-naive | compile | 32.279 | 23.859 | 0.7391 [0.6303, 0.8413] |
| taxonomy d5/i3/PF / semi-naive | query | 2.428 | 1.946 | 0.8015 [0.7097, 0.8333] |
| taxonomy d5/i3/PF / semi-naive | property_query | 1.023 | 0.756 | 0.7386 [0.6917, 0.7883] |
| taxonomy d5/i3/PF / semi-naive | subsumption | 118.737 | 0.479 | 0.004035 [0.00371, 0.004678] |
| taxonomy d5/i9/P0 / semi-naive | parse | 34.672 | 25.206 | 0.727 [0.3814, 0.7845] |
| taxonomy d5/i9/P0 / semi-naive | compile | 36.539 | 28.114 | 0.7694 [0.7478, 0.7803] |
| taxonomy d5/i9/P0 / semi-naive | query | 6.216 | 5.696 | 0.9163 [0.7885, 1.021] |
| taxonomy d5/i9/P0 / semi-naive | property_query | 2.659 | 2.064 | 0.7763 [0.7064, 0.974] |
| taxonomy d5/i9/P0 / semi-naive | subsumption | 223.879 | 0.627 | 0.002802 [0.002285, 0.003483] |
| taxonomy d5/i9/P1 / semi-naive | parse | 46.667 | 35.440 | 0.7594 [0.4253, 1.062] |
| taxonomy d5/i9/P1 / semi-naive | compile | 53.211 | 39.509 | 0.7425 [0.3869, 1.011] |
| taxonomy d5/i9/P1 / semi-naive | query | 6.945 | 6.103 | 0.8787 [0.8348, 0.9946] |
| taxonomy d5/i9/P1 / semi-naive | property_query | 2.801 | 2.167 | 0.7735 [0.7538, 0.8956] |
| taxonomy d5/i9/P1 / semi-naive | subsumption | 295.137 | 0.633 | 0.002146 [0.001897, 0.002504] |
| taxonomy d5/i9/PF / semi-naive | parse | 69.482 | 62.628 | 0.9013 [0.4444, 1.088] |
| taxonomy d5/i9/PF / semi-naive | compile | 86.649 | 66.043 | 0.7622 [0.5706, 1.029] |
| taxonomy d5/i9/PF / semi-naive | query | 7.713 | 6.916 | 0.8967 [0.7543, 1.042] |
| taxonomy d5/i9/PF / semi-naive | property_query | 3.157 | 2.410 | 0.7635 [0.686, 0.8878] |
| taxonomy d5/i9/PF / semi-naive | subsumption | 368.635 | 0.628 | 0.001703 [0.001563, 0.002446] |
| taxonomy d5/i15/P0 / semi-naive | parse | 52.788 | 44.190 | 0.8371 [0.7205, 1.188] |
| taxonomy d5/i15/P0 / semi-naive | compile | 56.894 | 64.436 | 1.133 [0.4935, 1.196] |
| taxonomy d5/i15/P0 / semi-naive | query | 11.062 | 9.514 | 0.8601 [0.7882, 0.9967] |
| taxonomy d5/i15/P0 / semi-naive | property_query | 4.400 | 3.942 | 0.8958 [0.8391, 1.015] |
| taxonomy d5/i15/P0 / semi-naive | subsumption | 402.960 | 0.607 | 0.001507 [0.001397, 0.001929] |
| taxonomy d5/i15/P1 / semi-naive | parse | 77.249 | 59.990 | 0.7766 [0.3698, 1.097] |
| taxonomy d5/i15/P1 / semi-naive | compile | 85.097 | 90.647 | 1.065 [0.589, 1.156] |
| taxonomy d5/i15/P1 / semi-naive | query | 12.172 | 10.813 | 0.8884 [0.797, 0.9981] |
| taxonomy d5/i15/P1 / semi-naive | property_query | 4.848 | 3.954 | 0.8155 [0.7014, 0.94] |
| taxonomy d5/i15/P1 / semi-naive | subsumption | 467.671 | 0.721 | 0.001541 [0.001413, 0.001683] |
| taxonomy d5/i15/PF / semi-naive | parse | 110.581 | 84.026 | 0.7599 [0.3657, 1.011] |
| taxonomy d5/i15/PF / semi-naive | compile | 167.828 | 103.738 | 0.6181 [0.4391, 1.016] |
| taxonomy d5/i15/PF / semi-naive | query | 13.354 | 11.941 | 0.8942 [0.8193, 0.9619] |
| taxonomy d5/i15/PF / semi-naive | property_query | 5.102 | 4.378 | 0.858 [0.807, 0.9514] |
| taxonomy d5/i15/PF / semi-naive | subsumption | 624.705 | 0.797 | 0.001276 [0.001104, 0.001386] |
| taxonomy d7/i3/P0 / semi-naive | parse | 150.247 | 111.463 | 0.7419 [0.2929, 1.092] |
| taxonomy d7/i3/P0 / semi-naive | compile | 164.006 | 178.918 | 1.091 [0.4698, 1.192] |
| taxonomy d7/i3/P0 / semi-naive | query | 27.909 | 22.876 | 0.8197 [0.6639, 0.8748] |
| taxonomy d7/i3/P0 / semi-naive | property_query | 12.851 | 12.937 | 1.007 [0.8314, 1.114] |
| taxonomy d7/i3/P0 / semi-naive | subsumption | 1099.823 | 4.647 | 0.004225 [0.003671, 0.004649] |
| taxonomy d7/i3/P1 / semi-naive | parse | 204.130 | 221.534 | 1.085 [0.4361, 1.134] |
| taxonomy d7/i3/P1 / semi-naive | compile | 229.462 | 170.852 | 0.7446 [0.5223, 0.8228] |
| taxonomy d7/i3/P1 / semi-naive | query | 32.476 | 25.322 | 0.7797 [0.6934, 0.9012] |
| taxonomy d7/i3/P1 / semi-naive | property_query | 14.183 | 14.170 | 0.9991 [0.7772, 1.242] |
| taxonomy d7/i3/P1 / semi-naive | subsumption | 1373.532 | 4.887 | 0.003558 [0.003195, 0.003636] |
| taxonomy d7/i3/PF / semi-naive | parse | 557.512 | 208.934 | 0.3748 [0.2984, 0.7591] |
| taxonomy d7/i3/PF / semi-naive | compile | 301.628 | 215.647 | 0.7149 [0.5748, 0.7902] |
| taxonomy d7/i3/PF / semi-naive | query | 35.109 | 28.016 | 0.798 [0.7646, 0.8194] |
| taxonomy d7/i3/PF / semi-naive | property_query | 19.076 | 15.569 | 0.8162 [0.7819, 0.9363] |
| taxonomy d7/i3/PF / semi-naive | subsumption | 1487.098 | 5.211 | 0.003504 [0.002883, 0.003851] |
| taxonomy d7/i9/P0 / semi-naive | parse | 398.193 | 232.459 | 0.5838 [0.1714, 0.8835] |
| taxonomy d7/i9/P0 / semi-naive | compile | 399.700 | 263.451 | 0.6591 [0.2319, 0.7599] |
| taxonomy d7/i9/P0 / semi-naive | query | 84.207 | 68.316 | 0.8113 [0.6099, 0.8262] |
| taxonomy d7/i9/P0 / semi-naive | property_query | 47.229 | 38.577 | 0.8168 [0.716, 0.8576] |
| taxonomy d7/i9/P0 / semi-naive | subsumption | 3220.993 | 6.341 | 0.001969 [0.001003, 0.002113] |
| taxonomy d7/i9/P1 / semi-naive | parse | 1371.182 | 454.552 | 0.3315 [0.08369, 0.8022] |
| taxonomy d7/i9/P1 / semi-naive | compile | 1160.278 | 369.301 | 0.3183 [0.08437, 0.4987] |
| taxonomy d7/i9/P1 / semi-naive | query | 148.352 | 73.586 | 0.496 [0.1909, 0.5402] |
| taxonomy d7/i9/P1 / semi-naive | property_query | 88.410 | 39.677 | 0.4488 [0.244, 0.7132] |
| taxonomy d7/i9/P1 / semi-naive | subsumption | 6682.962 | 6.866 | 0.001027 [0.0006172, 0.001255] |
| taxonomy d7/i9/PF / semi-naive | parse | 1096.393 | 521.409 | 0.4756 [0.3473, 0.8444] |
| taxonomy d7/i9/PF / semi-naive | compile | 1196.013 | 785.015 | 0.6564 [0.3352, 0.9415] |
| taxonomy d7/i9/PF / semi-naive | query | 138.176 | 83.303 | 0.6029 [0.5149, 0.6607] |
| taxonomy d7/i9/PF / semi-naive | property_query | 69.315 | 44.995 | 0.6491 [0.5617, 0.7484] |
| taxonomy d7/i9/PF / semi-naive | subsumption | 5910.086 | 7.488 | 0.001267 [0.0008742, 0.001508] |
| taxonomy d7/i15/P0 / semi-naive | parse | 785.515 | 446.218 | 0.5681 [0.3746, 1.01] |
| taxonomy d7/i15/P0 / semi-naive | compile | 814.767 | 399.176 | 0.4899 [0.2871, 0.6461] |
| taxonomy d7/i15/P0 / semi-naive | query | 241.877 | 125.605 | 0.5193 [0.132, 0.6069] |
| taxonomy d7/i15/P0 / semi-naive | property_query | 142.110 | 73.148 | 0.5147 [0.2283, 0.6252] |
| taxonomy d7/i15/P0 / semi-naive | subsumption | 9245.125 | 7.635 | 0.0008258 [0.0005545, 0.001254] |
| taxonomy d7/i15/P1 / semi-naive | parse | 1816.613 | 505.479 | 0.2783 [0.2316, 0.6626] |
| taxonomy d7/i15/P1 / semi-naive | compile | 1290.508 | 648.100 | 0.5022 [0.3159, 0.8465] |
| taxonomy d7/i15/P1 / semi-naive | query | 190.131 | 136.864 | 0.7198 [0.5384, 0.7616] |
| taxonomy d7/i15/P1 / semi-naive | property_query | 117.928 | 75.690 | 0.6418 [0.5545, 0.7895] |
| taxonomy d7/i15/P1 / semi-naive | subsumption | 7663.222 | 8.253 | 0.001077 [0.0005791, 0.001379] |
| taxonomy d7/i15/PF / semi-naive | parse | 1163.029 | 1209.430 | 1.04 [0.3843, 1.242] |
| taxonomy d7/i15/PF / semi-naive | compile | 1242.354 | 873.841 | 0.7034 [0.2561, 0.7339] |
| taxonomy d7/i15/PF / semi-naive | query | 200.764 | 154.165 | 0.7679 [0.6705, 0.8155] |
| taxonomy d7/i15/PF / semi-naive | property_query | 119.607 | 85.331 | 0.7134 [0.5772, 0.8079] |
| taxonomy d7/i15/PF / semi-naive | subsumption | 7983.876 | 9.338 | 0.00117 [0.0007161, 0.001239] |
| taxonomy d3/i3/P0 / naive | parse | 1.803 | 1.207 | 0.6694 [0.4602, 1.015] |
| taxonomy d3/i3/P0 / naive | compile | 2.095 | 1.367 | 0.6526 [0.5175, 0.8078] |
| taxonomy d3/i3/P0 / naive | query | 0.191 | 0.132 | 0.6932 [0.6516, 0.9945] |
| taxonomy d3/i3/P0 / naive | property_query | 0.064 | 0.045 | 0.6996 [0.6212, 0.7529] |
| taxonomy d3/i3/P0 / naive | subsumption | 9.144 | 0.048 | 0.005281 [0.004793, 0.00693] |
| taxonomy d3/i3/P0 / owlrl | parse | 1.908 | 1.269 | 0.6651 [0.4777, 0.9626] |
| taxonomy d3/i3/P0 / owlrl | compile | 0.000 | 0.000 | — |
| taxonomy d3/i3/P0 / owlrl | query | 0.075 | 0.051 | 0.679 [0.6471, 0.796] |
| equality 100 / semi-naive | parse | 2.764 | 1.892 | 0.6844 [0.5398, 0.8822] |
| equality 100 / semi-naive | compile | 3.493 | 2.406 | 0.6888 [0.6112, 1.595] |
| equality 100 / semi-naive | query | 0.486 | 0.326 | 0.6712 [0.6335, 0.8111] |
| equality 1000 / semi-naive | parse | 27.928 | 18.438 | 0.6602 [0.4279, 1.047] |
| equality 1000 / semi-naive | compile | 35.664 | 23.184 | 0.6501 [0.5764, 0.963] |
| equality 1000 / semi-naive | query | 5.314 | 3.434 | 0.6463 [0.478, 0.7016] |
| existential 100 / semi-naive | parse | 1.077 | 0.758 | 0.7037 [0.4203, 1.182] |
| existential 100 / semi-naive | compile | 1.334 | 0.982 | 0.7363 [0.5933, 0.7962] |
| existential 100 / semi-naive | query | 6.868 | 4.580 | 0.6669 [0.6537, 0.6827] |
| transitive 100 / semi-naive | parse | 1.050 | 0.700 | 0.6667 [0.1061, 1.316] |
| transitive 100 / semi-naive | compile | 1.339 | 0.882 | 0.6587 [0.6249, 0.7553] |
| transitive 100 / semi-naive | query | 12.634 | 8.398 | 0.6648 [0.6182, 0.9022] |
| cardinality d3/i3 / semi-naive | parse | 6.019 | 4.278 | 0.7108 [0.6256, 0.7798] |
| cardinality d3/i3 / semi-naive | compile | 7.996 | 5.572 | 0.6969 [0.4188, 0.7449] |
| cardinality d3/i3 / semi-naive | query | 0.595 | 0.416 | 0.6991 [0.6525, 0.7449] |
| cardinality d5/i3 / semi-naive | parse | 52.724 | 37.241 | 0.7063 [0.4714, 1.091] |
| cardinality d5/i3 / semi-naive | compile | 78.527 | 54.742 | 0.6971 [0.5022, 0.9961] |
| cardinality d5/i3 / semi-naive | query | 7.545 | 4.708 | 0.624 [0.607, 0.6755] |
| cardinality d7/i3 / semi-naive | parse | 668.684 | 469.546 | 0.7022 [0.4826, 0.9446] |
| cardinality d7/i3 / semi-naive | compile | 760.432 | 560.498 | 0.7371 [0.5808, 1.134] |
| cardinality d7/i3 / semi-naive | query | 85.394 | 63.828 | 0.7475 [0.7113, 0.785] |
| cardinality d5/i9 / semi-naive | parse | 157.891 | 105.706 | 0.6695 [0.3195, 0.984] |
| cardinality d5/i9 / semi-naive | compile | 226.737 | 128.639 | 0.5673 [0.3792, 0.9373] |
| cardinality d5/i9 / semi-naive | query | 26.488 | 15.720 | 0.5935 [0.4375, 0.7428] |
| factored unions 4 pairs/128 subjects / semi-naive | parse | 7.557 | 4.298 | 0.5687 [0.3836, 1.089] |
| factored unions 4 pairs/128 subjects / semi-naive | compile | 8.437 | 4.444 | 0.5267 [0.4619, 0.7156] |
| factored unions 4 pairs/128 subjects / semi-naive | query | 0.320 | 0.190 | 0.5928 [0.4376, 0.6863] |
| factored unions 8 pairs/128 subjects / semi-naive | parse | 15.032 | 7.360 | 0.4896 [0.3991, 0.7287] |
| factored unions 8 pairs/128 subjects / semi-naive | compile | 15.791 | 7.966 | 0.5045 [0.4007, 0.6553] |
| factored unions 8 pairs/128 subjects / semi-naive | query | 0.674 | 0.267 | 0.3965 [0.269, 0.5344] |
| factored unions 16 pairs/128 subjects / semi-naive | parse | 33.722 | 14.270 | 0.4232 [0.2782, 0.7106] |
| factored unions 16 pairs/128 subjects / semi-naive | compile | 36.010 | 15.595 | 0.4331 [0.187, 0.6952] |
| factored unions 16 pairs/128 subjects / semi-naive | query | 0.986 | 0.417 | 0.4228 [0.3914, 0.5752] |
| factored unions 32 pairs/128 subjects / semi-naive | parse | 61.096 | 28.332 | 0.4637 [0.3364, 0.6734] |
| factored unions 32 pairs/128 subjects / semi-naive | compile | 91.399 | 31.533 | 0.345 [0.2684, 0.5148] |
| factored unions 32 pairs/128 subjects / semi-naive | query | 1.562 | 0.839 | 0.537 [0.3952, 0.6049] |
| factored unions 64 pairs/128 subjects / semi-naive | parse | 84.582 | 54.845 | 0.6484 [0.4968, 0.7677] |
| factored unions 64 pairs/128 subjects / semi-naive | compile | 87.182 | 76.281 | 0.875 [0.5775, 0.9716] |
| factored unions 64 pairs/128 subjects / semi-naive | query | 2.286 | 1.528 | 0.6683 [0.5461, 0.7467] |
| factored enumerations 16 pairs/128 subjects / semi-naive | parse | 2.547 | 1.740 | 0.6832 [0.5418, 0.9577] |
| factored enumerations 16 pairs/128 subjects / semi-naive | compile | 3.674 | 2.458 | 0.6689 [0.5857, 0.7727] |
| factored enumerations 16 pairs/128 subjects / semi-naive | query | 0.193 | 0.143 | 0.738 [0.6786, 0.7861] |
| factored enumerations 32 pairs/128 subjects / semi-naive | parse | 3.894 | 2.997 | 0.7696 [0.6229, 0.9446] |
| factored enumerations 32 pairs/128 subjects / semi-naive | compile | 5.644 | 3.768 | 0.6677 [0.6506, 0.7237] |
| factored enumerations 32 pairs/128 subjects / semi-naive | query | 0.238 | 0.160 | 0.6729 [0.6175, 0.7404] |
| factored enumerations 64 pairs/128 subjects / semi-naive | parse | 6.368 | 4.594 | 0.7214 [0.6136, 0.8661] |
| factored enumerations 64 pairs/128 subjects / semi-naive | compile | 9.435 | 6.689 | 0.7089 [0.6747, 1.148] |
| factored enumerations 64 pairs/128 subjects / semi-naive | query | 0.301 | 0.194 | 0.6449 [0.5986, 0.6564] |
| maintenance d3/10% / semi-naive | parse | 10.184 | 6.810 | 0.6687 [0.6217, 1.047] |
| maintenance d3/10% / semi-naive | compile | 10.703 | 7.558 | 0.7062 [0.6793, 0.7231] |
| maintenance d3/10% / semi-naive | query | 1.339 | 0.944 | 0.7046 [0.6115, 0.7577] |
| maintenance d3/15% / semi-naive | parse | 10.221 | 6.739 | 0.6593 [0.3029, 1.037] |
| maintenance d3/15% / semi-naive | compile | 10.631 | 7.489 | 0.7044 [0.6973, 0.7273] |
| maintenance d3/15% / semi-naive | query | 1.301 | 0.936 | 0.7195 [0.6931, 0.7531] |
| maintenance d4/10% / semi-naive | parse | 52.051 | 33.721 | 0.6479 [0.3631, 0.7445] |
| maintenance d4/10% / semi-naive | compile | 80.813 | 38.909 | 0.4815 [0.3874, 0.7556] |
| maintenance d4/10% / semi-naive | query | 8.500 | 7.263 | 0.8544 [0.7725, 1.043] |
| maintenance d4/15% / semi-naive | parse | 53.710 | 33.822 | 0.6297 [0.3604, 0.9264] |
| maintenance d4/15% / semi-naive | compile | 52.740 | 38.277 | 0.7258 [0.6945, 0.7396] |
| maintenance d4/15% / semi-naive | query | 8.639 | 6.537 | 0.7567 [0.6958, 0.819] |
| maintenance d5/10% / semi-naive | parse | 249.729 | 211.203 | 0.8457 [0.3768, 1.058] |
| maintenance d5/10% / semi-naive | compile | 300.286 | 304.792 | 1.015 [0.4592, 1.172] |
| maintenance d5/10% / semi-naive | query | 57.330 | 43.817 | 0.7643 [0.7046, 0.8838] |
| maintenance d5/15% / semi-naive | parse | 292.262 | 174.508 | 0.5971 [0.2349, 0.7397] |
| maintenance d5/15% / semi-naive | compile | 276.383 | 222.030 | 0.8033 [0.7273, 1.236] |
| maintenance d5/15% / semi-naive | query | 55.067 | 44.239 | 0.8034 [0.7096, 0.8565] |

### Maintenance compared with the pinned implementation

These rows compare the same operation across versions. The separate fresh-rebuild ratio compares each version's recomputation cost. Input mutation counts and fresh-closure validation must agree before an operation is compared. All common evaluation counters and raw operation samples are retained in JSON.

| Workload | Operation | Previous ms | Current ms | Update ratio [interval] | Rebuild ratio [interval] | Overdeleted before → after |
|---|---|---:|---:|---:|---:|---:|
| maintenance d3/10% | fact_delete | 14.815 | 7.259 | 0.49 [0.3014, 0.5246] | 0.7054 [0.6764, 0.88] | 442 → 442 |
| maintenance d3/10% | fact_insert | 3.595 | 1.295 | 0.3601 [0.3348, 0.4394] | 0.6797 [0.4211, 0.9827] | 0 → 0 |
| maintenance d3/10% | rule_insert | 7.858 | 3.297 | 0.4196 [0.3884, 0.4477] | 0.6981 [0.4685, 0.9588] | 0 → 0 |
| maintenance d3/10% | rule_delete | 10.313 | 4.933 | 0.4783 [0.2438, 0.5073] | 0.6727 [0.491, 0.9331] | 276 → 276 |
| maintenance d3/10% | rule_replace | 11.668 | 5.824 | 0.4992 [0.4805, 0.5349] | 0.6447 [0.4418, 0.6725] | 272 → 272 |
| maintenance d3/10% | atomic_mixed | 13.472 | 8.122 | 0.6029 [0.5354, 0.9471] | 0.4685 [0.4137, 0.7264] | 975 → 975 |
| maintenance d3/15% | fact_delete | 13.933 | 7.492 | 0.5377 [0.3986, 0.5624] | 0.6821 [0.6725, 0.872] | 659 → 659 |
| maintenance d3/15% | fact_insert | 4.089 | 1.841 | 0.4503 [0.3944, 0.4974] | 0.6747 [0.4427, 1.027] | 0 → 0 |
| maintenance d3/15% | rule_insert | 7.653 | 3.284 | 0.4291 [0.3923, 0.4368] | 0.6967 [0.4739, 0.9728] | 0 → 0 |
| maintenance d3/15% | rule_delete | 10.047 | 4.876 | 0.4853 [0.2839, 0.4936] | 0.687 [0.5511, 0.9636] | 256 → 256 |
| maintenance d3/15% | rule_replace | 10.962 | 5.630 | 0.5136 [0.4843, 0.5343] | 0.677 [0.447, 0.6895] | 262 → 262 |
| maintenance d3/15% | atomic_mixed | 13.416 | 8.006 | 0.5968 [0.5653, 1.025] | 0.6787 [0.4349, 0.9529] | 1070 → 1070 |
| maintenance d4/10% | fact_delete | 115.146 | 45.338 | 0.3937 [0.3734, 0.6494] | 0.728 [0.6009, 1.016] | 2555 → 2555 |
| maintenance d4/10% | fact_insert | 19.578 | 9.133 | 0.4665 [0.1673, 1.616] | 0.5786 [0.5365, 0.7887] | 0 → 0 |
| maintenance d4/10% | rule_insert | 39.179 | 17.210 | 0.4393 [0.4167, 1.157] | 0.6868 [0.5956, 0.7929] | 0 → 0 |
| maintenance d4/10% | rule_delete | 101.124 | 27.662 | 0.2735 [0.2495, 0.5915] | 0.6711 [0.5985, 0.8593] | 1408 → 1408 |
| maintenance d4/10% | rule_replace | 66.449 | 32.144 | 0.4837 [0.2842, 0.9269] | 0.7197 [0.5774, 0.8867] | 1406 → 1406 |
| maintenance d4/10% | atomic_mixed | 78.822 | 44.268 | 0.5616 [0.3752, 0.9389] | 0.7138 [0.574, 0.9319] | 5075 → 5075 |
| maintenance d4/15% | fact_delete | 115.920 | 47.382 | 0.4087 [0.3903, 0.4679] | 0.7536 [0.6722, 0.8757] | 3822 → 3822 |
| maintenance d4/15% | fact_insert | 24.074 | 30.287 | 1.258 [0.4753, 1.633] | 0.5885 [0.5412, 0.718] | 0 → 0 |
| maintenance d4/15% | rule_insert | 38.753 | 17.273 | 0.4457 [0.4354, 1.024] | 0.7195 [0.5803, 0.7662] | 0 → 0 |
| maintenance d4/15% | rule_delete | 60.045 | 27.598 | 0.4596 [0.2453, 0.9161] | 0.7701 [0.5909, 0.8683] | 1342 → 1342 |
| maintenance d4/15% | rule_replace | 104.455 | 30.632 | 0.2933 [0.2684, 0.5388] | 0.8629 [0.6509, 0.9631] | 1332 → 1332 |
| maintenance d4/15% | atomic_mixed | 117.141 | 47.976 | 0.4096 [0.3789, 0.6475] | 0.8764 [0.5885, 0.989] | 5657 → 5657 |
| maintenance d5/10% | fact_delete | 634.307 | 300.636 | 0.474 [0.4034, 0.5649] | 0.7572 [0.5831, 0.8704] | 14744 → 14744 |
| maintenance d5/10% | fact_insert | 290.468 | 50.445 | 0.1737 [0.1335, 0.7506] | 0.7051 [0.5695, 0.7698] | 0 → 0 |
| maintenance d5/10% | rule_insert | 219.359 | 225.281 | 1.027 [0.4065, 1.15] | 0.6943 [0.6123, 0.7926] | 0 → 0 |
| maintenance d5/10% | rule_delete | 685.817 | 181.603 | 0.2648 [0.2155, 0.4287] | 0.7105 [0.595, 0.7319] | 7000 → 7000 |
| maintenance d5/10% | rule_replace | 417.815 | 200.632 | 0.4802 [0.2414, 0.525] | 0.719 [0.6036, 0.8974] | 7088 → 7088 |
| maintenance d5/10% | atomic_mixed | 771.007 | 284.407 | 0.3689 [0.322, 0.5999] | 0.6518 [0.5742, 0.9349] | 26362 → 26362 |
| maintenance d5/15% | fact_delete | 569.547 | 323.807 | 0.5685 [0.4983, 0.5963] | 0.593 [0.5434, 0.7819] | 22162 → 22162 |
| maintenance d5/15% | fact_insert | 147.132 | 73.498 | 0.4995 [0.2127, 1.618] | 0.643 [0.5559, 0.7133] | 0 → 0 |
| maintenance d5/15% | rule_insert | 219.218 | 102.014 | 0.4654 [0.2098, 1.147] | 0.6604 [0.4824, 0.7551] | 0 → 0 |
| maintenance d5/15% | rule_delete | 421.620 | 184.084 | 0.4366 [0.2555, 0.8994] | 0.6326 [0.5663, 0.6996] | 6580 → 6580 |
| maintenance d5/15% | rule_replace | 749.609 | 202.974 | 0.2708 [0.2226, 0.9202] | 0.6472 [0.607, 0.7421] | 6670 → 6670 |
| maintenance d5/15% | atomic_mixed | 817.228 | 303.521 | 0.3714 [0.2989, 0.597] | 0.7173 [0.6422, 0.7532] | 29778 → 29778 |

Matched 51 cases; excluded 3 new or changed cases. The raw report records each exclusion reason. No workload or reference timing is rewritten to obtain a match.

These workloads use the Bach worked examples and synthetic inputs inspired by thesis chapter 8, not a reproduction of the 2004 KAON/XSB/Racer measurements. Modern hardware, execution strategies and measurement boundaries differ. OWL RL includes additional axiomatic/schema triples, so its total closure count is not directly comparable; the named instance answers are verified.

The naive strategy shares the compiler and equality machinery; it is an execution baseline, not an independent semantic oracle. Unit validation also uses OWL RL and exhaustive finite models. There is no performance acceptance threshold or claim of production-scale throughput.

## Bach Table 2.5 (Turtle): checked queries

Source: `examples/bach.ttl`; profile L3. Parsing measures the original document syntax. Query ms in the summary is the total of all queries below.

| Query | Thesis reference | Answer | Median ms |
|---|---|---|---:|
| fathers | Table 2.5 T5/A1–A4/A7, p. 35; §5.4.2.2, p. 132 | `["johann-ambrosius", "johann-sebastian"]` | 0.020 |
| mothers | Table 2.5 T6, p. 35; §5.4.2.2, p. 132 | `[]` | 0.011 |
| people | Table 2.5 T1/T2/T5, p. 35; §5.4.2.2, p. 132 | `["anna-magdalena", "johann-ambrosius", "johann-sebastian", "maria-barbara", "wilhelm-friedemann"]` | 0.027 |
| masterpieces | Table 2.5 T11/A2/A9/A10, p. 35 | `["BWV248"]` | 0.012 |
| birthday-cantatas | Table 2.5 A14/A15, p. 35 | `["BWV213", "BWV214"]` | 0.012 |
| compositions | Table 2.5 T12–T15/A13–A15, p. 35 | `["BWV213", "BWV214", "BWV248"]` | 0.012 |
| named-birthdays | Table 2.5 T12/A14/A15, p. 35; Example 4.5.2, p. 94 | `[]` | 0.017 |
| leipzig-inhabitants | Table 2.5 T10/A8, p. 35 | `["johann-sebastian"]` | 0.011 |
| wives | Table 2.5 T3/A5/A6/A11/A12, p. 35 | `[]` | 0.009 |
| ambrosius-is-father | Table 2.5 T5/A1/A7, p. 35; §5.4.2.1, p. 132 | `true` | 0.011 |
| ambrosius-named-son-not-entailed | Table 2.5 A1, p. 35; Example 4.5.2, p. 94 | `false` | 0.008 |
| sebastian-known-children | Example 5.4.1, p. 131; §5.4.3, pp. 134–135 | `["wilhelm-friedemann"]` | 0.017 |
| sebastian-marriages | Table 2.5 A6/A12, p. 35; §5.4.3, pp. 134–135 | `["anna-magdalena", "maria-barbara"]` | 0.013 |
| symmetric-marriage | Table 2.5 T9/A6, p. 35; §5.4.3, pp. 134–135 | `["johann-sebastian"]` | 0.012 |
| sebastian-types | §5.4.2.3, p. 134; Table 2.5, p. 35 | `["Composer", "Father", "Genius", "LeipzigInhabitant", "Man", "Person", "owl:Thing"]` | 0.014 |
| male-child-existential | Example 4.5.2, p. 94; §5.4.2, pp. 132–133 | `["johann-ambrosius"]` | 8.742 |
| child-filler-intersection-union | Adapted Example 5.4.2, pp. 133–134; explicit filler scope | `["johann-ambrosius"]` | 9.085 |
| person-subsumes-father | Example 2.4.3, p. 39; §5.4.4.1, p. 135 | `true` | 0.060 |
| father-does-not-subsume-person | §5.4.4.1, pp. 135–136; Table 2.5 T5, p. 35 | `false` | 4.403 |
| composition-subsumes-birthday-cantata | Table 2.5 T12–T15, p. 35; §5.4.4.1, pp. 135–136 | `true` | 0.009 |
| father-satisfiable | Example 2.4.3, p. 39; §5.4.4.4, pp. 137–138 | `true` | 4.150 |
| ancestor-subsumes-child | Table 2.5 T7, p. 35; §5.4.4.5, pp. 138–139 | `true` | 0.007 |
| ancestor-transitive | Table 2.5 T8, p. 35; §5.4.4.6, p. 140 | `true` | 0.004 |
| marriage-symmetric | Table 2.5 T9, p. 35; §5.4.4.6, pp. 139–140 | `true` | 0.003 |
| dynasty-not-transitive | Table 2.5 T16/T17, p. 35; §6.2.2, p. 151 (corrected) | `false` | 4.059 |

## Bach Table 2.5 (RDF/XML): checked queries

Source: `examples/bach.owl`; profile L3. Parsing measures the original document syntax. Query ms in the summary is the total of all queries below.

| Query | Thesis reference | Answer | Median ms |
|---|---|---|---:|
| fathers | Table 2.5 T5/A1–A4/A7, p. 35; §5.4.2.2, p. 132 | `["johann-ambrosius", "johann-sebastian"]` | 0.020 |
| mothers | Table 2.5 T6, p. 35; §5.4.2.2, p. 132 | `[]` | 0.011 |
| people | Table 2.5 T1/T2/T5, p. 35; §5.4.2.2, p. 132 | `["anna-magdalena", "johann-ambrosius", "johann-sebastian", "maria-barbara", "wilhelm-friedemann"]` | 0.027 |
| masterpieces | Table 2.5 T11/A2/A9/A10, p. 35 | `["BWV248"]` | 0.012 |
| birthday-cantatas | Table 2.5 A14/A15, p. 35 | `["BWV213", "BWV214"]` | 0.012 |
| compositions | Table 2.5 T12–T15/A13–A15, p. 35 | `["BWV213", "BWV214", "BWV248"]` | 0.012 |
| named-birthdays | Table 2.5 T12/A14/A15, p. 35; Example 4.5.2, p. 94 | `[]` | 0.017 |
| leipzig-inhabitants | Table 2.5 T10/A8, p. 35 | `["johann-sebastian"]` | 0.011 |
| wives | Table 2.5 T3/A5/A6/A11/A12, p. 35 | `[]` | 0.009 |
| ambrosius-is-father | Table 2.5 T5/A1/A7, p. 35; §5.4.2.1, p. 132 | `true` | 0.011 |
| ambrosius-named-son-not-entailed | Table 2.5 A1, p. 35; Example 4.5.2, p. 94 | `false` | 0.008 |
| sebastian-known-children | Example 5.4.1, p. 131; §5.4.3, pp. 134–135 | `["wilhelm-friedemann"]` | 0.017 |
| sebastian-marriages | Table 2.5 A6/A12, p. 35; §5.4.3, pp. 134–135 | `["anna-magdalena", "maria-barbara"]` | 0.013 |
| symmetric-marriage | Table 2.5 T9/A6, p. 35; §5.4.3, pp. 134–135 | `["johann-sebastian"]` | 0.011 |
| sebastian-types | §5.4.2.3, p. 134; Table 2.5, p. 35 | `["Composer", "Father", "Genius", "LeipzigInhabitant", "Man", "Person", "owl:Thing"]` | 0.014 |
| male-child-existential | Example 4.5.2, p. 94; §5.4.2, pp. 132–133 | `["johann-ambrosius"]` | 8.817 |
| child-filler-intersection-union | Adapted Example 5.4.2, pp. 133–134; explicit filler scope | `["johann-ambrosius"]` | 9.003 |
| person-subsumes-father | Example 2.4.3, p. 39; §5.4.4.1, p. 135 | `true` | 0.066 |
| father-does-not-subsume-person | §5.4.4.1, pp. 135–136; Table 2.5 T5, p. 35 | `false` | 4.274 |
| composition-subsumes-birthday-cantata | Table 2.5 T12–T15, p. 35; §5.4.4.1, pp. 135–136 | `true` | 0.008 |
| father-satisfiable | Example 2.4.3, p. 39; §5.4.4.4, pp. 137–138 | `true` | 4.159 |
| ancestor-subsumes-child | Table 2.5 T7, p. 35; §5.4.4.5, pp. 138–139 | `true` | 0.008 |
| ancestor-transitive | Table 2.5 T8, p. 35; §5.4.4.6, p. 140 | `true` | 0.004 |
| marriage-symmetric | Table 2.5 T9, p. 35; §5.4.4.6, pp. 139–140 | `true` | 0.003 |
| dynasty-not-transitive | Table 2.5 T16/T17, p. 35; §6.2.2, p. 151 (corrected) | `false` | 4.068 |

## Bach family maintenance (Turtle): checked queries

Source: `examples/bach-family.ttl`; profile L0. Parsing measures the original document syntax. Query ms in the summary is the total of all queries below.

| Query | Thesis reference | Answer | Median ms |
|---|---|---|---:|
| johannes-descendants | Figure 6.2, p. 150; Example 6.3.2, p. 158 | `["christoph", "heinrich", "johann-ambrosius", "johann-christoph", "johann-michael", "johann-sebastian", "maria-barbara", "wilhelm-friedemann"]` | 0.021 |
| ambrosius-descendants | Figure 6.2; §6.2.1, p. 150 | `["johann-sebastian", "wilhelm-friedemann"]` | 0.012 |
| johannes-reaches-wilhelm | Figure 6.2; §6.2.1, p. 150 | `true` | 0.010 |
| base-dynasty-not-symmetric | Table 6.1; §6.2.2, p. 151 | `false` | 1.031 |
| base-dynasty-not-transitive | Table 6.1; §6.2.2, p. 151 | `false` | 1.088 |
| base-ancestor-transitive | Table 6.1 T1, p. 151 | `true` | 0.005 |
| base-cross-branch-not-entailed | §6.2.2, p. 151; docs/THESIS_ERRATA.md item 6 | `false` | 0.009 |

Bach updates each start from the original family graph. Both RDF update and fresh rebuild timings include compilation. Exact pair sets and the three removed/four added ancestor pairs are checked against independent graph traversal and recorded in JSON.
