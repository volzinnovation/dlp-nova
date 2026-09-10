"""Author/load portable .dlpn packages through the CPython-free native loader.

DLPNPKG1 complements the general JSON .dlppkg envelope with a bounded binary
builder stream. It carries the compiled Horn program, typed dictionary, local
query plan, semantic profile and provenance. Provider transport plans are rejected.
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
import struct
import subprocess
import sys
import tempfile
import threading
import time
from types import MappingProxyType

from rdflib import BNode, Literal, URIRef

from .domains import PROFILE, DomainRegistry
from .engine import Engine, _SEED, _literal_key
from .model import Atom, EQ, NEQ, TOP, Program, Rule, Skolem, Var, IncompleteReasoningError
from .native import _build_lock, _cache_root
from .standalone import NativeRuntime, _Limits, _Stats, _ordered, _variables
from .domain_native import _Value, _unpack
from .query_native import _Limits as _QueryLimits, _Stats as _QueryStats, _CONTROL

_MAGIC = b"DLPNPKG1"
_HEADER = struct.Struct("<8sQ32s")
_MAX_BYTES, _MAX_TEXT = 64 * 1024 * 1024, 1024 * 1024


class NativePackageError(ValueError):
    """Malformed, incompatible, or unsupported native compiled artifact."""


def _u32(number):
    return struct.pack("<I", number)


def _u64(number):
    return struct.pack("<Q", number)


def _text(value):
    if type(value) is not str:
        raise NativePackageError("Native package text must be a string")
    data = value.encode("utf-8")
    if len(data) > _MAX_TEXT:
        raise NativePackageError("Native package text exceeds 1MiB")
    return _u32(len(data)) + data


def _term(value):
    if value is _SEED:
        return b"\x06" + _text(str(value))
    if isinstance(value, URIRef):
        return b"\x01" + _text(str(value))
    if isinstance(value, BNode):
        return b"\x02" + _text(str(value))
    if isinstance(value, Literal):
        flags = 2 if value.language else 1 if value.datatype else 0
        return (b"\x03" + _text(str(value)) + bytes([flags])
                + (_text(value.language) if flags == 2 else
                   _text(str(value.datatype)) if flags == 1 else b""))
    if type(value) is str:
        return b"\x04" + _text(value)
    if type(value) is int:
        return b"\x05" + _text(str(value))
    raise NativePackageError(f"Unsupported portable term type: {type(value).__name__}")


def _layout(program, extra_terms=(), extra_predicates=()):
    # Same stable ordering as the direct NativeRuntime builder. This authoring
    # step never builds a library or materializes the compiled rule program.
    terms, predicates, symbols = {_SEED}, {EQ, NEQ, TOP, *extra_predicates}, set()

    def collect(value):
        if isinstance(value, Var):
            return
        if isinstance(value, Skolem):
            symbols.add(value.symbol)
            for child in value.args:
                collect(child)
            if any(_variables(value)):
                return
        terms.add(value)

    for value in extra_terms:
        collect(value)
    for item in (*program.facts, *(atom for rule in program.rules
                                   for atom in (*rule.body, *((rule.head,) if rule.head else ())))):
        predicates.add(item.predicate)
        for value in item.args:
            collect(value)
    term_ids, ordered = {}, []

    def visit(value):
        if value in term_ids:
            return
        if isinstance(value, Skolem):
            for child in value.args:
                visit(child)
        term_ids[value] = len(term_ids) + 1
        ordered.append(value)

    for value in sorted(terms, key=_ordered):
        visit(value)
    return (term_ids, ordered, {value: i + 1 for i, value in enumerate(sorted(predicates, key=_ordered))},
            {value: i + 1 for i, value in enumerate(sorted(symbols))})


def dumps_native(package, *, context=None):
    """Compile portable builder bytes without running rules or a C++ compiler."""
    program = package if isinstance(package, Program) else package.program
    query = None if isinstance(package, Program) else package.query_program
    registry = DomainRegistry()
    try:
        for operation, version in getattr(package, "requirements", ()):
            if registry.get(operation).version != version:
                raise NativePackageError("Incompatible native operation requirement")
    finally:
        registry.close()
    Engine(program)  # Existing structural safety/arity validator, no materialization.
    if program.profile not in ("L0", "L1", "L2", "L3"):
        raise NativePackageError("Unsupported native Horn profile")
    if len(program.rules) > 100_000:
        raise NativePackageError("Native package rule limit exceeded")
    supplied_context = dict(getattr(package, "context", {})) if context is None else dict(context)
    metadata = {"context": supplied_context, "warnings": list(program.warnings),
                "compiler": "dlp-reasoner-native-v1", "domain_profile": PROFILE}
    source = getattr(package, "source_triples", ())
    if source:
        encoded = sorted(b"".join(_term(value) for value in triple) for triple in source)
        metadata["source_sha256"] = hashlib.sha256(b"".join(encoded)).hexdigest()
    provenance = json.dumps(metadata, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=True, allow_nan=False)
    extra_terms, extra_predicates = (), ()
    if query is not None and query.rules:
        from .native_query_package import query_symbols
        extra_terms, extra_predicates = query_symbols(query, program)
    term_ids, ordered, predicates, symbols = _layout(program, extra_terms, extra_predicates)
    payload = bytearray(_u32(1) + _text(PROFILE) + _text(program.profile) + _text(provenance)
                        + b"".join(_u64(value) for value in
                                   (predicates[EQ], predicates[NEQ], predicates[TOP], term_ids[_SEED])))
    count = 0

    def record(opcode, data):
        nonlocal count
        count += 1
        if count > 2_000_000 or len(payload) + 9 + len(data) > _MAX_BYTES:
            raise NativePackageError("Native package byte/record limit exceeded")
        payload.extend(bytes([opcode]) + _u64(len(data)) + data)

    for value, value_id in predicates.items():
        if not isinstance(value, (URIRef, str)):
            raise NativePackageError("Portable predicates must be strings or IRIs")
        record(6, _u64(value_id) + _term(value))
    for value, value_id in symbols.items():
        record(1, _u64(value_id) + _text(repr(value)) + _text(value))
    groups = {}
    for value in ordered:
        value_id = term_ids[value]
        if isinstance(value, Skolem):
            record(3, _u64(value_id) + _u64(symbols[value.symbol]) + _u32(len(value.args))
                   + b"".join(_u64(term_ids[argument]) for argument in value.args))
        else:
            category = 0 if isinstance(value, URIRef) else 1 if isinstance(value, Literal) else 2
            key = _literal_key(value)
            group = groups.setdefault(key, len(groups) + 1) if key is not None else 0
            record(2, _u64(value_id) + _u32(category) + _u64(group)
                   + _text(type(value).__name__ + ":" + repr(value)) + _term(value))
    for fact in sorted(program.facts, key=repr):
        record(4, _u64(predicates[fact.predicate]) + _u32(len(fact.args))
               + b"".join(_u64(term_ids[value]) for value in fact.args))
    for rule in program.rules:
        variables = set()
        for item in (*rule.body, *((rule.head,) if rule.head else ())):
            for value in item.args:
                variables.update(_variables(value))
        slots = {value: i for i, value in enumerate(sorted(variables, key=lambda value: value.name))}

        def expression(value, depth=0):
            if depth > 256:
                raise NativePackageError("Native expression nesting exceeds256")
            if isinstance(value, Var):
                return b"\x01" + _u64(slots[value]) + _u32(0)
            if isinstance(value, Skolem):
                return (b"\x02" + _u64(symbols[value.symbol]) + _u32(len(value.args))
                        + b"".join(expression(child, depth + 1) for child in value.args))
            return b"\x00" + _u64(term_ids[value]) + _u32(0)

        def atom(item):
            return (_u64(predicates[item.predicate]) + _u32(len(item.args))
                    + b"".join(expression(value) for value in item.args))

        if len(rule.body) > 512 or "\0" in rule.label:
            raise NativePackageError("Native rule body/label exceeds supported structural limits")
        record(5, bytes([rule.head is not None]) + _u32(len(slots))
               + b"".join(_text(variable.name) for variable in slots) + _text(rule.label)
               + (atom(rule.head) if rule.head else b"") + _u32(len(rule.body))
               + b"".join(atom(item) for item in rule.body))
    if query is not None and query.rules:
        from .native_query_package import encode_query_records
        for opcode, data in encode_query_records(query, program, term_ids, predicates):
            record(opcode, data)
    record(0, b"")
    return _HEADER.pack(_MAGIC, len(payload), hashlib.sha256(payload).digest()) + payload


class _Options(c.Structure):
    _fields_ = [("reasoning", _Limits), ("max_candidates", c.c_uint64),
                ("max_matches", c.c_uint64), ("max_violations", c.c_uint64)]


class _Parameter(c.Structure):
    _fields_ = [("name", c.c_char_p), ("id", c.c_uint64), ("value", _Value),
                ("decode_status", c.c_int32), ("canonical", c.c_uint32),
                ("neq_group", c.c_uint32), ("neq_key", c.c_uint64),
                ("identity_order", c.c_char_p), ("identity_order_size", c.c_size_t),
                ("canonical_order", c.c_char_p), ("canonical_order_size", c.c_size_t),
                ("roles", c.c_uint32)]


_LIBRARIES, _DEFAULTS = {}, {}
_LOCK = threading.Lock()


def build_native_package(compiler=None, cache_dir=None):
    root = Path(__file__).parent
    sources = {name: (root / name).read_bytes() for name in
               ("native_package.cpp", "native_package.h", "native_runtime.cpp", "native_runtime.h",
                "native_query.cpp", "native_query.h", "native_domains.cpp", "native_domains.h",
                "vendor/date/date.h", "vendor/geographiclib/geodesic.c", "vendor/geographiclib/geodesic.h")}
    command = shlex.split(str(compiler or os.environ.get("CXX", "")))
    executable = shutil.which(command[0]) if command else (
        shutil.which("clang++") or shutil.which("g++") or shutil.which("c++"))
    if not executable:
        raise NativePackageError("Native package loader requires C++17 or DLP_PACKAGE_LIBRARY")
    command = [str(Path(executable).resolve()), *command[1:]]
    flags = ["-std=c++17", "-O3", "-DNDEBUG", "-shared", "-DDLP_HAVE_GEODESIC=1"] + ([] if os.name == "nt" else ["-fPIC"])
    cflags = ["-x", "c", "-std=c99", "-O3", "-DNDEBUG"] + ([] if os.name == "nt" else ["-fPIC"])
    try:
        version = subprocess.run([*command, "--version"], capture_output=True, text=True,
                                 check=True, timeout=30).stdout
        manifest = dict(abi=1, compiler=command, compiler_version=version, flags=flags, cflags=cflags,
                        platform=sys.platform, machine=platform.machine(),
                        sources={name: hashlib.sha256(data).hexdigest() for name, data in sources.items()})
        encoded = json.dumps(manifest, sort_keys=True)
        directory = ((Path(cache_dir) if cache_dir is not None else _cache_root() / "package")
                     .expanduser().resolve() / hashlib.sha256(encoded.encode()).hexdigest())
        directory.mkdir(parents=True, exist_ok=True)
        suffix = ".dylib" if sys.platform == "darwin" else ".dll" if os.name == "nt" else ".so"
        target = directory / ("libdlp_package" + suffix)
        with _build_lock(directory / "build.lock"):
            if target.is_file() and target.stat().st_size:
                return target
            with tempfile.TemporaryDirectory(prefix="build-", dir=directory) as temporary:
                temporary = Path(temporary)
                for name, data in sources.items():
                    destination = temporary / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(data)
                output = temporary / target.name
                geodesic = temporary / "geodesic.o"
                compiled = subprocess.run([*command, *cflags, "-c", str(temporary / "vendor/geographiclib/geodesic.c"),
                                           "-o", str(geodesic)], capture_output=True, text=True, timeout=180)
                if compiled.returncode:
                    raise NativePackageError("Geodesic compilation failed: " + compiled.stderr[-8000:])
                result = subprocess.run([*command, *flags, str(temporary / "native_package.cpp"),
                                         str(temporary / "native_runtime.cpp"), str(temporary / "native_query.cpp"),
                                         str(temporary / "native_domains.cpp"), str(geodesic), "-o", str(output)],
                                        capture_output=True, text=True, timeout=180)
                if result.returncode:
                    raise NativePackageError("Native package build failed:\n"
                                             + (result.stdout + result.stderr)[-8000:])
                if not output.is_file() or not output.stat().st_size:
                    raise NativePackageError("Compiler produced no native package library")
                (temporary / "build.json").write_text(encoded + "\n")
                os.replace(temporary / "build.json", directory / "build.json")
                os.replace(output, target)
        return target
    except (OSError, subprocess.SubprocessError) as error:
        raise NativePackageError(str(error)) from error


def _library():
    environment = tuple(os.environ.get(key) for key in ("DLP_PACKAGE_LIBRARY", "DLP_NATIVE_CACHE", "CXX"))
    with _LOCK:
        if environment in _DEFAULTS:
            return _DEFAULTS[environment]
        path = Path(environment[0]).expanduser().resolve() if environment[0] else build_native_package()
        if path not in _LIBRARIES:
            try:
                lib = c.CDLL(str(path))
                signatures = {
                    "dlp_native_package_abi_version": ([], c.c_uint32),
                    "dlp_native_package_error": ([], c.c_char_p),
                    "dlp_native_package_error_code": ([], c.c_int32),
                    "dlp_native_package_load": ([c.POINTER(c.c_uint8), c.c_size_t,
                                                 c.POINTER(_Options), c.POINTER(c.c_void_p)], c.c_int),
                    "dlp_native_package_take_runtime": ([c.c_void_p, c.POINTER(c.c_void_p)], c.c_int),
                    "dlp_native_package_runtime": ([c.c_void_p, c.POINTER(c.c_void_p)], c.c_int),
                    "dlp_native_package_next_term_id": ([c.c_void_p, c.POINTER(c.c_uint64)], c.c_int),
                    "dlp_native_package_prepare_query": ([c.c_void_p, c.POINTER(_QueryLimits),
                        c.POINTER(_Parameter), c.c_size_t, c.POINTER(c.c_void_p)], c.c_int),
                    "dlp_native_package_free": ([c.c_void_p], None),
                    "dlp_qx_last_error": ([], c.c_char_p),
                    "dlp_qx_last_status": ([], c.c_int32),
                    "dlp_qx_free": ([c.c_void_p], None),
                    "dlp_qx_rows": ([c.c_void_p, c.c_uint64, c.c_size_t,
                                     c.POINTER(c.c_uint64), c.c_size_t, c.c_int], c.c_int),
                    "dlp_qx_term": ([c.c_void_p, c.c_uint64, c.POINTER(_Value), c.c_int32,
                                     c.c_int, c.c_uint32, c.c_uint64], c.c_int),
                    "dlp_qx_term_order": ([c.c_void_p, c.c_uint64, c.c_char_p, c.c_size_t,
                                           c.c_char_p, c.c_size_t], c.c_int),
                    "dlp_qx_term_roles": ([c.c_void_p, c.c_uint64, c.c_uint32], c.c_int),
                    "dlp_qx_run": ([c.c_void_p, _CONTROL, c.c_void_p], c.c_int),
                    "dlp_qx_result": ([c.c_void_p, c.c_uint64, c.c_size_t, c.c_size_t,
                        c.POINTER(c.c_uint64), c.c_size_t, c.POINTER(c.c_size_t), c.POINTER(c.c_int)], c.c_int),
                    "dlp_qx_value": ([c.c_void_p, c.c_uint64, c.POINTER(_Value)], c.c_int),
                    "dlp_qx_get_stats": ([c.c_void_p, c.POINTER(_QueryStats)], c.c_int),
                    "dlp_runtime_abi_version": ([], c.c_uint32),
                    "dlp_runtime_error": ([], c.c_char_p), "dlp_runtime_error_code": ([], c.c_int32),
                    "dlp_runtime_free": ([c.c_void_p], None),
                    "dlp_runtime_get_stats": ([c.c_void_p, c.POINTER(_Stats)], c.c_int),
                    "dlp_runtime_fact": ([c.c_void_p, c.c_size_t, c.POINTER(c.c_uint64),
                                          c.POINTER(c.c_uint64), c.c_size_t, c.POINTER(c.c_size_t)], c.c_int),
                    "dlp_runtime_normalize": ([c.c_void_p, c.c_uint64, c.POINTER(c.c_uint64)], c.c_int),
                    "dlp_runtime_term": ([c.c_void_p, c.c_uint64, c.POINTER(c.c_uint32), c.POINTER(c.c_uint64),
                                         c.POINTER(c.c_uint64), c.c_size_t, c.POINTER(c.c_size_t)], c.c_int),
                    "dlp_runtime_find_skolem": ([c.c_void_p, c.c_uint64, c.POINTER(c.c_uint64),
                                                c.c_size_t, c.POINTER(c.c_uint64)], c.c_int),
                    "dlp_runtime_violation": ([c.c_void_p, c.c_size_t, c.POINTER(c.c_char_p)], c.c_int),
                }
                for name, (args, result) in signatures.items():
                    function = getattr(lib, name)
                    function.argtypes, function.restype = args, result
                if lib.dlp_native_package_abi_version() != 1 or lib.dlp_runtime_abi_version() != 1:
                    raise NativePackageError("Native package/runtime ABI mismatch")
                _LIBRARIES[path] = lib
            except (OSError, AttributeError) as error:
                raise NativePackageError(f"Cannot load native package library: {error}") from error
        _DEFAULTS[environment] = _LIBRARIES[path]
        return _DEFAULTS[environment]


class _Reader:
    """Python object reconstruction only AFTER the C++ loader validated bytes."""
    def __init__(self, data):
        self.data, self.offset = data, 0

    def number(self, size):
        value = int.from_bytes(self.data[self.offset:self.offset + size], "little")
        self.offset += size
        return value

    def text(self):
        size = self.number(4)
        value = self.data[self.offset:self.offset + size].decode("utf-8")
        self.offset += size
        return value

    def term(self):
        kind, text = self.number(1), self.text()
        if kind == 3:
            flags = self.number(1)
            extra = self.text() if flags else None
            return Literal(text, datatype=URIRef(extra) if flags == 1 else None,
                           lang=extra if flags == 2 else None, normalize=False)
        return {1: URIRef, 2: BNode, 4: str, 5: int, 6: lambda _: _SEED}[kind](text)


def _reconstruct(data):
    reader = _Reader(data[48:])
    reader.number(4)
    reader.text()  # required semantic profile
    profile, context = reader.text(), reader.text()
    for _ in range(4):
        reader.number(8)
    terms, predicates, symbols, facts, rules, heads = {}, {}, {}, set(), [], {}
    while reader.offset < len(reader.data):
        opcode, length = reader.number(1), reader.number(8)
        record = _Reader(reader.data[reader.offset:reader.offset + length])
        reader.offset += length
        if opcode == 0:
            break
        if opcode == 6:
            value_id = record.number(8)
            predicates[value_id] = record.term()
        elif opcode == 1:
            value_id = record.number(8)
            record.text()
            symbols[value_id] = record.text()
        elif opcode == 2:
            value_id = record.number(8)
            record.number(4)
            record.number(8)
            record.text()
            terms[value_id] = record.term()
        elif opcode == 3:
            value_id, symbol, arity = record.number(8), record.number(8), record.number(4)
            terms[value_id] = Skolem(symbols[symbol], tuple(terms[record.number(8)] for _ in range(arity)))
        elif opcode == 4:
            predicate, arity = record.number(8), record.number(4)
            facts.add(Atom(predicates[predicate], tuple(terms[record.number(8)] for _ in range(arity))))
        elif opcode == 5:
            head, variables_count = record.number(1), record.number(4)
            variable_names = [record.text() for _ in range(variables_count)]
            label = record.text()

            def expression():
                kind, ref, count = record.number(1), record.number(8), record.number(4)
                if kind == 2:
                    return Skolem(symbols[ref], tuple(expression() for _ in range(count)))
                return Var(variable_names[ref]) if kind == 1 else terms[ref]

            def atom():
                predicate, arity = record.number(8), record.number(4)
                return Atom(predicates[predicate], tuple(expression() for _ in range(arity)))

            head = atom() if head else None
            body = tuple(atom() for _ in range(record.number(4)))
            rules.append(Rule(head, body, label))
        elif opcode == 10:
            record.number(8)
            predicate, arity = record.number(8), record.number(4)
            if predicate in heads and heads[predicate] != arity:
                raise NativePackageError("Query head arity conflict")
            heads[predicate] = arity
    try:
        metadata = json.loads(context)
    except ValueError:
        metadata = {"opaque_context": context}
    warnings = metadata.get("warnings", []) if isinstance(metadata, dict) else []
    return Program(rules, facts, profile, warnings), terms, predicates, symbols, metadata, heads


class _PackageOwner:
    """Free a borrowed Horn handle through the package/library that owns it."""
    def __init__(self, library, package):
        self.library, self.package = library, package

    def __getattr__(self, name):
        return getattr(self.library, name)

    def dlp_runtime_free(self, _handle):
        if self.package:
            self.library.dlp_native_package_free(self.package)
            self.package = c.c_void_p()


def loads_native(data, *, max_rounds=1000, max_facts=1_000_000, max_depth=32,
                 max_terms=1_000_000, max_candidates=100_000_000, max_matches=10_000_000,
                 max_violations=100_000):
    """Return a completed NativeRuntime whose closure was loaded/executed in C++."""
    if type(data) is not bytes or not 48 <= len(data) <= _MAX_BYTES + 48:
        raise NativePackageError("Native package buffer exceeds size bounds")
    limits = dict(max_rounds=max_rounds, max_facts=max_facts, max_depth=max_depth,
                  max_terms=max_terms, max_candidates=max_candidates,
                  max_matches=max_matches, max_violations=max_violations)
    for name, value in limits.items():
        if type(value) is not int or not 0 <= value < 2**64 or (name != "max_depth" and not value):
            raise ValueError(f"Invalid {name}")
    options = _Options(_Limits(max_rounds, max_facts, max_terms, max_depth),
                       max_candidates, max_matches, max_violations)
    lib, handle = _library(), c.c_void_p()
    buffer = (c.c_uint8 * len(data)).from_buffer_copy(data)
    status = lib.dlp_native_package_load(buffer, len(data), c.byref(options), c.byref(handle))
    if status:
        code = lib.dlp_native_package_error_code()
        message = lib.dlp_native_package_error().decode("utf-8", "replace")
        raise (IncompleteReasoningError if code in (3, 6) else NativePackageError)(message)
    runtime = None
    try:
        program, terms, predicates, symbols, metadata, heads = _reconstruct(data)
        runtime = NativeRuntime.__new__(NativeRuntime)
        runtime._lock, runtime._handle = threading.RLock(), c.c_void_p()
        owner = _PackageOwner(lib, handle)
        runtime._lib, runtime._limits = owner, limits
        runtime._package_owner, runtime._query_heads = owner, heads
        runtime._facts, runtime._decoded = None, {}
        runtime.program, runtime.rules, runtime.asserted = program, tuple(program.rules), frozenset(program.facts)
        runtime.backend, runtime._revision, runtime.complete = "standalone-native", 0, True
        runtime._term_values, runtime._predicate_values, runtime._symbol_values = terms, predicates, symbols
        runtime._terms = {value: value_id for value_id, value in terms.items()}
        runtime._predicates = {value: value_id for value_id, value in predicates.items()}
        runtime._symbols = {value: value_id for value_id, value in symbols.items()}
        runtime.package_context = MappingProxyType(metadata) if isinstance(metadata, dict) else metadata
        if lib.dlp_native_package_runtime(handle, c.byref(runtime._handle)):
            raise NativePackageError(lib.dlp_native_package_error().decode())
        handle = c.c_void_p()  # The package owner now controls the borrowed runtime.
        runtime.stats = runtime._stats()
        runtime.violations = runtime._violations()
        return runtime
    except BaseException:
        if runtime is not None:
            runtime.close()
        raise
    finally:
        lib.dlp_native_package_free(handle)


def dump_native(package, path, **options):
    Path(path).write_bytes(dumps_native(package, **options))


def load_native(path, **limits):
    with Path(path).open("rb") as stream:
        data = stream.read(_MAX_BYTES + 49)
    return loads_native(data, **limits)


def _query_identity(value):
    """Restrict dynamic inputs to immutable typed values, including witnesses."""
    from .domains import _VALUES, FloatValue, identity_key
    if value is _SEED:
        return type(_SEED), _SEED
    if type(value) is Skolem:
        if type(value.symbol) is not str or type(value.args) is not tuple:
            raise NativePackageError("Witness input must have immutable fields")
        return Skolem, value.symbol, tuple(_query_identity(child) for child in value.args)
    if type(value) not in (URIRef, BNode, Literal, str, int, bool, float, *_VALUES):
        raise NativePackageError("Query inputs must be supported immutable ground terms")
    if type(value) is float:
        FloatValue(value)  # Raw binary64 carriers have the same finite domain.
    return identity_key(value)


class NativePackageQuery:
    """Owned native plan and source snapshot, with explicit host input selection.

    ``parameters`` maps given variable names to immutable ground values;
    ``relations`` maps predicate IRIs/strings to iterables of ground tuples.
    These rows supplement the canonical Horn closure. No completeness, location,
    or event-window selection is inferred here. Re-prepare after changing inputs.
    A successful run returns a mapping of query head predicates to frozen rows.
    The originating runtime must remain open and unchanged through the run.
    """
    def __init__(self, runtime, *, parameters=None, relations=None, max_rows=1_000_000,
                 max_bindings=1_000_000, max_rounds=1000, max_terms=1_000_000,
                 max_work=100_000_000):
        self.runtime, self.handle = runtime, c.c_void_p()
        self.stats, self.complete, self._result = MappingProxyType({}), False, None
        self._running = False
        limits = (max_rows, max_bindings, max_rounds, max_terms, max_work)
        if any(type(value) is not int or not 0 < value < 2**64 for value in limits):
            raise ValueError("Native query limits must be positive uint64 integers")
        self.limits = _QueryLimits(*limits)
        with runtime._lock:
            runtime._open()
            self.owner = getattr(runtime, "_package_owner", None)
            if not self.owner or not self.owner.package or not runtime._query_heads:
                raise NativePackageError("Snapshot has no active packaged local query plan")
            if getattr(runtime, "_package_query_running", False):
                raise NativePackageError("Reentrant package query execution")
            self.lib, self.revision = self.owner.library, runtime._revision
            runtime._package_query_running = True
            try:
                fresh = c.c_uint64()
                self._package_check(self.lib.dlp_native_package_next_term_id(self.owner.package, c.byref(fresh)))
                self.fresh, self.next_id = fresh.value, fresh.value
                self.host_values, self.new_ids = {}, {}
                self.dictionary_ids = {_query_identity(term): identifier
                                       for identifier, term in runtime._term_values.items()}
                self.literal_keys = {}
                for identifier, term in sorted(runtime._term_values.items()):
                    key = _literal_key(term)
                    if key is not None:
                        self.literal_keys.setdefault(key, len(self.literal_keys) + 1)
                self.predicates = dict(runtime._predicates)
                self.heads = dict(runtime._query_heads)
                self.registered = set()
                items = []
                for name, term in (parameters or {}).items():
                    name = name.name if isinstance(name, Var) else name
                    if type(name) is not str or "\0" in name or len(name.encode()) > _MAX_TEXT:
                        raise NativePackageError("Invalid query parameter name")
                    identifier = self._id(term)
                    packed, code, canonical, group, key, order, output_order, roles = self._metadata(term)
                    items.append(_Parameter(name.encode(), identifier, packed, code, canonical, group, key,
                                            order, len(order), output_order, len(output_order), roles))
                    self.registered.add(identifier)
                    if len(items) > 4096:
                        raise NativePackageError("Query parameter bound exceeded")
                arguments = (_Parameter * len(items))(*items)
                self._package_check(self.lib.dlp_native_package_prepare_query(self.owner.package,
                    c.byref(self.limits), arguments, len(arguments), c.byref(self.handle)))
                input_count = 0
                for predicate, rows in (relations or {}).items():
                    if not isinstance(predicate, (str, URIRef)):
                        raise NativePackageError("Input predicates must be strings or IRIs")
                    if str(predicate) in (EQ, NEQ):
                        predicate = str(predicate)
                    predicate_id = self.predicates.setdefault(predicate, max(self.predicates.values(), default=0) + 1)
                    for row in rows:
                        input_count += 1
                        if input_count > max_rows:
                            raise IncompleteReasoningError("Native package input row bound exceeded")
                        if type(row) is not tuple or len(row) > 4096:
                            raise NativePackageError("Input rows must be ground tuples of bounded arity")
                        identifiers = []
                        for term in row:
                            identifier = self._id(term)
                            if identifier >= self.fresh and identifier not in self.registered:
                                packed, code, canonical, group, key, order, output_order, roles = self._metadata(term)
                                self._check(self.lib.dlp_qx_term(self.handle, identifier, c.byref(packed),
                                                               code, canonical, group, key))
                                self._check(self.lib.dlp_qx_term_order(self.handle, identifier,
                                    order, len(order), output_order, len(output_order)))
                                self._check(self.lib.dlp_qx_term_roles(self.handle, identifier, roles))
                                self.registered.add(identifier)
                            identifiers.append(identifier)
                        encoded = (c.c_uint64 * len(identifiers))(*identifiers)
                        self._check(self.lib.dlp_qx_rows(self.handle, predicate_id, len(row), encoded, 1, 1))
            except BaseException:
                self.close()
                raise
            finally:
                runtime._package_query_running = False

    def _existing_id(self, term):
        known = self.dictionary_ids.get(_query_identity(term), 0)
        if known:
            return known
        if type(term) is Skolem and term.symbol in self.runtime._symbols:
            children = [self._existing_id(child) for child in term.args]
            if all(children):
                values, found = (c.c_uint64 * len(children))(*children), c.c_uint64()
                self.runtime._check(self.lib.dlp_runtime_find_skolem(self.runtime._handle,
                    self.runtime._symbols[term.symbol], values, len(values), c.byref(found)))
                return found.value
        return 0

    def _id(self, term):
        if isinstance(term, Var) or any(_variables(term)):
            raise NativePackageError("Query inputs must be ground")
        try:
            key = _query_identity(term)
            hash(key)
        except TypeError as error:
            raise NativePackageError("Query inputs must be immutable") from error
        identifier = self._existing_id(term)
        if identifier:
            normalized = c.c_uint64()
            self.runtime._check(self.lib.dlp_runtime_normalize(self.runtime._handle, identifier,
                                                             c.byref(normalized)))
            return normalized.value
        if key not in self.new_ids:
            if len(self.new_ids) >= self.limits.max_terms or self.next_id >= 2**64:
                raise IncompleteReasoningError("Native query term bound exceeded")
            self.new_ids[key] = self.next_id
            self.host_values[self.next_id] = term
            self.next_id += 1
        return self.new_ids[key]

    def _metadata(self, term):
        from .query_native import _term_metadata, term_order_keys, term_role_flags
        packed, code, canonical = _term_metadata(term)
        key = _literal_key(term)
        group = {"number": 1, "boolean": 2, "string": 3, "lang": 4}.get(key[0], 0) if key else 0
        key_id = self.literal_keys.setdefault(key, len(self.literal_keys) + 1) if key else 0
        order, output_order = term_order_keys(term)
        return packed, code, canonical, group, key_id, order, output_order, term_role_flags(term)

    def _package_check(self, result):
        if result:
            code = self.lib.dlp_native_package_error_code()
            message = self.lib.dlp_native_package_error().decode("utf-8", "replace")
            raise (IncompleteReasoningError if code in (3, 6) else NativePackageError)(message)

    def _check(self, result):
        if result:
            from .domain_native import _CODES
            from .domains import DomainError
            status = self.lib.dlp_qx_last_status()
            message = self.lib.dlp_qx_last_error().decode("utf-8", "replace")
            if status in (6, 9):
                raise IncompleteReasoningError(message)
            raise DomainError(_CODES.get(status, "INTERNAL"), message)

    def _guard(self):
        if not self.handle:
            raise NativePackageError("Prepared query is closed")
        if (not self.runtime._handle or not self.owner.package
                or self.runtime._revision != self.revision):
            raise NativePackageError("Originating package snapshot changed or closed")

    def run(self, *, deadline=None, cancel=None):
        """Run in C++; reuse successful immutable results on the same snapshot.

        Every call checks source lifetime, cancellation and deadline, including
        completed result reuse. Re-prepare after a failed execution.
        """
        from .domains import _literal
        with self.runtime._lock:
            self._guard()
            if getattr(self.runtime, "_package_query_running", False):
                raise NativePackageError("Reentrant package query execution")
            self.runtime._package_query_running = True
            self._running = True
            failures = []

            def control(_):
                try:
                    self._guard()
                    if deadline is not None and time.monotonic() >= deadline:
                        raise IncompleteReasoningError("Native package query deadline exceeded")
                    if cancel is not None and (cancel() if callable(cancel) else cancel.is_set()):
                        raise IncompleteReasoningError("Native package query cancelled")
                    return 0
                except BaseException as error:
                    failures.append(error)
                    return 1

            try:
                if control(None):
                    raise failures[0]
                if self._result is not None:
                    self.complete = True
                    return self._result
                status = self.lib.dlp_qx_run(self.handle, _CONTROL(control), None)
                if failures:
                    raise failures[0]
                self._check(status)
                result, decoded = {}, dict(self.host_values)

                def decode_term(identifier):
                    if identifier not in decoded:
                        if identifier < self.fresh:
                            value = self.runtime._term_values.get(identifier)
                            # Source rows/constants were already canonicalized
                            # before qx execution. A scalar operation may select
                            # the exact canonical RDF output spelling of an
                            # existing dictionary term; do not normalize that
                            # newly computed value through Horn equality again.
                            decoded[identifier] = (self.runtime._decode(identifier)
                                if value is None or isinstance(value, Skolem) else value)
                        else:
                            packed = _Value()
                            self._check(self.lib.dlp_qx_value(self.handle, identifier, c.byref(packed)))
                            decoded[identifier] = _literal(_unpack(packed))
                    return decoded[identifier]

                for predicate, arity in self.heads.items():
                    rows, offset, done = set(), 0, c.c_int()
                    while not done.value:
                        output, written = (c.c_uint64 * (512 * arity))(), c.c_size_t()
                        self._check(self.lib.dlp_qx_result(self.handle, predicate, arity, offset,
                                                          output, 512, c.byref(written), c.byref(done)))
                        for index in range(written.value):
                            rows.add(tuple(decode_term(output[index * arity + i]) for i in range(arity)))
                        offset += written.value
                    result[self.runtime._predicate_values[predicate]] = frozenset(rows)
                if control(None):
                    raise failures[0]
                stats = _QueryStats()
                self._check(self.lib.dlp_qx_get_stats(self.handle, c.byref(stats)))
                self.stats = MappingProxyType({name: getattr(stats, name) for name, _ in stats._fields_})
                self._result, self.complete = MappingProxyType(result), True
                return self._result
            except BaseException:
                self.complete = False
                raise
            finally:
                self.runtime._package_query_running = False
                self._running = False

    def close(self):
        with self.runtime._lock:
            if self._running:
                raise NativePackageError("Cannot close an executing prepared query")
            if self.handle:
                self.lib.dlp_qx_free(self.handle)
                self.handle = c.c_void_p()

    def __enter__(self):
        self._guard()
        return self

    def __exit__(self, *_):
        self.close()

    def __del__(self):
        if getattr(self, "handle", None):
            self.lib.dlp_qx_free(self.handle)
