# Query caching and indexed retrieval: measured results

This report compares the preserved implementation before query optimization,
the updated implementation with answer caching disabled, and the updated
implementation with its bounded answer cache enabled. The Python and native
backends are measured separately. Initial computation and repeated answers have
different measurement boundaries.

Repeated cached suites took 0.005–0.058 ms in this run, after their answers had
been computed, compared with 2.375–36.351 ms before the changes. Indexed queries
also helped without answer caching: repeated taxonomy queries improved by
7.28× on Python and 7.80× on native. First-query and construction measurements
below show the separate costs and regressions; the warm ratios do not describe
initial reasoning speed.

The [harness](../benchmarks/query_performance.py),
[raw observations](../benchmarks/query-performance-results.json), and
[source-only baseline archive](../benchmarks/query-baseline-source.tar.gz)
are new artifacts. Earlier native-backend and isolated-join reports remain
unchanged. See [QUERY_CACHING.md](QUERY_CACHING.md) for the implementation and
invalidation contract.

## Reproduce

```sh
PYTHONHASHSEED=0 uv run python -m benchmarks.query_performance \
  --repeats 5 --warm-loops 10 --output /tmp/dlp-query-performance.json
```

The baseline package was captured before implementation changes. The archive
contains its source files and a hash manifest. The harness verifies the files
and loads them under a separate package name, so their relative imports use
the original compiler, engine and reasoner while the current implementation
remains independently importable. Measurements can therefore alternate within
one process without changing the installed package. No executable is included
in the archive. Native sources are compiled through their ordinary cache before
query timing.

For each workload and backend, five repetitions rotate the order of three
modes. Each mode starts from a newly constructed reasoner:

- **Before:** the archived pre-change implementation.
- **Updated, cache disabled:** indexed retrieval and other query improvements,
  with `query_cache_size=0`.
- **Updated, cache enabled:** those improvements plus `query_cache_size=256`.

The **first suite** is measured once, without warming query answers. The
**repeated suite** immediately runs ten times; the elapsed block is divided by
ten, and the table reports the median of the five resulting per-suite means.
The raw report retains the complete block times, individual repetition order,
first-suite times, and cache counters. Construction/materialization is measured
separately and excluded from both query timers. Serialization and answer
validation are outside query timing.

## Workloads and validation

All 25 chapter 2 Bach manifest queries and all seven independent chapter 6 Bach
manifest queries are retained. Anonymous query expressions are parsed once
into stable expression nodes before each reasoner is built. Only their
structural expression triples are added; no query class definitions or new
individual assertions are installed. Repeated calls therefore refer to the
same expression, allowing the ordinary expression-query cache to be exercised.
The source manifest supplies the expected answers.

Taxonomy uses the unchanged depth-5 generator with nine individuals per
non-root class and P1 properties. Its eight queries cover four class instance
sets, an individual's types, one subject's property values, one property's
pairs, and a positive subsumption check. Expected class membership follows an
independent traversal of the generator's numbered tree.

The transitive workload uses the unchanged 100-edge chain. Its eight queries
cover values from four positions, every property pair, one individual's types,
transitivity and the first-to-last entailment. Expected property answers are
independently enumerated from chain positions.

For every mode and repetition, the first and final repeated suites are checked
against their complete expected answers. Intermediate repeated suites are
timed without per-loop validation. The three modes must produce identical
answer digests and isomorphic complete RDF materializations, including schema
and existential witnesses. Source hashes are checked before and after the run;
changing measured files aborts report retention.

## Observations

The retained run completed on 10 September 2026 in Europe/Berlin
(9 September, 23:07:37–23:08:31 UTC), on macOS 26.5.1 / arm64 with Python 3.12.9
and RDFLib 7.6.0, using `PYTHONHASHSEED=0`. The native build manifest records
Apple Clang 21.0.0. Values are milliseconds and medians of five repetitions.
Every case and mode is included.

**First query suite on a newly constructed reasoner:**

| Workload | Backend | Before ms | Updated, cache disabled ms | Updated, cache enabled ms |
| --- | --- | ---: | ---: | ---: |
| Bach, 25 queries | Python | 22.140 | 22.757 | 22.662 |
| Bach, 25 queries | Native | 28.199 | 28.084 | 27.789 |
| Bach family, 7 queries | Python | 2.354 | 2.384 | 2.464 |
| Bach family, 7 queries | Native | 3.134 | 3.482 | 3.459 |
| Taxonomy, 8 queries | Python | 22.920 | 9.977 | 11.550 |
| Taxonomy, 8 queries | Native | 37.243 | 12.722 | 18.912 |
| Transitive, 8 queries | Python | 13.561 | 9.726 | 11.231 |
| Transitive, 8 queries | Native | 12.225 | 9.163 | 11.457 |

