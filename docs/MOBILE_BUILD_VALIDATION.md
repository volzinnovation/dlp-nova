# Native mobile build validation — 2026-09-10

The seven-component aggregate library was built from the final native sources:
relations, domains, Horn reasoning, spatial index, event windows, finite local
queries and portable `.dlpn` packages. Tests executed native code with no Python
interpreter on the iOS simulator and Android emulator.

| Target | Build and execution evidence |
| --- | --- |
| macOS arm64 | Four CTest programs passed; Swift 6 and Kotlin/JNI smoke callers passed. All seven Python adapters loaded the same aggregate library for 99 passing tests. |
| iPhone arm64 | C/C++ library and Swift module crosscompiled for iOS 15.0 with SDK 26.5. No physical device execution. |
| iOS simulator arm64 + x86_64 | Universal static library and XCFramework built. Swift/Horn, native windows, local queries and portable packages executed on an arm64 iPhone 17 Pro simulator running iOS 26.5. |
| Android arm64-v8a + x86_64 | Both shared libraries crosscompiled for API 24 with NDK r30. C++ Horn/windows/query/package and Kotlin/JNI tests executed on an arm64 API 36 emulator with 4 KiB pages. |

The local query smoke executes `before` and `completedYears`, producing age 15.
The package smoke loads authored Horn data, prepares a query, releases the source
package and executes arithmetic, `MIN` and a filter, producing 3. The window tests
cover active rows, retained predecessors, checkpoints, idle expiry and corruption
rejection. The standalone window C++ smoke also passed ASan/UBSan; leak detection
was disabled because this macOS sanitizer runtime does not support it. The
reference/native window suite passed 43 tests.

The build used Xcode 26.6 (17F113), Apple Clang 21, iOS SDK 26.5, Kotlin 2.3.10,
JRE 17.0.18 and Android NDK 30.0.16248370. Device and both simulator object slices
report a deployment minimum of 15.0. Deployment targets are compilation settings;
execution on iOS 15 or Android API 24 was not tested.

Android `PT_LOAD` alignment and offset/address congruence are 16,384 bytes on
both ABIs; `GNU_RELRO` ends are also aligned. This is ELF validation only. No
16 KiB device, APK/AAB ZIP alignment, AAR, release signing, mobile background
lifecycle or physical-device tests were performed. The installed build-tools
36.1.0 D8 reported Kotlin 2.3 metadata compatibility warnings, retained in
`tmp/mobile-final-android/d8.log`; it generated a DEX that executed successfully.
Application packaging should use compatible Kotlin/D8 versions. See the official
[page-size guide](https://developer.android.com/guide/practices/page-sizes) and
[Kotlin/D8 version table](https://developer.android.com/studio/build/kotlin-d8-r8-versions).

The NDK came from the official
[r30 Darwin ZIP](https://dl.google.com/android/repository/android-ndk-r30-darwin.zip),
verified against Google's [repository metadata](https://dl.google.com/android/repository/repository2-3.xml):
974,984,488 bytes, SHA-1 `c060be96767eefbb8e0a27796d6f43115fc1a0c4`,
SHA-256 `d125634de97b26deb1e1bb1a562f9d839aa5803d1784a1e414485f5ccbe6739f`.
The archive and extracted toolchain occupy approximately 4 GB in the ignored
`tmp/android-toolchain/` cache. Existing SDK license acceptance was verified using
the SDK's whitespace-normalized license hash; no new license was accepted and no
global SDK configuration changed. The temporary read-only Android emulator was
closed after testing. The pre-existing iOS simulator was preserved.

Retained artifacts, relative to the repository:

- `tmp/mobile-final-host/install/lib/libdlp_native.dylib`
- `tmp/mobile-final-apple/DLP.xcframework`
- `tmp/mobile-final-android/jniLibs/{arm64-v8a,x86_64}/libdlp_native.so`
- `tmp/mobile-final-{host,apple,android}/build-manifest.json`

The [checked-in record](../mobile/validation/2026-09-10.json) contains source and
artifact SHA-256 hashes, sizes, ELF checks and full-manifest/log locations. Build
outputs remain ignored local artifacts. Android libraries are unstripped. Every
distribution includes the vendored source notices; Android additionally retains
NDK/LLVM notices for its statically linked C++ runtime.

Reproduce the checks with the commands in [mobile/README.md](../mobile/README.md).
The portable smoke fixture is deterministic:
`.venv/bin/python mobile/generate_fixture.py --check`. The build scripts use
installed toolchains and do not download them. `.dlq` authoring/planning, scoped
selection and external-provider transport remain host responsibilities; the
native local runtime does not imply complete mobile application integration.
