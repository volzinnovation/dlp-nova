# Native execution: profiling and bounded feasibility experiment

A C++ execution core is a plausible next optimization, especially for relational
joins and fact ingestion. A language change alone does not establish a speedup:
the engine also spends time hashing RDF terms, building indexes, canonicalizing
equality, and constructing result objects. The initial experiment here measures
one positive binary join; it does not implement or time a complete native DLP
reasoner.

The prototype and harness are isolated in
[`native_join.cpp`](../benchmarks/native_join.cpp) and
[`native_performance.py`](../benchmarks/native_performance.py). They do not change
the production backend, dependencies, or any prior benchmark results.

## Reproduce

From the repository root, with the locked development environment and a C++17
compiler (`clang++` or `g++`):

```sh
PYTHONHASHSEED=0 uv run python -m benchmarks.native_performance --repeats 7 \
  --output /tmp/dlp-native-performance.json
```

The harness compiles a temporary shared library with `-O3 -std=c++17 -fPIC
-shared`; compilation and dynamic loading are outside the runtime measurements.
It removes the temporary library on completion. `--compiler` can select another
compiler. It uses Python's standard-library `ctypes`, with no added package.
Choose a new output path for another run, or pass `--overwrite` to replace a
prior report from this experiment. Other tracked files, non-report files,
symbolic/hard-link aliases and the immutable baseline directory are protected.

The saved [raw observations](../benchmarks/native-performance-results.json)
include every sample, source hashes, compiler/version/flags, Python and RDFLib
versions, CPU/OS, hash seed, garbage collector settings, checkout state, input
and output digests, validation results, and the largest profile entries. Hashes
of the measured implementation and experiment sources must remain unchanged
throughout the run.

## Measurement boundaries and correctness

The real-engine profiles cover three existing workloads: taxonomy depth 5 with
9 individuals per non-root class and P1 properties, a 100-edge transitive chain,
and 300 equality groups. Graph generation, OWL compilation and `Engine`
construction precede the timer; `materialize()` is timed directly. Each case
has seven ordinary measurements plus one separate `cProfile` run, and all
closures must be identical, complete and consistent. The transitive closure
also matches an independent enumeration of every reachable pair. There is no
discarded warm-up for these engine measurements. Profiling adds substantial
overhead: use the ordinary measurements for latency, and profile entries only
to locate work. Nested cumulative profile times must not be added.

The join prototype computes the projected set for
`left(x,y), right(y,z) -> result(x,z)`. Both implementations receive identical
32-bit integer term identifiers, build a hash index on the right relation,
enumerate candidates, deduplicate packed `(x,z)` pairs in a hash set, and sort
the result. The Python comparison is a dedicated equivalent kernel, **not** the
production engine's complete join interpreter. The C++ implementation uses
standard-library containers; container implementations and allocation behavior
are part of the comparison. Neither implementation uses hand-written assembly,
parallel execution, or persistent indexes.

The chain-frontier snapshots join the adjacent edges with the complete chain
closure. The dense snapshot joins the closure with itself. These are synthetic
relations shaped like inputs to a transitive rule; they are not a recorded
sequence of semi-naive rounds. For `n` adjacent edges, the frontier case visits
`n(n-1)/2` candidates; the dense case visits `(n+1)n(n-1)/6`, including duplicate
projected results. Each returns exactly the pairs at distance at least two.

Each join case has one discarded warm-up per implementation and seven measured
repetitions. Python runs first on even-numbered repetitions and C++ first on odd
ones. Validation follows each timed result and is outside the timing. The
complete RDF pair sets must equal the independently enumerated chain answer.
An additional 105 deterministic small cases check both kernels against a nested
loop oracle, covering empty relations, duplicates, skew, no matches, and maximum
32-bit IDs. This establishes the prototype's measured operation; it does not
establish DLP semantics for a native backend.

The raw report separates:

- RDF term dictionary construction and integer encoding, common to both paths.
- Transfer of Python integer pairs into contiguous native input buffers.
- The Python or C++ kernel, including index construction, set projection and
  output sorting. The native measurement includes the C ABI call and native
  allocation; internal index/set destruction occurs before it returns.
- Copying the native output into a Python list and freeing its native buffer.
- Decoding integer pairs back into RDF term pairs on each path.
- The complete RDF snapshot operation, which sums the above applicable phases
  for each repetition before calculating its median.

Both paths exclude later destruction of their returned Python outputs. RDF
parsing, ontology compilation, fixed-point evaluation, head construction,
insertion into the reasoner's fact indexes, equality, constraints, Skolem
witnesses, queries, and incremental maintenance are outside the join experiment.
The complete RDF snapshot timings therefore remain **join-operation timings**,
not whole-engine timings.

The repetitions share one process and host, retain normal Python garbage
collection, and do not control background load, CPU frequency, or thermal state.
The harness alternates execution order but does not provide independent-run
confidence intervals or a production performance guarantee. It does not measure
memory consumption. A positive result is grounds for another measured
implementation step, not a claim that all workloads improve by that factor.

