"""Build/load the optional C++17 domain ABI and exchange bounded typed batches.

No import-time build or dependency download. Date and GeographicLib's small C
geodesic implementation are packaged. Mobile hosts supply an
ahead-of-time compiled binary using DLP_DOMAIN_LIBRARY instead of this builder.
"""
from __future__ import annotations

import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading

from .domains import (
    DateValue, DecimalValue, DomainError, DomainResult, DurationValue, FloatValue,
    InstantValue, IntegerValue, Interval, Point, Quantity, TimeValue, UNITS, identity_key,
)
from .native import _build_lock, _cache_root

_LOCK = threading.Lock()
_LIBRARIES = {}
_DEFAULTS = {}
_CODES = {1: "TYPE_ERROR", 2: "DOMAIN_ERROR", 3: "OVERFLOW", 4: "INEXACT",
          5: "UNAVAILABLE", 6: "RESOURCE_LIMIT", 7: "INTERNAL_ERROR", 8: "ARITY_ERROR"}


class _Value(c.Structure):
    _fields_ = [("tag", c.c_uint32), ("reserved", c.c_uint32),
                ("a", c.c_int64), ("b", c.c_int64), ("c", c.c_int64),
                ("x", c.c_double), ("y", c.c_double)]


class _ContextStats(c.Structure):
    _fields_ = [(name, c.c_uint64) for name in (
        "retained_values", "capacity", "generation", "intern_requests", "intern_hits",
        "transferred_inputs", "transferred_outputs", "evaluated_rows", "clears")]


def build_native_domains(compiler=None, cache_dir=None, *, geodesic=None):
    """Build native domains; geodesic=False explicitly omits bundled geodesics."""
    root = Path(__file__).parent
    sources = {name: (root / name).read_bytes() for name in
               ("native_domains.cpp", "native_domains.h", "vendor/date/date.h",
                "vendor/geographiclib/geodesic.c", "vendor/geographiclib/geodesic.h")}
    requested = compiler or os.environ.get("CXX")
    command = shlex.split(str(requested)) if requested else []
    executable = shutil.which(command[0]) if command else (
        shutil.which("clang++") or shutil.which("g++") or shutil.which("c++"))
    if not executable:
        raise DomainError("UNAVAILABLE", "Native domains require a C++17 clang++/g++ compiler")
    command = [str(Path(executable).resolve()), *command[1:]]
    flags = ["-std=c++17", "-O3", "-DNDEBUG", "-shared"]
    if os.name != "nt":
        flags.append("-fPIC")
    cflags = ["-x", "c", "-std=c99", "-O3", "-DNDEBUG"]
    if os.name != "nt":
        cflags.append("-fPIC")
    if geodesic is None:
        configured = os.environ.get("DLP_DOMAIN_GEODESIC", "auto")
        if configured not in ("auto", "0", "1"):
            raise DomainError("DOMAIN_ERROR", "DLP_DOMAIN_GEODESIC must be auto, 0 or 1")
        geodesic = {"auto": None, "0": False, "1": True}[configured]
    enabled = geodesic is not False
    if enabled:
        flags.append("-DDLP_HAVE_GEODESIC=1")
    compiler_version = subprocess.run([*command, "--version"], check=True,
                                      capture_output=True, text=True, timeout=30).stdout
    manifest = {"abi": 1, "platform": sys.platform, "machine": platform.machine(),
                "pointer_size": c.sizeof(c.c_void_p), "compiler": command,
                "compiler_version": compiler_version, "flags": flags, "cflags": cflags,
                "geodesic": "bundled-GeographicLib-C-2.2" if enabled else "unavailable",
                "sources": {name: hashlib.sha256(data).hexdigest() for name, data in sources.items()}}
    encoded = json.dumps(manifest, sort_keys=True)
    key = hashlib.sha256(encoded.encode()).hexdigest()
    cache = Path(cache_dir) if cache_dir is not None else _cache_root() / "domains"
    directory = cache.expanduser().resolve() / key
    directory.mkdir(parents=True, exist_ok=True)
    suffix = ".dylib" if sys.platform == "darwin" else ".dll" if os.name == "nt" else ".so"
    target = directory / ("libdlp_domains" + suffix)
    with _build_lock(directory / "build.lock"):
        if target.is_file() and target.stat().st_size:
            return target
        with tempfile.TemporaryDirectory(prefix="build-", dir=directory) as temporary:
            temporary = Path(temporary)
            for name, data in sources.items():
                path = temporary / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            output = temporary / target.name
            links = []
            if enabled:
                geodesic_object = temporary / "geodesic.o"
                compiled = subprocess.run([*command, *cflags, "-c",
                                           str(temporary / "vendor/geographiclib/geodesic.c"),
                                           "-o", str(geodesic_object)], capture_output=True,
                                          text=True, timeout=180)
                if compiled.returncode:
                    raise DomainError("UNAVAILABLE", "Bundled GeographicLib C build failed:\n"
                                      + (compiled.stdout + compiled.stderr)[-8000:])
                links.append(str(geodesic_object))
            result = subprocess.run([*command, *flags, str(temporary / "native_domains.cpp"),
                                     *links, "-o", str(output)], capture_output=True,
                                    text=True, timeout=180)
            if result.returncode:
                raise DomainError("UNAVAILABLE", "Native domain build failed:\n"
                                  + (result.stdout + result.stderr)[-8000:])
            if not output.is_file() or not output.stat().st_size:
                raise DomainError("UNAVAILABLE", "Compiler produced no domain library")
            (temporary / "build.json").write_text(encoded + "\n")
            os.replace(temporary / "build.json", directory / "build.json")
            os.replace(output, target)
    return target


