# Existing native backend: iOS compilation probe

Checked 10 September 2026. This is a compilation and packaging experiment on
the existing relation/index backend, not an iPhone application or a full native
reasoner. No production sources, dependencies or build configuration changed.

Using Xcode 26.6 (17F113), Apple Clang 21.0.0 and the installed iPhoneOS and
iPhoneSimulator 26.5 SDKs, the unchanged
`src/dlp_reasoner/native_store.cpp` compiled as C++17 for both iOS arm64 and
Simulator arm64 with `-O3 -DNDEBUG -Wall -Wextra -Werror`. Both objects were
archived and successfully packaged together as a static-library XCFramework.
`vtool -show-build` reported `IOS` and `IOSSIMULATOR` respectively, with SDK 26.5
and minimum OS 15.0. The minimum version was an experiment parameter, not a
chosen product requirement; optional libraries can impose higher versions.

Input SHA-256 values:

```text
native_store.cpp 60f8354e9f765b08aed96b7437f2e024fbfc1c39f4076fcd183acb05de8eb1c6
native_store.h   4f842aa8407d3d12945df4872b60c05ebdb31904787f4faba838861b9d6b60cd
```

Reproduce from the repository root on a Mac with Xcode and these SDKs installed.
All generated files go to a fresh temporary directory. These commands express
the same compiler, archive and packaging operations used in the experiment:

```sh
bash <<'SH'
set -euo pipefail
mobile_probe="$(mktemp -d /tmp/dlp-ios-portability.XXXXXX)"
mkdir -p "$mobile_probe/headers"
cp src/dlp_reasoner/native_store.h "$mobile_probe/headers/"
for mobile_sdk in iphoneos iphonesimulator; do
  mobile_target=arm64-apple-ios15.0
  if [ "$mobile_sdk" = iphonesimulator ]; then
    mobile_target=arm64-apple-ios15.0-simulator
  fi
  mobile_sysroot="$(xcrun --sdk "$mobile_sdk" --show-sdk-path)"
  mkdir -p "$mobile_probe/$mobile_sdk"
  xcrun --sdk "$mobile_sdk" clang++ -target "$mobile_target" \
    -isysroot "$mobile_sysroot" -std=c++17 -O3 -DNDEBUG \
    -Wall -Wextra -Werror -c src/dlp_reasoner/native_store.cpp \
    -o "$mobile_probe/$mobile_sdk/native_store.o"
  xcrun --sdk "$mobile_sdk" ar rcs "$mobile_probe/$mobile_sdk/libdlp_native.a" \
    "$mobile_probe/$mobile_sdk/native_store.o"
  xcrun vtool -show-build "$mobile_probe/$mobile_sdk/native_store.o"
done
xcodebuild -create-xcframework \
  -library "$mobile_probe/iphoneos/libdlp_native.a" -headers "$mobile_probe/headers" \
  -library "$mobile_probe/iphonesimulator/libdlp_native.a" -headers "$mobile_probe/headers" \
  -output "$mobile_probe/DLPNative.xcframework"
printf 'Generated artifacts: %s\n' "$mobile_probe"
SH
```

This follows Apple's documented support for
[static libraries in XCFrameworks](https://developer.apple.com/documentation/xcode/creating-a-multi-platform-binary-framework-bundle).
Separate device and simulator variants remain separate even when both are arm64.

There was no final application link, Swift binding test, simulator/device
execution, signing/distribution test, mobile domain-library build, or performance
measurement. A static archive can still contain unresolved symbols until the
final application link; this result does not establish runtime support.

Android platform SDKs were found locally, but no NDK was found in the configured
or conventional inspected SDK locations. Android cross-compilation was therefore
not attempted, and no SDK/NDK installation was performed. Both mobile platforms
still need executable conformance tests described in the
[mobile runtime proposal](../MOBILE_RUNTIME_PROPOSAL.md).
