# Fixed baseline: b1254c4

The user selected commit `b1254c441731ca4fdf32ea83570ff99aaa84ac2a` as the
performance baseline going forward. `results.json` and `results.md` are exact
copies of the corresponding files in that commit. Preserve them unchanged.

The manifest records the full commit, SHA-256 digests, 51 cases, five repetitions,
timing protocol, and the source hashes stored in the original report. Those
source hashes were checked against the pinned commit's blobs. The copied report
contains its original comparison against an older baseline; that nested
comparison is historical, not the reference selection for new runs.

New measurements go to `benchmarks/results.json` or another path outside this
directory. The benchmark runner verifies this reference and uses it by default.
Future improvements do not silently promote their own results to a new baseline.