**Repeated query suite, with unchanged input:**

| Workload | Backend | Before ms | Updated, cache disabled ms | Updated, cache enabled ms | Before / enabled ratio |
| --- | --- | ---: | ---: | ---: | ---: |
| Bach | Python | 23.314 | 23.349 | 0.01826 | 1,276.6× |
| Bach | Native | 28.790 | 28.604 | 0.01798 | 1,601.7× |
| Bach family | Python | 2.375 | 2.372 | 0.00517 | 459.3× |
| Bach family | Native | 3.236 | 3.090 | 0.00513 | 630.9× |
| Taxonomy | Python | 22.127 | 3.040 | 0.04535 | 487.9× |
| Taxonomy | Native | 36.351 | 4.663 | 0.04621 | 786.6× |
| Transitive | Python | 14.599 | 10.586 | 0.05765 | 253.2× |
| Transitive | Native | 13.145 | 9.759 | 0.05580 | 235.6× |

These large warm ratios reflect avoiding recomputation of identical answers.
They are measured through the normal query API, including revision checks,
guards and copying returned sets. They are not improvements to the underlying
fixed-point algorithm. The cache-disabled taxonomy improvement includes reuse
of the lazy reverse type index across queries; the first suite pays to build
that index.

**Construction and materialization, excluded from query timers:**

| Workload | Backend | Before ms | Updated, cache disabled ms | Updated, cache enabled ms |
| --- | --- | ---: | ---: | ---: |
| Bach | Python | 3.779 | 3.826 | 3.746 |
| Bach | Native | 5.242 | 4.908 | 4.827 |
| Bach family | Python | 0.907 | 0.866 | 0.842 |
| Bach family | Native | 1.418 | 1.246 | 1.202 |
| Taxonomy | Python | 215.822 | 224.313 | 228.051 |
| Taxonomy | Native | 331.654 | 308.453 | 344.583 |
| Transitive | Python | 391.505 | 422.699 | 347.584 |
| Transitive | Native | 337.184 | 338.085 | 337.427 |

Construction varied even between the two current modes, whose answer caches
were still empty during this phase. These measurements do not establish a
materialization speedup. The native taxonomy's cached first suite ranged from
12.709 to 65.727 ms; its median was 18.912 ms. Other cold regressions include
the native Bach-family suite, increasing from 3.134 to 3.459 ms.

Cache population has a measurable first-query cost for larger returned sets.
Relative to updated queries with caching disabled, the taxonomy cache added
1.572 ms to the median Python first suite and 6.190 ms to the median native
first suite, then saved 2.994 and 4.617 ms per repeated suite respectively.
Using those query-phase medians alone, one additional Python suite or two
native suites recover the initial cache-fill cost. This is an illustrative
same-instance crossover, not a confidence bound or a claim about construction,
updates, evictions or a different query distribution.

The first measured cached repetition on each backend recorded:

| Workload | Entries / initial misses | Hits after ten repetitions | Retained answer values | Estimated retained bytes |
| --- | ---: | ---: | ---: | ---: |
| Bach | 25 | 250 | 37 | 22,893 |
| Bach family | 7 | 70 | 15 | 6,807 |
| Taxonomy | 8 | 80 | 4,386 | 798,677 |
| Transitive | 8 | 80 | 5,204 | 863,083 Python / 851,806 native |

There were no evictions or bypasses in these suites. These are the cache's
conservative object-size estimates, not process resident-memory measurements;
the two transitive estimates reflect object/container representation details.
The configured bounds remained 256 entries, 50,000 returned values and 16 MiB
of estimated storage.

## Interpretation limits

Warm hits apply to repeated queries against unchanged state. They do not reduce
the work of the first entailment, first materialization or a genuinely new
query. Successful updates invalidate answer entries, and bounded caches can
evict or bypass answers. Returned sets are copied, so even a hit retains a cost
proportional to the number of returned elements.

The cache-disabled comparison isolates gains from query indexing and related
changes without attributing them to answer memoization. Construction timing
also exposes overhead from the new mutation tracking and cache setup. These
measurements do not establish faster ontology updates or faster rule execution.

This is a single process on an uncontrolled workstation. Rotating mode order
does not control thermal state, CPU frequency, garbage collection or unrelated
host load. Five repetitions provide observed variation, not independent-run
confidence intervals. The cache reports estimated retained answer sizes; the
experiment does not measure total process memory.
