#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
task_ndk=${ANDROID_NDK_HOME:-${ANDROID_NDK_ROOT:-}}
if [ -z "$task_ndk" ] || [ ! -f "$task_ndk/build/cmake/android.toolchain.cmake" ]; then
    echo "Android NDK is required. Set ANDROID_NDK_HOME to an installed NDK (r28+ recommended). No SDK/NDK is downloaded by this script." >&2
    exit 1
fi
command -v cmake >/dev/null || { echo "Install CMake 3.22+ before building." >&2; exit 1; }
task_output=${1:-"$task_root/dist/mobile/android"}
mkdir -p "$task_output"
task_output=$(CDPATH= cd -- "$task_output" && pwd)
for task_abi in arm64-v8a x86_64; do
    cmake -S "$task_root" -B "$task_output/build-$task_abi" \
        "-DCMAKE_TOOLCHAIN_FILE=$task_ndk/build/cmake/android.toolchain.cmake" \
        "-DANDROID_ABI=$task_abi" -DANDROID_PLATFORM=android-24 \
        -DANDROID_STL=c++_static -DCMAKE_BUILD_TYPE=Release \
        -DBUILD_SHARED_LIBS=ON -DDLP_BUILD_SMOKE=OFF -DDLP_BUILD_JNI=ON
    cmake --build "$task_output/build-$task_abi" --parallel "${DLP_BUILD_JOBS:-4}"
    mkdir -p "$task_output/jniLibs/$task_abi"
    cp "$task_output/build-$task_abi/libdlp_native.so" "$task_output/jniLibs/$task_abi/"
done
mkdir -p "$task_output/licenses"
cp "$task_root/src/dlp_reasoner/vendor/date/date.h" "$task_output/licenses/HowardHinnant-date-header-with-license.h"
cp "$task_root/src/dlp_reasoner/vendor/geographiclib/LICENSE.txt" "$task_output/licenses/GeographicLib-C-LICENSE.txt"
# Retain NDK/LLVM notices with the statically linked C++ runtime distribution.
cp "$task_ndk/NOTICE" "$task_output/licenses/Android-NDK-NOTICE.txt"
for task_notice in "$task_ndk"/toolchains/llvm/prebuilt/*/NOTICE; do
    [ -f "$task_notice" ] || continue
    task_host=$(basename "$(dirname "$task_notice")")
    cp "$task_notice" "$task_output/licenses/LLVM-$task_host-NOTICE.txt"
done
printf '%s\n' "Built $task_output/jniLibs (API 24; arm64-v8a and x86_64)."
