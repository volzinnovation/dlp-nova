# Related-work and contribution audit for the research report

Verified 9 September 2026. This is a targeted primary-source audit, not a
systematic review or a novelty certification. Sources were checked against
publisher, author, institutional-repository, and arXiv records. The inspected
local sources were `RESEARCH_EXPERIMENTS.md`, `RESEARCH_IMPROVEMENTS.md`,
`THESIS_SPEC.md`, `THESIS_ERRATA.md`, the thesis title page, and the unary
certificate implementation. No experiment was run for this audit.

## Original work and attribution

**Thesis.** Raphael Volz, *Web Ontology Reasoning with Logic Databases*,
dissertation, Universität Karlsruhe (TH), Fakultät für Wirtschaftswissenschaften,
2004; degree Dr. rer. pol.; oral examination 17 February 2004. The original
title page calls the institution Universität Fridericiana zu Karlsruhe.
The institutional catalogue lists XVI + 271 pages.
[Official record and DOI](https://publikationen.bibliothek.kit.edu/162004),
DOI **10.5445/IR/162004**. This is the appropriate `@phdthesis` source; do not
mistake the recent repository reconstruction for a publication by the original
thesis author.

Use printed thesis pages, with an explicit page-number convention. From
chapter 1 onward, one-based PDF page = printed page + 16. Relevant locations:

| Topic | Thesis location |
|---|---|
| Structural normalization | §4.3, pp. 83–87 |
| Four DLP fragments and translation | §5.1–5.2, pp. 115–123 |
| ABox/TBox queries, open-world semantics | §5.4, pp. 130–141 |
| Data-complexity result and L3 termination limits | §5.5, pp. 142–143 |
| Assertion/materialization distinction | §6.2.3, p. 152 |
| Fact changes | §6.3, pp. 152–158 |
| Rule changes | §6.4, pp. 159–165 |
| Prototype architecture | Chapter 7 |
| Historical evaluation | Chapter 8, pp. 193–223 |
| Historical measurement host | p. 198 |
| Taxonomy workloads | Tables 8.4–8.7, pp. 206–208 |
| Maintenance workloads | §8.6, pp. 220–221 |

Two antecedent papers should accompany the thesis citation:

* Benjamin N. Grosof, Ian Horrocks, Raphael Volz, and Stefan Decker.
  *Description Logic Programs: Combining Logic Programs with Description Logic*.
  WWW 2003, pp. 48–57. DOI **10.1145/775152.775160**.
  [Author paper](https://www.cs.ox.ac.uk/people/ian.horrocks/Publications/download/2003/p117-grosof.pdf),
  [author bibliography](https://www.cs.man.ac.uk/~horrocks/Publications/horrocks2003_bib.html).
  Credit this work and the thesis for the DLP foundation; this repository did
  not introduce DLP or the general ontology-to-rules approach.
* Raphael Volz, Steffen Staab, and Boris Motik. *Incremental Maintenance of
  Materialized Ontologies*. OTM/CoopIS/DOA/ODBASE 2003, LNCS 2888, pp. 707–724.
  DOI **10.1007/978-3-540-39964-3_45**.
  [Institutional record](https://publikationen.bibliothek.kit.edu/1000093298),
  [author paper](https://www.cs.ox.ac.uk/boris.motik/pubs/vsm03incremental.pdf).
  This treats both changing facts and changing rules before the thesis. The
  report should credit that history while retaining the independent errata's
  reservations about particular printed procedures.

For DRed itself, cite Ashish Gupta, Inderpal Singh Mumick, and V. S.
Subrahmanian, *Maintaining Views Incrementally*, SIGMOD Record 22(2),
1993, pp. 157–166. DOI **10.1145/170036.170066** (journal issue version).
[Publisher record](https://doi.org/10.1145/170036.170066).
The conference-proceedings incarnation has DOI 10.1145/170035.170066;
do not mix one venue/version with the other DOI unintentionally.

## Verified post-thesis references

### Maintenance and equality

**Kotowski et al. 2011.** Jakub Kotowski, François Bry, and Simon Brodt.
*Reasoning as Axioms Change: Incremental View Maintenance Reconsidered*.
RR 2011, LNCS 6902, pp. 139–154. DOI **10.1007/978-3-642-23580-1_11**.
[Publisher volume](https://link.springer.com/book/10.1007/978-3-642-23580-1),
[author manuscript](https://www.en.pms.ifi.lmu.de/publications/PMS-FB/PMS-FB-2011-5/PMS-FB-2011-5-paper.pdf).
This is an omitted relevant predecessor: it adapts semi-naive forward chaining
to avoid large transformed maintenance programs and coarse recomputation of
whole predicate extensions. It should be considered in a fuller comparison of
rule/axiom maintenance, in addition to the thesis and ZodiacEdge.

**Motik et al. 2015, B/F.** Boris Motik, Yavor Nenov, Robert Piro, and Ian
Horrocks. *Incremental Update of Datalog Materialisation: the Backward/Forward
Algorithm*. AAAI 2015, pp. 1560–1568, DOI **10.1609/aaai.v29i1.9409**.
[Publisher](https://ojs.aaai.org/index.php/AAAI/article/view/9409),
[author manuscript](https://www.cs.ox.ac.uk/people/ian.horrocks/Publications/download/2015/MNPH15b.pdf).
The broad motivation of avoiding DRed work on multiply supported facts is
already explicit here. The present unary certificate filter is not B/F and
has not been shown to dominate it.

**Motik et al. 2015, equality rewriting.** Same four authors. *Handling
owl:sameAs via Rewriting*. AAAI 2015, pp. 231–237, DOI
**10.1609/aaai.v29i1.9187**.
[Publisher](https://ojs.aaai.org/index.php/AAAI/article/view/9187),
[author report, arXiv:1411.3622](https://arxiv.org/abs/1411.3622).
The arXiv report dates to 13 November 2014; the conference year is 2015.
Sections 3–5 discuss correctness, rewriting rules as well as data, and query
handling. Representative rewriting is prior art and does not make this
repository a complete RDF/SPARQL equality implementation.

**Motik et al. 2015, equality updates.** Same four authors. *Combining Rewriting
and Incremental Materialisation Maintenance for Datalog Programs with
Equality*. IJCAI 2015, pp. 3127–3133.
[Official proceedings paper](https://www.ijcai.org/Proceedings/15/Papers/441.pdf),
[extended report, arXiv:1505.00212](https://arxiv.org/abs/1505.00212).
This is a particularly useful addition to the previous assessment. Incremental
maintenance and equality rewriting were combined here. The local equality
retraction fallback is an implementation limitation, not evidence that
incremental equality maintenance is an unsolved problem. No publisher DOI was
needed or inferred; the arXiv DOI is **10.48550/arXiv.1505.00212**.

**Hu et al. 2018.** Pan Hu, Boris Motik, and Ian Horrocks. *Optimised
Maintenance of Datalog Materialisations*. AAAI 32(1), 2018, pp. 1871–1879,
DOI **10.1609/aaai.v32i1.11554**.
[Publisher](https://ojs.aaai.org/index.php/AAAI/article/view/11554),
[preprint, arXiv:1711.03987](https://arxiv.org/abs/1711.03987).
DRedᶜ and B/Fᶜ combine counting with DRed/B/F to reduce backward evaluation
while supporting recursion. The present code maintains no persistent
derivation counters and should not be called an implementation of these
algorithms. Distinguish original nonrecursive counting from later recursive
counting variants.

**Motik et al. 2019.** Boris Motik, Yavor Nenov, Robert Piro, and Ian Horrocks.
*Maintenance of Datalog Materialisations Revisited*. Artificial Intelligence
269, pp. 76–136, DOI **10.1016/j.artint.2018.12.004**.
[Institutional record](https://ora.ox.ac.uk/objects/uuid%3A5b988e72-5128-4c40-b9a2-81d6597dc748),
[author paper](https://www.cs.ox.ac.uk/people/ian.horrocks/Publications/download/2019/MNPH19a.pdf).
Published online 4 January 2019, accepted 16 December 2018. The paper studies
recursive counting, optimized DRed, and Forward/Backward/Forward (FBF), including
tradeoffs and a broad evaluation. It is a strong source for the report's
caution that maintenance strategies are workload dependent.

**Hu et al. 2022.** Pan Hu, Boris Motik, and Ian Horrocks. *Modular
Materialisation of Datalog Programs*. Artificial Intelligence 308, article
103726, DOI **10.1016/j.artint.2022.103726**.
[Institutional record](https://ora.ox.ac.uk/objects/uuid%3Ae8b03b8d-bfb4-44fc-975b-579875405d52),
[author manuscript](https://www.cs.ox.ac.uk/people/boris.motik/pubs/hmh22modular-materialisation.pdf).
The 2022 article extends the AAAI 2019 paper (pp. 2859–2866, DOI
**10.1609/aaai.v33i01.33012859**). Its abstract and §1 explicitly cover
specialized materialization *and maintenance*, auxiliary state, and
correctness conditions. A sound specialized procedure with a generic fallback
is therefore not a new general architectural principle here.

**Xu and Curé 2023.** Weiqin Xu and Olivier Curé. *ZodiacEdge: a Datalog
Engine With Incremental Rule Set Maintenance*. arXiv:2312.14530v1,
22 December 2023, DOI **10.48550/arXiv.2312.14530**.
[Record](https://arxiv.org/abs/2312.14530),
[versioned text](https://arxiv.org/html/2312.14530v1).
Section 4.4 rebuilds directly affected strongly connected rule groups and
incrementally propagates effects to successors. The paper includes stratified
negation and aggregation. Cite as a preprint on the evidence inspected.
Its §1 assertion that no previous solution handled rule updates is too broad
when read against Volz et al. 2003, the 2004 thesis, and later axiom-maintenance
work; this is a limitation of its historical claim, not a disproof of the
ZodiacEdge algorithm.

### Access paths, set computation, storage, and systems

**Bille et al. 2007.** Philip Bille, Anna Pagh, and Rasmus Pagh. *Fast
Evaluation of Union-Intersection Expressions*. ISAAC 2007, LNCS 4835,
pp. 739–750.
[Author preprint, arXiv:0708.3259](https://arxiv.org/abs/0708.3259),
[institutional metadata](https://pure.itu.dk/en/publications/fast-evaluation-of-union-intersection-expressions/).
This treats preprocessed representations and word-level parallelism with
formal bounds. The local hash-set selector is an engineering specialization;
it neither implements those representations nor improves their bounds.

**Veldhuizen 2014.** Todd L. Veldhuizen. *Leapfrog Triejoin: A Simple,
Worst-Case Optimal Join Algorithm*. ICDT 2014.
[Author preprint, arXiv:1210.0481](https://arxiv.org/abs/1210.0481),
[proceedings paper](https://www.openproceedings.org/2014/conf/icdt/Veldhuizen14.pdf).
The proceedings PDF was intermittently unavailable during this audit; the
arXiv version is a reliable fallback. Set intersection is the unary case of
join evaluation; the repository does not implement general Leapfrog Triejoin
or inherit a general worst-case-optimal join guarantee.

**Motik et al. 2014.** Boris Motik, Yavor Nenov, Robert Piro, Ian Horrocks,
and Dan Olteanu. *Parallel Materialisation of Datalog Programs in Centralised,
Main-Memory RDF Systems*. AAAI 2014, pp. 129–137, DOI
**10.1609/aaai.v28i1.8730**.
[Publisher](https://ojs.aaai.org/index.php/AAAI/article/view/8730).
The repository's sequential exact probes and unary coalescing should not be
presented as RDFox's parallel schedule or mostly lock-free index structures.
Include Dan Olteanu in a full bibliography entry.

**Nenov et al. 2015.** Yavor Nenov, Robert Piro, Boris Motik, Ian Horrocks,
Zhe Wu, and Jay Banerjee. *RDFox: A Highly-Scalable RDF Store*. ISWC 2015,
LNCS 9367, pp. 3–20, DOI **10.1007/978-3-319-25010-6_1**.
[Institutional record](https://ora.ox.ac.uk/objects/uuid%3A2a08b023-77be-431a-a08c-89b47381586a),
[author paper](https://www.cs.ox.ac.uk/Boris.Motik/pubs/npmhwb15RDFox-scalable.pdf).
This is a system/competitor reference; the current research does not execute
RDFox. Historical scaling or runtimes do not form a matched contemporary
baseline for this Python implementation.

**Subotić et al. 2018.** Pavle Subotić, Herbert Jordan, Lijun Chang, Alan
Fekete, and Bernhard Scholz. *Automatic Index Selection for Large-Scale
Datalog Computation*. PVLDB 12(2), pp. 141–153, DOI
**10.14778/3282495.3282500**.
[Official paper](https://www.vldb.org/pvldb/vol12/p141-subotic.pdf).
The year printed in the paper is 2018, even though the volume is associated
with the following VLDB conference cycle. It develops minimum index selection
for all primitive searches in a program; exact hash membership alone is not
that algorithm.

**Carral et al. 2019.** David Carral, Irina Dragoste, Larry González, Ceriel
Jacobs, Markus Krötzsch, and Jacopo Urbani. *VLog: A Rule Engine for Knowledge
Graphs*. ISWC 2019, LNCS 11779, pp. 19–35, DOI
**10.1007/978-3-030-30796-7_2**.
[Author metadata](https://iccl.inf.tu-dresden.de/web/Inproceedings3218/en),
[institutional record and paper](https://research.vu.nl/en/publications/vlog-a-rule-engine-for-knowledge-graphs).
Use this full system paper for the mature engine and experimental setup.
The earlier *VLog: A Column-Oriented Datalog System for Large Knowledge
Graphs* is a different 2016 workshop paper by Urbani, Jacobs, and Krötzsch
in CEUR volume 1690. Do not combine their titles/authors/years.

**Hu et al. 2019, compressed RDF.** Pan Hu, Jacopo Urbani, Boris Motik, and
Ian Horrocks. *Datalog Reasoning over Compressed RDF Knowledge Bases*.
CIKM 2019, pp. 2065–2068, DOI **10.1145/3357384.3358147**.
[Author preprint](https://arxiv.org/abs/1908.10177),
[publisher](https://doi.org/10.1145/3357384.3358147).
Their compressed representation can apply rules to several facts together
and share derived structure. Sharing unary proof computation here does not
compress the stored materialization.

**Bajraktari et al. 2017.** Labinot Bajraktari, Magdalena Ortiz, and Mantas
Šimkus. *Goal-oriented Type-based Reasoning for Expressive DLs*. DL 2017,
CEUR Workshop Proceedings 1879, paper 63, one-page extended abstract.
[Official text](https://ceur-ws.org/Vol-1879/paper63.pdf).
The source explicitly exploits a limited set of recurring local concept
profiles to build query rewritings. It supports analogy to shared signatures,
but is not a proof-cache or DRed deletion algorithm. Describe it as related
profile-sharing work, not the closest maintenance algorithm.

**Zhang et al. 2024.** Xinyue Zhang, Pan Hu, Yavor Nenov, and Ian Horrocks.
*Optimised Storage for Datalog Reasoning*. AAAI 38(9), pp. 10748–10755,
DOI **10.1609/aaai.v38i9.28947**.
[Institutional record](https://ora.ox.ac.uk/objects/uuid%3A1c6b73ed-6d8b-4214-bd19-642236f4430c),
[author preprint](https://arxiv.org/abs/2312.11297).
This integrates storage schemes for transitivity and unions with a general
materializer. Explicit local fact-set memory and their compressed storage
measure different output representations; any comparison needs a query and
materialization contract, not just a closure count.

**Ivliev et al. 2024.** Alex Ivliev, Lukas Gerlach, Simon Meusel, Jakob
Steinberg, and Markus Krötzsch. *Nemo: Your Friendly and Versatile Rule
Reasoning Toolkit*. KR 2024, pp. 743–754, DOI **10.24963/kr.2024/70**.
[Author metadata](https://iccl.inf.tu-dresden.de/web/Inproceedings3390/en),
[official paper](https://proceedings.kr.org/2024/70/kr2024-0070-ivliev-et-al.pdf).
Nemo supports Datalog extensions and restricted chase. It is an appropriate
modern external materialization comparator on a matched positive fragment.
Do not infer equivalent witness identities or support for the repository's
mixed fact/rule transaction API merely from its existential-rule support.

### Recent incremental-query work: different contracts

**Budiu et al. 2023.** Mihai Budiu, Tej Chajed, Frank McSherry, Leonid
Ryzhyk, and Val Tannen. *DBSP: Automatic Incremental View Maintenance for
Rich Query Languages*. PVLDB 16(7), pp. 1601–1614, DOI
**10.14778/3587136.3587137**.
[Official paper](https://www.vldb.org/pvldb/vol16/p1601-budiu.pdf).
This develops compositional incrementalization of stream computations,
including recursion. It provides a broader alternative foundation; it does
not validate the local proof filter. The later journal extension has an
expanded author list: Budiu, Ryzhyk, Zellweger, Pfaff, Suresh, Kassing,
Gyawali, Budiu, Chajed, McSherry, and Tannen; The VLDB Journal 34, article
39 (8 May 2025), DOI **10.1007/s00778-025-00922-y**.
[Publisher record](https://link.springer.com/article/10.1007/s00778-025-00922-y).
Do not transfer the five-author list to the 2025 article.

**Abo-Khamis et al. 2026.** Mahmoud Abo-Khamis, Eden Chmielewski, Andrei
Draghici, Ahmet Kara, and Dan Olteanu. *Maintaining Queries under Updates
Using Heavy-Light Partitioning of the Input Relations*. arXiv:2605.08397v1,
8 May 2026, DOI **10.48550/arXiv.2605.08397**.
[Record](https://arxiv.org/abs/2605.08397),
[versioned text](https://arxiv.org/html/2605.08397v1).
The contract is arbitrary full conjunctive queries, single-tuple updates,
and constant-delay output enumeration; §1/Table 1 compares amortized update
bounds under that contract. The local batch full-materialization experiment
does not establish an improvement over their maintenance-width results.
Treat this as a preprint and cite its exact version.

**Qiao et al. 2026.** Yiming Qiao, Peter Boncz, and Huanchen Zhang. *Robust
Predicate Transfer with Dynamic Execution*. PVLDB 19(6), pp. 1278–1290,
DOI **10.14778/3797919.3797934**.
[Author paper](https://people.iiis.tsinghua.edu.cn/~huanchen/publications/rpt%2B-vldb26.pdf).
Dynamic execution and filtering are relevant to overhead-aware planning.
This is adjacent join-execution research, not a direct DRed or unary
certificate competitor; the current code does not implement RPT+.

**Zhao et al. 2026 (scope boundary).** Kaiyue Zhao, Dingqi Chen, Shaoyu Wang,
and Pan Hu. *Incremental Maintenance of DatalogMTL Materialisations*. AAAI
40(23), pp. 19467–19476, DOI **10.1609/aaai.v40i23.39025**.
[Publisher](https://ojs.aaai.org/index.php/AAAI/article/view/39025).
Published 14 March 2026. It extends DRed to bounded-interval DatalogMTL and
periodic representations. It is contemporary maintenance work, but temporal
semantics and periodic output are outside this repository's language.

## Contribution wording appropriate for the report

| Item | Defensible contribution status |
|---|---|
| OWL-to-DLP compilation, four fragments, open-world queries, rule changes | Original thesis/paper foundations; modern implementation and independently checked correction of particular printed errors |
| Semi-naive execution, DRed, exact indexes, equality representatives | Established methods implemented or specialized locally |
| Unary union/intersection identity | Elementary set algebra applied to coalesced delta evaluation; not a new general join algorithm |
| Cardinality selector and full-delta shortcut | Concrete local implementation and cost analysis, including a falsified pilot and adverse-case evaluation |
| Current unary support shared by exact assertion signature | Specific bounded transaction-local design and implementation; candidate combination, with global novelty unresolved |
| Protection of certified facts during DRed | Specialization of established support-aware maintenance ideas, accompanied by a local preservation argument |
| Protocol, source archive, tests, randomized mixed transactions, negative results | New reproducible artifacts and experimental evidence for this implementation |
| Large speed ratios against `b1254c4` | Cumulative local implementation comparison, not speedup against the 2004 software or external contemporary systems |

Preferred phrase: “We contribute an executable specialization, a scoped
preservation argument, and a controlled evaluation of its benefits and adverse
cases.” Avoid “first,” “novel optimal algorithm,” “state of the art,” or
“proven superior” unless a separate priority search and matched external
comparison establish those claims.

The local preservation lemma is scoped to finite positive function-free,
equality-free programs with complete old materialization. Its domain seeds
must include the current nonempty-domain representative. Partial oracle
exploration proves only positive facts; failure is unknown. The reported
`3M` scan accounting is not a runtime competitive ratio and excludes costs
already listed in the research report. Tests substantiate examples; they do
not convert the argument into a machine-checked implementation proof.

## Corrections or additions recommended for the LaTeX report

1. Add the 2003 DLP and ontology-maintenance papers, the 2011 axiom-maintenance
   paper, and the 2015 equality-maintenance paper. These materially clarify
   attribution and limitations.
2. Use “protocol specified before the confirmatory run” rather than relying on
   the unqualified word “preregistered.” The local protocol was not an
   independently timestamped public preregistration.
3. Preserve the disclosed possible overlap with a separately rewritten Bach
   benchmark report. The later support replay is post-hoc replication, not a
   replacement for the original primary sample.
4. Preserve the neutral complete-transaction result for adaptive unary
   planning and the adverse unsupported-cycle overhead. A favorable kernel
   count is not a general end-to-end speedup.
5. Mark all historical external timings as contextual until a pinned same-host
   run matches data scale, rules, semantics, result set, and timing boundaries.
   An official benchmark workload alone does not guarantee comparability.
6. Separate thesis errata, defects corrected in the reconstruction, and new
   optimization experiments. An error in a printed rule does not prove that
   the historical KAON code implemented that rule literally.

The inspected report already makes the main semantic and performance
qualifications above. This audit did not establish a new error in its unary
identity or positive-certificate argument; the most material findings are
missing prior-work citations and the need to keep contribution claims narrow.
