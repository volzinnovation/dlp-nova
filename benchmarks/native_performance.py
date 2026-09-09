"""Profile the real engine and compare an isolated Python/C++ binary join.

This is a benchmark-only C ABI library, compiled into a temporary directory.
It does not select or modify the production reasoner's execution backend.
"""
from __future__ import annotations

import argparse
from array import array
from collections import defaultdict
import cProfile
import ctypes
from datetime import datetime, timezone
import gc
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import pstats
import random
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

from rdflib import URIRef

from dlp_reasoner.compiler import compile_graph
from dlp_reasoner.engine import Engine
from .workloads import EX, equality, taxonomy, transitive


ROOT = Path(__file__).resolve().parents[1]
REPORT_SCOPE = "isolated-binary-join-prototype-not-full-native-engine"
DEFAULT_OUTPUT = ROOT / "benchmarks/native-performance-results.json"
SOURCE_FILES = ["benchmarks/native_performance.py", "benchmarks/native_join.cpp",
                "benchmarks/workloads.py", "src/dlp_reasoner/compiler.py",
                "src/dlp_reasoner/engine.py", "src/dlp_reasoner/joins.py",
                "src/dlp_reasoner/model.py", "src/dlp_reasoner/support.py"]


def hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in SOURCE_FILES}


def protect_output(output, overwrite):
    """Never replace historical evidence or an unrelated file with this report."""
    resolved = output.resolve()
    if resolved.is_relative_to((ROOT / "benchmarks/baselines").resolve()):
        raise ValueError("Output cannot be inside immutable baselines")
    if output.is_symlink():
        raise ValueError("Output must not be a symbolic link")
    if resolved.is_relative_to(ROOT) and resolved != DEFAULT_OUTPUT:
        tracked = subprocess.check_output(
            ["git", "ls-files", "--", str(resolved.relative_to(ROOT))], cwd=ROOT, text=True)
        if tracked:
            raise ValueError("Output must not replace another tracked repository file")
    if output.exists():
        if not overwrite:
            raise ValueError("Output exists; use a new path or --overwrite for a prior native report")
        if not output.is_file() or output.stat().st_nlink != 1:
            raise ValueError("Output must be a regular file with no hard-link aliases")
        try:
            previous = json.loads(output.read_text())
        except (OSError, ValueError) as exc:
            raise ValueError("Existing output is not a native-performance report") from exc
        if not isinstance(previous, dict) or previous.get("scope") != REPORT_SCOPE:
            raise ValueError("Only a prior native-performance report may be overwritten")


def timed(function):
    start = time.perf_counter()
    result = function()
    return result, time.perf_counter() - start


def summary(values):
    return {"samples": values, "median": statistics.median(values),
            "minimum": min(values), "maximum": max(values)}


def python_join(left, right):
    """Same hash-index / projected-set / sorted-output algorithm as C++."""
    index = defaultdict(list)
    for y, z in right:
        index[y].append(z)
    matches = set()
    for x, y in left:
        prefix = x << 32
        for z in index.get(y, ()):
            matches.add(prefix | z)
    return sorted(matches)


def encode(left, right):
    terms = sorted({term for pair in (*left, *right) for term in pair})
    if len(terms) >= 2**32:
        raise ValueError("The experimental kernel uses 32-bit term IDs")
    ids = {term: position for position, term in enumerate(terms)}
    return ([(ids[x], ids[y]) for x, y in left],
            [(ids[y], ids[z]) for y, z in right], terms)


def decode(rows, terms):
    return [(terms[row >> 32], terms[row & 0xffffffff]) for row in rows]


def transfer(left, right):
    buffers = [array("I", (value for row in relation for value in row))
               for relation in (left, right)]
    if buffers[0].itemsize != 4:
        raise RuntimeError("array('I') must have 32-bit items for this C ABI")
    # Keep both arrays alive while the native call borrows their memory.
    pointers = [(ctypes.c_uint32 * len(buffer)).from_buffer(buffer) for buffer in buffers]
    return buffers, pointers


class NativeJoin:
    def __init__(self, path):
        library = ctypes.CDLL(str(path))
        library.dlp_join.argtypes = [ctypes.POINTER(ctypes.c_uint32), ctypes.c_size_t,
                                    ctypes.POINTER(ctypes.c_uint32), ctypes.c_size_t]
        library.dlp_join.restype = ctypes.c_void_p
        library.dlp_join_size.argtypes = [ctypes.c_void_p]
        library.dlp_join_size.restype = ctypes.c_size_t
        library.dlp_join_data.argtypes = [ctypes.c_void_p]
        library.dlp_join_data.restype = ctypes.POINTER(ctypes.c_uint64)
        library.dlp_join_free.argtypes = [ctypes.c_void_p]
        library.dlp_join_free.restype = None
        self.library = library

    def call(self, pointers, sizes):
        result = self.library.dlp_join(pointers[0], sizes[0], pointers[1], sizes[1])
        if not result:
            raise RuntimeError("Native join failed, including possible allocation failure")
        return result

    def copy_and_free(self, result):
        try:
            size = self.library.dlp_join_size(result)
            return self.library.dlp_join_data(result)[:size]
        finally:
            self.library.dlp_join_free(result)


