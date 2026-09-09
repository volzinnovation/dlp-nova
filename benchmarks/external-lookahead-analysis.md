# Analysis of the separate bounded-lookahead experiment

Raw report: `benchmarks/external-lookahead-results.json`, SHA-256 `fc2a9d7bf5f82e6fc24938ff7f7dd1758c13ee6ccabce6645566bcd9882aa387`. The 90 workers ran from 2026-09-09T18:25:27.501031+00:00 to 2026-09-09T18:31:44.434862+00:00. The source archive SHA-256 is `e88dd9c8e1ea25145c05b5a6eb172f5d06074d03631cc295583edd54bb1e9253`.

All 54 TPC-H-derived and 36 adverse-control observations passed complete independent answer comparisons and exact full base-closure checks. A separate verification recomputed every summary median/range and all 60 paired metric summaries, checked every configuration flag and imported source/driver hash, checked the preserved archive members, and matched each SQL answer digest/count to the pinned manifest.

“Registered” in the generated artifact means a locally saved, frozen protocol at launch. It is not independently timestamped or publicly preregistered. This is explicitly a post-hoc study motivated by the preceding Q5 findings. All timing comparisons below are within this study; the older sequential-query experiment is preserved and is not pooled with it.

## Paired effects and limits

The principal result is narrower than a general speedup: on Q5 at SF0.1, lookahead reduces enumerated candidates from 621,901 to 155,969 while preserving all 865 answers. It uses 30 extra lookups, 16 physical samples and 2 hints, making 101 reordered choices. The median within-block join-time ratio is 0.510 against the same-source compiled control and 0.274 against b1254c4. The compiled and lookahead arms share every other optimization and the closure-lifecycle correction.

Entries below are median within-block lookahead/compiled elapsed-time ratios, with the complete observed range in parentheses. Below 1 means less time. Three repetitions are descriptive, not confidence intervals.

| Case | Answers | Join ratio | Component total ratio | Process wall ratio |
|---|---:|---:|---:|---:|
| sf0.01-q3 | 356 | 0.996 (0.995–1.043) | 0.986 (0.983–1.015) | 0.979 (0.971–0.988) |
| sf0.01-q5 | 103 | 1.001 (0.967–1.012) | 1.016 (0.984–1.018) | 1.011 (0.982–1.019) |
| sf0.01-q9 | 3223 | 1.040 (1.020–1.052) | 1.004 (0.999–1.034) | 0.998 (0.994–1.026) |
| sf0.1-q3 | 3321 | 1.015 (1.006–1.024) | 1.001 (0.992–1.029) | 1.003 (0.989–1.027) |
| sf0.1-q5 | 865 | 0.510 (0.481–0.520) | 0.975 (0.972–1.273) | 0.990 (0.976–1.285) |
| sf0.1-q9 | 32160 | 1.043 (1.021–1.076) | 1.000 (0.961–1.008) | 0.998 (0.972–1.009) |
| control-unique | 64 | 1.123 (1.090–1.124) | 1.019 (1.009–1.038) | 0.990 (0.923–1.027) |
| control-nonselective | 4096 | 1.066 (1.053–1.082) | 1.029 (1.027–1.037) | 1.006 (1.005–1.011) |
| control-skewed | 64 | 1.155 (1.070–1.251) | 1.027 (0.991–1.167) | 0.995 (0.989–1.017) |
| control-empty-cycle | 0 | 1.238 (1.218–1.302) | 1.064 (0.999–1.066) | 1.008 (0.992–1.010) |

Q5 SF0.1 has separate join medians of 0.515s compiled and 0.260s lookahead. Its separate component-total medians go in the other direction: 7.307s and 9.298s. The paired total ratio is 0.975 with range 0.972–1.273. These are different estimands: one slower matched block changes the ordering of the three marginal total observations. A robust end-to-end improvement is not established by this small, variable sample. The paired process-wall ratio is 0.990, also with a wide range.

