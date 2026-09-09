# Supplemental support-certificate replication

Status: **passed**.

This post-hoc robustness check was prompted by a Bach benchmark artifact changing during the original factorial run. The origin and extent of possible concurrent host activity were not established. This replication does not replace the original measurements, alter their adoption thresholds, or change the b1254c4 baseline.

Each workload uses nine independently launched process pairs, alternating AB/BA order with the same explicit hash seed within each pair. Both versions use the fixed unary plan; only support certificates differ. Memory instrumentation is off.

| Case | DRed median ms | Support median ms | Paired median ratio | Interval |
|---|---:|---:|---:|---|
| {"depth": 4, "family": "support", "mode": "alternate-support", "size": 256} | 12.063 | 3.671 | 0.3031 | [0.2992, 0.3085] |
| {"depth": 32, "family": "support", "mode": "alternate-support", "size": 256} | 60.268 | 7.920 | 0.1323 | [0.1266, 0.1338] |
| {"depth": 4, "family": "support", "mode": "unsupported-cycle", "size": 256} | 5.003 | 5.921 | 1.178 | [1.136, 1.195] |
| {"depth": 32, "family": "support", "mode": "unsupported-cycle", "size": 256} | 26.783 | 32.114 | 1.188 | [1.154, 1.228] |
| {"depth": 4, "family": "support", "mode": "mixed-new-support", "size": 256} | 13.102 | 4.887 | 0.3819 | [0.3658, 0.3948] |
| {"depth": 32, "family": "support", "mode": "mixed-new-support", "size": 256} | 62.186 | 9.233 | 0.1495 | [0.1477, 0.1532] |
| {"depth": 4, "family": "support", "mode": "unique-signatures", "size": 256} | 16.025 | 14.457 | 0.9053 | [0.9, 0.917] |
| {"depth": 32, "family": "support", "mode": "unique-signatures", "size": 256} | 64.636 | 50.797 | 0.7849 | [0.7724, 0.8319] |

Ratios below one favor support certificates. Intervals are descriptive paired resampling intervals from one host. All observations, process orders, seeds, work counters and source/driver/protocol digests are retained in JSON. The full actual initial/final closure hashes must match both the pair and original factorial case. The assertion/rule hashes identify the expected transaction state. Each worker also checks its actual updated closure against fresh fixed-plan recomputation.
