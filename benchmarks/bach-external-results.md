# Bach comparisons with HermiT and ZodiacEdge

Original-scale dissertation examples. Exact answers are checked in every completed state.

Times include input preparation, reasoning and all requested answers; milliseconds.
Incremental times include the change and nine updated answers; setup is separate.

| Task | b1254c4 | Current | HermiT | ZodiacEdge |
|---|---:|---:|---:|---:|
| static/ontology | 89.525 | 55.556 | 347.374 | N/A |
| static/initial | 9.407 | 7.493 | 269.669 | 4.425 |
| static/fact-replace | 9.441 | 7.655 | 269.036 | 4.528 |
| static/rule-remove | 8.470 | 6.745 | 267.737 | 4.144 |
| static/symmetry-insert | 10.577 | 6.774 | 277.835 | 5.149 |
| incremental/fact-replace | 5.846 | 4.846 | N/A | FAILED (6/12) |
| incremental/rule-remove | 4.766 | 4.003 | N/A | 0.472 |
| incremental/symmetry-insert | 6.529 | 3.643 | N/A | 1.267 |

12 repeated blocks; 336 fresh processes, executed sequentially.
HermiT reconstructs each static state. No HermiT incremental timing is claimed.
ZodiacEdge executes the complete positive family rules; the full existential OWL ontology is unsupported.
The 25 full-ontology questions and nine family questions include exact complete pair sets.
Each incremental scenario starts from the original input and attempts to return to it; all completed states are checked.
Any failed worker disqualifies its entire configuration/task from timing rankings; all failures remain in the raw data.
ZodiacEdge's mixed fact replacement uses deletion then insertion, with both calls timed.
Schema questions use native fresh-instance probes; they are not inferred from observed pairs.
The preserved b1254c4 package is newly measured here; its historical saved baseline has no Bach results.
These tiny examples establish source fidelity and illustrate overheads, not large-scale superiority.
Raw JSON retains every phase, question, exact answer, process duration and paired ratio.
