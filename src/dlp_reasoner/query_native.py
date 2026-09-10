"""Host boundary for the native finite-query interpreter, with no scalar callbacks.

The C++ context keeps source relations resident. Each query transfers a copied,
validated plan and currently active term metadata; typed operations and strata
run entirely in C++. Providers/custom domain registries use the advertised hybrid
path in QueryRuntime. Loading does not install or download dependencies.
"""
from __future__ import annotations

from collections import defaultdict
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

from rdflib import Literal, URIRef

from .domain_native import _CODES, _Value, _pack, _unpack
from .domains import DomainError, DomainRegistry, UNITS, _literal, decode
from .engine import _literal_key
from .model import EQ, NEQ, Var
from .native import _build_lock, _cache_root
from .query_ir import Aggregate, Bind, Filter, ProviderScan, RelationAtom


_LOCK = threading.Lock()
_LIBRARIES = {}
_CONTROL = c.CFUNCTYPE(c.c_int, c.c_void_p)


class _Arg(c.Structure):
    _fields_ = [("slot", c.c_int32), ("constant", c.c_uint64)]


class _Node(c.Structure):
    _fields_ = [("kind", c.c_uint32), ("opcode", c.c_uint32), ("predicate", c.c_uint64),
                ("arity", c.c_size_t), ("args", c.POINTER(_Arg)), ("output", _Arg),
                ("group_count", c.c_size_t), ("groups", c.POINTER(c.c_int32)),
                ("value_slot", c.c_int32)]


class _Limits(c.Structure):
    _fields_ = [(name, c.c_uint64) for name in
                ("max_rows", "max_bindings", "max_rounds", "max_terms", "max_work")]


class _Stats(c.Structure):
    _fields_ = [(name, c.c_uint64) for name in
                ("rounds", "candidate_rows", "body_matches", "operation_rows", "domain_evaluations",
                 "generated_terms", "input_additions", "input_removals", "work")]
    _fields_ += [(name, c.c_uint64) for name in
                 ("memo_hits", "memo_entries", "memo_bytes", "memo_evictions", "memo_bypasses")]


def build_native_query(compiler=None, cache_dir=None):
    root = Path(__file__).parent
    names = ("native_query.cpp", "native_query.h", "native_domains.cpp", "native_domains.h",
             "vendor/date/date.h", "vendor/geographiclib/geodesic.c", "vendor/geographiclib/geodesic.h")
    sources = {name: (root / name).read_bytes() for name in names}
    try:
        requested = compiler or os.environ.get("CXX")
        command = shlex.split(str(requested)) if requested else []
        executable = shutil.which(command[0]) if command else (
            shutil.which("clang++") or shutil.which("g++") or shutil.which("c++"))
        if not executable:
            raise DomainError("UNAVAILABLE", "Native queries require a C++17 clang++/g++ compiler")
        command = [str(Path(executable).resolve()), *command[1:]]
        flags = ["-std=c++17", "-O3", "-DNDEBUG", "-shared", "-DDLP_HAVE_GEODESIC=1"]
        cflags = ["-x", "c", "-std=c99", "-O3", "-DNDEBUG"]
        if os.name != "nt":
            flags.append("-fPIC")
            cflags.append("-fPIC")
        version = subprocess.run([*command, "--version"], check=True, capture_output=True,
                                 text=True, timeout=30).stdout
        manifest = dict(abi=1, platform=sys.platform, machine=platform.machine(), compiler=command,
                        compiler_version=version, flags=flags, cflags=cflags,
                        sources={name: hashlib.sha256(data).hexdigest() for name, data in sources.items()})
        encoded = json.dumps(manifest, sort_keys=True)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        cache = Path(cache_dir) if cache_dir is not None else _cache_root() / "queries"
        directory = cache.expanduser().resolve() / digest
        directory.mkdir(parents=True, exist_ok=True)
        suffix = ".dylib" if sys.platform == "darwin" else ".dll" if os.name == "nt" else ".so"
        target = directory / ("libdlp_queries" + suffix)
        with _build_lock(directory / "build.lock"):
            if target.is_file() and target.stat().st_size:
                return target
            with tempfile.TemporaryDirectory(prefix="build-", dir=directory) as temporary:
                temporary = Path(temporary)
                for name, data in sources.items():
                    path = temporary / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                obj, output = temporary / "geodesic.o", temporary / target.name
                for args in ([*command, *cflags, "-c", str(temporary / "vendor/geographiclib/geodesic.c"), "-o", str(obj)],
                             [*command, *flags, str(temporary / "native_query.cpp"),
                              str(temporary / "native_domains.cpp"), str(obj), "-o", str(output)]):
                    result = subprocess.run(args, capture_output=True, text=True, timeout=180)
                    if result.returncode:
                        raise DomainError("UNAVAILABLE", "Native query build failed:\n" + (result.stdout + result.stderr)[-8000:])
                if not output.is_file() or not output.stat().st_size:
                    raise DomainError("UNAVAILABLE", "Compiler produced no native query library")
                (temporary / "build.json").write_text(encoded + "\n")
                os.replace(temporary / "build.json", directory / "build.json")
                os.replace(output, target)
        return target
    except DomainError:
        raise
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise DomainError("UNAVAILABLE", f"Cannot build native query capability: {exc}") from exc


