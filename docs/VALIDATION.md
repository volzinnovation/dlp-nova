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

## Integrated package verification

The final integrated run on the same environment passed **183 tests** in 1.03 seconds:

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
including its existential witness. Benchmark evidence is in
[results.md](../benchmarks/results.md), with source digests and raw samples in
[results.json](../benchmarks/results.json).

A final datatype audit added ten engine regressions. RDFLib's Python values can
identify literals from OWL-disjoint datatype spaces; automatic identity is now
restricted to well-typed plain/language strings, `xsd:string`, the integer/decimal
family and booleans. Other datatypes remain opaque RDF terms, and ill-typed
literals are excluded from semantic value matching. Regressions cover URI/string,
decimal/float/double, binary values, invalid unsigned-byte values and has-value
classification. This is a deliberately limited datatype interpretation, not
complete OWL datatype entailment or consistency checking. See the
[W3C datatype maps](https://www.w3.org/TR/owl2-syntax/#Datatype_Maps).
