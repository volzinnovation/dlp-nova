# Measured benchmark results

Run: 2026-09-09T12:17:42.674335+00:00. Python 3.12.9; macOS-26.5.1-arm64-arm-64bit.

Measured checkout: `b1254c441731ca4fdf32ea83570ff99aaa84ac2a`; dirty: True. Exact measured source hashes and checkout status are in the raw report.

Recorded: 54 validated cases, 0 errors, 54 planned cases. Repetitions per case: 5.

All times below are medians in milliseconds. Every raw sample is in `results.json`.
Peak RSS is the entire isolated worker (including parser, retained input and repetitions), not incremental reasoner allocation. Compiler and materializer timings are separate.

| Workload | Engine | Input triples | Closure facts | Compile ms | Materialize ms | Query ms | Peak MiB |
|---|---|---:|---:|---:|---:|---:|---:|
| taxonomy d3/i3/P0 | semi-naive | 196 | 541 | 1.883 | 2.674 | 0.183 | 37.3 |
| taxonomy d3/i3/P1 | semi-naive | 275 | 580 | 2.716 | 2.973 | 0.203 | 38.7 |
| taxonomy d3/i3/PF | semi-naive | 513 | 658 | 4.995 | 3.785 | 0.226 | 42.2 |
| taxonomy d3/i9/P0 | semi-naive | 430 | 1621 | 4.063 | 7.427 | 0.529 | 41.7 |
| taxonomy d3/i9/P1 | semi-naive | 587 | 1738 | 5.880 | 8.462 | 0.599 | 43.1 |
| taxonomy d3/i9/PF | semi-naive | 981 | 1972 | 9.780 | 10.457 | 0.671 | 50.3 |
| taxonomy d3/i15/P0 | semi-naive | 664 | 2701 | 6.219 | 11.916 | 0.891 | 44.6 |
| taxonomy d3/i15/P1 | semi-naive | 899 | 2896 | 8.918 | 13.929 | 1.043 | 49.3 |
| taxonomy d3/i15/PF | semi-naive | 1449 | 3286 | 14.914 | 17.204 | 1.140 | 56.1 |
| taxonomy d5/i3/P0 | semi-naive | 1816 | 7102 | 17.746 | 39.423 | 2.070 | 60.7 |
| taxonomy d5/i3/P1 | semi-naive | 2543 | 7465 | 25.353 | 51.080 | 2.327 | 65.8 |
| taxonomy d5/i3/PF | semi-naive | 3105 | 8191 | 31.820 | 45.231 | 2.466 | 71.2 |
| taxonomy d5/i9/P0 | semi-naive | 3994 | 21304 | 36.685 | 115.118 | 6.372 | 90.5 |
| taxonomy d5/i9/P1 | semi-naive | 5447 | 22393 | 54.351 | 142.476 | 7.599 | 105.4 |
| taxonomy d5/i9/PF | semi-naive | 7461 | 24571 | 85.023 | 162.226 | 7.668 | 120.4 |
| taxonomy d5/i15/P0 | semi-naive | 6172 | 35506 | 84.667 | 238.030 | 12.074 | 128.9 |
| taxonomy d5/i15/P1 | semi-naive | 8351 | 37321 | 91.361 | 284.075 | 13.481 | 148.5 |
| taxonomy d5/i15/PF | semi-naive | 11817 | 40951 | 155.883 | 294.467 | 14.122 | 174.5 |
| taxonomy d7/i3/P0 | semi-naive | 16396 | 83647 | 226.382 | 617.860 | 28.611 | 240.3 |
| taxonomy d7/i3/P1 | semi-naive | 22955 | 86926 | 233.271 | 726.870 | 30.772 | 302.4 |
| taxonomy d7/i3/PF | semi-naive | 26433 | 93484 | 289.163 | 816.582 | 35.284 | 343.0 |
| taxonomy d7/i9/P0 | semi-naive | 36070 | 250939 | 348.702 | 2088.887 | 82.227 | 568.1 |
| taxonomy d7/i9/P1 | semi-naive | 49187 | 260776 | 510.707 | 2260.063 | 89.168 | 655.0 |
| taxonomy d7/i9/PF | semi-naive | 65781 | 280450 | 752.714 | 2821.851 | 109.312 | 814.7 |
| taxonomy d7/i15/P0 | semi-naive | 55744 | 418231 | 809.647 | 3737.269 | 199.171 | 903.7 |
| taxonomy d7/i15/P1 | semi-naive | 75419 | 434626 | 880.510 | 3970.123 | 207.613 | 1004.5 |
| taxonomy d7/i15/PF | semi-naive | 105129 | 467416 | 1249.815 | 4388.391 | 238.684 | 1256.0 |
| taxonomy d3/i3/P0 | naive | 196 | 541 | 1.905 | 3.792 | 0.184 | 37.2 |
| taxonomy d3/i3/P0 | owlrl | 196 | 1105 | 0.000 | 93.312 | 0.067 | 37.8 |
| equality 100 | semi-naive | 302 | 601 | 3.301 | 11.399 | 0.436 | 39.7 |
| equality 1000 | semi-naive | 3002 | 6001 | 32.593 | 127.478 | 4.903 | 73.0 |
| existential 100 | semi-naive | 112 | 1401 | 1.289 | 76.768 | 6.664 | 39.3 |
| transitive 100 | semi-naive | 101 | 5152 | 1.952 | 710.512 | 19.323 | 48.5 |
| cardinality d3/i3 | semi-naive | 560 | 1057 | 10.860 | 22.129 | 0.630 | 42.5 |
| cardinality d5/i3 | semi-naive | 5204 | 13288 | 118.473 | 367.386 | 9.814 | 92.3 |
| cardinality d7/i3 | semi-naive | 47000 | 152527 | 747.375 | 3019.994 | 72.760 | 557.6 |
| cardinality d5/i9 | semi-naive | 10286 | 39862 | 134.976 | 727.454 | 20.568 | 164.2 |
| factored unions 4 pairs/128 subjects | semi-naive | 638 | 1281 | 6.042 | 6.287 | 0.267 | 41.7 |
| factored unions 8 pairs/128 subjects | semi-naive | 1178 | 2305 | 10.970 | 10.985 | 0.378 | 46.1 |
| factored unions 16 pairs/128 subjects | semi-naive | 2258 | 4353 | 21.756 | 32.413 | 0.568 | 56.3 |
| factored unions 32 pairs/128 subjects | semi-naive | 4418 | 8449 | 50.156 | 48.117 | 1.163 | 68.1 |
| factored unions 64 pairs/128 subjects | semi-naive | 8738 | 16641 | 109.897 | 119.371 | 2.367 | 104.2 |
| factored enumerations 16 pairs/128 subjects | semi-naive | 258 | 54 | 3.374 | 2.679 | 0.189 | 38.0 |
| factored enumerations 32 pairs/128 subjects | semi-naive | 386 | 102 | 5.225 | 3.982 | 0.221 | 41.0 |
| factored enumerations 64 pairs/128 subjects | semi-naive | 642 | 198 | 9.407 | 6.059 | 0.288 | 43.5 |
| maintenance d3/10% | semi-naive | 1096 | 4331 | 16.616 | 26.154 | 1.602 | 50.8 |
| maintenance d3/15% | semi-naive | 1096 | 4331 | 14.446 | 20.722 | 1.339 | 50.3 |
| maintenance d4/10% | semi-naive | 5471 | 25581 | 73.357 | 157.530 | 7.925 | 120.6 |
| maintenance d4/15% | semi-naive | 5471 | 25581 | 74.086 | 152.377 | 8.155 | 120.8 |
| maintenance d5/10% | semi-naive | 27346 | 147456 | 396.340 | 1428.643 | 53.062 | 499.6 |
| maintenance d5/15% | semi-naive | 27346 | 147456 | 314.615 | 1335.744 | 51.280 | 490.0 |
| Bach Table 2.5 (Turtle) | semi-naive | 164 | 99 | 3.154 | 1.513 | 45.778 | 43.2 |
| Bach Table 2.5 (RDF/XML) | semi-naive | 164 | 99 | 2.545 | 1.434 | 41.524 | 43.4 |
| Bach family maintenance (Turtle) | semi-naive | 25 | 58 | 0.245 | 0.668 | 3.420 | 36.9 |

## Additional query timings

