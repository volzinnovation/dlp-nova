# Comparing the original Bach examples

The [results](../benchmarks/bach-external-results.md) extend the existing Bach
suite to HermiT and the actual, unchanged ZodiacEdge implementation. The
[independent source audit](bach-comparison-protocol-notes.md) records the
dissertation pages, logical interpretation, and expected answers.

The complete Table 2.5 ontology and the chapter 6 family example are separate
inputs. No facts from one are silently added to the other.

| Track | Questions | Compared systems |
|---|---|---|
| Complete ontology | All 25 existing questions, including existential expressions and schema entailment | Current, preserved b1254c4, HermiT |
| Family, from scratch | Seven existing questions plus complete ancestor and dynasty pair sets, in four states | All four systems |
| Family, incremental | Original state, one change, restoration; nine questions at every completed state | Current, preserved b1254c4, ZodiacEdge |

ZodiacEdge cannot directly execute the existential restrictions and constraints
of the complete OWL ontology. That cell is unsupported, not a zero-time result.
For the family it receives every logical axiom and assertion, translated into
positive binary rules and facts; the translator performs no inference.
HermiT computes each resulting family state from scratch. Its static times are
not presented as incremental maintenance times.

The four family states contain 24/24, 25/25, 24/0, and 24/48 complete named
ancestor/dynasty pairs, respectively: original, fact replacement, rule removal,
and symmetry addition. Each change starts from the original state. The fact
replacement is the dissertation's hypothetical withdrawal of Sebastian's
ancestry of Wilhelm Friedemann and insertion of his ancestry of Johann
Christian; it is not a historical claim about parentage.

Expected named answers exclude anonymous witnesses. Empty or false results
mean not entailed. The schema questions ask about universal logical properties;
the fact that a finite relation happens to be transitive is insufficient.
The Zodiac adapter answers them by fresh canonical facts and the unchanged
native rule engine, charging all probe preparation and reasoning to the query.

## Measurement and retained failures

Twelve blocks rotate engine order, using hash seeds 7100–7111. The eight jobs
produce 28 fresh processes per block, 336 overall. Only one worker executes at
a time. Input generation, dependency downloads, Java compilation, source
freezing, and untimed smoke checks precede the recorded series.

Static task times include RDF loading, query-expression preparation, necessary
representation conversion/indexing, reasoning, consistency where supported,
and complete sorted answers. Python expression queries require a temporary
graph and a query-specific reasoner; that work remains in the query interval.
HermiT may defer inference until an answer request, so construction alone is
not the compared outcome. Every phase is retained. Runtime/module startup and
native source verification are outside task times but inside separate process
wall times, together with validation, serialization and shutdown. Filesystem
caches are not cleared.

An incremental task includes the whole change application and all nine updated
answers; original-state setup is separate. ZodiacEdge exposes separate fact
deletion and insertion calls, so both are included without an intervening query.
The original state is then restored and checked. Every completed state is
checked against independently derived full answers; native closure checks also
compare all relation tuples. Count agreement alone is insufficient.

The upstream ZodiacEdge fact-replacement path was found to lose a conclusion
that remains supported through the other family branch for some hash seeds.
The run records failures rather than selecting passing seeds or modifying
upstream code. If any worker fails, its entire configuration/task is excluded
from timing rankings. Successful static reconstructions and other update tasks
remain separate evidence. This finding concerns the pinned implementation and
tested task; it does not establish a defect in every rule-maintenance method.

The preserved baseline commit is
`b1254c441731ca4fdf32ea83570ff99aaa84ac2a`. Its package is executed from an
isolated checkout snapshot. These are newly collected Bach measurements of
that implementation: its historical saved report contains no Bach cases and
is unchanged. Current package bytes and all measured RDF/XML inputs are
archived alongside the new protocol/results. Drivers, original sources, query
manifest, runtime artifacts and upstream source are identified by hashes.

The HermiT runtime is the pinned OWLAPI-maintained artifact
`net.sourceforge.owlapi:org.semanticweb.hermit:1.4.5.519` with OWLAPI 5.1.9.
Its API reports version 1.4.1.513; both identities are retained. ZodiacEdge is
the unchanged author revision `e15721161d1055f019c4b8f9ac1bd8648417f154`.
Fetched source and jars remain in ignored caches, not redistributed here.

## Reproduction

Use Python dependencies from the project and an available Java/JDK runtime.
Preparation verifies or downloads the already pinned external artifacts.

```sh
uv run python -m benchmarks.bach_external prepare
uv run python -m benchmarks.bach_external smoke
uv run pytest -q tests/test_bach_benchmark.py tests/test_bach_external.py tests/test_bach_zodiac.py
```

Then run in a quiet window, using an unused output directory. Preparation
freezes the current package before timing; reproducing the saved candidate
requires restoring the package bytes in `bach-external-source.tar.gz` into an
isolated checkout first. The archived RDF/XML files preserve exact input bytes;
fresh generation is also checked for RDF graph equivalence.

```sh
uv run python -m benchmarks.bach_external run --blocks 12 \
  --output tmp/bach-reproduction/results.json
uv run python scripts/build_research_report.py --check-bundle
```

The paper builder validates the preserved primary series without rerunning it.
It rejects changed protocol, package, input or driver hashes and checks every
saved successful answer, phase sum, complete block pairing and reported median.
These small original examples establish source fidelity and reveal overheads
and correctness failures. They are not a synthetic scaling experiment or a
replacement for LUBM or the larger published benchmark studies.
