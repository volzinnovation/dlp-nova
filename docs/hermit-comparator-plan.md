# Finite L3 task comparison with a broader OWL reasoner

This is an original controlled experiment addressing computational value for a
stated fragment. It is not an established corpus benchmark, a prevalence study,
or a comparison of full internal materializations.

## Exact task and independent expected answers

All arms receive identical RDF/XML bytes containing the fixed TBox

\[
A\sqsubseteq\exists R.B,\qquad \exists R.B\sqsubseteq C
\]

and `N` named individuals asserted to belong to `A`, for
`N = 100, 1000, 10000`. One further named individual belongs only to `B`.
An unrelated class `D` is declared. Each worker must establish consistency,
return exactly the `N` named `A` individuals as `C` instances, and return no
entailed `D` instances. The B-only individual must not appear in the C answers.
An empty certain-answer set for D is not a claim that every individual belongs
to the complement of D.

The expected result follows independently from the two GCIs: every A individual
has some R-successor in B and therefore belongs to C. For the negative control,
construct a model with all A individuals in C, one shared B witness reached by
every A individual, the B-only control outside C, and D empty. This satisfies
the ontology, establishes consistency, and shows that neither the B-only C
answer nor any D answer is entailed. Dropping either GCI permits a model with
C empty. Small tests exercise these two counterfactual omissions.

