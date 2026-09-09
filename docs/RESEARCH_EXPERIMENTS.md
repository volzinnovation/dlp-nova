# Certificate-guided maintenance and delta-sensitive joins

An implementation study of the DLP reasoner, 9 September 2026.

**Finding:** shared current-proof certificates make selected supported-cycle
updates up to 7.45× faster, but cost about 19% on unsupported cycles. Adaptive
unary planning is neutral on complete transactions. Both remain experimental
after failing the predeclared default-adoption screen. These are reproducible
local findings, not evidence of global state-of-the-art superiority.

## Research question and contribution status

Can a reasoner avoid expensive temporary delta unions and unnecessary deletion
work while retaining its existing finite Horn semantics, including simultaneous
changes to assertions and rules? This study develops two executable hypotheses,
derives their preservation conditions, and tests both favorable and adverse
workloads. It follows the [2004–2026 assessment](RESEARCH_IMPROVEMENTS.md), but
separates the application of known techniques from potential original research.

The historical baseline remains commit
`b1254c441731ca4fdf32ea83570ff99aaa84ac2a`. The preceding modernization was
committed and pushed as `8ce254fb011c2a2fa72345e66a25373c0885273a` before this
study. Its recorded results are retained. The four experimental configurations
below isolate two mechanisms in the subsequent source tree; their fixed-plan
configuration is not an exact historical checkout.

The candidate contribution is a bounded, transaction-local combination:
subjects with identical current assertion signatures share unary proof search,
and positively certified old facts stop DRed overdeletion even when their
replacement proofs use newly inserted rules or facts. It maintains no persistent
per-fact derivation counts. The accompanying adaptive evaluator chooses between
equivalent unary expressions using current delta and relation sizes. Both are
independently implemented and experimentally falsifiable. Publication novelty
and superiority over competitive external systems remain unestablished.

## Reconsidering the earlier observations

The earlier 87-fold union-workload improvement and 647-fold selected schema-query
improvement compared against an expensive local implementation. Those results
identify avoidable work in this repository. They do not measure the distance to
RDFox, Soufflé, ELK, or another contemporary frontier. Likewise, Python binding
visits omit work inside C-level set operations, so a large reduction in
`candidate_rows` cannot be called the same reduction in CPU operations.

The historical full-suite run also had apparent transitivity and maintenance
regressions. A subsequent alternating archived-source replay did not reproduce
the largest ones, although smaller costs remained. This motivates independent
process blocks, balanced configuration order, and raw sample retention here.
Neither sequential historical timings nor the earlier seven selected replay
cases support a workload-independent speed claim.

Two remaining mechanisms are worth investigating. First, the fixed unary plan
constructs the union of participating deltas before applying the full join. A
large delta union is unnecessary if a tiny full relation already limits all
answers. Second, ordinary DRed can remove an entire recursive region and then
restore it even when its facts have independent surviving support. Avoiding that
work requires a proof of current support, rather than trusting the old closure.

## Prior art and the remaining research space

This is a targeted primary-source review through 9 September 2026. Searches
covered adaptive set expressions, delta-query planning, support-aware Datalog
maintenance, shared type contexts, modular materialization, and rule updates.
It is not a systematic review of every paper in those fields.

| Component | Closest established work | What this study does and does not establish |
|---|---|---|
| Reordering union/intersection work | Bille, Pagh and Pagh, 2007 [^1] | A cheap selector for existing Python hash sets; not a new general set-expression algorithm or the paper's preprocessed word-parallel representation. |
| Efficient Datalog access paths | Subotić et al., 2018 [^2] | Unary/binary lookup specialization and direct exact probes; no implementation of Soufflé's index-cover algorithm. |
| Checking surviving support before deletion | Motik et al., B/F, 2015 [^3] | Positive unary certificates stop selected deletions; the broad idea of support-aware deletion is established. |
| Recursive/nonrecursive support accounting | Hu, Motik and Horrocks, 2018; Motik et al., 2019 [^4] [^5] | No persistent derivation counters, and no claim to implement DRedᶜ, B/Fᶜ, or FBF. |
| Sharing reasoning across recurring assertion profiles | Bajraktari, Ortiz and Šimkus, 2017 [^6] | Transaction-local unary Horn closure per exact seed signature; repeated profiles are not a newly discovered optimization opportunity. |
| Applying rules to shared representations | Hu et al., 2019 [^7] | Shared proof computation only; ordinary consequences and indexes remain explicit. |
| Specialized reasoning inside a general maintenance procedure | Hu, Motik and Horrocks, 2022 [^8] | A positive protection interface with a preservation argument, narrower than their modular framework. |
| Changing rule programs | Xu and Curé, ZodiacEdge, 2023 [^9] | Mixed positive fact/rule transactions with certificates; no negation or aggregate extension and no measured comparison with ZodiacEdge. |
| Current adaptive query maintenance | Abo-Khamis et al., May 2026 preprint [^10] | No improvement over their maintenance-width bounds; their arbitrary-join, single-tuple-update and enumeration contract differs from this full-materialization experiment. |
| Avoiding adaptive execution overhead | Qiao, Boncz and Zhang, PVLDB 2026 [^11] | Their dynamic filtering work reinforces the need for adverse cases; this implementation has none of RPT+'s Bloom-filter pipelines. |

