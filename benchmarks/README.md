# Benchmark methodology

Run from the repository root with the locked development environment:

```sh
uv run python -m benchmarks.run --suite thesis --repeats 5 \
  --output /tmp/dlp-results.json
```

The runner writes JSON after every case and derives an adjacent Markdown report. Each case runs in a separate Python subprocess with a configurable wall-time limit (180 seconds by default). A timeout, mismatch or error is recorded and makes the runner exit unsuccessfully. Five repetitions occur within the worker; there is no discarded warm-up. Generation and N-Triples serialization are outside the timed phases. Parsing, compilation and materialization are separate, measured with `time.perf_counter`. Instance queries run against the materialized store. TBox subsumption times the complete first public `subsumes` call on each fresh reasoner: the baseline rebuilt an isolated probe, while a new lazy schema index or fast path built inside that call remains included in its measured time. This preserves the observable operation and timing boundary when the implementation changes. Full raw samples, median, mean, spread, counts and process peak RSS are recorded.

The input hash covers sorted N-Triples. Generators use fixed IRIs, fixed blank-node labels, and seed 2004. Peak RSS is the process high-water mark, including input graphs, parser, retained objects and previous repetitions; it is not the engine's isolated allocation. Values are normalized to bytes on macOS and Linux. Workloads run sequentially. Package versions, platform, architecture, CPU information, Python hash-seed setting, full Git HEAD, dirty checkout status, and SHA-256 hashes of every reasoner and benchmark Python source are saved. Source hashes are checked after each case; changing measured Python files during a run stops it with an error. The Git revision identifies the checkout, while the hashes identify the exact measured source bytes, including uncommitted changes. Assertions are enabled; the worker refuses optimized Python execution that would disable validation.

The full suite contains **54 cases**: 27 taxonomy cases, two external/execution comparators, two inverse-functional equality cases, one existential case, one transitivity case, four cardinality cases, five union cases, three enumeration cases, six synthetic maintenance cases, and three Bach cases. `--suite quick` selects 17 cases, retaining a smaller example of each family. A case is reported as validated only after all of its repetitions and correctness checks finish.

Run only the source-backed Bach cases with `uv run python -m benchmarks.run --suite bach --repeats 5`.
This suite defaults to `benchmarks/bach-results.json` and an adjacent Markdown report. It parses
the actual [Turtle/RDF/XML ontologies](../docs/BACH_BENCHMARK.md), with file reading outside the
timer, instead of reserializing a generated graph into N-Triples. The 25 full-ontology queries
run for each syntax; seven further queries exercise the separate family tree. Each query's
complete expected and actual answer and timing are recorded. The summary query time is their
sum per repetition; complex OWL expression queries include temporary query compilation and
materialization. The input hash uses canonical blank-node labels, with source-file and query-manifest
hashes also saved. Bach maintenance uses the RDF API, so update and fresh-rebuild timings both
include compilation; synthetic maintenance uses precompiled inputs. See the
[Bach report](bach-results.md) and [query manifest](../examples/bach-queries.json).

## Cases and deviations from the thesis

