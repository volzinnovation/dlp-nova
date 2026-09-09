# Measured benchmark results

Run: 2026-09-09T17:09:20.295282+00:00. Python 3.12.9; macOS-26.5.1-arm64-arm-64bit.

Measured checkout: `8ce254fb011c2a2fa72345e66a25373c0885273a`; dirty: True. Exact measured source hashes and checkout status are in the raw report.

Recorded: 54 validated cases, 0 errors, 54 planned cases. Repetitions per case: 5.

All times below are medians in milliseconds. Every raw sample is in `research-thesis-results.json`.
Peak RSS is the entire isolated worker (including parser, retained input and repetitions), not incremental reasoner allocation. Compiler and materializer timings are separate.

| Workload | Engine | Input triples | Closure facts | Compile ms | Materialize ms | Query ms | Peak MiB |
|---|---|---:|---:|---:|---:|---:|---:|
| taxonomy d3/i3/P0 | semi-naive | 196 | 541 | 2.000 | 2.830 | 0.193 | 37.4 |
| taxonomy d3/i3/P1 | semi-naive | 275 | 580 | 2.819 | 3.134 | 0.211 | 38.8 |
| taxonomy d3/i3/PF | semi-naive | 513 | 658 | 4.875 | 4.002 | 0.241 | 42.3 |
| taxonomy d3/i9/P0 | semi-naive | 430 | 1621 | 4.136 | 7.699 | 0.552 | 41.3 |
| taxonomy d3/i9/P1 | semi-naive | 587 | 1738 | 6.180 | 8.966 | 0.635 | 43.1 |
| taxonomy d3/i9/PF | semi-naive | 981 | 1972 | 10.155 | 10.839 | 0.718 | 50.6 |
| taxonomy d3/i15/P0 | semi-naive | 664 | 2701 | 6.162 | 12.519 | 0.920 | 44.8 |
| taxonomy d3/i15/P1 | semi-naive | 899 | 2896 | 9.027 | 13.987 | 1.019 | 48.9 |
| taxonomy d3/i15/PF | semi-naive | 1449 | 3286 | 15.197 | 17.651 | 1.128 | 55.0 |
| taxonomy d5/i3/P0 | semi-naive | 1816 | 7102 | 17.796 | 40.090 | 2.102 | 59.6 |
| taxonomy d5/i3/P1 | semi-naive | 2543 | 7465 | 24.997 | 51.105 | 2.315 | 64.1 |
| taxonomy d5/i3/PF | semi-naive | 3105 | 8191 | 32.463 | 45.673 | 2.801 | 73.6 |
| taxonomy d5/i9/P0 | semi-naive | 3994 | 21304 | 38.783 | 124.425 | 7.118 | 89.0 |
| taxonomy d5/i9/P1 | semi-naive | 5447 | 22393 | 54.555 | 144.068 | 7.511 | 104.7 |
| taxonomy d5/i9/PF | semi-naive | 7461 | 24571 | 90.676 | 167.100 | 8.555 | 118.5 |
| taxonomy d5/i15/P0 | semi-naive | 6172 | 35506 | 82.484 | 230.232 | 11.752 | 121.3 |
| taxonomy d5/i15/P1 | semi-naive | 8351 | 37321 | 112.575 | 230.025 | 13.436 | 140.7 |
| taxonomy d5/i15/PF | semi-naive | 11817 | 40951 | 144.302 | 277.843 | 14.825 | 169.3 |
| taxonomy d7/i3/P0 | semi-naive | 16396 | 83647 | 228.704 | 627.548 | 28.856 | 237.5 |
| taxonomy d7/i3/P1 | semi-naive | 22955 | 86926 | 228.349 | 749.057 | 31.221 | 298.3 |
| taxonomy d7/i3/PF | semi-naive | 26433 | 93484 | 290.802 | 844.506 | 34.951 | 329.6 |
| taxonomy d7/i9/P0 | semi-naive | 36070 | 250939 | 351.790 | 2347.012 | 110.074 | 552.7 |
| taxonomy d7/i9/P1 | semi-naive | 49187 | 260776 | 502.551 | 2151.096 | 94.931 | 650.2 |
| taxonomy d7/i9/PF | semi-naive | 65781 | 280450 | 1078.071 | 2853.775 | 123.921 | 795.1 |
| taxonomy d7/i15/P0 | semi-naive | 55744 | 418231 | 529.566 | 3501.702 | 158.159 | 859.6 |
| taxonomy d7/i15/P1 | semi-naive | 75419 | 434626 | 902.166 | 4182.578 | 216.728 | 997.0 |
| taxonomy d7/i15/PF | semi-naive | 105129 | 467416 | 1159.083 | 4777.663 | 242.963 | 1242.3 |
| taxonomy d3/i3/P0 | naive | 196 | 541 | 1.972 | 3.699 | 0.196 | 37.7 |
| taxonomy d3/i3/P0 | owlrl | 196 | 1105 | 0.000 | 96.956 | 0.074 | 38.0 |
| equality 100 | semi-naive | 302 | 601 | 3.420 | 11.890 | 0.472 | 39.9 |
| equality 1000 | semi-naive | 3002 | 6001 | 33.236 | 132.597 | 5.068 | 74.3 |
| existential 100 | semi-naive | 112 | 1401 | 1.296 | 66.276 | 6.516 | 39.1 |
| transitive 100 | semi-naive | 101 | 5152 | 1.257 | 446.153 | 12.248 | 46.4 |
| cardinality d3/i3 | semi-naive | 560 | 1057 | 8.056 | 18.562 | 0.579 | 42.2 |
| cardinality d5/i3 | semi-naive | 5204 | 13288 | 77.127 | 227.536 | 6.597 | 92.3 |
| cardinality d7/i3 | semi-naive | 47000 | 152527 | 759.865 | 3061.815 | 83.966 | 547.1 |
| cardinality d5/i9 | semi-naive | 10286 | 39862 | 130.497 | 685.736 | 19.773 | 160.1 |
| factored unions 4 pairs/128 subjects | semi-naive | 638 | 1281 | 6.027 | 6.263 | 0.265 | 41.4 |
| factored unions 8 pairs/128 subjects | semi-naive | 1178 | 2305 | 11.062 | 11.255 | 0.366 | 46.1 |
| factored unions 16 pairs/128 subjects | semi-naive | 2258 | 4353 | 21.450 | 26.627 | 0.575 | 55.2 |
| factored unions 32 pairs/128 subjects | semi-naive | 4418 | 8449 | 44.040 | 41.447 | 1.041 | 67.2 |
| factored unions 64 pairs/128 subjects | semi-naive | 8738 | 16641 | 104.242 | 105.388 | 1.850 | 98.8 |
| factored enumerations 16 pairs/128 subjects | semi-naive | 258 | 54 | 3.361 | 2.744 | 0.195 | 37.9 |
| factored enumerations 32 pairs/128 subjects | semi-naive | 386 | 102 | 5.160 | 3.768 | 0.200 | 41.1 |
| factored enumerations 64 pairs/128 subjects | semi-naive | 642 | 198 | 9.304 | 5.717 | 0.265 | 43.3 |
| maintenance d3/10% | semi-naive | 1096 | 4331 | 10.479 | 20.558 | 1.295 | 48.4 |
| maintenance d3/15% | semi-naive | 1096 | 4331 | 10.567 | 20.421 | 1.263 | 48.7 |
| maintenance d4/10% | semi-naive | 5471 | 25581 | 56.704 | 154.360 | 8.434 | 117.4 |
| maintenance d4/15% | semi-naive | 5471 | 25581 | 51.552 | 158.873 | 8.968 | 115.2 |
| maintenance d5/10% | semi-naive | 27346 | 147456 | 449.888 | 1399.206 | 56.102 | 467.0 |
| maintenance d5/15% | semi-naive | 27346 | 147456 | 277.787 | 1438.969 | 55.979 | 470.4 |
| Bach Table 2.5 (Turtle) | semi-naive | 164 | 99 | 2.694 | 1.466 | 42.830 | 42.5 |
| Bach Table 2.5 (RDF/XML) | semi-naive | 164 | 99 | 2.613 | 1.429 | 43.013 | 43.0 |
| Bach family maintenance (Turtle) | semi-naive | 25 | 58 | 0.336 | 0.564 | 3.425 | 36.9 |

## Additional query timings

