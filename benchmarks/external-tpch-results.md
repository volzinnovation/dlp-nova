# TPC-H-derived join components

Q3/Q5/Q9 FROM+WHERE joins at SF0.01 and SF0.1, using DuckDB1.4.4's official tpch/dbgen extension.
This is not a complete TPC-H execution, a QphH metric, a TPC-audited result, or a reproduction of Qiao et al.'s SF100 SQL evaluation.

| Scale | Component | Configuration | Facts | Answers | Filter(ms) | Encode(ms) | Index(ms) | Join(ms) | Componenttotal(ms) |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| 0.01 | Q3 | b1254c4 | 39883 | 356 | 4.640 | 11.238 | 203.672 | 5.034 | 224.583 |
| 0.01 | Q3 | 5531be4 | 39883 | 356 | 4.835 | 11.196 | 200.592 | 4.762 | 221.311 |
| 0.01 | Q3 | current-fixed | 39883 | 356 | 4.749 | 11.155 | 206.396 | 4.692 | 226.804 |
| 0.01 | Q3 | candidate | 39883 | 356 | 4.772 | 10.767 | 204.917 | 3.694 | 223.301 |
| 0.01 | Q5 | b1254c4 | 64104 | 103 | 8.694 | 26.622 | 372.655 | 20.258 | 428.229 |
| 0.01 | Q5 | 5531be4 | 64104 | 103 | 8.488 | 26.530 | 373.657 | 21.299 | 429.608 |
| 0.01 | Q5 | current-fixed | 64104 | 103 | 8.580 | 26.514 | 382.914 | 21.265 | 438.617 |
| 0.01 | Q5 | candidate | 64104 | 103 | 8.332 | 20.513 | 379.234 | 11.338 | 419.324 |
| 0.01 | Q9 | b1254c4 | 83407 | 3223 | 13.259 | 76.480 | 533.688 | 35.978 | 657.890 |
| 0.01 | Q9 | 5531be4 | 83407 | 3223 | 12.419 | 72.360 | 530.837 | 34.760 | 650.377 |
| 0.01 | Q9 | current-fixed | 83407 | 3223 | 12.418 | 74.762 | 534.863 | 34.431 | 654.303 |
| 0.01 | Q9 | candidate | 83407 | 3223 | 12.154 | 46.218 | 546.394 | 23.084 | 627.627 |
| 0.1 | Q3 | b1254c4 | 400111 | 3321 | 44.966 | 173.686 | 3776.983 | 45.104 | 4040.739 |
| 0.1 | Q3 | 5531be4 | 400111 | 3321 | 47.107 | 178.118 | 3862.531 | 44.803 | 4130.654 |
| 0.1 | Q3 | current-fixed | 400111 | 3321 | 44.521 | 167.496 | 3744.383 | 43.046 | 3999.446 |
| 0.1 | Q3 | candidate | 400111 | 3321 | 45.311 | 171.165 | 3811.495 | 31.779 | 4057.003 |
| 0.1 | Q5 | b1254c4 | 639556 | 865 | 84.096 | 941.511 | 6800.396 | 941.867 | 8767.870 |
| 0.1 | Q5 | 5531be4 | 639556 | 865 | 84.530 | 941.801 | 6792.209 | 957.380 | 8767.373 |
| 0.1 | Q5 | current-fixed | 639556 | 865 | 84.549 | 930.784 | 6753.838 | 949.313 | 8712.045 |
| 0.1 | Q5 | candidate | 639556 | 865 | 83.840 | 517.486 | 7012.433 | 500.093 | 8112.880 |
| 0.1 | Q9 | b1254c4 | 832672 | 32160 | 124.091 | 1548.827 | 9677.010 | 390.872 | 11740.799 |
| 0.1 | Q9 | 5531be4 | 832672 | 32160 | 123.176 | 1553.237 | 9560.411 | 378.172 | 11614.997 |
| 0.1 | Q9 | current-fixed | 832672 | 32160 | 124.556 | 1540.820 | 9507.161 | 380.532 | 11533.745 |
| 0.1 | Q9 | candidate | 832672 | 32160 | 125.337 | 802.386 | 9800.587 | 266.399 | 10994.709 |

All participating table primary keys remain in every answer (including both components of lineitem and partsupp keys). Each Datalog answer set is compared with the exact DuckDB SQL bag of pre-aggregation row identities; multiplicities are verified rather than silently collapsed.
The joins and constant filters are taken from the extension's pinned Q3/Q5/Q9 queries. Aggregation, arithmetic outputs, sorting and top-k are omitted. DuckDB performs date/string filters and narrow column projections; their extraction time is reported separately and included in component end-to-end time.
The component rule is queried through the existing Engine._solutions evaluator. Any candidate join-plan construction is inside the join timer. A new engine loads the component's facts; index construction and fact encoding are separate and included in component end-to-end time. Integer primary keys are ordinary Datalog constants; this is not an RDF parser benchmark.
Baseline b1254c4 and pre-extension5531be4 are immutable checkouts; current-fixed disables experimental switches; candidate enables compiled joins, incremental index maintenance and insertion validation reuse. The latter two are maintenance features and do not have update work to accelerate here; their setup overhead is included.
Raw process observations, pinned database/extension/source hashes, original SQL texts, component SQL, table counts and exact oracle digests are in the JSON. Queries run sequentially Q3,Q5,Q9 inside each fresh process. Whole-database integrity hashing precedes timing and warms the filesystem cache; DuckDB caches are not reset between components. DuckDB uses one thread. Its oracle time is context, not a fair end-to-end speed ranking against the Python DLP pipeline.

## Reproduce

```sh
uv venv tmp/tpch-python --python .venv/bin/python
uv pip install --python tmp/tpch-python/bin/python duckdb==1.4.4 rdflib==7.6.0
tmp/tpch-python/bin/python -m benchmarks.external_tpch --prepare
tmp/tpch-python/bin/python -m benchmarks.external_tpch --blocks 3 --output /tmp/tpch-components-reproduction.json
```

Sources: [DuckDB tpch extension](https://duckdb.org/docs/lts/core_extensions/tpch), [TPC-H specification](https://www.tpc.org/tpc_documents_current_versions/pdf/tpc-h_v3.0.0.pdf).