| Workload | Property pairs ms | Subsumption ms |
|---|---:|---:|
| taxonomy d3/i3/P0 | 0.064 | 0.062 |
| taxonomy d3/i3/P1 | 0.070 | 0.064 |
| taxonomy d3/i3/PF | 0.081 | 0.065 |
| taxonomy d3/i9/P0 | 0.184 | 0.067 |
| taxonomy d3/i9/P1 | 0.218 | 0.064 |
| taxonomy d3/i9/PF | 0.241 | 0.066 |
| taxonomy d3/i15/P0 | 0.312 | 0.072 |
| taxonomy d3/i15/P1 | 0.373 | 0.073 |
| taxonomy d3/i15/PF | 0.392 | 0.072 |
| taxonomy d5/i3/P0 | 0.879 | 0.628 |
| taxonomy d5/i3/P1 | 0.924 | 0.648 |
| taxonomy d5/i3/PF | 1.027 | 0.633 |
| taxonomy d5/i9/P0 | 2.639 | 0.740 |
| taxonomy d5/i9/P1 | 3.055 | 0.811 |
| taxonomy d5/i9/PF | 3.129 | 0.829 |
| taxonomy d5/i15/P0 | 5.222 | 0.875 |
| taxonomy d5/i15/P1 | 5.391 | 0.917 |
| taxonomy d5/i15/PF | 5.430 | 1.054 |
| taxonomy d7/i3/P0 | 13.650 | 6.433 |
| taxonomy d7/i3/P1 | 12.895 | 6.838 |
| taxonomy d7/i3/PF | 14.814 | 6.848 |
| taxonomy d7/i9/P0 | 44.457 | 8.491 |
| taxonomy d7/i9/P1 | 45.896 | 9.156 |
| taxonomy d7/i9/PF | 53.712 | 9.976 |
| taxonomy d7/i15/P0 | 102.336 | 10.858 |
| taxonomy d7/i15/P1 | 103.339 | 13.114 |
| taxonomy d7/i15/PF | 99.931 | 12.339 |
| taxonomy d3/i3/P0 | 0.064 | 0.063 |

## Incremental maintenance

Every operation is checked against a fresh closure from separately tracked facts and rules. Synthetic maintenance uses precompiled Engine inputs, excluding recompilation from both timings. Bach uses RDF updates and includes compilation in both timings.

| Workload | Operation | Update ms | Fresh rebuild ms | Observed method |
|---|---|---:|---:|---|
| maintenance d3/10% | fact_delete | 17.727 | 23.527 | dred |
| maintenance d3/10% | fact_insert | 4.243 | 32.089 | incremental-insert |
| maintenance d3/10% | rule_insert | 8.143 | 32.725 | incremental-rules |
| maintenance d3/10% | rule_delete | 13.291 | 35.515 | dred-rules |
| maintenance d3/10% | rule_replace | 15.694 | 29.540 | dred-rules |
| maintenance d3/10% | atomic_mixed | 20.046 | 33.234 | dred-rules |
| maintenance d3/15% | fact_delete | 17.971 | 18.549 | dred |
| maintenance d3/15% | fact_insert | 4.238 | 21.622 | incremental-insert |
| maintenance d3/15% | rule_insert | 7.039 | 30.783 | incremental-rules |
| maintenance d3/15% | rule_delete | 10.123 | 29.646 | dred-rules |
| maintenance d3/15% | rule_replace | 10.667 | 22.822 | dred-rules |
| maintenance d3/15% | atomic_mixed | 12.972 | 25.408 | dred-rules |
| maintenance d4/10% | fact_delete | 93.021 | 142.055 | dred |
| maintenance d4/10% | fact_insert | 18.946 | 186.124 | incremental-insert |
| maintenance d4/10% | rule_insert | 38.283 | 217.335 | incremental-rules |
| maintenance d4/10% | rule_delete | 57.883 | 215.112 | dred-rules |
| maintenance d4/10% | rule_replace | 64.010 | 199.756 | dred-rules |
| maintenance d4/10% | atomic_mixed | 76.894 | 193.840 | dred-rules |
| maintenance d4/15% | fact_delete | 102.365 | 137.084 | dred |
| maintenance d4/15% | fact_insert | 24.296 | 179.914 | incremental-insert |
| maintenance d4/15% | rule_insert | 40.756 | 212.747 | incremental-rules |
| maintenance d4/15% | rule_delete | 58.764 | 213.792 | dred-rules |
| maintenance d4/15% | rule_replace | 60.486 | 204.850 | dred-rules |
| maintenance d4/15% | atomic_mixed | 107.416 | 174.062 | dred-rules |
| maintenance d5/10% | fact_delete | 687.888 | 1343.581 | dred |
| maintenance d5/10% | fact_insert | 121.534 | 1339.024 | incremental-insert |
| maintenance d5/10% | rule_insert | 372.468 | 1658.109 | incremental-rules |
| maintenance d5/10% | rule_delete | 598.605 | 1612.715 | dred-rules |
| maintenance d5/10% | rule_replace | 725.576 | 1412.292 | dred-rules |
| maintenance d5/10% | atomic_mixed | 709.321 | 1299.353 | dred-rules |
| maintenance d5/15% | fact_delete | 676.341 | 1272.287 | dred |
| maintenance d5/15% | fact_insert | 173.106 | 1408.724 | incremental-insert |
| maintenance d5/15% | rule_insert | 380.343 | 1438.865 | incremental-rules |
| maintenance d5/15% | rule_delete | 666.594 | 1502.175 | dred-rules |
| maintenance d5/15% | rule_replace | 406.264 | 1396.978 | dred-rules |
| maintenance d5/15% | atomic_mixed | 773.958 | 1387.384 | dred-rules |
| Bach family maintenance (Turtle) | facts_update | 1.032 | 1.223 | dred |
| Bach family maintenance (Turtle) | rule_delete | 0.711 | 0.965 | dred-rules |
| Bach family maintenance (Turtle) | symmetry_insert | 0.859 | 1.424 | incremental-rules |

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
| unionOf | 4 | 16 | 10 | 1 | 6.042 |
| unionOf | 8 | 256 | 18 | 1 | 10.970 |
| unionOf | 16 | 65536 | 34 | 1 | 21.756 |
| unionOf | 32 | 4294967296 | 66 | 1 | 50.156 |
| unionOf | 64 | 18446744073709551616 | 130 | 1 | 109.897 |
| oneOf | 16 | 65536 | 34 | 1 | 3.374 |
| oneOf | 32 | 4294967296 | 66 | 1 | 5.225 |
| oneOf | 64 | 18446744073709551616 | 130 | 1 | 9.407 |

## Before/after comparison on unchanged inputs

Baseline: `/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/benchmarks/baselines/b1254c4/results.json`, run 2026-09-09T11:35:50.349359+00:00. Reference commit: `b1254c441731ca4fdf32ea83570ff99aaa84ac2a`. Rows require identical case controls, input hashes and timing boundaries. Different source hashes are retained in JSON for attribution. Ratios below 1 mean a shorter current median. Brackets show deterministic 95% percentile bootstrap intervals for the ratio of medians, resampling the recorded observations. With five repetitions in one worker per case, these are descriptive sensitivity intervals, not guarantees of independent-run coverage or causal speedup. They omit between-run machine-load/drift effects.

Cross-version correctness checks passed for 51/51 matched cases: initial fact counts, expected query-answer checks, and maintenance closure counts. The historical report does not store full answer-set digests.