| Workload | Property pairs ms | Subsumption ms |
|---|---:|---:|
| taxonomy d3/i3/P0 | 0.066 | 0.069 |
| taxonomy d3/i3/P1 | 0.073 | 0.072 |
| taxonomy d3/i3/PF | 0.091 | 0.071 |
| taxonomy d3/i9/P0 | 0.191 | 0.067 |
| taxonomy d3/i9/P1 | 0.229 | 0.074 |
| taxonomy d3/i9/PF | 0.241 | 0.073 |
| taxonomy d3/i15/P0 | 0.309 | 0.076 |
| taxonomy d3/i15/P1 | 0.369 | 0.074 |
| taxonomy d3/i15/PF | 0.388 | 0.074 |
| taxonomy d5/i3/P0 | 0.878 | 0.618 |
| taxonomy d5/i3/P1 | 0.921 | 0.654 |
| taxonomy d5/i3/PF | 1.048 | 0.706 |
| taxonomy d5/i9/P0 | 2.837 | 0.787 |
| taxonomy d5/i9/P1 | 2.765 | 0.782 |
| taxonomy d5/i9/PF | 3.286 | 0.851 |
| taxonomy d5/i15/P0 | 4.452 | 0.871 |
| taxonomy d5/i15/P1 | 4.940 | 0.927 |
| taxonomy d5/i15/PF | 5.438 | 1.080 |
| taxonomy d7/i3/P0 | 13.546 | 6.469 |
| taxonomy d7/i3/P1 | 13.692 | 6.469 |
| taxonomy d7/i3/PF | 16.294 | 6.876 |
| taxonomy d7/i9/P0 | 46.253 | 8.694 |
| taxonomy d7/i9/P1 | 46.590 | 8.978 |
| taxonomy d7/i9/PF | 53.715 | 9.713 |
| taxonomy d7/i15/P0 | 120.641 | 10.165 |
| taxonomy d7/i15/P1 | 124.393 | 11.647 |
| taxonomy d7/i15/PF | 120.137 | 12.843 |
| taxonomy d3/i3/P0 | 0.065 | 0.069 |

## Incremental maintenance

Every operation is checked against a fresh closure from separately tracked facts and rules. Synthetic maintenance uses precompiled Engine inputs, excluding recompilation from both timings. Bach uses RDF updates and includes compilation in both timings.

| Workload | Operation | Update ms | Fresh rebuild ms | Observed method |
|---|---|---:|---:|---|
| maintenance d3/10% | fact_delete | 13.202 | 19.354 | dred |
| maintenance d3/10% | fact_insert | 3.289 | 20.347 | incremental-insert |
| maintenance d3/10% | rule_insert | 7.232 | 23.828 | incremental-rules |
| maintenance d3/10% | rule_delete | 9.774 | 22.748 | dred-rules |
| maintenance d3/10% | rule_replace | 10.685 | 22.698 | dred-rules |
| maintenance d3/10% | atomic_mixed | 12.744 | 19.993 | dred-rules |
| maintenance d3/15% | fact_delete | 12.998 | 17.864 | dred |
| maintenance d3/15% | fact_insert | 4.064 | 20.519 | incremental-insert |
| maintenance d3/15% | rule_insert | 7.056 | 24.001 | incremental-rules |
| maintenance d3/15% | rule_delete | 9.683 | 22.835 | dred-rules |
| maintenance d3/15% | rule_replace | 10.427 | 22.519 | dred-rules |
| maintenance d3/15% | atomic_mixed | 12.691 | 19.614 | dred-rules |
| maintenance d4/10% | fact_delete | 98.567 | 143.907 | dred |
| maintenance d4/10% | fact_insert | 19.586 | 195.115 | incremental-insert |
| maintenance d4/10% | rule_insert | 38.458 | 218.525 | incremental-rules |
| maintenance d4/10% | rule_delete | 81.628 | 213.318 | dred-rules |
| maintenance d4/10% | rule_replace | 60.826 | 210.823 | dred-rules |
| maintenance d4/10% | atomic_mixed | 72.195 | 190.822 | dred-rules |
| maintenance d4/15% | fact_delete | 77.524 | 146.695 | dred |
| maintenance d4/15% | fact_insert | 24.232 | 164.304 | incremental-insert |
| maintenance d4/15% | rule_insert | 67.106 | 184.833 | incremental-rules |
| maintenance d4/15% | rule_delete | 84.795 | 212.655 | dred-rules |
| maintenance d4/15% | rule_replace | 58.961 | 203.188 | dred-rules |
| maintenance d4/15% | atomic_mixed | 73.204 | 188.835 | dred-rules |
| maintenance d5/10% | fact_delete | 732.195 | 1303.462 | dred |
| maintenance d5/10% | fact_insert | 116.278 | 1519.191 | incremental-insert |
| maintenance d5/10% | rule_insert | 228.417 | 1495.092 | incremental-rules |
| maintenance d5/10% | rule_delete | 413.883 | 1612.047 | dred-rules |
| maintenance d5/10% | rule_replace | 457.058 | 1598.564 | dred-rules |
| maintenance d5/10% | atomic_mixed | 791.637 | 1450.282 | dred-rules |
| maintenance d5/15% | fact_delete | 608.832 | 1316.560 | dred |
| maintenance d5/15% | fact_insert | 147.161 | 1380.673 | incremental-insert |
| maintenance d5/15% | rule_insert | 218.483 | 1645.547 | incremental-rules |
| maintenance d5/15% | rule_delete | 407.214 | 1521.670 | dred-rules |
| maintenance d5/15% | rule_replace | 753.958 | 1526.673 | dred-rules |
| maintenance d5/15% | atomic_mixed | 518.557 | 1349.173 | dred-rules |
| Bach family maintenance (Turtle) | facts_update | 1.018 | 1.205 | dred |
| Bach family maintenance (Turtle) | rule_delete | 0.717 | 0.943 | dred-rules |
| Bach family maintenance (Turtle) | symmetry_insert | 0.867 | 1.415 | incremental-rules |

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
| unionOf | 4 | 16 | 10 | 1 | 6.027 |
| unionOf | 8 | 256 | 18 | 1 | 11.062 |
| unionOf | 16 | 65536 | 34 | 1 | 21.450 |
| unionOf | 32 | 4294967296 | 66 | 1 | 44.040 |
| unionOf | 64 | 18446744073709551616 | 130 | 1 | 104.242 |
| oneOf | 16 | 65536 | 34 | 1 | 3.361 |
| oneOf | 32 | 4294967296 | 66 | 1 | 5.160 |
| oneOf | 64 | 18446744073709551616 | 130 | 1 | 9.304 |

## Before/after comparison on unchanged inputs

Baseline: `/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/benchmarks/baselines/b1254c4/results.json`, run 2026-09-09T11:35:50.349359+00:00. Reference commit: `b1254c441731ca4fdf32ea83570ff99aaa84ac2a`. Rows require identical case controls, input hashes and timing boundaries. Different source hashes are retained in JSON for attribution. Ratios below 1 mean a shorter current median. Brackets show deterministic 95% percentile bootstrap intervals for the ratio of medians, resampling the recorded observations. With five repetitions in one worker per case, these are descriptive sensitivity intervals, not guarantees of independent-run coverage or causal speedup. They omit between-run machine-load/drift effects.

Cross-version correctness checks passed for 51/51 matched cases: initial fact counts, expected query-answer checks, and maintenance closure counts. The historical report does not store full answer-set digests.

