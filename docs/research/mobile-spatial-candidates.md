# Spatial libraries for iOS and Android

Checked **10 September 2026**. This note assesses native library and packaging
evidence; it adds no engine feature, dependency, or mobile application. Linked
build recipes and CI configurations were inspected, not executed here. A CI
configuration does not establish that its latest run passed. Undated project
documentation is identified by the retrieval date above.

**Recommendation:** use the same project-owned C ABI on desktop and phones.
Start with **GeographicLib's C geodesic core** for WGS84 point distance and
radius checks. Add **GEOS** when planar polygon/line topology and prepared
geometries are needed; retain **PROJ as an optional CRS-transformation module**.
If static distribution with permissive dependencies is a priority, evaluate
**Boost.Geometry** for the required planar subset before committing to GEOS.
These are architectural recommendations based on the evidence below, not
claims that all candidates are interchangeable or already supported here.

## Evidence by candidate

| Candidate | iPhone/iOS evidence | Android evidence | Implication |
| --- | --- | --- | --- |
| **GEOS** | Downstream `GEOSwift/geos` packages GEOS **3.14.1** as a dynamic SwiftPM library with a public C API, iOS **12+**, and C++17. Its CI specifies an iOS 17.5 simulator build; the higher-level GEOSwift CI specifies simulator tests. | QField has an Android NDK build recipe and CI, and its QGIS port depends explicitly on GEOS. | Concrete downstream mobile packaging/build evidence on both platforms; our wrapper and app still need their own build/runtime validation. |
| **PROJ** | QField supplies iOS arm64 device and simulator recipes; its QGIS port explicitly depends on PROJ. The iOS workflow configures arm64 and packages an app. | The same dependency chain is built through QField's Android workflow, which specifies NDK 28.2 and four ABIs. | Full CRS support is feasible on phones, with additional library and resource packaging. This is downstream evidence, not an upstream mobile SDK promise. |
| **GeographicLib-C** | A downstream Swift package wraps its C sources and declares iOS among supported platforms; its API is labelled work in progress. | The inspected upstream C source and CMake target are portable candidates for NDK compilation; this note did not establish an Android-specific native build/test result. | Smallest dependency surface for the requested WGS84 point metric. Validate the pinned C source on both targets; the optional Swift wrapper need not become a dependency. |
| **Boost.Geometry** | Header-only C++14 is compatible in principle with the intended C++17 build. No candidate-specific iOS execution result was established here. | Same portability inference for NDK C++17; no Android geometry test result established here. | A credible permissive alternative, conditional on testing the exact operations and geometry types. General compiler portability is weaker evidence than a mobile test. |

Primary evidence for the table:

- [GEOS C package README](https://github.com/GEOSwift/geos/blob/main/README.md),
  [its manifest](https://github.com/GEOSwift/geos/blob/main/Package.swift),
  [its build CI](https://github.com/GEOSwift/geos/blob/main/.github/workflows/main.yml),
  and [GEOSwift test CI](https://github.com/GEOSwift/GEOSwift/blob/main/.github/workflows/main.yml).
- [QField mobile development recipes](https://github.com/opengisch/QField/blob/master/doc/dev.md),
  [QGIS dependency manifest](https://github.com/opengisch/QField/blob/master/vcpkg/ports/qgis/vcpkg.json),
  [Android CI](https://github.com/opengisch/QField/blob/master/.github/workflows/android.yml),
  and [iOS CI](https://github.com/opengisch/QField/blob/master/.github/workflows/ios.yml).
  The inspected iOS workflow disables tests and gates substantial steps on
  maintainer secrets; it supplies packaging evidence, not a public device-test
  result. QField's complete Qt/QGIS stack is a reference, not a proposed app
  dependency.
- [GeographicLib-C v2.2 source target](https://github.com/geographiclib/geographiclib-c/blob/v2.2/src/CMakeLists.txt),
  [Swift wrapper](https://github.com/scottrhoyt/geographiclib-swift),
  and [its C-source manifest](https://github.com/scottrhoyt/geographiclib-swift/blob/main/Package.swift).
- [Boost.Geometry compilation requirements](https://www.boost.org/doc/libs/latest/libs/geometry/doc/html/geometry/compilation.html).

Version distinctions matter: upstream GEOS now lists **3.15.0**, released
1 September 2026; the local desktop probe and the inspected SwiftPM package use
**3.14.1**. Online PROJ documentation is **9.8.1**, while the desktop probe used
**9.8.0**. These are separate observations, not a verified combination of the
latest releases. [GEOS releases](https://libgeos.org/usage/download/),
[PROJ installation documentation](https://proj.org/en/stable/install.html),
[retained desktop probe](../../examples/temporal_geo/library_probe/README.md).

## Keep the geodesic kernel separate from CRS transformation

The standalone GeographicLib-C library consists of `geodesic.c` and
`geodesic.h`, with an MIT/X11 license. Its CMake target compiles those files;
the implementation uses standard C mathematical facilities. It does not require
PROJ, SQLite, a CRS database, transformation grids, or networking. This is a
source/dependency observation, not a measured mobile binary size. The official
standalone build supplies tests but no CMake installation rule.
[Standalone documentation](https://geographiclib.sourceforge.io/html/C/standalone.html),
[pinned implementation](https://github.com/geographiclib/geographiclib-c/blob/v2.2/src/geodesic.c).

Use `geod_init` with the chosen ellipsoid and `geod_inverse` for point distance;
the same family also provides direct geodesics and polygon area/perimeter.
That does **not** supply polygon containment, arbitrary geometry distance,
CRS selection, or road-network routing. Preserve explicit latitude/longitude
order, finite input validation and metres at the project boundary.
[C API documentation](https://geographiclib.sourceforge.io/html/C/library.html).

Full PROJ requires C99/C++17, CMake, target-architecture SQLite headers/library,
and a **host** `sqlite3` executable when cross-compiling. TIFF support and curl
can be disabled; nlohmann/json can come from the bundled implementation.
Disabling curl and TIFF does not remove the mandatory SQLite dependency from
the full PROJ build. Start from pinned CMake configuration and test the exact
operations included in the mobile product.
[PROJ requirements](https://proj.org/en/stable/install.html),
[PROJ 9.8.1 CMake configuration](https://github.com/OSGeo/PROJ/blob/9.8.1/CMakeLists.txt).

For EPSG/CRS lookup, bundle a compatible `proj.db` and any required grids,
configure the application resource directory with
`proj_context_set_search_paths`, and explicitly keep network access off for
the offline profile. Some simple explicit operations need fewer resources,
but that is not a general replacement for the database. PROJ documents database
reduction; any reduction must preserve the declared operation set. Missing
grids can affect which transformation is selected, so require the chosen
accuracy/operation and report unavailable resources instead of silently
relaxing the application's contract.
[PROJ resource files and selection controls](https://proj.org/en/stable/resource_files.html).

GEOS assumes Cartesian planar geometry. Passing longitude/latitude directly to
its distance function produces coordinate-space distance, not metres on WGS84.
Keep the planar and geodesic paths distinct and project to a suitable CRS when
using GEOS predicates for a local region.
[GEOS spatial model](https://libgeos.org/usage/faq/).

## GEOS packaging and the permissive alternative

Use GEOS's stable C interface rather than exposing its changing C++ object
model. Create a reentrant context for each executing thread; explicitly own
and release geometries, prepared geometries and indexes. Fixed geofence
geometry can be prepared once and reused as vehicle positions change.
[GEOS C API, lifetime and prepared-geometry guidance](https://libgeos.org/usage/c_api/).

GEOS brings LGPL distribution requirements. Its LGPL 2.1 text includes notices
and library-source requirements, and section 6 describes relinking materials
or a suitable shared-library mechanism among the available routes. Static
archives can therefore entail distributing app object/source material and
build instructions sufficient for relinking; simply supplying an `.a` or
calling through a C ABI does not resolve that issue. The downstream SwiftPM
package deliberately produces a dynamic library and discourages static GEOS.
This is a packaging constraint to review for the intended distribution, not a
legal determination that a particular App Store arrangement complies.
[GEOS license, especially sections 4–6](https://github.com/libgeos/geos/blob/3.14.1/COPYING),
[GEOSwift/geos packaging decision](https://github.com/GEOSwift/geos/blob/main/README.md).

Boost.Geometry is header-only and depends only on other header-only Boost
libraries, so selected operations can compile directly into our C++ module.
Its Boost Software License offers a permissive distribution route. We would
still supply the C ABI and test the required predicates, boundary behavior,
invalid/empty geometries, coordinate strategies and numerical tolerances.
Header-only does not imply zero compiled size or exact GEOS behavior. Treat it
as an alternate implementation of a specified subset, not a drop-in GEOS C API.
[Boost.Geometry requirements](https://www.boost.org/doc/libs/latest/libs/geometry/doc/html/geometry/compilation.html),
[library scope](https://www.boost.org/library/latest/geometry/),
[Boost Software License](https://www.boost.org/LICENSE_1_0.txt).

## Binding and validation plan

The proposed shared boundary is a versioned C ABI with opaque handles,
fixed-width IDs, explicit array lengths, per-result status and deterministic
destruction. Desktop Python calls that ABI through `ctypes`; the native engine
calls it directly; a Swift-facing module and a thin Kotlin/Java JNI layer call
the same implementation. Shapely and pyproj can remain desktop conveniences.
Neither is required inside the phone application.

Package iOS device and simulator builds separately in an XCFramework, and
build Android native libraries once per selected ABI with the NDK toolchain.
Minimum OS/API versions and runtime dependencies belong to the package
contract. These are standard platform mechanisms, not evidence that our
proposed spatial module has already run on either platform.
[Apple XCFramework guidance](https://developer.apple.com/documentation/xcode/creating-a-multi-platform-binary-framework-bundle),
[Android NDK CMake guidance](https://developer.android.com/ndk/guides/cmake).

The first mobile validation should run identical fixtures through the native
API, Swift and JNI: projected 3–4–5 distance and inclusive boundaries;
WGS84 inverse distance including antimeridian/polar cases; polygon boundary
versus interior; invalid inputs and empty geometries; repeated prepared-region
queries; and concurrent context lifetimes. For PROJ, add an offline fresh-install
test with the exact bundled database/grids. Measure binary/resources size,
query latency and memory on real devices before claiming a mobile performance
or battery advantage. The existing desktop
[library probe](../../examples/temporal_geo/library_probe/README.md) verifies
shared C++/Python calls only; the separate
[mobile store build probe](mobile-build-probe.md) has its own narrower scope.