def _library():
    environment = tuple(os.environ.get(key) for key in
                        ("DLP_DOMAIN_LIBRARY", "DLP_DOMAIN_GEODESIC", "DLP_NATIVE_CACHE", "CXX"))
    with _LOCK:
        if environment in _DEFAULTS:
            return _DEFAULTS[environment]
        try:
            path = (Path(environment[0]).expanduser().resolve() if environment[0]
                    else build_native_domains())
            if path not in _LIBRARIES:
                library = c.CDLL(str(path))
                library.dlp_domain_abi_version.argtypes = []
                library.dlp_domain_abi_version.restype = c.c_uint32
                library.dlp_domain_capabilities.argtypes = []
                library.dlp_domain_capabilities.restype = c.c_uint32
                library.dlp_domain_geodesic_version.argtypes = []
                library.dlp_domain_geodesic_version.restype = c.c_char_p
                library.dlp_domain_last_error.argtypes = []
                library.dlp_domain_last_error.restype = c.c_char_p
                library.dlp_domain_evaluate.argtypes = [c.c_uint32, c.POINTER(_Value),
                    c.c_size_t, c.c_size_t, c.POINTER(_Value), c.POINTER(c.c_int32)]
                library.dlp_domain_evaluate.restype = c.c_int
                signatures = {
                    "last_status": ([], c.c_int32),
                    "new": ([c.c_uint64, c.POINTER(c.c_void_p)], c.c_int),
                    "free": ([c.c_void_p], None),
                    "clear": ([c.c_void_p], c.c_int),
                    "intern": ([c.c_void_p, c.POINTER(_Value), c.c_size_t,
                                c.POINTER(c.c_uint64)], c.c_int),
                    "get": ([c.c_void_p, c.POINTER(c.c_uint64), c.c_size_t,
                             c.POINTER(_Value), c.POINTER(c.c_int32)], c.c_int),
                    "evaluate": ([c.c_void_p, c.c_uint32, c.POINTER(c.c_uint64),
                                  c.c_size_t, c.c_size_t, c.POINTER(c.c_uint64),
                                  c.POINTER(c.c_int32)], c.c_int),
                    "get_stats": ([c.c_void_p, c.POINTER(_ContextStats)], c.c_int),
                    "compare": ([c.c_void_p, c.c_uint64, c.c_uint64, c.POINTER(c.c_int32)], c.c_int),
                }
                for name, (arguments, result) in signatures.items():
                    function = getattr(library, "dlp_domain_context_" + name)
                    function.argtypes, function.restype = arguments, result
                if library.dlp_domain_abi_version() != 1:
                    raise DomainError("UNAVAILABLE", "Native domain ABI mismatch")
                _LIBRARIES[path] = library
            _DEFAULTS[environment] = _LIBRARIES[path]
            return _DEFAULTS[environment]
        except DomainError:
            raise
        except (OSError, AttributeError, subprocess.SubprocessError, ValueError) as error:
            raise DomainError("UNAVAILABLE", f"Cannot load requested native domains: {error}") from error