| Workload | Engine | Previous materialize ms | Current materialize ms | Ratio [interval] | Candidate rows before → after |
|---|---|---:|---:|---:|---:|
| taxonomy d3/i3/P0 | semi-naive | 3.089 | 2.830 | 0.9162 [0.8528, 1.149] | 306 → 306 |
| taxonomy d3/i3/P1 | semi-naive | 2.973 | 3.134 | 1.054 [0.9253, 1.18] | 306 → 306 |
| taxonomy d3/i3/PF | semi-naive | 3.884 | 4.002 | 1.03 [0.9286, 1.102] | 306 → 306 |
| taxonomy d3/i9/P0 | semi-naive | 7.731 | 7.699 | 0.9959 [0.9217, 1.664] | 918 → 918 |
| taxonomy d3/i9/P1 | semi-naive | 8.843 | 8.966 | 1.014 [0.6232, 1.611] | 918 → 918 |
| taxonomy d3/i9/PF | semi-naive | 11.003 | 10.839 | 0.9851 [0.4791, 1.519] | 918 → 918 |
| taxonomy d3/i15/P0 | semi-naive | 12.620 | 12.519 | 0.992 [0.9764, 1.027] | 1530 → 1530 |
| taxonomy d3/i15/P1 | semi-naive | 14.439 | 13.987 | 0.9686 [0.5334, 1.33] | 1530 → 1530 |
| taxonomy d3/i15/PF | semi-naive | 17.561 | 17.651 | 1.005 [0.9556, 1.027] | 1530 → 1530 |
| taxonomy d5/i3/P0 | semi-naive | 36.123 | 40.090 | 1.11 [0.77, 1.295] | 4923 → 4923 |
| taxonomy d5/i3/P1 | semi-naive | 58.334 | 51.105 | 0.8761 [0.6243, 1.286] | 4923 → 4923 |
| taxonomy d5/i3/PF | semi-naive | 60.895 | 45.673 | 0.75 [0.6353, 1.357] | 4923 → 4923 |
| taxonomy d5/i9/P0 | semi-naive | 141.331 | 124.425 | 0.8804 [0.766, 1.123] | 14769 → 14769 |
| taxonomy d5/i9/P1 | semi-naive | 137.726 | 144.068 | 1.046 [0.8727, 1.202] | 14769 → 14769 |
| taxonomy d5/i9/PF | semi-naive | 161.332 | 167.100 | 1.036 [0.8286, 1.235] | 14769 → 14769 |
| taxonomy d5/i15/P0 | semi-naive | 238.712 | 230.232 | 0.9645 [0.8406, 1.027] | 24615 → 24615 |
| taxonomy d5/i15/P1 | semi-naive | 268.182 | 230.025 | 0.8577 [0.8147, 1.036] | 24615 → 24615 |
| taxonomy d5/i15/PF | semi-naive | 268.046 | 277.843 | 1.037 [0.8514, 1.221] | 24615 → 24615 |
| taxonomy d7/i3/P0 | semi-naive | 675.359 | 627.548 | 0.9292 [0.7946, 1.034] | 63972 → 63972 |
| taxonomy d7/i3/P1 | semi-naive | 822.431 | 749.057 | 0.9108 [0.7158, 1.18] | 63972 → 63972 |
| taxonomy d7/i3/PF | semi-naive | 914.899 | 844.506 | 0.9231 [0.8184, 1.083] | 63972 → 63972 |
| taxonomy d7/i9/P0 | semi-naive | 2068.547 | 2347.012 | 1.135 [0.8807, 1.258] | 191916 → 191916 |
| taxonomy d7/i9/P1 | semi-naive | 4044.267 | 2151.096 | 0.5319 [0.1765, 0.6548] | 191916 → 191916 |
| taxonomy d7/i9/PF | semi-naive | 3602.462 | 2853.775 | 0.7922 [0.6719, 0.9018] | 191916 → 191916 |
| taxonomy d7/i15/P0 | semi-naive | 4866.225 | 3501.702 | 0.7196 [0.3257, 0.8409] | 319860 → 319860 |
| taxonomy d7/i15/P1 | semi-naive | 4299.402 | 4182.578 | 0.9728 [0.8004, 1.081] | 319860 → 319860 |
| taxonomy d7/i15/PF | semi-naive | 4860.310 | 4777.663 | 0.983 [0.6261, 1.087] | 319860 → 319860 |
| taxonomy d3/i3/P0 | naive | 3.595 | 3.699 | 1.029 [0.4776, 1.061] | 954 → 954 |
| taxonomy d3/i3/P0 | owlrl | 99.400 | 96.956 | 0.9754 [0.9551, 1.006] | — |
| equality 100 | semi-naive | 12.141 | 11.890 | 0.9793 [0.7071, 1.004] | 1800 → 1800 |
| equality 1000 | semi-naive | 137.208 | 132.597 | 0.9664 [0.8299, 0.9847] | 18000 → 18000 |
| existential 100 | semi-naive | 69.623 | 66.276 | 0.9519 [0.883, 1.009] | 800 → 800 |
| transitive 100 | semi-naive | 451.250 | 446.153 | 0.9887 [0.9725, 1.019] | 204656 → 204656 |
| cardinality d3/i3 | semi-naive | 20.620 | 18.562 | 0.9002 [0.8437, 0.9768] | 3900 → 3900 |
| cardinality d5/i3 | semi-naive | 243.571 | 227.536 | 0.9342 [0.8365, 1.084] | 41250 → 41250 |
| cardinality d7/i3 | semi-naive | 2942.138 | 3061.815 | 1.041 [0.8893, 1.183] | 416424 → 416424 |
| cardinality d5/i9 | semi-naive | 941.582 | 685.736 | 0.7283 [0.4844, 1.024] | 123750 → 123750 |
| factored unions 4 pairs/128 subjects | semi-naive | 14.022 | 6.263 | 0.4467 [0.3521, 0.6057] | 2112 → 672 |
| factored unions 8 pairs/128 subjects | semi-naive | 57.850 | 11.255 | 0.1946 [0.1893, 0.2539] | 7232 → 1184 |
| factored unions 16 pairs/128 subjects | semi-naive | 301.281 | 26.627 | 0.08838 [0.06778, 0.1176] | 26688 → 2208 |
| factored unions 32 pairs/128 subjects | semi-naive | 1663.508 | 41.447 | 0.02492 [0.01685, 0.02908] | 102464 → 4256 |
| factored unions 64 pairs/128 subjects | semi-naive | 10406.030 | 105.388 | 0.01013 [0.008526, 0.01051] | 401472 → 8352 |
| factored enumerations 16 pairs/128 subjects | semi-naive | 4.340 | 2.744 | 0.6322 [0.5954, 0.6598] | 305 → 34 |
| factored enumerations 32 pairs/128 subjects | semi-naive | 15.561 | 3.768 | 0.2421 [0.2319, 0.2448] | 1121 → 66 |
| factored enumerations 64 pairs/128 subjects | semi-naive | 95.863 | 5.717 | 0.05964 [0.05608, 0.06091] | 4289 → 130 |
| maintenance d3/10% | semi-naive | 22.419 | 20.558 | 0.917 [0.6259, 0.9388] | 3080 → 3080 |
| maintenance d3/15% | semi-naive | 21.925 | 20.421 | 0.9314 [0.569, 0.9688] | 3080 → 3080 |
| maintenance d4/10% | semi-naive | 167.815 | 154.360 | 0.9198 [0.7812, 1.196] | 19330 → 19330 |
| maintenance d4/15% | semi-naive | 193.323 | 158.873 | 0.8218 [0.755, 1.01] | 19330 → 19330 |
| maintenance d5/10% | semi-naive | 1281.996 | 1399.206 | 1.091 [0.6846, 1.251] | 116205 → 116205 |
| maintenance d5/15% | semi-naive | 1649.397 | 1438.969 | 0.8724 [0.6467, 1.29] | 116205 → 116205 |

### Parsing, compilation and public query calls

Subsumption still times the complete first public call on each fresh reasoner. A lazy schema index or fast path built inside that call remains inside the timing. It is not silently excluded as setup. All phase samples remain available in JSON.

