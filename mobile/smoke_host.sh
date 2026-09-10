#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
task_output=${1:-"$task_root/tmp/mobile-host"}
mkdir -p "$task_output"
task_output=$(CDPATH= cd -- "$task_output" && pwd)
task_jni=OFF
if [ "${DLP_TEST_JNI:-0}" = 1 ]; then task_jni=ON; fi
cmake -S "$task_root" -B "$task_output/build" -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_SHARED_LIBS=ON -DDLP_BUILD_SMOKE=ON "-DDLP_BUILD_JNI=$task_jni" \
    "-DCMAKE_INSTALL_PREFIX=$task_output/install"
cmake --build "$task_output/build" --parallel "${DLP_BUILD_JOBS:-4}"
ctest --test-dir "$task_output/build" --output-on-failure
cmake --install "$task_output/build"
if [ "$(uname -s)" = Darwin ]; then
    xcrun swiftc -swift-version 6 -I "$task_output/install/include/dlp" \
        "$task_root/mobile/swift/DLPRuntime.swift" "$task_root/mobile/swift/DLPWindowStore.swift" "$task_root/mobile/swift/Smoke.swift" \
        -L "$task_output/install/lib" -ldlp_native -lc++ \
        -Xlinker -rpath -Xlinker "$task_output/install/lib" -o "$task_output/swift-smoke"
    "$task_output/swift-smoke"
fi
if [ "$task_jni" = ON ]; then
    kotlinc "$task_root/mobile/android/NativeRuntime.kt" "$task_root/mobile/android/NativeWindowStore.kt" "$task_root/mobile/android/Smoke.kt" \
        -include-runtime -d "$task_output/kotlin-smoke.jar"
    java "-Djava.library.path=$task_output/install/lib" -jar "$task_output/kotlin-smoke.jar"
fi
