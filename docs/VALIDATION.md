# Validation methodology

The checks implement the semantic obligations in [THESIS_SPEC.md](THESIS_SPEC.md) and deliberately use several different reference methods. Passing these tests is evidence for the exercised fragment and cases, not a proof of conformance to all OWL or all possible DLP ontologies.

Run the independent suite with:

```sh
.venv/bin/python -m pytest -q tests/test_semantic_validation.py
```

The development dependency set contains `pytest` and `owlrl`. The oracle import is mandatory: a missing external oracle causes collection to fail rather than silently reducing coverage.

## External reasoner comparison

Seven hand-built ontologies and eight seeded generated ontologies are independently expanded by RDFLib's `owlrl.OWLRL_Semantics`. Each input is also evaluated by this reasoner. The tests compare 100 named ground queries per ontology: 20 class memberships, 64 property assertions, and 16 individual equalities.

The shared cases cover taxonomy, property inclusion/equivalence/inverse/transitivity/symmetry, domain/range, class intersection, antecedent union and existential, consequent universal and has-value, antecedent nominals, explicit equality, functionality and inverse functionality. Queries include both entailed and non-entailed assertions.

Only named application-vocabulary assertions are compared. OWL RL's extra schema, built-in vocabulary, blank-node and axiomatic triples are outside this comparison. The test does not use OWL RL as an oracle for L3 witness generation, datatype semantics, arbitrary negation, singleton-nominal consequents, or unrestricted OWL consistency. In particular, the OWL RL rules do not derive equality from `A ⊑ {c}` and `A(a)`, whereas DLP does. That case has a separate direct first-order expectation test and is deliberately excluded from the differential oracle. Both engines receive the same input RDF graph, and the external reference expands a separate graph copy.

## Exhaustive finite interpretation oracle

Thirty-two deterministic inputs use three named unary predicates and two named individuals, with subclass inclusions, intersections in antecedents, disjointness, and positive ABox assertions. For each input the test enumerates all 64 interpretations of those predicates over the two-element domain, applying the source constraints directly without compiling rules or computing a closure.

An input is consistent exactly when a satisfying interpretation exists. A ground membership is entailed exactly when it holds in every satisfying interpretation. Inconsistent inputs are checked for explicit refusal of ordinary queries, matching the public operational policy.

This domain bound is sufficient for the tested language because it has only universally quantified monadic constraints and ground positive assertions: no relation, equality, nominal, existential or counting axiom requires extra domain elements or identifies names. Every interpretation of the named individuals' unary memberships is represented, including identical memberships for the two names. This argument does not extend to the richer language without additional work.

## Direct relation oracle and incremental updates

Six seeds each create a six-individual property graph. A small independent relation-algebra evaluator directly applies subproperty inclusion, inverse, symmetry and transitive closure. All ground property queries are checked against this reference after initial materialization and after each of twelve updates. The update sequence includes both fact changes and removal/reintroduction of the transitivity axiom.

At each of these 78 states, the current materialized fact set is also compared with fresh compilation and reasoning from the authoritative RDF assertions. The relation oracle addresses shared implementation mistakes between incremental and fresh evaluation; the fresh-recomputation comparison addresses incomplete update propagation.

Dedicated update regressions cover a cycle losing its final external support, multiple independent derivations, a fact with both explicit and inferred support, and equality retraction splitting previously propagated aliases.

## Thesis-specific regressions

Additional checks cover independent variable scopes in nested restrictions, constraint violations appearing only after equality/subclass inference, the nonempty domain with an empty ABox, query probes preserving the live state, normalization before profile selection, and rejection of a non-Horn positive union consequent. Final API regressions check universal consequences for fresh query names, fresh-name equality in a singleton domain, reuse of returned existential witnesses in queries, structured CLI errors for invalid Turtle, and resource-limit reporting for temporary query-domain extensions.

