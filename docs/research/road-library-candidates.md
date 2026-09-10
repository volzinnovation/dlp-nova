# Road and lane libraries for both backends

Checked **10 September 2026** against upstream documentation, tagged source,
release pages and the actual PyPI release files. This is a library selection
note; nothing was installed, benchmarked, or integrated. Geometry libraries
remain responsible for ordinary distance/intersection operations. The libraries
below add road connectivity, routing costs, map matching and lane semantics.
The mobile addendum includes inspection of published archives, but no device
build or execution.

## Recommended choice

Use **Valhalla as the first optional road-routing provider**, with its official
Python `Actor` and C++ `valhalla::tyr::actor_t` behind one provider contract.
For **iPhone/iOS and Android**, retain Valhalla as the first offline candidate,
but use a mobile native wrapper rather than desktop Python wheels. The verified
downstream `valhalla-mobile` package is concrete evidence of mobile delivery;
its older core and narrower API require deliberate parity checks. Keep Lanelet2
off the initial mobile dependency path unless lane-level processing on the phone
is necessary and its native port has been demonstrated. See the addendum below.
It offers the useful combination of routes, matrices, trace matching,
isochrones and request-specific costing, including departure/arrival time.
Choose **Lanelet2 additionally when curated lane-level maps and traffic-sign
applicability are required**. It supplies lane relations and regulatory-element
interpretation that a road router alone does not establish. These are project
recommendations based on the documented APIs, not measured rankings.
[Valhalla Actor](https://valhalla.github.io/valhalla/bindings/python/api/actor/),
[routing options](https://valhalla.github.io/valhalla/api/route/api-reference/),
[Lanelet2 routing](https://raw.githubusercontent.com/fzi-forschungszentrum-informatik/Lanelet2/master/lanelet2_routing/README.md)

**OSRM is a credible alternative with official Python bindings now available.**
It should no longer be described as C++ plus Python HTTP wrappers only.
Prefer it if its prepared-profile routing and matrix contract fits the measured
workload better. HTTP remains an optional deployment interface for both routers;
it is not required for Python access.
[OSRM Python bindings, release 26.9.0](https://raw.githubusercontent.com/Project-OSRM/osrm-backend/v26.9.0/src/python/README.md)

## Verified release and installation availability

| Library | Release evidence | Software license | Actual published Python artifacts |
| --- | --- | --- | --- |
| Valhalla / `pyvalhalla` | 3.8.3; upstream release notes date 24 July 2026, PyPI upload 25 July | MIT | CPython 3.12+ `abi3`: Linux x86_64/aarch64, glibc 2.28+; macOS 14+ arm64; Windows amd64. Source distribution also present; package metadata permits Python 3.9+. |
| OSRM / `osrm-bindings` | 26.9.0; released/uploaded 1 September 2026 | BSD-2-Clause | CPython 3.12+ `abi3`: Linux x86_64/aarch64, glibc 2.28+; macOS 15+ arm64/x86_64. Source distribution present; Python 3.10+ for source builds. No Windows wheel in this release's PyPI file list. |
| Lanelet2 / `lanelet2` | 1.2.3; released/uploaded 18 June 2026 | BSD-3-Clause | Linux x86_64 wheels for CPython 3.8–3.13. For 3.10–3.13 the tag requires glibc 2.31+; 3.8 uses 2.27+, 3.9 includes 2.26/2.27 tags. No macOS/Windows wheel or source distribution in this PyPI release. |

Release sources:
[Valhalla](https://github.com/valhalla/valhalla/releases),
[OSRM](https://github.com/Project-OSRM/osrm-backend/releases),
[Lanelet2](https://github.com/fzi-forschungszentrum-informatik/Lanelet2/releases).
Artifact sources:
[pyvalhalla 3.8.3 files](https://pypi.org/project/pyvalhalla/3.8.3/#files),
[osrm-bindings 26.9.0 files](https://pypi.org/project/osrm-bindings/26.9.0/#files),
[lanelet2 1.2.3 files](https://pypi.org/project/lanelet2/1.2.3/#files).
License texts:
[Valhalla](https://raw.githubusercontent.com/valhalla/valhalla/master/COPYING),
[OSRM](https://raw.githubusercontent.com/Project-OSRM/osrm-backend/v26.9.0/LICENSE.TXT),
[Lanelet2](https://raw.githubusercontent.com/fzi-forschungszentrum-informatik/Lanelet2/1.2.3/LICENSE).

There are documentation discrepancies: OSRM's README advertises a Windows wheel
and omits Linux aarch64 from one table; Lanelet2's README still says Python
3.8–3.11. The artifact table above records the actual inspected release files.
It does not imply that an unlisted platform cannot build from source.
[OSRM binding README](https://raw.githubusercontent.com/Project-OSRM/osrm-backend/v26.9.0/src/python/README.md),
[Lanelet2 README](https://github.com/fzi-forschungszentrum-informatik/Lanelet2)

This repository currently permits Python 3.11. A wheel-only optional Valhalla or
OSRM integration therefore needs an explicit Python 3.12+ environment policy;
otherwise allow and document the native source build. Lanelet2 needs a Linux
deployment or a separately verified build on this macOS workspace. Recent
releases establish current maintenance activity, not a support SLA or evidence
that this repository's workload has been tested.

## Valhalla: broad road-network provider

The public Python entry point is `from valhalla import Actor, get_config`;
construct `Actor(config)` once and call `route`, `matrix`, `locate`,
`trace_route`, `trace_attributes`, or `isochrone`. Requests accept dictionaries
or JSON strings. These bindings wrap native computation rather than calling an
HTTP server. The C++ actor provides corresponding methods and can receive a
preconstructed `GraphReader`; methods accept JSON and optionally an `Api`
protobuf object, and support an interrupt callback. This is a concrete route
to persistent native graph ownership.
[Python Actor API](https://valhalla.github.io/valhalla/bindings/python/api/actor/),
[C++ actor header](https://raw.githubusercontent.com/valhalla/valhalla/master/valhalla/tyr/actor.h)

Installation alone supplies no routable map. Download a chosen OSM PBF extract,
create a configuration, run `valhalla_build_tiles`, and configure the resulting
tile directory/extract for the actor. The Python package includes selected data
tools, accessible through `python -m valhalla`, and separate configuration/extract
scripts. Record the input extract and build configuration as the graph version.
[Binding installation and graph preparation](https://valhalla.github.io/valhalla/bindings/python/)

Native builds require more than this project's current C++17 standard-library
backend: the released 3.8.3 build defaults to **C++20**, with Boost, Protobuf and
additional feature-dependent libraries. Upstream documents Linux, macOS and
Windows builds. Keep the provider separately packaged and built.
[3.8.3 CMake configuration](https://raw.githubusercontent.com/valhalla/valhalla/3.8.3/CMakeLists.txt),
[build guide](https://valhalla.github.io/valhalla/start/building/)

Two contracts matter for reasoning. First, default routing optimizes its costing
model, not necessarily metres. `shortest=true` removes other costs but may still
be suboptimal because of hierarchy pruning. The documented optimal-path option
disables pruning only for supported modes and within configured distance limits.
Second, public `date_time` supports specified departure, arrival and invariant
time, with mode restrictions; its string is local time at the relevant location.
An adapter must resolve this explicitly from the engine's instant/timezone policy.
[Costing and date/time contracts](https://valhalla.github.io/valhalla/api/route/api-reference/)

Traffic-aware costs require supplied data. Valhalla documents historical speed
profiles and a separately produced live traffic overlay, with configured speed
selection. A live GPS stream does not automatically become traffic speeds.
Version traffic inputs alongside the road graph and costing configuration;
route-time support does not implement general temporal rule reasoning.
[Valhalla speed information](https://valhalla.github.io/valhalla/concepts/speeds/)

## OSRM: direct C++ and Python access, plus HTTP

`libosrm` exposes `osrm::OSRM(EngineConfig&)`, typed `RouteParameters`,
`TableParameters`, `MatchParameters` and related requests. Calls fill structured
results and return a status. Official Python bindings are built alongside that
library and share its version. Their documented example constructs
`osrm.OSRM(dataset_base)`, builds
`osrm.RouteParameters(coordinates=[(longitude, latitude), ...])`, and calls
`engine.Route(parameters)` to obtain a Python result. Use the exact binding
package name `osrm-bindings`; unrelated packages named similarly are not evidence
of upstream support.
[C++ API](https://raw.githubusercontent.com/Project-OSRM/osrm-backend/v26.9.0/include/osrm/osrm.hpp),
[Python API example](https://raw.githubusercontent.com/Project-OSRM/osrm-backend/v26.9.0/src/python/README.md)

Prepare OSM PBF data with an extraction-time Lua profile using `osrm-extract`.
The recommended MLD pipeline then uses `osrm-partition` and `osrm-customize`;
CH instead uses `osrm-contract`. Configure the matching algorithm when opening
the dataset. The `.osrm` base denotes a family of files. Reuse the loaded
instance; do not repeat preprocessing per query. Upstream supplies Docker images
and native CMake/vcpkg build instructions requiring C++20. The Python binding
itself offers read-only routing access, not a streaming graph editor.
[Upstream build and data preparation](https://github.com/Project-OSRM/osrm-backend)

Do not expose `Table(..., distance)` as minimum road distance: the API explicitly
returns the distance **along the fastest route**, in metres; durations are in
seconds. Snapping, travel direction and routing profile affect answers. A missing
route is distinct from a failed snap; matrix `null` values must remain explicit.
Do not enable straight-line fallback estimates for a predicate claiming proven
network reachability. Trace timestamps assist map matching; the inspected Route
API does not advertise a Valhalla-style departure/arrival-time routing parameter.
[Release 26.9.0 HTTP/service semantics](https://raw.githubusercontent.com/Project-OSRM/osrm-backend/v26.9.0/docs/http.md)

## Lanelet2: lane and traffic-rule semantics

Lanelet2 is a C++ map framework with Python bindings, targeting high-definition
lane maps. Its OSM-format reader does **not** make arbitrary ordinary OSM extracts
valid Lanelet2 maps. Supply lane boundaries, connectivity, regulatory elements
and a correct local projection/origin; run map validation. Native installation
is Linux-oriented through ROS/Catkin, with an experimental Conan route. Its
documented dependency set includes Boost/Python, Eigen, pugixml and GeographicLib;
C++14 or newer is required.
[Upstream scope and installation](https://github.com/fzi-forschungszentrum-informatik/Lanelet2)

Both languages build a `RoutingGraph` from a map, country/participant-specific
traffic rules and routing costs. It exposes shortest paths, reachable sets,
following lanes, permitted lane changes and merely adjacent lanes. Costs may
represent length or travel time and can include lane-change penalties: declare
the selected cost instead of interpreting every result as pure metres. Python
`shortestPath` returns `None` when no path exists.
[Routing graph API](https://raw.githubusercontent.com/fzi-forschungszentrum-informatik/Lanelet2/master/lanelet2_routing/README.md)

The traffic-rule interface supplies `canPass` and `speedLimit` and extension
points for country/participant interpretation. The matching module offers
distance-based and covariance-aware pose matching, with explicit filtering of
rule-incompatible matches. This helps distinguish an adjacent opposite-direction
lane from an applicable lane; it does not establish that a particular noisy
observation has one certain lane assignment.
[Traffic rules](https://raw.githubusercontent.com/fzi-forschungszentrum-informatik/Lanelet2/master/lanelet2_traffic_rules/README.md),
[matching in C++ and Python](https://raw.githubusercontent.com/fzi-forschungszentrum-informatik/Lanelet2/master/lanelet2_matching/README.md)

An essential live-data limitation: the default implementation ignores regulatory
elements marked dynamic. Time-dependent closures, wet-road limits or traffic-light
states require a specialized traffic-rule implementation and explicit state.
Do not claim that installing Lanelet2 implements them. Rebuild/version affected
routing state when those rules change; automatic incremental propagation is not
established by these APIs.
[Regulatory-element semantics](https://raw.githubusercontent.com/fzi-forschungszentrum-informatik/Lanelet2/master/lanelet2_core/doc/RegulatoryElementTagging.md)

## Provider contract for this engine

The following are integration recommendations, not upstream API guarantees:

- Keep `snap_candidates`, `match_trace`, `route`, `route_matrix` and
  `lane_applicability` distinct. Preserve ambiguity, unmatched observations and
  unreachable destinations rather than converting them into zero distance.
- Tie every edge/lane identifier to a provider graph version. Join stable sign
  identifiers to that mapping and ontology revision. Graph rebuilds may change
  provider identifiers even when the RDF individual is unchanged.
- Return route distance, duration and optimization objective separately. For
  “sign ahead,” retain lane/direction and longitudinal position; proximity and
  generic shortest paths do not by themselves define sign applicability.
- Reuse native providers across queries; batch candidates/matrices. Separate
  map replacement from moving observation updates. Cache on graph/traffic/rules
  revisions, profile, exact endpoints, snapping options and relevant time.
- Expose providers through an optional module and stable project-owned boundary.
  A Python wheel and a separately linked C++ library do not automatically share
  one graph allocation. Validate ownership and concurrency before sharing handles.
- Python and C++ wrappers around the same routing implementation demonstrate API
  parity, not independent algorithmic correctness. Add tiny hand-checked networks
  with one-way roads, disconnected components and alternative costs.

Software licenses do not cover all map and traffic inputs. OSM data is ODbL and
has attribution requirements; selected elevation, traffic and HD-map datasets
retain their own terms. Track these separately in the provider's dataset manifest.
[Valhalla's official data-source/license inventory](https://valhalla.github.io/valhalla/contributing/data/data-sources/)

## Mobile addendum: iPhone/iOS and Android

### What is demonstrated, and what is not

| Candidate | Verified mobile evidence | Recommended role |
| --- | --- | --- |
| Valhalla | Upstream says the engine is used on iOS/Android. Rallista's separate MIT-licensed `valhalla-mobile` 0.6.3 has published Swift/XCFramework and Kotlin/AAR packages, inspected below. | First optional on-device regional/offline router. This is a downstream integration, not an upstream promise that every current desktop API is packaged for phones. |
| OSRM | An upstream maintainer described successful native mobile ports in 2023, with substantial platform integration work. The inspected current release/build presets establish desktop platforms, not a maintained mobile SDK or phone artifact. | Server provider initially; on-device use remains a separately tested cross-compilation project. C++ source availability alone is insufficient evidence. |
| Lanelet2 | Upstream installation targets Linux/ROS/Catkin, with an experimental Conan route; the inspected Python artifacts are Linux x86_64. No current iOS/Android package or supported build recipe was established in this review. | Keep lane-rule preparation on a server/workstation initially, or ship versioned derived lane relations. A full on-device Lanelet2 port is conditional work. |

Sources:
[Valhalla 3.8.3 platform statement](https://raw.githubusercontent.com/valhalla/valhalla/3.8.3/README.md),
[mobile wrapper 0.6.3](https://raw.githubusercontent.com/Rallista/valhalla-mobile/0.6.3/README.md),
[OSRM maintainer discussion](https://github.com/Project-OSRM/osrm-backend/discussions/6824),
[OSRM 26.9.0 presets](https://raw.githubusercontent.com/Project-OSRM/osrm-backend/v26.9.0/CMakePresets.json),
[Lanelet2 1.2.3 installation](https://raw.githubusercontent.com/fzi-forschungszentrum-informatik/Lanelet2/1.2.3/README.md).

These evidence levels distinguish a published mobile package, historical reports
of ports, and an unverified port. Absence of a verified recipe is not a claim
that OSRM or Lanelet2 cannot run on a phone. Desktop macOS arm64 and Linux
aarch64 Python wheels are not iOS and Android binaries.

### The concrete Valhalla mobile package

Rallista released **0.6.3 on 28 August 2026**. This review downloaded its public
archives to temporary directories and inspected their contents without installing
or executing them:

| Target | Inspected artifact | Declared minimum / integration |
| --- | --- | --- |
| iPhone | XCFramework `Info.plist`: `ios-arm64`, containing static `libvalhalla_all.a` | Swift package declares iOS 16.4+; Swift API and Objective-C++ bridge |
| iOS Simulator | Same archive: `ios-arm64_x86_64-simulator` | arm64 and x86_64 simulator slice, distinct from the device slice |
| Android | Maven AAR contains `libvalhalla-wrapper.so` for `arm64-v8a`, `armeabi-v7a`, `x86_64`, `x86` | Gradle declares API 24 minimum, compile SDK 36; Kotlin API and JNI bridge |

The inspected Android AAR has no Prefab package: consuming its Kotlin/JNI API
does not automatically supply a packaged C++ development interface. The source
build scripts provide Xcode/vcpkg and Android NDK/vcpkg recipes. The recorded
development NDK is 29.0.14206865. These are package/toolchain declarations and
archive contents, not test results on supported devices.
[Release and XCFramework](https://github.com/Rallista/valhalla-mobile/releases/tag/0.6.3),
[Swift manifest](https://raw.githubusercontent.com/Rallista/valhalla-mobile/0.6.3/Package.swift),
[Android manifest/build](https://raw.githubusercontent.com/Rallista/valhalla-mobile/0.6.3/android/valhalla/build.gradle.kts),
[published Maven metadata](https://repo1.maven.org/maven2/io/github/rallista/valhalla-mobile/0.6.3/valhalla-mobile-0.6.3.pom),
[AAR](https://repo1.maven.org/maven2/io/github/rallista/valhalla-mobile/0.6.3/valhalla-mobile-0.6.3.aar),
[build prerequisites](https://raw.githubusercontent.com/Rallista/valhalla-mobile/0.6.3/docs/development.md)

The tagged source pins Valhalla commit
`e2f017b16080f49203de245a211b09efab09cf72`, exactly upstream **3.6.3**, rather than
the desktop **3.8.3** examined above. Its `.gitmodules` points at upstream;
the architecture note's older reference to a Rallista core fork is stale. No
separate core patch series was found in the inspected tagged tree/build scripts.
The mobile wrapper and its configuration/model layer still constitute additional
code, so an upstream core pin alone does not prove cross-platform parity.
[Pinned submodule metadata](https://api.github.com/repos/Rallista/valhalla-mobile/contents/src/valhalla?ref=0.6.3),
[upstream 3.6.3 commit](https://github.com/valhalla/valhalla/tree/e2f017b16080f49203de245a211b09efab09cf72),
[submodule declaration](https://raw.githubusercontent.com/Rallista/valhalla-mobile/0.6.3/.gitmodules)

Both mobile wrappers expose `route`, `trace_route`, `trace_attributes`, `height`
and `sources_to_targets` (matrix). They do not expose `isochrone`, `locate`,
`optimized_route` or `expansion`; PBF responses are unsupported. Elevation needs
its own tiles. This is materially narrower than the Python Actor API.
[Tagged support matrix](https://raw.githubusercontent.com/Rallista/valhalla-mobile/0.6.3/README.md)

The mobile build disables data tools, Python bindings, the HTTP service and
Valhalla's curl path. A wrapper-specific tile-fetch hook still allows network
access when configured; offline behavior requires preloaded data and an explicit
network policy. Calls use one serialized actor and synchronously join a worker
with a 16 MiB stack reservation to accommodate long matching traces. Keep calls
off the UI thread, bound trace/matrix sizes, and measure peak memory. That stack
reservation is not a claim of 16 MiB resident memory per call.
[Mobile build switches](https://raw.githubusercontent.com/Rallista/valhalla-mobile/0.6.3/src/CMakeLists.txt),
[actor/thread/tile-fetch implementation](https://raw.githubusercontent.com/Rallista/valhalla-mobile/0.6.3/src/wrapper/valhalla_actor.cpp)

Before expecting desktop/mobile equality, align core version, graph build,
costing defaults, timezone data and request/config models. The wrapper's upgrade
instructions explicitly warn that unrepresented config fields can be silently
dropped by model decoding. Test the actual serialized request that reaches each
core, not only similarly named application methods.
[Wrapper upgrade and configuration contract](https://raw.githubusercontent.com/Rallista/valhalla-mobile/0.6.3/docs/src/bumping-valhalla.md)

### Refined deployment choice

For offline use, prepare regional graph tiles on a build machine and distribute
a versioned bundle containing the applicable road graph, sign/lane relations
and required auxiliary data. Run the mobile native provider against that bundle;
keep the desktop Python interface as tooling/reference access. Do not put Python
wheel installation or native graph preprocessing into the phone's query path.
This is the proposed architecture, not a new library capability.

Offer a server provider for large coverage, expensive matrices and centrally
updated traffic when connectivity is available. It must advertise its graph and
traffic revisions, because silently switching from an older offline graph to a
newer server graph changes the dataset. Offline “unreachable” also needs a
coverage qualification: a route may leave the downloaded region. Test region
edges, air-plane-mode operation, missing/corrupt tiles, replacement during active
queries, device suspension, cancellation and memory pressure. No mobile latency,
battery, storage or capacity result has been measured here.

Map presentation is a separate choice. MapLibre Native provides an iOS/Android
renderer; render tiles and an offline map view do not supply the routing graph
or our sign-applicability rules. MapKit does offer `MKDirections`, but its
documented calculation asks Apple's servers. Google separates Maps SDK mapping
from its Navigation SDK's routing/navigation functions. These are useful product
APIs, but adopting them does not demonstrate the same versioned road dataset,
cost model and rule semantics on Python, C++, iOS and Android.
[MapLibre architecture](https://maplibre.org/maplibre-native/docs/book/design/ten-thousand-foot-view.html),
[Apple MKDirections](https://developer.apple.com/documentation/mapkit/mkdirections),
[Google Maps SDK](https://developers.google.com/maps/documentation/android-sdk/overview),
[Google Navigation SDK](https://developers.google.com/maps/documentation/navigation/android-sdk)