- **Taxonomy:** the complete 27-case matrix uses branching factor 3, depths 3/5/7 (40/364/3280 classes), 3/9/15 individuals per non-root class, and P0/P1/PF property variants from thesis Tables 8.4–8.6. P1 creates one property per class and a filler on each third individual; the root has neither individuals nor fillers. This follows the generator prose rather than the inconsistent filler counts in Table 8.7. PF declares 200 properties and picks one uniformly per individual. Property targets use the previous generated individual; the first PF individual points to itself. This corrects the prior generator's untyped `i0_0` target outside its declared population. Actual population and filler counts are recorded. This baseline taxonomy has no added constructor restrictions.
- **Queries:** repeated root instance retrieval and a fixed property pair query provide stable, analytically checkable workloads, rather than the thesis's random query selection. Named subclass probes verify the deepest class is subsumed by the root. The root instance count and all generated class-fact counts have independent arithmetic expectations.
- **Equality:** inverse-functional keys identify 100 and 1,000 pairs of named aliases. Both aliases must inherit their class memberships. These original cases isolate inferred equality.
- **Corrected cardinality distribution:** four additional cases use depth/individuals-per-class controls `(3,3)`, `(5,3)`, `(7,3)`, and `(5,9)`. Following §8.5.2, each internal class has one universal restriction to its first child; first and third children have maximum one, and second children have minimum zero. Thus universal/max-one/min-zero counts are **13/26/13**, **121/242/121**, and **1,093/2,186/1,093** at depths 3/5/7. The runner counts the RDF restriction nodes and checks these expectations. Each directly max-one-restricted subject has two fresh named fillers on the applicable property, forcing one equality merge. Exact merge counts, named answers, and canonical class-fact totals are checked. Minimum zero is recorded in the input even though normalization removes it. This explicit filler policy makes equality reproducible; it does not claim to recover the historical ABox generator.
- **Factored unions:** conjunctions of 4/8/16/32/64 binary unions classify 128 subjects, with exactly 96 positives. Their explicit DNF expansions would have `2^n` branches. Actual compiled rule counts and maximum variables per rule are recorded and checked to remain bounded linearly in this family. Branch counts describe avoided expansions, not work the engine executes.
- **Factored enumerations:** conjunctions of 16/32/64 `owl:oneOf` pairs directly exercise the compiler defect corrected after the errata review. Each pair is `{Ai,Bi}`, all `Ai` are asserted equal to one common individual, and 128 query aliases split equally between that individual and `B0`. The query must return the common individual, all `Ai`, and the 64 positive aliases, excluding `Bi` and the negative aliases. Equality-merge counts are also checked. The union and enumeration cases measure compilation separately from reasoning and querying.
- **Existentials:** 100 named roots generate four acyclic levels of witnesses. The final level must contain exactly 100 witnesses. Cyclic witness bounds are unit-tested, not presented as a completed timing benchmark.
- **Transitivity:** a chain of 100 edges must yield exactly 5,050 reachable ordered pairs.
- **Maintenance:** the full six-case matrix uses branching factor five, depths 3/4/5 and change ratios 10%/15%. Five individuals belong directly to **every class, including the root**, following the explicit population formula on p. 221: 780/3,905/19,530 individuals. Seeded sampling selects the changed assertions, with integer flooring for the percentage. Additional rules give a predicate two supported branches, an empty alternate body, and a recursive cycle. Each repetition performs fact deletion, fact insertion, rule insertion, rule deletion retaining alternate support, simultaneous rule replacement, and an atomic batch changing both facts and rules. The cyclic result must lose unsupported memberships when an external support disappears. All six operations are timed separately, and observed maintenance methods/counters are retained. Eligible rule deletions must use `dred-rules`; an unnoticed rebuild is a validation failure for these cases.
- **Maintenance validation:** independently tracked asserted facts and source rules construct a fresh engine after every operation. The complete fact set and consistency must match. Each update has a corresponding fresh-rebuild timing excluding parsing/compilation, because the update API also receives precompiled rules. This checks incremental maintenance against recomputation using the same engine; it is not an independent proof of all Horn semantics. The six-operation sequence is an expanded modern stress test, not the historical rewriting program or its exact update sequence.
- **Comparators:** a small depth-3/3-individual/P0 case runs the naive engine and the external `owlrl` OWL RL materializer. OWL RL performs additional schema/axiomatic inference, so total closure counts and workload scope differ. The root's named instance answer is checked against the same expectation. Naive and semi-naive share the compiler and equality code; independent semantic oracles are in the test suite.

No comparison with the thesis's historical millisecond figures is meaningful: both hardware and measurement boundaries differ. The implementation does not claim the thesis's exact quartic data-complexity bound for every accepted rule shape, nor a production performance guarantee. Measurements characterize these deterministic workloads on the recorded machine.

## Before/after comparisons

The default reference is **commit `b1254c441731ca4fdf32ea83570ff99aaa84ac2a`**, preserved in [baselines/b1254c4/results.json](baselines/b1254c4/results.json) with a [manifest](baselines/b1254c4/manifest.json). It contains all 51 cases with five repetitions each. The saved report's SHA-256 is `6f0bc493cae0fb96b474405eb9496dc9ce2c3155b313f2bcd3de49b3dc8b51e2`. This replaces the older `baseline-results.json` as the default reference; that earlier artifact remains historical evidence.

Loading the default verifies its pinned full commit and report digest, manifest/source hashes, case count, repetitions and validation status. Where the commit's Git objects are available, the report and every recorded source hash are also checked against those immutable blobs. Output paths inside `benchmarks/baselines/`, and aliases that would overwrite the chosen baseline, are rejected. Running a benchmark never updates or replaces the reference. `--baseline PATH` explicitly selects another report; an external custom report without verified provenance is labeled accordingly. `--no-baseline` explicitly disables comparisons.

