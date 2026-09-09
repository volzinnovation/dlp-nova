# Factorial reasoning experiments

Status: **passed**.

The fixed baseline b1254c4 remains unchanged. These comparisons isolate two mechanisms in one source tree; they are not historical commit replays or external state-of-the-art comparisons.

| Case | Contrast | Before ms | After ms | Paired median ratio | Interval |
|---|---|---:|---:|---:|---|
| {"family": "unary", "mode": "sparse-single", "size": 2048, "width": 8} | adaptive-only | 10.623 | 10.628 | 1.003 | [0.9768, 1.012] |
| {"family": "unary", "mode": "sparse-single", "size": 2048, "width": 8} | support-only | 10.623 | 10.732 | 1.011 | [0.9759, 1.05] |
| {"family": "unary", "mode": "sparse-single", "size": 2048, "width": 8} | combined | 10.623 | 10.699 | 1.025 | [0.9714, 1.052] |
| {"family": "unary", "mode": "sparse-single", "size": 2048, "width": 8} | adaptive-with-support | 10.732 | 10.699 | 0.9911 | [0.9627, 1.064] |
| {"family": "unary", "mode": "sparse-single", "size": 2048, "width": 8} | support-with-adaptive | 10.628 | 10.699 | 1.017 | [0.9674, 1.049] |
| {"family": "unary", "mode": "sparse-single", "size": 2048, "width": 64} | adaptive-only | 100.506 | 99.957 | 1.006 | [0.9624, 1.021] |
| {"family": "unary", "mode": "sparse-single", "size": 2048, "width": 64} | support-only | 100.506 | 100.551 | 1.004 | [0.963, 1.042] |
| {"family": "unary", "mode": "sparse-single", "size": 2048, "width": 64} | combined | 100.506 | 101.397 | 0.9961 | [0.9552, 1.01] |
| {"family": "unary", "mode": "sparse-single", "size": 2048, "width": 64} | adaptive-with-support | 100.551 | 101.397 | 0.9916 | [0.9738, 1.022] |
| {"family": "unary", "mode": "sparse-single", "size": 2048, "width": 64} | support-with-adaptive | 99.957 | 101.397 | 0.9912 | [0.977, 1.012] |
| {"family": "unary", "mode": "sparse-disjoint", "size": 2048, "width": 8} | adaptive-only | 10.502 | 10.782 | 0.9961 | [0.934, 1.041] |
| {"family": "unary", "mode": "sparse-disjoint", "size": 2048, "width": 8} | support-only | 10.502 | 10.705 | 1.021 | [0.9447, 1.066] |
| {"family": "unary", "mode": "sparse-disjoint", "size": 2048, "width": 8} | combined | 10.502 | 10.821 | 1.015 | [0.9542, 1.046] |
| {"family": "unary", "mode": "sparse-disjoint", "size": 2048, "width": 8} | adaptive-with-support | 10.705 | 10.821 | 1.01 | [0.9331, 1.024] |
| {"family": "unary", "mode": "sparse-disjoint", "size": 2048, "width": 8} | support-with-adaptive | 10.782 | 10.821 | 1.003 | [0.9825, 1.019] |
| {"family": "unary", "mode": "sparse-disjoint", "size": 2048, "width": 64} | adaptive-only | 103.556 | 103.567 | 0.9972 | [0.9734, 1.047] |
| {"family": "unary", "mode": "sparse-disjoint", "size": 2048, "width": 64} | support-only | 103.556 | 103.906 | 1.001 | [0.9774, 1.049] |
| {"family": "unary", "mode": "sparse-disjoint", "size": 2048, "width": 64} | combined | 103.556 | 105.056 | 1.014 | [0.9827, 1.064] |
| {"family": "unary", "mode": "sparse-disjoint", "size": 2048, "width": 64} | adaptive-with-support | 103.906 | 105.056 | 1.017 | [0.9804, 1.038] |
| {"family": "unary", "mode": "sparse-disjoint", "size": 2048, "width": 64} | support-with-adaptive | 103.567 | 105.056 | 1.018 | [0.9638, 1.031] |
| {"family": "unary", "mode": "sparse-overlap", "size": 32, "width": 8} | adaptive-only | 0.271 | 0.269 | 1.025 | [0.9672, 1.19] |
| {"family": "unary", "mode": "sparse-overlap", "size": 32, "width": 8} | support-only | 0.271 | 0.264 | 0.9674 | [0.9511, 1.106] |
| {"family": "unary", "mode": "sparse-overlap", "size": 32, "width": 8} | combined | 0.271 | 0.269 | 1.013 | [0.9794, 1.056] |
| {"family": "unary", "mode": "sparse-overlap", "size": 32, "width": 8} | adaptive-with-support | 0.264 | 0.269 | 1.017 | [0.9264, 1.065] |
| {"family": "unary", "mode": "sparse-overlap", "size": 32, "width": 8} | support-with-adaptive | 0.269 | 0.269 | 0.9931 | [0.8933, 1.031] |
| {"family": "unary", "mode": "sparse-overlap", "size": 32, "width": 64} | adaptive-only | 2.132 | 2.147 | 1.002 | [0.9945, 1.02] |
| {"family": "unary", "mode": "sparse-overlap", "size": 32, "width": 64} | support-only | 2.132 | 2.114 | 0.992 | [0.9716, 1.002] |
| {"family": "unary", "mode": "sparse-overlap", "size": 32, "width": 64} | combined | 2.132 | 2.145 | 1.005 | [0.9865, 1.021] |
| {"family": "unary", "mode": "sparse-overlap", "size": 32, "width": 64} | adaptive-with-support | 2.114 | 2.145 | 1.015 | [0.991, 1.037] |
| {"family": "unary", "mode": "sparse-overlap", "size": 32, "width": 64} | support-with-adaptive | 2.147 | 2.145 | 1.006 | [0.9776, 1.031] |
| {"family": "unary", "mode": "dense-overlap", "size": 2048, "width": 8} | adaptive-only | 53.179 | 53.651 | 1.002 | [0.9944, 1.033] |
| {"family": "unary", "mode": "dense-overlap", "size": 2048, "width": 8} | support-only | 53.179 | 53.838 | 1.002 | [0.9936, 1.032] |
| {"family": "unary", "mode": "dense-overlap", "size": 2048, "width": 8} | combined | 53.179 | 54.247 | 1.002 | [0.9894, 1.049] |
| {"family": "unary", "mode": "dense-overlap", "size": 2048, "width": 8} | adaptive-with-support | 53.838 | 54.247 | 1.008 | [0.9903, 1.027] |
| {"family": "unary", "mode": "dense-overlap", "size": 2048, "width": 8} | support-with-adaptive | 53.651 | 54.247 | 1.001 | [0.9703, 1.035] |
| {"family": "unary", "mode": "dense-overlap", "size": 2048, "width": 64} | adaptive-only | 688.126 | 697.530 | 1.013 | [0.9814, 1.03] |
| {"family": "unary", "mode": "dense-overlap", "size": 2048, "width": 64} | support-only | 688.126 | 707.545 | 1.013 | [0.9786, 1.091] |
| {"family": "unary", "mode": "dense-overlap", "size": 2048, "width": 64} | combined | 688.126 | 684.829 | 1.001 | [0.9749, 1.045] |
| {"family": "unary", "mode": "dense-overlap", "size": 2048, "width": 64} | adaptive-with-support | 707.545 | 684.829 | 0.985 | [0.9463, 1.02] |
| {"family": "unary", "mode": "dense-overlap", "size": 2048, "width": 64} | support-with-adaptive | 697.530 | 684.829 | 1.004 | [0.9702, 1.02] |
| {"family": "unary", "mode": "dense-selective", "size": 2048, "width": 8} | adaptive-only | 42.324 | 41.733 | 0.9903 | [0.9777, 1.019] |
| {"family": "unary", "mode": "dense-selective", "size": 2048, "width": 8} | support-only | 42.324 | 42.304 | 1.001 | [0.9725, 1.034] |
| {"family": "unary", "mode": "dense-selective", "size": 2048, "width": 8} | combined | 42.324 | 42.147 | 0.9972 | [0.9728, 1.015] |
| {"family": "unary", "mode": "dense-selective", "size": 2048, "width": 8} | adaptive-with-support | 42.304 | 42.147 | 0.9932 | [0.9703, 1.021] |
| {"family": "unary", "mode": "dense-selective", "size": 2048, "width": 8} | support-with-adaptive | 41.733 | 42.147 | 1.003 | [0.9742, 1.028] |
| {"family": "unary", "mode": "dense-selective", "size": 2048, "width": 64} | adaptive-only | 656.392 | 667.461 | 0.9818 | [0.9378, 1.102] |
| {"family": "unary", "mode": "dense-selective", "size": 2048, "width": 64} | support-only | 656.392 | 699.286 | 1.039 | [0.9495, 1.112] |
| {"family": "unary", "mode": "dense-selective", "size": 2048, "width": 64} | combined | 656.392 | 672.983 | 1.024 | [0.9341, 1.091] |
| {"family": "unary", "mode": "dense-selective", "size": 2048, "width": 64} | adaptive-with-support | 699.286 | 672.983 | 0.9776 | [0.954, 1.043] |
| {"family": "unary", "mode": "dense-selective", "size": 2048, "width": 64} | support-with-adaptive | 667.461 | 672.983 | 0.978 | [0.9552, 1.12] |
| {"depth": 4, "family": "support", "mode": "alternate-support", "size": 256} | adaptive-only | 12.159 | 12.203 | 1.001 | [0.985, 1.032] |
| {"depth": 4, "family": "support", "mode": "alternate-support", "size": 256} | support-only | 12.159 | 3.667 | 0.2977 | [0.2929, 0.3103] |
| {"depth": 4, "family": "support", "mode": "alternate-support", "size": 256} | combined | 12.159 | 3.709 | 0.303 | [0.2949, 0.3214] |
| {"depth": 4, "family": "support", "mode": "alternate-support", "size": 256} | adaptive-with-support | 3.667 | 3.709 | 1.021 | [1.007, 1.048] |
| {"depth": 4, "family": "support", "mode": "alternate-support", "size": 256} | support-with-adaptive | 12.203 | 3.709 | 0.3046 | [0.2965, 0.3114] |
| {"depth": 32, "family": "support", "mode": "alternate-support", "size": 256} | adaptive-only | 60.161 | 59.751 | 0.9884 | [0.9753, 1.015] |
| {"depth": 32, "family": "support", "mode": "alternate-support", "size": 256} | support-only | 60.161 | 8.121 | 0.1343 | [0.1322, 0.1387] |
| {"depth": 32, "family": "support", "mode": "alternate-support", "size": 256} | combined | 60.161 | 8.097 | 0.1345 | [0.1298, 0.137] |
| {"depth": 32, "family": "support", "mode": "alternate-support", "size": 256} | adaptive-with-support | 8.121 | 8.097 | 1.002 | [0.9796, 1.013] |
| {"depth": 32, "family": "support", "mode": "alternate-support", "size": 256} | support-with-adaptive | 59.751 | 8.097 | 0.1337 | [0.1323, 0.1383] |
| {"depth": 4, "family": "support", "mode": "unsupported-cycle", "size": 256} | adaptive-only | 5.133 | 5.107 | 0.9874 | [0.9778, 1.023] |
| {"depth": 4, "family": "support", "mode": "unsupported-cycle", "size": 256} | support-only | 5.133 | 6.045 | 1.19 | [1.178, 1.196] |
| {"depth": 4, "family": "support", "mode": "unsupported-cycle", "size": 256} | combined | 5.133 | 5.998 | 1.167 | [1.158, 1.212] |
| {"depth": 4, "family": "support", "mode": "unsupported-cycle", "size": 256} | adaptive-with-support | 6.045 | 5.998 | 1.002 | [0.9733, 1.025] |
| {"depth": 4, "family": "support", "mode": "unsupported-cycle", "size": 256} | support-with-adaptive | 5.107 | 5.998 | 1.182 | [1.173, 1.2] |
| {"depth": 32, "family": "support", "mode": "unsupported-cycle", "size": 256} | adaptive-only | 25.979 | 26.087 | 1.004 | [0.9885, 1.064] |
| {"depth": 32, "family": "support", "mode": "unsupported-cycle", "size": 256} | support-only | 25.979 | 30.277 | 1.186 | [1.146, 1.247] |
| {"depth": 32, "family": "support", "mode": "unsupported-cycle", "size": 256} | combined | 25.979 | 31.007 | 1.187 | [1.158, 1.239] |
| {"depth": 32, "family": "support", "mode": "unsupported-cycle", "size": 256} | adaptive-with-support | 30.277 | 31.007 | 1.01 | [0.9485, 1.041] |
| {"depth": 32, "family": "support", "mode": "unsupported-cycle", "size": 256} | support-with-adaptive | 26.087 | 31.007 | 1.17 | [1.142, 1.201] |
| {"depth": 4, "family": "support", "mode": "mixed-new-support", "size": 256} | adaptive-only | 12.807 | 12.607 | 0.9887 | [0.9782, 1.007] |
| {"depth": 4, "family": "support", "mode": "mixed-new-support", "size": 256} | support-only | 12.807 | 4.780 | 0.373 | [0.3704, 0.3932] |
| {"depth": 4, "family": "support", "mode": "mixed-new-support", "size": 256} | combined | 12.807 | 4.905 | 0.3835 | [0.3719, 0.391] |
| {"depth": 4, "family": "support", "mode": "mixed-new-support", "size": 256} | adaptive-with-support | 4.780 | 4.905 | 1.011 | [0.9794, 1.035] |
| {"depth": 4, "family": "support", "mode": "mixed-new-support", "size": 256} | support-with-adaptive | 12.607 | 4.905 | 0.3843 | [0.3714, 0.4022] |
| {"depth": 32, "family": "support", "mode": "mixed-new-support", "size": 256} | adaptive-only | 61.375 | 61.275 | 0.9894 | [0.9569, 1.026] |
| {"depth": 32, "family": "support", "mode": "mixed-new-support", "size": 256} | support-only | 61.375 | 9.110 | 0.1478 | [0.144, 0.1514] |
| {"depth": 32, "family": "support", "mode": "mixed-new-support", "size": 256} | combined | 61.375 | 8.907 | 0.1457 | [0.1426, 0.1533] |
| {"depth": 32, "family": "support", "mode": "mixed-new-support", "size": 256} | adaptive-with-support | 9.110 | 8.907 | 0.9999 | [0.9657, 1.037] |
| {"depth": 32, "family": "support", "mode": "mixed-new-support", "size": 256} | support-with-adaptive | 61.275 | 8.907 | 0.1468 | [0.1451, 0.1523] |
| {"depth": 4, "family": "support", "mode": "unique-signatures", "size": 256} | adaptive-only | 15.878 | 15.656 | 0.986 | [0.9726, 1.017] |
| {"depth": 4, "family": "support", "mode": "unique-signatures", "size": 256} | support-only | 15.878 | 14.255 | 0.9062 | [0.8821, 0.9287] |
| {"depth": 4, "family": "support", "mode": "unique-signatures", "size": 256} | combined | 15.878 | 14.560 | 0.9196 | [0.8978, 0.9254] |
| {"depth": 4, "family": "support", "mode": "unique-signatures", "size": 256} | adaptive-with-support | 14.255 | 14.560 | 1.002 | [0.9902, 1.032] |
| {"depth": 4, "family": "support", "mode": "unique-signatures", "size": 256} | support-with-adaptive | 15.656 | 14.560 | 0.9264 | [0.8986, 0.9432] |
| {"depth": 32, "family": "support", "mode": "unique-signatures", "size": 256} | adaptive-only | 65.929 | 66.572 | 1.006 | [0.9729, 1.015] |
| {"depth": 32, "family": "support", "mode": "unique-signatures", "size": 256} | support-only | 65.929 | 52.127 | 0.7907 | [0.7738, 0.8283] |
| {"depth": 32, "family": "support", "mode": "unique-signatures", "size": 256} | combined | 65.929 | 52.485 | 0.7837 | [0.7791, 0.8164] |
| {"depth": 32, "family": "support", "mode": "unique-signatures", "size": 256} | adaptive-with-support | 52.127 | 52.485 | 1 | [0.9867, 1.021] |
| {"depth": 32, "family": "support", "mode": "unique-signatures", "size": 256} | support-with-adaptive | 66.572 | 52.485 | 0.7894 | [0.7685, 0.8316] |

Ratios below one indicate shorter update times. All raw initial and update statistics, full outcome hashes, worker order, seed and source provenance are retained in JSON. Intervals describe these paired samples on one host. Candidate rows omit C-level set probes; do not interpret them as all CPU work.

Predeclared engineering screen:

```json
{
  "adaptive_geometric_mean_ratio": 1.0014460705958534,
  "adaptive_worst_case_ratio": 1.0246370792622899,
  "adaptive_threshold_met": false,
  "support_worst_overhead_ratio": 1.1896476417862125,
  "support_worst_benefit_case_ratio": 0.3842600679417518,
  "support_threshold_met": false,
  "interpretation": "Predeclared engineering screen on one host, not statistical significance or proof of external superiority. No dispatch changes are made by the experiment. All outcomes require interpretation."
}
```
