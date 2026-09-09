# Research-informed improvements, 2004–2026

This report records the modernization committed as `8ce254f`. The subsequent
[original experimental study](RESEARCH_EXPERIMENTS.md) revisits these observations,
adds falsifiable hypotheses and controlled ablations, and retains `b1254c4` as
the historical baseline.

This assessment uses the implementation and recorded evaluation at commit
`b1254c441731ca4fdf32ea83570ff99aaa84ac2a` as its fixed starting point. It is a
targeted review of primary research relevant to this reasoner's measured costs,
conducted on 2026-09-09, rather than an exhaustive review of every publication
since the 2004 thesis. The implementation remains a Python DLP reasoner with
RDFLib parsing and the same supported semantics and public API.

## What the baseline suggests

The corrected compiler already avoids exponential distribution of conjunctions
of unions, but the evaluator still pays heavily for their long rule bodies. The
64-pair union workload compiles to 130 rules and only 16,641 materialized facts,
yet materialization takes a median 10.406 seconds. Repeated selection of the next
join and evaluation of overlapping delta variants are the immediate targets.

Schema queries present another opportunity: the baseline proves even a simple
named subclass chain by copying the whole ontology, adding a fresh individual,
recompiling, and materializing a new closure. This is appropriate as a general
semantic test, but much more work than needed for consequences already provable
from simple schema rules. Instance-query scans, equality reindexing, compilation,
and deletion maintenance remain separate costs.

These observations are specific to the preserved [baseline data](../benchmarks/baselines/b1254c4/results.json).
They do not establish that the historical KAON implementation had the same costs.

## Research and implementation decisions