| Workload / engine | Phase | Previous ms | Current ms | Ratio [interval] |
|---|---|---:|---:|---:|
| taxonomy d3/i3/P0 / semi-naive | parse | 1.756 | 1.733 | 0.9869 [0.7002, 1.45] |
| taxonomy d3/i3/P0 / semi-naive | compile | 1.859 | 2.000 | 1.076 [0.9881, 1.362] |
| taxonomy d3/i3/P0 / semi-naive | query | 0.179 | 0.193 | 1.078 [1.002, 1.102] |
| taxonomy d3/i3/P0 / semi-naive | property_query | 0.062 | 0.066 | 1.076 [1.022, 1.115] |
| taxonomy d3/i3/P0 / semi-naive | subsumption | 7.130 | 0.069 | 0.009625 [0.006369, 0.01069] |
| taxonomy d3/i3/P1 / semi-naive | parse | 2.391 | 2.366 | 0.9894 [0.7448, 1.359] |
| taxonomy d3/i3/P1 / semi-naive | compile | 2.624 | 2.819 | 1.074 [0.9056, 1.202] |
| taxonomy d3/i3/P1 / semi-naive | query | 0.199 | 0.211 | 1.062 [1.01, 1.174] |
| taxonomy d3/i3/P1 / semi-naive | property_query | 0.071 | 0.073 | 1.035 [0.9943, 1.072] |
| taxonomy d3/i3/P1 / semi-naive | subsumption | 8.712 | 0.072 | 0.008322 [0.005347, 0.03424] |
| taxonomy d3/i3/PF / semi-naive | parse | 5.054 | 4.476 | 0.8856 [0.8109, 1.129] |
| taxonomy d3/i3/PF / semi-naive | compile | 4.729 | 4.875 | 1.031 [0.4801, 2.233] |
| taxonomy d3/i3/PF / semi-naive | query | 0.228 | 0.241 | 1.059 [1.016, 1.104] |
| taxonomy d3/i3/PF / semi-naive | property_query | 0.083 | 0.091 | 1.087 [1.005, 1.171] |
| taxonomy d3/i3/PF / semi-naive | subsumption | 13.080 | 0.071 | 0.005422 [0.004833, 0.006489] |
| taxonomy d3/i9/P0 / semi-naive | parse | 4.173 | 3.789 | 0.9078 [0.8464, 1.182] |
| taxonomy d3/i9/P0 / semi-naive | compile | 4.004 | 4.136 | 1.033 [0.935, 1.096] |
| taxonomy d3/i9/P0 / semi-naive | query | 0.540 | 0.552 | 1.021 [0.9433, 1.104] |
| taxonomy d3/i9/P0 / semi-naive | property_query | 0.189 | 0.191 | 1.013 [0.83, 1.055] |
| taxonomy d3/i9/P0 / semi-naive | subsumption | 17.337 | 0.067 | 0.003872 [0.002621, 0.004655] |
| taxonomy d3/i9/P1 / semi-naive | parse | 4.942 | 5.161 | 1.044 [0.8473, 1.23] |
| taxonomy d3/i9/P1 / semi-naive | compile | 5.678 | 6.180 | 1.088 [1.026, 1.142] |
| taxonomy d3/i9/P1 / semi-naive | query | 0.592 | 0.635 | 1.074 [1.039, 1.259] |
| taxonomy d3/i9/P1 / semi-naive | property_query | 0.214 | 0.229 | 1.069 [1.037, 1.108] |
| taxonomy d3/i9/P1 / semi-naive | subsumption | 20.912 | 0.074 | 0.003533 [0.002386, 0.004224] |
| taxonomy d3/i9/PF / semi-naive | parse | 8.767 | 8.983 | 1.025 [0.9615, 1.109] |
| taxonomy d3/i9/PF / semi-naive | compile | 9.401 | 10.155 | 1.08 [1.041, 1.123] |
| taxonomy d3/i9/PF / semi-naive | query | 0.667 | 0.718 | 1.076 [1.018, 1.237] |
| taxonomy d3/i9/PF / semi-naive | property_query | 0.236 | 0.241 | 1.024 [0.9995, 1.076] |
| taxonomy d3/i9/PF / semi-naive | subsumption | 30.023 | 0.073 | 0.002433 [0.001869, 0.002593] |
| taxonomy d3/i15/P0 / semi-naive | parse | 5.568 | 6.094 | 1.095 [0.8855, 1.285] |
| taxonomy d3/i15/P0 / semi-naive | compile | 6.174 | 6.162 | 0.9981 [0.9655, 1.909] |
| taxonomy d3/i15/P0 / semi-naive | query | 0.878 | 0.920 | 1.047 [1.013, 1.062] |
| taxonomy d3/i15/P0 / semi-naive | property_query | 0.312 | 0.309 | 0.9903 [0.9823, 1.052] |
| taxonomy d3/i15/P0 / semi-naive | subsumption | 26.737 | 0.076 | 0.002849 [0.002567, 0.00328] |
| taxonomy d3/i15/P1 / semi-naive | parse | 8.245 | 7.854 | 0.9526 [0.8753, 1.081] |
| taxonomy d3/i15/P1 / semi-naive | compile | 8.846 | 9.027 | 1.02 [0.9938, 1.046] |
| taxonomy d3/i15/P1 / semi-naive | query | 0.984 | 1.019 | 1.035 [0.9806, 1.088] |
| taxonomy d3/i15/P1 / semi-naive | property_query | 0.354 | 0.369 | 1.042 [1.016, 1.088] |
| taxonomy d3/i15/P1 / semi-naive | subsumption | 32.686 | 0.074 | 0.002273 [0.001967, 0.003144] |
| taxonomy d3/i15/PF / semi-naive | parse | 13.417 | 12.984 | 0.9677 [0.4198, 1.387] |
| taxonomy d3/i15/PF / semi-naive | compile | 14.557 | 15.197 | 1.044 [0.975, 1.716] |
| taxonomy d3/i15/PF / semi-naive | query | 1.109 | 1.128 | 1.017 [0.9848, 1.043] |
| taxonomy d3/i15/PF / semi-naive | property_query | 0.392 | 0.388 | 0.9878 [0.9659, 1.038] |
| taxonomy d3/i15/PF / semi-naive | subsumption | 52.956 | 0.074 | 0.001401 [0.001227, 0.001667] |
| taxonomy d5/i3/P0 / semi-naive | parse | 16.283 | 15.765 | 0.9682 [0.9406, 1.016] |
| taxonomy d5/i3/P0 / semi-naive | compile | 17.418 | 17.796 | 1.022 [1.006, 1.064] |
| taxonomy d5/i3/P0 / semi-naive | query | 1.998 | 2.102 | 1.052 [0.9933, 1.125] |
| taxonomy d5/i3/P0 / semi-naive | property_query | 0.864 | 0.878 | 1.016 [0.9952, 1.056] |
| taxonomy d5/i3/P0 / semi-naive | subsumption | 83.211 | 0.618 | 0.007428 [0.007127, 0.01019] |
| taxonomy d5/i3/P1 / semi-naive | parse | 23.173 | 21.829 | 0.942 [0.9264, 0.9843] |
| taxonomy d5/i3/P1 / semi-naive | compile | 24.735 | 24.997 | 1.011 [0.8463, 1.174] |
| taxonomy d5/i3/P1 / semi-naive | query | 2.403 | 2.315 | 0.9635 [0.919, 1.118] |
| taxonomy d5/i3/P1 / semi-naive | property_query | 0.997 | 0.921 | 0.9238 [0.6759, 0.9969] |
| taxonomy d5/i3/P1 / semi-naive | subsumption | 103.113 | 0.654 | 0.006347 [0.005827, 0.008883] |
| taxonomy d5/i3/PF / semi-naive | parse | 27.847 | 28.226 | 1.014 [0.6365, 1.477] |
| taxonomy d5/i3/PF / semi-naive | compile | 32.279 | 32.463 | 1.006 [0.8576, 1.155] |
| taxonomy d5/i3/PF / semi-naive | query | 2.428 | 2.801 | 1.153 [1.009, 1.265] |
| taxonomy d5/i3/PF / semi-naive | property_query | 1.023 | 1.048 | 1.024 [1.007, 1.22] |
| taxonomy d5/i3/PF / semi-naive | subsumption | 118.737 | 0.706 | 0.005949 [0.005255, 0.006596] |
| taxonomy d5/i9/P0 / semi-naive | parse | 34.672 | 35.542 | 1.025 [0.5352, 1.073] |
| taxonomy d5/i9/P0 / semi-naive | compile | 36.539 | 38.783 | 1.061 [1.026, 1.086] |
| taxonomy d5/i9/P0 / semi-naive | query | 6.216 | 7.118 | 1.145 [1.09, 1.208] |
| taxonomy d5/i9/P0 / semi-naive | property_query | 2.659 | 2.837 | 1.067 [0.9744, 1.224] |
| taxonomy d5/i9/P0 / semi-naive | subsumption | 223.879 | 0.787 | 0.003515 [0.003406, 0.004626] |
| taxonomy d5/i9/P1 / semi-naive | parse | 46.667 | 49.313 | 1.057 [0.5917, 1.478] |
| taxonomy d5/i9/P1 / semi-naive | compile | 53.211 | 54.555 | 1.025 [0.5426, 1.379] |
| taxonomy d5/i9/P1 / semi-naive | query | 6.945 | 7.511 | 1.082 [0.997, 13.25] |
| taxonomy d5/i9/P1 / semi-naive | property_query | 2.801 | 2.765 | 0.987 [0.9628, 7.488] |
| taxonomy d5/i9/P1 / semi-naive | subsumption | 295.137 | 0.782 | 0.00265 [0.002512, 0.007927] |
| taxonomy d5/i9/PF / semi-naive | parse | 69.482 | 85.726 | 1.234 [0.601, 1.485] |
| taxonomy d5/i9/PF / semi-naive | compile | 86.649 | 90.676 | 1.046 [0.768, 1.371] |
| taxonomy d5/i9/PF / semi-naive | query | 7.713 | 8.555 | 1.109 [0.9831, 1.197] |
| taxonomy d5/i9/PF / semi-naive | property_query | 3.157 | 3.286 | 1.041 [0.9353, 1.057] |
| taxonomy d5/i9/PF / semi-naive | subsumption | 368.635 | 0.851 | 0.002309 [0.002134, 0.00335] |
| taxonomy d5/i15/P0 / semi-naive | parse | 52.788 | 60.299 | 1.142 [0.9916, 1.535] |
| taxonomy d5/i15/P0 / semi-naive | compile | 56.894 | 82.484 | 1.45 [0.6822, 1.538] |
| taxonomy d5/i15/P0 / semi-naive | query | 11.062 | 11.752 | 1.062 [1.028, 1.112] |
| taxonomy d5/i15/P0 / semi-naive | property_query | 4.400 | 4.452 | 1.012 [1.001, 1.06] |
| taxonomy d5/i15/P0 / semi-naive | subsumption | 402.960 | 0.871 | 0.002161 [0.001999, 0.002215] |
| taxonomy d5/i15/P1 / semi-naive | parse | 77.249 | 78.676 | 1.018 [0.5003, 1.345] |
| taxonomy d5/i15/P1 / semi-naive | compile | 85.097 | 112.575 | 1.323 [0.7314, 1.506] |
| taxonomy d5/i15/P1 / semi-naive | query | 12.172 | 13.436 | 1.104 [0.9921, 1.172] |
| taxonomy d5/i15/P1 / semi-naive | property_query | 4.848 | 4.940 | 1.019 [0.9731, 1.078] |
| taxonomy d5/i15/P1 / semi-naive | subsumption | 467.671 | 0.927 | 0.001982 [0.001836, 0.002159] |
| taxonomy d5/i15/PF / semi-naive | parse | 110.581 | 116.599 | 1.054 [0.5045, 1.383] |
| taxonomy d5/i15/PF / semi-naive | compile | 167.828 | 144.302 | 0.8598 [0.6108, 1.346] |
| taxonomy d5/i15/PF / semi-naive | query | 13.354 | 14.825 | 1.11 [1.04, 1.194] |
| taxonomy d5/i15/PF / semi-naive | property_query | 5.102 | 5.438 | 1.066 [1.007, 1.158] |
| taxonomy d5/i15/PF / semi-naive | subsumption | 624.705 | 1.080 | 0.001729 [0.001529, 0.001833] |
| taxonomy d7/i3/P0 / semi-naive | parse | 150.247 | 154.306 | 1.027 [0.4054, 1.456] |
| taxonomy d7/i3/P0 / semi-naive | compile | 164.006 | 228.704 | 1.394 [0.6005, 1.573] |
| taxonomy d7/i3/P0 / semi-naive | query | 27.909 | 28.856 | 1.034 [0.8374, 1.106] |
| taxonomy d7/i3/P0 / semi-naive | property_query | 12.851 | 13.546 | 1.054 [0.9059, 1.381] |
| taxonomy d7/i3/P0 / semi-naive | subsumption | 1099.823 | 6.469 | 0.005882 [0.005239, 0.006472] |
| taxonomy d7/i3/P1 / semi-naive | parse | 204.130 | 327.368 | 1.604 [0.6444, 1.729] |
| taxonomy d7/i3/P1 / semi-naive | compile | 229.462 | 228.349 | 0.9952 [0.6981, 1.116] |
| taxonomy d7/i3/P1 / semi-naive | query | 32.476 | 31.221 | 0.9614 [0.8448, 1.111] |
| taxonomy d7/i3/P1 / semi-naive | property_query | 14.183 | 13.692 | 0.9654 [0.7509, 1.099] |
| taxonomy d7/i3/P1 / semi-naive | subsumption | 1373.532 | 6.469 | 0.00471 [0.004011, 0.004915] |
| taxonomy d7/i3/PF / semi-naive | parse | 557.512 | 279.466 | 0.5013 [0.4065, 1.015] |
| taxonomy d7/i3/PF / semi-naive | compile | 301.628 | 290.802 | 0.9641 [0.7751, 1.079] |
| taxonomy d7/i3/PF / semi-naive | query | 35.109 | 34.951 | 0.9955 [0.9405, 1.091] |
| taxonomy d7/i3/PF / semi-naive | property_query | 19.076 | 16.294 | 0.8542 [0.8208, 1.168] |
| taxonomy d7/i3/PF / semi-naive | subsumption | 1487.098 | 6.876 | 0.004624 [0.004018, 0.005257] |
| taxonomy d7/i9/P0 / semi-naive | parse | 398.193 | 320.819 | 0.8057 [0.2365, 1.191] |
| taxonomy d7/i9/P0 / semi-naive | compile | 399.700 | 351.790 | 0.8801 [0.3097, 1.027] |
| taxonomy d7/i9/P0 / semi-naive | query | 84.207 | 110.074 | 1.307 [0.9468, 1.399] |
| taxonomy d7/i9/P0 / semi-naive | property_query | 47.229 | 46.253 | 0.9793 [0.8584, 1.219] |
| taxonomy d7/i9/P0 / semi-naive | subsumption | 3220.993 | 8.694 | 0.002699 [0.001301, 0.00307] |
| taxonomy d7/i9/P1 / semi-naive | parse | 1371.182 | 598.397 | 0.4364 [0.1102, 1.056] |
| taxonomy d7/i9/P1 / semi-naive | compile | 1160.278 | 502.551 | 0.4331 [0.1148, 0.6787] |
| taxonomy d7/i9/P1 / semi-naive | query | 148.352 | 94.931 | 0.6399 [0.2463, 0.9217] |
| taxonomy d7/i9/P1 / semi-naive | property_query | 88.410 | 46.590 | 0.527 [0.2865, 0.8938] |
| taxonomy d7/i9/P1 / semi-naive | subsumption | 6682.962 | 8.978 | 0.001343 [0.0008071, 0.001655] |
| taxonomy d7/i9/PF / semi-naive | parse | 1096.393 | 682.322 | 0.6223 [0.4578, 1.287] |
| taxonomy d7/i9/PF / semi-naive | compile | 1196.013 | 1078.071 | 0.9014 [0.444, 1.409] |
| taxonomy d7/i9/PF / semi-naive | query | 138.176 | 123.921 | 0.8968 [0.7248, 1.101] |
| taxonomy d7/i9/PF / semi-naive | property_query | 69.315 | 53.715 | 0.7749 [0.6706, 1.065] |
| taxonomy d7/i9/PF / semi-naive | subsumption | 5910.086 | 9.713 | 0.001643 [0.001231, 0.001956] |
| taxonomy d7/i15/P0 / semi-naive | parse | 785.515 | 562.537 | 0.7161 [0.5119, 1.326] |
| taxonomy d7/i15/P0 / semi-naive | compile | 814.767 | 529.566 | 0.65 [0.3809, 0.8571] |
| taxonomy d7/i15/P0 / semi-naive | query | 241.877 | 158.159 | 0.6539 [0.1662, 0.8624] |
| taxonomy d7/i15/P0 / semi-naive | property_query | 142.110 | 120.641 | 0.8489 [0.3765, 1.031] |
| taxonomy d7/i15/P0 / semi-naive | subsumption | 9245.125 | 10.165 | 0.001099 [0.000793, 0.001669] |
| taxonomy d7/i15/P1 / semi-naive | parse | 1816.613 | 674.532 | 0.3713 [0.3091, 0.8842] |
| taxonomy d7/i15/P1 / semi-naive | compile | 1290.508 | 902.166 | 0.6991 [0.4397, 1.305] |
| taxonomy d7/i15/P1 / semi-naive | query | 190.131 | 216.728 | 1.14 [0.8509, 1.29] |
| taxonomy d7/i15/P1 / semi-naive | property_query | 117.928 | 124.393 | 1.055 [0.817, 1.306] |
| taxonomy d7/i15/P1 / semi-naive | subsumption | 7663.222 | 11.647 | 0.00152 [0.0008172, 0.002101] |
| taxonomy d7/i15/PF / semi-naive | parse | 1163.029 | 1820.139 | 1.565 [0.6016, 1.99] |
| taxonomy d7/i15/PF / semi-naive | compile | 1242.354 | 1159.083 | 0.933 [0.3397, 1.61] |
| taxonomy d7/i15/PF / semi-naive | query | 200.764 | 242.963 | 1.21 [0.9398, 1.38] |
| taxonomy d7/i15/PF / semi-naive | property_query | 119.607 | 120.137 | 1.004 [0.792, 1.3] |
| taxonomy d7/i15/PF / semi-naive | subsumption | 7983.876 | 12.843 | 0.001609 [0.0009848, 0.001971] |
| taxonomy d3/i3/P0 / naive | parse | 1.803 | 1.768 | 0.9808 [0.6742, 1.391] |
| taxonomy d3/i3/P0 / naive | compile | 2.095 | 1.972 | 0.9414 [0.7435, 1.122] |
| taxonomy d3/i3/P0 / naive | query | 0.191 | 0.196 | 1.027 [0.9482, 1.133] |
| taxonomy d3/i3/P0 / naive | property_query | 0.064 | 0.065 | 1.02 [0.9049, 1.098] |
| taxonomy d3/i3/P0 / naive | subsumption | 9.144 | 0.069 | 0.007514 [0.007249, 0.00863] |
| taxonomy d3/i3/P0 / owlrl | parse | 1.908 | 1.773 | 0.9292 [0.6675, 1.279] |
| taxonomy d3/i3/P0 / owlrl | compile | 0.000 | 0.000 | — |
| taxonomy d3/i3/P0 / owlrl | query | 0.075 | 0.074 | 0.9922 [0.9753, 1.12] |
| equality 100 / semi-naive | parse | 2.764 | 2.742 | 0.9919 [0.7822, 1.233] |
| equality 100 / semi-naive | compile | 3.493 | 3.420 | 0.9791 [0.8688, 2.277] |
| equality 100 / semi-naive | query | 0.486 | 0.472 | 0.9716 [0.917, 1.125] |
| equality 1000 / semi-naive | parse | 27.928 | 26.633 | 0.9536 [0.6181, 1.468] |
| equality 1000 / semi-naive | compile | 35.664 | 33.236 | 0.9319 [0.8263, 1.325] |
| equality 1000 / semi-naive | query | 5.314 | 5.068 | 0.9538 [0.7054, 1.239] |
| existential 100 / semi-naive | parse | 1.077 | 1.071 | 0.9948 [0.5942, 1.621] |
| existential 100 / semi-naive | compile | 1.334 | 1.296 | 0.9713 [0.8237, 1.072] |
| existential 100 / semi-naive | query | 6.868 | 6.516 | 0.9488 [0.923, 0.9694] |
| transitive 100 / semi-naive | parse | 1.050 | 0.960 | 0.9143 [0.1455, 1.661] |
| transitive 100 / semi-naive | compile | 1.339 | 1.257 | 0.9387 [0.8947, 1.02] |
| transitive 100 / semi-naive | query | 12.634 | 12.248 | 0.9695 [0.9016, 1.506] |
| cardinality d3/i3 / semi-naive | parse | 6.019 | 5.752 | 0.9556 [0.8309, 1.046] |
| cardinality d3/i3 / semi-naive | compile | 7.996 | 8.056 | 1.007 [0.6054, 1.663] |
| cardinality d3/i3 / semi-naive | query | 0.595 | 0.579 | 0.9737 [0.9088, 0.9908] |
| cardinality d5/i3 / semi-naive | parse | 52.724 | 60.013 | 1.138 [0.7596, 1.523] |
| cardinality d5/i3 / semi-naive | compile | 78.527 | 77.127 | 0.9822 [0.7075, 1.302] |
| cardinality d5/i3 / semi-naive | query | 7.545 | 6.597 | 0.8744 [0.8544, 0.955] |
| cardinality d7/i3 / semi-naive | parse | 668.684 | 625.590 | 0.9356 [0.6483, 1.367] |
| cardinality d7/i3 / semi-naive | compile | 760.432 | 759.865 | 0.9993 [0.7874, 1.752] |
| cardinality d7/i3 / semi-naive | query | 85.394 | 83.966 | 0.9833 [0.926, 1.148] |
| cardinality d5/i9 / semi-naive | parse | 157.891 | 130.560 | 0.8269 [0.3947, 1.215] |
| cardinality d5/i9 / semi-naive | compile | 226.737 | 130.497 | 0.5755 [0.4653, 0.9922] |
| cardinality d5/i9 / semi-naive | query | 26.488 | 19.773 | 0.7465 [0.5503, 0.9344] |
| factored unions 4 pairs/128 subjects / semi-naive | parse | 7.557 | 5.675 | 0.7509 [0.5064, 1.496] |
| factored unions 4 pairs/128 subjects / semi-naive | compile | 8.437 | 6.027 | 0.7143 [0.6264, 0.956] |
| factored unions 4 pairs/128 subjects / semi-naive | query | 0.320 | 0.265 | 0.8287 [0.6117, 0.9594] |
| factored unions 8 pairs/128 subjects / semi-naive | parse | 15.032 | 10.445 | 0.6949 [0.5664, 0.9755] |
| factored unions 8 pairs/128 subjects / semi-naive | compile | 15.791 | 11.062 | 0.7005 [0.5564, 0.91] |
| factored unions 8 pairs/128 subjects / semi-naive | query | 0.674 | 0.366 | 0.5438 [0.3689, 0.7231] |
| factored unions 16 pairs/128 subjects / semi-naive | parse | 33.722 | 20.019 | 0.5936 [0.3903, 0.9969] |
| factored unions 16 pairs/128 subjects / semi-naive | compile | 36.010 | 21.450 | 0.5957 [0.2572, 0.9562] |
| factored unions 16 pairs/128 subjects / semi-naive | query | 0.986 | 0.575 | 0.5837 [0.541, 0.7941] |
| factored unions 32 pairs/128 subjects / semi-naive | parse | 61.096 | 40.006 | 0.6548 [0.475, 0.8769] |
| factored unions 32 pairs/128 subjects / semi-naive | compile | 91.399 | 44.040 | 0.4818 [0.368, 0.7189] |
| factored unions 32 pairs/128 subjects / semi-naive | query | 1.562 | 1.041 | 0.6664 [0.4905, 0.7533] |
| factored unions 64 pairs/128 subjects / semi-naive | parse | 84.582 | 76.214 | 0.9011 [0.6904, 1.061] |
| factored unions 64 pairs/128 subjects / semi-naive | compile | 87.182 | 104.242 | 1.196 [0.7871, 1.27] |
| factored unions 64 pairs/128 subjects / semi-naive | query | 2.286 | 1.850 | 0.8092 [0.7647, 0.8996] |
| factored enumerations 16 pairs/128 subjects / semi-naive | parse | 2.547 | 2.516 | 0.988 [0.7834, 1.271] |
| factored enumerations 16 pairs/128 subjects / semi-naive | compile | 3.674 | 3.361 | 0.9148 [0.8011, 0.9818] |
| factored enumerations 16 pairs/128 subjects / semi-naive | query | 0.193 | 0.195 | 1.007 [0.9597, 1.079] |
| factored enumerations 32 pairs/128 subjects / semi-naive | parse | 3.894 | 3.637 | 0.934 [0.756, 1.263] |
| factored enumerations 32 pairs/128 subjects / semi-naive | compile | 5.644 | 5.160 | 0.9142 [0.8935, 0.9882] |
| factored enumerations 32 pairs/128 subjects / semi-naive | query | 0.238 | 0.200 | 0.8399 [0.7707, 0.8975] |
| factored enumerations 64 pairs/128 subjects / semi-naive | parse | 6.368 | 6.286 | 0.9871 [0.8395, 1.152] |
| factored enumerations 64 pairs/128 subjects / semi-naive | compile | 9.435 | 9.304 | 0.9861 [0.9467, 1.034] |
| factored enumerations 64 pairs/128 subjects / semi-naive | query | 0.301 | 0.265 | 0.881 [0.8178, 0.8914] |
| maintenance d3/10% / semi-naive | parse | 10.184 | 9.385 | 0.9215 [0.8756, 0.9848] |
| maintenance d3/10% / semi-naive | compile | 10.703 | 10.479 | 0.979 [0.9615, 1.536] |
| maintenance d3/10% / semi-naive | query | 1.339 | 1.295 | 0.967 [0.8392, 1.117] |
| maintenance d3/15% / semi-naive | parse | 10.221 | 9.209 | 0.901 [0.414, 1.05] |
| maintenance d3/15% / semi-naive | compile | 10.631 | 10.567 | 0.994 [0.9716, 1.521] |
| maintenance d3/15% / semi-naive | query | 1.301 | 1.263 | 0.9713 [0.9356, 1.034] |
| maintenance d4/10% / semi-naive | parse | 52.051 | 46.624 | 0.8957 [0.5021, 1.054] |
| maintenance d4/10% / semi-naive | compile | 80.813 | 56.704 | 0.7017 [0.5255, 1.403] |
| maintenance d4/10% / semi-naive | query | 8.500 | 8.434 | 0.9922 [0.8977, 1.043] |
| maintenance d4/15% / semi-naive | parse | 53.710 | 49.898 | 0.929 [0.5317, 1.221] |
| maintenance d4/15% / semi-naive | compile | 52.740 | 51.552 | 0.9775 [0.9544, 1.486] |
| maintenance d4/15% / semi-naive | query | 8.639 | 8.968 | 1.038 [0.8886, 1.119] |
| maintenance d5/10% / semi-naive | parse | 249.729 | 252.930 | 1.013 [0.4512, 1.745] |
| maintenance d5/10% / semi-naive | compile | 300.286 | 449.888 | 1.498 [0.6226, 1.799] |
| maintenance d5/10% / semi-naive | query | 57.330 | 56.102 | 0.9786 [0.8231, 1.132] |
| maintenance d5/15% / semi-naive | parse | 292.262 | 282.998 | 0.9683 [0.325, 1.493] |
| maintenance d5/15% / semi-naive | compile | 276.383 | 277.787 | 1.005 [0.9105, 1.618] |
| maintenance d5/15% / semi-naive | query | 55.067 | 55.979 | 1.017 [0.8599, 1.07] |