def _library():
    environment = tuple(os.environ.get(key) for key in ("DLP_QUERY_LIBRARY", "DLP_NATIVE_CACHE", "CXX"))
    with _LOCK:
        if environment not in _LIBRARIES:
            try:
                path = Path(environment[0]).expanduser().resolve() if environment[0] else build_native_query()
                lib = c.CDLL(str(path))
                signatures = {
                    "abi_version": ([], c.c_uint32), "last_error": ([], c.c_char_p),
                    "last_status": ([], c.c_int32),
                    "new": ([c.POINTER(_Limits), c.POINTER(c.c_void_p)], c.c_int),
                    "free": ([c.c_void_p], None), "begin": ([c.c_void_p], c.c_int),
                    "validate": ([c.c_void_p], c.c_int),
                    "rows": ([c.c_void_p, c.c_uint64, c.c_size_t, c.POINTER(c.c_uint64), c.c_size_t, c.c_int], c.c_int),
                    "term": ([c.c_void_p, c.c_uint64, c.POINTER(_Value), c.c_int32, c.c_int, c.c_uint32, c.c_uint64], c.c_int),
                    "term_order": ([c.c_void_p, c.c_uint64, c.c_char_p, c.c_size_t, c.c_char_p, c.c_size_t], c.c_int),
                    "term_roles": ([c.c_void_p, c.c_uint64, c.c_uint32], c.c_int),
                    "memo_limits": ([c.c_void_p, c.c_uint64, c.c_uint64], c.c_int),
                    "rule": ([c.c_void_p, c.c_uint64, c.c_uint64, c.c_size_t, c.POINTER(_Arg), c.c_size_t,
                              c.POINTER(c.c_uint64), c.POINTER(_Node), c.c_size_t], c.c_int),
                    "run": ([c.c_void_p, _CONTROL, c.c_void_p], c.c_int),
                    "result": ([c.c_void_p, c.c_uint64, c.c_size_t, c.c_size_t, c.POINTER(c.c_uint64),
                                c.c_size_t, c.POINTER(c.c_size_t), c.POINTER(c.c_int)], c.c_int),
                    "value": ([c.c_void_p, c.c_uint64, c.POINTER(_Value)], c.c_int),
                    "get_stats": ([c.c_void_p, c.POINTER(_Stats)], c.c_int),
                }
                for name, (args, result) in signatures.items():
                    function = getattr(lib, "dlp_qx_" + name)
                    function.argtypes, function.restype = args, result
                if lib.dlp_qx_abi_version() != 1:
                    raise DomainError("UNAVAILABLE", "Native query ABI mismatch")
                _LIBRARIES[environment] = lib
            except (OSError, AttributeError) as exc:
                raise DomainError("UNAVAILABLE", f"Cannot load native query capability: {exc}") from exc
        return _LIBRARIES[environment]


def hybrid_reasons(prepared, domains):
    reasons = set()
    # Custom registries may override a familiar opcode/URI's behavior; only the
    # unchanged built-in descriptor table is a native scalar execution promise.
    standard = DomainRegistry().operations
    trusted = type(domains) is DomainRegistry and domains.operations == standard
    for rule in prepared.rules:
        for node in rule.body:
            if isinstance(node, ProviderScan):
                reasons.add("provider scan requires host orchestration")
            elif isinstance(node, (Bind, Filter)):
                try:
                    operation = domains.get(node.operation)
                except (KeyError, ValueError):
                    reasons.add("provider scalar requires host orchestration")
                else:
                    if not trusted or not operation.opcode:
                        reasons.add("custom domain registry requires host orchestration")
    return tuple(sorted(reasons))


def _term_metadata(term):
    packed, code, canonical = _Value(), 1, False
    try:
        decoded = decode(term)
        packed = _pack(decoded)
        canonical = term == _literal(decoded)
        code = 0
    except DomainError as exc:
        code = next((number for number, name in _CODES.items() if name == exc.code), 1)
    return packed, code, canonical


def term_role_flags(term):
    """Boundary coercion profile: unit eligibility/code and anniversary policy."""
    flags, text = 0, str(term)
    if text in ("march1", "urn:dlp:calendar-policy:march1", "urn:dlp:proposed:calendar-policy:march1"):
        flags |= 2
    if isinstance(term, (str, URIRef, Literal)):
        flags |= 1
        unit = text.replace("urn:dlp:proposed:unit:", "urn:dlp:unit:")
        unit = "urn:dlp:unit:" + unit if unit in ("metre", "second", "kmh") else unit
        if unit in UNITS:
            flags |= (UNITS.index(unit) + 1) << 2
    return flags