Comparisons match case controls (ignoring repetition count), exact input hashes, and both reports' timing protocols. All 51 original cases, including PF and maintenance, match the selected reference when the input generators remain unchanged; the three new Bach cases have no measurements in the pinned report and are excluded from its before/after ratios. Maintenance additionally requires the same operation protocol and fact/rule mutation counts. Each of its six operations reports before/after update time, fresh-rebuild time, and work counters, rather than only comparing initial materialization. Parsing, compilation, instance/property queries, and the public subsumption call receive separate comparisons. Common counters retain both versions' samples; newly introduced unary-plan/intersection/coalescing counters have `null` baseline values and an explicit availability flag, never invented zeros.

`candidate_rows` counts rows visited by Python's binding evaluator. It excludes hash probes performed inside C-level set intersections; `unary_intersections` counts those intersection calls. Reductions in candidate rows therefore describe avoided interpreter work, not a count of every primitive operation performed by the engine.

Cross-version correctness evidence includes both runs' successful workload checks, expected query-answer counts, unchanged initial fact counts, and corresponding maintenance closure counts. Every update still must match a fresh closure. The historical reference did not save full answer sets or their digests, so the comparison does not claim a historical output-hash match; it relies on the expected-answer assertions in the verified benchmark source. A mismatch in recorded correctness fields makes the new run exit unsuccessfully. Changes in evaluation counters are expected and are not treated as semantic failures.

## Uncertainty and interpretation

Each timing comparison records the ratio of medians, raw sample counts and observed ranges. For two or more positive observations per version, it also reports a deterministic 95% percentile bootstrap interval from 2,000 independent resamplings of the two recorded lists, using seed 2004. Nonpositive or missing observations yield no interval; a zero baseline median yields no ratio. The baseline's original five observations are preserved exactly.

These intervals describe sensitivity to the observed samples. Five repetitions within one process cannot characterize between-process variation, between-run drift, or machine-load differences, and the old and new runs are not interleaved. The intervals therefore are **descriptive resampling intervals**, not guarantees of 95% repeated-experiment coverage, causal speedups, or significance tests. A ratio below one means a shorter current median; the full spread and absolute timings matter, especially for tiny cached queries. No suite-wide throughput claim is inferred by pooling unrelated cases.

The methodology follows the emphasis on explicit experimental conditions and interpretable uncertainty in [Hoefler and Belli, *Scientific Benchmarking of Parallel Computing Systems* (2015)](https://spcl.inf.ethz.ch/Publications/index.php?pub=222), and on uncertainty in performance ratios in [Kalibera and Jones, *Quantifying Performance Changes with Effect Size Confidence Intervals* (2012)](https://www.cs.kent.ac.uk/pubs/2012/3233/). Our limited retrospective comparison does not implement their full experimental designs. A stronger follow-up would repeat independently launched processes and interleave versions under controlled machine conditions, while retaining the pinned historical results.

OWL RL counts additional schema and axiomatic triples, so its total closure count is not directly comparable to the DLP store. Within a given implementation/case, unchanged closure counts are checked across versions; different stored auxiliary representations would require an explicit explanation rather than a silent comparison.

## Supplemental paired replay

To investigate historical-run regressions without replacing the fixed reference:

```sh
.venv/bin/python scripts/replay_b1254c4.py --timeout 300
```

Run this after other benchmarks finish. The driver extracts the exact `b1254c4`
sources into an ignored temporary directory and verifies their hashes and Python
import locations. Seven selected workloads each run in five baseline/current
pairs: 35 pairs and 70 independent workers, one repetition per worker, alternating
AB/BA order and using the same explicit hash seed within each pair. They cover
transitivity, cardinality, existentials, the widest union, a taxonomy, and small
and large maintenance cases. Input hashes must still match the pinned report;
closure counts, expected answers, and update checks must agree.

The separate [replay report](replay-results.md) and [raw replay data](replay-results.json)
retain both new sample sets, execution order, source/driver hashes and paired
descriptive resampling intervals. These intervals resample paired observations
together, unlike the unpaired retrospective full-run comparison. Five pairs
remain limited evidence and do not control every source of machine noise. The
driver protects both the pinned reference and the recorded full-run outputs;
the supplemental measurements never become the default baseline automatically.
