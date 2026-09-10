#!/usr/bin/env python3
"""Record toolchain, native source hashes and artifact hashes; no runtime dependency."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


def capture(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return (result.stdout + result.stderr).strip() if result.returncode == 0 else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Existing build output directory")
    args = parser.parse_args()
    output = args.output.resolve(strict=True)
    root = Path(__file__).resolve().parent.parent
    sources = [root / "CMakeLists.txt"]
    native = root / "src/dlp_reasoner"
    sources += [path for path in native.glob("native_*") if path.suffix in (".cpp", ".h")]
    sources += [path for path in (native / "vendor").rglob("*") if path.is_file()]
    sources += [path for path in (root / "mobile").rglob("*")
                if path.is_file() and path.suffix in (".swift", ".kt", ".cpp", ".h", ".sh", ".py", ".modulemap", ".dlpn")]
    binaries = [path for path in output.rglob("*") if path.is_file() and
                path.suffix in (".a", ".so", ".dylib", ".jar")]
    configured = sorted(output.rglob("native-sources.sha256"))
    if not configured:
        parser.error("No CMake native-sources.sha256 manifests found; configure and build first")
    for manifest in configured:
        for line in manifest.read_text().splitlines():
            expected, name = line.split("  ", 1)
            if digest(root / name) != expected:
                parser.error(f"Source changed since configuration: {name}; rebuild before recording artifacts")
    data = {
        "format": "dlp-native-build-manifest-v1",
        "host": {"system": platform.system(), "machine": platform.machine()},
        "tools": {"cmake": capture(["cmake", "--version"]),
                  "xcode": capture(["xcodebuild", "-version"]),
                  "clang": capture(["clang", "--version"]),
                  "swift": capture(["swiftc", "--version"])},
        "sources_sha256": {str(path.relative_to(root)): digest(path) for path in sorted(sources)},
        "configured_native_inputs": {str(path.relative_to(output)): path.read_text() for path in configured},
        "artifacts_sha256": {str(path.relative_to(output)): digest(path) for path in sorted(binaries)},
        "cmake_cache": {str(path.relative_to(output)): path.read_text()
                        for path in sorted(output.rglob("CMakeCache.txt"))},
    }
    path = output / "build-manifest.json"
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(path)


if __name__ == "__main__":
    main()
