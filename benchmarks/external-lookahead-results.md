# Post-hoc bounded lookahead evaluation

This separately registered follow-up was motivated by the previous Q5 intermediate-count finding. It retains all six TPC-H-derived components and adds four adverse synthetic controls. Each observation uses a fresh process for a single component. Original artifacts are unchanged.

| Case | Configuration | Answers | Join median(ms) | Component total median(ms) | Process wall median(ms) | Candidate rows by block |
|---|---|---:|---:|---:|---:|---|
| sf0.01-q3 | b1254c4 | 356 | 6.499 | 280.919 | 543.466 | [2490, 2490, 2490] |
| sf0.01-q3 | compiled | 356 | 4.436 | 277.488 | 512.115 | [2490, 2490, 2490] |
| sf0.01-q3 | lookahead | 356 | 4.628 | 273.489 | 506.164 | [2490, 2490, 2490] |
| sf0.01-q5 | b1254c4 | 103 | 58.258 | 527.912 | 883.061 | [13739, 13739, 13739] |
| sf0.01-q5 | compiled | 103 | 48.740 | 516.853 | 836.049 | [13739, 13739, 13739] |
| sf0.01-q5 | lookahead | 103 | 49.326 | 526.162 | 851.610 | [13739, 13739, 13739] |
| sf0.01-q9 | b1254c4 | 3223 | 48.721 | 769.167 | 1269.514 | [24668, 24668, 24668] |
| sf0.01-q9 | compiled | 3223 | 32.406 | 757.941 | 1180.421 | [24668, 24668, 24668] |
| sf0.01-q9 | lookahead | 3223 | 33.060 | 756.847 | 1173.513 | [24668, 24668, 24668] |
| sf0.1-q3 | b1254c4 | 3321 | 58.692 | 4919.761 | 7574.997 | [21656, 21656, 21656] |
| sf0.1-q3 | compiled | 3321 | 42.424 | 4971.353 | 7029.186 | [21656, 21656, 21656] |
| sf0.1-q3 | lookahead | 3321 | 43.047 | 4930.417 | 6954.358 | [21656, 21656, 21656] |
| sf0.1-q5 | b1254c4 | 865 | 923.572 | 7508.549 | 11223.637 | [632591, 632591, 632591] |
| sf0.1-q5 | compiled | 865 | 515.218 | 7306.866 | 10150.572 | [621901, 621901, 621901] |
| sf0.1-q5 | lookahead | 865 | 260.271 | 9298.470 | 13041.727 | [155969, 155969, 155969] |
| sf0.1-q9 | b1254c4 | 32160 | 398.469 | 10619.594 | 15309.713 | [246125, 246125, 246125] |
| sf0.1-q9 | compiled | 32160 | 262.076 | 10705.226 | 14130.349 | [246125, 246125, 246125] |
| sf0.1-q9 | lookahead | 32160 | 272.030 | 10707.923 | 14105.014 | [246125, 246125, 246125] |
| control-unique | b1254c4 | 64 | 0.316 | 1.206 | 63.346 | [192, 192, 192] |
| control-unique | compiled | 64 | 0.283 | 1.145 | 70.616 | [192, 192, 192] |
| control-unique | lookahead | 64 | 0.309 | 1.155 | 65.172 | [192, 192, 192] |
| control-nonselective | b1254c4 | 4096 | 119.297 | 131.080 | 3542.619 | [266304, 266304, 266304] |
| control-nonselective | compiled | 4096 | 7.757 | 19.834 | 3425.317 | [8256, 8256, 8256] |
| control-nonselective | lookahead | 4096 | 8.272 | 20.442 | 3444.484 | [8256, 8256, 8256] |
| control-skewed | b1254c4 | 64 | 0.399 | 1.205 | 77.583 | [384, 384, 384] |
| control-skewed | compiled | 64 | 0.282 | 1.134 | 76.892 | [192, 192, 192] |
| control-skewed | lookahead | 64 | 0.341 | 1.247 | 78.212 | [192, 192, 192] |
| control-empty-cycle | b1254c4 | 0 | 0.296 | 1.204 | 64.199 | [192, 192, 192] |
| control-empty-cycle | compiled | 0 | 0.177 | 1.112 | 64.574 | [128, 128, 128] |
| control-empty-cycle | lookahead | 0 | 0.220 | 1.110 | 65.240 | [128, 128, 128] |

All results are validated against complete independent SQL/control answers and the complete base closure. TPC-H SQL bag row identities, filter pushdown and scope are unchanged from `external-tpch-methodology.md`. Aggregation, ordering, top-k and full TPC-H scores remain outside the experiment.

The compiled and lookahead arms share adopted optimizations and recursive-closure cleanup. The only difference between them is invocation-local ordering lookahead, disabled by default. It samples up to 4 rows from each of two similarly sized buckets (minimum 32 rows, factor 4), uses at most 1024 extra lookups, and never prunes rows. Planning, complete answer consumption and cleanup are included in join time. A fixed work budget provides no bound on a bad ordering choice.

The JSON contains every observation, fixed protocol, source archive, original input hashes, planning counters, paired ratios and observed ranges. Process wall time includes validation, hashing, startup, serialization and teardown; component total excludes those costs. Three matched blocks are descriptive. This is an adaptation experiment, not an RPT+/SYA implementation or a claim of state-of-the-art performance.

```sh
tmp/tpch-python/bin/python -m benchmarks.external_lookahead --blocks 3 --output /tmp/lookahead-reproduction.json
```
