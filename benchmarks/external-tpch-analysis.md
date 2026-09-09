# Analysis of the frozen TPC-H-derived component study

Raw report: `benchmarks/external-tpch-results.json`; SHA-256 `2efee8721e8555323f46cd23149285aab28e02811f5ce9bde047dcde175618be`. The study ran from 2026-09-09T18:07:01.311295+00:00 to 2026-09-09T18:14:39.371245+00:00.

All 24 fresh workers completed. All 72 component observations matched both the exact DuckDB SQL row-identity tuples and the independently specified complete base closure. The driver, protocol, generated input, imported package and summary statistics were checked again after completion. The current package hashes match `benchmarks/followup-source-manifest.json` and its preserved source archive.

The table reports median **within-block candidate/reference time ratios**, with the complete observed range in parentheses. Below 1 means the candidate used less elapsed time. These are three descriptive repetitions per case, not confidence intervals or significance tests. They differ from ratios of separately computed medians.

| Scale | Component | Candidate/b125 join | Candidate/current-fixed join | Candidate/current-fixed component total |
|---:|---|---:|---:|---:|
| 0.01 | Q3 | 0.724 (0.683–0.734) | 0.755 (0.693–0.787) | 0.985 (0.984–1.025) |
| 0.01 | Q5 | 0.569 (0.560–0.570) | 0.538 (0.533–0.539) | 0.974 (0.954–1.025) |
| 0.01 | Q9 | 0.636 (0.631–0.642) | 0.670 (0.658–0.677) | 0.959 (0.943–0.964) |
| 0.1 | Q3 | 0.719 (0.697–0.741) | 0.752 (0.738–0.774) | 1.008 (0.948–1.025) |
| 0.1 | Q5 | 0.523 (0.520–0.531) | 0.523 (0.512–0.529) | 0.919 (0.916–0.940) |
| 0.1 | Q9 | 0.674 (0.669–0.896) | 0.700 (0.674–0.702) | 0.952 (0.951–0.953) |

The positional plan reduces join interpretation time across these six cases. End-to-end improvement is smaller because loading and indexing dominate this adapter: the large Q3 total has a paired median ratio of 1.008, so this study does not establish a pipeline improvement for every case. The large Q5 component improves by about 8.1% against current-fixed, while its join interval improves by about 47.7%. These are component results with pushed-down filters; they are not complete TPC-H SQL scores.

## Evidence for a follow-up planning experiment

Candidate and current-fixed enumerate exactly the same number of candidate rows in every case and block. For Q5 that count rises from 13,739 at SF0.01 to 621,901 at SF0.1 (45.27 times), while input facts rise from 64,104 to 639,556 (9.98 times) and answers from 103 to 865 (8.40 times). Q3 candidate rows grow from 2,490 to 21,656 and Q9 from 24,668 to 246,125. The b1254c4 Q5 count at SF0.1 is 632,591; both later fixed implementations and the positional candidate visit 621,901.

The matched Q5 counters establish intermediate expansion on this workload. Inspection of its cyclic customer–orders–lineitem–supplier–nation join suggests that selecting a small current bucket without considering the next join can expose a large customer/supplier intermediate. The counters alone do not establish the precise causal decision; a separately versioned ordering ablation is needed. The positional plan improves per-row execution but leaves this ordering issue intact.

`docs/RESEARCH_JOIN_FOLLOWUP.md` describes two safe candidates. A bounded lookahead that changes only traversal order is the smaller next experiment. It can compare two similarly sized buckets using a fixed number of sampled next-step lookups, retain exact unification and complete row enumeration, and stop planning at a fixed probe budget. Samples must never filter answers. Invocation-local hints must be discarded between queries. This transfers a lesson about intermediate expansion from RPT+/SYA without implementing their algorithms or inheriting their guarantees.

This potential follow-up is post hoc: the current Q5 study supplied the motivation. Its implementation, constants, source snapshot, protocol and results must be separate from this frozen study. Evaluate all six unchanged components, charge planning to the join timer, retain total pipeline cost and negative controls, and report any regressions. Three runs on the discovery workload cannot establish general superiority or a new state-of-the-art claim.

Full paired values against b1254c4, 5531be4 and current-fixed are preserved in the companion analysis JSON. Original raw observations are unchanged.