### Maintenance compared with the pinned implementation

These rows compare the same operation across versions. The separate fresh-rebuild ratio compares each version's recomputation cost. Input mutation counts and fresh-closure validation must agree before an operation is compared. All common evaluation counters and raw operation samples are retained in JSON.

| Workload | Operation | Previous ms | Current ms | Update ratio [interval] | Rebuild ratio [interval] | Overdeleted before → after |
|---|---|---:|---:|---:|---:|---:|
| maintenance d3/10% | fact_delete | 14.815 | 13.202 | 0.8911 [0.5481, 1.265] | 0.9764 [0.9384, 0.9808] | 442 → 442 |
| maintenance d3/10% | fact_insert | 3.595 | 3.289 | 0.9148 [0.8505, 0.9824] | 0.9385 [0.5814, 1.3] | 0 → 0 |
| maintenance d3/10% | rule_insert | 7.858 | 7.232 | 0.9203 [0.8847, 0.9634] | 0.9437 [0.6333, 1.269] | 0 → 0 |
| maintenance d3/10% | rule_delete | 10.313 | 9.774 | 0.9477 [0.4831, 0.9743] | 0.934 [0.6817, 1.237] | 276 → 276 |
| maintenance d3/10% | rule_replace | 11.668 | 10.685 | 0.9157 [0.8931, 0.9636] | 0.8997 [0.6188, 1.169] | 272 → 272 |
| maintenance d3/10% | atomic_mixed | 13.472 | 12.744 | 0.946 [0.8468, 1.404] | 0.6538 [0.5773, 0.9726] | 975 → 975 |
| maintenance d3/15% | fact_delete | 13.933 | 12.998 | 0.9329 [0.6916, 1.371] | 0.9519 [0.9365, 0.9864] | 659 → 659 |
| maintenance d3/15% | fact_insert | 4.089 | 4.064 | 0.9938 [0.8704, 1.085] | 0.9476 [0.6218, 1.289] | 0 → 0 |
| maintenance d3/15% | rule_insert | 7.653 | 7.056 | 0.922 [0.8967, 0.9544] | 0.9676 [0.6581, 1.275] | 0 → 0 |
| maintenance d3/15% | rule_delete | 10.047 | 9.683 | 0.9638 [0.5639, 0.9955] | 0.965 [0.7741, 1.282] | 256 → 256 |
| maintenance d3/15% | rule_replace | 10.962 | 10.427 | 0.9512 [0.9063, 0.9733] | 0.9416 [0.6218, 1.24] | 262 → 262 |
| maintenance d3/15% | atomic_mixed | 13.416 | 12.691 | 0.946 [0.896, 0.9762] | 0.9563 [0.6128, 1.278] | 1070 → 1070 |
| maintenance d4/10% | fact_delete | 115.146 | 98.567 | 0.856 [0.6247, 1.257] | 0.9504 [0.7898, 1.252] | 2555 → 2555 |
| maintenance d4/10% | fact_insert | 19.578 | 19.586 | 1 [0.3588, 1.071] | 0.9111 [0.7345, 1.096] | 0 → 0 |
| maintenance d4/10% | rule_insert | 39.179 | 38.458 | 0.9816 [0.9428, 1.868] | 0.922 [0.7175, 0.9883] | 0 → 0 |
| maintenance d4/10% | rule_delete | 101.124 | 81.628 | 0.8072 [0.5633, 1.725] | 0.9476 [0.8126, 1.194] | 1408 → 1408 |
| maintenance d4/10% | rule_replace | 66.449 | 60.826 | 0.9154 [0.545, 1.474] | 0.9047 [0.7621, 1.115] | 1406 → 1406 |
| maintenance d4/10% | atomic_mixed | 78.822 | 72.195 | 0.9159 [0.6119, 1.367] | 0.8853 [0.7184, 1.156] | 5075 → 5075 |
| maintenance d4/15% | fact_delete | 115.920 | 77.524 | 0.6688 [0.6335, 0.9859] | 1.043 [0.967, 1.185] | 3822 → 3822 |
| maintenance d4/15% | fact_insert | 24.074 | 24.232 | 1.007 [0.9546, 1.035] | 0.7714 [0.7019, 0.9478] | 0 → 0 |
| maintenance d4/15% | rule_insert | 38.753 | 67.106 | 1.732 [0.9702, 1.784] | 0.7827 [0.7236, 1.045] | 0 → 0 |
| maintenance d4/15% | rule_delete | 60.045 | 84.795 | 1.412 [0.7537, 1.55] | 0.9566 [0.9192, 1.079] | 1342 → 1342 |
| maintenance d4/15% | rule_replace | 104.455 | 58.961 | 0.5645 [0.52, 0.8909] | 1.108 [0.8357, 1.188] | 1332 → 1332 |
| maintenance d4/15% | atomic_mixed | 117.141 | 73.204 | 0.6249 [0.5962, 0.9705] | 1.151 [0.8202, 1.184] | 5657 → 5657 |
| maintenance d5/10% | fact_delete | 634.307 | 732.195 | 1.154 [0.9456, 1.36] | 1.082 [0.8166, 1.276] | 14744 → 14744 |
| maintenance d5/10% | fact_insert | 290.468 | 116.278 | 0.4003 [0.3078, 3.079] | 1.101 [0.872, 1.185] | 0 → 0 |
| maintenance d5/10% | rule_insert | 219.359 | 228.417 | 1.041 [0.4122, 2.257] | 0.9249 [0.8223, 1.124] | 0 → 0 |
| maintenance d5/10% | rule_delete | 685.817 | 413.883 | 0.6035 [0.5232, 1.39] | 1.065 [0.8773, 1.369] | 7000 → 7000 |
| maintenance d5/10% | rule_replace | 417.815 | 457.058 | 1.094 [0.55, 1.966] | 1.091 [0.8818, 1.16] | 7088 → 7088 |
| maintenance d5/10% | atomic_mixed | 771.007 | 791.637 | 1.027 [0.6513, 1.576] | 0.958 [0.8766, 1.374] | 26362 → 26362 |
| maintenance d5/15% | fact_delete | 569.547 | 608.832 | 1.069 [0.8315, 1.245] | 0.9225 [0.6934, 1.216] | 22162 → 22162 |
| maintenance d5/15% | fact_insert | 147.132 | 147.161 | 1 [0.4259, 2.126] | 0.8967 [0.7997, 0.9984] | 0 → 0 |
| maintenance d5/15% | rule_insert | 219.218 | 218.483 | 0.9966 [0.4494, 2.461] | 0.9841 [0.7188, 1.177] | 0 → 0 |
| maintenance d5/15% | rule_delete | 421.620 | 407.214 | 0.9658 [0.5743, 1.66] | 0.9013 [0.8102, 0.9662] | 6580 → 6580 |
| maintenance d5/15% | rule_replace | 749.609 | 753.958 | 1.006 [0.5059, 1.987] | 0.8695 [0.7316, 0.9988] | 6670 → 6670 |
| maintenance d5/15% | atomic_mixed | 817.228 | 518.557 | 0.6345 [0.5106, 1.205] | 0.9334 [0.8259, 1.008] | 29778 → 29778 |