## Observations on the measured host

The run finished on 10 September 2026 local time (9 September 22:17 UTC), on
an Apple M4 Max with macOS 26.5.1, Python 3.12.9, RDFLib 7.6.0 and Apple Clang
21.0.0. The recorded checkout is `b3d036c0ab05780a5137b9eeaab17817ce2a675e`
with working-tree changes; exact measured source hashes are in the JSON.
Values below are medians of seven repetitions, in milliseconds.

| Join snapshot | Candidate pairs | Output pairs | Python kernel ms | C++ kernel ms | Kernel ratio | Python RDF operation ms | C++ RDF operation ms | RDF operation ratio |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Chain frontier, 128 edges | 8,128 | 8,128 | 2.137 | 0.533 | 4.01× | 4.006 | 2.915 | 1.37× |
| Chain frontier, 768 edges | 294,528 | 294,528 | 82.394 | 18.791 | 4.38× | 170.420 | 131.770 | 1.29× |
| Dense chain, 128 edges | 349,504 | 8,128 | 34.011 | 1.413 | 24.07× | 36.576 | 5.033 | 7.27× |

Ratios divide the Python median by the corresponding C++ median. In the large
frontier snapshot, common RDF encoding cost 29.048 ms, native input transfer
19.248 ms, native output copy/free 3.438 ms, and RDF decoding 59.685 ms on the
Python path versus 60.964 ms on the native path. The transfer and reconstruction
costs substantially reduce the observed benefit. The dense case does more
join work per returned pair and benefits more. These values favor keeping
encoded relations in native memory between calls, subject to validation in an
actual evaluator. Medians of phases need not sum to the median of total time.

| Actual engine workload | Closure facts | Unprofiled materialize ms | Main work in the separate profile |
|---|---:|---:|---|
| Taxonomy, depth 5 / 9 individuals / P1 | 22,393 | 197.932 | Ingestion, fact storage, canonicalization and index updates |
| Transitive chain, 100 edges | 5,152 | 742.552 | Join traversal, head construction and term binding |
| Equality, 300 groups | 1,801 | 33.143 | Ingestion, canonicalization, equality representative lookup and joins |

The ordinary transitive samples ranged from 571.320 to 1,136.770 ms in this
run. That variation reinforces the limitation of an uncontrolled workstation
measurement; these profiles identify work to optimize, not stable throughput.

For the profiled transitive case, positional `solutions()` accounted for
0.814 s cumulative within 1.941 s for `materialize()`, while `_heads()` accounted
for 1.509 s including its nested join work. For taxonomy, `_ingest()` accounted
for 0.468 s within 0.692 s. Equality's `_ingest()` accounted for 0.055 s within
0.097 s. This mix is why a join-only port cannot be expected to deliver the
same improvement across all programs. The profiling times include profiler
overhead and are not performance baselines for the native kernel.

## Porting decision

**C++:** Start with a bulk integer relation/index layer and positive rule
evaluation, while preserving the Python parser/compiler/API and existing
semantic tests. Keep data and indexes in native memory across rule firings;
crossing the boundary for individual atoms or rebuilding buffers each time can
consume the gain. An integer dictionary must preserve RDF term identity,
supported datatype equality, and changes of individual representatives. A
later native evaluator must also preserve completeness limits, constraints,
existential witnesses, and maintenance behavior. Python officially supports
[C/C++ extensions and C-library interfaces](https://docs.python.org/3/extending/extending.html);
that integration path supports a staged experiment without a whole-program
rewrite. This recommendation is an engineering inference from the local
profiles and experiment, not an external performance guarantee.

**Go:** A viable compiled implementation language, especially if an independent
service is wanted. It still needs deliberate term encoding, efficient relation
storage, join planning and allocation control. The official
[Go garbage collector guide](https://go.dev/doc/gc-guide) explains the CPU/memory
tradeoff and why allocation rate matters. Go was not installed on the measured
host; no Go executable, kernel, or speedup was tested. These observations do not
rank Go versus C++ throughput.

**Assembly:** Do not begin with a whole-engine assembly port. The measured work
is dominated by joins, hashing, indexing and object handling; improve those
representations first. LLVM already provides
[loop and straight-line vectorization](https://llvm.org/docs/Vectorizers.html).
If a future contiguous bitmap or sorted-integer kernel remains important after
native profiling, inspect compiler output and measure portable intrinsics or a
small architecture-specific routine. No assembly speedup has been measured
here, and compiler vectorization does not imply that the current hash-based
join is vectorized.

The next decision should depend on a native prototype completing the existing
semantic and incremental-update tests, followed by the same unchanged Bach,
taxonomy, transitive, equality, existential, and maintenance workloads with
separate compile/materialize/query timings. Amdahl's law also limits any narrow
port: accelerating fraction `f` of a complete operation by factor `s` gives at
most `1 / ((1-f) + f/s)` overall before conversion costs. A kernel ratio cannot
be substituted for a measured value of `f` in the whole reasoner.