def native_capabilities():
    library = _library()
    return {"abi": 1, "date": "HowardHinnant-date-3.0.5", "decimal": "coefficient64-scale18-v1",
            "geodesic": bool(library.dlp_domain_capabilities() & 1), "resident_values": True,
            "geodesic_version": library.dlp_domain_geodesic_version().decode()}


def _pack(value):
    if type(value) is bool:
        return _Value(tag=1, a=int(value))
    if type(value) is IntegerValue:
        return _Value(tag=2, a=value.value)
    if type(value) is DecimalValue:
        return _Value(tag=3, a=value.coefficient, b=value.scale)
    if type(value) is FloatValue:
        return _Value(tag=4, x=value.value)
    if type(value) is DateValue:
        return _Value(tag=5, a=value.year, b=value.month, c=value.day)
    if type(value) in (InstantValue, TimeValue, DurationValue):
        return _Value(tag={InstantValue: 6, TimeValue: 7, DurationValue: 8}[type(value)],
                      a=value.microseconds)
    if type(value) is Point:
        return _Value(tag=9, x=value.longitude, y=value.latitude)
    if type(value) is Interval:
        if type(value.start) is DateValue:
            return _Value(tag=10, a=value.start.ordinal, b=value.end.ordinal, c=5)
        return _Value(tag=10, a=value.start.microseconds, b=value.end.microseconds, c=6)
    if type(value) is Quantity:
        scalar = _pack(value.value)
        return _Value(tag=12, a=scalar.a, b=scalar.b, c=scalar.tag, x=UNITS.index(value.unit) + 1)
    if value == "march1":
        return _Value(tag=11, a=1)
    if value in UNITS:
        return _Value(tag=13, a=UNITS.index(value) + 1)
    raise DomainError("TYPE_ERROR", "Unsupported native value")


def _unpack(value):
    if value.tag == 1:
        return bool(value.a)
    if value.tag == 2:
        return IntegerValue(value.a)
    if value.tag == 3:
        return DecimalValue(value.a, value.b)
    if value.tag == 4:
        return FloatValue(value.x)
    if value.tag == 5:
        return DateValue(value.a, value.b, value.c)
    if value.tag in (6, 7, 8):
        return {6: InstantValue, 7: TimeValue, 8: DurationValue}[value.tag](value.a)
    if value.tag == 9:
        return Point(value.x, value.y)
    if value.tag == 10:
        if value.c == 5:
            from datetime import date
            def endpoint(ordinal):
                result = date.fromordinal(ordinal)
                return DateValue(result.year, result.month, result.day)
            return Interval(endpoint(value.a), endpoint(value.b))
        return Interval(InstantValue(value.a), InstantValue(value.b))
    if value.tag == 12:
        scalar = IntegerValue(value.a) if value.c == 2 else DecimalValue(value.a, value.b)
        return Quantity(scalar, UNITS[int(value.x) - 1])
    raise DomainError("INTERNAL_ERROR", f"Unknown native output tag {value.tag}")


