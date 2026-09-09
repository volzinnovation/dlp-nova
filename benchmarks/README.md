# Benchmark methodology

Run from the repository root with the locked development environment:

```sh
uv run python -m benchmarks.run --suite thesis --repeats 5 --output /tmp/dlp-results.json
```

The runner writes JSON after every case and derives an adjacent Markdown report. Each case runs in a separate Python subprocess with a configurable wall-time limit (180 seconds by default). A timeout, mismatch or error is recorded and makes the runner exit unsuccessfully. Five repetitions occur within the worker; there is no discarded warm-up. Generation and N-Triples serialization are outside the timed phases. Parsing, compilation and materialization are separate, measured with `time.perf_counter`. Instance queries run against the materialized store. TBox subsumption includes an isolated probe recompilation and materialization. Full raw samples, median, mean, spread, counts and process peak RSS are recorded.

The input hash covers sorted N-Triples. Generators use fixed IRIs, fixed blank-node labels for existential inputs, and seed 2004. Peak RSS is the process high-water mark, including input graphs, parser, retained objects and previous repetitions; it is not the engine's isolated allocation. Values are normalized to bytes on macOS and Linux. Workloads run sequentially. Package versions, platform, architecture and CPU count are saved.

## Cases and deviations from the thesis

- **Taxonomy:** the complete 27-case matrix uses branching factor 3, depths 3/5/7 (40/364/3280 classes), 3/9/15 individuals per non-root class, and P0/P1/PF property variants from thesis Tables 8.4–8.6. P1 creates one property per class and a filler on each third individual. PF declares 200 properties and picks one uniformly per individual. Property targets use the previous generated individual, with a fixed initial target. The generator omits the additional ontology-library-derived class restrictions used in other thesis experiments.
- **Queries:** repeated root instance retrieval and a fixed property pair query provide stable, analytically checkable workloads, rather than the thesis's random query selection. Named subclass probes verify the deepest class is subsumed by the root. The root instance count and all generated class-fact counts have independent arithmetic expectations.
- **Equality:** inverse-functional keys identify 100 and 1,000 pairs of named aliases. Both aliases must inherit their class memberships. This isolates inferred equality; it does not reproduce the thesis's exact max-one constructor distribution.
- **Existentials:** 100 named roots generate four acyclic levels of witnesses. The final level must contain exactly 100 witnesses. Cyclic witness bounds are unit-tested, not presented as a completed timing benchmark.
- **Transitivity:** a chain of 100 edges must yield exactly 5,050 reachable ordered pairs.
- **Maintenance:** a five-way depth-4 taxonomy has five individuals per non-root class. Remove 10% of assertions, insert an equal number of new assertions, add and remove a rule, checking equality with a fresh closure after each operation. Deletion, insertion, rule insertion and full-rebuild times are separate. This is one representative setting, not all of the thesis's depth/ratio combinations.
- **Comparators:** a small depth-3/3-individual/P0 case runs the naive engine and the external `owlrl` OWL RL materializer. OWL RL performs additional schema/axiomatic inference, so total closure counts and workload scope differ. The root's named instance answer is checked against the same expectation. Naive and semi-naive share the compiler and equality code; independent semantic oracles are in the test suite.

No comparison with the thesis's historical millisecond figures is meaningful: both hardware and measurement boundaries differ. The implementation does not claim the thesis's exact quartic data-complexity bound for every accepted rule shape, nor a production performance guarantee. Measurements characterize these deterministic workloads on the recorded machine.
