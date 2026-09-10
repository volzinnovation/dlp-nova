#!/bin/sh
# Use an already running emulator. No APK installation or global SDK mutation.
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
task_output=${1:-"$task_root/dist/mobile/android"}
task_output=$(CDPATH= cd -- "$task_output" && pwd)
task_serial=${DLP_ANDROID_SERIAL:-}
case "$task_serial" in emulator-[0-9]*) ;; *) echo "Set DLP_ANDROID_SERIAL to a running emulator-NNNN (physical devices are not selected automatically)." >&2; exit 1;; esac
task_sdk=${ANDROID_SDK_ROOT:-${ANDROID_HOME:-"$HOME/Library/Android/sdk"}}
task_adb="$task_sdk/platform-tools/adb"
task_abi=$("$task_adb" -s "$task_serial" shell getprop ro.product.cpu.abi | tr -d '\r')
case "$task_abi" in arm64-v8a|x86_64) ;; *) echo "Unsupported emulator ABI: $task_abi" >&2; exit 1;; esac
cmake -S "$task_root" -B "$task_output/build-$task_abi" -DDLP_BUILD_SMOKE=ON
cmake --build "$task_output/build-$task_abi" --parallel "${DLP_BUILD_JOBS:-4}"
task_remote="/data/local/tmp/dlp-native-smoke-$$"
"$task_adb" -s "$task_serial" shell mkdir "$task_remote"
trap '"$task_adb" -s "$task_serial" shell rm -rf "$task_remote" >/dev/null 2>&1 || true' EXIT HUP INT TERM
"$task_adb" -s "$task_serial" push "$task_output/build-$task_abi/libdlp_native.so" "$task_remote/"
"$task_adb" -s "$task_serial" push "$task_root/mobile/fixtures/query.dlpn" "$task_remote/"
for task_test in native windows query package; do
    task_name="dlp_${task_test}_smoke"
    "$task_adb" -s "$task_serial" push "$task_output/build-$task_abi/$task_name" "$task_remote/"
    if [ "$task_test" = package ]; then
        "$task_adb" -s "$task_serial" shell "LD_LIBRARY_PATH=$task_remote $task_remote/$task_name $task_remote/query.dlpn"
    else
        "$task_adb" -s "$task_serial" shell "LD_LIBRARY_PATH=$task_remote $task_remote/$task_name"
    fi
done

if [ "${DLP_TEST_JNI:-0}" = 1 ]; then
    task_build_tools=${DLP_ANDROID_BUILD_TOOLS:-36.1.0}
    task_platform=${DLP_ANDROID_PLATFORM:-android-36}
    task_d8="$task_sdk/build-tools/$task_build_tools/d8"
    [ -x "$task_d8" ] || { echo "Set DLP_ANDROID_BUILD_TOOLS to installed build tools containing d8." >&2; exit 1; }
    mkdir -p "$task_output/dex"
    kotlinc "$task_root/mobile/android/NativeRuntime.kt" "$task_root/mobile/android/NativeWindowStore.kt" \
        "$task_root/mobile/android/Smoke.kt" -include-runtime -d "$task_output/kotlin-smoke.jar"
    # Keep full tool diagnostics without flooding the caller with metadata warnings
    # when the locally installed Kotlin compiler is newer than the installed D8.
    if ! "$task_d8" --min-api 24 --lib "$task_sdk/platforms/$task_platform/android.jar" \
        --output "$task_output/dex" "$task_output/kotlin-smoke.jar" >"$task_output/d8.log" 2>&1; then
        tail -n 40 "$task_output/d8.log" >&2
        exit 1
    fi
    if [ -s "$task_output/d8.log" ]; then
        printf '%s\n' "D8 diagnostics retained in $task_output/d8.log; use matching Kotlin/D8 versions for app packaging."
    fi
    "$task_adb" -s "$task_serial" push "$task_output/dex/classes.dex" "$task_remote/"
    "$task_adb" -s "$task_serial" shell \
        "CLASSPATH=$task_remote/classes.dex app_process -Djava.library.path=$task_remote /system/bin org.example.dlp.SmokeKt"
fi