The rest of the repository's tests cover parser errors, API/CLI behavior, expression queries, serialization and L3 witness visibility/resource limits. Benchmark correctness checks and measured timings are reported separately; the semantic tests are not performance tests.

## Results

Validated on 2026-09-09 with Python 3.12.9, RDFLib 7.6.0, owlrl 7.6.2 and pytest 9.1.1:

```text
.venv/bin/python -m pytest -q tests/test_semantic_validation.py
70 passed in 0.85s

.venv/bin/python -m ruff check tests/test_semantic_validation.py
All checks passed!
```

The successful run includes 1,500 external-oracle query comparisons; 2,048 enumerated interpretations across 32 inputs (24 consistent and eight inconsistent); and 78 property/update states checked against both direct relation algebra and fresh recomputation. The exhaustive oracle found 297 satisfying interpretations in total. Timings above describe this test run only and are not reasoning benchmark claims.

The initial run identified missing pre-profile normalization and an invalid oracle assumption about singleton consequents. The compiler's normalization was corrected, and the singleton test was moved to a direct semantic regression while the OWL RL comparison was narrowed to its actual shared fragment. These changes preserve the intended semantic coverage rather than hiding a reasoner mismatch. A final API review additionally identified missing universal consequences for fresh query names, unresolved exported witness identifiers, and repeated query-domain expansion under a tight fact bound. Each received a regression test and a verified implementation fix.

## Original package verification before the errata fixes

The original integrated run on the same environment passed **183 tests** in 1.03 seconds. This is the baseline preceding the errata corrections, not the current suite total:

```sh
uv sync --locked --extra dev
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests benchmarks
uv build
git diff --check
```

The locked environment synchronized successfully; Ruff and whitespace checks passed;
both the wheel and source distribution built. CLI smoke checks validated the family
example, returned its two equal parent names, and exported the finite L3 example
including its existential witness. These original benchmark observations and
source digests are preserved in [baseline-results.json](../benchmarks/baseline-results.json).