def validate_native(native):
    """Independent nested-loop oracle, including empty/skewed/duplicate inputs."""
    randomizer = random.Random(2004)
    cases = [([], []), ([(0, 1)], []), ([], [(0, 1)]),
             ([(0, 1), (0, 1)], [(1, 2), (1, 2)]),
             ([(2**32 - 1, 7)], [(7, 2**32 - 1)])]
    for _ in range(100):
        cases.append(([(randomizer.randrange(12), randomizer.randrange(12))
                       for _ in range(randomizer.randrange(60))],
                      [(randomizer.randrange(12), randomizer.randrange(12))
                       for _ in range(randomizer.randrange(60))]))
    for left, right in cases:
        expected = sorted({(x << 32) | z for x, y in left for y2, z in right if y == y2})
        buffers, pointers = transfer(left, right)
        observed = native.copy_and_free(native.call(pointers, (len(left), len(right))))
        if observed != expected or python_join(left, right) != expected:
            raise AssertionError("Native/Python join differs from independent oracle")
    return len(cases)


def benchmark_join(native, name, size, dense, repeats):
    nodes = [URIRef(f"urn:native-performance:{i:06d}") for i in range(size + 1)]
    closure = [(nodes[x], nodes[y]) for x in range(size) for y in range(x + 1, size + 1)]
    left = closure if dense else list(zip(nodes[:-1], nodes[1:]))
    expected = {(nodes[x], nodes[z]) for x in range(size - 1)
                for z in range(x + 2, size + 1)}
    phases = {name: [] for name in ("encode_seconds", "native_transfer_seconds",
              "python_kernel_seconds", "native_kernel_seconds", "native_copy_free_seconds",
              "python_decode_seconds", "native_decode_seconds", "python_rdf_total_seconds",
              "native_rdf_total_seconds", "native_integer_total_seconds")}
    orders = []
    # One explicitly discarded warm-up for each implementation.
    warm_left, warm_right, _ = encode(left, closure)
    python_join(warm_left, warm_right)
    warm_buffers, warm_pointers = transfer(warm_left, warm_right)
    native.copy_and_free(native.call(warm_pointers, (len(left), len(closure))))
    for repeat in range(repeats):
        (encoded_left, encoded_right, terms), encoding = timed(lambda: encode(left, closure))
        phases["encode_seconds"].append(encoding)
        order = ("python", "native") if repeat % 2 == 0 else ("native", "python")
        orders.append(order)
        for implementation in order:
            if implementation == "python":
                result, kernel = timed(lambda: python_join(encoded_left, encoded_right))
                decoded, decoding = timed(lambda: decode(result, terms))
                phases["python_kernel_seconds"].append(kernel)
                phases["python_decode_seconds"].append(decoding)
                phases["python_rdf_total_seconds"].append(encoding + kernel + decoding)
            else:
                (buffers, pointers), packing = timed(lambda: transfer(encoded_left, encoded_right))
                handle, kernel = timed(lambda: native.call(pointers, (len(left), len(closure))))
                result, copying = timed(lambda: native.copy_and_free(handle))
                decoded, decoding = timed(lambda: decode(result, terms))
                phases["native_transfer_seconds"].append(packing)
                phases["native_kernel_seconds"].append(kernel)
                phases["native_copy_free_seconds"].append(copying)
                phases["native_decode_seconds"].append(decoding)
                phases["native_integer_total_seconds"].append(packing + kernel + copying)
                phases["native_rdf_total_seconds"].append(
                    encoding + packing + kernel + copying + decoding)
            if set(decoded) != expected or len(decoded) != len(expected):
                raise AssertionError(f"Incorrect join output: {name}, {implementation}")
    result = {"name": name, "chain_edges": size, "left_rows": len(left),
              "right_rows": len(closure), "output_rows": len(expected),
              "candidate_pairs": (size * (size - 1) * (size + 1) // 6 if dense
                                  else size * (size - 1) // 2),
              "input_sha256": hashlib.sha256(repr((left, closure)).encode()).hexdigest(),
              "output_sha256": hashlib.sha256(repr(sorted(expected)).encode()).hexdigest(),
              "validation": "exact-independent-chain-answer-set", "execution_orders": orders,
              **{phase: summary(values) for phase, values in phases.items()}}
    result["kernel_speedup_python_over_cpp"] = (
        result["python_kernel_seconds"]["median"] / result["native_kernel_seconds"]["median"])
    result["rdf_snapshot_speedup_python_over_cpp"] = (
        result["python_rdf_total_seconds"]["median"] / result["native_rdf_total_seconds"]["median"])
    return result


def engine_profiles(repeats):
    results = []
    workloads = [("taxonomy_d5_ipc9_p1", taxonomy(5, 9, "P1")[0]),
                 ("transitive_n100", transitive(100)), ("equality_n300", equality(300))]
    for name, graph in workloads:
        program = compile_graph(graph)
        elapsed = []
        reference = None
        for _ in range(repeats):
            engine = Engine(program)
            _, seconds = timed(engine.materialize)
            elapsed.append(seconds)
            if not engine.complete or engine.violations:
                raise AssertionError(f"Incomplete/inconsistent profile workload {name}")
            if reference is None:
                reference = frozenset(engine.facts)
            elif engine.facts != reference:
                raise AssertionError("Repeated materializations differ")
        engine = Engine(program)
        profiler = cProfile.Profile()
        profiler.enable()
        engine.materialize()
        profiler.disable()
        if engine.facts != reference:
            raise AssertionError("Profiled and unprofiled materializations differ")
        if name == "transitive_n100":
            actual = {fact.args for fact in reference if fact.predicate == EX.p}
            expected = {(EX[f"a{i}"], EX[f"a{j}"]) for i in range(100)
                        for j in range(i + 1, 101)}
            if actual != expected:
                raise AssertionError("Transitivity differs from independent reachability oracle")
        stats = pstats.Stats(profiler)
        rows = [{"file": str(Path(file).relative_to(ROOT)) if file.startswith(str(ROOT)) else file,
                 "line": line, "function": function, "primitive_calls": calls[0],
                 "total_calls": calls[1], "self_seconds": calls[2],
                 "cumulative_seconds": calls[3]}
                for (file, line, function), calls in stats.stats.items()]
        results.append({"name": name, "facts": len(reference), "rules": len(program.rules),
                        "unprofiled_materialize_seconds": summary(elapsed),
                        "profile_total_seconds": stats.total_tt,
                        "top_cumulative_functions": sorted(
                            rows, key=lambda row: row["cumulative_seconds"], reverse=True)[:20],
                        "top_self_functions": sorted(
                            rows, key=lambda row: row["self_seconds"], reverse=True)[:20],
                        "closure_sha256": hashlib.sha256(
                            repr(sorted(map(repr, reference))).encode()).hexdigest(),
                        "validation": "all-repeated-and-profiled-closures-equal",
                        "independent_reachability_check": name == "transitive_n100"})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/native-performance-results.json"))
    parser.add_argument("--overwrite", action="store_true",
                        help="Replace an existing native report; other files remain protected")
    parser.add_argument("--compiler", default=shutil.which("clang++") or shutil.which("g++"))
    args = parser.parse_args()
    if args.repeats < 2:
        parser.error("--repeats must be at least two")
    if not args.compiler:
        parser.error("C++17 compiler not found; provide --compiler")
    try:
        protect_output(args.output, args.overwrite)
    except ValueError as exc:
        parser.error(str(exc))
    measured_hashes = hashes()
    flags = ["-O3", "-std=c++17", "-fPIC", "-shared"]
    with tempfile.TemporaryDirectory(prefix="dlp-native-performance-") as temporary:
        library = Path(temporary) / ("join.dylib" if sys.platform == "darwin" else "join.so")
        subprocess.run([args.compiler, *flags, str(ROOT / "benchmarks/native_join.cpp"),
                        "-o", str(library)], check=True, capture_output=True, text=True)
        native = NativeJoin(library)
        validation_cases = validate_native(native)
        profiles = engine_profiles(args.repeats)
        joins = [benchmark_join(native, name, size, dense, args.repeats)
                 for name, size, dense in [("chain-frontier-128", 128, False),
                                           ("chain-frontier-768", 768, False),
                                           ("dense-chain-128", 128, True)]]
    if measured_hashes != hashes():
        raise RuntimeError("Measured source changed during the run; rerun before retaining results")
    report = {"timestamp": datetime.now(timezone.utc).isoformat(),
              "scope": REPORT_SCOPE,
              "repeats": args.repeats, "join_discarded_warmups_per_implementation": 1,
              "native_oracle_validation_cases": validation_cases,
              "compiler": subprocess.check_output([args.compiler, "--version"], text=True).strip(),
              "compiler_flags": flags, "source_sha256": measured_hashes,
              "environment": {"python": sys.version, "platform": platform.platform(),
                              "machine": platform.machine(), "cpu_count": os.cpu_count(),
                              "rdflib": importlib.metadata.version("rdflib"),
                              "garbage_collection_enabled": gc.isenabled(),
                              "garbage_collection_thresholds": gc.get_threshold(),
                              "python_hash_seed": os.environ.get("PYTHONHASHSEED", "random"),
                              "cpu": (subprocess.check_output(
                                  ["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
                                  if sys.platform == "darwin" else platform.processor()),
                              "go_executable": shutil.which("go"),
                              "git_head": subprocess.check_output(
                                  ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                              "git_status": subprocess.check_output(
                                  ["git", "status", "--short"], cwd=ROOT, text=True).splitlines()},
              "engine_profiles": profiles, "join_results": joins}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    protect_output(args.output, args.overwrite)
    with args.output.open("w" if args.overwrite else "x") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    for result in joins:
        print(f"{result['name']}: kernel {result['kernel_speedup_python_over_cpp']:.2f}x; "
              f"RDF snapshot {result['rdf_snapshot_speedup_python_over_cpp']:.2f}x")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