ZodiacEdge organizes rule dependencies into strongly connected modules and
recomputes affected portions while incrementally updating successors. Its
introduction also states that the authors know of no previous incremental
rule-set solution. That historical statement needs qualification against this
repository's 2004 thesis, which already treats rule-change maintenance. This
observation concerns prior-art coverage; it does not invalidate ZodiacEdge's
technical contribution or make the corrected implementation equivalent to it.
The thesis's printed maintenance algorithm has an erratum; its earlier treatment
of the problem is not proof that every proposed historical procedure was correct.
[^9] [^12]

The literature therefore rules out broad claims such as “first adaptive unary
join,” “first support-aware deletion,” or “first incremental rule update.” The
specific combination and its measured tradeoffs are the research object. A
stronger novelty claim would require a detailed comparison with full B/F and
modular implementations, not merely a different name for a specialization.

## Hypothesis A: choose a unary expression from current cardinalities

For a recognized body `P1(x), …, Pk(x)`, let `Ii` be the current relation and
`Di` its current delta. Repeated predicates are deduplicated. Coalesced
semi-naive evaluation must return exactly

```text
J = (I1 ∩ … ∩ Ik) ∩ (D1 ∪ … ∪ Dk).
```

The implementation invariant is `Di ⊆ Ii`: the engine ingests each frontier
before evaluating it. Equality reindexing replaces the frontier with canonical
facts. During DRed, individual delta variants use the old store still present;
the coalesced shortcut is not imposed on arbitrary unrelated delta inputs.

The selector first rejects an empty required relation. If `x` is already bound,
it checks tuple membership directly and preserves other initial bindings. If
some nonempty delta has the same size as its full relation, the subset invariant
proves equality of those sets. Every full-body solution then satisfies the delta
condition, so the union and final delta filter are redundant. A single nonempty
delta is used directly without copying a union.

For the remaining case define `M = Σ|Di|`, `s = min|Ii|`, and let `h ≤ k` count
nonempty deltas. When `M ≤ k·s`, evaluation retains union-first processing. When
`M > k·s`, it computes `T = ⋂Ii` first and returns `⋃(T ∩ Di)`. Set
distributivity proves equivalence. The latter temporary sets contain at most
`s` tuples. Evaluation stops once the accumulated delta-filtered result covers
`T`. Selection uses actual current cardinalities, not stale compile-time
estimates or sampled selectivity.

### Work bound and its limits

Assume expected constant-time hashing/equality and ordinary hash-set operations.
The old plan must consume `M` union inputs and may allocate `|⋃Di|` tuples. The
full-first branch has expected work `O(k log k + k·s + h·s)` and temporary
space `O(s)`, excluding references to existing sets and emitted bindings.
This is a bound for one unary evaluation, not for a whole transaction.

A simple scan accounting gives at most `k·s` rows for copying/intersecting full
relations and at most `2h·s` for delta intersections plus inserting their outputs
into the result union. Therefore its scan bound is
`(k + 2h)·s ≤ 3k·s < 3M`, apart from selection/sorting. This is not a
three-competitive runtime theorem: Python overhead, allocation, hash collisions,
unequal operation constants and output processing remain outside that estimate.
The work counters also omit internal hash probes and some set-output updates.

An initial selector used `M ≥ s` to choose full-first. A development pilot
falsified it: 64 identical singleton deltas over 32-row full relations have a
one-row union, but force many full intersections under that rule. The observed
body-evaluator pilot was about 2.7 times slower. The width-aware threshold above
was adopted before the confirmatory matrix and that adversary was added to it.
Even the revised selector has bookkeeping costs on small updates; this was a
reason to test it, not to omit the workload. Exploratory kernel timings exclude
transaction preparation and are not the confirmatory performance evidence.
The pilot timing is a development observation; archived raw timing samples in
this study belong to the final confirmatory protocol.