Matched 51 cases; excluded 3 new or changed cases. The raw report records each exclusion reason. No workload or reference timing is rewritten to obtain a match.

These workloads use the Bach worked examples and synthetic inputs inspired by thesis chapter 8, not a reproduction of the 2004 KAON/XSB/Racer measurements. Modern hardware, execution strategies and measurement boundaries differ. OWL RL includes additional axiomatic/schema triples, so its total closure count is not directly comparable; the named instance answers are verified.

The naive strategy shares the compiler and equality machinery; it is an execution baseline, not an independent semantic oracle. Unit validation also uses OWL RL and exhaustive finite models. There is no performance acceptance threshold or claim of production-scale throughput.

## Bach Table 2.5 (Turtle): checked queries

Source: `examples/bach.ttl`; profile L3. Parsing measures the original document syntax. Query ms in the summary is the total of all queries below.

| Query | Thesis reference | Answer | Median ms |
|---|---|---|---:|
| fathers | Table 2.5 T5/A1–A4/A7, p. 35; §5.4.2.2, p. 132 | `["johann-ambrosius", "johann-sebastian"]` | 0.027 |
| mothers | Table 2.5 T6, p. 35; §5.4.2.2, p. 132 | `[]` | 0.016 |
| people | Table 2.5 T1/T2/T5, p. 35; §5.4.2.2, p. 132 | `["anna-magdalena", "johann-ambrosius", "johann-sebastian", "maria-barbara", "wilhelm-friedemann"]` | 0.038 |
| masterpieces | Table 2.5 T11/A2/A9/A10, p. 35 | `["BWV248"]` | 0.017 |
| birthday-cantatas | Table 2.5 A14/A15, p. 35 | `["BWV213", "BWV214"]` | 0.017 |
| compositions | Table 2.5 T12–T15/A13–A15, p. 35 | `["BWV213", "BWV214", "BWV248"]` | 0.018 |
| named-birthdays | Table 2.5 T12/A14/A15, p. 35; Example 4.5.2, p. 94 | `[]` | 0.024 |
| leipzig-inhabitants | Table 2.5 T10/A8, p. 35 | `["johann-sebastian"]` | 0.016 |
| wives | Table 2.5 T3/A5/A6/A11/A12, p. 35 | `[]` | 0.014 |
| ambrosius-is-father | Table 2.5 T5/A1/A7, p. 35; §5.4.2.1, p. 132 | `true` | 0.016 |
| ambrosius-named-son-not-entailed | Table 2.5 A1, p. 35; Example 4.5.2, p. 94 | `false` | 0.012 |
| sebastian-known-children | Example 5.4.1, p. 131; §5.4.3, pp. 134–135 | `["wilhelm-friedemann"]` | 0.024 |
| sebastian-marriages | Table 2.5 A6/A12, p. 35; §5.4.3, pp. 134–135 | `["anna-magdalena", "maria-barbara"]` | 0.019 |
| symmetric-marriage | Table 2.5 T9/A6, p. 35; §5.4.3, pp. 134–135 | `["johann-sebastian"]` | 0.017 |
| sebastian-types | §5.4.2.3, p. 134; Table 2.5, p. 35 | `["Composer", "Father", "Genius", "LeipzigInhabitant", "Man", "Person", "owl:Thing"]` | 0.020 |
| male-child-existential | Example 4.5.2, p. 94; §5.4.2, pp. 132–133 | `["johann-ambrosius"]` | 11.897 |
| child-filler-intersection-union | Adapted Example 5.4.2, pp. 133–134; explicit filler scope | `["johann-ambrosius"]` | 12.429 |
| person-subsumes-father | Example 2.4.3, p. 39; §5.4.4.1, p. 135 | `true` | 0.073 |
| father-does-not-subsume-person | §5.4.4.1, pp. 135–136; Table 2.5 T5, p. 35 | `false` | 5.795 |
| composition-subsumes-birthday-cantata | Table 2.5 T12–T15, p. 35; §5.4.4.1, pp. 135–136 | `true` | 0.011 |
| father-satisfiable | Example 2.4.3, p. 39; §5.4.4.4, pp. 137–138 | `true` | 5.898 |
| ancestor-subsumes-child | Table 2.5 T7, p. 35; §5.4.4.5, pp. 138–139 | `true` | 0.010 |
| ancestor-transitive | Table 2.5 T8, p. 35; §5.4.4.6, p. 140 | `true` | 0.005 |
| marriage-symmetric | Table 2.5 T9, p. 35; §5.4.4.6, pp. 139–140 | `true` | 0.004 |
| dynasty-not-transitive | Table 2.5 T16/T17, p. 35; §6.2.2, p. 151 (corrected) | `false` | 5.798 |

