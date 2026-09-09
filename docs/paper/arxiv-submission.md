# arXiv submission metadata

Use this metadata with the
[combined manuscript source archive](../../output/arxiv/combined-report-source.tar.gz).
These are prepared metadata entries; this document does not record a submission.

Keep this copy aligned with the authoritative abstract in
[`research-report.tex`](research-report.tex). The build assembles that source
and the technical appendices into [`combined-report.tex`](combined-report.tex).
After changing the abstract, rebuild the manuscript and refresh the copy below.

## Title

```text
Description Logic Programs Revisited: The Benefits and Limits of Specialized Ontology Reasoning
```

## Author and affiliation

Author: Raphael Volz

Affiliation: Pforzheim University

## ACM 1998 classification

Paste this entry into the ACM classification field:

```text
I.2.3; I.2.4; H.2.4
```

The recommended entries cover deduction, knowledge representation, and database
query processing:

- **I.2.3:** Deduction and Theorem Proving.
- **I.2.4:** Knowledge Representation Formalisms and Methods.
- **H.2.4:** Systems, under Database Management; relevant topics include query
  processing and rule-based databases.

Labels follow the [1998 ACM classification mirror](https://www.mi.sanu.ac.rs/~zorano/acm/ccs98.html).

## MSC2020 classification

Paste this entry into the MSC classification field:

```text
68T27 (Primary) 68T30, 68N17 (Secondary)
```

- **68T27:** Logic in artificial intelligence.
- **68T30:** Knowledge representation.
- **68N17:** Logic programming.

The labels are verified against the AMS
[artificial intelligence classifications](https://mathscinet.ams.org/msc/msc2020.html?btn=Current&t=68T05)
and [software classifications](https://mathscinet.ams.org/mathscinet/msc/msc2020.html?t=68N18).
The primary and secondary ordering is our recommendation for this paper.
Field conventions follow the [arXiv metadata guidance](https://info.arxiv.org/help/prep.html).

## Abstract

The following copy contains 1,641 ASCII characters, excluding its enclosing code
fence and final newline. It is normalized directly from the combined TeX abstract:
TeX `--` becomes `-`, `\%` becomes `%`, and whitespace is collapsed to single
spaces. Copy only the paragraph inside the fence, without the fence markers.

```text
Restricting the expressive power of a knowledge representation language can make reasoning more efficient, but the conditions under which this advantage appears require empirical examination. We revisit Description Logic Programs, which connect ontology languages with rule-based inference, through a reconstruction of the original work and experiments on changing knowledge and query answering. We investigate whether sharing explanations and adapting the order of reasoning reduce computation while preserving its conclusions. Sharing explanations accelerates a favourable update task by approximately 7.5 times, with a similar result in a separate replication, but adds 18-19% overhead when suitable explanations are absent. Adaptive evaluation reduces some intermediate work without consistently improving complete task times. Comparisons with established reasoners likewise reveal operation-specific advantages and substantial disadvantages. The original Bach examples also exposed a loss of valid conclusions during deletion in the tested ZodiacEdge rule reasoner. On a finite task involving the existence of unnamed individuals, specialized reasoning is 2.6-21.5 times faster than the tested HermiT distribution; the task also belongs to the established OWL 2 EL profile. These findings support a conditional account of specialization: benefits depend on the structure of the knowledge, the change, and the question. A fragment's theoretical or computational value is distinct from how frequently it is used. The evidence supports useful specializations, without establishing a general performance advantage or a new complexity bound.
```