| Workload | Engine | Previous materialize ms | Current materialize ms | Ratio [interval] | Candidate rows before → after |
|---|---|---:|---:|---:|---:|
| taxonomy d3/i3/P0 | semi-naive | 3.089 | 2.674 | 0.8655 [0.7973, 1.102] | 306 → 306 |
| taxonomy d3/i3/P1 | semi-naive | 2.973 | 2.973 | 0.9999 [0.8777, 1.114] | 306 → 306 |
| taxonomy d3/i3/PF | semi-naive | 3.884 | 3.785 | 0.9746 [0.8855, 1.042] | 306 → 306 |
| taxonomy d3/i9/P0 | semi-naive | 7.731 | 7.427 | 0.9607 [0.918, 1.641] | 918 → 918 |
| taxonomy d3/i9/P1 | semi-naive | 8.843 | 8.462 | 0.9569 [0.5881, 1.512] | 918 → 918 |
| taxonomy d3/i9/PF | semi-naive | 11.003 | 10.457 | 0.9504 [0.4622, 1.437] | 918 → 918 |
| taxonomy d3/i15/P0 | semi-naive | 12.620 | 11.916 | 0.9442 [0.9308, 1.014] | 1530 → 1530 |
| taxonomy d3/i15/P1 | semi-naive | 14.439 | 13.929 | 0.9647 [0.5312, 1.351] | 1530 → 1530 |
| taxonomy d3/i15/PF | semi-naive | 17.561 | 17.204 | 0.9797 [0.9314, 1.031] | 1530 → 1530 |
| taxonomy d5/i3/P0 | semi-naive | 36.123 | 39.423 | 1.091 [0.7572, 1.336] | 4923 → 4923 |
| taxonomy d5/i3/P1 | semi-naive | 58.334 | 51.080 | 0.8756 [0.6631, 1.286] | 4923 → 4923 |
| taxonomy d5/i3/PF | semi-naive | 60.895 | 45.231 | 0.7428 [0.6291, 1.278] | 4923 → 4923 |
| taxonomy d5/i9/P0 | semi-naive | 141.331 | 115.118 | 0.8145 [0.7123, 1.065] | 14769 → 14769 |
| taxonomy d5/i9/P1 | semi-naive | 137.726 | 142.476 | 1.034 [0.8631, 1.273] | 14769 → 14769 |
| taxonomy d5/i9/PF | semi-naive | 161.332 | 162.226 | 1.006 [0.8044, 1.208] | 14769 → 14769 |
| taxonomy d5/i15/P0 | semi-naive | 238.712 | 238.030 | 0.9971 [0.8341, 1.137] | 24615 → 24615 |
| taxonomy d5/i15/P1 | semi-naive | 268.182 | 284.075 | 1.059 [0.8824, 1.24] | 24615 → 24615 |
| taxonomy d5/i15/PF | semi-naive | 268.046 | 294.467 | 1.099 [0.9023, 1.237] | 24615 → 24615 |
| taxonomy d7/i3/P0 | semi-naive | 675.359 | 617.860 | 0.9149 [0.7823, 1.068] | 63972 → 63972 |
| taxonomy d7/i3/P1 | semi-naive | 822.431 | 726.870 | 0.8838 [0.7542, 1.234] | 63972 → 63972 |
| taxonomy d7/i3/PF | semi-naive | 914.899 | 816.582 | 0.8925 [0.8253, 1.023] | 63972 → 63972 |
| taxonomy d7/i9/P0 | semi-naive | 2068.547 | 2088.887 | 1.01 [0.8311, 1.106] | 191916 → 191916 |
| taxonomy d7/i9/P1 | semi-naive | 4044.267 | 2260.063 | 0.5588 [0.1855, 0.6386] | 191916 → 191916 |
| taxonomy d7/i9/PF | semi-naive | 3602.462 | 2821.851 | 0.7833 [0.6355, 1.037] | 191916 → 191916 |
| taxonomy d7/i15/P0 | semi-naive | 4866.225 | 3737.269 | 0.768 [0.3476, 1.036] | 319860 → 319860 |
| taxonomy d7/i15/P1 | semi-naive | 4299.402 | 3970.123 | 0.9234 [0.7744, 1.028] | 319860 → 319860 |
| taxonomy d7/i15/PF | semi-naive | 4860.310 | 4388.391 | 0.9029 [0.5751, 1.01] | 319860 → 319860 |
| taxonomy d3/i3/P0 | naive | 3.595 | 3.792 | 1.055 [0.4896, 1.254] | 954 → 954 |
| taxonomy d3/i3/P0 | owlrl | 99.400 | 93.312 | 0.9388 [0.9213, 0.9682] | — |
| equality 100 | semi-naive | 12.141 | 11.399 | 0.9389 [0.6779, 0.9527] | 1800 → 1800 |
| equality 1000 | semi-naive | 137.208 | 127.478 | 0.9291 [0.825, 1.163] | 18000 → 18000 |
| existential 100 | semi-naive | 69.623 | 76.768 | 1.103 [0.9816, 1.428] | 800 → 800 |
| transitive 100 | semi-naive | 451.250 | 710.512 | 1.575 [1.007, 1.958] | 204656 → 204656 |
| cardinality d3/i3 | semi-naive | 20.620 | 22.129 | 1.073 [1.006, 1.42] | 3900 → 3900 |
| cardinality d5/i3 | semi-naive | 243.571 | 367.386 | 1.508 [0.9779, 2.701] | 41250 → 41250 |
| cardinality d7/i3 | semi-naive | 2942.138 | 3019.994 | 1.026 [0.9379, 1.17] | 416424 → 416424 |
| cardinality d5/i9 | semi-naive | 941.582 | 727.454 | 0.7726 [0.5138, 1.064] | 123750 → 123750 |
| factored unions 4 pairs/128 subjects | semi-naive | 14.022 | 6.287 | 0.4483 [0.3534, 0.608] | 2112 → 672 |
| factored unions 8 pairs/128 subjects | semi-naive | 57.850 | 10.985 | 0.1899 [0.1846, 0.2478] | 7232 → 1184 |
| factored unions 16 pairs/128 subjects | semi-naive | 301.281 | 32.413 | 0.1076 [0.06911, 0.221] | 26688 → 2208 |
| factored unions 32 pairs/128 subjects | semi-naive | 1663.508 | 48.117 | 0.02893 [0.01956, 0.03841] | 102464 → 4256 |
| factored unions 64 pairs/128 subjects | semi-naive | 10406.030 | 119.371 | 0.01147 [0.009205, 0.01293] | 401472 → 8352 |
| factored enumerations 16 pairs/128 subjects | semi-naive | 4.340 | 2.679 | 0.6173 [0.6013, 0.6727] | 305 → 34 |
| factored enumerations 32 pairs/128 subjects | semi-naive | 15.561 | 3.982 | 0.2559 [0.2426, 0.2598] | 1121 → 66 |
| factored enumerations 64 pairs/128 subjects | semi-naive | 95.863 | 6.059 | 0.06321 [0.05944, 0.0678] | 4289 → 130 |
| maintenance d3/10% | semi-naive | 22.419 | 26.154 | 1.167 [0.7963, 1.509] | 3080 → 3080 |
| maintenance d3/15% | semi-naive | 21.925 | 20.722 | 0.9451 [0.5774, 1.459] | 3080 → 3080 |
| maintenance d4/10% | semi-naive | 167.815 | 157.530 | 0.9387 [0.7973, 1.219] | 19330 → 19330 |
| maintenance d4/15% | semi-naive | 193.323 | 152.377 | 0.7882 [0.7552, 0.9689] | 19330 → 19330 |
| maintenance d5/10% | semi-naive | 1281.996 | 1428.643 | 1.114 [0.585, 2.262] | 116205 → 116205 |
| maintenance d5/15% | semi-naive | 1649.397 | 1335.744 | 0.8098 [0.6515, 1.485] | 116205 → 116205 |

### Parsing, compilation and public query calls

Subsumption still times the complete first public call on each fresh reasoner. A lazy schema index or fast path built inside that call remains inside the timing. It is not silently excluded as setup. All phase samples remain available in JSON.

