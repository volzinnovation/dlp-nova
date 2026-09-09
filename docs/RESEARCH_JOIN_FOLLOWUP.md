# Bounded follow-up on greedy join ordering

**Historical design note:** written during the frozen external benchmark series
on 9 September 2026, before either mechanism was implemented or evaluated.
The proposal below is retained as the design-stage record. Candidate B was
subsequently selected and implemented; its [separate implementation record](RESEARCH_JOIN_FOLLOWUP_IMPLEMENTATION.md)
and [new study](../benchmarks/external-lookahead-results.md) document the fixed
parameters, evidence and adverse controls. Candidate A remains unimplemented.
The motivating pilot mixed configurations and ran outside the quiet measurement
window; it cannot establish a performance claim.

The pilot's Q5 component visited 13,739 candidate rows at SF0.01 and 621,901 at
SF0.1, producing 103 and 865 answers respectively. This raises a specific
hypothesis: choosing the smallest immediate relation bucket can create a large
customer–supplier intermediate product before orders and lineitem reject it.
Matched final counters must confirm this pattern before it is treated as a
finding. Q3 and Q9 are mandatory controls, including negative results.

## Relation to prior work

Qiao, Boncz and Zhang's [RPT+](https://www.vldb.org/pvldb/vol19/p1278-qiao.pdf)
(PVLDB 19(6), 2026, doi:10.14778/3797919.3797934) addresses robustness and filtering
overhead through asymmetric transfer plans, cascade filters and dynamic
execution. Its important lesson here is that reducing intermediates is useful
only when filter construction and application costs are also controlled. The
current positional binding interpreter is not RPT+.

Semijoin reduction is classical, including
[Yannakakis's acyclic-query work](https://www.vldb.org/dblp/db/conf/vldb/Yannakakis81.html)
(VLDB 1981, pp.82–94). A directly relevant later implementation study is
Bekkers, Neven, Vansummeren and Wang,
[Instance-Optimal Acyclic Join Processing Without Regret](https://www.vldb.org/pvldb/vol18/p2413-vansummeren.pdf)
(PVLDB 18(8), 2025, doi:10.14778/3742728.3742737). Their Shredded Yannakakis
algorithm formalizes lookup and expansion through Nested Semijoin Algebra and
provides a cost guarantee for a specified class of acyclic plans. Those
guarantees do not transfer automatically to a Python implementation or cyclic
Q5. Any work here would be an adaptation and empirical contribution; algorithmic
novelty would remain unestablished.

## Candidate A: exact, budgeted predicate transfer

For one fixed positive conjunctive query, create separate temporary views for
its **atom occurrences**, even when two atoms use the same predicate. First
apply each atom's constants, repeated-variable constraints and initial bindings.
For occurrences i and j sharing variable tuple S, form the exact key set
K = projection(S, V_i) and retain in V_j only rows whose S-values belong to K.
Use the current index's column buckets when they avoid a full scan. Shared key
sets can be reused within the invocation; building the same projection twice
should not be charged invisibly to the baseline.

A first bounded prototype would perform one selective forward pass and one
backward pass on an explicitly recorded occurrence graph. It would skip empty
shared-variable sets, stop at a predeclared row/probe and temporary-memory
budget, and then run the ordinary complete join on the surviving views. At a
budget boundary it can either retain completed exact reductions or discard
all temporary views and use the original relations. Neither choice changes the
answer. It must not partially apply an unfinished key set: an incomplete key
set can delete legitimate rows.

**Preservation argument.** Let t be a complete answer binding before a transfer.
Its row in V_i contributes t[S] to K. Its row in V_j therefore survives. Every
complete answer survives each exact transfer, and induction covers any finite
sequence or any prefix stopped by the budget. Surviving rows still undergo the
original join, so transfers introduce no answers. On cyclic queries, pairwise
reductions need not remove every impossible row; nonempty reduced views are
not a proof that an answer exists.

The views must never overwrite `engine.facts`, asserted facts or persistent
indexes. A later query, equality merge or transaction can invalidate their
filtering context. The first prototype should use full-index queries on an
already completed materialization. A future semi-naive version must distinguish
atom occurrences and the selected delta relation: a filter derived for one
delta position cannot be reused for another variant or a later frontier.
Equality/inequality builtins and unsupported term patterns should keep their
existing evaluator until covered by a separate proof and tests. All matching
must use the engine's current normalized terms.

**Cost boundary.** Measure projection creation, bucket unions/intersections,
filter application, additional indexes and memory, not just subsequent joins.
Existing single-column buckets may make transfer cheap; large composite-key
sets or weakly selective scans may dominate. An initial cap can bound added
work, but no runtime or regret guarantee follows merely from such a cap.
Any activation threshold and budget must be recorded before the follow-up
measurements, rather than selected from the final Q5 timing.

## Candidate B: bounded lookahead without pruning

A smaller alternative changes only atom order. At a high-fanout choice, consider
the two smallest buckets when their sizes are within a fixed factor. Sample at
most a fixed number of rows from each, perform exact row unification, and
estimate the next step's bucket sizes after those bindings. Count these probes
explicitly and impose a per-invocation budget. A tentative score is the first
bucket size plus estimated next-step candidate volume. The Q5 hypothesis is
that binding lineitem's order key quickly exposes a selective orders lookup;
immediate customer-bucket size alone misses that effect.

A recorded heuristic choice may be reused for the same remaining-atom/binding
mask and similar bucket-size range. Such a cache stores an **ordering hint**, not
answers or admissible-value sets. Every selected atom must still enumerate all
its matching rows. An empty or unrepresentative sample cannot justify removing
rows or returning an empty answer. Budget exhaustion uses the existing greedy
choice. Sampling order, seeds, score, cache key and thresholds must be fixed in
the protocol. Learning a rule from TPC-H table or query names is excluded.

**Correctness boundary.** Reordering positive finite natural joins preserves all
bindings; the cost estimate need not be accurate for that fact to hold. Bounds
on sampling work do not bound the cost of a bad chosen order, so this proposal
has no worst-case-optimality or no-regret claim. Skew, correlated samples and
cache reuse can make it slower. It should initially share Candidate A's
full-index positive-query scope.

## Follow-up decision and evidence

If matched Q5 counters confirm excessive intermediates, select **one** candidate
for a new bounded study, with a new source snapshot and protocol. Exact predicate
transfer is closer to the identified robustness problem; lookahead offers a
smaller implementation with weaker performance guarantees. Neither should be
enabled by default from this pilot.

The follow-up should preserve all six existing TPC-H components and scales,
retain the prior source as a comparator, and include small independent join
oracles before timing. Add controls with no reduction, near-unique joins, skewed
keys, a nonempty pairwise-consistent cycle with no global answer, repeated
predicates, repeated variables, constants and exhausted budgets. Compare
complete answers and full base closures, including row identities that preserve
SQL multiplicity. If delta support is added, also compare every frontier variant
and final closure with ordinary evaluation.

Report matched candidate visits, filter/lookahead work, temporary peak memory,
join time **including planning/filtering**, and the existing cold component total
including preprocessing, fact encoding and index construction. Loading dominates
some of these Python cases: a large join-kernel gain may yield only a small total
benefit. Record regressions and activation/fallback rates. Keep discovery,
implementation pilots and final evaluation separate; do not replace the current
frozen measurements with the follow-up's more favorable rows. A local successful
adaptation would not establish superiority over RPT+, SYA or native SQL systems.
