# Official LUBM(1,0) evaluation

UBA1.7, index 0, seed 0; full official ontology under L3; all 14 official reference answer sets.

These are new same-host measurements, separate from the frozen b1254c4 thesis suite.
Queries use RDFLib parsing plus the existing DLP indexed BGP join evaluator; this adapter is not a general SPARQL frontend.

| Configuration | Parse + reasoner(s) | Compile(s) | Materialize(s) | Export(s) | All queries(s) | PeakRSS(MiB) |
|---|---:|---:|---:|---:|---:|---:|
| b1254c4 | 7.423 | 1.379 | 3.322 | 2.373 | 0.218 | 984.0 |
| current-fixed | 7.218 | 1.362 | 3.180 | 2.319 | 0.151 | 983.9 |
| current-adaptive | 7.387 | 1.395 | 3.310 | 2.274 | 0.151 | 983.7 |

| Query | Official answers | Exact match(all workers) | Baseline(ms) | Current fixed(ms) | Adaptive(ms) |
|---|---:|---|---:|---:|---:|
| Q1 | 4 | yes | 0.051 | 0.052 | 0.051 |
| Q2 | 0 | yes | 0.303 | 0.327 | 0.297 |
| Q3 | 6 | yes | 0.041 | 0.046 | 0.040 |
| Q4 | 34 | yes | 0.890 | 0.854 | 0.873 |
| Q5 | 719 | yes | 3.471 | 3.027 | 3.034 |
| Q6 | 7790 | yes | 11.781 | 11.895 | 11.851 |
| Q7 | 67 | yes | 0.615 | 0.621 | 0.587 |
| Q8 | 7790 | yes | 80.428 | 78.831 | 77.853 |
| Q9 | 208 | yes | 109.780 | 44.678 | 45.876 |
| Q10 | 4 | yes | 0.045 | 0.045 | 0.042 |
| Q11 | 224 | yes | 1.045 | 0.925 | 0.937 |
| Q12 | 15 | yes | 0.383 | 0.358 | 0.354 |
| Q13 | 1 | yes | 0.014 | 0.015 | 0.013 |
| Q14 | 5916 | yes | 8.768 | 8.831 | 8.999 |

## Interpretation and limits

9 fresh processes; balanced configuration order; three repeats per configuration by default. Raw observations, process/source hashes, upstream artifact hashes and generated-file hashes are in the JSON.
The ontology's existential consequents require L3. No logical axioms are removed; imports are resolved locally. Query bindings include only named individuals/literal values, as in the official extensional answer files. Skolem witnesses are still present throughout full materialization.
Official query punctuation errors and the old namespace are normalized without changing atoms/projections. Reference files use lexical strings; full typed RDF-term digests separately validate closure stability.
All14 query answer sets, not just cardinalities, are compared with the official reference files. Repeated workers additionally compare full internal closures within each configuration and named UB closures across configurations; this is not an independent proof of every unqueried consequence.
The two experimental certificate switches concern deletions and are inactive in this static workload. The adaptive unary candidate is compared with the current fixed default. Three repeats and one small university qualify correctness/performance; they do not establish scalability or statistical superiority.
Cold means fresh Python process; OS filesystem caches are not flushed. Query preparation is outside timing; each BGP is run once per worker through Engine._solutions and fully consumed inside its timer. Parse, reasoner, RDF export and query times are separated. Peak RSS includes loading, materialization, export, queries and validation in that process.
Absolute wall times cannot be ranked against published systems on different hardware, software, storage, entailment regimes or query pipelines.

## Reproduce

```sh
python -m benchmarks.lubm --prepare
python -m benchmarks.lubm --blocks 3 --output /tmp/lubm-reproduction.json
```

Sources: [official LUBM project](https://swat.cse.lehigh.edu/projects/lubm/), [official reference answers](https://swat.cse.lehigh.edu/projects/lubm/answers.htm), [official ontology](https://swat.cse.lehigh.edu/onto/univ-bench.owl), [official query text](https://swat.cse.lehigh.edu/projects/lubm/queries-sparql.txt).
