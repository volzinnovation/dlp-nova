# Research preprint

The **combined arXiv manuscript** is
[`output/pdf/combined-report.pdf`](../../output/pdf/combined-report.pdf).
Upload **[`output/arxiv/combined-report-source.tar.gz`](../../output/arxiv/combined-report-source.tar.gz)**
as a single source archive. It contains one document root,
`combined-report.tex`, the matching compiled bibliography, bibliography source,
local style and its license/provenance. Plots are defined directly in the TeX.
The archive is checked by extracting and compiling its actual contents in an
isolated directory.

[Submission metadata](arxiv-submission.md) provides the title, author,
classification entries, and an ASCII abstract ready to paste into arXiv's
metadata fields.

The merged manuscript has one title page, abstract and bibliography. The
scientific discussion ends with a concise conclusion; the technical material
follows as appendices. Data and research transparency are part of the final
reproducibility appendix. Section, table, figure and citation references are
resolved across the complete document.

Edit the authoritative source parts described below. The build regenerates
`combined-report.tex` through `scripts/prepare_combined_report.py`;
`combined-source-map.json` records the contributing source hashes.
The separately readable paper and supplement are also built from those parts.

`research-report.tex` is a scientific paper for readers beyond specialist
reasoner development. It is organized around research questions, conceptual
methods, findings, and their implications. Concepts are introduced through the
thesis's original Bach family examples and the actual Lehigh University
Benchmark (LUBM) ontology. The latter connects the exposition to standard
benchmark questions. The overview figure and table preserve both positive
and negative evidence. The author is **Raphael Volz,
Pforzheim University**.

`technical-supplement.tex` retains detailed semantic corrections, proofs,
experimental protocols, complete tables, implementation choices, and
reproducibility information. Earlier experimental observations are preserved.
The subsequent Bach comparison adds new measurements of the thesis's original
examples, including a fresh evaluation of the preserved reference implementation.

The template is George Kour's community `arxiv-style`, pinned to commit
`920514696f6e7270cab0558fd97c44515c63b4c4`. Its unchanged style file, MIT license,
and SHA-256 provenance are included. This is a preprint layout suitable for arXiv,
not an official arXiv template or an endorsement.

From the repository root, using an existing TeX Live/MacTeX installation:

```sh
uv run python scripts/build_research_report.py --check-bundle
```

This regenerates figures and tables from the saved JSON observations, assembles
the combined manuscript, compiles all three documents and bibliographies, and checks isolated builds using only each
document's packaged source files.
It does not rerun any benchmark. Outputs are:

- `output/pdf/research-report.pdf`
- `output/pdf/research-report-manifest.json`
- `output/arxiv/research-report-source.tar.gz`
- `output/pdf/technical-supplement.pdf`
- `output/pdf/technical-supplement-manifest.json`
- `output/arxiv/technical-supplement-source.tar.gz`
- `output/pdf/combined-report.pdf`
- `output/pdf/combined-report-manifest.json`
- `output/arxiv/combined-report-source.tar.gz`

Each source bundle includes one document root and its required `.tex`, `.bib`,
`.bbl`, local style, generated figures/tables, and template provenance/license.
They use standard pdfLaTeX packages and no shell escape. From the unpacked main
paper bundle, build with:

```sh
latexmk -norc -pdf -interaction=nonstopmode -halt-on-error research-report.tex
```

For the separate supplement bundle, use `technical-supplement.tex` instead.
Authorship and affiliation follow the author's supplied instructions.
No submission or publication is performed.
For the upload archive, compile `combined-report.tex` with pdfLaTeX. The
[arXiv TeX guidance](https://info.arxiv.org/help/submit_tex.html) requires TeX
source and its dependencies for TeX-authored manuscripts. The
[supported environment](https://info.arxiv.org/help/faq/texlive.html) currently
defaults to TeX Live 2025 and supports pdfLaTeX. The archive includes a fresh
`combined-report.bbl` alongside `references.bib`; no hand-written submission
configuration is needed for this ordinary single-root document.

The bibliography metadata is documented in the [related-work audit](../research-related-work-notes.md).
The [benchmark survey](../research-benchmark-survey-notes.md) and
[target benchmark notes](../research-target-benchmarks.md) retain source details,
published reference timings, and comparison limits. Large fetched/generated
datasets live in ignored `tmp/`; their hashes and preparation commands are
recorded by each runner. The fixed `b1254c4` baseline remains unchanged.

The report explicitly asks whether DLP fragments are still worthwhile alongside
OWL 2 RL. Its [separate assessment](../DLP_PROFILE_ASSESSMENT.md) distinguishes
standard profile membership, accepted compiler syntax, and optimization
eligibility. DLP L0–L3 are retained for historical reproduction; accepting an input
does not certify OWL 2 RL conformance.

The follow-up source adds insertion-validation reuse, incremental
DRed index erasure, and positional positive join plans, now enabled by default.
The original paired experiments
compare the bundle with the same source's disabled configuration and immutable
`b1254c4` / `5531be4` checkouts. Exact tuple checks and complete timing boundaries
are retained. A TPC-H component result is not a complete SQL benchmark result;
the author-supplied ZodiacEdge program is not a full OWL translation of LUBM.

The later bounded-lookahead experiment uses one fresh process per component,
including four adverse controls, and remains opt-in. It includes a separate
source archive so the earlier experiment stays reproducible. The actual native
ZodiacEdge comparison is mixed; a selected insertion advantage does not imply
overall superiority. A separate finite DLP L3 comparison with HermiT evaluates
consistency and exact named consequences. Its positive result needs no premise
about ontology prevalence; the family also lies in OWL 2 EL and is not a
complexity result or comparison against specialized EL engines.

The Bach comparison retains the examples' original scale. It includes 25
questions on the complete Table 2.5 ontology and nine on the separate family
graph, with 12 repetition blocks specifying 336 fresh processes. Current,
baseline, and HermiT runs cover the full ontology. All four engines reconstruct
the four family states; the two local versions and ZodiacEdge also apply and
reverse the three changes. HermiT has no incremental timing in this study.
The baseline's original report contained no Bach cases, so its new measurements
are distinct from the preserved historical results.

An independently reproduced, seed-sensitive failure of the pinned ZodiacEdge
version loses still-supported ancestry during the family fact replacement.
The affected task is excluded from timing rankings, and failed executions are
retained. This finding does not replace the earlier successful university
rule-update observations. The supplement's `bach-comparison.tex` records the
semantic contracts, timing boundaries, and limits; generated tables use the new
`benchmarks/bach-external-results.json` and its separately preserved protocol.