| Research | Relevant finding | Decision for this implementation |
|---|---|---|
| Motik et al., *Parallel Materialisation of Datalog Programs in Centralised, Main-Memory RDF Systems*, AAAI 2014, §§3–4. [Paper](https://ojs.aaai.org/index.php/AAAI/article/view/8730/8589) | Hash indexes accelerate bound atom matching; different triggering body facts can repeat the same rule instantiation. | Implement exact membership probes and coalesce delta variants for eligible unary conjunctions. This is a sequential adaptation; it does not implement RDFox's parallel scheduler, fact ordering, or lock-free indexes. |
| Subotić et al., *Automatic Index Selection for Large-Scale Datalog Computation*, PVLDB 12(2), 2018. [Paper](https://www.vldb.org/pvldb/vol12/p141-subotic.pdf) | Planning the primitive searches performed by a Datalog program can substantially improve indexing and execution. | Cache recognition of a common body shape and execute it as set intersections. Retain existing hash indexes. This does not implement Soufflé's minimum-index selection algorithm or its native compilation. |
| Kazakov, Krötzsch and Simančík, *The Incredible ELK*, Journal of Automated Reasoning, 2014. [Author manuscript](https://iccl.inf.tu-dresden.de/w/images/3/38/Incredible-elk-jar-2013.pdf) | Context-based consequence computation and premise indexing make lightweight ontology classification efficient. | Add a lazy index of positive schema consequences, using a much smaller Horn fragment. It is neither a complete EL classifier nor an implementation of ELK's calculus or parallelization. |
| Armas Romero, Cuenca Grau and Horrocks, *MORe: Modular Combination of OWL Reasoners for Ontology Classification*, ISWC 2012. [Paper](https://www.cs.ox.ac.uk/people/ian.horrocks/Publications/download/2012/ArCH12b.pdf) | Cheap obvious subsumptions and combinations of specialized and general reasoning can reduce classification work. Complete modular reasoning requires preservation conditions. | Return a positive result when a schema derivation proves it; otherwise retain the independent full semantic probe. Do not infer a negative result from the restricted cache or remove ABox axioms without a preservation argument. |
| Veldhuizen, *Leapfrog Triejoin: A Simple, Worst-Case Optimal Join Algorithm*, ICDT 2014, §3.1. [Paper](https://www.openproceedings.org/2014/conf/icdt/Veldhuizen14.pdf) | Unary joins are set intersections; the full algorithm generalizes this through sorted trie iterators with a worst-case guarantee. | Implement the unary case with hash-set intersections. Defer a full trie-join backend: the exposed large conjunction needs no general multi-variable join. No general worst-case-optimal join claim is made for this engine. |
| Motik et al., *Handling owl:sameAs via Rewriting*, AAAI 2015. [Author report](https://arxiv.org/abs/1411.3622) | Canonical representative rewriting avoids expanding all equivalent names, but correctness requires careful interaction with rule evaluation. | The baseline already uses representative equality and congruence. Preserve it, and test optimized execution after equality reindexing. This pass does not introduce a new equality algorithm. |
| Hu, Motik and Horrocks, *Optimised Maintenance of Datalog Materialisations*, AAAI 2018. [Paper](https://www.cs.ox.ac.uk/people/ian.horrocks/Publications/download/2018/HuMH18a.pdf) | Hybrid counting with DRed/B/F reduces expensive backward evaluation and handles recursive programs. | Retain corrected DRed and measure how execution improvements affect it. A future DRedᶜ/B/Fᶜ implementation needs recursive/nonrecursive support accounting; simple total reference counts would incorrectly retain unsupported cycles. |
| Motik et al., *Maintenance of Datalog Materialisations Revisited*, Artificial Intelligence 269, 2019. [Publication](https://doi.org/10.1016/j.artint.2018.12.004) | Optimized DRed and Forward/Backward/Forward address redundant derivations and multiple support; algorithms have workload-dependent tradeoffs. | Defer a maintenance replacement until support counters, rule transactions, and memory costs are evaluated together. The existing fresh-recomputation oracle and mixed-update suite remain applicable. |
| Hu, Motik and Horrocks, *Modular Materialisation of Datalog Programs*, AAAI 2019; extended journal study, 2022. [Conference paper](https://ojs.aaai.org/index.php/AAAI/article/download/4139/4017), [journal record](https://ora.ox.ac.uk/objects/uuid%3Ae8b03b8d-bfb4-44fc-975b-579875405d52) | Specialized closure procedures can avoid enumerating redundant rule applications; integrating modules requires explicit correctness conditions. | Adopt the narrow principle of recognizing an exact, provably equivalent subcase with a generic fallback. Defer specialized transitivity modules and their deletion interfaces. The present optimizer is not an implementation of that modular maintenance framework. |
| Budiu et al., *DBSP: Automatic Incremental View Maintenance for Rich Query Languages*, PVLDB 16(7), 2023. [Paper](https://www.vldb.org/pvldb/vol16/p1601-budiu.pdf) | Stream algebra provides compositional incrementalization, including recursive queries, with machine-checked foundations. | A promising future backend, but replacing this finite-set engine with weighted stream circuits is a larger design change. Equality splitting, Skolem limits, and changing rule programs require an explicit translation. DBSP's proof is not a proof of this implementation. |
| Zhang et al., *Enhancing Datalog Reasoning with Hypertree Decompositions*, IJCAI 2023. [Paper](https://www.ijcai.org/proceedings/2023/0377.pdf) | Hypertree decomposition reduces redundancy in complex cyclic rule bodies, but decomposition structures add runtime and memory overhead. | Keep a cheap specialized plan for the current unary bottleneck and the existing general solver for other bodies. Defer general hypertree plans until workloads with complex cyclic joins can justify and validate the added structures. |
| Zhang et al., *Optimised Storage for Datalog Reasoning*, AAAI 2024. [Paper](https://www.cs.ox.ac.uk/people/ian.horrocks/Publications/download/2024/Zhang0N024.pdf); Zhang, *Optimising Datalog Materialisations*, Oxford DPhil, 2025. [Thesis record](https://ora.ox.ac.uk/objects/uuid%3Ac2b829f0-4810-416e-8e63-6919228c0722) | Specialized representations of transitive closure and union rules can reduce the storage cost of explicit materialization; the thesis combines storage and rule-evaluation approaches. | A high-priority future direction for large closures. Defer compressed relations here: the engine and update oracle expose explicit fact sets, so lazy storage would need a relation abstraction, deletion support, and separate memory/query tradeoff benchmarks. The present set intersections accelerate evaluation without compressing stored consequences. |

The selected changes address measured costs without a new production dependency.
Parallel native execution, compressed storage, a new maintenance backend, and a
full classification engine are larger engineering projects. Temporal extensions
and approximate/neural reasoning would change the task's language or entailment
contract and are outside this performance modernization.

## Execution changes and correctness obligations

For a body `P1(x), ..., Pn(x)`, let `I(Pi)` be its current unary relation. Its
solutions are exactly the intersection of those relations. For semi-naive
evaluation with delta relations `D(Pi)`, the union of all ordinary delta variants
is exactly:

```text
(I(P1) ∩ ... ∩ I(Pn)) ∩ (D(P1) ∪ ... ∪ D(Pn)).
```

Membership in the second factor means that at least one body atom uses a new
fact; membership in the first means all premises hold. Each resulting binding
needs to fire the rule only once because materialization uses set semantics.
Repeated predicates in a body do not change this argument. A bound variable
reduces the calculation to membership of its singleton value.

The implementation caches only eligible shapes and evaluates their intersections
starting from small sets. Equality atoms, inequality atoms, different variables,
and structured body terms retain the general solver. Head construction,
normalization, fact limits, integrity checks, and update propagation still go
through their existing mechanisms. Naive evaluation retains the general body
solver as a differential reference.

A fully bound relational atom denotes one tuple, so exact tuple membership in
the relation replaces scanning a single-column bucket. Partially bound atoms
retain the existing indexed search. This changes access work, not the selected
substitutions.

## Schema changes and correctness obligations

The schema cache records consequences of selected compiled rules without using
observed ABox membership as evidence for a universal assertion. Unary Horn
consequences are closed in a class context. Property inclusions carry an
orientation so inverse links reverse arguments explicitly. Domain and range
consequences follow these oriented inclusions and unary class implications.
Transitivity is transferred through proven property equivalence, including
inversion, rather than through a strict subproperty link.

Every shortcut must be a derivation using rules valid in the full ontology.
Adding other axioms cannot invalidate a positive classical consequence. Missing
information in this restricted cache establishes nothing, so the previous full
probe handles remaining cases, including nominal- and equality-dependent
reasoning. The public consistency/completeness guards still apply. Cache state
is discarded after a successful ontology update; a rejected update preserves
the old ontology and cache together. Class equivalence still establishes its
two directions independently.

## Evaluation contract

The default reference is the exact JSON blob from `b1254c4`, protected by a
recorded SHA-256 digest and source hashes. Its 51 cases, all five raw repetitions,
and historical measurement environment remain unchanged. The older
`benchmarks/baseline-results.json` is historical evidence preceding the errata
fixes; it is not the default baseline anymore.

Run the full workload suite with:

```sh
.venv/bin/python -m benchmarks.run --suite thesis --repeats 5 --timeout 300 \
  --output benchmarks/results.json
```

The concurrently added Bach benchmark extends the suite to 54 cases. The
original 51 cases retain their inputs and controls and are compared with
`b1254c4`; the three new Bach cases have no recorded baseline and are reported
separately. They do not contribute to aggregate before/after ratios.

Input hashes, workload controls, measurement boundaries, result counts, and
maintenance operation controls must match before making a comparison. All
initial closures and updates must pass the workload's expected-answer checks;
each maintenance operation must also match a fresh closure. Changed evaluation
counters are performance evidence, not correctness mismatches. `candidate_rows`
counts tuples visited by the Python binding solver; it excludes internal
hash-set intersection probes and is not a count of all CPU operations. Timing of a
schema query includes construction of its lazy schema index.

Five repetitions per worker describe variation within that run. Bootstrap
intervals in the generated comparison are descriptive, not a claim of
statistical significance or a correction for machine load, thermal effects,
process order, or differences between runs. Small timing changes, especially
in phases with unchanged source code, require caution. Report improvements and
regressions separately rather than averaging unlike query and materialization
phases together. Whole-process peak RSS is not isolated engine memory.

The [generated comparison](../benchmarks/results.md) and
[validation record](VALIDATION.md) contain the completed measurements and checks.
The [supplemental paired replay](../benchmarks/replay-results.md) investigates
selected gains and regressions using newly measured archived/current code; it
does not replace the historical baseline. The validated changes offer large
improvements on their target workloads, with mixed results elsewhere.