The additional unary/binary `_Index.lookup` specialization avoids generic
argument-loop overhead for these common arities. It retains identity checks for
the private unbound sentinel and exact tuple semantics. It is shared by all four
factorial configurations, so their contrasts cannot attribute its effect.

## Hypothesis B: protect facts with current proof certificates

Let `P,E` be the old rules and explicit facts, and let `D` contain the generated
`TOP` facts for the old active domain, including the private nonempty-domain
representative. Write `M = lfp(P,E ∪ D)` for the complete old least model and
`M′ = lfp(P′,E′ ∪ D′)` for the corresponding new state. Ordinary DRed seeds deletion from removed
assertions, old instantiations of removed rules, and departed domain terms;
follows old dependencies; and restores consequences exclusively under `P′`.
Explicit current facts already act as protected deletion boundaries.

The new oracle supplies additional boundaries. It indexes only current rules of
the form `H(x) ← B1(x), …, Bm(x)`, with at least one premise and the same single
variable in every atom. Rules with constants, multiple variables, binary atoms,
existential terms, or constraint heads do not participate. For a queried subject
`a`, its seeds are the predicates of explicitly asserted unary facts in `E′`,
plus `TOP` only if `a` is in the current active domain.

Forward Horn closure of that predicate signature provides finite proofs. Equal
signatures share a closure, even across many subjects. The oracle never seeds
proof search from old derived facts, so a recursive cycle with no current entry
cannot certify itself. New rules and newly inserted assertions are valid proof
premises because the transaction is evaluated against its complete proposed
state. The oracle is discarded after the transaction.

Only old facts considered for deletion are protected. Other oracle conclusions
are not silently inserted into the store: normal new-rule evaluation, assertion
ingestion, and delta propagation must still produce and propagate them. This
distinction is essential when a replacement proof uses a new intermediate fact
or a newly inserted binary rule needs a retained unary premise.

### Preservation lemma

**Statement.** For finite positive function-free, equality-free programs with a
complete old materialization, DRed may additionally protect any queried old
facts `C ⊆ M′` while propagating losses through the old program, provided
restoration evaluates current definitions of deleted predicates, all inserted
rules, and propagates all new/restored facts to a fixed point.

**Soundness argument.** Every old fact has a finite derivation tree. If its proof
depends on a removed assertion, removed rule or departed domain seed, deletion is seeded there and
propagates along the old proof unless it encounters a protected fact. Cutting a
proof at such a fact is safe: substitute its finite current proof. Leaves that
are current explicit facts or valid current domain facts are safe by definition.
Following finite old trees avoids assuming that a recursive cycle proves itself.
Thus retained facts have current proofs; restoration under only current rules
adds only sound consequences.

**Completeness argument.** A deleted old consequence whose current premises all
survived is recovered by current rules defining a deleted predicate. If a premise
is instead inserted or restored, ordinary delta propagation triggers its uses.
Every inserted rule is evaluated once. An unchanged rule whose premises were
all in the complete old model could not produce a genuinely new head absent
from that model. Therefore no new unchanged-rule consequence is missed merely
because some old certified premises never reenter the delta. Fixed-point
restoration obtains all current consequences.

The unary oracle meets the lemma's premise by induction over its forward rule
firings: seeds are current facts, and each conclusion follows from a current
rule with already proved premises. A partially explored monotone closure is
still a sound subset. This is an implementation preservation argument, not a
machine-checked proof or a claim that the general protection principle is new.
Constraints are rechecked separately. Equality splitting, datatype identity
merges and existential witnesses retain the engine's rematerialization fallback.

### Budgets and adverse cases

The oracle defaults to at most 128 cached signatures and 100,000 dependency
visits per transaction. Exhaustion means unknown, so ordinary DRed continues.
These limits bound proof exploration and cache contexts, not total transaction
time or memory. Rule indexing scans current rule bodies; the lazy assertion
index scans current explicit facts; every attempted certificate has lookup and
signature-construction costs. Cache entries may contain many predicate names.
Candidate and dependency order can determine which signatures receive the
limited budget; recorded hash seeds expose that source of performance variation.
Only optimization opportunities change with the order, never the truth of a
positive certificate.