def evaluate_native_batch(opcode, rows):
    if not rows:
        return []
    library = _library()
    results = []
    arity = len(rows[0])
    try:
        # Bound C buffer allocations independently of caller's result cardinality.
        for start in range(0, len(rows), 512):
            block = rows[start:start + 512]
            if any(len(row) != arity for row in block):
                raise DomainError("ARITY_ERROR", "Native rows have inconsistent arity")
            packed = (_Value * (len(block) * arity))(*(_pack(v) for row in block for v in row))
            outputs = (_Value * len(block))()
            statuses = (c.c_int32 * len(block))()
            code = library.dlp_domain_evaluate(opcode, packed, len(block), arity, outputs, statuses)
            if code:
                raise DomainError("INTERNAL_ERROR", library.dlp_domain_last_error().decode())
            for output, status in zip(outputs, statuses):
                if status:
                    name = _CODES.get(status, "INTERNAL_ERROR")
                    results.append(DomainResult(error=DomainError(name,
                        f"Native domain operation {opcode}: {name}")))
                else:
                    results.append(DomainResult(_unpack(output)))
    except MemoryError as error:
        raise DomainError("RESOURCE_LIMIT", "Native domain batch allocation failed") from error
    return results


_resident_key = identity_key

class NativeDomainContext:
    """Bounded resident C++ typed values, reused between query evaluations.

    ``intern``/``evaluate_ids``/``get`` let a native host retain opaque value IDs
    without transferring output payloads until requested. IDs survive successful
    calls; explicit clear invalidates them and never reuses their numbers.
    ``evaluate`` is the Python value adapter: it may clear at a batch boundary
    when full, so callers retaining raw IDs must use the lower-level methods.
    No scalar Python implementation is called. Methods serialize this handle.
    """

    def __init__(self, capacity=4096):
        if type(capacity) is not int or not 4 <= capacity < 2**64:
            raise ValueError("native value capacity must be an integer from 4 to uint64 max")
        self.capacity = capacity
        self._lock = threading.RLock()
        self._lib = _library()
        self._handle = c.c_void_p()
        self._ids, self._decoded = {}, {}
        self._check(self._lib.dlp_domain_context_new(capacity, c.byref(self._handle)))

    def _check(self, status):
        if status:
            code = self._lib.dlp_domain_context_last_status()
            name = _CODES.get(code, "INTERNAL_ERROR")
            raise DomainError(name, self._lib.dlp_domain_last_error().decode("utf-8", "replace"))

    def _open(self):
        if not self._handle:
            raise DomainError("UNAVAILABLE", "Native domain context is closed")

    def stats(self):
        with self._lock:
            self._open()
            stats = _ContextStats()
            self._check(self._lib.dlp_domain_context_get_stats(self._handle, c.byref(stats)))
            return {name: getattr(stats, name) for name, _ in _ContextStats._fields_}

    def clear(self):
        with self._lock:
            self._open()
            self._check(self._lib.dlp_domain_context_clear(self._handle))
            self._ids.clear()
            self._decoded.clear()

    def intern(self, values):
        with self._lock:
            self._open()
            values = tuple(values)
            missing = {}
            for value in values:
                key = _resident_key(value)
                if key not in self._ids:
                    missing[key] = value
            if missing:
                data = (_Value * len(missing))(*(_pack(value) for value in missing.values()))
                ids = (c.c_uint64 * len(missing))()
                self._check(self._lib.dlp_domain_context_intern(self._handle, data, len(data), ids))
                for key, value, value_id in zip(missing, missing.values(), ids):
                    self._ids[key] = value_id
                    self._decoded[value_id] = value
            return tuple(self._ids[_resident_key(value)] for value in values)

    def evaluate_ids(self, opcode, rows):
        """Return (output ID, status) per row; no output value crosses the ABI."""
        with self._lock:
            self._open()
            rows = tuple(tuple(row) for row in rows)
            if not rows:
                return ()
            arity = len(rows[0])
            if any(len(row) != arity for row in rows):
                raise DomainError("ARITY_ERROR", "Resident input rows have inconsistent arity")
            if any(type(value) is not int or not 0 < value < 2**64 for row in rows for value in row):
                raise DomainError("TYPE_ERROR", "Resident input IDs must be nonzero uint64 values")
            inputs = (c.c_uint64 * (len(rows) * arity))(*(value for row in rows for value in row))
            outputs, statuses = (c.c_uint64 * len(rows))(), (c.c_int32 * len(rows))()
            self._check(self._lib.dlp_domain_context_evaluate(self._handle, opcode, inputs,
                        len(rows), arity, outputs, statuses))
            return tuple(zip(outputs, statuses))

    def compare(self, left, right):
        with self._lock:
            self._open()
            if any(type(value) is not int or not 0 < value < 2**64 for value in (left, right)):
                raise DomainError("TYPE_ERROR", "Resident value IDs must be nonzero uint64 values")
            result = c.c_int32()
            self._check(self._lib.dlp_domain_context_compare(self._handle, left, right, c.byref(result)))
            return result.value

    def get(self, ids):
        """Retrieve only requested output payloads; repeated gets stay in Python."""
        with self._lock:
            self._open()
            ids = tuple(ids)
            if any(type(value) is not int or not 0 < value < 2**64 for value in ids):
                raise DomainError("TYPE_ERROR", "Resident value IDs must be nonzero uint64 values")
            missing = tuple(dict.fromkeys(value for value in ids if value not in self._decoded))
            if missing:
                requested = (c.c_uint64 * len(missing))(*missing)
                output, statuses = (_Value * len(missing))(), (c.c_int32 * len(missing))()
                self._check(self._lib.dlp_domain_context_get(self._handle, requested, len(missing),
                            output, statuses))
                for value_id, value, status in zip(missing, output, statuses):
                    if status:
                        raise DomainError(_CODES.get(status, "INTERNAL_ERROR"), "Unknown or stale native value ID")
                    decoded = _unpack(value)
                    self._decoded[value_id] = decoded
                    self._ids[_resident_key(decoded)] = value_id
            return tuple(self._decoded[value] for value in ids)

    def evaluate(self, opcode, rows):
        """Evaluate decoded Python rows using resident IDs and bounded buffers."""
        with self._lock:
            self._open()
            if not rows:
                return []
            arity = len(rows[0])
            if not 1 <= arity <= 3 or any(len(row) != arity for row in rows):
                raise DomainError("ARITY_ERROR", "Resident rows have invalid arity")
            block_size = max(1, min(512, self.capacity // (arity + 1)))
            results = []
            for start in range(0, len(rows), block_size):
                block = rows[start:start + block_size]
                for attempt in range(2):
                    try:
                        inputs = self.intern(value for row in block for value in row)
                        ids = [inputs[offset:offset + arity] for offset in range(0, len(inputs), arity)]
                        outputs = self.evaluate_ids(opcode, ids)
                        break
                    except DomainError as error:
                        if error.code != "RESOURCE_LIMIT" or attempt:
                            raise
                        self.clear()
                successful = [value_id for value_id, status in outputs if status == 0]
                decoded = iter(self.get(successful))
                for _, status in outputs:
                    if status:
                        name = _CODES.get(status, "INTERNAL_ERROR")
                        results.append(DomainResult(error=DomainError(name, f"Native domain: {name}")))
                    else:
                        results.append(DomainResult(next(decoded)))
            return results

    def close(self):
        with self._lock:
            if self._handle:
                self._lib.dlp_domain_context_free(self._handle)
                self._handle = c.c_void_p()
            self._ids.clear()
            self._decoded.clear()

    def __enter__(self):
        self._open()
        return self

    def __exit__(self, *_):
        self.close()

    def __del__(self):
        if getattr(self, "_handle", None):
            self._lib.dlp_domain_context_free(self._handle)
            self._handle = c.c_void_p()
