# ZodiacEdge LUBM(1) rule-maintenance reproduction

All 128 author rules; 100,543 ABox facts; original * (8 rules) and # (16 rules) transactions.
This measures the exact author Datalog program, not full OWL LUBM entailment.

| Configuration | Subset | Initial total (s) | Insert (s) | Delete (s) |
|---|---|---:|---:|---:|
| b1254c4 | * | 3.538229 | 0.333778 | 2.332182 |
| b1254c4 | # | 3.261465 | 0.492269 | 1.596192 |
| 5531be4 | * | 3.281087 | 0.334273 | 2.141756 |
| 5531be4 | # | 3.164557 | 0.493263 | 1.554094 |
| current-fixed | * | 2.900180 | 0.318160 | 1.966065 |
| current-fixed | # | 2.776441 | 0.440315 | 1.406106 |
| candidate | * | 2.780916 | 0.102022 | 1.357553 |
| candidate | # | 2.455075 | 0.245773 | 1.083834 |

Supplemental deterministic 1,000-assertion deletion/reinsertion transactions use the same full program. These follow the small-batch idea from materialization maintenance research; they are not ZodiacEdge's published rule transactions or a reproduction of Motik's original benchmark dataset.

| Configuration | Fact delete median (s) | Fact reinsert median (s) |
|---|---:|---:|
| b1254c4 | 2.372699 | 0.134950 |
| 5531be4 | 2.162658 | 0.120961 |
| current-fixed | 1.871949 | 0.114059 |
| candidate | 1.425814 | 0.039540 |

All complete tuple digests at every stage match a fresh naive materialization from frozen b1254c4. This reference shares the original engine semantics; it is not an independent OWL reasoner. Internal TOP facts are excluded from comparisons.
Each block uses fresh processes, identical hash seeds across configurations, and rotated order. Initial timing includes construction; RDF parsing, artifact parsing, hashing and validation are outside the timers. Insertion then deletion use the same already materialized instance, restoring the original partial program.
The author README reports 0.5889/0.2169/0.2525 seconds for * and 0.6037/0.0563/0.0215 seconds for # (initial/insert/delete). Its additional LUBM test does not specify hardware, seeds, repetitions or timer boundaries. These published values are context only; no cross-machine speedup is inferred.
The generated UBA1.7 index-0/seed-0 input matches the author's stated EDB count, but the author's original input hash and generator seed were not published.
The candidate combines positional join plans, delta index maintenance and reusable validation metadata for monotone fact/rule insertions. The primary track exercises rule insertion; supplemental transactions also exercise assertion reinsertion.

[Frozen author benchmark](https://raw.githubusercontent.com/xwq610728213/zodiac_edge/e15721161d1055f019c4b8f9ac1bd8648417f154/README.md)