A final datatype audit added ten engine regressions. RDFLib's Python values can
identify literals from OWL-disjoint datatype spaces; automatic identity is now
restricted to well-typed plain/language strings, `xsd:string`, the integer/decimal
family and booleans. Other datatypes remain opaque RDF terms, and ill-typed
literals are excluded from semantic value matching. Regressions cover URI/string,
decimal/float/double, binary values, invalid unsigned-byte values and has-value
classification. This is a deliberately limited datatype interpretation, not
complete OWL datatype entailment or consistency checking. See the
[W3C datatype maps](https://www.w3.org/TR/owl2-syntax/#Datatype_Maps).

## Validation of the errata corrections

The [errata](THESIS_ERRATA.md) maps each correction to its implementation and evidence. New semantic regressions in `tests/test_thesis_corrections.py` cover the exact nominal-equivalence counterexample, strict-subproperty inverse/transitivity errors, domain/range inheritance, the Bach-family example, formula direction and scope, and linear compiled size for conjunctions of unions and enumerations. Positive and negative property queries use fresh probes, including empty properties and incomplete-query limits. Sixteen CLI cases exercise the corrected public query commands.

Rule-maintenance regressions check stale deleted-rule support, alternative derivations and shared rule ownership, unsupported cycles, simultaneous changes, addition/removal overlap, new and removed domain constants, inequality, constraints, equality/function fallbacks, literal identity caches, and resource limits. Three seeds under both naive and semi-naive evaluation perform 45 mixed updates each: **270 transactions**, each checked against fresh materialization and a separate exhaustive ground positive-rule evaluator. The independent evaluator enumerates substitutions and computes closure without using engine joining or maintenance helpers. It covers the selected finite positive Datalog cases, not equality or L3; those have direct regression expectations and safe rebuild paths.

The [corrected maintenance document](CORRECTED_MAINTENANCE.md) states the algorithm and its correctness argument separately from these empirical checks. Tests do not by themselves constitute a general proof. Source validation and performance measurements concern this modern implementation; historical KAON code and raw measurements are not available here.

The dependency-free scripts remain independent evidence for the source errata:

```sh
python3 scripts/check_thesis_logic.py
python3 scripts/check_thesis_errata.py
```

Both scripts pass. The latter demonstrates the *faulty printed algorithm* and its minimal counterexample controls; the engine regressions validate the complete modern replacement. Benchmark correctness assertions run after every measured update and reject partial, inconsistent, or mismatched results.

The integrated correction suite passed **273 tests in 2.68 seconds** on 2026-09-09, including 59 engine tests and 34 benchmark-generator/protocol tests. Ruff and whitespace checks passed. The locked environment synchronized, both package distributions built, and CLI smoke checks returned the expected class-equivalence and transitivity answers:

```sh
uv sync --locked --extra dev
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests benchmarks scripts
python3 scripts/check_thesis_logic.py
python3 scripts/check_thesis_errata.py
uv build
git diff --check
```

## Corrected benchmark results at b1254c4

The corrected benchmark run used:

```sh
uv run python -m benchmarks.run --suite thesis --repeats 5 --timeout 300 \
  --baseline benchmarks/baseline-results.json --output benchmarks/results.json
```

The run started at **2026-09-09T11:35:50Z** on an Apple M4 Max (16 CPUs), macOS 26.5.1, Python 3.12.9, RDFLib 7.6.0, and owlrl 7.6.2. **All 51 cases and 255 repetitions passed**, with no timeouts, mismatches, or incomplete closures. The six maintenance cases each perform six operations in five repetitions, giving **180 checked update/rebuild comparisons**. A post-run audit verified all sample counts and that every recorded source hash still matches the tested files.

Observed correction results:

- A conjunction of 64 two-member enumerations compiles into **130 rules** in a median **9.435 ms**. The avoided `2⁶⁴` expansion is a theoretical branch count, not an executed baseline.
- Rule deletion was **2.21–4.00 times faster** than fresh materialization across the six measured maintenance cases. At depth 5 with 10% changes, deletion took **685.817 ms** versus **1,513.560 ms** for a fresh closure; at 15%, **421.620 ms** versus **1,688.326 ms**. Both inputs started with 147,456 materialized facts. These are workload-specific observations, not a universal incremental-maintenance speed guarantee.
- The largest taxonomy case contains 105,129 RDF triples and materializes 467,416 facts in a median **4.860 seconds**. Its corrected PF target changes the input hash, so it is excluded from before/after comparisons.
- **24 cases** have matching baseline inputs and timing boundaries; **27 are excluded** because their inputs or controls differ or they are new. The median of the 24 per-case materialization ratios is **1.012**, with ratios from **0.881 to 1.759**. The fixes do not provide a general materialization speedup. Some large-input repetitions varied substantially; separate runs were not interleaved or controlled for machine load.

The preserved [b1254c4 report](../benchmarks/baselines/b1254c4/results.md) retains per-case results and comparison exclusions, and [b1254c4 raw observations](../benchmarks/baselines/b1254c4/results.json) retain all repetitions, spreads, operation statistics, input hashes, and source hashes. The [original observations](../benchmarks/baseline-results.json) remain available. At that commit, large conjunction bodies still incurred evaluation cost even when their compilation was factored; the union-scaling cases exposed the limitation addressed by the subsequent research-informed execution improvements.

## Validation of the research-informed improvements

The [research assessment](RESEARCH_IMPROVEMENTS.md) records primary sources,
implementation choices, and the correctness arguments for exact tuple lookup,
unary intersection/delta coalescing, and positive schema consequence indexes.
The compiler, supported language, equality algorithm, and DRed maintenance
algorithm are unchanged by these optimizations.

Fifteen execution regressions compare optimized and generic/naive closures and
explicit expectations. They exercise selective joins, duplicate unary premises,
multiple simultaneous deltas, initially bound variables, constraints, TOP,
ground and equality heads, equality reindexing and retraction, mixed fact/rule
updates, and fact/witness limits. Work-counter assertions verify the avoided
interpreter work without depending on wall-clock timing.

Twenty-five schema regressions compare shortcuts with the original independent
semantic probes, including generated small class/property schemas. They check
conjunctions, cycles, inverses, domains/ranges, equivalence-safe transitivity,
nominal and equality counterexamples, fresh/anonymous classes, empty and
unsatisfiable predicates, invalid API input, and consistency guards. Additional
checks enforce lazy construction without copying a large ABox, separate query
domain state, bounded context retention, and cache invalidation after updates.
Rejected updates preserve the previous cache and ontology together.

The integrated checkout, including the separately added Bach examples and their
tests, passed **363 tests in 6.06 seconds** on 2026-09-09. Ruff, both independent
errata scripts, package wheel/source builds, and whitespace checks passed.
The existing independent OWL RL, finite-model, relation-algebra and randomized
transaction oracles remain in the suite. These tests support the exercised
semantics; they do not establish conformance to unsupported OWL constructs.

The benchmark runner additionally verifies the immutable `b1254c4` report,
its manifest, and every recorded source hash against the commit's Git blobs.
A self-comparison matches all 51 original cases and 36 maintenance operation
groups. Protocol tests reject changed input hashes, timing boundaries,
maintenance mutation controls, and correctness evidence, and prevent outputs
from overwriting the pinned reference. New reports retain source/checkout
provenance and fail if source bytes change during measurement.

## Performance against the fixed b1254c4 baseline

The full run started at **2026-09-09T12:17:42Z** on the same reported Apple M4 Max,
macOS 26.5.1, Python 3.12.9, RDFLib 7.6.0 and owlrl 7.6.2 environment. All
**54 cases and 270 repetitions passed**. All **51 original cases** matched the
pinned inputs, controls, fact counts and expected-answer checks; the **three new
Bach cases** were excluded from historical ratios. The six original maintenance
cases completed **180 update/fresh-closure comparisons**. The runner verified
source integrity throughout, and a final audit matched all 12 recorded source
digests to the measured checkout. This is a measurement of the uncommitted
implementation recorded by those digests, not of unchanged code at HEAD.

Selected medians from the recorded full run:

| Workload and phase | b1254c4 | Improved implementation | Baseline/current |
|---|---:|---:|---:|
| Union conjunction, 4 pairs: materialization | 14.022 ms | 6.287 ms | 2.23× |
| Union conjunction, 8 pairs: materialization | 57.850 ms | 10.985 ms | 5.27× |
| Union conjunction, 16 pairs: materialization | 301.281 ms | 32.413 ms | 9.30× |
| Union conjunction, 32 pairs: materialization | 1,663.508 ms | 48.117 ms | 34.57× |
| Union conjunction, 64 pairs: materialization | 10,406.030 ms | 119.371 ms | 87.17× |
| Enumeration conjunction, 64 pairs: materialization | 95.863 ms | 6.059 ms | 15.82× |
| Taxonomy depth 7, 15 individuals/class, PF: subsumption | 7,983.876 ms | 12.339 ms | 647.03× |
| Same taxonomy: materialization | 4,860.310 ms | 4,388.391 ms | 1.11× |
| Transitive chain, 100 edges: materialization | 451.250 ms | 710.512 ms | 0.64× |
| Cardinality taxonomy depth 5, 3 individuals/class: materialization | 243.571 ms | 367.386 ms | 0.66× |

The 64-pair union keeps 130 compiled rules, 16,641 materialized facts and 96 named
answers. Its Python candidate-row visits decrease from 401,472 to 8,352 and its
body matches from 14,400 to 8,352. Sixty-three redundant delta variants are
coalesced. These counters exclude work inside C-level set intersections and
should not be interpreted as all primitive CPU operations. The largest taxonomy
still contains 105,129 input triples and 467,416 closure facts. Its query timing
includes lazy index construction; it is not a pre-warmed cache measurement.

Across the 28 measured subsumption calls, the median of the per-case speedups is
366.80×, ranging from 114.31× to 851.43×. These are positive named hierarchy
queries that the selected schema fragment can prove. They do not characterize
negative, anonymous, nominal-dependent or arbitrary classification queries.
The median current/baseline materialization ratio over 50 DLP cases (excluding
the external OWL RL control) is **0.939**. This unweighted description is not a
suite-throughput estimate or a uniform speed guarantee.

Maintenance is mixed. Across its six workloads, the median current/baseline
ratios are 1.136 for fact deletion, 1.023 for fact insertion, 1.044 for rule
insertion, 0.993 for rule deletion, 0.968 for rule replacement and 0.957 for mixed
updates. At depth 5 with 10% changes, rule insertion rose from 219.359 to
372.468 ms and rule replacement from 417.815 to 725.576 ms. The algorithm itself
is still DRed; these measurements do not justify claiming a general maintenance
improvement.

Variation is substantial in several regressions: current transitivity samples
range from 454.608 to 883.737 ms, and the cardinality case ranges from 238.193 to
657.805 ms. The baseline and current full runs were not interleaved. Their
original observations and regressions remain visible in the
[full report](../benchmarks/results.md) and [raw results](../benchmarks/results.json).

### Supplemental alternating-version replay

A follow-up run started at **2026-09-09T12:27:28Z**, using
`scripts/replay_b1254c4.py`. It extracted and verified the exact baseline sources
without changing the live branch. Seven workloads ran in **35 pairs / 70
independently launched workers**, alternating baseline/current order and sharing
an explicit hash seed within each pair. All input, closure, expected-answer and
maintenance checks passed. Both versions used the same Python environment, and
the current source hashes match the full-run report. The replay driver has its
own recorded digest.

| Replayed phase | Newly measured baseline | Current | Current/baseline |
|---|---:|---:|---:|
| Transitivity, 100 edges: materialization | 431.559 ms | 439.196 ms | 1.018 |
| Cardinality depth 5, 3 individuals/class: materialization | 219.843 ms | 229.828 ms | 1.045 |
| Existentials, 100 roots: materialization | 65.344 ms | 64.770 ms | 0.991 |
| Union conjunction, 64 pairs: materialization | 10,046.223 ms | 91.846 ms | 0.00914 |
| Taxonomy depth 5, 9 individuals/class, PF: materialization | 152.202 ms | 149.394 ms | 0.982 |
| Same taxonomy: subsumption | 365.093 ms | 0.782 ms | 0.00214 |
| Maintenance depth 5, 10%: rule insertion | 211.294 ms | 206.136 ms | 0.976 |
| Same maintenance: rule replacement | 392.590 ms | 388.564 ms | 0.990 |

The large historical-run regressions were not reproduced at that magnitude.
Small costs remain: transitivity was **1.8% slower** and the selected cardinality
case **4.5% slower** in this replay. These regressions are retained as tradeoffs
of the integrated implementation; the optimization is not universally faster.
The union and schema-query gains persist. All six maintenance operation medians
were lower in each of the two replayed sizes: approximately 3.0–9.6% at depth 3
and 1.0–8.5% at depth 5. Five pairs and two maintenance workloads do not establish
a general maintenance speed guarantee.

The [paired report](../benchmarks/replay-results.md) and
[raw paired observations](../benchmarks/replay-results.json) preserve all 70
worker outputs, execution orders, controls and descriptive paired-resampling
intervals. This provides stronger attribution evidence than the separate full
runs, while leaving machine variability and limited sample size unresolved.
**The pinned historical `b1254c4` report remains the default baseline.** None of
its timings are replaced by these newly measured baseline observations.