| Workload / engine | Phase | Previous ms | Current ms | Ratio [interval] |
|---|---|---:|---:|---:|
| taxonomy d3/i3/P0 / semi-naive | parse | 1.756 | 1.642 | 0.9354 [0.6618, 1.446] |
| taxonomy d3/i3/P0 / semi-naive | compile | 1.859 | 1.883 | 1.013 [0.9302, 1.231] |
| taxonomy d3/i3/P0 / semi-naive | query | 0.179 | 0.183 | 1.024 [0.9542, 1.069] |
| taxonomy d3/i3/P0 / semi-naive | property_query | 0.062 | 0.064 | 1.029 [0.9885, 1.066] |
| taxonomy d3/i3/P0 / semi-naive | subsumption | 7.130 | 0.062 | 0.008748 [0.005789, 0.01034] |
| taxonomy d3/i3/P1 / semi-naive | parse | 2.391 | 2.300 | 0.9619 [0.7241, 1.292] |
| taxonomy d3/i3/P1 / semi-naive | compile | 2.624 | 2.716 | 1.035 [0.8414, 1.112] |
| taxonomy d3/i3/P1 / semi-naive | query | 0.199 | 0.203 | 1.02 [0.9712, 1.039] |
| taxonomy d3/i3/P1 / semi-naive | property_query | 0.071 | 0.070 | 0.9877 [0.9578, 1.021] |
| taxonomy d3/i3/P1 / semi-naive | subsumption | 8.712 | 0.064 | 0.007399 [0.004754, 0.008308] |
| taxonomy d3/i3/PF / semi-naive | parse | 5.054 | 4.465 | 0.8833 [0.8088, 1.091] |
| taxonomy d3/i3/PF / semi-naive | compile | 4.729 | 4.995 | 1.056 [0.4919, 2.217] |
| taxonomy d3/i3/PF / semi-naive | query | 0.228 | 0.226 | 0.9901 [0.9741, 1.035] |
| taxonomy d3/i3/PF / semi-naive | property_query | 0.083 | 0.081 | 0.969 [0.9445, 1.009] |
| taxonomy d3/i3/PF / semi-naive | subsumption | 13.080 | 0.065 | 0.00495 [0.004599, 0.005521] |
| taxonomy d3/i9/P0 / semi-naive | parse | 4.173 | 3.683 | 0.8827 [0.8209, 1.118] |
| taxonomy d3/i9/P0 / semi-naive | compile | 4.004 | 4.063 | 1.015 [0.9403, 1.095] |
| taxonomy d3/i9/P0 / semi-naive | query | 0.540 | 0.529 | 0.9803 [0.9052, 1.027] |
| taxonomy d3/i9/P0 / semi-naive | property_query | 0.189 | 0.184 | 0.9744 [0.7983, 0.9871] |
| taxonomy d3/i9/P0 / semi-naive | subsumption | 17.337 | 0.067 | 0.003872 [0.002621, 0.004325] |
| taxonomy d3/i9/P1 / semi-naive | parse | 4.942 | 4.887 | 0.9888 [0.8024, 1.206] |
| taxonomy d3/i9/P1 / semi-naive | compile | 5.678 | 5.880 | 1.036 [0.9984, 1.086] |
| taxonomy d3/i9/P1 / semi-naive | query | 0.592 | 0.599 | 1.013 [0.9803, 1.024] |
| taxonomy d3/i9/P1 / semi-naive | property_query | 0.214 | 0.218 | 1.019 [1.003, 1.033] |
| taxonomy d3/i9/P1 / semi-naive | subsumption | 20.912 | 0.064 | 0.003064 [0.00207, 0.003517] |
| taxonomy d3/i9/PF / semi-naive | parse | 8.767 | 8.631 | 0.9845 [0.9255, 1.086] |
| taxonomy d3/i9/PF / semi-naive | compile | 9.401 | 9.780 | 1.04 [1.011, 1.061] |
| taxonomy d3/i9/PF / semi-naive | query | 0.667 | 0.671 | 1.005 [0.984, 1.026] |
| taxonomy d3/i9/PF / semi-naive | property_query | 0.236 | 0.241 | 1.024 [0.9995, 1.337] |
| taxonomy d3/i9/PF / semi-naive | subsumption | 30.023 | 0.066 | 0.002191 [0.001684, 0.003024] |
| taxonomy d3/i15/P0 / semi-naive | parse | 5.568 | 5.900 | 1.06 [0.8573, 1.19] |
| taxonomy d3/i15/P0 / semi-naive | compile | 6.174 | 6.219 | 1.007 [0.9546, 1.88] |
| taxonomy d3/i15/P0 / semi-naive | query | 0.878 | 0.891 | 1.015 [0.9815, 1.062] |
| taxonomy d3/i15/P0 / semi-naive | property_query | 0.312 | 0.312 | 0.9989 [0.9903, 1.059] |
| taxonomy d3/i15/P0 / semi-naive | subsumption | 26.737 | 0.072 | 0.002705 [0.002598, 0.002847] |
| taxonomy d3/i15/P1 / semi-naive | parse | 8.245 | 7.856 | 0.9527 [0.8754, 1.077] |
| taxonomy d3/i15/P1 / semi-naive | compile | 8.846 | 8.918 | 1.008 [0.9585, 1.036] |
| taxonomy d3/i15/P1 / semi-naive | query | 0.984 | 1.043 | 1.06 [1.01, 1.141] |
| taxonomy d3/i15/P1 / semi-naive | property_query | 0.354 | 0.373 | 1.055 [1.003, 1.091] |
| taxonomy d3/i15/P1 / semi-naive | subsumption | 32.686 | 0.073 | 0.002247 [0.001945, 0.002775] |
| taxonomy d3/i15/PF / semi-naive | parse | 13.417 | 12.804 | 0.9543 [0.414, 1.338] |
| taxonomy d3/i15/PF / semi-naive | compile | 14.557 | 14.914 | 1.025 [0.9568, 1.739] |
| taxonomy d3/i15/PF / semi-naive | query | 1.109 | 1.140 | 1.027 [1, 1.091] |
| taxonomy d3/i15/PF / semi-naive | property_query | 0.392 | 0.392 | 0.998 [0.977, 1.041] |
| taxonomy d3/i15/PF / semi-naive | subsumption | 52.956 | 0.072 | 0.001361 [0.001236, 0.001869] |
| taxonomy d5/i3/P0 / semi-naive | parse | 16.283 | 15.824 | 0.9718 [0.9441, 1.014] |
| taxonomy d5/i3/P0 / semi-naive | compile | 17.418 | 17.746 | 1.019 [1.001, 1.078] |
| taxonomy d5/i3/P0 / semi-naive | query | 1.998 | 2.070 | 1.036 [0.978, 1.06] |
| taxonomy d5/i3/P0 / semi-naive | property_query | 0.864 | 0.879 | 1.017 [0.9815, 1.188] |
| taxonomy d5/i3/P0 / semi-naive | subsumption | 83.211 | 0.628 | 0.007544 [0.007115, 0.01078] |
| taxonomy d5/i3/P1 / semi-naive | parse | 23.173 | 22.592 | 0.9749 [0.938, 1.183] |
| taxonomy d5/i3/P1 / semi-naive | compile | 24.735 | 25.353 | 1.025 [0.8583, 1.224] |
| taxonomy d5/i3/P1 / semi-naive | query | 2.403 | 2.327 | 0.9684 [0.9018, 1.058] |
| taxonomy d5/i3/P1 / semi-naive | property_query | 0.997 | 0.924 | 0.9269 [0.6781, 1.002] |
| taxonomy d5/i3/P1 / semi-naive | subsumption | 103.113 | 0.648 | 0.006283 [0.0059, 0.008685] |
| taxonomy d5/i3/PF / semi-naive | parse | 27.847 | 26.838 | 0.9638 [0.6052, 1.414] |
| taxonomy d5/i3/PF / semi-naive | compile | 32.279 | 31.820 | 0.9858 [0.8407, 1.113] |
| taxonomy d5/i3/PF / semi-naive | query | 2.428 | 2.466 | 1.016 [0.928, 1.05] |
| taxonomy d5/i3/PF / semi-naive | property_query | 1.023 | 1.027 | 1.004 [0.9789, 1.042] |
| taxonomy d5/i3/PF / semi-naive | subsumption | 118.737 | 0.633 | 0.005331 [0.005008, 0.005557] |
| taxonomy d5/i9/P0 / semi-naive | parse | 34.672 | 33.748 | 0.9734 [0.5107, 1.045] |
| taxonomy d5/i9/P0 / semi-naive | compile | 36.539 | 36.685 | 1.004 [0.9795, 1.211] |
| taxonomy d5/i9/P0 / semi-naive | query | 6.216 | 6.372 | 1.025 [0.9698, 1.149] |
| taxonomy d5/i9/P0 / semi-naive | property_query | 2.659 | 2.639 | 0.9924 [0.969, 1.561] |
| taxonomy d5/i9/P0 / semi-naive | subsumption | 223.879 | 0.740 | 0.003304 [0.003108, 0.004329] |
| taxonomy d5/i9/P1 / semi-naive | parse | 46.667 | 55.696 | 1.193 [0.6683, 1.451] |
| taxonomy d5/i9/P1 / semi-naive | compile | 53.211 | 54.351 | 1.021 [0.5412, 1.585] |
| taxonomy d5/i9/P1 / semi-naive | query | 6.945 | 7.599 | 1.094 [1.022, 1.151] |
| taxonomy d5/i9/P1 / semi-naive | property_query | 2.801 | 3.055 | 1.091 [1.03, 1.175] |
| taxonomy d5/i9/P1 / semi-naive | subsumption | 295.137 | 0.811 | 0.002748 [0.002637, 0.004048] |
| taxonomy d5/i9/PF / semi-naive | parse | 69.482 | 81.880 | 1.178 [0.5901, 1.393] |
| taxonomy d5/i9/PF / semi-naive | compile | 86.649 | 85.023 | 0.9812 [0.7624, 1.355] |
| taxonomy d5/i9/PF / semi-naive | query | 7.713 | 7.668 | 0.9941 [0.9363, 1.102] |
| taxonomy d5/i9/PF / semi-naive | property_query | 3.157 | 3.129 | 0.9912 [0.8906, 1.111] |
| taxonomy d5/i9/PF / semi-naive | subsumption | 368.635 | 0.829 | 0.002248 [0.002073, 0.003042] |
| taxonomy d5/i15/P0 / semi-naive | parse | 52.788 | 61.236 | 1.16 [0.9786, 1.523] |
| taxonomy d5/i15/P0 / semi-naive | compile | 56.894 | 84.667 | 1.488 [0.6916, 1.573] |
| taxonomy d5/i15/P0 / semi-naive | query | 11.062 | 12.074 | 1.092 [0.9995, 1.337] |
| taxonomy d5/i15/P0 / semi-naive | property_query | 4.400 | 5.222 | 1.187 [1.065, 1.744] |
| taxonomy d5/i15/P0 / semi-naive | subsumption | 402.960 | 0.875 | 0.002171 [0.002022, 0.002446] |
| taxonomy d5/i15/P1 / semi-naive | parse | 77.249 | 79.703 | 1.032 [0.5309, 1.401] |
| taxonomy d5/i15/P1 / semi-naive | compile | 85.097 | 91.361 | 1.074 [0.5936, 1.928] |
| taxonomy d5/i15/P1 / semi-naive | query | 12.172 | 13.481 | 1.108 [1.01, 1.314] |
| taxonomy d5/i15/P1 / semi-naive | property_query | 4.848 | 5.391 | 1.112 [1.02, 1.423] |
| taxonomy d5/i15/P1 / semi-naive | subsumption | 467.671 | 0.917 | 0.00196 [0.001814, 0.002309] |
| taxonomy d5/i15/PF / semi-naive | parse | 110.581 | 130.334 | 1.179 [0.5011, 1.413] |
| taxonomy d5/i15/PF / semi-naive | compile | 167.828 | 155.883 | 0.9288 [0.6598, 1.379] |
| taxonomy d5/i15/PF / semi-naive | query | 13.354 | 14.122 | 1.058 [0.9783, 1.276] |
| taxonomy d5/i15/PF / semi-naive | property_query | 5.102 | 5.430 | 1.064 [1.005, 1.146] |
| taxonomy d5/i15/PF / semi-naive | subsumption | 624.705 | 1.054 | 0.001688 [0.001493, 0.002146] |
| taxonomy d7/i3/P0 / semi-naive | parse | 150.247 | 153.952 | 1.025 [0.4045, 1.522] |
| taxonomy d7/i3/P0 / semi-naive | compile | 164.006 | 226.382 | 1.38 [0.5945, 1.525] |
| taxonomy d7/i3/P0 / semi-naive | query | 27.909 | 28.611 | 1.025 [0.8234, 1.386] |
| taxonomy d7/i3/P0 / semi-naive | property_query | 12.851 | 13.650 | 1.062 [0.8213, 1.328] |
| taxonomy d7/i3/P0 / semi-naive | subsumption | 1099.823 | 6.433 | 0.005849 [0.005341, 0.006435] |
| taxonomy d7/i3/P1 / semi-naive | parse | 204.130 | 301.255 | 1.476 [0.593, 1.524] |
| taxonomy d7/i3/P1 / semi-naive | compile | 229.462 | 233.271 | 1.017 [0.7131, 1.242] |
| taxonomy d7/i3/P1 / semi-naive | query | 32.476 | 30.772 | 0.9475 [0.8411, 1.095] |
| taxonomy d7/i3/P1 / semi-naive | property_query | 14.183 | 12.895 | 0.9092 [0.7072, 1.153] |
| taxonomy d7/i3/P1 / semi-naive | subsumption | 1373.532 | 6.838 | 0.004978 [0.004243, 0.005135] |
| taxonomy d7/i3/PF / semi-naive | parse | 557.512 | 280.830 | 0.5037 [0.4108, 1.02] |
| taxonomy d7/i3/PF / semi-naive | compile | 301.628 | 289.163 | 0.9587 [0.7707, 1.132] |
| taxonomy d7/i3/PF / semi-naive | query | 35.109 | 35.284 | 1.005 [0.9453, 1.201] |
| taxonomy d7/i3/PF / semi-naive | property_query | 19.076 | 14.814 | 0.7766 [0.726, 1.334] |
| taxonomy d7/i3/PF / semi-naive | subsumption | 1487.098 | 6.848 | 0.004605 [0.004114, 0.006281] |
| taxonomy d7/i9/P0 / semi-naive | parse | 398.193 | 324.614 | 0.8152 [0.2393, 1.385] |
| taxonomy d7/i9/P0 / semi-naive | compile | 399.700 | 348.702 | 0.8724 [0.307, 1.283] |
| taxonomy d7/i9/P0 / semi-naive | query | 84.207 | 82.227 | 0.9765 [0.7341, 1.051] |
| taxonomy d7/i9/P0 / semi-naive | property_query | 47.229 | 44.457 | 0.9413 [0.814, 1.122] |
| taxonomy d7/i9/P0 / semi-naive | subsumption | 3220.993 | 8.491 | 0.002636 [0.001363, 0.002891] |
| taxonomy d7/i9/P1 / semi-naive | parse | 1371.182 | 615.250 | 0.4487 [0.1133, 1.086] |
| taxonomy d7/i9/P1 / semi-naive | compile | 1160.278 | 510.707 | 0.4402 [0.1167, 0.7284] |
| taxonomy d7/i9/P1 / semi-naive | query | 148.352 | 89.168 | 0.6011 [0.2313, 0.8959] |
| taxonomy d7/i9/P1 / semi-naive | property_query | 88.410 | 45.896 | 0.5191 [0.2823, 0.825] |
| taxonomy d7/i9/P1 / semi-naive | subsumption | 6682.962 | 9.156 | 0.00137 [0.000823, 0.001674] |
| taxonomy d7/i9/PF / semi-naive | parse | 1096.393 | 664.316 | 0.6059 [0.4749, 1.15] |
| taxonomy d7/i9/PF / semi-naive | compile | 1196.013 | 752.714 | 0.6294 [0.4085, 1.252] |
| taxonomy d7/i9/PF / semi-naive | query | 138.176 | 109.312 | 0.7911 [0.6164, 1.123] |
| taxonomy d7/i9/PF / semi-naive | property_query | 69.315 | 53.712 | 0.7749 [0.6449, 0.9368] |
| taxonomy d7/i9/PF / semi-naive | subsumption | 5910.086 | 9.976 | 0.001688 [0.001249, 0.002042] |
| taxonomy d7/i15/P0 / semi-naive | parse | 785.515 | 873.750 | 1.112 [0.5044, 1.761] |
| taxonomy d7/i15/P0 / semi-naive | compile | 814.767 | 809.647 | 0.9937 [0.5823, 1.41] |
| taxonomy d7/i15/P0 / semi-naive | query | 241.877 | 199.171 | 0.8234 [0.2093, 2.023] |
| taxonomy d7/i15/P0 / semi-naive | property_query | 142.110 | 102.336 | 0.7201 [0.3193, 0.924] |
| taxonomy d7/i15/P0 / semi-naive | subsumption | 9245.125 | 10.858 | 0.001174 [0.0009025, 0.001783] |
| taxonomy d7/i15/P1 / semi-naive | parse | 1816.613 | 653.674 | 0.3598 [0.2995, 0.8569] |
| taxonomy d7/i15/P1 / semi-naive | compile | 1290.508 | 880.510 | 0.6823 [0.4291, 1.322] |
| taxonomy d7/i15/P1 / semi-naive | query | 190.131 | 207.613 | 1.092 [0.7928, 1.187] |
| taxonomy d7/i15/P1 / semi-naive | property_query | 117.928 | 103.339 | 0.8763 [0.6677, 1.094] |
| taxonomy d7/i15/P1 / semi-naive | subsumption | 7663.222 | 13.114 | 0.001711 [0.0009201, 0.002177] |
| taxonomy d7/i15/PF / semi-naive | parse | 1163.029 | 1501.532 | 1.291 [0.5174, 1.759] |
| taxonomy d7/i15/PF / semi-naive | compile | 1242.354 | 1249.815 | 1.006 [0.3663, 1.613] |
| taxonomy d7/i15/PF / semi-naive | query | 200.764 | 238.684 | 1.189 [0.8921, 1.263] |
| taxonomy d7/i15/PF / semi-naive | property_query | 119.607 | 99.931 | 0.8355 [0.6759, 0.9834] |
| taxonomy d7/i15/PF / semi-naive | subsumption | 7983.876 | 12.339 | 0.001546 [0.0009462, 0.001747] |
| taxonomy d3/i3/P0 / naive | parse | 1.803 | 1.764 | 0.9783 [0.6725, 1.687] |
| taxonomy d3/i3/P0 / naive | compile | 2.095 | 1.905 | 0.9095 [0.7291, 1.338] |
| taxonomy d3/i3/P0 / naive | query | 0.191 | 0.184 | 0.9603 [0.919, 1.241] |
| taxonomy d3/i3/P0 / naive | property_query | 0.064 | 0.064 | 0.9961 [0.8845, 1.248] |
| taxonomy d3/i3/P0 / naive | subsumption | 9.144 | 0.063 | 0.006885 [0.006447, 0.01011] |
| taxonomy d3/i3/P0 / owlrl | parse | 1.908 | 1.747 | 0.9156 [0.6577, 1.29] |
| taxonomy d3/i3/P0 / owlrl | compile | 0.000 | 0.000 | — |
| taxonomy d3/i3/P0 / owlrl | query | 0.075 | 0.067 | 0.8945 [0.8543, 1.009] |
| equality 100 / semi-naive | parse | 2.764 | 2.526 | 0.9139 [0.7208, 1.189] |
| equality 100 / semi-naive | compile | 3.493 | 3.301 | 0.9451 [0.8386, 2.117] |
| equality 100 / semi-naive | query | 0.486 | 0.436 | 0.898 [0.8476, 0.9819] |
| equality 1000 / semi-naive | parse | 27.928 | 25.382 | 0.9089 [0.5891, 1.377] |
| equality 1000 / semi-naive | compile | 35.664 | 32.593 | 0.9139 [0.8104, 1.293] |
| equality 1000 / semi-naive | query | 5.314 | 4.903 | 0.9226 [0.6824, 1.196] |
| existential 100 / semi-naive | parse | 1.077 | 1.080 | 1.002 [0.5987, 1.989] |
| existential 100 / semi-naive | compile | 1.334 | 1.289 | 0.9659 [0.8209, 1.227] |
| existential 100 / semi-naive | query | 6.868 | 6.664 | 0.9703 [0.9423, 1.581] |
| transitive 100 / semi-naive | parse | 1.050 | 1.485 | 1.415 [0.2251, 1.808] |
| transitive 100 / semi-naive | compile | 1.339 | 1.952 | 1.458 [0.9768, 1.575] |
| transitive 100 / semi-naive | query | 12.634 | 19.323 | 1.529 [0.9356, 2.693] |
| cardinality d3/i3 / semi-naive | parse | 6.019 | 6.709 | 1.115 [0.886, 2.276] |
| cardinality d3/i3 / semi-naive | compile | 7.996 | 10.860 | 1.358 [0.8162, 1.809] |
| cardinality d3/i3 / semi-naive | query | 0.595 | 0.630 | 1.06 [0.9819, 1.503] |
| cardinality d5/i3 / semi-naive | parse | 52.724 | 68.787 | 1.305 [0.8484, 2.615] |
| cardinality d5/i3 / semi-naive | compile | 78.527 | 118.473 | 1.509 [0.9644, 1.944] |
| cardinality d5/i3 / semi-naive | query | 7.545 | 9.814 | 1.301 [0.9404, 1.451] |
| cardinality d7/i3 / semi-naive | parse | 668.684 | 630.468 | 0.9428 [0.6367, 1.42] |
| cardinality d7/i3 / semi-naive | compile | 760.432 | 747.375 | 0.9828 [0.7744, 1.686] |
| cardinality d7/i3 / semi-naive | query | 85.394 | 72.760 | 0.8521 [0.8111, 1.004] |
| cardinality d5/i9 / semi-naive | parse | 157.891 | 126.112 | 0.7987 [0.3812, 1.264] |
| cardinality d5/i9 / semi-naive | compile | 226.737 | 134.976 | 0.5953 [0.4812, 0.9835] |
| cardinality d5/i9 / semi-naive | query | 26.488 | 20.568 | 0.7765 [0.5724, 0.9719] |
| factored unions 4 pairs/128 subjects / semi-naive | parse | 7.557 | 5.790 | 0.7661 [0.5167, 1.452] |
| factored unions 4 pairs/128 subjects / semi-naive | compile | 8.437 | 6.042 | 0.7161 [0.6279, 0.9941] |
| factored unions 4 pairs/128 subjects / semi-naive | query | 0.320 | 0.267 | 0.8337 [0.6155, 1.611] |
| factored unions 8 pairs/128 subjects / semi-naive | parse | 15.032 | 10.370 | 0.6899 [0.5528, 0.9586] |
| factored unions 8 pairs/128 subjects / semi-naive | compile | 15.791 | 10.970 | 0.6947 [0.5518, 0.9024] |
| factored unions 8 pairs/128 subjects / semi-naive | query | 0.674 | 0.378 | 0.5611 [0.3807, 0.7438] |
| factored unions 16 pairs/128 subjects / semi-naive | parse | 33.722 | 19.727 | 0.585 [0.3846, 0.9823] |
| factored unions 16 pairs/128 subjects / semi-naive | compile | 36.010 | 21.756 | 0.6042 [0.2608, 1.429] |
| factored unions 16 pairs/128 subjects / semi-naive | query | 0.986 | 0.568 | 0.576 [0.5339, 0.7836] |
| factored unions 32 pairs/128 subjects / semi-naive | parse | 61.096 | 51.643 | 0.8453 [0.6132, 1.12] |
| factored unions 32 pairs/128 subjects / semi-naive | compile | 91.399 | 50.156 | 0.5488 [0.4293, 0.8188] |
| factored unions 32 pairs/128 subjects / semi-naive | query | 1.562 | 1.163 | 0.7448 [0.5482, 5.885] |
| factored unions 64 pairs/128 subjects / semi-naive | parse | 84.582 | 85.463 | 1.01 [0.7658, 1.304] |
| factored unions 64 pairs/128 subjects / semi-naive | compile | 87.182 | 109.897 | 1.261 [0.7841, 1.408] |
| factored unions 64 pairs/128 subjects / semi-naive | query | 2.286 | 2.367 | 1.035 [0.9457, 1.174] |
| factored enumerations 16 pairs/128 subjects / semi-naive | parse | 2.547 | 2.459 | 0.9656 [0.7657, 1.263] |
| factored enumerations 16 pairs/128 subjects / semi-naive | compile | 3.674 | 3.374 | 0.9184 [0.8042, 0.9949] |
| factored enumerations 16 pairs/128 subjects / semi-naive | query | 0.193 | 0.189 | 0.9791 [0.9321, 1.057] |
| factored enumerations 32 pairs/128 subjects / semi-naive | parse | 3.894 | 3.679 | 0.9447 [0.7647, 1.236] |
| factored enumerations 32 pairs/128 subjects / semi-naive | compile | 5.644 | 5.225 | 0.9257 [0.9047, 0.9929] |
| factored enumerations 32 pairs/128 subjects / semi-naive | query | 0.238 | 0.221 | 0.9306 [0.854, 0.9445] |
| factored enumerations 64 pairs/128 subjects / semi-naive | parse | 6.368 | 6.338 | 0.9952 [0.8464, 1.314] |
| factored enumerations 64 pairs/128 subjects / semi-naive | compile | 9.435 | 9.407 | 0.997 [0.9681, 1.091] |
| factored enumerations 64 pairs/128 subjects / semi-naive | query | 0.301 | 0.288 | 0.9583 [0.8896, 0.9878] |
| maintenance d3/10% / semi-naive | parse | 10.184 | 12.075 | 1.186 [0.9262, 2.735] |
| maintenance d3/10% / semi-naive | compile | 10.703 | 16.616 | 1.552 [0.959, 2.58] |
| maintenance d3/10% / semi-naive | query | 1.339 | 1.602 | 1.196 [0.9376, 1.606] |
| maintenance d3/15% / semi-naive | parse | 10.221 | 11.074 | 1.083 [0.4978, 1.251] |
| maintenance d3/15% / semi-naive | compile | 10.631 | 14.446 | 1.359 [0.9743, 1.529] |
| maintenance d3/15% / semi-naive | query | 1.301 | 1.339 | 1.03 [0.9641, 1.343] |
| maintenance d4/10% / semi-naive | parse | 52.051 | 47.971 | 0.9216 [0.5166, 1.335] |
| maintenance d4/10% / semi-naive | compile | 80.813 | 73.357 | 0.9077 [0.5856, 1.463] |
| maintenance d4/10% / semi-naive | query | 8.500 | 7.925 | 0.9324 [0.85, 1.084] |
| maintenance d4/15% / semi-naive | parse | 53.710 | 48.109 | 0.8957 [0.5126, 1.313] |
| maintenance d4/15% / semi-naive | compile | 52.740 | 74.086 | 1.405 [0.9871, 1.521] |
| maintenance d4/15% / semi-naive | query | 8.639 | 8.155 | 0.944 [0.8583, 1.081] |
| maintenance d5/10% / semi-naive | parse | 249.729 | 418.664 | 1.676 [0.7469, 2.073] |
| maintenance d5/10% / semi-naive | compile | 300.286 | 396.340 | 1.32 [0.6289, 1.716] |
| maintenance d5/10% / semi-naive | query | 57.330 | 53.062 | 0.9256 [0.7988, 1.638] |
| maintenance d5/15% / semi-naive | parse | 292.262 | 298.024 | 1.02 [0.3286, 1.448] |
| maintenance d5/15% / semi-naive | compile | 276.383 | 314.615 | 1.138 [0.9695, 2.508] |
| maintenance d5/15% / semi-naive | query | 55.067 | 51.280 | 0.9312 [0.8813, 1.405] |

