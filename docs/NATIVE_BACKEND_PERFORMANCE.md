# Persistent C++ backend: matched public API measurements

This experiment compares the production Python backend with the optional
persistent C++ relation and join backend through the same `Reasoner` API.
The parser, OWL compiler, equality reasoning, witness construction, constraints,
completeness limits and update policy remain Python responsibilities.
The C++ backend stores integer relations and evaluates positive relational joins;
it does not implement an independent complete OWL reasoner.

On the recorded host, the native backend reduced the median construction time
of the 100-edge transitive workload by about 6%, while construction was slower
for taxonomy, equality and both Bach workloads. The result supports keeping the
backend optional. The earlier isolated kernel's much larger ratios do not carry
over to these complete public API operations.

The harness is [`benchmarks/native_backend.py`](../benchmarks/native_backend.py).
Its [raw observations](../benchmarks/native-backend-results.json) are separate
from the earlier [isolated join experiment](NATIVE_PERFORMANCE.md), whose source,
results and interpretation remain unchanged.

## Reproduction and measurement boundaries

```sh
PYTHONHASHSEED=0 uv run python -m benchmarks.native_backend --repeats 5 \
  --output /tmp/dlp-native-backend-results.json
```

The harness accepts three to five paired repetitions and requires a C++17
compiler. Building and loading the initial native library occur before timing;
the compiler manifest, flags and library hash are recorded. One discarded,
validated construction/query warm-up runs on each backend for each workload.
Python runs first on even-numbered repetitions and C++ first on odd-numbered
ones. Updates use the same alternating order and always start from a fresh
materialization of the original asserted graph. There is no separately discarded
update warm-up.

The retained workloads use the existing generators unchanged: taxonomy depth 5,
nine individuals per non-root class, P1 properties; a transitive chain of 100
edges; 300 equality groups; and the separate chapter 2 and chapter 6 Bach inputs.
The Bach inputs use the new DLP serialization and existing query manifest, with
source hashes recorded. Parsing and graph construction precede timing.

`construct_seconds` measures the complete `Reasoner(graph, backend=...)` call,
including graph copy, OWL compilation, Engine construction and materialization.
The separately recorded `compile_seconds` is the reasoner's ordinary compiler
measurement. `engine_materialize_seconds` is its ordinary `materialize_seconds`:
it includes Engine construction and cached native-context setup, followed by
fixed-point reasoning. These boundaries differ from the earlier microbenchmark's
isolated kernel and its Engine-only profiles.

Queries use the public APIs. All existing Bach manifest queries are retained,
including temporary reasoning needed for schema or expression probes. Taxonomy
queries retrieve the root's instances, transitivity queries retrieve the first
node's property values, and equality queries retrieve B instances and an alias's
type. Query time includes these operations but excludes answer validation.

`update_seconds` measures the complete `Reasoner.update` call, including candidate
graph construction, recompilation, and incremental maintenance or rematerialization.
Initial setup for each transaction and validation afterward are excluded.
The report keeps every measured sample, backend order, phase duration, update
method, native counter and closure digest.

## Recorded observations

The run completed on 10 September 2026 in Europe/Berlin (9 September,
22:35:06–22:36:47 UTC), using an Apple M4 Max, macOS 26.5.1, Python 3.12.9,
RDFLib 7.6.0 and Apple Clang 21.0.0. The library used
`-O3 -std=c++17 -DNDEBUG -shared -fPIC`. Each entry below is the median of five
measured repetitions, in milliseconds. Ratios divide the Python median by the
native median: above 1 favors native; below 1 favors Python. All workloads and
transactions are shown, including slowdowns.

| Workload | Closure facts | Python construction ms | Native construction ms | Ratio |
| --- | ---: | ---: | ---: | ---: |
| Taxonomy, depth 5 / 9 individuals / P1 | 22,393 | 251.682 | 262.408 | 0.959× |
| Transitive chain, 100 edges | 5,152 | 459.913 | 430.878 | 1.067× |
| Equality, 300 groups | 1,801 | 46.500 | 67.738 | 0.686× |
| Bach, chapter 2 | 99 | 4.877 | 6.431 | 0.758× |
| Bach family, chapter 6 | 58 | 1.102 | 1.615 | 0.682× |

The public construction measure includes graph copying and compilation. The
engine/materialization and public-query portions were:

