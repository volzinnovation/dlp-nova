# External benchmark selection and published reference results

Research notes verified on 2026-09-09. These notes distinguish a benchmark's
published design and measurements from our assessment of suitability. Timings
below belong to their cited experiments; they are **not measurements of this
repository** and must not be divided by local timings to claim speedups.

## Selection for this implementation

The current implementation is an eager DLP/Horn materializer with limited
datatypes, explicit rejection of unsupported constructors, optional bounded
existentials, and fact/rule maintenance. Its unary proof certificates specifically
address repeated current assertion signatures. The following choices follow from
that scope, rather than popularity alone.

| Priority | Benchmark | Useful evaluation | Required qualification |
|---|---|---|---|
| First | Official LUBM(1,0), then increasing university counts | End-to-end ontology loading; named query answers; materialization separately | Use the official ontology, UBA generator, queries, and reference answer sets. Any ontology projection must be named and recorded. |
| First for the new maintenance hypothesis | Oxford maintenance workloads: Reactome, Claros, ChEMBL, UniProt, UOBM transformations | Initial closure plus seeded fact deletion, mixed changes, and sensitivity to repeated unary signatures | Use the exact published rule program and explicit facts. The U/R/LE transformations have different semantics. Small samples are derivatives, not full benchmark runs. |
| Second | ORE 2015 corpus | Real ontology coverage; consistency, named classification and realization | Enumerate unsupported cases. A supported DLP subset is a new filtered track and cannot inherit ORE's complete DL/EL rankings. |
| Second | OWL2Bench | Explicit feature coverage and scalable ABoxes in named profiles | RL also includes unsupported features here; run a coverage gate before measurement. |
| Later, for general query infrastructure | WatDiv and BSBM | Join diversity and SPARQL service performance | These do not directly measure OWL closure or DRed maintenance. A query adapter must be benchmarked separately from this reasoner's kernel. |

## LUBM: directly reusable answers and historical context

