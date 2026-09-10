# Thesis errata and corrections
*Mea culpa, mea maxima culpa* / Raphael Volz (original author)

Review date: 2026-09-09. 

*Web Ontology Reasoning with Logic Databases* (2004), [Volltext.pdf](Volltext.pdf).
The source PDF's SHA-256 is `80146ec324e0a7c342508e38cbe7712f207db8917d6655cd70b9acbcaee2f570`.

*Important:* All page references use **printed page numbers**. Add **16**, so the printed page 136 is PDF page 152 in the digital PDF. Suspect formulas and tables were checked visually in rendered pages, because text extraction can move superscripts and change apparent formulas.

There are confirmed formula errors, substantive errors in some stated reasoning procedures, and internal inconsistencies in benchmark descriptions. **These findings do not establish that the historical KAON implementation made the same mistakes or that its recorded execution times are wrong**. 

This was a focused review more than two decades after the writing of chapters 5–8 and relevant definitions, not an exhaustive verification of every proof or citation.

## Semantic basis for the corrections

The [2004 OWL direct semantics](https://www.w3.org/TR/2004/REC-owl-semantics-20040210/direct.html) provides an independent primary reference for class/property inclusion, inverse properties, and equality without a unique-name assumption, **the thesis was written before those definitions**.

## Confirmed local formula errors

| Location | Problem in the printed formula | Correction or check |
| --- | --- | --- |
| Table 5.3, p. 122 (PDF 138), subproperty row | `P ⊑ Q` is translated as `Q(x,y) → P(x,y)`. | Correct direction: `P(x,y) → Q(x,y)`. Table 6.1, p. 151, uses the correct rule. |
| Table 5.3, p. 122, transitivity row | `P(x,y) → P(x,z) ∧ P(z,y)`. | Correct: `P(x,z) ∧ P(z,y) → P(x,y)`. The printed formula requires decomposition through every universally quantified `z`. Tables 4.4 and 6.1 give the correct direction. |
| Example 5.2.1, p. 121 (PDF 137) | For `A ⊓ ∃R.C ⊑ B ⊓ ∀P.D`, the intermediate formula places `B(x)` inside the implication guarded by `P(x,y₂)`. | The consequent must be `B(x) ∧ (P(x,y₂) → D(y₂))`. With an empty `P`, the printed intermediate formula fails to require `B`. The final two rules immediately below are correct. |
| Table 7.1, p. 184 (PDF 200), body conjunction | The expansion of `C ⊓ D` repeats `φᴸ(C,x)` twice. | The second occurrence must be `φᴸ(D,x)`. Table 5.2 has the correct conjunction translation. |
| §5.4.2.2, p. 133 (PDF 149), distributivity | `F ∨ (G ∧ H) ⇒ (F ∧ G) ∨ (F ∧ H)`. | False, for example at `F=true, G=H=false`. The DNF rewrite needed here is `F ∧ (G ∨ H) ≡ (F ∧ G) ∨ (F ∧ H)`. If retaining the printed left side, the valid distribution gives `(F ∨ G) ∧ (F ∨ H)` instead. |

The intended corrections are clear, but copying these formulas literally would change entailments. Calling them typographical errors describes their likely origin, not their impact on an implementation.

## Substantive errors in stated procedures

### 1. The combined class-equivalence probe can give a false positive

**§5.4.4.2, p. 136 (PDF 152).** The proposed test adds both `C(a)` and `D(b)` to the same knowledge base, then checks `D(a)` and `C(b)`, with `a,b` fresh names.

Consider this L1 ontology, where `{o}` is a singleton nominal:

```text
C ⊑ {o}
D ⊑ {o}
```

It does not entail `C ≡ D`: the interpretation `C={o}`, `D=∅` is a countermodel. But adding both test assertions forces `a=o=b`. Both queried memberships then follow by equality. The augmented ontology is consistent; this failure does not rely on explosion from inconsistency. Fresh names need not denote distinct objects.

**Correction:** run the two subsumption probes independently, discarding the first trial state before starting the second:

```text
KB ∪ {C(a)} ⊨ D(a)
KB ∪ {D(b)} ⊨ C(b)
```

### 2. Exact inverse relationships do not inherit to strict subproperties

**Eq. (5.13), p. 140 (PDF 156):**

```text
inverse(x,z) :- (x ≤ y), inverse(y,z).
```

If `P ⊑ Q` and `Q = R⁻`, then `P ⊑ R⁻`; equality `P = R⁻` does not follow. The surrounding text uses `inverse` to answer exact inverse-property and symmetry queries, so interpreting this predicate as mere inverse inclusion does not repair the procedure.

A countermodel also exposes the interaction with Eq. (5.14), which propagates transitivity through inverses. Let `U={a,b,c}`, `Q=U×U`, and `P={(a,b),(b,c)}`. Then `P ⊆ Q`, `Q` is its own inverse, and `Q` is transitive. The displayed rules derive `inverse(P,Q)` and then `isTransitive(P)`. But `P` is not transitive: `(a,c)` is missing.

**Correction:** propagate exact inverses through property equivalence, or represent inverse inclusion separately and do not use it to infer transitivity.

### 3. Rule deletion leaves an obsolete rederivation rule

**Algorithm 6.1, p. 163 (PDF 179), with Table 6.3, p. 160.** Start with:

```text
A(a).                 # B is empty
P(x) :- A(x).         # r1
P(x) :- B(x).         # r2
```

Initially `P(a)` is materialized. Delete `r1`. Since `r2` still defines `P`, Algorithm 6.1's last-defining-rule branch does not run. The obsolete rewrite of `r1` remains:

```text
PRed(x) :- PDel(x), ANew(x).
```

The temporary rewrites for the directly affected predicate give `PDel(a)` from the old `P`, while `PNew` and `PIns` are empty because the remaining body `BNew` is empty. The surviving `ANew(a)` makes the obsolete rule derive `PRed(a)`. Therefore the differential rule

```text
PMinus(x) :- PDel(x), not PIns(x), not PRed(x).
```

produces no deletion, and the old `P(a)` incorrectly survives. Full recomputation gives an empty `P`. Algorithm 6.2, p. 164, does not remove this obsolete rederivation rule either.

**Correction:** remove the deleted source rule's rederivation contribution even when other rules define the same head; shared rewrites need appropriate ownership bookkeeping. This counterexample grants the differential rules omitted in the next finding, so it is an additional defect in the printed algorithm. A local edit fixing this example alone is not a general correctness argument. The implemented replacement is specified in [CORRECTED_MAINTENANCE.md](CORRECTED_MAINTENANCE.md): overdelete with the old program, then restore support exclusively from the current program. The document gives its scope, algorithm, and soundness/completeness argument.

### 4. The maintenance-program generator omits its differential rules

**Table 6.2 and Definition 6.3.1, pp. 155–156 (PDF 171–172).** The aggregate `θidb(P)` includes the `New`, `Ins`, `Del`, and `Red` generators, but omits the separately listed `θ⁺` and `θ⁻`. The definition constructs the maintenance program from that aggregate and `θedbNew`. Taken literally, it does not generate the `P⁺` and `P⁻` rules needed to update the stored materialization. Example 6.3.1 omits them as well.

**Correction:** define the complete generator as `θidb(P) = θNew(P) ∪ θIns(P) ∪ θDel(P) ∪ θRed(P) ∪ θ⁺(P) ∪ θ⁻(P)`, or explicitly install the last two generators in a separate step. This is a specification omission; it does not establish that the running historical software omitted them. The modern implementation computes fact-set differences directly, so it does not require generated `P⁺`/`P⁻` rules.

### 5. Domain and range inheritance is described backwards

**§5.4.4.6, p. 139 (PDF 155).** The paragraph proposes retrieving subclasses of the asserted domain or range. The valid inheritance goes to superclasses. If `domain(P,Person)` and `Student ⊑ Person ⊑ Agent`, every subject of `P` is an `Agent`, but need not be a `Student`. The same issue applies to ranges.

The alternative fresh-assertion method in the following paragraph has the direction right. This appears to be a local textual reversal, but following it literally gives wrong query answers.

### 6. Symmetry alone does not justify the Bach-family example's new pair

**§6.2.2, p. 151 (PDF 167), Figure 6.2, p. 150.** The example has transitive `AncestorOf`, `AncestorOf ⊑ InDynasty`, and then adds symmetry of `InDynasty`. It claims `InDynasty(jc1,c)` follows, although Figure 6.2 places `jc1` and `c` in different branches, neither an ancestor of the other.

Take `AncestorOf` to be the tree's transitive closure and `InDynasty = AncestorOf ∪ AncestorOf⁻`. This satisfies all three axioms and excludes `(jc1,c)`. Symmetry reverses existing pairs; it does not connect two branches by composing a path. A valid illustrative new pair is `(jc1,j)`, the reverse of an ancestor pair. Making `InDynasty` transitive would also connect the branches, but changes the ontology.

## Complexity statements that need correction

**DNF expansion, p. 133.** The text calls the multiplication linear in the number of conjunctions. An allowed query

```text
(A₁ ∨ B₁) ∧ (A₂ ∨ B₂) ∧ … ∧ (Aₙ ∨ Bₙ)
```

has linear input size but `2ⁿ` irredundant branches in its explicit positive DNF. At `n=20`, that is 1,048,576 branches. Keeping a factored representation or introducing auxiliary predicates can avoid constructing that expansion; the literal expansion cannot be given the claimed linear bound.

**Translation depth versus size, §5.5.3, p. 143 (PDF 159).** The bound `O((l+r)m)` defines `l,r` as the maximum left/right expression depth and `m` as the number of axioms. One axiom containing a balanced binary conjunction of `2ᵈ` distinct atoms has depth `d`, but reading or translating its atoms requires at least `Ω(2ᵈ)` work. A linear structural translation should be bounded in total syntax size, with any cardinality expansion accounted for. Counting already normalized, bounded-size axioms can recover a size-based bound, but that is a different parameterization from the printed statement.

Neither counterexample refutes the separate polynomial **data-complexity** claim with the TBox and query fixed. This review has not established an error in the at-most-three-variables argument or Corollary 5.5.1's `O(|ABox|⁴)` bound under its stated structural transformation. It also has not verified every global L3 complexity claim.

## Algebra and benchmark inconsistencies

**Power-law regression, pp. 204–205 (PDF 220–221).** Starting from `P(r)=c r^(−a)`, the correct transformation is `log P(r)=log c − a log r`. The intercept is `log c` and the slope is `−a`. Page 205 prints a plus sign and swaps the descriptions of slope and intercept. This establishes an algebra/reporting error, not that the numerical regression was necessarily performed incorrectly.

**Table 8.9, p. 216 (PDF 232).** The construction, formulas, and relative columns say that maximum-one restrictions occur twice as often as minimum-zero restrictions. The two absolute columns are reversed. Correct counts under the described construction are:

| TBox | Universal restrictions | Maximum one | Minimum zero |
| --- | ---: | ---: | ---: |
| TS | 13 | 26 | 13 |
| TM | 121 | 242 | 121 |
| TL | 1,093 | 2,186 | 1,093 |

**Table 8.10 and Figure 8.6, p. 217 (PDF 233).** The table associates TM-IS with 3,267 individuals and TM-IM with 5,445. Table 8.7 and the unchanged ABox generator imply 1,089 and 3,267, respectively; 5,445 belongs to TM-IL. The figure repeats the shifted counts. This is an internal inconsistency. The document alone does not establish which workload the recorded timing actually used.

**Table 8.7, p. 208 (PDF 224).** The described P1 generator on p. 207 assigns one filler per third individual and excludes individuals at the root. The printed filler counts appear to include the root when computing fillers, while excluding it when computing individuals:

| TBox | IS: expected / printed | IM: expected / printed | IL: expected / printed |
| --- | ---: | ---: | ---: |
| TS | 39 / 40 | 117 / 120 | 195 / 200 |
| TM | 363 / 364 | 1,089 / 1,092 | 1,815 / 1,820 |
| TL | 3,279 / 3,280 | 9,837 / 9,840 | 16,395 / 16,400 |

These corrections are conditional on the prose generator being authoritative. They do not recover the historical generator's implementation.

## Ambiguous notation and minor presentation issues

**Correction to our earlier mapping:** Example 5.4.2, pp. 133–134, displays `∃R.A ⊓ (B ⊔ C)` and then evaluates `B` and `C` on the successor. With tight-binding restriction notation, the displayed expression places those conjuncts on the subject, while the following formulas implement `∃R.(A ⊓ (B ⊔ C))`. However, the thesis uses similarly loose scope notation on p. 86, where the explicit normalization makes wider quantifier scope apparent. This should therefore be reported as **ambiguous scope/missing parentheses**, not as a separately proven semantic error. The previous mapping was too categorical.

Two further small issues require these replacements: on p. 134 use `n` naive checks for retrieving the `n` classes of one given individual, reserving `n×m` for all `m` individuals. In Table 7.1's L3 existential row on p. 184, put the right-side translation marker in the head; `φᴿ(∃R.C,x) :- B` generates `C(fᵢ(x)) :- B` and `R(x,fᵢ(x)) :- B`, with well-formed parentheses. For a complex filler `C`, continue its structural head translation.

## Reproducible checks and effect on this implementation

The following dependency-free scripts check finite countermodels, Boolean formulas, the printed maintenance rules, and numerical identities without using this repository's reasoner as an oracle:

```sh
python3 scripts/check_thesis_logic.py
python3 scripts/check_thesis_errata.py
```

See [logical counterexamples](../scripts/check_thesis_logic.py) and [maintenance and arithmetic checks](../scripts/check_thesis_errata.py). The finite checks substantiate the counterexamples; they are not a proof of the correctness of an entire replacement reasoner.

The corrected implementation and its regression coverage are mapped below. Historical regression figures and counts are corrected analytically; no historical raw data or KAON source is available in this repository to reconstruct its original experiments.

| Required correction | Implementation or replacement | Evidence |
| --- | --- | --- |
| Inclusion, transitivity, conjunction, and restriction scope | Correct Horn translations retained; explicit scope cases added | `tests/test_thesis_corrections.py` |
| Independent class-equivalence tests | `Reasoner.equivalent_classes` runs separate fresh probes | Nominal contamination, empty-class, and isolation regressions |
| Exact inverses and correct domain/range inheritance | Property APIs use semantic probes, including two independent inverse directions | Strict-subproperty, empty-property, inferred-domain/range, and accidental ABox-shape regressions |
| Symmetry example | Symmetry derives reversed ancestor pairs, without connecting separate branches | Bach-family regression |
| Rule deletion and missing differential generation | Direct DRed over old/current programs; full compiled candidates determine surviving rule ownership | Engine regressions, independent ground oracle, and [correctness argument](CORRECTED_MAINTENANCE.md) |
| Avoid exponential query expansion | Existing Boolean factoring retained; remaining conjunction-of-enumerations expansion fixed with auxiliary predicates | 20 two-member enumerations compile to 42 rules; Boolean and enumeration scaling regressions |
| Stable unchanged rule identity | Canonical rule-local variable names | Unrelated schema additions preserve unchanged rules; shared-owner deletion regression |
| Benchmark counts and labels | Generators assert actual class, individual, filler, and restriction counts; P1 excludes root individuals; maintenance follows its separate root-inclusive population | `tests/test_benchmark_workloads.py`, corrected cardinality and maintenance benchmark cases |
| New performance evidence | Full suite rerun with five samples per case, raw input/source hashes, validation after every update, and preserved prior observations | [Results](../benchmarks/results.md), [raw data](../benchmarks/results.json), [baseline](../benchmarks/baseline-results.json) |

The matching CLI commands expose the corrected class and property queries. Equality and existential retractions retain explicit rematerialization fallbacks. These changes validate the modern replacement within its documented scope; they do not certify the historical implementation or recreate unavailable experimental data. Full test and build results are recorded in [VALIDATION.md](VALIDATION.md).
