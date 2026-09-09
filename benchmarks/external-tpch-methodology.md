# Scope of the TPC-H-derived join experiment

This experiment evaluates the positive joins underlying Q3, Q5 and Q9, using
DuckDB 1.4.4's official `tpch` extension and its `dbgen` data at scale factors
0.01 and 0.1. It is a component experiment, not a complete TPC-H run or a
reproduction of Qiao et al.'s evaluation of full SQL at SF100. It does not produce
an audited TPC result or the TPC-H QphH metric. The [DuckDB extension documentation](https://duckdb.org/docs/lts/core_extensions/tpch)
provides the generator, fixed query parameters and query text; the
[TPC-H specification](https://www.tpc.org/tpc_documents_current_versions/pdf/tpc-h_v3.0.0.pdf)
defines the full workload and reporting requirements.

The original extension query text is captured in the input manifest. Each
component retains the original `FROM` relations and `WHERE` conditions, and
replaces the original output expressions with all participating rows' primary
keys. Aggregation, revenue/profit arithmetic, ordering and the Q3 top-ten limit
are outside this experiment. Date/string selections and column projection run
in DuckDB before the Datalog engine is loaded. Their elapsed time is recorded
separately and included in the cold component total.

| Component | Relations | Constant selections |
|---|---|---|
| Q3 | customer, orders, lineitem | BUILDING market segment; order date before 1995-03-15; ship date after 1995-03-15 |
| Q5 | customer, orders, lineitem, supplier, nation, region | ASIA region; order date in 1994 |
| Q9 | part, supplier, lineitem, partsupp, orders, nation | part name contains `green` |

The predicates contain the integer keys from the generated SQL tables. No RDF
encoding, OWL compilation, OWL datatype interpretation or aggregation is being
benchmarked. These are ordinary positive Datalog relations. The implementation
uses the existing indexed `Engine._solutions` evaluator through an external
adapter; the adapter is not a general SQL frontend.

## Preserving SQL bag semantics

Dropping duplicate projected rows before a SQL aggregate can change its result.
This experiment avoids that issue by retaining row identities. Each input
relation keeps its full primary key. Each component answer keeps every
participating relation's full key, including both `l_orderkey,l_linenumber` for
lineitem and both `ps_partkey,ps_suppkey` for partsupp. Keys equated by joins occur
again in the answer tuple when they identify another participating table.

For a dataset satisfying those primary keys, a component's complete answer tuple
identifies its entire tuple of input rows. Thus the mapping from SQL join
witnesses to answer tuples is injective. Set evaluation of this relation
preserves the original pre-aggregation SQL bag's multiplicity. This argument
does not make the DLP engine a bag-semantics or aggregation engine.

Every measured worker verifies that each filtered base projection contains no
collapsed duplicate rows, that both the SQL oracle and Datalog result contain
no duplicate answer tuples, and that their complete answer sets are equal.
Both counts and canonical answer hashes must also match the independently
prepared DuckDB SQL oracle for that scale. Answer-set cardinality alone is not
accepted as validation. The SQL oracle runs the component's original joins and
filters directly over the generated database, rather than over DLP-exported
relations.

## What is measured

Four time intervals are reported separately:

1. DuckDB selection/projection and complete transfer of the selected key rows;
2. conversion of those rows to the engine's immutable facts;
3. engine construction, validation, domain initialization and base indexing;
4. full consumption of the join's answer bindings, including any candidate plan
   construction performed on that call.

Their sum is the cold component total. Join time is the principal query-kernel
measurement; the total shows the practical cost of constructing this particular
Python pipeline. Correctness checks, reference SQL execution and result hashing
are outside those intervals. The SQL oracle's separate time is retained for
context; its in-process native database pipeline differs from the DLP pipeline,
so it is not presented as a fair end-to-end speed ranking.

The base-loading program has no rules. Its entire expected closure is therefore
specified independently as the input facts together with one TOP fact for each
active-domain value and the engine's private nonempty-domain seed. Every worker
checks exact equality to that closure before querying and checks that queries
leave it unchanged. Filtered relation digests are also compared across the
implementations and repetitions.

The four implementations are the immutable `b1254c4` baseline, the immutable
`5531be4` pre-extension checkpoint, the final source with experimental switches
disabled, and the same final source with the compiled-join, incremental-index and
incremental-validation switches enabled. Static joins exercise the compiled
join plan. The two maintenance switches have no update to accelerate here, but
their setup overhead remains part of the combined candidate's measurements.
The positional binding plan retains dynamic cardinality selection. It is an
implementation experiment motivated by join-processing research; it is not an
implementation of RPT+ or a claim to supersede that work.

Each scale/configuration/block uses a fresh Python process, running Q3, Q5 and
Q9 sequentially. DuckDB is restricted to one thread. Whole-database integrity
hashing precedes the timers and warms the filesystem cache. OS caches are not
flushed, and DuckDB caches may carry between components within a worker.
"Cold" refers to constructing a new DLP engine, not cold disk reads; process
startup and opening the DuckDB connection are outside the component intervals. Configuration order
rotates across the scale/block grid. The three-block protocol produces 24
workers and 72 component observations; its rotation is not a complete four-row
Latin square. Three repetitions per configuration at each scale provide a
small descriptive comparison, not a strong statistical or scalability claim.
The raw range as well as the median should be inspected before interpreting a
small difference.

The artifact records the exact generator extension bytes, database hashes,
table counts, SQL text, source hashes, process hash seeds and all worker
observations. Existing thesis and LUBM results remain separate. The generated
DuckDB databases and isolated dependency environment remain in ignored `tmp/`;
the module's `--prepare` command recreates the public inputs. Reproduction
commands are included in the generated report.
