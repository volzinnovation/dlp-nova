# Corrected maintenance under changes to facts and rules

This document specifies the operational replacement for the faulty rule-maintenance procedure identified in [THESIS_ERRATA.md](THESIS_ERRATA.md), Algorithm 6.1 on printed p. 163. It uses delete-and-rederive (DRed) directly over materialized facts instead of retaining a second program of generated maintenance rules. The change preserves the thesis's goal of incremental maintenance while eliminating obsolete rewrite ownership as a source of support.

## Scope and state

Let `E` be the old explicit facts, `P` the old rule set, and `M = lfp(P,E)` the complete old materialization. The update supplies fact additions/removals and rule additions/removals together. Their set semantics define the new explicit facts `E'` and rules `P'`, with addition winning when the same item occurs in both input sets. The implementation validates the complete candidate before changing the live state.

The incremental deletion argument applies to finite, function-free positive Horn materialization without individual equality. Every stored tuple has a finite positive derivation, and rule bodies are monotone. The engine's fixed semantics for explicit inequality and supported literal distinctions are preserved; denials report violations but do not derive arbitrary consequences. Domain membership includes the nonempty-domain representative and constants used by the active facts and rules.

Equality can merge or split individual representatives; existential function terms can generate an unbounded domain. Retractions outside the incremental deletion eligibility conditions use complete rematerialization, subject to the ordinary resource limits. A partial old materialization is never accepted as a completed starting point for deletion maintenance.

## Replacement algorithm

The key rule is: **use old rules to identify potentially invalid consequences, and only current rules to justify their restoration.**

```text
1. Validate E' and P', retaining the old rules P for overdeletion.

2. Seed a deletion set D with:
   - removed explicit facts that were present in M;
   - heads obtained by evaluating each removed rule over M;
   - old domain facts whose constants no longer occur in E' or P'.
   Current explicit facts and current domain facts remain protected.

3. Overdelete to a fixed point using P and the old materialization M:
   whenever an old rule has a satisfied body containing a fact in D,
   add its old head to D, except protected facts.
   Respect the symmetry of explicitly represented inequality facts.

4. Remove D from the materialized store, install P', and rebuild its indexes.

5. Restore current explicit/domain facts, find surviving support for deleted
   heads using P' only, and evaluate newly added rules. Propagate the resulting
   insertions/rederivations with the ordinary positive fixed-point evaluator.

6. Recheck constraints and publish the completed new materialization.
```

Step 5 may be implemented as separate rederivation and insertion phases. The final result must equal the least fixed point of the current facts and rules, regardless of that scheduling. A removed rule never participates in rederivation. If two active source axioms compile to the same semantic rule, removing just one source axiom must leave the rule present; the RDF layer computes deltas between the complete old and new compiled programs.

Protecting a current explicit fact also protects its consequences from unnecessary overdeletion through that particular support: the fact has an independent surviving justification. Facts having other surviving rule derivations may still be overdeleted and subsequently restored. This is intentional; recursive facts must not preserve one another after all external support disappears.

## Correctness argument

Under the eligibility assumptions and with sufficient resources, the algorithm computes exactly `lfp(P',E')`.

**Retained facts are sound.** Choose any finite old derivation of a retained fact. If that proof uses a removed assertion, a removed rule, or an obsolete domain fact, step 2 seeds the affected node and step 3 propagates overdeletion along the proof. The propagation can stop at a protected fact, but that fact already has a current explicit/domain justification. Replacing those stopped proof prefixes with their current justifications leaves a derivation using current support. Thus an unsupported old consequence cannot remain outside the deletion set.

**Rederivation is sound.** After overdeletion, retained facts and current explicit/domain facts are sound. Subsequent positive inference uses only rules in `P'`, so every restored or inserted fact is sound in the current materialization. In particular, the removed rule in the thesis's counterexample cannot rederive `P(a)`.

**Rederivation is complete.** Every fact in the new least model has a finite derivation from `E'` and `P'`. By induction on its derivation height, a fact is either already retained/currently asserted, or all premises of a current rule eventually become available. The evaluator checks surviving support for the affected heads, evaluates new rules, and propagates every new fact through dependent rule positions until a fixed point. Consequently every such head is eventually derived.

The implementation's targeted rederivation optimization also depends on the unchanged old model being complete: an unchanged rule whose premises were already retained cannot suddenly derive an entirely new old-domain head, because that head would have been in `M`. A genuinely new conclusion must involve a new rule, a newly inserted/domain fact, or a restored premise, each of which triggers evaluation.

These arguments describe the corrected algorithm. They do not retroactively prove the printed Algorithm 6.1, establish a complexity bound for arbitrary accepted programs, or certify the historical KAON implementation.

## Bounded execution and fallbacks

Overdeletion temporarily works with old facts, some of which may be unsupported after the update. If a resource limit interrupts that phase, the engine discards that tentative result and rematerializes from current facts and rules. Any resulting finite prefix therefore contains only sound current consequences. Resource exhaustion remains visible through `complete=False`; an unfinished computation cannot establish a negative answer.

Updates that require equality reconstruction or existential reconstruction retain the safe rematerialization path. The selected method is exposed through `stats["update_method"]`. Benchmark results report that method alongside timing; a fallback is not labeled incremental rule maintenance.

## Executable validation

The engine regressions cover deletion of the only successful rule when another unsuccessful rule shares the head, surviving alternative support, unsupported recursive cycles, shared source rules, simultaneous rule/fact changes, changing domain constants, equality/existential fallbacks, and interrupted overdeletion. Seeded mixed-update sequences compare every completed state with fresh materialization and a separate small positive evaluator.

The benchmark suite times rule deletion separately from fresh recomputation and checks their full materialized fact sets for equality. It also validates the full fact/rule update sequence after each operation. See [VALIDATION.md](VALIDATION.md) and the [benchmark methodology](../benchmarks/README.md) for commands, measured coverage, and limitations.
