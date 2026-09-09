# Finite L3 existential-bridge task comparison

Original controlled workload; consistency and exact named C/D instances on identical ontologies.
No witness-store equivalence or corpus-prevalence claim is made.

| N | Configuration | Task median (s) | Process median (s) |
|---:|---|---:|---:|
| 100 | b1254c4 | 0.010029 | 0.101472 |
| 100 | candidate | 0.009945 | 0.099147 |
| 100 | hermit | 0.220450 | 0.272145 |
| 1000 | b1254c4 | 0.086836 | 0.188231 |
| 1000 | candidate | 0.083865 | 0.178843 |
| 1000 | hermit | 0.318659 | 0.372038 |
| 10000 | b1254c4 | 1.016922 | 1.135562 |
| 10000 | candidate | 0.937498 | 1.055745 |
| 10000 | hermit | 2.475294 | 2.532972 |

HermiT is the OWLAPI-maintained 1.4.5.519 fork (OWLAPI 5.1.9), not a claim about the latest upstream full OWL reasoner. Phase timings accommodate eager DLP materialization and HermiT's normal lazy classification/realization; use the summed task time for the matched operation. Full process time additionally includes runtime startup, answer serialization and process exit. The fixed TBox implies A⊑C, so explicit witness construction is not necessary to answer this query. Both existential axioms are essential to that entailment; no axiom is removed or rewritten by the adapter.
