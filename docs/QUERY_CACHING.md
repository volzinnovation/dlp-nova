# Querying a rarely changing ontology

Keep one `Reasoner` alive and issue queries against it. Construction compiles
and materializes once; repeated queries reuse the closure, relation indexes,
schema proofs and a bounded cache of completed answers. Both Python and native
backends use the same query cache.

```python
from rdflib import Namespace, RDF
from dlp_reasoner import Reasoner

F = Namespace("https://example.org/family#")
r = Reasoner.from_file("examples/family.dlp", query_cache_size=4096)

parents = r.instances(F.Parent)       # Compute and remember the answer.
parents_again = r.instances(F.Parent) # Return a fresh set from the cache.
assert parents == parents_again
print(r.query_cache_info)

r.update(add=[(F.new_composer, RDF.type, F.Composer)])
assert F.new_composer in r.instances(F.Person)  # Recompute after the update.
```

The default capacity is 256 entries per reasoner. `query_cache_size` changes
that limit; `0` disables answer memoization while retaining indexed lookups.
The cache also limits retained answers to 50,000 values and an estimated 16 MiB,
including keys and RDF values. It evicts the least recently used entries.
Oversized or unsupported values bypass caching and still return their complete
answers. The byte estimate is conservative accounting, not a process RSS limit.

`clear_query_cache()` releases stored answers and auxiliary query views without
recomputing the materialization. Existing valid schema proofs can remain.
`query_cache_info` reports hits, misses, evictions, bypasses, entries, values,
estimated bytes and limits. Counters are cumulative for the instance, including
across cache clearing. They are separate from `stats`, whose timings continue
to describe reasoning and maintenance.

## Cached queries and cold lookups

The cache covers boolean entailment/schema/satisfiability queries and set-valued
`instances`, `types`, `property_values` and `property_pairs`. Anonymous-expression
queries and fresh-individual queries cache their final answers; they do not
retain whole temporary reasoners. Original query identifiers remain distinct:
individual equality does not conflate class or property names.

Cached sets are immutable internally and copied on return. Mutating a returned
set cannot change later answers. Copying a large result still costs time
proportional to its size. Boolean hits avoid recomputation entirely.

On a cache miss, instance and property queries use the existing predicate and
column indexes. They no longer scan every materialized fact. `types` builds a
reverse unary-fact index once on first use; later calls reuse it for other
individuals. Source blank-node membership also has a lazy query view. These
views are additional memory proportional to the relevant ontology data and
are separate from the bounded answer-cache budget.

The first query may pay for a schema proof, temporary semantic probe, reverse
index or cache insertion. These changes target repeated querying rather than
claiming faster initial materialization. The
[query measurements](QUERY_PERFORMANCE.md) report first-use and warm timings
separately, including an answer-cache-disabled control.

## Invalidation and semantic guarantees

Consistency and completeness checks precede cache hits. Exceptions are never
memoized, and positive entailments from an incomplete live materialization are
not inserted as completed cached answers. Resource limits retain their existing
meaning; caching never turns an unknown result into a negative answer.

Successful `Reasoner.update` calls invalidate all answer caches and query views.
If the compiled rules are unchanged, the existing schema proof index is reused;
data-dependent probe answers are still discarded. An invalid candidate rejected
before mutation preserves the current cache. An exception after an engine
mutation also clears potentially stale answers and views.

Owned RDF graphs use an in-memory store with a mutation revision. Query hits
check it in constant time instead of hashing the whole ontology. This covers
`add`, `remove`, `set`, bulk insertion, parsing, SPARQL updates and direct store
writes, including same-size changes and partial failures. Engine updates and
rematerializations, graph replacement, profile changes and probe option changes
also invalidate cached answers. If `r.graph` is replaced with an arbitrary
external graph, an exact triple snapshot provides a conservative fallback;
that fallback scans the source graph on each query.

Direct graph edits can supply or revise anonymous query expressions, as before.
Use `Reasoner.update` to change ontology assertions or rules and synchronize the
materialization. Editing an internal fact/index container directly is not an
update API. Finish queries before mutating the reasoner; it is not a concurrent
transactional database.

Construct an anonymous query expression once and reuse its blank-node identifier.
Adding a fresh expression to the graph on every call advances the graph revision
and invalidates answers even when the new expression has equivalent meaning.

Caches live in the current Python process. Separate CLI invocations each build
a new reasoner and do not share query answers. A long-lived Python application
is the intended execution pattern for many queries against stable data.