Repeated signatures with independent surviving support should amortize search.
Unsupported cycles should receive no positive certificate and expose pure
overhead. Unique signatures can exhaust the context budget. Binary-derived
support is deliberately incomplete in this oracle and must be recovered by
general DRed. A sound incomplete oracle can therefore be a poor performance
choice; correctness alone does not justify enabling it by default.

## Experimental design

The immutable [v3 protocol](../benchmarks/research-protocol-v3.json) was written
before the confirmatory matrix. Earlier v1/v2 proposals are retained to disclose
the increased population and added correlated-delta adversary. Development
pilots informed these choices; this is a preregistered local experiment after
exploration, not an independently timestamped public preregistration.

| Factor | Levels |
|---|---|
| Unary evaluator | Fixed union-first; adaptive |
| Deletion protection | Ordinary DRed; bounded current support certificates |
| Unary shapes | Sparse single delta; sparse disjoint deltas; sparse overlapping deltas; dense overlapping deltas; dense deltas with a selective full join |
| Unary width/population | Width 8 and 64; 2,048 subjects, except the overlapping-singleton adversary with 32 |
| Support shapes | Alternative survives; unsupported cycle; simultaneous replacement rule and new supporting assertions; unique seed signatures |
| Support depth/population | Depth parameter 4 and 32; 256 subjects; the generator creates predicates C0 through Cdepth plus an answer predicate |
| Repetition | Nine independent process blocks for every case and all four configurations |

There are 18 cases and 648 timed workers. Each block shares an explicit hash
seed across its four workers. Seeded Latin-square rotations balance position
over complete groups of four blocks; the ninth is necessarily not perfectly
balanced. Case order is fixed and recorded. A worker performs one cold initial
materialization and one atomic update. Input generation, outcome hashing, and
validation are outside the measured operations. No warm-up observations are
discarded. The research agents suspended their other timing work during the
matrix. Exclusive use of the whole machine was not established: a separately
rewritten Bach report bears a timestamp of 17:07:00Z, inside the experiment
window (16:55:19Z–17:08:25Z). Its origin and exact CPU overlap were not recorded.
This is a threat to timing attribution, even though measured source hashes and
all semantic checks remained valid. The original observations are retained;
a separate post-hoc replication of every support case checks the principal
conditional speedup and overhead finding.

The primary endpoint is outer wall time of the complete `Engine.update`,
including validation, rule planning, oracle preparation, deletion and restoration.
This is broader than the engine's internal statistics timer. Initial
materialization and engine counters are secondary. Every case records paired
ratios and descriptive paired-bootstrap intervals; nine blocks on one host
cannot establish population-wide significance. Case medians are not pooled as
if workloads were repeated measurements of the same quantity.

Each update must equal a fresh fixed-plan materialization as a full fact set.
Inputs, expected final assertions/rules, and complete actual initial/final
closures have canonical digests that must agree across configurations and blocks.
The original worker's assertion/rule digests describe the expected transaction
state; they do not independently hash the engine's internal assertion/rule state.
The randomized integration checks separately compare that internal state with
the independently maintained inputs. Nine small counterparts
under all four configurations add 36 checks against an independently written
exhaustive finite-grounding evaluator. That oracle covers the experimental
positive relational language, not arbitrary OWL equality or datatypes.

Seventy-two additional processes measure allocations with `tracemalloc`, one
per case/configuration. Those instrumented times never enter primary summaries.
The allocation interval begins after the old store is built and measures
additional Python allocations during update. It omits native allocation and
already retained store memory. Whole-process peak RSS includes the fresh
validation closure and is not an isolated engine-memory measurement.

Source and protocol hashes are checked after each worker. Machine/runtime
information, orders, seeds, all raw samples, statistics and digests are retained
in [research-results.json](../benchmarks/research-results.json). The acceptance
screen was fixed beforehand: adaptive unary execution needs a geometric mean
update ratio no greater than one and no case over 10% slower; certificates remain
experimental if adverse cases exceed 10% overhead or intended benefits are not
consistent. This is an engineering rule, not a significance test.

## Results and adoption

The matrix completed successfully: **648 timing workers, 72 separate memory
workers, and 36 small independent-oracle controls**. The offline artifact
validator verified initial and final completeness/consistency, every saved
configuration/order/seed, complete outcome hashes, the source archive, and
all recomputed summaries and adoption decisions. No observed correctness
failure was discarded. Measurements began at 2026-09-09T16:55:19Z, using
Python 3.12.9 and RDFLib 7.6.0 on the recorded macOS arm64 host.