## Bach Table 2.5 (RDF/XML): checked queries

Source: `examples/bach.owl`; profile L3. Parsing measures the original document syntax. Query ms in the summary is the total of all queries below.

| Query | Thesis reference | Answer | Median ms |
|---|---|---|---:|
| fathers | Table 2.5 T5/A1–A4/A7, p. 35; §5.4.2.2, p. 132 | `["johann-ambrosius", "johann-sebastian"]` | 0.027 |
| mothers | Table 2.5 T6, p. 35; §5.4.2.2, p. 132 | `[]` | 0.016 |
| people | Table 2.5 T1/T2/T5, p. 35; §5.4.2.2, p. 132 | `["anna-magdalena", "johann-ambrosius", "johann-sebastian", "maria-barbara", "wilhelm-friedemann"]` | 0.037 |
| masterpieces | Table 2.5 T11/A2/A9/A10, p. 35 | `["BWV248"]` | 0.017 |
| birthday-cantatas | Table 2.5 A14/A15, p. 35 | `["BWV213", "BWV214"]` | 0.017 |
| compositions | Table 2.5 T12–T15/A13–A15, p. 35 | `["BWV213", "BWV214", "BWV248"]` | 0.018 |
| named-birthdays | Table 2.5 T12/A14/A15, p. 35; Example 4.5.2, p. 94 | `[]` | 0.024 |
| leipzig-inhabitants | Table 2.5 T10/A8, p. 35 | `["johann-sebastian"]` | 0.016 |
| wives | Table 2.5 T3/A5/A6/A11/A12, p. 35 | `[]` | 0.014 |
| ambrosius-is-father | Table 2.5 T5/A1/A7, p. 35; §5.4.2.1, p. 132 | `true` | 0.016 |
| ambrosius-named-son-not-entailed | Table 2.5 A1, p. 35; Example 4.5.2, p. 94 | `false` | 0.013 |
| sebastian-known-children | Example 5.4.1, p. 131; §5.4.3, pp. 134–135 | `["wilhelm-friedemann"]` | 0.024 |
| sebastian-marriages | Table 2.5 A6/A12, p. 35; §5.4.3, pp. 134–135 | `["anna-magdalena", "maria-barbara"]` | 0.018 |
| symmetric-marriage | Table 2.5 T9/A6, p. 35; §5.4.3, pp. 134–135 | `["johann-sebastian"]` | 0.016 |
| sebastian-types | §5.4.2.3, p. 134; Table 2.5, p. 35 | `["Composer", "Father", "Genius", "LeipzigInhabitant", "Man", "Person", "owl:Thing"]` | 0.020 |
| male-child-existential | Example 4.5.2, p. 94; §5.4.2, pp. 132–133 | `["johann-ambrosius"]` | 11.957 |
| child-filler-intersection-union | Adapted Example 5.4.2, pp. 133–134; explicit filler scope | `["johann-ambrosius"]` | 12.354 |
| person-subsumes-father | Example 2.4.3, p. 39; §5.4.4.1, p. 135 | `true` | 0.076 |
| father-does-not-subsume-person | §5.4.4.1, pp. 135–136; Table 2.5 T5, p. 35 | `false` | 5.608 |
| composition-subsumes-birthday-cantata | Table 2.5 T12–T15, p. 35; §5.4.4.1, pp. 135–136 | `true` | 0.012 |
| father-satisfiable | Example 2.4.3, p. 39; §5.4.4.4, pp. 137–138 | `true` | 5.718 |
| ancestor-subsumes-child | Table 2.5 T7, p. 35; §5.4.4.5, pp. 138–139 | `true` | 0.010 |
| ancestor-transitive | Table 2.5 T8, p. 35; §5.4.4.6, p. 140 | `true` | 0.006 |
| marriage-symmetric | Table 2.5 T9, p. 35; §5.4.4.6, pp. 139–140 | `true` | 0.004 |
| dynasty-not-transitive | Table 2.5 T16/T17, p. 35; §6.2.2, p. 151 (corrected) | `false` | 5.949 |

