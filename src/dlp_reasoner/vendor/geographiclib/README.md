# Pinned GeographicLib C geodesic core

Unmodified `geodesic.c`, `geodesic.h` and `LICENSE.txt` from upstream
[geographiclib/geographiclib-c](https://github.com/geographiclib/geographiclib-c),
release **v2.2**, tagged **2025-08-19**. The annotated tag
`0876b89abea6c6473667fad9cbde4cb064ca2649` points to commit
[`321c9a61359661fc2afa650dc888f5b1f5652443`](https://github.com/geographiclib/geographiclib-c/tree/321c9a61359661fc2afa650dc888f5b1f5652443).
The header reports API version 2.2.0. License: MIT, retained in LICENSE.txt.

| File | SHA-256 |
| --- | --- |
| geodesic.c | `87a91e0e30e7db839cbd1ef5aafea77487524958070565ff9155e50e9bead550` |
| geodesic.h | `a964a747bc4f388fb3a93cc9bc379aebe4cdd78b3ee909c071be711b82db4b10` |
| LICENSE.txt | `44e8d5e992a01915a3522d48296b8a684df5641e8162be44431c9911b9e9f32b` |

Verified against the tagged upstream files and tag metadata on 2026-09-10.
The [standalone documentation](https://geographiclib.sourceforge.io/html/C/standalone.html)
describes the two-file C library. Builds compile geodesic.c as C99 and link it
with our C++17 domain ABI. This replaces the default domain build's dependency on
full PROJ; no data grids or runtime downloads are required for WGS84 point distance.
PROJ remains a separately selected CRS-transformation capability, not provided by
this library. `DLP_DOMAIN_GEODESIC=0` explicitly omits geodesic capability.

Our public point API takes longitude then latitude. The domain adapter explicitly
passes latitude then longitude to `geod_inverse`, as required by its C API.
Our ellipsoid is WGS84: a=6378137 metres, f=1/298.257223563. The native version
function reports `GeographicLib-C-2.2.0` rather than a PROJ package version.
