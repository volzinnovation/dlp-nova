# Measured benchmark results

Run: 2026-09-09T10:50:18.777091+00:00. Python 3.12.9; macOS-26.5.1-arm64-arm-64bit.

All times below are medians in milliseconds. Every raw sample is in `results.json`.
Peak RSS is the entire isolated worker (including parser, retained input and repetitions), not incremental reasoner allocation. Compiler and materializer timings are separate.

| Workload | Engine | Input triples | Closure facts | Compile ms | Materialize ms | Query ms | Peak MiB |
|---|---|---:|---:|---:|---:|---:|---:|
| taxonomy d3/i3/P0 | semi-naive | 196 | 541 | 1.841 | 2.869 | 0.186 | 38.7 |
| taxonomy d3/i3/P1 | semi-naive | 275 | 580 | 2.588 | 3.077 | 0.203 | 39.8 |
| taxonomy d3/i3/PF | semi-naive | 513 | 659 | 4.834 | 4.123 | 0.242 | 44.4 |
| taxonomy d3/i9/P0 | semi-naive | 430 | 1621 | 3.831 | 7.892 | 0.544 | 49.1 |
| taxonomy d3/i9/P1 | semi-naive | 587 | 1738 | 5.676 | 9.059 | 0.614 | 49.8 |
| taxonomy d3/i9/PF | semi-naive | 981 | 1973 | 9.785 | 10.995 | 0.730 | 53.4 |
| taxonomy d3/i15/P0 | semi-naive | 664 | 2701 | 6.050 | 12.698 | 0.883 | 47.5 |
| taxonomy d3/i15/P1 | semi-naive | 899 | 2896 | 8.741 | 14.447 | 0.999 | 52.6 |
| taxonomy d3/i15/PF | semi-naive | 1449 | 3287 | 14.367 | 17.808 | 1.117 | 60.5 |
| taxonomy d5/i3/P0 | semi-naive | 1816 | 7102 | 16.547 | 41.022 | 2.106 | 65.3 |
| taxonomy d5/i3/P1 | semi-naive | 2543 | 7465 | 23.428 | 62.341 | 2.209 | 73.9 |
| taxonomy d5/i3/PF | semi-naive | 3105 | 8192 | 31.399 | 47.146 | 2.468 | 77.3 |
| taxonomy d5/i9/P0 | semi-naive | 3994 | 21304 | 35.644 | 123.021 | 6.202 | 101.8 |
| taxonomy d5/i9/P1 | semi-naive | 5447 | 22393 | 52.614 | 143.101 | 7.236 | 120.2 |
| taxonomy d5/i9/PF | semi-naive | 7461 | 24572 | 102.650 | 175.229 | 8.486 | 130.7 |
| taxonomy d5/i15/P0 | semi-naive | 6172 | 35506 | 56.556 | 237.871 | 11.222 | 137.2 |
| taxonomy d5/i15/P1 | semi-naive | 8351 | 37321 | 113.410 | 281.924 | 12.977 | 149.6 |
| taxonomy d5/i15/PF | semi-naive | 11817 | 40952 | 181.631 | 301.345 | 15.366 | 182.7 |
| taxonomy d7/i3/P0 | semi-naive | 16396 | 83647 | 157.675 | 633.873 | 29.575 | 281.6 |
| taxonomy d7/i3/P1 | semi-naive | 22955 | 86926 | 225.595 | 804.882 | 33.973 | 364.5 |
| taxonomy d7/i3/PF | semi-naive | 26433 | 93485 | 293.151 | 909.897 | 35.736 | 379.6 |
| taxonomy d7/i9/P0 | semi-naive | 36070 | 250939 | 525.783 | 2050.202 | 84.357 | 652.1 |
| taxonomy d7/i9/P1 | semi-naive | 49187 | 260776 | 518.548 | 2298.690 | 89.635 | 774.1 |
| taxonomy d7/i9/PF | semi-naive | 65781 | 280451 | 1058.627 | 2579.609 | 101.164 | 973.8 |
| taxonomy d7/i15/P0 | semi-naive | 55744 | 418231 | 532.935 | 3557.792 | 156.294 | 1053.8 |
| taxonomy d7/i15/P1 | semi-naive | 75419 | 434626 | 860.575 | 3801.796 | 182.337 | 1248.7 |
| taxonomy d7/i15/PF | semi-naive | 105129 | 467417 | 1169.578 | 4548.465 | 188.464 | 1524.8 |
| taxonomy d3/i3/P0 | naive | 196 | 541 | 1.829 | 3.908 | 0.184 | 40.2 |
| taxonomy d3/i3/P0 | owlrl | 196 | 1105 | 0.000 | 93.754 | 0.067 | 37.5 |
| equality 100 | semi-naive | 302 | 601 | 3.268 | 11.538 | 0.450 | 39.5 |
| equality 1000 | semi-naive | 3002 | 6001 | 32.419 | 129.228 | 4.968 | 71.3 |
| existential 100 | semi-naive | 112 | 1401 | 1.231 | 66.283 | 6.459 | 39.1 |
| transitive 100 | semi-naive | 101 | 5152 | 1.236 | 444.733 | 12.017 | 45.8 |
| maintenance  | semi-naive | 5461 | 22451 | 51.288 | 152.248 | 7.191 | 123.5 |

