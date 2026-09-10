# DLP Nova tutorials

Small executable examples accompany the [user guide](../../docs/DLP_NOVA_USER_GUIDE.md),
[base language guide](../../docs/DLP_NOVA_LANGUAGE_GUIDE.md) and
[extension guide](../../docs/DLP_NOVA_EXTENSIONS.md). Run commands from the
repository root after `uv sync --extra dev --locked`.

## Base ontology language

| File | Profile | Purpose |
| --- | --- | --- |
| [base-l0.dlp](base-l0.dlp) | L0 | Class inclusion, complete definitions, existential antecedents, property hierarchy and transitivity |
| [base-local-scope.dlp](base-local-scope.dlp) | L0 | A class-local universal restriction |
| [base-literals.dlp](base-literals.dlp) | L0 | RDF literal storage and has-value classification |
| [base-l1.dlp](base-l1.dlp) | L1 | Functionality, inverse functionality, singleton enumeration and equality |
| [base-l2.dlp](base-l2.dlp) | L2 | Disjointness, complement and zero-cardinality constraints |
| [base-l2-inconsistent.dlp](base-l2-inconsistent.dlp) | L2 | Intentional inconsistency; validation must return exit 2 |
| [base-l3.dlp](base-l3.dlp) | L3 | Finite existential witnesses and minimum cardinality |

```sh
uv run dlp validate examples/dlp_nova/base-l0.dlp --profile L0
uv run dlp instances examples/dlp_nova/base-l0.dlp \
  'https://example.org/nova#KnownParent' --profile L0
uv run dlp values examples/dlp_nova/base-l0.dlp \
  'https://example.org/nova#anna' 'https://example.org/nova#ancestorOf' --profile L0
uv run dlp validate examples/dlp_nova/base-l1.dlp --profile L1
uv run dlp validate examples/dlp_nova/base-l2.dlp --profile L2
uv run dlp validate examples/dlp_nova/base-l2-inconsistent.dlp --profile L2
uv run dlp materialize examples/dlp_nova/base-l3.dlp --profile L3 \
  --include-witnesses -o /tmp/nova-witnesses.ttl
```

The first query finds Anna. The ancestor query returns Lea and Max. Inspect the
language guide for the meanings of the equality and witness examples; different
names alone do not establish different individuals.

## Temporal and spatial rules

[extension-core.dlq](extension-core.dlq) contains the actual version 1 rules.
[extension-demo.py](extension-demo.py) supplies typed inputs and asserts results
for calendar anniversaries, interval validity, nearby active signs, conservative
point-index scans with exact distance refinement, directed-road statuses and
corrected event windows.

```sh
uv run python examples/dlp_nova/extension-demo.py --backend both
# With the optional GEOS C library installed:
uv run python examples/dlp_nova/extension-demo.py --backend both --geos
```

The JSON output reports the actual execution mode. Pure local operations run in
native mode when selected; registered Python provider scans and GEOS calls use
hybrid orchestration. WGS84 distance uses the native domain library on both
backends. The optional geometry example checks that a boundary point is covered
but not contained, and that the distance from `(0,0)` to `(30,40)` is 50 metres
in a declared local metre grid.

Larger worked applications remain in [Bach temporal](../bach_temporal/README.md),
[traffic signs](../traffic_signs/README.md) and
[temporal/geospatial events](../temporal_geo/README.md). The paper's
[evidence collector](../../scripts/collect_dlp_nova_evidence.py) runs those
applications and this extension tutorial, preserves their JSON answers and
records source fingerprints. It requires GEOS and native libraries/build tools.