| Workload | Python engine ms | Native engine ms | Engine ratio | Python query ms | Native query ms | Query ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Taxonomy | 150.140 | 184.748 | 0.813× | 7.254 | 7.179 | 1.011× |
| Transitive | 458.140 | 429.129 | 1.068× | 1.427 | 1.472 | 0.970× |
| Equality | 33.141 | 54.334 | 0.610× | 1.485 | 1.461 | 1.017× |
| Bach, chapter 2 | 1.590 | 3.125 | 0.509× | 40.720 | 49.607 | 0.821× |
| Bach family, chapter 6 | 0.593 | 1.103 | 0.538× | 3.132 | 4.214 | 0.743× |

The unchanged compiler's phase samples are retained in the raw report. Medians
of phases need not sum to the median of the complete operation. Bach's query
suite includes temporary reasoning for expression and schema probes, so its
query time can exceed one initial materialization.

| Workload / independent transaction | Maintenance method | Python update ms | Native update ms | Ratio |
| --- | --- | ---: | ---: | ---: |
| Taxonomy: move one asserted type | DRed | 127.846 | 136.201 | 0.939× |
| Taxonomy: delete one subclass rule | DRed rules | 136.386 | 138.682 | 0.983× |
| Transitive: replace one asserted edge | DRed | 685.487 | 627.414 | 1.093× |
| Transitive: delete transitivity rule | DRed rules | 1,103.464 | 1,029.852 | 1.071× |
| Equality: retract one alias's key | Rematerialize | 61.712 | 50.222 | 1.229× |
| Equality: delete inverse functionality | Rematerialize rules | 24.205 | 27.222 | 0.889× |
| Bach: retract Genius assertion | Rematerialize | 4.765 | 5.638 | 0.845× |
| Bach: delete ancestor/dynasty inclusion | Rematerialize rules | 4.585 | 5.572 | 0.823× |
| Bach family: original fact replacement | DRed | 1.045 | 1.186 | 0.881× |
| Bach family: original rule deletion | DRed rules | 0.728 | 0.823 | 0.884× |
| Bach family: original symmetry insertion | Incremental rules | 0.843 | 0.952 | 0.886× |

The transitive construction samples ranged from 453.415–465.538 ms for Python
and 422.654–507.926 ms for native. Equality construction ranged from
46.029–48.016 ms for Python and 51.025–75.673 ms for native. This variability
limits interpretation of small ratios, including apparent update improvements;
the samples do not establish statistically reliable wins.

The counters explain one important boundary. Taxonomy executed zero native
join queries because its existing unary specialization handles the rules,
while native storage still received 22,393 rows. The first transitive repetition
executed 16 native join queries and returned 194,556 bindings; Python still
constructed heads and ingested their consequences. Full and delta stores
together received 10,304 rows for the 5,152-fact closure. This is a staged
relation/index implementation, and further speedups would require profiling
and reducing the remaining orchestration and object-construction work. These
observations do not justify a Go or assembly throughput claim.

## Correctness and provenance

Every pair must be complete and consistent and export isomorphic RDF graphs,
including all schema and existential witnesses. Blank-node identities may vary;
their relationships and multiplicities must agree. Every update additionally
matches a fresh Python rebuild of the independently edited input graph.

Independent checks enumerate taxonomy ancestry and class membership, traverse
transitive and Bach-family graphs, and check expected equality groups. Original
Bach answers must match the existing source-backed query manifest. Chapter 6
fact replacement, rule deletion and symmetry insertion remain separate
transactions from the original input.

Source hashes cover the reasoner modules, C++ source/header, this harness,
workload generators, native regression tests and Bach inputs. Any source change
during the run aborts report retention. The report records UTC timestamps,
Python/RDFLib versions, operating system, CPU, hash seed, garbage-collector
settings and the native compiler manifest. Output protection prevents replacing
historical baseline evidence or an unrelated existing file.

The regression tests in
[`tests/test_native_backend.py`](../tests/test_native_backend.py) also compare
finite positive programs with an exhaustive assignment oracle; exercise random
fact/rule transactions, equality splitting, datatype value identity, Skolem
congruence, constraints, rejected transactions and limits; and check persistent
store identity, unchanged-relation transfer counts, cursor invalidation and
bounded streaming of large Cartesian products.

## Limitations

This is one process on an uncontrolled workstation. Alternating order does not
control background load, CPU frequency, thermal state or garbage collection.
Repeated samples are not independent host runs, and the report supplies no
confidence interval or production throughput guarantee. Memory consumption is
not measured. Native and Python iteration orders may differ, especially for
resource-limited prefixes; completed materializations must retain the same
semantics.

The native backend still crosses Python boundaries to construct heads, ingest
facts and coordinate rounds. Unary specializations and equality/inequality
evaluation can use existing Python paths. Native storage therefore adds overhead
on workloads that perform little suitable join work. A speedup on one workload
does not justify changing the default backend or projecting the earlier
microkernel ratio onto the complete reasoner.