Ratios below one favor the candidate. **The ratio is the median of the nine
within-block ratios**, not the ratio of the two separately reported medians;
these can differ and even fall on opposite sides of one. Intervals are the
predeclared descriptive paired-bootstrap intervals.

### Unary planning: a null end-to-end result

| Shape | Width | Fixed ms | Adaptive ms | Paired ratio | Descriptive interval |
|---|---:|---:|---:|---:|---|
| sparse-single | 8 | 10.623 | 10.628 | 1.0026 | [0.9768, 1.0123] |
| sparse-single | 64 | 100.506 | 99.957 | 1.0060 | [0.9624, 1.0209] |
| sparse-disjoint | 8 | 10.502 | 10.782 | 0.9961 | [0.9340, 1.0409] |
| sparse-disjoint | 64 | 103.556 | 103.567 | 0.9972 | [0.9734, 1.0473] |
| sparse-overlap | 8 | 0.271 | 0.269 | 1.0246 | [0.9672, 1.1895] |
| sparse-overlap | 64 | 2.132 | 2.147 | 1.0018 | [0.9945, 1.0201] |
| dense-overlap | 8 | 53.179 | 53.651 | 1.0019 | [0.9944, 1.0327] |
| dense-overlap | 64 | 688.126 | 697.530 | 1.0127 | [0.9814, 1.0303] |
| dense-selective | 8 | 42.324 | 41.733 | 0.9903 | [0.9777, 1.0194] |
| dense-selective | 64 | 656.392 | 667.461 | 0.9818 | [0.9378, 1.1023] |

The geometric mean of the ten paired case ratios is **1.001446**: 0.14% more
update time, with a worst case ratio of 1.024637. Every interval includes one.
This does not establish that adaptation is slower in general; it fails the
prespecified acceptance requirement to keep the geometric mean at or below one. The
candidate therefore remains experimental and the production default was
returned to fixed union-first execution. The failed threshold was not moved.

The mechanism did reduce its intended work. At width 64 in the dense-selective
case, delta-union input visits fell from **64,512 to zero**, while 32 delta-filter
input visits sufficed. Both variants emitted the same 32 body matches. Yet
additional traced peak allocation fell by only **56,106 bytes**, from 79,735,524
to 79,679,418 bytes. Large assertion batches and index/store updates dominate
the complete operation. The kernel improvement alone is not a persuasive
application-level win on this matrix.

For sparse-single updates, the median fraction outside the internal evaluator
timer was **99.46% at width 8 and 99.88% at width 64**. This descriptive diagnostic
is computed per worker as `1 − stats.seconds / update_seconds`, then summarized
by its median. It locates work outside the internal timer, chiefly candidate
state construction, validation and rule preparation; it does not time those
components individually. Incremental validation and reuse of unchanged rule
plans are better-supported next hypotheses for this workload than another
unary kernel refinement. Such changes were not implemented or tuned against
this confirmatory matrix.

### Support certificates: substantial conditional gains and a counterexample

| Shape | Depth | DRed ms | Certificates ms | Paired ratio | Descriptive interval | Overdeleted, before → after |
|---|---:|---:|---:|---:|---|---:|
| alternate-support | 4 | 12.159 | 3.667 | 0.2977 | [0.2929, 0.3103] | 1,536 → 0 |
| alternate-support | 32 | 60.161 | 8.121 | 0.1343 | [0.1322, 0.1387] | 8,704 → 0 |
| unsupported-cycle | 4 | 5.133 | 6.045 | 1.1896 | [1.1775, 1.1965] | 1,536 → 1,536 |
| unsupported-cycle | 32 | 25.979 | 30.277 | 1.1859 | [1.1463, 1.2470] | 8,704 → 8,704 |
| mixed-new-support | 4 | 12.807 | 4.780 | 0.3730 | [0.3704, 0.3932] | 1,536 → 0 |
| mixed-new-support | 32 | 61.375 | 9.110 | 0.1478 | [0.1440, 0.1514] | 8,704 → 0 |
| unique-signatures | 4 | 15.878 | 14.255 | 0.9062 | [0.8821, 0.9287] | 1,536 → 768 |
| unique-signatures | 32 | 65.929 | 52.127 | 0.7907 | [0.7738, 0.8283] | 8,704 → 4,352 |

