# Native ZodiacEdge comparison on the same host

Pinned unmodified upstream engine and local candidate; the exact author 128-rule program on official LUBM(1,0), with its marked eight- and sixteen-rule transactions.

| Subset | Engine | Initial compute(s) | Insert(s) | Delete(s) |
|---|---|---:|---:|---:|
| * | native | 1.400109 | 0.559004 | 0.784984 |
| * | candidate | 2.456711 | 0.088029 | 1.196505 |
| # | native | 1.659507 | 0.058858 | 0.023442 |
| # | candidate | 2.180692 | 0.213821 | 0.970931 |

Each block runs both arms in fresh processes with the same hash seed; their order alternates. All six complete tuple sets per worker must match frozen naive references. No author engine code is changed. Only positive variable-only rules are evaluated; no claim about negation, aggregation, or full OWL conformance follows.

The author's Program constructor performs reasoning. Native initial compute therefore includes indexed DataStore construction plus Program construction; both components are also recorded separately. Local initial compute includes Engine construction plus materialization. RDF parsing, representation conversion, rule parsing, and result validation are outside compute timing; native conversion is recorded separately. Peak RSS includes parsing, representation conversion, and validation; it is not isolated engine storage usage.

Native unary atoms retain the author's rdf:type encoding. RDF constants are injectively tagged by type, lexical form, datatype and language before entering the author's opaque constant model; output is decoded before comparison. These representation differences are part of the systems, not a common physical plan.

This small same-host execution does not reproduce the unspecified hardware or original data bytes of the author's published LUBM timing table.