## Bach family maintenance (Turtle): checked queries

Source: `examples/bach-family.ttl`; profile L0. Parsing measures the original document syntax. Query ms in the summary is the total of all queries below.

| Query | Thesis reference | Answer | Median ms |
|---|---|---|---:|
| johannes-descendants | Figure 6.2, p. 150; Example 6.3.2, p. 158 | `["christoph", "heinrich", "johann-ambrosius", "johann-christoph", "johann-michael", "johann-sebastian", "maria-barbara", "wilhelm-friedemann"]` | 0.028 |
| ambrosius-descendants | Figure 6.2; §6.2.1, p. 150 | `["johann-sebastian", "wilhelm-friedemann"]` | 0.017 |
| johannes-reaches-wilhelm | Figure 6.2; §6.2.1, p. 150 | `true` | 0.015 |
| base-dynasty-not-symmetric | Table 6.1; §6.2.2, p. 151 | `false` | 1.895 |
| base-dynasty-not-transitive | Table 6.1; §6.2.2, p. 151 | `false` | 1.422 |
| base-ancestor-transitive | Table 6.1 T1, p. 151 | `true` | 0.006 |
| base-cross-branch-not-entailed | §6.2.2, p. 151; docs/THESIS_ERRATA.md item 6 | `false` | 0.013 |

Bach updates each start from the original family graph. Both RDF update and fresh rebuild timings include compilation. Exact pair sets and the three removed/four added ancestor pairs are checked against independent graph traversal and recorded in JSON.