With a surviving alternative at depth 32, the paired ratio is **0.13429**, or
**7.45× faster**. One shared context and 35 dependency visits certify the 256
entry facts; no deletion propagates through their 8,704 old consequences.
Python binding visits fall from 17,920 to 256. Additional traced peak allocation
falls from **6,418,467 to 3,029,976 bytes**, a 52.8% reduction during the update.
That is not a 52.8% reduction in total resident engine memory.

The simultaneous replacement-rule/new-assertion cases also benefit: paired
speedups are about **2.68× and 6.77×**. Thus protection is useful even when the
new proof was unavailable in the old program. Independent integration tests
add harder mixed cases with new intermediates and binary downstream rules.

The unsupported-cycle cases falsify uniform benefit. Their closures are deleted
correctly, but the proof filter adds **18.96% and 18.59%** paired overhead, both
over the predeclared 10% limit. Their descriptive intervals also lie above one.
The certificate feature therefore stays **off by default** despite its strong
supported-case gains. This decision follows the measured tradeoff, not a
correctness defect.

Unique signatures exercise the 128-context cap rather than being omitted.
Exactly half of the 256 entries receive certificates. At depth 32, 4,352 facts
are still overdeleted/rederived, the median proof-search count is 4,992 visits,
and 4,352 budget misses are recorded. The paired update ratio remains 0.79065.
At depth 4, additional traced peak memory increases from 2,492,123 to 2,551,440
bytes, illustrating that partial time savings need not save memory.

All four combinations are retained in the machine-generated report. Median
multiplicative interaction ratios range from **0.9550 to 1.0329** across the
18 cases. No strong general interaction claim follows from these small,
workload-specific deviations. The benefit of certificates is visible with
either unary plan; adaptation did not cure the unsupported-cycle overhead.

### Separate robustness replication

After the production suite finished, all eight support workloads were rerun
with **nine independent AB/BA pairs per case: 144 further workers**, using new
hash seeds 3000–3008 and fixed unary planning in both arms. Its protocol was
saved before its workers started, but the study is explicitly **post-hoc**,
prompted by the possible host-activity overlap described above. It neither
replaces the original data nor changes their adoption thresholds. Source,
driver, protocol and original-report hashes were checked throughout; initial
and final full closure hashes also matched the original factorial cases.

| Shape | Depth | Replicated paired ratio | Descriptive interval |
|---|---:|---:|---|
| alternate-support | 4 | 0.3031 | [0.2992, 0.3085] |
| alternate-support | 32 | 0.1323 | [0.1266, 0.1338] |
| unsupported-cycle | 4 | 1.1784 | [1.1364, 1.1947] |
| unsupported-cycle | 32 | 1.1879 | [1.1537, 1.2280] |
| mixed-new-support | 4 | 0.3819 | [0.3658, 0.3948] |
| mixed-new-support | 32 | 0.1495 | [0.1477, 0.1532] |
| unique-signatures | 4 | 0.9053 | [0.9000, 0.9170] |
| unique-signatures | 32 | 0.7849 | [0.7724, 0.8319] |

The supported depth-32 case again improves by about **7.6×**, while unsupported
cycles again cost about **18–19%** more. The conditional benefit and the reason
for leaving certificates off by default survive this replication. All 144
workers passed. The [replication report](../benchmarks/research-support-replay.md)
and [raw observations](../benchmarks/research-support-replay.json) retain all
pairs, counters and host load averages. This remains one-host evidence; load
averages do not prove that every external process was controlled.

Reproduce this additional check, after other timing work finishes, with:

```sh
.venv/bin/python scripts/replay_support_research.py \
  --output /tmp/dlp-support-reproduction.json
```

### Adoption and final production comparison

The production engine keeps the tested unary/binary lookup specialization,
fixed union-first planning, and ordinary DRed. Both research mechanisms remain
available through the explicit configurations in `benchmarks.research`; these
private research switches are not a new supported public API. The archived
experimental source retains its original candidate default, while the final
production source records the screen-driven default change. The four measured
configurations explicitly override defaults, so their semantics are unaffected.

The final production suite began at **2026-09-09T17:09:20Z**. All **54 cases ×
five repetitions (270 measured runs)** passed, including the three Bach cases.
All 51 historical cases matched the pinned `b1254c4` input and correctness
controls. The 14 recorded Python source hashes match the final source, and the
baseline SHA-256 remains unchanged. Full results and every phase comparison are
in [research-thesis-results.json](../benchmarks/research-thesis-results.json)
and its [generated report](../benchmarks/research-thesis-results.md).

