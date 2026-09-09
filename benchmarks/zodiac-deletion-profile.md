# Diagnostic profile of ZodiacEdge `#` rule deletion

This is **one instrumented observation**, separate from the benchmark replicates. It identifies where the frozen candidate spends time; it does not measure an optimization or predict a speedup.

The machine, CPython 3.12.9 runtime, official LUBM(1,0) input, 128 author rules, and frozen primary candidate match [the paired native comparison](zodiac-native-results.md). With `PYTHONHASHSEED=7300`, the diagnostic first materialized the 112 unmarked rules over 100,543 assertions, inserted the 16 `#` rules, and then profiled only `engine.update(remove_rules=marked_hash_rules)` using `cProfile`. Preparation, insertion, and full-state validation were outside the profile. All three typed-tuple closure checks passed: 214,429 tuples initially and finally, and 238,474 after insertion. The final state was complete and consistent.

[The compact JSON](zodiac-deletion-profile.json) records the complete frozen source hashes, profiler source hashes, raw profile hash, reference hash, method, and counters. The source snapshot is `tmp/zodiac-lubm/source-working-3cc7bae8d99debb5c6aa2cb9f71c4bc99e6e25947cd432566f902be42c201e89`. The original driver was an inline invocation; a separate driver file was not retained. The raw binary profile and expanded export remain in ignored `tmp/zodiac-native/profile-hash-delete.prof` and `.json`.

## Nonoverlapping costs

The instrumented update accumulated 2.130745 s of profiler time (2.131757 s elapsed). The following call groups include their descendants but do not include one another. Source lines refer to the frozen `src/dlp_reasoner/engine.py`, not the evolving working tree.

| Call group | Calls | Cumulative seconds | Frozen source |
|---|---:|---:|---|
| Canonicalize asserted facts for protection | 100,543 | 0.551646 | `_canonical`, line 448; caller `_dred`, line 870 |
| Check old and new DRed eligibility | 2 | 0.520192 | `_can_dred`, line 826; caller `update`, line 989 |
| Validate the proposed complete input | 1 | 0.295590 | `_validate`, line 211; caller `update`, line 989 |
| Recompute active-domain constants | 1 | 0.186231 | `_domain_constants`, line 495; caller `_dred`, line 870 |
| **Four groups combined** | | **1.553658 (72.9%)** | |
| All other update work, by subtraction | | 0.577087 | |

Do not add the enclosing `_dred` time or nested `normalize`, `_find`, and `_literal_key` times to this subtotal. The engine's internal `seconds` counter starts after validation and eligibility checks and therefore measures a narrower interval than the profiled public update.

The deletion evaluated 16 rules, visited 34,679 candidate rows, erased 24,045 indexed tuples, and rederived zero facts. The overdeleted set size is exactly the difference between the complete closures, 238,474 − 214,429. Therefore this case incurred no excess logical overdeletion. Repeated global preparation and protection passes are the largest observed costs within this candidate operation. Because the native engine was not profiled, these observations do not quantitatively decompose the separately measured 41.3× candidate/native ratio.

## Implications for future implementation

Maintaining auxiliary state incrementally is established practice in [incremental view maintenance](https://doi.org/10.1145/170035.170066) and [materialization maintenance](https://doi.org/10.1016/j.artint.2018.12.004). Rule-change reasoning also uses dependency analysis to limit reconsideration, including [Kotowski et al.](https://doi.org/10.1007/978-3-642-23580-1_11) and [ZodiacEdge](https://arxiv.org/abs/2312.14530). Applying those general principles to this engine's input checks and metadata is an engineering proposal, not an attribution of these exact shortcuts to those papers or a new maintenance algorithm.

Concrete candidates require separate proofs and measurements:

- DRed eligibility already guarantees identity representatives. Copying current assertions into the protection set could avoid canonicalizing every assertion again; explicit inequality symmetry and active-domain protection must remain correct.
- Eligibility certificates could avoid rescanning unchanged facts, but must account for datatype aliases, equality history, function terms, incomplete closures, and direct mutation of public containers.
- Predicate occurrence counts could retain valid arity certificates across deletion. Removing a predicate's last occurrence must release its arity before a later insertion with a different arity.
- Active-domain reference counts could avoid scanning unchanged assertions when rules change. Constants appearing only in removed rules, the nonempty-domain seed, and consequences of departed domain facts require explicit handling.

None of these proposals was implemented or measured in this diagnostic. Profiling overhead changes the relative cost of call-heavy paths; a single selected transaction cannot establish general workload behavior, an optimized runtime, or how much of the native gap could be removed.
