# Separate implementation of the bounded join-order follow-up

The frozen `benchmarks/external-tpch-results.json` study confirmed the motivating
Q5 intermediate-count expansion. This follow-up is explicitly post hoc; the
original design, inputs, drivers, source archive and results are preserved.

The implementation chooses Candidate B from `RESEARCH_JOIN_FOLLOWUP.md`.
It considers only the two smallest current buckets when the smaller has at
least 32 rows and the larger is at most four times its size. Each estimate
examines at most four physical rows, performs exact unification, and scores the
current bucket size times one plus the mean smallest next-step bucket size.
Invalid sampled rows contribute zero next-step work. Ties keep the greedy
choice. Every selected bucket is subsequently enumerated completely.

An invocation performs at most 1024 additional index lookups. Review identified
that repeated-variable failures can make samples spend no lookups, so the same
fixed limit also caps retained ordering hints at 1024. Together these bounds cap
sampled physical rows at 8192. Exhaustion uses the original greedy choice and
ignores existing hints. The hint key contains remaining atom occurrences, the
bound-variable mask, the two ordered candidate occurrences, and their bucket
size bit-lengths. Hints contain no answers or admissible values and are discarded
when the query ends. Bad estimates can hurt runtime but cannot reject bindings.

The scope is positive external headless queries over a completed materialization.
Installed rules, incomplete closures, equality/difference builtins and every
delta variant retain their prior evaluator. Ground constants are normalized on
each invocation. `_join_lookahead_enabled` stays False by default.

The three optimizations already assessed together by the earlier controlled
study now default to True: positional joins, incremental index maintenance and
monotone insertion validation/plan reuse. Explicit disabled subclasses preserve
the independent interpreter and validation ablations in tests. Adoption does
not imply that every workload benefits.

A separate lifecycle correction breaks the recursive local `visit` closure's
self-reference when either join evaluator is exhausted, explicitly closed or
terminated by an exception. This releases captured engines/indexes without
waiting for cyclic garbage collection. Tests disable cyclic GC and check weak
references after all three termination modes. The same correction is present
in both new compiled and lookahead arms, so their comparison isolates ordering.
It does not establish the cause of earlier encoding-time differences without
an additional GC probe.

The new `benchmarks/external_lookahead.py` runner uses one fresh process per
component: 54 TPC-H processes (three implementations, two scales, three queries,
three balanced blocks), plus 36 fresh-process adverse controls. Controls cover
near-unique joins, joins without useful reduction, skew and a pairwise-consistent
cycle with no global answer. All answers and full base closures have independent
oracles. Query timing includes planning, full result consumption and recursive
closure cleanup. Filter extraction, fact encoding and indexing are separately
recorded and included in component total. Outer process wall time includes
startup, input hashing, validation, serialization and teardown.

These are bounded interpreter heuristics motivated by RPT+/SYA's focus on
intermediate expansion and total overhead. They neither implement those
algorithms nor inherit their guarantees. Results, adverse cases and planning
counters must be reported together; the discovery dataset is not a held-out
generalization test.