| Phase | b1254c4 ms | Recorded 8ce254f ms | Final default ms | Final / b1254c4 |
|---|---:|---:|---:|---:|
| Union conjunction, 64 pairs | 10,406.030 | 119.371 | 105.388 | 0.0101 |
| Enumeration, 64 pairs | 95.863 | 6.059 | 5.717 | 0.0596 |
| Largest PF taxonomy: materialization | 4,860.310 | 4,388.391 | 4,777.663 | 0.9830 |
| Same taxonomy: subsumption | 7,983.876 | 12.339 | 12.843 | 0.0016 |
| Transitivity, 100 edges | 451.250 | 710.512 | 446.153 | 0.9887 |
| Cardinality, depth 5 / 3 individuals | 243.571 | 367.386 | 227.536 | 0.9342 |
| Maintenance depth 5 / 10%: rule insertion | 219.359 | 372.468 | 228.417 | 1.0413 |
| Maintenance depth 5 / 10%: rule replacement | 417.815 | 725.576 | 457.058 | 1.0939 |
| Maintenance depth 5 / 10%: rule deletion | 685.817 | 598.605 | 413.883 | 0.6035 |
| Maintenance depth 5 / 10%: mixed transaction | 771.007 | 709.321 | 791.637 | 1.0268 |

These historical ratios include the modernization already committed in
`8ce254f`; they do not attribute all gains to this research phase. The widest
union remains about **98.7×** faster than `b1254c4`, and the selected largest
schema query about **622×** faster. Independent process pairing in the new
factorial study isolates mechanisms; this separate full-suite table compares
recorded runs and remains sensitive to machine and process variation.

Regressions remain visible. The depth-7 / 9-individual P0 taxonomy materializes
**13.46% more slowly** than its historical baseline. The selected depth-5
maintenance rule insertion and replacement are **4.13% and 9.39% slower**,
respectively, while its rule deletion is faster. Neither the new lookup paths
nor the cumulative implementation is asserted to improve every operation.
An exact archived-8ce254f paired replay was not performed here, so changes
relative to that column cannot be attributed solely to lookup specialization.

## Validation and reproducibility

The final production configuration passes **593 tests**, Ruff, both thesis
errata/logic scripts, and package build. Semantic validation includes 1,458 exhaustive small relation/delta combinations,
all lookup patterns at arities zero through four, repeated predicates, initially
bound variables, equality reindexing, and mixed transactions. Certificate tests
cover unsupported cycles, conjunctions, current-domain removal, removed rules,
new proof intermediates, binary downstream consequences, constraints, budgets,
and bounded fallback. One integration test family checks 1,000 randomized atomic
states against both fresh materialization and independent exhaustive grounding.
Randomized tests and finite examples complement, rather than replace, the
preservation arguments above.

Validate the recorded artifacts and re-evaluate the current implementations
without overwriting the preserved observations:

```sh
uv sync --extra dev --locked
.venv/bin/python -m pytest -q
.venv/bin/python scripts/validate_research_artifacts.py
.venv/bin/python -m benchmarks.research --blocks 9 --memory --timeout 120 \
  --output /tmp/dlp-research-reproduction.json
.venv/bin/python -m benchmarks.run --suite thesis --repeats 5 \
  --output /tmp/dlp-thesis-reproduction.json
```

The existing protocol is a required input. Do not overwrite it to accommodate a
different experiment: use a new version/path and retain the earlier evidence.
The original baseline directory and preceding full-suite/replay results are
protected. The thesis-suite command still compares against pinned `b1254c4`.
The exact measured Python sources and v3 protocol are also preserved in
[research-source.tar.gz](../benchmarks/research-source.tar.gz), with a
[SHA-256 manifest](../benchmarks/research-source.json). Overlay this archive only
onto a separate Git checkout of `8ce254f` when reproducing the original experiment;
this recovers its source bytes even if the final adoption policy or validation
guards are changed later. The four configuration switches are explicit, so
they do not inherit the production default. Set up the locked environment and
run the factorial command from that separate checkout for exact source replay.
The commands above run the current source and record its own hashes; the offline
verifier checks the preserved original report against its original archive.

## Limits and next falsifiable steps

The matrix is intentionally synthetic and emphasizes the mechanisms being
developed. It is not a representative sample of deployed ontologies. The small
Bach and generated thesis workloads add regression coverage but cannot supply
industrial generality. A single Apple M4 Max host and one Python version do not
establish cross-platform behavior. Formula-level work savings can disappear
inside validation, assertion ingestion, allocation, and explicit output costs.