def term_order_keys(term):
    """Stable MIN identities shared by the live and native-package encoders."""
    from .query_runtime import minimum_identity_key
    try:
        decoded = decode(term)
        # Non-ordered types can never reach a successful MIN comparison.
        from .domains import order_key
        order_key(term)
        return ("\0".join(minimum_identity_key(term)).encode("utf-8"),
                "\0".join(minimum_identity_key(_literal(decoded))).encode("utf-8"))
    except (DomainError, UnicodeError):
        return b"", b""


class NativeQueryContext:
    def __init__(self, runtime):
        self.runtime, self.owner = runtime, runtime._native
        self.lib, self.handle = _library(), c.c_void_p()
        self.limits = _Limits(runtime.max_rows, runtime.max_bindings, runtime.max_rounds,
                              min(runtime.max_terms, runtime.max_native_terms), runtime.max_native_work)
        if any(value >= 2**64 for value in (runtime.max_rows, runtime.max_bindings, runtime.max_rounds,
                                           runtime.max_terms, runtime.max_native_terms, runtime.max_native_work)):
            raise ValueError("native query limits must fit unsigned 64-bit integers")
        self._facts = set()
        self._check(self.lib.dlp_qx_new(c.byref(self.limits), c.byref(self.handle)))
        self._finalizer = weakref.finalize(self, self.lib.dlp_qx_free, self.handle)
        self._check(self.lib.dlp_qx_memo_limits(self.handle, runtime.operation_cache_size, runtime.max_operation_cache_bytes))

    def _check(self, code):
        if code:
            from .query_runtime import QueryExecutionError
            status = self.lib.dlp_qx_last_status()
            detail = self.lib.dlp_qx_last_error().decode("utf-8", "replace")
            if status in (6, 7, 9):
                raise QueryExecutionError(detail)
            raise DomainError(_CODES.get(status, "INTERNAL_ERROR"), detail)

    def memo_info(self):
        if not self.handle:
            return {"entries": 0, "estimated_bytes": 0}
        stats = _Stats()
        self._check(self.lib.dlp_qx_get_stats(self.handle, c.byref(stats)))
        return {"entries": stats.memo_entries, "estimated_bytes": stats.memo_bytes,
                "last_query_hits": stats.memo_hits, "last_query_evictions": stats.memo_evictions,
                "last_query_bypasses": stats.memo_bypasses,
                "max_entries": self.runtime.operation_cache_size,
                "max_bytes": self.runtime.max_operation_cache_bytes}

    def clear_memo(self):
        if self.handle:
            self._check(self.lib.dlp_qx_memo_limits(self.handle, 0, 0))
            self._check(self.lib.dlp_qx_memo_limits(self.handle, self.runtime.operation_cache_size,
                                                  self.runtime.max_operation_cache_bytes))

    def _sync(self, inputs):
        wanted = {(predicate, row) for predicate, rows in inputs.items() for row in rows}
        try:
            for changes, add in ((self._facts - wanted, False), (wanted - self._facts, True)):
                batches = defaultdict(list)
                for predicate, row in changes:
                    batches[predicate, len(row)].append(row)
                for (predicate, arity), rows in batches.items():
                    for start in range(0, len(rows), 512):
                        batch = rows[start:start + 512]
                        flat = (c.c_uint64 * (len(batch) * arity))(*(self.owner.term_id(v) for row in batch for v in row))
                        self._check(self.lib.dlp_qx_rows(self.handle, self.owner.predicate_id(predicate),
                                    arity, flat, len(batch), int(add)))
            self._facts = wanted
        except BaseException:
            self.close()
            raise

    def evaluate(self, prepared, inputs, initial):
        runtime = self.runtime
        self._check(self.lib.dlp_qx_begin(self.handle))
        self._sync(inputs)
        # Include predicates in the current-term budget without inventing RDF
        # values: the C++ value capacity gets the remaining explicit allowance.
        # Placeholders are opaque metadata only, never relation arguments.
        active = {self.owner.term_id(value): value for value in runtime._current_terms}
        literal_keys = {}
        for term_id, term in active.items():
            packed, code, canonical = _term_metadata(term)
            key = _literal_key(term)
            group = {"number": 1, "boolean": 2, "string": 3, "lang": 4}.get(key[0], 0) if key else 0
            key_id = literal_keys.setdefault(key, len(literal_keys) + 1) if key else 0
            self._check(self.lib.dlp_qx_term(self.handle, term_id, c.byref(packed), code, int(canonical), group, key_id))
            order, canonical_order = term_order_keys(term)
            self._check(self.lib.dlp_qx_term_order(self.handle, term_id, order, len(order), canonical_order, len(canonical_order)))
            self._check(self.lib.dlp_qx_term_roles(self.handle, term_id, term_role_flags(term)))
        reserved = max(active, default=0) + 1
        for offset, _ in enumerate(runtime._current_predicates):
            self._check(self.lib.dlp_qx_term(self.handle, reserved + offset, c.byref(_Value()), 1, 0, 0, 0))
        # All arrays are copied by rule(), so their lifetimes need only cover
        # that call. They carry host RDF IDs, never pointers to Python objects.
        head_arities = {}
        for stratum, rules in enumerate(prepared.strata):
            for rule in rules:
                variables = set(initial)
                for node in (rule.head, *rule.body):
                    if isinstance(node, Aggregate):
                        variables.update(node.group_by)
                        variables.update((node.value, node.output))
                        node = node.source
                    variables.update(term for term in node.args if isinstance(term, Var))
                    if isinstance(node, Bind) and isinstance(node.output, Var):
                        variables.add(node.output)
                slots = {variable: index for index, variable in enumerate(sorted(variables, key=lambda v: v.name))}
                def arg(term):
                    return _Arg(slots[term], 0) if isinstance(term, Var) else _Arg(-1, self.owner.term_id(runtime.normalize(term)))
                head = (_Arg * len(rule.head.args))(*(arg(term) for term in rule.head.args))
                seed = (c.c_uint64 * len(slots))(*(self.owner.term_id(initial[v]) if v in initial else 0 for v in slots))
                arrays, nodes = [], []
                for node in rule.body:
                    actual = node.source if isinstance(node, Aggregate) else node
                    args = (_Arg * len(actual.args))(*(arg(term) for term in actual.args))
                    arrays.append(args)
                    if isinstance(node, RelationAtom):
                        name = str(node.predicate)
                        kind = 1 if name == EQ else 2 if name == NEQ else 0
                        predicate = name if kind in (1, 2) else node.predicate
                        data = _Node(kind=kind, predicate=self.owner.predicate_id(predicate), arity=len(args), args=args)
                    elif isinstance(node, Aggregate):
                        groups = (c.c_int32 * len(node.group_by))(*(slots[v] for v in node.group_by))
                        arrays.append(groups)
                        data = _Node(kind=5, predicate=self.owner.predicate_id(node.source.predicate), arity=len(args),
                                     args=args, output=arg(node.output), group_count=len(groups), groups=groups,
                                     value_slot=slots[node.value])
                    else:
                        operation = runtime.domains.get(node.operation)
                        data = _Node(kind=3 if isinstance(node, Filter) else 4, opcode=operation.opcode,
                                     arity=len(args), args=args, output=arg(node.output) if isinstance(node, Bind) else _Arg(-1, 0))
                    nodes.append(data)
                body = (_Node * len(nodes))(*nodes)
                self._check(self.lib.dlp_qx_rule(self.handle, stratum, self.owner.predicate_id(rule.head.predicate),
                            len(head), head, len(slots), seed, body, len(body)))
                head_arities[rule.head.predicate] = len(head)
        errors = []
        @_CONTROL
        def control(_):
            try:
                runtime._check_budget(0)
                return 0
            except BaseException as exc:
                errors.append(exc)
                return 1
        status = self.lib.dlp_qx_run(self.handle, control, None)
        if errors:
            raise errors[0]
        self._check(status)
        stats = _Stats()
        self._check(self.lib.dlp_qx_get_stats(self.handle, c.byref(stats)))
        runtime.stats.update({name: getattr(stats, name) for name, _ in _Stats._fields_})
        runtime.stats["native_term_metadata_rows"] = len(active)
        output_values = dict(active)
        derived = {}
        for predicate, arity in head_arities.items():
            rows, offset = set(), 0
            while True:
                runtime._check_budget(0)
                flat = (c.c_uint64 * (512 * arity))()
                written, done = c.c_size_t(), c.c_int()
                self._check(self.lib.dlp_qx_result(self.handle, self.owner.predicate_id(predicate), arity, offset,
                            flat, 512, c.byref(written), c.byref(done)))
                for number in range(written.value):
                    row = []
                    for term_id in flat[number * arity:(number + 1) * arity]:
                        if term_id not in output_values:
                            packed = _Value()
                            self._check(self.lib.dlp_qx_value(self.handle, term_id, c.byref(packed)))
                            output_values[term_id] = _literal(_unpack(packed))
                        row.append(output_values[term_id])
                    rows.add(tuple(row))
                offset += written.value
                if done.value:
                    break
            derived[predicate] = rows
        return derived

    def close(self):
        if self.handle:
            self._finalizer()
            self.handle = c.c_void_p()
        self._facts.clear()
