# Persistent C++ relation/index backend

Select `backend="native"` or CLI `--backend native` to keep encoded relations,
tuple membership, and column indexes in C++ memory across rule firings.
Positive relational joins run in C++ and return bounded batches of bindings.
This is an optional stage of the reasoner, with the Python backend retained as
the default and comparison implementation.

```sh
uv run python -m dlp_reasoner.native --build
uv run dlp validate examples/family.dlp --backend native
uv run dlp validate examples/bach.dlp --profile L3 --backend native
uv run dlp values examples/bach-family.dlp \
  'http://www.jsbach.org/bach#johannes' 'http://www.jsbach.org/bach#ancestorOf' \
  --profile L0 --backend native
```

```python
from dlp_reasoner import Reasoner

reasoner = Reasoner.from_file("examples/family.dlp", backend="native")
print(reasoner.stats)
```

The same option is accepted by `Engine(program, backend="native")` and
`Reasoner.from_dlp(text, backend="native")`. Query probes and ontology updates
preserve the chosen backend. An unavailable native build is an explicit error;
the requested backend does not silently switch to Python.

## What runs where

| Responsibility | Implementation in this stage |
| --- | --- |
| Parsing DLP/RDF and compiling OWL axioms | Existing Python compiler |
| Stable predicate/individual IDs | Per-engine Python dictionaries using the original objects' equality and hashes |
| Tuple storage, membership, and column indexes | Persistent C++ relation store |
| Positive relational joins | C++ traversal with streamed binding batches |
| Optimized unary conjunctions | Existing Python set-intersection path, with unary row mirrors |
| Equality and explicit/known inequality | Existing Python normalization and built-ins |
| Head construction, constraints, Skolem witnesses, limits | Existing Python evaluator |
| Semi-naive rounds and DRed updates | Existing Python orchestration operating on native indexes |
| Public materialized/asserted facts and RDF exports | Existing Python representations |

`Engine.facts` remains the authoritative Python fact set. The native store is
its query index, not an independent source of truth. Unary and explicit equality/
inequality mirrors support existing specialized paths; positive binary and
higher-arity indexes stay in C++. The representation deliberately retains some
Python memory while moving the repeated join work across the language boundary.

The term dictionary retains IDs and their Python values for the lifetime of
its engine context, including retired terms. Deleting tuples frees their native
index entries but does not compact the dictionary. Reconstruct an engine when
reclaiming retired dictionary entries matters for a long-running workload.

The `naive` strategy uses the Python reference traversal over the selected
index. Equality/inequality bodies also retain that traversal. The experimental
Python query-order lookahead stays on its existing path when enabled. These
fallbacks preserve supported behavior and do not constitute a second native
implementation of those semantic algorithms.

## Persistence and semantic boundaries

Full and delta indexes share a term dictionary. Pending insertions are packed
in batches; positive joins reuse the native full relations and indexes instead
of transferring all RDF rows for each rule firing. A delta relation contains
only its frontier and replaces exactly the designated body occurrence, including
when the same predicate appears several times.

Repeated variables, constants, initial bindings, and zero/higher-arity predicates
retain their existing meaning. Constants are normalized again on each join
invocation, so cached plans cannot retain an obsolete equality representative.
Native IDs do not stringify RDF terms or assume that distinct IRIs denote
different individuals. Python remains responsible for supported literal value
identity and equality congruence.

Ordinary insertions extend the live index. Eligible small deletions remove the
affected tuples and column entries; larger deletions use the existing index
rebuild decision. Equality changes rebuild the index from canonical facts.
Equality or existential retractions retain the existing rematerialization path.
Rule updates replace plans without retaining old relation pointers.

Join output is streamed rather than fully materialized. The Python evaluator
can stop consuming bindings when its fact budget is reached, and unfinished
cursors release their native resources. A cursor detects relation mutations
before continuing rather than dereferencing invalidated iterators. The engine
is not a concurrently mutable database; callers should finish or close a query
before changing its underlying engine.

Rebuilding the engine's index closes the old native index as well, so suspended
queries cannot continue returning a previous materialization after a reset or
equality rebuild. A completed native closure has the same semantic answers as
the Python path; traversal order and the particular sound prefix retained at a
resource limit need not be identical.

The existing `max_facts`, `max_rounds`, and `max_depth` policies continue to
report incomplete reasoning. The native backend does not introduce a hidden
answer limit. Native allocation/build/ABI errors raise an exception instead of
being interpreted as an empty relation or completed closure.

## Building and deployment

The package ships C++ source and a C ABI header. Native selection compiles a
shared library with a local C++17 compiler and loads it through standard-library
`ctypes`; the Python backend neither loads nor builds this library. Builds use
a cache outside the installed package, keyed by source, platform, and toolchain
information, and publish completed libraries atomically. Compiler discovery and
failures are reported explicitly. Runtime compilation requires a writable cache
and the local toolchain; installing the Python package alone does not install a
compiler.

A compatible compiler must be discoverable when a process first selects the
native backend, even when reusing a library from a previous process: toolchain
identity is part of cache resolution. The current packaging does not provide
precompiled platform wheels.

Use `CXX` to choose a clang++/g++ compatible compiler command, and
`DLP_NATIVE_CACHE` to choose the cache directory. The build command also accepts
`--compiler` and `--cache-dir`. The default cache is under `~/Library/Caches`
on macOS or `$XDG_CACHE_HOME` / `~/.cache` on Linux. A warm engine initialization
reuses the resolved build in the same process without launching the compiler
again; changed source bytes, toolchain identity, or cache configuration
invalidate that resolution.

Execution statistics include `backend` and native counters. `native_rows_inserted`
and `native_rows_deleted` count applied tuples across all indexes, including
delta stores and rebuilds; they are not distinct logical fact counts.
`native_queries`, `native_batches`, and `native_bindings` measure native cursor
work. A cursor can prefetch up to 512 bindings before Python stops consuming,
so native binding counts can exceed the delivered `body_matches` at a limit.
`native_stores_live` and `native_active_cursors` are handle gauges at the point
the statistics are captured, not memory measurements.

Prebuild with `python -m dlp_reasoner.native --build` when separating compilation
from runtime matters. Compare both cold initialization and warm reasoning when
choosing an operational configuration. Compiler/build time is not a
materialization speedup. Packaged source makes a pure Python wheel usable with
either backend, but native compilation remains host-specific.

## Validation and performance

The [backend experiment](NATIVE_BACKEND_PERFORMANCE.md) compares actual Python
and native reasoning/updates on the same inputs and checks complete results.
It is separate from the earlier [isolated join prototype](NATIVE_PERFORMANCE.md),
whose measurements are preserved as historical feasibility evidence.

```sh
uv run pytest -q tests/test_native_backend.py
uv run pytest -q
uv run ruff check src tests benchmarks scripts
uv build
```

Tests compare native answers with Python and independent finite relation
oracles, including randomized updates, equality merge/split, literals,
existential witnesses, constraints, resource bounds, and native cursor lifetime.
Optional availability skips on machines without a compiler do not establish
native validation on those machines.