No equivalent native external maintenance baseline was executed. Soufflé and
RDFox were absent from the environment. Existing `owlrl` is useful for overlap
in supported entailments but does not provide the arbitrary Horn mixed-rule
transaction interface used here. A competitive study needs pinned engine
versions, matched semantics and update contracts, independently chosen datasets,
compilation costs separated from execution, and full answer verification.

The strongest next experiment would compare these certificates with DRedᶜ/B/Fᶜ
and modular maintenance on the same changing programs, including the memory
cost of persistent counts. A second would determine whether signature reuse and
deletion fan-out can predict benefit cheaply enough to justify automatic
dispatch. Such a predictor must be tested on held-out workloads; choosing it
after seeing this matrix would require a new confirmatory experiment. Compressed
relations and heavy-light query plans are broader research directions with
different storage and output contracts, not optimizations this study has already
implemented.

## Sources

[^1]: Philip Bille, Anna Pagh and Rasmus Pagh. *Fast Evaluation of Union-Intersection Expressions*. ISAAC 2007, pp. 739–750. [Author preprint](https://arxiv.org/abs/0708.3259).
[^2]: Pavle Subotić et al. *Automatic Index Selection for Large-Scale Datalog Computation*. PVLDB 12(2), 2018, pp. 141–153. [Paper](https://www.vldb.org/pvldb/vol12/p141-subotic.pdf).
[^3]: Boris Motik, Yavor Nenov, Robert Piro and Ian Horrocks. *Incremental Update of Datalog Materialisation: the Backward/Forward Algorithm*. AAAI 2015. [Publisher](https://ojs.aaai.org/index.php/AAAI/article/view/9409).
[^4]: Pan Hu, Boris Motik and Ian Horrocks. *Optimised Maintenance of Datalog Materialisations*. AAAI 2018. [Publisher](https://ojs.aaai.org/index.php/AAAI/article/view/11554).
[^5]: Boris Motik, Yavor Nenov, Robert Piro and Ian Horrocks. *Maintenance of Datalog Materialisations Revisited*. Artificial Intelligence 269, 2019, pp. 76–136. [DOI](https://doi.org/10.1016/j.artint.2018.12.004).
[^6]: Labinot Bajraktari, Magdalena Ortiz and Mantas Šimkus. *Goal-oriented Type-based Reasoning for Expressive DLs*. DL 2017 extended abstract. [Paper](https://ceur-ws.org/Vol-1879/paper63.pdf).
[^7]: Pan Hu, Jacopo Urbani, Boris Motik and Ian Horrocks. *Datalog Reasoning over Compressed RDF Knowledge Bases*. CIKM 2019. [Author preprint](https://arxiv.org/abs/1908.10177).
[^8]: Pan Hu, Boris Motik and Ian Horrocks. *Modular Materialisation of Datalog Programs*. Artificial Intelligence 308, 2022, article 103726. [Author manuscript](https://www.cs.ox.ac.uk/people/boris.motik/pubs/hmh22modular-materialisation.pdf).
[^9]: Weiqin Xu and Olivier Curé. *ZodiacEdge: a Datalog Engine With Incremental Rule Set Maintenance*. Preprint, 22 December 2023, especially §§1 and 4.4. [Full text](https://arxiv.org/html/2312.14530v1).
[^10]: Mahmoud Abo-Khamis, Eden Chmielewski, Andrei Draghici, Ahmet Kara and Dan Olteanu. *Maintaining Queries under Updates Using Heavy-Light Partitioning of the Input Relations*. Preprint, 8 May 2026. [Record and paper](https://arxiv.org/abs/2605.08397).
[^11]: Yiming Qiao, Peter Boncz and Huanchen Zhang. *Robust Predicate Transfer with Dynamic Execution*. PVLDB 19(6), 2026, pp. 1278–1290. [Author manuscript](https://people.iiis.tsinghua.edu.cn/~huanchen/publications/rpt%2B-vldb26.pdf), [project publication page](https://duckdb.org/library/robust-predicate-transfer-vldb/).
[^12]: Raphael Volz. *Web Ontology Reasoning with Logic Databases*. PhD thesis, 2004. [Repository PDF](Volltext.pdf); consult the [errata](THESIS_ERRATA.md) for the implemented corrections and their scope.