The [official LUBM site](https://swat.cse.lehigh.edu/projects/lubm/) provides
UBA 1.7, the Univ-Bench ontology, 14 SPARQL 1.0 queries, and reference answers for
LUBM(1,0). It explicitly states that UBA 1.7 with `-index 0 -seed 0` reproduces
the datasets used in its OWL benchmark papers. Preserve the ontology's original
IRI; changing HTTP to HTTPS changes RDF terms. Download links are resolved from
the official page, rather than substituting a third-party generator.

Published historical reference: Guo, Pan and Heflin, *LUBM: A Benchmark for OWL
Knowledge Base Systems*, Journal of Web Semantics 3(2–3), 158–182 (2005),
[DOI](https://doi.org/10.1016/j.websem.2005.06.005),
[author PDF](https://swat.cse.lehigh.edu/pubs/guo05a.pdf).
Section 3.2 used UBA 1.6, a Pentium 4 at 1.8 GHz, 256 MB RAM, Windows XP,
Java SDK 1.4.1, and a 512 MB heap. Table 1 (author PDF p. 15) reports
LUBM(1,0): 15 files, 103,397 triples; the count includes duplicate ABox triples.
Sesame 1.0 with RDFS inference took 13 s in memory and 542 s with MySQL 4.0.16;
DLDB-OWL release 2004-03-29 with Access 2002 took 343 s. Table 3 (author PDF
p. 31) gives Q1: 15 ms, 46 ms, and 59 ms respectively, each returning four
answers. These are load and query measurements with distinct semantic/storage
configurations, not uniform full OWL materialization measurements.

Our comparison rule: validate exact answer tuples first, then report parse,
compile, materialize, serialization/adapter, and query intervals separately.
Official reference answers provide an independently published correctness target;
the 2005 timings provide historical context only. Counts of RDF triples and
internal unary/binary facts need separate labels.

## UOBM and OWL2Bench: expressivity matters

Ma, Yang, Qiu, Xie, Pan and Liu, *Towards a Complete OWL Ontology Benchmark*,
ESWC 2006, LNCS 4011, pp. 125–139,
[DOI/publisher](https://doi.org/10.1007/11762256_12), extends LUBM with separate
OWL Lite and OWL DL ontologies and more interconnected data. Its publisher
abstract is accessible; numeric tables from the subscription full text were not
verified here and are not transcribed.

The [Oxford UOBM generator](https://www.cs.ox.ac.uk/isg/tools/UOBMGenerator/)
is an explicitly different data generator. Its authors state that its
distributions differ from the original one-, five-, and ten-university datasets;
notably, it changes the `isFriendOf` skew. They also describe disjunction and
negation in the ontology. Consequently, `UOBM(N)` alone is an insufficient
dataset identifier: cite generator/version, seed, ontology and data hashes.

Singh, Bhatia and Mutharaju, *OWL2Bench: A Benchmark for OWL 2 Reasoners*,
ISWC 2020, LNCS 12507, pp. 81–96,
[DOI/publisher](https://doi.org/10.1007/978-3-030-62466-8_6), supplies TBoxes for
EL, QL, RL and DL, an ABox generator and reasoning-dependent queries.
The publisher's accessible appendix identifies property chains in Q2 for EL/RL/DL
and reflexivity in Q1. Those are concrete coverage gaps for the current DLP
compiler, not performance failures. The
[authors' repository](https://github.com/kracr/owl2bench) provides code,
ontologies and an `Experiments` directory. No original numeric OWL2Bench result
is used here because the complete methods/results were not independently
checked. Pin a repository commit before running a future experiment.

## Maintenance workloads: closest published algorithm comparison

Hu, Motik and Horrocks, *Optimised Maintenance of Datalog Materialisations*,
AAAI 2018,
[author PDF](https://www.cs.ox.ac.uk/people/ian.horrocks/Publications/download/2018/HuMH18a.pdf),
Section 6 and Table 1 (PDF pp. 7–8), compare DRed, DRedc, B/F and B/Fc.
Experiments used a Dell PowerEdge R720, two Xeon E5-2670 2.6 GHz processors,
256 GB RAM, Fedora 24 and kernel 4.8.12-200.fc24.x86_64.
Their small-deletion test averages ten randomly selected subsets of 1,000 facts.

| Published program | Explicit facts | Nonrecursive / recursive rules | DRed (s) | DRedc (s) | B/F (s) | B/Fc (s) |
|---|---:|---:|---:|---:|---:|---:|
| Reactome-U | 12.5 million | 814 / 28 | 1.03 | 0.06 | 1.00 | 0.05 |
| UOBM-U | 254.8 million | 135 / 144 | 1,185.87 | 179.24 | 31.96 | 1.18 |

The U programs are complete but unsound OWL approximations; R programs are
sound but incomplete transformations; Claros-LE adds difficult rules manually.
The paper's artifact location is
`http://krr-nas.cs.ox.ac.uk/2017/counting/`; retrieval failed during this survey,
so no artifact version or modern rerun is claimed.

These results motivate comparing our certificates with DRedc and B/Fc on the
**same program**, especially where unary signatures repeat. Ordinary DRed is a
useful internal control but insufficient by itself for a claim against current
maintenance research. Report all fact-removal sizes, actual closure changes,
proof-certificate hit rates, budgets, rejected fragments and fallback cost.
Rule changes must be a separately labeled extension of a fact-update benchmark.

The longer theoretical/empirical follow-up is Motik, Nenov, Piro and Horrocks,
*Maintenance of Datalog Materialisations Revisited*, Artificial Intelligence 269,
76–136 (2019), [author PDF](https://www.cs.ox.ac.uk/boris.motik/pubs/mnph19maintenance-revisited.pdf).
It compares robustness on small updates and break-even behavior on larger ones;
no single strategy is uniformly best. This supports retaining adverse update
families rather than choosing only certificate-friendly examples.

## ORE: real ontologies and explicit failure accounting

Parsia, Matentzoglu, Gonçalves, Glimm and Steigmiller, *The OWL Reasoner
Evaluation (ORE) 2015 Competition Report*, Journal of Automated Reasoning 59,
455–482 (2017), [open paper](https://doi.org/10.1007/s10817-017-9406-8),
reports consistency, classification and realization tracks for OWL 2 DL and EL.
Section 3.5 gives live clients with Xeon L5410 quad-core 2.33 GHz CPUs and
12 GB RAM (10 GB available to a reasoner); live tasks had a 180 s overall limit,
with 150 s allowed for reported reasoning and 30 s additional I/O allowance.
Figure 2/Section 5 reports EL consistency totals of 425.1 s for ELK and 1,050.4 s
for Konclude, both including parsing, tied on solved count. These aggregate
track times cannot be compared with one local ontology. The paper warns that
majority-vote answer validation can accept wrong results.

The [official corpus deposit](https://zenodo.org/records/18578) is version v1,
15 June 2015: `ore2015_sample.zip`, 725.4 MB,
MD5 `109f04cf8f124eb551d33c100e549730`. Its reuse terms cover benchmarking;
individual ontology licenses still apply. Use named-class realization as the
closest task to this materializer, and check the exact supported fragment.

## WatDiv and BSBM: query benchmarks, not reasoning rankings

Aluç, Hartig, Özsu and Daudjee, *Diversified Stress Testing of RDF Data
Management Systems*, ISWC 2014, pp. 197–212,
[author PDF](https://cs.uwaterloo.ca/~tozsu/publications/rdf/ISWC14-final.pdf),
Section 5.2, uses approximately 10 million and 100 million triples (scale factors
100 and 1,000), 12,500 queries from 125 templates, five randomized warm-cache
repetitions, one thread and a 60 s query timeout. Hardware: AMD Phenom II X4
955, 3.2 GHz, 16 GB RAM, Ubuntu 12.04 LTS. Figure 4a (PDF p. 13) reports
10M workload totals of 41,612 s for Virtuoso 6.1.8 and 51,268 s for Virtuoso
7.1.0. These totals involve timeout handling and must not be treated as the cost
of one query or of closure computation.
The [official site](https://dsg-uwaterloo.github.io/watdiv/) currently offers
generator v0.6. Reproducing the paper requires pinning its actual workload,
not assuming the latest generator's default workload matches it.

BSBM's standard publication is Bizer and Schultz, *The Berlin SPARQL Benchmark*,
IJSWIS 5(2), 1–24 (2009), [DOI](https://doi.org/10.4018/jswis.2009040101).
The [BSBM tools project](https://sourceforge.net/p/bsbmtools/) describes a
SPARQL-protocol benchmark for RDF stores and relational-to-RDF wrappers.
An [author-hosted CWI chapter](https://ir.cwi.nl/pub/21394/21394B.pdf), Section
1.3, describes specification 3.1's Explore and Business Intelligence mixes,
including SPARQL 1.1 grouping/aggregation. The original Mannheim/FU Berlin
result pages failed retrieval here. No unverified numeric BSBM comparison is
included.

Our interpretation: both are useful later for general join and RDF service
scalability. Running their queries through RDFLib would predominantly test that
adapter unless the reasoner's own join path is explicitly instrumented. A
successful BSBM or WatDiv run does not establish OWL entailment completeness.

## Minimal reproducible external evaluation protocol

1. Pin original artifact URLs, hashes, generator releases/commits, seed, scale,
   ontology and rule translation. Preserve the untouched input and a machine-
   readable manifest of any projection. Label projected results as such.
2. Evaluate semantic support before timing. An unsupported case is a recorded
   outcome, never a silently skipped or empty-answer case.
3. Validate full answer tuples against official gold answers where available;
   cross-check supported OWL answers with an independent reference reasoner.
   Include both false-positive and false-negative counts.
4. Measure cold parse/load, compilation, materialization, warm queries and
   updates separately, including required validation/recompilation in public API
   timings. Record closure size, peak memory, timeouts and limits.
5. Compare baseline `b1254c4`, production, and experimental certificate variants
   on identical inputs in randomized fresh-process blocks. Retain the original
   benchmark as an external workload, rather than retuning the heuristic on it.
6. To claim competitive speed, rerun a pinned independent system on the same
   host with matched semantics and work boundaries. Published cross-machine
   numbers remain a contextual table until those conditions hold.

This file is a sourced selection and protocol note, not a claim that every
listed suite has been executed. The main report should cite actual generated
result files separately from this survey.

## Bibliographic metadata for the report

Author order and spelling were checked against the author PDF or the publisher
pages cited above. BSBM was additionally checked against the
[author's institutional publication record](https://madoc.bib.uni-mannheim.de/34767/);
the journal article is from 2009, not the separate 2011 book chapter with the
same title. The following entries preserve full author lists rather than
importing abbreviated citation exports.

```bibtex
@article{guo2005lubm,
  author = {Guo, Yuanbo and Pan, Zhengxiang and Heflin, Jeff},
  title = {{LUBM}: A Benchmark for {OWL} Knowledge Base Systems},
  journal = {Journal of Web Semantics},
  year = {2005},
  volume = {3},
  number = {2--3},
  pages = {158--182},
  doi = {10.1016/j.websem.2005.06.005},
  url = {https://swat.cse.lehigh.edu/pubs/guo05a.pdf}
}

@inproceedings{ma2006uobm,
  author = {Ma, Li and Yang, Yang and Qiu, Zhaoming and Xie, Guotong
            and Pan, Yue and Liu, Shengping},
  title = {Towards a Complete {OWL} Ontology Benchmark},
  booktitle = {The Semantic Web: Research and Applications ({ESWC} 2006)},
  series = {Lecture Notes in Computer Science},
  volume = {4011},
  year = {2006},
  pages = {125--139},
  publisher = {Springer},
  doi = {10.1007/11762256_12}
}

@inproceedings{singh2020owl2bench,
  author = {Singh, Gunjan and Bhatia, Sumit and Mutharaju, Raghava},
  title = {{OWL2Bench}: A Benchmark for {OWL} 2 Reasoners},
  booktitle = {The Semantic Web -- {ISWC} 2020},
  series = {Lecture Notes in Computer Science},
  volume = {12507},
  year = {2020},
  pages = {81--96},
  publisher = {Springer},
  doi = {10.1007/978-3-030-62466-8_6}
}

@article{parsia2017ore,
  author = {Parsia, Bijan and Matentzoglu, Nicolas
            and Gon{\c{c}}alves, Rafael S. and Glimm, Birte
            and Steigmiller, Andreas},
  title = {The {OWL} Reasoner Evaluation ({ORE}) 2015 Competition Report},
  journal = {Journal of Automated Reasoning},
  year = {2017},
  volume = {59},
  number = {4},
  pages = {455--482},
  doi = {10.1007/s10817-017-9406-8}
}

@inproceedings{aluc2014watdiv,
  author = {Alu{\c{c}}, G{\"u}ne{\c{s}} and Hartig, Olaf
            and {\"O}zsu, M. Tamer and Daudjee, Khuzaima},
  title = {Diversified Stress Testing of {RDF} Data Management Systems},
  booktitle = {The Semantic Web -- {ISWC} 2014},
  series = {Lecture Notes in Computer Science},
  volume = {8796},
  year = {2014},
  pages = {197--212},
  publisher = {Springer},
  doi = {10.1007/978-3-319-11964-9_13},
  url = {https://cs.uwaterloo.ca/~tozsu/publications/rdf/ISWC14-final.pdf}
}

@article{bizer2009bsbm,
  author = {Bizer, Christian and Schultz, Andreas},
  title = {The Berlin {SPARQL} Benchmark},
  journal = {International Journal on Semantic Web and Information Systems},
  year = {2009},
  volume = {5},
  number = {2},
  pages = {1--24},
  doi = {10.4018/jswis.2009040101}
}
```

The Oxford 2018 U/R qualifications describe the translation's fidelity to the
original OWL ontology. They do **not** mean that an otherwise correct Datalog
engine is unsound for the resulting Datalog program. Section 6 (author PDF
p. 7) explicitly describes U as a complete but unsound transformation, R as
sound but incomplete, and Claros-LE as a manually extended lower-bound program.
Reported U/R/LE timings are therefore measurements of the transformed programs.
