# Ahead-of-time native builds

The root CMake target `dlp_native` packages the persistent relation store,
standalone Horn runtime, typed domain kernels, resident spatial index, native
event windows, finite query interpreter and native `.dlpn` package loader in one
library. It needs a 64-bit Clang/GCC toolchain with C99, C++17 and `__int128`.
Runtime execution needs no Python, RDFLib, compiler, PROJ, downloads or network.
The native headers remain the complete C interface; `include/module.modulemap`
exposes them to Swift as `CDLP`.

The `.dlq` authoring parser/planner, scoped query selections and provider registry
remain Python components. A phone host loads a compiled `.dlpn` package or supplies
compiled IR and term dictionaries through the C ABI. The native query interpreter
executes supported local relation joins, typed scalar operations, filters and
aggregates without Python. The package loader validates and materializes Horn
data, then prepares an independently owned query context with explicit parameters.
Hosts supply scoped selection rows and provider results where needed; the loader
does not invent completeness certificates or external-provider behavior.
The standalone native window
ABI maintains its own event state/checkpoints without Python; see
[native windows](../docs/NATIVE_WINDOWS.md). The C headers expose these full native
interfaces; the small Swift/Kotlin convenience wrappers cover the subset below.
No GEOS/PROJ, road router, timezone database, OSM downloader or mobile map SDK is
included in this library.

## Builds and wrappers

Run these commands from the repository root. The scripts use installed tools and
local vendored sources only. Choose a fresh output directory for each retained
Apple artifact; an existing XCFramework is preserved rather than overwritten.

```sh
# macOS/Linux C++ smoke; macOS also builds and executes Swift 6 convenience calls.
mobile/smoke_host.sh tmp/mobile-host

# macOS iOS static library + XCFramework; Xcode and iOS SDKs required.
mobile/build_apple.sh dist/mobile/apple
mobile/smoke_simulator.sh dist/mobile/apple

# Android native libraries; requires an installed NDK, performs no installation.
ANDROID_NDK_HOME=/path/to/installed/ndk mobile/build_android.sh dist/mobile/android
# Run C++ and Kotlin/JNI checks on an already running 64-bit Android emulator.
DLP_ANDROID_SERIAL=emulator-5560 DLP_TEST_JNI=1 mobile/smoke_android.sh dist/mobile/android

# Record source/toolchain/cache settings and binary SHA-256 after a settled build.
python3 mobile/build_manifest.py dist/mobile/apple
```

The simulator smoke uses an **already booted** simulator and runs a local test
executable; it does not install or launch an application. It signs that local
executable ad hoc, requiring no signing identity or account. Apple libraries are
static, so no application signing occurs during XCFramework construction.

| Artifact | Chosen target | What was actually checked on 2026-09-10 |
| --- | --- | --- |
| iPhone library | arm64, deployment iOS 15.0 | C/C++ crosscompile, Swift module compile, XCFramework slice |
| iOS simulator library | arm64 + x86_64, deployment iOS 15.0 | Universal library crosscompile; Swift/Horn, windows, query and package execution on arm64 iPhone 17 Pro simulator, iOS 26.5 |
| macOS host | arm64 | Four C++ smokes, Swift 6 and Kotlin/JNI on JRE 17; 99 Python tests using the aggregate precompiled binary |
| Android native libraries | arm64-v8a + x86_64, API 24 | Both crosscompiled with NDK r30; native Horn/query/windows and Kotlin/JNI executed on arm64 API 36 emulator with 4 KiB pages |

Artifact hashes, toolchain details, commands and limitations are retained in the
[validation note](../docs/MOBILE_BUILD_VALIDATION.md) and its
[machine-readable record](validation/2026-09-10.json).

iOS 15 is the recipe's deployment minimum, **not evidence of execution on iOS 15
or physical iPhone hardware**. `DLP_IOS_MINIMUM` can select a higher deployment
target. The build found and removed an accidental dependency on Apple's iOS 26
floating `std::from_chars`; decimal-to-double conversion uses the classic locale
with strict parsing. Both iOS device and simulator sources compile after that fix.

`swift/DLPRuntime.swift` owns a native handle, serializes calls and close with an
`NSLock`, and frees the handle in `deinit`. Use an application worker for inference.
`android/NativeRuntime.kt` uses synchronized calls and explicit `Closeable.use`
ownership; it has no finalizer. Its JNI adapter rejects invalid IDs, excessive
argument/key sizes, and use after close. Ordinary UTF-8 byte arrays preserve
Unicode ordering keys instead of JNI's modified UTF-8 string representation.
The Kotlin wrapper accepts positive signed 64-bit IDs; the C/Swift ABI supports
unsigned 64-bit IDs. Import `consumer-rules.pro` when shrinking Android classes;
renaming the Kotlin package also requires updating the JNI symbol names.