### Maintenance compared with the pinned implementation

These rows compare the same operation across versions. The separate fresh-rebuild ratio compares each version's recomputation cost. Input mutation counts and fresh-closure validation must agree before an operation is compared. All common evaluation counters and raw operation samples are retained in JSON.

| Workload | Operation | Previous ms | Current ms | Update ratio [interval] | Rebuild ratio [interval] | Overdeleted before → after |
|---|---|---:|---:|---:|---:|---:|
| maintenance d3/10% | fact_delete | 14.815 | 17.727 | 1.197 [0.6797, 2.262] | 1.187 [0.9615, 3.255] | 442 → 442 |
| maintenance d3/10% | fact_insert | 3.595 | 4.243 | 1.18 [0.9453, 1.575] | 1.48 [0.672, 1.502] | 0 → 0 |
| maintenance d3/10% | rule_insert | 7.858 | 8.143 | 1.036 [0.896, 2.123] | 1.296 [0.8697, 1.967] | 0 → 0 |
| maintenance d3/10% | rule_delete | 10.313 | 13.291 | 1.289 [0.6569, 1.724] | 1.458 [0.9316, 2.376] | 276 → 276 |
| maintenance d3/10% | rule_replace | 11.668 | 15.694 | 1.345 [0.9096, 1.721] | 1.171 [0.6345, 1.874] | 272 → 272 |
| maintenance d3/10% | atomic_mixed | 13.472 | 20.046 | 1.488 [0.9215, 2.432] | 1.087 [0.6594, 1.868] | 975 → 975 |
| maintenance d3/15% | fact_delete | 13.933 | 17.971 | 1.29 [0.8455, 2.323] | 0.9884 [0.9527, 1.903] | 659 → 659 |
| maintenance d3/15% | fact_insert | 4.089 | 4.238 | 1.036 [0.9078, 2.215] | 0.9986 [0.6517, 1.843] | 0 → 0 |
| maintenance d3/15% | rule_insert | 7.653 | 7.039 | 0.9198 [0.8996, 1.311] | 1.241 [0.8441, 1.306] | 0 → 0 |
| maintenance d3/15% | rule_delete | 10.047 | 10.123 | 1.008 [0.5895, 1.482] | 1.253 [0.9298, 1.449] | 256 → 256 |
| maintenance d3/15% | rule_replace | 10.962 | 10.667 | 0.9731 [0.9182, 1.519] | 0.9543 [0.6302, 2.056] | 262 → 262 |
| maintenance d3/15% | atomic_mixed | 13.416 | 12.972 | 0.9669 [0.9158, 1.385] | 1.239 [0.63, 1.423] | 1070 → 1070 |
| maintenance d4/10% | fact_delete | 115.146 | 93.021 | 0.8078 [0.5994, 1.182] | 0.9382 [0.7796, 1.099] | 2555 → 2555 |
| maintenance d4/10% | fact_insert | 19.578 | 18.946 | 0.9677 [0.3471, 1.003] | 0.8691 [0.6948, 1.045] | 0 → 0 |
| maintenance d4/10% | rule_insert | 39.179 | 38.283 | 0.9771 [0.9385, 1.762] | 0.917 [0.7011, 1.123] | 0 → 0 |
| maintenance d4/10% | rule_delete | 101.124 | 57.883 | 0.5724 [0.5222, 1.073] | 0.9555 [0.8804, 1.16] | 1408 → 1408 |
| maintenance d4/10% | rule_replace | 66.449 | 64.010 | 0.9633 [0.5695, 1.356] | 0.8572 [0.7348, 1.056] | 1406 → 1406 |
| maintenance d4/10% | atomic_mixed | 78.822 | 76.894 | 0.9755 [0.6163, 1.363] | 0.8993 [0.8096, 1.232] | 5075 → 5075 |
| maintenance d4/15% | fact_delete | 115.920 | 102.365 | 0.8831 [0.6305, 1.011] | 0.9749 [0.9162, 1.156] | 3822 → 3822 |
| maintenance d4/15% | fact_insert | 24.074 | 24.296 | 1.009 [0.9627, 1.037] | 0.8447 [0.7686, 1.017] | 0 → 0 |
| maintenance d4/15% | rule_insert | 38.753 | 40.756 | 1.052 [0.946, 2.099] | 0.9009 [0.8401, 1.216] | 0 → 0 |
| maintenance d4/15% | rule_delete | 60.045 | 58.764 | 0.9787 [0.5223, 1.91] | 0.9617 [0.8067, 1.092] | 1342 → 1342 |
| maintenance d4/15% | rule_replace | 104.455 | 60.486 | 0.5791 [0.5335, 0.9865] | 1.117 [0.8426, 1.239] | 1332 → 1332 |
| maintenance d4/15% | atomic_mixed | 117.141 | 107.416 | 0.917 [0.6028, 1.332] | 1.061 [0.8161, 1.206] | 5657 → 5657 |
| maintenance d5/10% | fact_delete | 634.307 | 687.888 | 1.084 [0.8391, 1.362] | 1.116 [0.6839, 1.913] | 14744 → 14744 |
| maintenance d5/10% | fact_insert | 290.468 | 121.534 | 0.4184 [0.3217, 1.656] | 0.9702 [0.742, 1.582] | 0 → 0 |
| maintenance d5/10% | rule_insert | 219.359 | 372.468 | 1.698 [0.6721, 2.226] | 1.026 [0.8404, 2.32] | 0 → 0 |
| maintenance d5/10% | rule_delete | 685.817 | 598.605 | 0.8728 [0.5485, 1.7] | 1.066 [0.7469, 1.716] | 7000 → 7000 |
| maintenance d5/10% | rule_replace | 417.815 | 725.576 | 1.737 [0.6414, 2.295] | 0.9638 [0.7452, 1.609] | 7088 → 7088 |
| maintenance d5/10% | atomic_mixed | 771.007 | 709.321 | 0.92 [0.5725, 1.547] | 0.8583 [0.7986, 1.51] | 26362 → 26362 |
| maintenance d5/15% | fact_delete | 569.547 | 676.341 | 1.188 [0.8749, 1.576] | 0.8915 [0.768, 1.176] | 22162 → 22162 |
| maintenance d5/15% | fact_insert | 147.132 | 173.106 | 1.177 [0.501, 3.241] | 0.9149 [0.7753, 1.538] | 0 → 0 |
| maintenance d5/15% | rule_insert | 219.218 | 380.343 | 1.735 [0.4472, 3.237] | 0.8605 [0.6285, 1.328] | 0 → 0 |
| maintenance d5/15% | rule_delete | 421.620 | 666.594 | 1.581 [0.8876, 1.962] | 0.8897 [0.7811, 1.454] | 6580 → 6580 |
| maintenance d5/15% | rule_replace | 749.609 | 406.264 | 0.542 [0.4414, 1.43] | 0.7956 [0.7479, 1.162] | 6670 → 6670 |
| maintenance d5/15% | atomic_mixed | 817.228 | 773.958 | 0.9471 [0.669, 1.641] | 0.9598 [0.8163, 1.2] | 29778 → 29778 |

