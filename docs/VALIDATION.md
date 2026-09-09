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

## Corrected benchmark results

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

The full [generated report](../benchmarks/results.md) retains per-case results and comparison exclusions, and [raw observations](../benchmarks/results.json) retain all repetitions, spreads, operation statistics, input hashes, and source hashes. The [original observations](../benchmarks/baseline-results.json) remain available. Large conjunction bodies still incur evaluation cost even when their compilation is factored; the union-scaling cases expose that remaining performance limitation.
