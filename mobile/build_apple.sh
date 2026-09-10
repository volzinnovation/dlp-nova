#!/bin/sh
# Build from local sources only. No signing identity, account, or network required.
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
task_output=${1:-"$task_root/dist/mobile/apple"}
mkdir -p "$task_output"
task_output=$(CDPATH= cd -- "$task_output" && pwd)
task_min_ios=${DLP_IOS_MINIMUM:-15.0}
command -v cmake >/dev/null || { echo "Install CMake 3.22+ before building." >&2; exit 1; }
command -v xcrun >/dev/null || { echo "Apple builds require macOS with Xcode and iOS SDKs." >&2; exit 1; }
xcrun --sdk iphoneos --show-sdk-path >/dev/null
xcrun --sdk iphonesimulator --show-sdk-path >/dev/null
for task_platform in device simulator; do
    if [ "$task_platform" = device ]; then
        task_sdk=iphoneos
        task_arch=arm64
    else
        task_sdk=iphonesimulator
        task_arch='arm64;x86_64'
    fi
    cmake -S "$task_root" -B "$task_output/build-$task_platform" \
        -DCMAKE_BUILD_TYPE=Release -DCMAKE_SYSTEM_NAME=iOS \
        "-DCMAKE_OSX_SYSROOT=$task_sdk" "-DCMAKE_OSX_ARCHITECTURES=$task_arch" \
        "-DCMAKE_OSX_DEPLOYMENT_TARGET=$task_min_ios" \
        -DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY \
        -DBUILD_SHARED_LIBS=OFF -DDLP_BUILD_SMOKE=OFF -DDLP_BUILD_JNI=OFF \
        "-DCMAKE_INSTALL_PREFIX=$task_output/$task_platform"
    cmake --build "$task_output/build-$task_platform" --parallel "${DLP_BUILD_JOBS:-4}"
    cmake --install "$task_output/build-$task_platform"
done
# xcodebuild refuses to replace an existing output; retain it until the new build succeeds.
task_xcframework="$task_output/DLP.xcframework"
if [ -e "$task_xcframework" ]; then
    echo "XCFramework already exists: $task_xcframework. Choose a new output directory." >&2
    exit 1
fi
xcodebuild -create-xcframework \
    -library "$task_output/device/lib/libdlp_native.a" -headers "$task_output/device/include/dlp" \
    -library "$task_output/simulator/lib/libdlp_native.a" -headers "$task_output/simulator/include/dlp" \
    -output "$task_xcframework"
mkdir -p "$task_output/licenses"
cp "$task_output/device/share/dlp/licenses/"* "$task_output/licenses/"
printf '%s\n' "Built $task_xcframework (iOS $task_min_ios; device arm64; simulator arm64/x86_64)."