Both runtime wrappers provide scalar term/fact insertion, a unary inclusion
convenience, materialization, bounded fact pages and WGS84 distance. The separate
`DLPWindowStore.swift` and `NativeWindowStore.kt` wrappers own native windows and
support event insertion, explicit clock advancement and checkpoint/resume.
Swift exposes active/history change rows; Kotlin exposes change counts, with full
row iteration available through the native C API. These wrappers cover a small
tested subset and are not complete user-facing mobile apps or package readers.
Fact pages default to 256 rows, enforce 4096 row/arity ceilings and a one-million
cell total cap. Term ordering keys are bounded at 1 MiB. Hosts must set native
reasoning limits appropriate to the dataset and device budget.

For Android, copy the generated `jniLibs/` into an application's native-library
source set, include the Kotlin wrapper and retain the generated `licenses/`.
This recipe uses one shared library with the C++ runtime linked statically.
An app combining other C++ libraries must audit its C++ runtime/link strategy;
only the C ABI crosses this library boundary. The recipe sets 16 KiB ELF page
alignment; APK/AAB alignment and execution on 16 KiB devices still require app
packaging validation. Google's guidance recommends NDK r28+ and AGP 8.5.1+ for
default support, and distinguishes library ELF alignment from APK ZIP alignment.
See [Android's page-size guide](https://developer.android.com/guide/practices/page-sizes)
and [NDK CMake configuration](https://developer.android.com/ndk/guides/cmake).
The build scripts do not download an NDK. Validation used an isolated official
NDK r30 archive after verifying the existing SDK license acceptance; no new license
was accepted and no global SDK configuration was changed. No Android AAR, APK or
AAB was built. The installed Kotlin 2.3.10 compiler and build-tools 36.1.0 D8
produced metadata compatibility warnings while generating the smoke DEX; the DEX
executed successfully. `smoke_android.sh` retains those diagnostics in `d8.log`.
Production app builds should select matching Kotlin/D8 versions.

The portable smoke fixture at `fixtures/query.dlpn` contains a Horn inclusion,
two integer inputs, arithmetic, grouped `MIN` and a filter. The native package
smoke loads and materializes it, prepares a query, releases the package, then
executes the independent query and checks the answer `3`. The fixture is authored
once with `.venv/bin/python mobile/generate_fixture.py`; `--check` verifies its
deterministic bytes. Neither execution nor mobile builds invoke that authoring
script or require Python.

For Apple, link `DLP.xcframework`, add the required Swift wrappers, make its headers/module
visible to the app target, link libc++, and retain the adjacent `licenses/` in
the application's license notices. The public native headers are installed.

To exercise the JNI wrapper on a desktop JDK, without an Android toolchain:

```sh
JAVA_HOME=/path/to/jdk DLP_TEST_JNI=1 mobile/smoke_host.sh tmp/mobile-jni-host
```

## Shared geodesic implementation

WGS84 distance uses vendored **GeographicLib-C 2.2.0**, upstream tag `v2.2`
(2025-08-19), commit `321c9a61359661fc2afa650dc888f5b1f5652443`, under MIT.
The unmodified two-file C library is compiled as C99. Its exact source hashes,
upstream links and license are retained in
[the vendor note](../src/dlp_reasoner/vendor/geographiclib/README.md).
The same C code supplies Python's native domain backend and these mobile builds.
Points are longitude/latitude in the public ABI; the adapter reverses the argument
order for GeographicLib's latitude/longitude inverse function. Distances are
WGS84 ellipsoidal metres, not road lengths. Howard Hinnant `date.h` v3.0.5 remains
vendored with its MIT notice for calendar arithmetic.

Desktop Python can load the aggregate binary without invoking a compiler:

```sh
export DLP_NATIVE_LIBRARY=/absolute/path/to/libdlp_native.dylib
export DLP_DOMAIN_LIBRARY="$DLP_NATIVE_LIBRARY"
export DLP_RUNTIME_LIBRARY="$DLP_NATIVE_LIBRARY"
export DLP_SPATIAL_LIBRARY="$DLP_NATIVE_LIBRARY"
export DLP_WINDOWS_LIBRARY="$DLP_NATIVE_LIBRARY"
export DLP_QUERY_LIBRARY="$DLP_NATIVE_LIBRARY"
export DLP_PACKAGE_LIBRARY="$DLP_NATIVE_LIBRARY"
```

Each loader checks its ABI. Explicit missing/incompatible libraries fail instead
of silently compiling or falling back. The Python default continues to build its
content-addressed component libraries lazily. `DLP_DOMAIN_GEODESIC=0` affects the
component builder only; it cannot remove geodesic symbols from an explicitly
selected precompiled library.
