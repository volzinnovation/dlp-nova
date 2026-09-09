# Directly applicable benchmark targets

Research and artifact inspection date: 2026-09-09. The primary local target is
the complete 128-rule LUBM maintenance program published in the ZodiacEdge
repository. Qiao's SQL workloads require a separate SQL-aware adapter; their
SQL aggregate and bag semantics cannot be replaced silently with Datalog set
semantics. Published wall times provide historical context, not a cross-machine
ranking.

## 1. ZodiacEdge: exact published rule program on LUBM(1)

Weiqin Xu and Olivier Curé, *ZodiacEdge: a Datalog Engine With Incremental Rule
Set Maintenance*, arXiv:2312.14530v1, 22 December 2023.
[Paper](https://arxiv.org/html/2312.14530v1).

The repository's additional LUBM experiment supplies 128 positive Datalog rules
and two marked rule subsets: `*` contains 8 rules, `#` contains 16, and one rule
belongs to both subsets. For each subset, the procedure starts without its
rules, materializes, inserts them, then deletes them. The published input sizes
are 100,543, 1,272,575 and 13,405,381 facts for LUBM1/10/100. Its LUBM1 timings
in milliseconds are:

| Subset | Initial reasoning | Rule insertion | Rule deletion |
|---|---:|---:|---:|
| `*` | 588.9 | 216.9 | 252.5 |
| `#` | 603.7 | 56.3 | 21.5 |

These are **additional repository results**, not a table from the December
2023 paper. Hardware, generator seed, repetitions and timer boundaries are
unspecified for this additional experiment. Matching the input count does not
establish byte-identical author data.
[Frozen author benchmark](https://github.com/xwq610728213/zodiac_edge/blob/e15721161d1055f019c4b8f9ac1bd8648417f154/README.md).

### Frozen inputs and implementation contract

The inspected author repository commit is
`e15721161d1055f019c4b8f9ac1bd8648417f154`. Its `README.md` SHA-256 is
`5f410708840431e4cef28b8a032c5bc8f90c29260f723847c5757bf79bc6042d`.
`benchmarks/zodiac.py` downloads that exact file into ignored `tmp/` and rejects
digest drift. A strict parser rejects unexpected grammar, markers, counts,
duplicate rules, unsafe rules, aggregation, negation, comparisons and constants.
Every published rule is retained. No upstream implementation code is copied.
No `LICENSE` file was found in the pinned repository tree; do not describe the
ZodiacEdge artifact as MIT-licensed or redistribute its implementation under
this project's license.

The input is the official unchanged UBA1.7 generator, one university, index 0,
seed 0, already prepared by `benchmarks/lubm.py`. The 15 department RDF/XML files
are hashed in `tmp/lubm-official/manifest.json`. Only the 15 document ontology
declarations and 15 import links are removed. All **100,543 ABox assertions**
remain; this count was verified against the actual generated files. Class
assertions become unary predicates and property assertions binary predicates.
Their names receive the author's `src_` wrapper. Typed RDF constants are
retained. An assertion absent from the author's source-predicate vocabulary
causes failure rather than silent loss.

This benchmark evaluates the author's explicit Datalog program. It is separate
from the full official LUBM ontology evaluation in `benchmarks/lubm.py`, whose
existential consequents require the implementation's L3 profile. It must not be
reported as a complete OWL DL or OWL RL conformance result.

The driver compares four arms: `b1254c4`, `5531be4`, current fixed behavior and
the current combined candidate. Package bytes are copied into immutable source
snapshots before execution, without switching branches. The candidate switches
are `_incremental_validation_enabled`, `_incremental_index_enabled`, and
`_compiled_joins_enabled`; unrelated adaptive-unary and support-certificate
experiments remain disabled. Each configuration receives a fresh process and
the same hash seed within a block. Four-block Latin-square rotations balance
execution position.

Fresh naive materializations using frozen `b1254c4` establish complete typed
tuple digests for full and reduced programs before timed workers run. Every
observed closure at every transaction stage must match the corresponding
reference, including its tuples rather than only its cardinality. Internal TOP
facts are excluded from these Datalog comparisons. This is independent of the
candidate optimization and incremental path, but shares the original engine's
semantics; it is not an independent external reasoner. Small recursive tests
also compare against a separate exhaustive grounding oracle.

Initial construction and materialization are measured separately and together.
Rule parsing, RDF parsing, digest construction and correctness validation are
outside those timers. Insertion and deletion use the same materialized instance.
Process RSS includes parsing and validation and is not an isolated engine memory
measurement. The original frozen thesis-suite outputs are never overwritten.

```sh
python -m benchmarks.lubm --prepare
python -m benchmarks.zodiac --prepare
python -m benchmarks.zodiac --blocks 4 --fact-samples 10 \
  --output benchmarks/zodiac-results.json
```

`--prepare` does not run materialization. Actual measurements require a separate
invocation after the source and quiet measurement window are confirmed. The
default supplemental fact-sample count is one; set it explicitly in reported
runs. Existing output/protocol files cause an error rather than overwrite.

### Supplemental data maintenance

The same complete author program also supports a separate test of 1,000 uniformly
sampled assertion deletions followed by exact reinsertion. Seeds are
`9100, 9101, ...`; each removal starts from the full closure, and reinsertion
restores it before the next sample. Sampling is based on a stable ordering of
typed facts, so hash randomization cannot change the chosen data. Each reduced
closure has its own fresh naive reference.

This uses the small-deletion methodology of materialization-maintenance work;
it is **our supplemental experiment**, not one of Xu's published rule
transactions. Hu, Motik and Horrocks' 2018 evaluation deletes 1,000 facts and
averages ten random subsets. Our Datalog program, generated data, runtime and
hardware differ, so even ten local samples do not reproduce that paper's
original dataset experiments.
[Hu et al., §6 and Table 1](https://www.cs.ox.ac.uk/people/ian.horrocks/Publications/download/2018/HuMH18a.pdf).

## 2. ZodiacEdge wind-turbine workloads: why they are secondary

The 2023 paper evaluates DS1 chains of 50–400 wind turbines, and DS2 programs
up to 800 turbines. RS1 includes aggregation; RS2 and RS3 introduce negation.
The reported machine is a six-core 2.6 GHz Intel Core i7 MacBook Pro with 16 GB
RAM. Figure 9 separately studies symmetric/transitive neighbor inference with
fact and rule removal; Figure 10 adds and removes 10–50% data from a 200-node
base. The current reasoner's positive language cannot reproduce all three
programs without extensions. A declared dependency-closed neighbor subprogram
would be a valid component experiment, but the complete positive LUBM program
above provides a stronger immediate comparison.
[Xu and Curé, §6 and Appendices A–C](https://arxiv.org/html/2312.14530v1).

Artifact variants must not be confused: the pinned `generate_data.py` contains
separate sensor-type, temperature and multi-predicate generators; its SHA-256 is
`6c3418d1662ef553912a57b3bce3a64a870623203e7342dc644cb7f8f5db1651`.
The file `testData/roadConnectionTestRules.rules` has two uncommented rules and
no inequality guard, whereas the README's wind-neighbor transitivity example
contains a comparison. Dropping that guard changes self-neighbor consequences.

## 3. Qiao, Boncz and Zhang: preserve SQL semantics and exact workload identity

Yiming Qiao, Peter Boncz and Huanchen Zhang, *Robust Predicate Transfer with
Dynamic Execution*, PVLDB 19(6), 1278–1290, 2026,
doi:10.14778/3797919.3797934.
[Final primary paper](https://www.vldb.org/pvldb/vol19/p1278-qiao.pdf).
Use the final PVLDB PDF; an earlier personal-site draft contains placeholder
publication metadata and different TPC-H summary numbers.

The final evaluation uses TPC-H SF100 (18 queries with joins), JOB (113 queries),
Appian (8 queries), and SQLStorm (18,251 queries; 13,308 complete, 2,837 fail and
2,106 time out at 10 seconds). DuckDB v1.3.0 is the baseline. The platform has
two Intel Xeon Platinum 8474C processors, 512 GB DDR5 RAM and Debian 12; eight
threads are used by default. The reported aggregate speedups are 1.17× on
TPC-H, 1.47× on JOB, 1.01× on Appian and 1.28× on SQLStorm. These are the
authors' SQL engine measurements, not results for this reasoner.
[Final paper, §6](https://www.vldb.org/pvldb/vol19/p1278-qiao.pdf).

The inspected artifact commit is
`e5a5633f31ee55769394dd0d916851a44a8e0e09` in
`embryo-labs/dynamic-predicate-transfer`. It includes an MIT license (DuckDB
Foundation copyright 2018–2025), unlike the inspected ZodiacEdge repository.
The README provides these commands:

```sh
BUILD_BENCHMARK=1 BUILD_TPCH=1 BUILD_TPCDS=1 BUILD_HTTPFS=1 \
  CORE_EXTENSIONS='tpch' make -j$(nproc)
build/release/benchmark/benchmark_runner \
  'benchmark/large/tpch-sf10/.*.benchmark' --threads=1
build/release/benchmark/benchmark_runner \
  'benchmark/large/tpch-sf100/.*.benchmark' --threads=8
build/release/benchmark/benchmark_runner \
  'benchmark/imdb/.*.benchmark' --threads=8
```

The artifact also supplies Appian and SQLStorm instructions. The April 2026
README update mentions a missing `-march=native` correction; record compiler
and target architecture for an external reproduction.
[Frozen artifact](https://github.com/embryo-labs/dynamic-predicate-transfer/tree/e5a5633f31ee55769394dd0d916851a44a8e0e09).

A practical small local target is an explicitly labeled smaller TPC-H scale
with complete SQL answers validated by DuckDB. A Horn join adapter must retain
row identities and reproduce filters, aggregation, ordering and duplicate
semantics in explicit stages. Timing only its join component is a kernel
comparison; it cannot be ranked against the paper's full-query aggregate
speedups. TPC-H or JOB queries must be selected before examining performance,
and every excluded construct must be disclosed. The artifact's three-table
modulus demo is useful for diagnostics but is not itself an established
benchmark.

## Immediate interpretation limits

The new established target is exact **rule-program** reproduction at one
officially generated LUBM scale, with fully specified transactions. Its data
count matches the author's repository table, but author input hashes are
unavailable. The principal valid speed comparisons are paired measurements
between frozen versions of this repository on the same host. Widely accepted
benchmark names alone do not make full OWL reasoning, Datalog materialization,
incremental maintenance and SQL query execution interchangeable tasks.
