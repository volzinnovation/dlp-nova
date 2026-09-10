"""Optional, persistent C++ relations behind a small standard-library C ABI.

Importing this module never compiles or loads native code. Selecting the native
backend builds the packaged C++17 sources in a user cache if necessary. Python
objects are interned by their ordinary hash/equality semantics, without text
serialization; only opaque integer IDs cross the ABI. The engine still owns
its authoritative facts, equality, witnesses, limits, and maintenance policy.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from contextlib import contextmanager
import ctypes
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

from .model import EQ, NEQ


_ABI_VERSION = 1
_BATCH_SIZE = 512
_U64 = ctypes.c_uint64
_I32 = ctypes.c_int32
_SIZE = ctypes.c_size_t
_HANDLE = ctypes.c_void_p
_U64P = ctypes.POINTER(_U64)
_LIBRARIES = {}
_LIBRARY_LOCK = threading.Lock()
_BUILD_PATHS = {}
_BUILD_PATH_LOCK = threading.Lock()


class NativeBackendError(RuntimeError):
    """A requested native backend could not build, load, or execute safely."""


class _Atom(ctypes.Structure):
    _fields_ = [("predicate", _U64), ("arity", _SIZE),
                ("slots", ctypes.POINTER(_I32)), ("constants", _U64P)]


def _cache_root():
    configured = os.environ.get("DLP_NATIVE_CACHE")
    if configured:
        return Path(configured).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "dlp-reasoner" / "native"
    base = os.environ.get("XDG_CACHE_HOME")
    return (Path(base).expanduser() if base else Path.home() / ".cache") / "dlp-reasoner" / "native"


@contextmanager
def _build_lock(path):
    """An OS lock survives neither a crashed compiler nor a crashed builder."""
    with path.open("a+b") as lock:
        if os.name == "nt":
            import msvcrt
            if lock.tell() == 0:
                lock.write(b"\0")
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def build_native(compiler=None, cache_dir=None):
    """Return the content-addressed library path, compiling it when absent.

    ``compiler`` (or ``CXX``) selects a clang++/g++ compatible C++17 command.
    ``cache_dir`` (or ``DLP_NATIVE_CACHE``) overrides the user cache directory.
    Builds are atomic and serialized across processes. No project files are
    generated or modified, and no downloaded compiler or package is required.
    Warm contexts reuse the resolved path without invoking the compiler again.
    """
    requested = compiler if compiler is not None else os.environ.get("CXX")
    if requested:
        try:
            command = ([os.fspath(requested)] if isinstance(requested, os.PathLike)
                       else shlex.split(requested))
        except ValueError as exc:
            raise NativeBackendError(f"Invalid CXX/compiler command: {exc}") from exc
    else:
        executable = shutil.which("clang++") or shutil.which("g++") or shutil.which("c++")
        command = [executable] if executable else []
    executable = shutil.which(command[0]) if command else None
    if not executable:
        raise NativeBackendError(
            "The native backend requires a C++17 compiler (clang++ or g++). "
            "Install the platform's C++ development tools, set CXX to its compiler, "
            "or select backend='python'.")
    command[0] = str(Path(executable).resolve())
    try:
        source = Path(__file__).with_name("native_store.cpp")
        header = source.with_suffix(".h")
        source_data, header_data = source.read_bytes(), header.read_bytes()
        flags = ["-O3", "-std=c++17", "-DNDEBUG", "-shared"]
        if os.name != "nt":
            flags.append("-fPIC")
        compiler_stat = Path(command[0]).stat()
        manifest = {
            "abi_version": _ABI_VERSION, "compiler": command,
            "compiler_size": compiler_stat.st_size, "compiler_mtime_ns": compiler_stat.st_mtime_ns,
            "flags": flags, "platform": sys.platform, "machine": platform.machine(),
            "pointer_size": ctypes.sizeof(_HANDLE), "byteorder": sys.byteorder,
            "source_sha256": hashlib.sha256(source_data).hexdigest(),
            "header_sha256": hashlib.sha256(header_data).hexdigest(),
        }
        root = Path(cache_dir).expanduser() if cache_dir is not None else _cache_root()
        cache_key = (str(root.resolve()), json.dumps(manifest, sort_keys=True))
        with _BUILD_PATH_LOCK:
            cached = _BUILD_PATHS.get(cache_key)
            if cached is not None and cached.is_file() and cached.stat().st_size:
                return cached
            manifest["compiler_version"] = subprocess.run(
                [*command, "--version"], check=True, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, timeout=30).stdout
            manifest_json = json.dumps(manifest, sort_keys=True, indent=2)
            key = hashlib.sha256(manifest_json.encode()).hexdigest()
            directory = root.resolve() / key
            directory.mkdir(parents=True, exist_ok=True)
            suffix = ".dylib" if sys.platform == "darwin" else ".dll" if os.name == "nt" else ".so"
            target = directory / ("libdlp_native" + suffix)
            with _build_lock(directory / "build.lock"):
                if target.is_file() and target.stat().st_size:
                    _BUILD_PATHS[cache_key] = target
                    return target
                # Build the exact bytes that were hashed, even if the checkout is
                # being edited by another process during compilation.
                with tempfile.TemporaryDirectory(prefix="build-", dir=directory) as temporary:
                    temporary = Path(temporary)
                    build_source = temporary / source.name
                    build_source.write_bytes(source_data)
                    (temporary / header.name).write_bytes(header_data)
                    output = temporary / target.name
                    result = subprocess.run([*command, *flags, str(build_source), "-o", str(output)],
                                            text=True, stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT, timeout=180)
                    if result.returncode:
                        raise NativeBackendError(
                            "Building the native relation backend failed. Use a C++17 clang++/g++ "
                            "compiler via CXX, or select backend='python'.\n" + result.stdout[-8000:])
                    if not output.is_file() or not output.stat().st_size:
                        raise NativeBackendError("The native compiler produced no shared library.")
                    (temporary / "build.json").write_text(manifest_json + "\n")
                    os.replace(temporary / "build.json", directory / "build.json")
                    os.replace(output, target)
            _BUILD_PATHS[cache_key] = target
            return target
    except NativeBackendError:
        raise
    except (OSError, subprocess.SubprocessError) as exc:
        raise NativeBackendError(
            f"Cannot prepare the native relation backend: {exc}. "
            "Check the CXX compiler and DLP_NATIVE_CACHE directory, or select backend='python'."
        ) from exc


def _library(path):
    with _LIBRARY_LOCK:
        if path in _LIBRARIES:
            return _LIBRARIES[path]
        try:
            library = ctypes.CDLL(str(path))
            signatures = {
                "dlp_abi_version": ([], ctypes.c_uint32),
                "dlp_last_error": ([], ctypes.c_char_p),
                "dlp_store_new": ([ctypes.POINTER(_HANDLE)], ctypes.c_int),
                "dlp_store_free": ([_HANDLE], None),
                "dlp_store_add_rows": ([_HANDLE, _U64, _SIZE, _U64P, _SIZE,
                                        ctypes.POINTER(_SIZE)], ctypes.c_int),
                "dlp_store_discard_rows": ([_HANDLE, _U64, _SIZE, _U64P, _SIZE,
                                            ctypes.POINTER(_SIZE)], ctypes.c_int),
                "dlp_store_lookup": ([_HANDLE, _U64, _SIZE, _U64P, _U64P, _SIZE,
                                      ctypes.POINTER(_SIZE)], ctypes.c_int),
                "dlp_store_relation_info": ([_HANDLE, _U64, ctypes.POINTER(_SIZE),
                                             ctypes.POINTER(_SIZE),
                                             ctypes.POINTER(ctypes.c_int)], ctypes.c_int),
                "dlp_query_new": ([_HANDLE, _HANDLE, ctypes.POINTER(_Atom), _SIZE,
                                   _SIZE, _U64P, ctypes.c_int64,
                                   ctypes.POINTER(_HANDLE)], ctypes.c_int),
                "dlp_query_next": ([_HANDLE, _U64P, _SIZE, ctypes.POINTER(_SIZE),
                                    ctypes.POINTER(ctypes.c_int)], ctypes.c_int),
                "dlp_query_stats": ([_HANDLE, _U64P, _U64P], ctypes.c_int),
                "dlp_query_free": ([_HANDLE], None),
            }
            for name, (arguments, result) in signatures.items():
                function = getattr(library, name)
                function.argtypes, function.restype = arguments, result
            if library.dlp_abi_version() != _ABI_VERSION:
                raise NativeBackendError(f"Native backend ABI mismatch in {path}; provide ABI {_ABI_VERSION} or rebuild it.")
        except (OSError, AttributeError) as exc:
            raise NativeBackendError(
                f"Cannot load native backend {path}: {exc}. Provide a compatible library via "
                "DLP_NATIVE_LIBRARY, build with a C++17 compiler, or select backend='python'."
            ) from exc
        _LIBRARIES[path] = library
        return library


def _check(library, result):
    if result:
        message = library.dlp_last_error()
        raise NativeBackendError(message.decode("utf-8", "replace") if message
                                 else "The native relation backend reported an unknown error.")


def _release_store(library, handle, counters):
    library.dlp_store_free(handle)
    counters["native_stores_live"] -= 1


def _release_cursor(library, handle, counters):
    library.dlp_query_free(handle)
    counters["native_active_cursors"] -= 1


class NativeContext:
    """One engine's identity dictionaries, library, and native instrumentation.

    The dictionaries deliberately use Python's existing equality and hashing,
    including RDFLib's distinctions between URI references, blank nodes, and
    literals. IDs and their original Python values survive relation rebuilds.
    """

    def __init__(self, missing, *, compiler=None, cache_dir=None):
        self.missing = missing
        configured = os.environ.get("DLP_NATIVE_LIBRARY")
        self.library_path = (Path(configured).expanduser().resolve() if configured
                             else build_native(compiler, cache_dir))
        self.library = _library(self.library_path)
        self._terms = {}
        self._values = [missing]
        self._predicates = {}
        self._indexes = weakref.WeakSet()
        self._cursors = weakref.WeakSet()
        self._lock = threading.RLock()
        self._closed = False
        self._counters = {name: 0 for name in (
            "native_stores_created", "native_stores_live", "native_bulk_calls",
            "native_rows_inserted", "native_rows_deleted", "native_queries",
            "native_batches", "native_bindings", "native_active_cursors",
            "native_lookup_calls")}

    def _ensure_open(self):
        if self._closed:
            raise NativeBackendError("The native relation context is closed.")

    def term_id(self, term):
        identifier = self._terms.get(term)
        if identifier is None:
            identifier = len(self._values)
            self._terms[term] = identifier
            self._values.append(term)
        return identifier

    def predicate_id(self, predicate):
        identifier = self._predicates.get(predicate)
        if identifier is None:
            identifier = len(self._predicates) + 1
            self._predicates[predicate] = identifier
        return identifier

    def reset_stats(self):
        with self._lock:
            for name in self._counters:
                if name not in {"native_stores_live", "native_active_cursors"}:
                    self._counters[name] = 0

    def stats(self):
        with self._lock:
            return {**self._counters, "native_terms": len(self._terms),
                    "native_predicates": len(self._predicates)}

    def close(self):
        with self._lock:
            if self._closed:
                return
            for cursor in list(self._cursors):
                cursor.close()
            for index in list(self._indexes):
                index.close()
            self._closed = True

    def __enter__(self):
        self._ensure_open()
        return self

    def __exit__(self, *_):
        self.close()


class _Rows(Mapping):
    """Compatibility surface; binary positive tuples are decoded on demand."""

    def __init__(self, index):
        self._index = weakref.ref(index)

    def get(self, predicate, default=None):
        index = self._index()
        if index is None:
            raise NativeBackendError("The native relation index no longer exists.")
        index._ensure_open()
        if predicate in index._mirrors:
            return index._mirrors[predicate] or default
        arity = index._arities.get(predicate)
        if arity is None:
            return default
        rows = index.lookup(predicate, (index.context.missing,) * arity)
        return set(rows) if rows else default

    def __getitem__(self, predicate):
        marker = object()
        result = self.get(predicate, marker)
        if result is marker:
            raise KeyError(predicate)
        return result

    def __iter__(self):
        index = self._index()
        if index is None:
            raise NativeBackendError("The native relation index no longer exists.")
        for predicate in tuple(index._arities):
            if self.get(predicate):
                yield predicate

    def __len__(self):
        return sum(1 for _ in self)


class _Cursor:
    def __init__(self, index, delta, atoms, width, initial, delta_position):
        self.context = context = index.context
        self.indexes = tuple(dict.fromkeys(i for i in (index, delta) if i is not None))
        self.versions = tuple(i._version for i in self.indexes)
        self.width = width
        self._handle = _HANDLE()
        context._ensure_open()
        _check(context.library, context.library.dlp_query_new(
            index._handle, delta._handle if delta is not None else None,
            atoms, len(atoms), width, initial,
            -1 if delta_position is None else delta_position, ctypes.byref(self._handle)))
        context._counters["native_queries"] += 1
        context._counters["native_active_cursors"] += 1
        self._finalizer = weakref.finalize(self, _release_cursor, context.library,
                                          self._handle, context._counters)
        context._cursors.add(self)
        self.candidates = self.matches = 0

    def _check_valid(self):
        self.context._ensure_open()
        if not self._handle:
            raise NativeBackendError("The native query cursor is closed.")
        for index, version in zip(self.indexes, self.versions):
            index._ensure_open()
            if index._version != version:
                raise NativeBackendError("The native relation index changed while a query was active.")

    def read(self, output, capacity):
        with self.context._lock:
            self._check_valid()
            written, done = _SIZE(), ctypes.c_int()
            library = self.context.library
            _check(library, library.dlp_query_next(self._handle, output, capacity,
                                                  ctypes.byref(written), ctypes.byref(done)))
            candidates, matches = _U64(), _U64()
            _check(library, library.dlp_query_stats(self._handle, ctypes.byref(candidates),
                                                   ctypes.byref(matches)))
            self.candidates, self.matches = candidates.value, matches.value
            self.context._counters["native_batches"] += 1
            self.context._counters["native_bindings"] += written.value
            return written.value, bool(done.value)

    def close(self):
        with self.context._lock:
            if self._handle:
                self._finalizer()
                self._handle = _HANDLE()


class NativeIndex:
    """Persistent native relation sets with exact membership/column indexes.

    Additions and removals are coalesced until a native read, then transferred
    once per changed predicate and operation. Unary relations retain Python
    sets for the existing specialized intersection plans. EQ/NEQ retain sets
    for the Python semantic checks. Other tuple/column indexes live in C++.
    """

    def __init__(self, context, facts=()):
        self.context = context
        self._handle = _HANDLE()
        self._pending = {}
        self._arities = {}
        self._mirrors = {}
        self._version = 0
        self.rows = _Rows(self)
        with context._lock:
            context._ensure_open()
            _check(context.library, context.library.dlp_store_new(ctypes.byref(self._handle)))
            context._counters["native_stores_created"] += 1
            context._counters["native_stores_live"] += 1
            self._finalizer = weakref.finalize(self, _release_store, context.library,
                                              self._handle, context._counters)
            context._indexes.add(self)
        try:
            for fact in facts:
                self.add(fact)
        except BaseException:
            self.close()
            raise

    def _ensure_open(self):
        self.context._ensure_open()
        if not self._handle:
            raise NativeBackendError("The native relation index is closed.")

    def _change(self, fact, present):
        context = self.context
        with context._lock:
            self._ensure_open()
            predicate, arity = fact.predicate, len(fact.args)
            old_arity = self._arities.get(predicate)
            if old_arity is not None and old_arity != arity:
                if not present:
                    return
                # Updates can retire a predicate's final old occurrence and
                # introduce it at a new arity while retaining other relations.
                self.flush()
                stored_arity, count, exists = _SIZE(), _SIZE(), ctypes.c_int()
                _check(context.library, context.library.dlp_store_relation_info(
                    self._handle, context.predicate_id(predicate), ctypes.byref(stored_arity),
                    ctypes.byref(count), ctypes.byref(exists)))
                if count.value:
                    raise NativeBackendError(f"Inconsistent native relation arity for {predicate!r}.")
                self._mirrors.pop(predicate, None)
            if old_arity is None and not present:
                return
            self._arities[predicate] = arity
            if arity == 1 or predicate in {EQ, NEQ}:
                mirror = self._mirrors.setdefault(predicate, set())
                if present:
                    mirror.add(fact.args)
                else:
                    mirror.discard(fact.args)
            identifier = context.predicate_id(predicate)
            row = tuple(context.term_id(term) for term in fact.args)
            self._pending.setdefault(identifier, (arity, {}))[1][row] = present
            self._version += 1

    def add(self, fact):
        self._change(fact, True)

    def discard(self, fact):
        self._change(fact, False)

    def flush(self):
        context = self.context
        with context._lock:
            self._ensure_open()
            for predicate, (arity, changes) in list(self._pending.items()):
                for present in (False, True):
                    rows = [row for row, operation in changes.items() if operation == present]
                    if not rows:
                        continue
                    flat = (_U64 * (len(rows) * arity))(*(value for row in rows for value in row))
                    changed = _SIZE()
                    operation = (context.library.dlp_store_add_rows if present
                                 else context.library.dlp_store_discard_rows)
                    _check(context.library, operation(self._handle, predicate, arity, flat,
                                                       len(rows), ctypes.byref(changed)))
                    context._counters["native_bulk_calls"] += 1
                    counter = "native_rows_inserted" if present else "native_rows_deleted"
                    context._counters[counter] += changed.value
                    for row in rows:
                        del changes[row]
                del self._pending[predicate]

    def lookup(self, predicate, values):
        context = self.context
        with context._lock:
            self._ensure_open()
            arity = self._arities.get(predicate)
            if arity is None:
                return ()
            if arity != len(values):
                raise NativeBackendError(f"Inconsistent native lookup arity for {predicate!r}.")
            if predicate in self._mirrors:
                rows = self._mirrors[predicate]
                if all(value is not context.missing for value in values):
                    return (values,) if values in rows else ()
                if arity == 1 or all(value is context.missing for value in values):
                    return rows
            encoded = []
            for value in values:
                identifier = 0 if value is context.missing else context._terms.get(value)
                if identifier is None:
                    return ()
                encoded.append(identifier)
            self.flush()
            values_buffer = (_U64 * arity)(*encoded)
            count = _SIZE()
            library = context.library
            identifier = context._predicates[predicate]
            context._counters["native_lookup_calls"] += 1
            _check(library, library.dlp_store_lookup(self._handle, identifier, arity,
                                                    values_buffer, None, 0, ctypes.byref(count)))
            if not count.value:
                return ()
            output = (_U64 * (arity * count.value))()
            _check(library, library.dlp_store_lookup(self._handle, identifier, arity,
                                                    values_buffer, output, count.value,
                                                    ctypes.byref(count)))
            decode = context._values
            return tuple(tuple(decode[output[row * arity + col]] for col in range(arity))
                         for row in range(count.value))

    def arity(self, predicate):
        self._ensure_open()
        return self._arities.get(predicate)

    def solutions(self, plan, engine, missing, delta_index=None, delta_position=None, initial=None):
        """Stream positive join bindings without rebuilding relation snapshots."""
        context = self.context
        if missing is not context.missing:
            raise NativeBackendError("Native query uses a different unbound-value sentinel.")
        if delta_index is not None and delta_index.context is not context:
            raise NativeBackendError("Native full and delta indexes must share their term dictionary.")
        if delta_position is not None and delta_index is None:
            raise NativeBackendError("A native delta atom requires its delta index.")
        initial = {} if initial is None else initial
        variables = plan.variables
        width = len(variables)
        buffers = []
        atoms = (_Atom * len(plan.atoms))()
        with context._lock:
            self.flush()
            if delta_index is not None:
                delta_index.flush()
            for position, (predicate, terms) in enumerate(plan.atoms):
                slots = (_I32 * len(terms))(*(slot for slot, _ in terms))
                constants = (_U64 * len(terms))(*(
                    context.term_id(engine.normalize(term)) if slot < 0 else 0
                    for slot, term in terms))
                buffers.extend((slots, constants))
                atoms[position] = _Atom(context.predicate_id(predicate), len(terms), slots, constants)
            binding = (_U64 * width)(*(
                0 if initial.get(variable, missing) is missing else context.term_id(initial[variable])
                for variable in variables))
            cursor = _Cursor(self, delta_index, atoms, width, binding, delta_position)
        # The native cursor owns copies of plan metadata, never borrowed arrays.
        del buffers, atoms, binding
        output = (_U64 * (width * _BATCH_SIZE))()
        decode = context._values
        stats = engine.stats
        previous_candidates = 0
        try:
            done = False
            while not done:
                count, done = cursor.read(output, _BATCH_SIZE)
                stats["candidate_rows"] += cursor.candidates - previous_candidates
                previous_candidates = cursor.candidates
                for row in range(count):
                    # A caller can mutate after any yield, even inside a batch.
                    # Reject it before returning an already prefetched binding.
                    cursor._check_valid()
                    offset = row * width
                    stats["body_matches"] += 1
                    yield {**initial, **{variable: decode[output[offset + slot]]
                                         for slot, variable in enumerate(variables)}}
        finally:
            cursor.close()
            stats.update(context.stats())

    def close(self):
        with self.context._lock:
            if self._handle:
                self._version += 1
                self._finalizer()
                self._handle = _HANDLE()
                self._pending.clear()
                self._mirrors.clear()

    def __enter__(self):
        self._ensure_open()
        return self

    def __exit__(self, *_):
        self.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build the optional persistent C++ relation backend.")
    parser.add_argument("--build", action="store_true", required=True,
                        help="build or locate the cached shared library")
    parser.add_argument("--compiler", help="C++17 compiler command (default: CXX, clang++, g++, c++)")
    parser.add_argument("--cache-dir", type=Path, help="override DLP_NATIVE_CACHE/user cache directory")
    args = parser.parse_args(argv)
    try:
        print(build_native(args.compiler, args.cache_dir))
    except NativeBackendError as exc:
        parser.exit(1, f"Native backend error: {exc}\n")


if __name__ == "__main__":
    main()