Maintenance deletion median: 105.753 ms; full rebuild: 145.344 ms.


## Additional query and maintenance timings

| Workload | Property pairs ms | Subsumption ms | Delete ms | Insert ms | Rule insert ms | Rebuild ms |
|---|---:|---:|---:|---:|---:|---:|
| d3/i3/P0 | 0.064 | 7.419 | — | — | — | — |
| d3/i3/P1 | 0.072 | 8.751 | — | — | — | — |
| d3/i3/PF | 0.087 | 13.766 | — | — | — | — |
| d3/i9/P0 | 0.193 | 16.921 | — | — | — | — |
| d3/i9/P1 | 0.220 | 21.192 | — | — | — | — |
| d3/i9/PF | 0.245 | 34.990 | — | — | — | — |
| d3/i15/P0 | 0.312 | 26.585 | — | — | — | — |
| d3/i15/P1 | 0.352 | 32.834 | — | — | — | — |
| d3/i15/PF | 0.392 | 53.218 | — | — | — | — |
| d5/i3/P0 | 0.883 | 82.211 | — | — | — | — |
| d5/i3/P1 | 0.939 | 102.101 | — | — | — | — |
| d5/i3/PF | 1.022 | 120.280 | — | — | — | — |
| d5/i9/P0 | 2.718 | 230.545 | — | — | — | — |
| d5/i9/P1 | 2.839 | 302.687 | — | — | — | — |
| d5/i9/PF | 3.281 | 384.243 | — | — | — | — |
| d5/i15/P0 | 4.420 | 434.800 | — | — | — | — |
| d5/i15/P1 | 4.917 | 456.047 | — | — | — | — |
| d5/i15/PF | 5.974 | 652.709 | — | — | — | — |
| d7/i3/P0 | 15.424 | 1059.002 | — | — | — | — |
| d7/i3/P1 | 19.093 | 1362.937 | — | — | — | — |
| d7/i3/PF | 19.392 | 1540.487 | — | — | — | — |
| d7/i9/P0 | 47.697 | 3090.463 | — | — | — | — |
| d7/i9/P1 | 47.837 | 3546.990 | — | — | — | — |
| d7/i9/PF | 53.197 | 4427.417 | — | — | — | — |
| d7/i15/P0 | 89.254 | 5212.128 | — | — | — | — |
| d7/i15/P1 | 94.440 | 6336.702 | — | — | — | — |
| d7/i15/PF | 102.904 | 7552.961 | — | — | — | — |
| d3/i3/P0 | 0.061 | 8.404 | — | — | — | — |
| maintenance | — | — | 105.753 | 15.397 | 144.208 | 145.344 |

These are synthetic workloads inspired by thesis chapter 8, not a reproduction of the 2004 KAON/XSB/Racer measurements. Modern hardware, execution strategies and measurement boundaries differ. OWL RL includes additional axiomatic/schema triples, so its total closure count is not directly comparable; the named instance answers are verified.

The naive strategy shares the compiler and equality machinery; it is an execution baseline, not an independent semantic oracle. Unit validation also uses OWL RL and exhaustive finite models. There is no performance acceptance threshold or claim of production-scale throughput.
