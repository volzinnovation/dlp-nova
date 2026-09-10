"""Optional immutable native spatial candidate index; no dependency downloads."""
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
import weakref

from .native import NativeBackendError, _build_lock, _cache_root

_LOCK = threading.Lock()
_LIBRARIES = {}


def build_spatial_library():
    source = Path(__file__).with_name("native_spatial.cpp").read_bytes()
    header = Path(__file__).with_name("native_spatial.h").read_bytes()
    try:
        command = shlex.split(os.environ.get("CXX", ""))
        executable = shutil.which(command[0]) if command else (
            shutil.which("clang++") or shutil.which("g++") or shutil.which("c++"))
        if not executable:
            raise NativeBackendError("Native spatial indexing requires a C++17 compiler or DLP_SPATIAL_LIBRARY")
        command = [str(Path(executable).resolve()), *command[1:]]
        version = subprocess.run([*command, "--version"], check=True, capture_output=True,
                                 text=True, timeout=30).stdout
        flags = ["-O3", "-std=c++17", "-shared"] + ([] if os.name == "nt" else ["-fPIC"])
        manifest = dict(abi=1, compiler=command, version=version, flags=flags,
                        platform=sys.platform, machine=platform.machine(), pointer=c.sizeof(c.c_void_p),
                        source=hashlib.sha256(source).hexdigest(), header=hashlib.sha256(header).hexdigest())
        encoded = json.dumps(manifest, sort_keys=True)
        directory = _cache_root() / "spatial" / hashlib.sha256(encoded.encode()).hexdigest()
        directory.mkdir(parents=True, exist_ok=True)
        suffix = ".dylib" if sys.platform == "darwin" else ".dll" if os.name == "nt" else ".so"
        target = directory / ("libdlp_spatial" + suffix)
        with _build_lock(directory / "build.lock"):
            if target.is_file() and target.stat().st_size:
                return target
            with tempfile.TemporaryDirectory(dir=directory) as folder:
                folder = Path(folder)
                (folder / "native_spatial.cpp").write_bytes(source)
                (folder / "native_spatial.h").write_bytes(header)
                output = folder / target.name
                result = subprocess.run([*command, *flags, str(folder / "native_spatial.cpp"),
                                         "-o", str(output)], capture_output=True, text=True, timeout=180)
                if result.returncode or not output.is_file():
                    raise NativeBackendError("Native spatial build failed:\n" + result.stderr[-8000:])
                (folder / "build.json").write_text(encoded + "\n")
                os.replace(folder / "build.json", directory / "build.json")
                os.replace(output, target)
        return target
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise NativeBackendError(f"Cannot build native spatial index: {exc}") from exc


def _library():
    key = tuple(os.environ.get(name) for name in ("DLP_SPATIAL_LIBRARY", "DLP_NATIVE_CACHE", "CXX"))
    with _LOCK:
        if key in _LIBRARIES:
            return _LIBRARIES[key]
        try:
            library = c.CDLL(key[0] or str(build_spatial_library()))
            signatures = {
                "dlp_spatial_abi": ([], c.c_uint32),
                "dlp_spatial_new": ([c.POINTER(c.c_double), c.c_size_t, c.POINTER(c.c_void_p)], c.c_int),
                "dlp_spatial_free": ([c.c_void_p], None),
                "dlp_spatial_query": ([c.c_void_p, c.POINTER(c.c_double), c.POINTER(c.c_double),
                                        c.POINTER(c.c_void_p)], c.c_int),
                "dlp_spatial_next": ([c.c_void_p, c.POINTER(c.c_uint64), c.c_size_t,
                                       c.POINTER(c.c_size_t), c.POINTER(c.c_int)], c.c_int),
                "dlp_spatial_query_free": ([c.c_void_p], None),
            }
            for name, (args, result) in signatures.items():
                getattr(library, name).argtypes, getattr(library, name).restype = args, result
            if library.dlp_spatial_abi() != 1:
                raise NativeBackendError("Native spatial ABI mismatch")
        except (OSError, AttributeError) as exc:
            raise NativeBackendError(f"Cannot load native spatial index: {exc}") from exc
        _LIBRARIES[key] = library
        return library


def _check(status):
    if status:
        raise NativeBackendError({1: "Invalid native spatial arguments", 2: "Native spatial allocation failed"}
                                 .get(status, "Native spatial internal error"))


class NativePointIndex:
    def __init__(self, xyz):
        self.library, self.handle = _library(), c.c_void_p()
        packed = (c.c_double * (len(xyz) * 3))(*(v for point in xyz for v in point))
        _check(self.library.dlp_spatial_new(packed, len(xyz), c.byref(self.handle)))
        self._finalizer = weakref.finalize(self, self.library.dlp_spatial_free, self.handle)

    def close(self):
        self._finalizer()

    def candidates(self, lower, upper):
        if not self._finalizer.alive:
            raise NativeBackendError("Native spatial index is closed")
        handle = c.c_void_p()
        _check(self.library.dlp_spatial_query(self.handle, (c.c_double * 3)(*lower),
                                             (c.c_double * 3)(*upper), c.byref(handle)))
        try:
            rows, count, done = (c.c_uint64 * 256)(), c.c_size_t(), c.c_int()
            while not done.value:
                _check(self.library.dlp_spatial_next(handle, rows, 256, c.byref(count), c.byref(done)))
                for index in range(count.value):
                    if not self._finalizer.alive:
                        raise NativeBackendError("Native spatial index was closed during enumeration")
                    yield rows[index]
        finally:
            self.library.dlp_spatial_query_free(handle)