Extraction, encoding and indexing dominate many component totals. Process wall time additionally contains startup, full-file hashing, independent oracle execution, validation, serialization and teardown. In particular, the deliberately simple independent nested-join oracle dominates the nonselective control’s process wall time, so that metric should not be interpreted as its query-kernel cost.

Lookahead regresses in every adverse control against the compiled control: paired median join increases are 12.3% (unique), 6.6% (nonselective), 15.5% (skewed) and 23.8% (empty cycle). These controls make no reordered choices, so their added work brings no reduction. Three controls have sub-millisecond join times; absolute costs and ranges matter. Q9 adds about 4% join overhead at both scales. Q3 and small Q5 do not show a consistent benefit. `_join_lookahead_enabled` therefore remains False by default.

## Exact work and planning counters

Candidate-row counts and all reported planning counters are identical across the three blocks of each configuration. Baseline improvements already present in the compiled control must not be attributed to lookahead.

| Case | b125 rows | Compiled rows | Lookahead rows | Extra probes | Samples | Hints | Cache hits | Reordered choices |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| sf0.01-q3 | 2,490 | 2,490 | 2,490 | 0 | 0 | 0 | 0 | 0 |
| sf0.01-q5 | 13,739 | 13,739 | 13,739 | 0 | 0 | 0 | 0 | 0 |
| sf0.01-q9 | 24,668 | 24,668 | 24,668 | 12 | 8 | 1 | 99 | 0 |
| sf0.1-q3 | 21,656 | 21,656 | 21,656 | 0 | 0 | 0 | 0 | 0 |
| sf0.1-q5 | 632,591 | 621,901 | 155,969 | 30 | 16 | 2 | 223 | 101 |
| sf0.1-q9 | 246,125 | 246,125 | 246,125 | 0 | 0 | 0 | 0 | 0 |
| control-unique | 192 | 192 | 192 | 16 | 8 | 1 | 0 | 0 |
| control-nonselective | 266,304 | 8,256 | 8,256 | 24 | 16 | 2 | 63 | 0 |
| control-skewed | 384 | 192 | 192 | 16 | 8 | 1 | 0 | 0 |
| control-empty-cycle | 192 | 128 | 128 | 16 | 8 | 1 | 0 | 0 |

No measured case exhausted the 1024-lookup or 1024-hint limit. Dedicated tests cover exhaustion and invalid repeated-variable samples that consume zero lookups. The bound permits at most 8192 sampled rows per invocation; it is not a runtime or regret bound. The samples are the first four physical index rows, not an unbiased statistical sample. All selected buckets are still enumerated fully.

## Interpretation and reproducibility

One fresh process per query component removes previous-engine teardown/retention from later component timers. Both new arms include the recursive-closure cleanup; gc-disabled weak-reference tests cover exhaustion, explicit close and exceptions. These checks establish prompt object release, not a causal explanation for the older experiment’s encoding-time differences. The old experiment uses a different execution protocol and must remain separate.

Only one benchmark worker ran at a time during the coordinated window. Normal desktop activity continued; neither CPU affinity nor the operating system’s scheduling/frequency was controlled. A read-only process snapshot showed a worker near one full CPU core and ordinary WindowServer activity during the window. All samples were retained. Input integrity hashing warms the filesystem cache; this is a fresh engine/process experiment, not cold-disk measurement.

The current-source arms explicitly enable compiled joins, incremental index maintenance and monotone validation reuse; only their lookahead flag differs. Historical b1254c4 lacks these private switches, recorded as null rather than pretending they are available. Full flags and parameters are recorded per worker. The source archive contains both exact benchmark drivers and all imported current package files; the historical package hashes were independently checked against its Git archive.

The result supports a bounded ordering adaptation for this identified Q5 case and documents its overhead elsewhere. It is not a reproduction or implementation of RPT+/SYA, a complete TPC-H score, a held-out generalization result, or evidence of state-of-the-art superiority. The preserved original data, exact oracles, adverse controls and new source/protocol make the narrower claim reproducible.