The TBox implies `A ⊑ C`. Both existential axioms are essential to this
entailment, but **explicit witness construction is not necessary** to answer
the query. HermiT is allowed to use normal classification, blocking and
realization. The DLP implementation may materialize witnesses. No adapter
rewrites the TBox to `A ⊑ C`, and no equivalence between witness stores is claimed.
RDF-based subclass propagation can also answer C for this particular shape,
despite its existential consequent being outside structural OWL RL. This
experiment therefore tests a particular correct algorithm/task pairing, not
the necessity of witness construction or strict separation from every RL rule
implementation.
The same ontology family is also in OWL 2 EL, whose grammar permits these
existential class expressions and subclass axioms. A result against HermiT
therefore does not establish superiority over specialized EL implementations.
[W3C OWL 2 profiles, Sections 2.1–2.2](https://www.w3.org/TR/owl2-profiles/#OWL_2_EL).

## Three-arm protocol

The arms are immutable `b1254c4`, the exact candidate already measured in the
ZodiacEdge experiment, and pinned HermiT. The candidate is reconstructed from
`benchmarks/followup-source.tar.gz` and its per-file hash manifest. Three process
blocks, three populations and three arms produce 27 fresh workers. Arm order
rotates by block and population position. All source, dataset and Java bytecode
hashes are recorded before timing. Unsupported inputs, inconsistent results,
wrong answer tuples and resource limits are failures, not timed successes.

The measured task is loading plus reasoner construction plus consistency plus
fully consumed C and D queries, in that order. Phase times are separate;
their sum is the comparable task time. A fresh-subprocess timer additionally
includes runtime startup, output serialization and process exit. Input generation,
dependency preparation and Java compilation are excluded. Python's eager
materialization and HermiT's lazy work make constructor-only ratios misleading.
HermiT uses `-Xms64m -Xmx2g`; this is a JVM heap configuration, not a measured
memory advantage. Both engines otherwise retain normal execution behavior.

The Java API adapter is `benchmarks/OwlBridge.java`; the coordinator is
`benchmarks/owl_bridge.py`. No production dependency is installed. Compilation,
semantic preflight and all timed workers ran after the TPC-H and native
ZodiacEdge windows finished, with other timed work idle.

## Distribution feasibility and provenance

OpenJDK and javac 17.0.18 are already available. No Maven executable or existing
OWLAPI Maven cache was found. The preferred comparator is the published
**OWLAPI-maintained HermiT 1.4.5.519 fork with OWLAPI 5.1.9**. Eleven top-level
Maven artifacts are SHA-256 pinned in `benchmarks/hermit-dependencies.json`.
Their bundled dependency jars are extracted from those verified bytes and
individually hashed in the protocol. The coordinator constructs an explicit
plain-JVM classpath; no Maven invocation or production dependency is needed.
HermiT's normal reasoner factory is retained. The fork's POM says explicitly
that it is not officially supported by the original HermiT developers.

As a fallback investigated before this classpath was assembled, Owlready2's
official 0.51 source distribution
contains a standalone modified HermiT jar with all required OWLAPI classes.
The bundled version is **HermiT 1.3.8.1099 / OWLAPI 3.4.3**, not a recent HermiT
release. HermiT's bundled readme states LGPL-3.0-or-later; other included
libraries have their own licenses. Distribution and license files remain in
ignored `tmp/owl-bridge`; they are not vendored into the production package.
[Owlready2 reasoning documentation](https://owlready2.readthedocs.io/en/latest/reasoning.html),
[official package](https://pypi.org/project/owlready2/0.51/).

The verified source archive SHA-256 is
`65adebc79ff6abdd2a0bde8d3aac21c6beed8699bf1e7c849d30eba9c513795e`;
the extracted jar SHA-256 is
`97e53f519720a0a2e328556e03b806aa239347c85e57637a935e6433ed2ad3a8`.

A bounded newer-release check found that the upstream `com.hermit-reasoner`
Maven coordinate ends at 1.3.8.4 (metadata last updated in 2014). The
OWLAPI-maintained `net.sourceforge.owlapi` coordinate ends at **1.4.5.519**
(2020), using OWLAPI 5.1.9. Its POM explicitly identifies it as a fork supporting
newer OWLAPI versions, not officially supported by the original HermiT developers.
The newer published jar and OWLAPI OSGi bundle have been inspected read-only;
their additional published classpath dependencies are pinned in the lockfile.
Java compilation and semantic smoke checks succeeded. Selecting this fork
preserves its provenance rather than calling it a recent
original-author standalone release.
[Upstream metadata](https://repo.maven.apache.org/maven2/com/hermit-reasoner/org.semanticweb.hermit/maven-metadata.xml),
[OWLAPI fork metadata](https://repo.maven.apache.org/maven2/net/sourceforge/owlapi/org.semanticweb.hermit/maven-metadata.xml),
[fork POM](https://repo.maven.apache.org/maven2/net/sourceforge/owlapi/org.semanticweb.hermit/1.4.5.519/org.semanticweb.hermit-1.4.5.519.pom).

The jar's `Bundle-Version` and Maven `pom.properties` both identify version
1.4.5.519; `Implementation-Version` is `1.4.5.519.2020-02-18T20:48:14Z`.
However, its `getReasonerVersion()` returns **1.4.1.513**. Read-only bytecode
inspection confirms that the pinned jar's `Reasoner` static initializer
constructs `Version(1, 4, 1, 513)`. This is a discrepancy inside the published
artifact, not evidence that a different jar ran. The unmodified reported
string is retained in every Java worker record. The distribution is identified
by its Maven coordinate and SHA-256; the API-reported string is also disclosed.

## Completed results

All 27 measured workers agreed with the independently justified exact named
answers and consistency result. All nine separate preflight processes also
passed the full input and each omitted-GCI control on all three arms. Ten small
Python tests passed, including the semantic controls and dependency tampering
check. No source, input or classpath drift, timeout or failed worker occurred.
The measured worker series lasted 18.18 seconds; compilation and preflight are
outside that interval.

| N | b1254c4 task median (s) | Candidate task median (s) | HermiT task median (s) | Candidate/HermiT paired task ratio | Candidate/HermiT paired process ratio |
|---:|---:|---:|---:|---:|---:|
| 100 | 0.010029 | 0.009945 | 0.220450 | 0.046429 | 0.379001 |
| 1,000 | 0.086836 | 0.083865 | 0.318659 | 0.262592 | 0.475576 |
| 10,000 | 1.016922 | 0.937498 | 2.475294 | 0.378055 | 0.415056 |

The candidate/b1254c4 paired task ratios are respectively 0.985908, 0.965185
and 0.950003. Three process blocks describe observed variation; they do not
support a broad statistical population claim. Ratios are the median of the
within-block ratios, so they need not equal the ratio of two marginal medians.
At N=100, HermiT loading dominates its task time. At N=10,000, its median
consistency and positive-query phases take approximately 1.176 and 0.903
seconds, respectively. Constructor-only comparisons would therefore omit
substantial HermiT work. Full process ratios retain startup, answer
serialization and process exit for all implementations.

The data are in `benchmarks/owl-bridge-results.json`; the protocol was written
before timing to `benchmarks/owl-bridge-results-protocol.json`. The nine
preflight outcomes are in `benchmarks/owl-bridge-smoke.json`. This family shows
an observed advantage for the measured DLP implementations on a correct task
with existential axioms, under the stated conditions. Most of the advantage
over this HermiT artifact is already present in b1254c4; it should not be
attributed entirely to the new candidate optimizations.

Any result applies to the pinned implementations, runtimes, ontology family
and stated operation. It supplies no corpus-prevalence estimate, no generic
asymptotic separation, and no claim about the latest full-OWL performance
frontier. Demonstrated speed on the same correct task can still establish
computational value for that task, independently of prevalence.

The algorithmic reference is Birte Glimm, Ian Horrocks, Boris Motik, Giorgos
Stoilos and Zhe Wang, *HermiT: An OWL 2 Reasoner*, Journal of Automated Reasoning
53(3):245–269 (2014), DOI 10.1007/s10817-014-9305-1.
[Author-hosted article](https://www.cs.ox.ac.uk/people/boris.motik/pubs/ghmsw14HermiT.pdf).
