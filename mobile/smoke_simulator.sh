#!/bin/sh
# Requires an already booted simulator; does not launch/install an application.
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
task_apple=${1:-"$task_root/dist/mobile/apple"}
task_apple=$(CDPATH= cd -- "$task_apple" && pwd)
task_arch=$(uname -m)
task_sdk=$(xcrun --sdk iphonesimulator --show-sdk-path)
task_min_ios=${DLP_IOS_MINIMUM:-15.0}
xcrun --sdk iphonesimulator swiftc -swift-version 6 -target "$task_arch-apple-ios$task_min_ios-simulator" \
    -sdk "$task_sdk" -I "$task_apple/simulator/include/dlp" \
    "$task_root/mobile/swift/DLPRuntime.swift" "$task_root/mobile/swift/DLPWindowStore.swift" "$task_root/mobile/swift/Smoke.swift" \
    "$task_apple/simulator/lib/libdlp_native.a" -lc++ -o "$task_apple/swift-simulator-smoke"
codesign --force --sign - "$task_apple/swift-simulator-smoke"
xcrun simctl spawn booted "$task_apple/swift-simulator-smoke"
for task_component in windows query package; do
    xcrun --sdk iphonesimulator clang++ -std=c++17 \
        -target "$task_arch-apple-ios$task_min_ios-simulator" -isysroot "$task_sdk" \
        -I "$task_apple/simulator/include/dlp" "$task_root/mobile/${task_component}_smoke.cpp" \
        "$task_apple/simulator/lib/libdlp_native.a" -o "$task_apple/$task_component-simulator-smoke"
    codesign --force --sign - "$task_apple/$task_component-simulator-smoke"
    if [ "$task_component" = package ]; then
        xcrun simctl spawn booted "$task_apple/$task_component-simulator-smoke" "$task_root/mobile/fixtures/query.dlpn"
    else
        xcrun simctl spawn booted "$task_apple/$task_component-simulator-smoke"
    fi
done