Matched 51 cases; excluded 3 new or changed cases. The raw report records each exclusion reason. No workload or reference timing is rewritten to obtain a match.

These workloads use the Bach worked examples and synthetic inputs inspired by thesis chapter 8, not a reproduction of the 2004 KAON/XSB/Racer measurements. Modern hardware, execution strategies and measurement boundaries differ. OWL RL includes additional axiomatic/schema triples, so its total closure count is not directly comparable; the named instance answers are verified.

The naive strategy shares the compiler and equality machinery; it is an execution baseline, not an independent semantic oracle. Unit validation also uses OWL RL and exhaustive finite models. There is no performance acceptance threshold or claim of production-scale throughput.

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
| leipzig-inhabitants | Table 2.5 T10/A8, p. 35 | `["johann-sebastian"]` | 0.015 |
| wives | Table 2.5 T3/A5/A6/A11/A12, p. 35 | `[]` | 0.014 |
| ambrosius-is-father | Table 2.5 T5/A1/A7, p. 35; §5.4.2.1, p. 132 | `true` | 0.016 |
| ambrosius-named-son-not-entailed | Table 2.5 A1, p. 35; Example 4.5.2, p. 94 | `false` | 0.012 |
| sebastian-known-children | Example 5.4.1, p. 131; §5.4.3, pp. 134–135 | `["wilhelm-friedemann"]` | 0.024 |
| sebastian-marriages | Table 2.5 A6/A12, p. 35; §5.4.3, pp. 134–135 | `["anna-magdalena", "maria-barbara"]` | 0.019 |
| symmetric-marriage | Table 2.5 T9/A6, p. 35; §5.4.3, pp. 134–135 | `["johann-sebastian"]` | 0.016 |
| sebastian-types | §5.4.2.3, p. 134; Table 2.5, p. 35 | `["Composer", "Father", "Genius", "LeipzigInhabitant", "Man", "Person", "owl:Thing"]` | 0.020 |
| male-child-existential | Example 4.5.2, p. 94; §5.4.2, pp. 132–133 | `["johann-ambrosius"]` | 12.152 |
| child-filler-intersection-union | Adapted Example 5.4.2, pp. 133–134; explicit filler scope | `["johann-ambrosius"]` | 13.308 |
| person-subsumes-father | Example 2.4.3, p. 39; §5.4.4.1, p. 135 | `true` | 0.081 |
| father-does-not-subsume-person | §5.4.4.1, pp. 135–136; Table 2.5 T5, p. 35 | `false` | 5.912 |
| composition-subsumes-birthday-cantata | Table 2.5 T12–T15, p. 35; §5.4.4.1, pp. 135–136 | `true` | 0.015 |
| father-satisfiable | Example 2.4.3, p. 39; §5.4.4.4, pp. 137–138 | `true` | 5.865 |
| ancestor-subsumes-child | Table 2.5 T7, p. 35; §5.4.4.5, pp. 138–139 | `true` | 0.010 |
| ancestor-transitive | Table 2.5 T8, p. 35; §5.4.4.6, p. 140 | `true` | 0.006 |
| marriage-symmetric | Table 2.5 T9, p. 35; §5.4.4.6, pp. 139–140 | `true` | 0.004 |
| dynasty-not-transitive | Table 2.5 T16/T17, p. 35; §6.2.2, p. 151 (corrected) | `false` | 6.258 |

