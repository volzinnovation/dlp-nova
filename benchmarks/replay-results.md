# Supplemental paired replay of b1254c4

Status: **passed**. Reference commit: `b1254c441731ca4fdf32ea83570ff99aaa84ac2a`.

These are new measurements of the archived baseline and current implementation, not replacements for the pinned historical report. Each pair launches two independent workers with one repetition and the same explicit hash seed, alternating AB/BA order. Five pairs give limited evidence about remaining timing noise; intervals are descriptive paired resampling intervals, not guaranteed confidence coverage.

Current checkout: `b1254c441731ca4fdf32ea83570ff99aaa84ac2a`; dirty: True. Full source hashes, input hashes, worker outputs, assertions and execution orders are retained in JSON.

| Case | Phase | Baseline median ms | Current median ms | Current / baseline | Paired interval |
|---|---|---:|---:|---:|---:|
| {"kind": "transitive", "size": 100} | parse_seconds | 1.651 | 1.618 | 0.9803 | [0.7847, 1.002] |
| {"kind": "transitive", "size": 100} | compile_seconds | 1.302 | 1.317 | 1.011 | [0.9608, 1.026] |
| {"kind": "transitive", "size": 100} | materialize_seconds | 431.559 | 439.196 | 1.018 | [1.005, 1.024] |
| {"kind": "transitive", "size": 100} | query_seconds | 11.605 | 12.068 | 1.04 | [1.008, 1.07] |
| {"depth": 5, "ipc": 3, "kind": "cardinality"} | parse_seconds | 55.512 | 55.720 | 1.004 | [0.9847, 1.024] |
| {"depth": 5, "ipc": 3, "kind": "cardinality"} | compile_seconds | 72.179 | 72.080 | 0.9986 | [0.9567, 1.013] |
| {"depth": 5, "ipc": 3, "kind": "cardinality"} | materialize_seconds | 219.843 | 229.828 | 1.045 | [1.036, 1.059] |
| {"depth": 5, "ipc": 3, "kind": "cardinality"} | query_seconds | 6.803 | 6.574 | 0.9664 | [0.9517, 1.026] |
| {"kind": "existential", "size": 100} | parse_seconds | 1.733 | 1.745 | 1.007 | [0.9773, 1.015] |
| {"kind": "existential", "size": 100} | compile_seconds | 1.400 | 1.354 | 0.9672 | [0.9363, 0.9781] |
| {"kind": "existential", "size": 100} | materialize_seconds | 65.344 | 64.770 | 0.9912 | [0.9605, 0.9978] |
| {"kind": "existential", "size": 100} | query_seconds | 6.346 | 6.353 | 1.001 | [0.9689, 1.066] |
| {"kind": "factored-unions", "pairs": 64, "size": 128} | parse_seconds | 81.697 | 82.065 | 1.005 | [0.9987, 1.031] |
| {"kind": "factored-unions", "pairs": 64, "size": 128} | compile_seconds | 84.195 | 82.326 | 0.9778 | [0.9602, 1.006] |
| {"kind": "factored-unions", "pairs": 64, "size": 128} | materialize_seconds | 10046.223 | 91.846 | 0.009142 | [0.008635, 0.009643] |
| {"kind": "factored-unions", "pairs": 64, "size": 128} | query_seconds | 2.293 | 1.812 | 0.7902 | [0.7896, 0.8151] |
| {"depth": 5, "ipc": 9, "kind": "taxonomy", "variant": "PF"} | parse_seconds | 70.677 | 71.267 | 1.008 | [0.9891, 1.012] |
| {"depth": 5, "ipc": 9, "kind": "taxonomy", "variant": "PF"} | compile_seconds | 88.506 | 88.464 | 0.9995 | [0.9785, 1.041] |
| {"depth": 5, "ipc": 9, "kind": "taxonomy", "variant": "PF"} | materialize_seconds | 152.202 | 149.394 | 0.9815 | [0.9714, 1.001] |
| {"depth": 5, "ipc": 9, "kind": "taxonomy", "variant": "PF"} | query_seconds | 8.110 | 8.143 | 1.004 | [0.947, 1.138] |
| {"depth": 5, "ipc": 9, "kind": "taxonomy", "variant": "PF"} | property_query_seconds | 3.182 | 3.164 | 0.9945 | [0.9033, 1.124] |
| {"depth": 5, "ipc": 9, "kind": "taxonomy", "variant": "PF"} | subsumption_seconds | 365.093 | 0.782 | 0.002142 | [0.002107, 0.002325] |
| {"change_percent": 10, "depth": 3, "kind": "maintenance"} | parse_seconds | 10.349 | 10.232 | 0.9887 | [0.9631, 1.007] |
| {"change_percent": 10, "depth": 3, "kind": "maintenance"} | compile_seconds | 10.358 | 10.523 | 1.016 | [0.9858, 1.032] |
| {"change_percent": 10, "depth": 3, "kind": "maintenance"} | materialize_seconds | 22.167 | 20.489 | 0.9243 | [0.7119, 0.9598] |
| {"change_percent": 10, "depth": 3, "kind": "maintenance"} | query_seconds | 1.313 | 1.282 | 0.976 | [0.5943, 1.029] |
| {"change_percent": 10, "depth": 3, "kind": "maintenance"} | maintenance.fact_delete.update | 18.575 | 17.678 | 0.9517 | [0.3644, 0.9693] |
| {"change_percent": 10, "depth": 3, "kind": "maintenance"} | maintenance.fact_delete.rebuild | 19.266 | 18.780 | 0.9747 | [0.3747, 0.9793] |
| {"change_percent": 10, "depth": 3, "kind": "maintenance"} | maintenance.fact_insert.update | 3.657 | 3.305 | 0.9038 | [0.6109, 0.9306] |
| {"change_percent": 10, "depth": 3, "kind": "maintenance"} | maintenance.fact_insert.rebuild | 20.864 | 20.652 | 0.9898 | [0.6178, 0.9898] |
| {"change_percent": 10, "depth": 3, "kind": "maintenance"} | maintenance.rule_insert.update | 7.554 | 7.062 | 0.9349 | [0.6321, 0.9433] |
| {"change_percent": 10, "depth": 3, "kind": "maintenance"} | maintenance.rule_insert.rebuild | 24.845 | 23.866 | 0.9606 | [0.8019, 0.9787] |
| {"change_percent": 10, "depth": 3, "kind": "maintenance"} | maintenance.rule_delete.update | 9.943 | 9.427 | 0.9482 | [0.9179, 0.9838] |
| {"change_percent": 10, "depth": 3, "kind": "maintenance"} | maintenance.rule_delete.rebuild | 31.934 | 29.385 | 0.9202 | [0.9047, 0.9485] |
| {"change_percent": 10, "depth": 3, "kind": "maintenance"} | maintenance.rule_replace.update | 11.507 | 10.539 | 0.9159 | [0.9012, 0.9335] |
| {"change_percent": 10, "depth": 3, "kind": "maintenance"} | maintenance.rule_replace.rebuild | 23.546 | 22.765 | 0.9668 | [0.9326, 1.015] |
| {"change_percent": 10, "depth": 3, "kind": "maintenance"} | maintenance.atomic_mixed.update | 12.645 | 12.268 | 0.9702 | [0.947, 1.01] |
| {"change_percent": 10, "depth": 3, "kind": "maintenance"} | maintenance.atomic_mixed.rebuild | 31.224 | 20.510 | 0.6569 | [0.624, 0.6708] |
| {"change_percent": 10, "depth": 5, "kind": "maintenance"} | parse_seconds | 292.659 | 296.361 | 1.013 | [0.9477, 1.039] |
| {"change_percent": 10, "depth": 5, "kind": "maintenance"} | compile_seconds | 302.219 | 305.326 | 1.01 | [0.9997, 1.026] |
| {"change_percent": 10, "depth": 5, "kind": "maintenance"} | materialize_seconds | 1111.781 | 1065.418 | 0.9583 | [0.9514, 1.088] |
| {"change_percent": 10, "depth": 5, "kind": "maintenance"} | query_seconds | 51.027 | 50.962 | 0.9987 | [0.9887, 1.025] |
| {"change_percent": 10, "depth": 5, "kind": "maintenance"} | maintenance.fact_delete.update | 618.040 | 586.145 | 0.9484 | [0.9304, 0.9737] |
| {"change_percent": 10, "depth": 5, "kind": "maintenance"} | maintenance.fact_delete.rebuild | 1030.092 | 971.629 | 0.9432 | [0.9363, 0.9691] |
| {"change_percent": 10, "depth": 5, "kind": "maintenance"} | maintenance.fact_insert.update | 277.479 | 253.950 | 0.9152 | [0.8943, 0.9211] |
| {"change_percent": 10, "depth": 5, "kind": "maintenance"} | maintenance.fact_insert.rebuild | 1225.557 | 1157.549 | 0.9445 | [0.9107, 0.9524] |
| {"change_percent": 10, "depth": 5, "kind": "maintenance"} | maintenance.rule_insert.update | 211.294 | 206.136 | 0.9756 | [0.9563, 0.9981] |
| {"change_percent": 10, "depth": 5, "kind": "maintenance"} | maintenance.rule_insert.rebuild | 1357.318 | 1264.896 | 0.9319 | [0.9216, 0.9421] |
| {"change_percent": 10, "depth": 5, "kind": "maintenance"} | maintenance.rule_delete.update | 592.601 | 568.177 | 0.9588 | [0.9165, 0.9676] |
| {"change_percent": 10, "depth": 5, "kind": "maintenance"} | maintenance.rule_delete.rebuild | 1357.303 | 1287.243 | 0.9484 | [0.9278, 0.9571] |
| {"change_percent": 10, "depth": 5, "kind": "maintenance"} | maintenance.rule_replace.update | 392.590 | 388.564 | 0.9897 | [0.9619, 1.085] |
| {"change_percent": 10, "depth": 5, "kind": "maintenance"} | maintenance.rule_replace.rebuild | 1342.914 | 1258.375 | 0.937 | [0.9243, 0.9524] |
| {"change_percent": 10, "depth": 5, "kind": "maintenance"} | maintenance.atomic_mixed.update | 673.806 | 637.314 | 0.9458 | [0.9263, 0.9632] |
| {"change_percent": 10, "depth": 5, "kind": "maintenance"} | maintenance.atomic_mixed.rebuild | 1242.979 | 1177.858 | 0.9476 | [0.9267, 0.9699] |

Work counters remain in each raw worker output. Candidate rows measure Python binding visits, excluding C-level set-intersection probes. Whole worker wall time includes startup/generation/validation and is separate from the phase timings above.
