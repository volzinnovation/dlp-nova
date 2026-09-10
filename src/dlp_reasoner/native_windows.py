"""Native event-window memory, with the WindowStore protocol at the Python boundary.

Only retained key identities are mirrored in Python to preserve Python hashing
and equality. Event records, retention, clocks, revisions and checkpoints live
in the C++ store. Importing this module never builds or loads a library.
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
import weakref

from .native import NativeBackendError, _build_lock, _cache_root
from .providers import _decode, _packed
from .windows import (Event, EventRevisionError, LateEventError, ReplayGapError,
                      WindowChange, WindowError, WindowResourceError, WindowStore, _integer)


class _Bytes(c.Structure):
    _fields_ = [("data", c.c_void_p), ("size", c.c_size_t)]


class _Event(c.Structure):
    _fields_ = [("id", _Bytes), ("key", _Bytes), ("row", _Bytes),
                ("time", c.c_int64), ("revision", c.c_int64)]


class _Config(c.Structure):
    _fields_ = [(name, c.c_int64) for name in ("width", "lateness", "end", "watermark")] + [
        (name, c.c_uint64) for name in ("max_events", "max_bytes", "max_keys")] + [
        (name, c.c_uint32) for name in ("predecessors", "allow_gaps")]


class _Info(c.Structure):
    _fields_ = [(name, c.c_uint64) for name in ("revision", "events", "tombstones", "bytes", "sources")] + [
        (name, c.c_int64) for name in ("end", "watermark")]


_LOCK = threading.Lock()
_LIBRARIES = {}


def build_native_windows(compiler=None, cache_dir=None):
    root = Path(__file__).parent
    try:
        sources = {name: (root / name).read_bytes() for name in ("native_windows.cpp", "native_windows.h")}
        command = shlex.split(compiler or os.environ.get("CXX", ""))
        executable = shutil.which(command[0]) if command else (
            shutil.which("clang++") or shutil.which("g++") or shutil.which("c++"))
        if not executable:
            raise NativeBackendError("Native windows require C++17 or DLP_WINDOWS_LIBRARY")
        command = [str(Path(executable).resolve()), *command[1:]]
        version = subprocess.run([*command, "--version"], check=True, capture_output=True,
                                 text=True, timeout=30).stdout
        flags = ["-std=c++17", "-O3", "-shared"] + ([] if os.name == "nt" else ["-fPIC"])
        manifest = dict(abi=1, platform=sys.platform, machine=platform.machine(),
                        pointer=c.sizeof(c.c_void_p), compiler=command, version=version, flags=flags,
                        sources={name: hashlib.sha256(data).hexdigest() for name, data in sources.items()})
        encoded = json.dumps(manifest, sort_keys=True)
        cache = Path(cache_dir) if cache_dir is not None else _cache_root() / "windows"
        directory = cache.expanduser().resolve() / hashlib.sha256(encoded.encode()).hexdigest()
        directory.mkdir(parents=True, exist_ok=True)
        suffix = ".dylib" if sys.platform == "darwin" else ".dll" if os.name == "nt" else ".so"
        target = directory / ("libdlp_windows" + suffix)
        with _build_lock(directory / "build.lock"):
            if target.is_file() and target.stat().st_size:
                return target
            with tempfile.TemporaryDirectory(dir=directory) as folder:
                folder = Path(folder)
                for name, data in sources.items():
                    (folder / name).write_bytes(data)
                output = folder / target.name
                result = subprocess.run([*command, *flags, str(folder / "native_windows.cpp"),
                                         "-o", str(output)], capture_output=True, text=True, timeout=180)
                if result.returncode or not output.is_file():
                    raise NativeBackendError("Native window build failed:\n" + result.stderr[-8000:])
                (folder / "build.json").write_text(encoded + "\n")
                os.replace(folder / "build.json", directory / "build.json")
                os.replace(output, target)
        return target
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise NativeBackendError(f"Cannot build native windows: {exc}") from exc


def _library():
    environment = tuple(os.environ.get(key) for key in ("DLP_WINDOWS_LIBRARY", "DLP_NATIVE_CACHE", "CXX"))
    with _LOCK:
        if environment in _LIBRARIES:
            return _LIBRARIES[environment]
        try:
            lib = c.CDLL(environment[0] or str(build_native_windows()))
            h, hp, p = c.c_void_p, c.POINTER(c.c_void_p), c.POINTER
            signatures = {
                "abi": ([], c.c_uint32), "error": ([], c.c_char_p), "error_code": ([], c.c_int32),
                "new": ([p(_Config), _Bytes, hp], c.c_int), "free": ([h], None),
                "info": ([h, p(_Info)], c.c_int), "config": ([h, p(_Config), p(_Bytes)], c.c_int),
                "event": ([h, _Bytes, p(_Event), p(c.c_int)], c.c_int),
                "predecessor": ([h, _Bytes, p(_Event), p(c.c_int)], c.c_int),
                "offset": ([h, c.c_size_t, p(_Bytes), p(c.c_int64)], c.c_int),
                "upsert": ([h, p(_Event), _Bytes, c.c_int64, hp], c.c_int),
                "remove": ([h, _Bytes, c.c_int64, hp], c.c_int),
                "advance": ([h, c.c_int64, c.c_int64, hp], c.c_int),
                "forget": ([h, _Bytes, hp], c.c_int), "rows": ([h, c.c_uint32, hp], c.c_int),
                "next": ([h, p(_Event), c.c_size_t, p(c.c_size_t), p(c.c_int)], c.c_int),
                "rows_free": ([h], None),
                "change_next": ([h, c.c_uint32, p(_Event), c.c_size_t, p(c.c_size_t), p(c.c_int)], c.c_int),
                "change_revision": ([h, p(c.c_uint64)], c.c_int), "change_free": ([h], None),
                "checkpoint": ([h, h, c.c_size_t, p(c.c_size_t)], c.c_int),
                "restore": ([h, c.c_size_t, c.c_uint64, c.c_uint64, c.c_uint64, c.c_uint64, p(_Bytes), hp], c.c_int),
            }
            for name, (arguments, result) in signatures.items():
                fn = getattr(lib, "dlp_windows_" + name)
                fn.argtypes, fn.restype = arguments, result
            if lib.dlp_windows_abi() != 1:
                raise NativeBackendError("Native window ABI mismatch")
        except (OSError, AttributeError) as exc:
            raise NativeBackendError(f"Cannot load native windows: {exc}") from exc
        _LIBRARIES[environment] = lib
        return lib


def _check(lib, status):
    if status:
        message = lib.dlp_windows_error().decode("utf-8", "replace")
        cls = {2: WindowResourceError, 3: LateEventError, 4: EventRevisionError, 5: ReplayGapError}.get(
            lib.dlp_windows_error_code(), WindowError)
        raise cls(message)


def _input(data):
    # The c_char_p and bytes remain in ctypes' ownership graph through the call.
    return _Bytes(c.cast(c.c_char_p(data), c.c_void_p), len(data))


def _output(data):
    return c.string_at(data.data, data.size)


def _text(value, name, *, empty=False):
    if type(value) is not str or (not value and not empty):
        raise WindowError(f"{name} must be a nonempty string")
    try:
        return value.encode("utf-8")
    except UnicodeError as exc:
        raise WindowError(f"{name} must be valid UTF-8") from exc


def _unpack(data):
    try:
        value = _decode(json.loads(data))
        if _packed(value) != data:
            raise WindowError("Noncanonical native window value")
        return value
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, RecursionError) as exc:
        raise WindowError(f"Malformed native window value: {exc}") from exc


def _record(record):
    row = _unpack(_output(record.row))
    if type(row) is not tuple or len(row) < 3:
        raise WindowError("Malformed native event row")
    event = Event(row[0], row[1], row[2], row[3:], record.revision)
    if _text(event.event_id, "event ID") != _output(record.id) or event.event_time != record.time:
        raise WindowError("Native event row differs from metadata")
    key = _output(record.key)
    if _unpack(key) != event.key:
        raise WindowError("Native grouping key differs from event key")
    return event, key


class NativeWindowStore:
    """WindowStore-compatible owner; use close/context manager for prompt release.

    Checkpoints are native binary v1, separate from WindowStore's JSON v1.
    Pure Python entry predicates run at the API boundary; native mobile callers
    consume active/predecessor rows and apply their own compiled predicates.
    """

    def __init__(self, width, **options):
        reference = WindowStore(width, **options)  # shared public input validation only
        lib = _library()
        cfg = _Config(reference.width, reference.allowed_lateness, reference.evaluation_time,
                      reference.watermark, reference.max_events, reference.max_bytes, reference.max_keys,
                      reference.retain_predecessor, reference.allow_offset_gaps)
        handle = c.c_void_p()
        _check(lib, lib.dlp_windows_new(c.byref(cfg), _input(_packed(reference.context)), c.byref(handle)))
        self._adopt(lib, handle)

    def _adopt(self, lib, handle):
        self._lib, self._handle = lib, handle
        self._lock = threading.RLock()
        self._finalizer = weakref.finalize(self, lib.dlp_windows_free, handle)
        self._keys, self._counts, self._wire_keys = {}, {}, {}
        cfg, context = _Config(), _Bytes()
        try:
            _check(lib, lib.dlp_windows_config(handle, c.byref(cfg), c.byref(context)))
            self._config = cfg
            self._context = _unpack(_output(context))
            if type(self.context) is not tuple:
                raise WindowError("Native context must be a tuple")
            for event, key in self._records(2):
                if event.key in self._keys and self._keys[event.key] != key:
                    raise WindowError("Checkpoint has incompatible Python grouping keys")
                self._keys[event.key] = key
                self._counts[event.key] = self._counts.get(event.key, 0) + 1
                self._wire_keys[key] = event.key
        except BaseException:
            self.close()
            raise

    def close(self):
        with self._lock:
            self._finalizer()
            self._keys.clear()
            self._counts.clear()
            self._wire_keys.clear()

    def __enter__(self):
        self._ensure_open()
        return self

    def __exit__(self, *unused):
        self.close()

    def _ensure_open(self):
        if not self._finalizer.alive:
            raise WindowError("Native window store is closed")

    @property
    def width(self):
        return self._config.width

    @property
    def allowed_lateness(self):
        return self._config.lateness

    @property
    def max_events(self):
        return self._config.max_events

    @property
    def max_bytes(self):
        return self._config.max_bytes

    @property
    def max_keys(self):
        return self._config.max_keys

    @property
    def retain_predecessor(self):
        return bool(self._config.predecessors)

    @property
    def allow_offset_gaps(self):
        return bool(self._config.allow_gaps)

    @property
    def context(self):
        return self._context

    def _info(self):
        self._ensure_open()
        value = _Info()
        _check(self._lib, self._lib.dlp_windows_info(self._handle, c.byref(value)))
        return value

    @property
    def revision(self):
        with self._lock:
            return self._info().revision

    @property
    def evaluation_time(self):
        with self._lock:
            return self._info().end

    @property
    def watermark(self):
        with self._lock:
            return self._info().watermark

    @property
    def offsets(self):
        with self._lock:
            result = {}
            for index in range(self._info().sources):
                source, offset = _Bytes(), c.c_int64()
                _check(self._lib, self._lib.dlp_windows_offset(self._handle, index, c.byref(source), c.byref(offset)))
                result[_output(source).decode("utf-8")] = offset.value
            return result

    def info(self):
        with self._lock:
            info = self._info()
            return dict(revision=info.revision, events=info.events, tombstones=info.tombstones,
                        bytes=info.bytes, evaluation_time=info.end, watermark=info.watermark,
                        context=self.context, offsets=self.offsets)

    def _read(self, handle, mode=None, cache=None, keys_only=False):
        result = []
        batch, count, done = (_Event * 128)(), c.c_size_t(), c.c_int()
        while not done.value:
            fn = self._lib.dlp_windows_next if mode is None else self._lib.dlp_windows_change_next
            args = (handle,) if mode is None else (handle, mode)
            _check(self._lib, fn(*args, batch, 128, c.byref(count), c.byref(done)))
            for i in range(count.value):
                record = batch[i]
                if keys_only:
                    key = _output(record.key)
                    value = self._wire_keys.get(key)
                    if key not in self._wire_keys:
                        value = _unpack(key)
                    result.append((value, key))
                elif cache is None:
                    result.append(_record(record))
                else:
                    identity = record.id.data, record.revision
                    if identity not in cache:
                        cache[identity] = _record(record)
                    result.append(cache[identity])
        return result

    def _records(self, mode):
        self._ensure_open()
        cursor = c.c_void_p()
        _check(self._lib, self._lib.dlp_windows_rows(self._handle, mode, c.byref(cursor)))
        try:
            return self._read(cursor)
        finally:
            self._lib.dlp_windows_rows_free(cursor)

    def rows(self, *, include_predecessors=False):
        with self._lock:
            return frozenset(event.row for event, _ in self._records(int(bool(include_predecessors))))

    def _lookup(self, event_id, *, predecessor=False):
        self._ensure_open()
        output, found = _Event(), c.c_int()
        fn = self._lib.dlp_windows_predecessor if predecessor else self._lib.dlp_windows_event
        _check(self._lib, fn(self._handle, _input(_text(event_id, "event ID")), c.byref(output), c.byref(found)))
        return _record(output)[0] if found.value else None

    def predecessor(self, event_id):
        with self._lock:
            if self._lookup(event_id) is None:
                raise KeyError(event_id)
            return self._lookup(event_id, predecessor=True)

    def entry_rows(self, predicate):
        with self._lock:
            # One bounded export and Python key grouping avoids per-row ABI scans.
            events = [event for event, _ in self._records(2)]
            groups = {}
            for event in events:
                groups.setdefault(event.key, []).append(event)
            start, end = self.evaluation_time - self.width, self.evaluation_time
            result = set()
            for values in groups.values():
                values.sort(key=lambda e: (e.event_time, e.event_id))
                for previous, event in zip(values, values[1:]):
                    if start <= event.event_time < end and predicate(event) and not predicate(previous):
                        result.add(event.row)
            return frozenset(result)

    def _mutate(self, function, *args):
        self._ensure_open()
        change = c.c_void_p()
        _check(self._lib, function(self._handle, *args, c.byref(change)))
        try:
            revision = c.c_uint64()
            _check(self._lib, self._lib.dlp_windows_change_revision(change, c.byref(revision)))
            cache = {}
            streams = [self._read(change, mode, cache=cache) for mode in range(4)]
            added_keys = self._read(change, 4, keys_only=True)
            removed_keys = self._read(change, 5, keys_only=True)
            for value, _ in removed_keys:
                self._counts[value] -= 1
            for value, key in added_keys:
                self._keys[value] = key
                self._counts[value] = self._counts.get(value, 0) + 1
                self._wire_keys[key] = value
            for key in [key for key, count in self._counts.items() if not count]:
                self._counts.pop(key)
                self._wire_keys.pop(self._keys.pop(key))
            sets = [frozenset(event.row for event, _ in stream) for stream in streams]
            # Python row equality may equate distinct typed wire forms (e.g. 0/False).
            return WindowChange(revision.value, sets[0] - sets[1], sets[1] - sets[0],
                                sets[2] - sets[3], sets[3] - sets[2])
        except BaseException:
            # The native commit succeeded; failed publication decoding must never
            # leave a usable store with a stale Python key interner.
            self.close()
            raise
        finally:
            self._lib.dlp_windows_change_free(change)

    def upsert(self, event, *, source=None, offset=None):
        if not isinstance(event, Event):
            raise WindowError("Expected Event")
        if (source is None) != (offset is None):
            raise WindowError("Source and offset must be supplied together")
        partition = b"" if source is None else _text(source, "source")
        position = -1 if offset is None else _integer(offset, "offset", minimum=0)
        with self._lock:
            old = self._lookup(event.event_id)
            if old == event:
                event = old  # Preserve exact payload on Python-equal duplicate delivery.
            key = self._keys.get(event.key, _packed(event.key))
            record = _Event(_input(_text(event.event_id, "event ID")), _input(key),
                            _input(_packed(event.row)), event.event_time, event.revision)
            return self._mutate(self._lib.dlp_windows_upsert, c.byref(record), _input(partition), position)

    def remove(self, event_id, *, revision):
        _integer(revision, "removal revision", minimum=0)
        with self._lock:
            return self._mutate(self._lib.dlp_windows_remove, _input(_text(event_id, "event ID")), revision)

    def advance(self, end, *, watermark=None):
        _integer(end, "evaluation time")
        watermark = end if watermark is None else _integer(watermark, "watermark")
        with self._lock:
            return self._mutate(self._lib.dlp_windows_advance, end, watermark)

    def forget_key(self, key):
        with self._lock:
            return self._mutate(self._lib.dlp_windows_forget, _input(self._keys.get(key, _packed(key))))

    def checkpoint(self):
        with self._lock:
            self._ensure_open()
            size = c.c_size_t()
            fn = self._lib.dlp_windows_checkpoint
            _check(self._lib, fn(self._handle, None, 0, c.byref(size)))
            output = c.create_string_buffer(size.value)
            _check(self._lib, fn(self._handle, output, size.value, c.byref(size)))
            return output.raw

    @classmethod
    def restore(cls, checkpoint, *, max_checkpoint_bytes=64 * 1024 * 1024, expected_context=None,
                max_events=10000, max_bytes=16 * 1024 * 1024, max_keys=1000):
        for name, value in (("max_checkpoint_bytes", max_checkpoint_bytes), ("max_events", max_events),
                            ("max_bytes", max_bytes), ("max_keys", max_keys)):
            _integer(value, name, minimum=1)
        if type(checkpoint) is not bytes or len(checkpoint) > max_checkpoint_bytes:
            raise WindowResourceError("Invalid or oversized native window checkpoint")
        lib, handle = _library(), c.c_void_p()
        expected = None if expected_context is None else _input(_packed(expected_context))
        _check(lib, lib.dlp_windows_restore(checkpoint, len(checkpoint), max_checkpoint_bytes,
                                            max_events, max_bytes, max_keys,
                                            None if expected is None else c.byref(expected), c.byref(handle)))
        result = cls.__new__(cls)
        result._adopt(lib, handle)
        if expected_context is not None and result.context != expected_context:
            result.close()
            raise ReplayGapError("Checkpoint static-data context does not match")
        return result