## Bach Table 2.5 (RDF/XML): checked queries

Source: `examples/bach.owl`; profile L3. Parsing measures the original document syntax. Query ms in the summary is the total of all queries below.

| Query | Thesis reference | Answer | Median ms |
|---|---|---|---:|
| fathers | Table 2.5 T5/A1–A4/A7, p. 35; §5.4.2.2, p. 132 | `["johann-ambrosius", "johann-sebastian"]` | 0.026 |
| mothers | Table 2.5 T6, p. 35; §5.4.2.2, p. 132 | `[]` | 0.015 |
| people | Table 2.5 T1/T2/T5, p. 35; §5.4.2.2, p. 132 | `["anna-magdalena", "johann-ambrosius", "johann-sebastian", "maria-barbara", "wilhelm-friedemann"]` | 0.036 |
| masterpieces | Table 2.5 T11/A2/A9/A10, p. 35 | `["BWV248"]` | 0.017 |
| birthday-cantatas | Table 2.5 A14/A15, p. 35 | `["BWV213", "BWV214"]` | 0.017 |
| compositions | Table 2.5 T12–T15/A13–A15, p. 35 | `["BWV213", "BWV214", "BWV248"]` | 0.017 |
| named-birthdays | Table 2.5 T12/A14/A15, p. 35; Example 4.5.2, p. 94 | `[]` | 0.023 |
| leipzig-inhabitants | Table 2.5 T10/A8, p. 35 | `["johann-sebastian"]` | 0.015 |
| wives | Table 2.5 T3/A5/A6/A11/A12, p. 35 | `[]` | 0.014 |
| ambrosius-is-father | Table 2.5 T5/A1/A7, p. 35; §5.4.2.1, p. 132 | `true` | 0.015 |
| ambrosius-named-son-not-entailed | Table 2.5 A1, p. 35; Example 4.5.2, p. 94 | `false` | 0.012 |
| sebastian-known-children | Example 5.4.1, p. 131; §5.4.3, pp. 134–135 | `["wilhelm-friedemann"]` | 0.023 |
| sebastian-marriages | Table 2.5 A6/A12, p. 35; §5.4.3, pp. 134–135 | `["anna-magdalena", "maria-barbara"]` | 0.018 |
| symmetric-marriage | Table 2.5 T9/A6, p. 35; §5.4.3, pp. 134–135 | `["johann-sebastian"]` | 0.016 |
| sebastian-types | §5.4.2.3, p. 134; Table 2.5, p. 35 | `["Composer", "Father", "Genius", "LeipzigInhabitant", "Man", "Person", "owl:Thing"]` | 0.020 |
| male-child-existential | Example 4.5.2, p. 94; §5.4.2, pp. 132–133 | `["johann-ambrosius"]` | 11.716 |
| child-filler-intersection-union | Adapted Example 5.4.2, pp. 133–134; explicit filler scope | `["johann-ambrosius"]` | 12.338 |
| person-subsumes-father | Example 2.4.3, p. 39; §5.4.4.1, p. 135 | `true` | 0.069 |
| father-does-not-subsume-person | §5.4.4.1, pp. 135–136; Table 2.5 T5, p. 35 | `false` | 5.481 |
| composition-subsumes-birthday-cantata | Table 2.5 T12–T15, p. 35; §5.4.4.1, pp. 135–136 | `true` | 0.011 |
| father-satisfiable | Example 2.4.3, p. 39; §5.4.4.4, pp. 137–138 | `true` | 5.650 |
| ancestor-subsumes-child | Table 2.5 T7, p. 35; §5.4.4.5, pp. 138–139 | `true` | 0.009 |
| ancestor-transitive | Table 2.5 T8, p. 35; §5.4.4.6, p. 140 | `true` | 0.005 |
| marriage-symmetric | Table 2.5 T9, p. 35; §5.4.4.6, pp. 139–140 | `true` | 0.004 |
| dynasty-not-transitive | Table 2.5 T16/T17, p. 35; §6.2.2, p. 151 (corrected) | `false` | 5.782 |

## Bach family maintenance (Turtle): checked queries

Source: `examples/bach-family.ttl`; profile L0. Parsing measures the original document syntax. Query ms in the summary is the total of all queries below.

| Query | Thesis reference | Answer | Median ms |
|---|---|---|---:|
| johannes-descendants | Figure 6.2, p. 150; Example 6.3.2, p. 158 | `["christoph", "heinrich", "johann-ambrosius", "johann-christoph", "johann-michael", "johann-sebastian", "maria-barbara", "wilhelm-friedemann"]` | 0.027 |
| ambrosius-descendants | Figure 6.2; §6.2.1, p. 150 | `["johann-sebastian", "wilhelm-friedemann"]` | 0.017 |
| johannes-reaches-wilhelm | Figure 6.2; §6.2.1, p. 150 | `true` | 0.014 |
| base-dynasty-not-symmetric | Table 6.1; §6.2.2, p. 151 | `false` | 1.911 |
| base-dynasty-not-transitive | Table 6.1; §6.2.2, p. 151 | `false` | 1.457 |
| base-ancestor-transitive | Table 6.1 T1, p. 151 | `true` | 0.006 |
| base-cross-branch-not-entailed | §6.2.2, p. 151; docs/THESIS_ERRATA.md item 6 | `false` | 0.013 |

Bach updates each start from the original family graph. Both RDF update and fresh rebuild timings include compilation. Exact pair sets and the three removed/four added ancestor pairs are checked against independent graph traversal and recorded in JSON.
