"""Optional standalone C++17 compiled-Horn runtime (no Python rule callbacks).

This adapter supplies an RDF term dictionary and immutable compiled IR to the
native C ABI. The kernel itself has no CPython dependency. New query operators,
providers/windows and the portable JSON package loader are separate layers;
this class deliberately implements the legacy Horn Program contract only.
Updates use a complete candidate rebuild and retain the prior complete snapshot
when validation, allocation or reasoning limits prevent successful publication.
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

from rdflib import Literal, URIRef

from .engine import _SEED, _literal_key
from .model import Atom, EQ, NEQ, TOP, IncompleteReasoningError, ProfileError, Program, Rule, Skolem, Var
from .native import _build_lock, _cache_root


class NativeRuntimeError(RuntimeError):
    """Native runtime build, ABI or unexpected kernel failure."""


class _Expr(c.Structure):
    pass


_Expr._fields_ = [("kind", c.c_uint32), ("reserved", c.c_uint32),
                 ("reference", c.c_uint64), ("arity", c.c_size_t),
                 ("arguments", c.POINTER(_Expr))]


class _Atom(c.Structure):
    _fields_ = [("predicate", c.c_uint64), ("arity", c.c_size_t),
                ("arguments", c.POINTER(_Expr))]


class _Limits(c.Structure):
    _fields_ = [(name, c.c_uint64) for name in
                ("max_rounds", "max_facts", "max_terms", "max_depth")]


class _Stats(c.Structure):
    _fields_ = [(name, c.c_uint64) for name in
                ("rounds", "facts", "terms", "candidate_rows", "body_matches",
                 "equality_merges", "violations")] + [("complete", c.c_int32), ("reserved", c.c_int32)]


_LOAD_LOCK = threading.Lock()
_LIBRARIES = {}
_DEFAULTS = {}


def build_native_runtime(compiler=None, cache_dir=None):
    """Build the dependency-free kernel into a content-addressed local cache."""
    source = Path(__file__).parent
    files = {name: (source / name).read_bytes() for name in
             ("native_runtime.cpp", "native_runtime.h")}
    requested = compiler or os.environ.get("CXX")
    command = shlex.split(str(requested)) if requested else []
    executable = shutil.which(command[0]) if command else (
        shutil.which("clang++") or shutil.which("g++") or shutil.which("c++"))
    if not executable:
        raise NativeRuntimeError("Standalone runtime requires a C++17 compiler or DLP_RUNTIME_LIBRARY")
    command = [str(Path(executable).resolve()), *command[1:]]
    flags = ["-std=c++17", "-O3", "-DNDEBUG", "-shared"]
    if os.name != "nt":
        flags.append("-fPIC")
    try:
        version = subprocess.run([*command, "--version"], capture_output=True,
                                 text=True, check=True, timeout=30).stdout
        manifest = {"abi": 1, "platform": sys.platform, "machine": platform.machine(),
                    "pointer_size": c.sizeof(c.c_void_p), "compiler": command,
                    "compiler_version": version, "flags": flags,
                    "sources": {name: hashlib.sha256(data).hexdigest()
                                for name, data in files.items()}}
        encoded = json.dumps(manifest, sort_keys=True)
        directory = ((Path(cache_dir) if cache_dir is not None else _cache_root() / "runtime")
                     .expanduser().resolve() / hashlib.sha256(encoded.encode()).hexdigest())
        directory.mkdir(parents=True, exist_ok=True)
        suffix = ".dylib" if sys.platform == "darwin" else ".dll" if os.name == "nt" else ".so"
        target = directory / ("libdlp_runtime" + suffix)
        with _build_lock(directory / "build.lock"):
            if target.is_file() and target.stat().st_size:
                return target
            with tempfile.TemporaryDirectory(prefix="build-", dir=directory) as temporary:
                temporary = Path(temporary)
                for name, data in files.items():
                    (temporary / name).write_bytes(data)
                output = temporary / target.name
                result = subprocess.run([*command, *flags, str(temporary / "native_runtime.cpp"),
                                         "-o", str(output)], capture_output=True,
                                        text=True, timeout=180)
                if result.returncode:
                    raise NativeRuntimeError("Standalone build failed:\n"
                                             + (result.stdout + result.stderr)[-8000:])
                if not output.is_file() or not output.stat().st_size:
                    raise NativeRuntimeError("Compiler produced no standalone library")
                (temporary / "build.json").write_text(encoded + "\n")
                os.replace(temporary / "build.json", directory / "build.json")
                os.replace(output, target)
        return target
    except (OSError, subprocess.SubprocessError) as error:
        raise NativeRuntimeError(f"Cannot build standalone runtime: {error}") from error


def _library():
    environment = tuple(os.environ.get(key) for key in ("DLP_RUNTIME_LIBRARY", "DLP_NATIVE_CACHE", "CXX"))
    with _LOAD_LOCK:
        if environment in _DEFAULTS:
            return _DEFAULTS[environment]
        path = Path(environment[0]).expanduser().resolve() if environment[0] else build_native_runtime()
        if path not in _LIBRARIES:
            try:
                lib = c.CDLL(str(path))
                signatures = {
                    "abi_version": ([], c.c_uint32),
                    "error": ([], c.c_char_p), "error_code": ([], c.c_int32),
                    "new": ([c.c_uint64] * 4 + [c.POINTER(_Limits), c.POINTER(c.c_void_p)], c.c_int),
                    "free": ([c.c_void_p], None),
                    "cancel": ([c.c_void_p], c.c_int),
                    "set_work_limits": ([c.c_void_p, c.c_uint64, c.c_uint64, c.c_uint64], c.c_int),
                    "add_symbol": ([c.c_void_p, c.c_uint64, c.c_char_p], c.c_int),
                    "add_term": ([c.c_void_p, c.c_uint64, c.c_uint32, c.c_char_p, c.c_uint64], c.c_int),
                    "add_skolem": ([c.c_void_p, c.c_uint64, c.c_uint64,
                                    c.POINTER(c.c_uint64), c.c_size_t], c.c_int),
                    "add_fact": ([c.c_void_p, c.c_uint64, c.POINTER(c.c_uint64), c.c_size_t], c.c_int),
                    "add_rule": ([c.c_void_p, c.POINTER(_Atom), c.POINTER(_Atom),
                                  c.c_size_t, c.c_size_t, c.c_char_p], c.c_int),
                    "materialize": ([c.c_void_p], c.c_int),
                    "get_stats": ([c.c_void_p, c.POINTER(_Stats)], c.c_int),
                    "fact": ([c.c_void_p, c.c_size_t, c.POINTER(c.c_uint64),
                              c.POINTER(c.c_uint64), c.c_size_t, c.POINTER(c.c_size_t)], c.c_int),
                    "normalize": ([c.c_void_p, c.c_uint64, c.POINTER(c.c_uint64)], c.c_int),
                    "term": ([c.c_void_p, c.c_uint64, c.POINTER(c.c_uint32), c.POINTER(c.c_uint64),
                              c.POINTER(c.c_uint64), c.c_size_t, c.POINTER(c.c_size_t)], c.c_int),
                    "find_skolem": ([c.c_void_p, c.c_uint64, c.POINTER(c.c_uint64),
                                     c.c_size_t, c.POINTER(c.c_uint64)], c.c_int),
                    "violation": ([c.c_void_p, c.c_size_t, c.POINTER(c.c_char_p)], c.c_int),
                }
                for name, (args, result) in signatures.items():
                    function = getattr(lib, "dlp_runtime_" + name)
                    function.argtypes, function.restype = args, result
                if lib.dlp_runtime_abi_version() != 1:
                    raise NativeRuntimeError("Standalone runtime ABI mismatch")
                _LIBRARIES[path] = lib
            except (OSError, AttributeError) as error:
                raise NativeRuntimeError(f"Cannot load standalone runtime: {error}") from error
        _DEFAULTS[environment] = _LIBRARIES[path]
        return _DEFAULTS[environment]


def _ordered(value):
    return type(value).__name__, repr(value)


def _variables(term):
    if isinstance(term, Var):
        yield term
    elif isinstance(term, Skolem):
        for child in term.args:
            yield from _variables(child)


class NativeRuntime:
    """Materialized compiled Horn Program executed entirely by the C++ kernel.

    ``facts`` is an immutable canonical snapshot. Contradictory closures complete
    normally and expose ``violations``; failed limits raise
    IncompleteReasoningError. A failed update retains every old published field.
    Handles are serialized by this adapter. Direct C callers must serialize.
    The ABI supports at most 512 body atoms and 256 nested expression nodes.
    """

    def __init__(self, program: Program, *, max_rounds=1000, max_facts=1_000_000,
                 max_depth=32, max_terms=1_000_000, max_candidates=100_000_000,
                 max_matches=10_000_000, max_violations=100_000):
        for name, value in (("max_rounds", max_rounds), ("max_facts", max_facts),
                            ("max_depth", max_depth), ("max_terms", max_terms),
                            ("max_candidates", max_candidates), ("max_matches", max_matches),
                            ("max_violations", max_violations)):
            if type(value) is not int or not 0 <= value < 2**64 or (name != "max_depth" and value == 0):
                raise ValueError(f"Invalid {name}")
        if not isinstance(program, Program):
            raise ProfileError("Expected a compiled Horn Program")
        self._lock = threading.RLock()
        self._handle = c.c_void_p()
        self._lib = _library()
        self._limits = dict(max_rounds=max_rounds, max_facts=max_facts,
                            max_depth=max_depth, max_terms=max_terms, max_candidates=max_candidates,
                            max_matches=max_matches, max_violations=max_violations)
        self._facts = None
        self._decoded = {}
        self.complete = False
        self.program = Program(list(dict.fromkeys(program.rules)), set(program.facts),
                               program.profile, list(program.warnings))
        self.rules = tuple(self.program.rules)
        self.asserted = frozenset(self.program.facts)
        self.backend = "standalone-native"
        self._revision = 0
        try:
            self._build()
            self._check(self._lib.dlp_runtime_materialize(self._handle))
            self.complete = True
            self.stats = self._stats()
            self.violations = self._violations()
        except BaseException:
            self.close()
            raise

    def _check(self, status):
        if status:
            code = self._lib.dlp_runtime_error_code()
            message = self._lib.dlp_runtime_error().decode("utf-8", "replace")
            error = {1: ProfileError, 2: IncompleteReasoningError,
                     3: MemoryError, 5: IncompleteReasoningError}.get(code, NativeRuntimeError)
            raise error(message)

    def _open(self):
        if not self._handle:
            raise NativeRuntimeError("Standalone runtime is closed")

    def _build(self):
        terms, predicates, symbols = {_SEED}, {EQ, NEQ, TOP}, set()

        def collect(term):
            if isinstance(term, Var):
                return
            if isinstance(term, Skolem):
                if not isinstance(term.args, tuple) or not isinstance(term.symbol, str):
                    raise ProfileError("Skolem requires a string symbol and immutable arguments")
                symbols.add(term.symbol)
                for child in term.args:
                    collect(child)
                if any(_variables(term)):
                    return
            try:
                terms.add(term)
            except TypeError as error:
                raise ProfileError("Terms must be hashable") from error

        def atom(atom, ground=False):
            if not isinstance(atom, Atom) or not isinstance(atom.args, tuple):
                raise ProfileError("Atoms require immutable tuple arguments")
            if isinstance(atom.predicate, (Var, Skolem)):
                raise ProfileError("Variable/function predicates are unsupported")
            predicates.add(atom.predicate)
            for term in atom.args:
                if ground and any(_variables(term)):
                    raise ProfileError("Assertions must be ground")
                collect(term)

        for fact in self.asserted:
            atom(fact, True)
        for rule in self.rules:
            if not isinstance(rule, Rule) or not isinstance(rule.body, tuple):
                raise ProfileError("Expected immutable Rule body")
            if rule.head is not None:
                atom(rule.head)
            for body_atom in rule.body:
                atom(body_atom)
        self._predicates = {value: i + 1 for i, value in enumerate(sorted(predicates, key=_ordered))}
        self._predicate_values = {i: value for value, i in self._predicates.items()}
        self._symbols = {value: i + 1 for i, value in enumerate(sorted(symbols))}
        self._symbol_values = {i: value for value, i in self._symbols.items()}
        self._terms = {}
        ordered = []

        def visit(term):
            if term in self._terms:
                return
            if isinstance(term, Skolem):
                for child in term.args:
                    visit(child)
            self._terms[term] = len(self._terms) + 1
            ordered.append(term)

        for term in sorted(terms, key=_ordered):
            visit(term)
        self._term_values = {i: value for value, i in self._terms.items()}
        limits = _Limits(**{name: self._limits[name] for name, _ in _Limits._fields_})
        self._check(self._lib.dlp_runtime_new(self._predicates[EQ], self._predicates[NEQ],
                    self._predicates[TOP], self._terms[_SEED], c.byref(limits), c.byref(self._handle)))
        self._check(self._lib.dlp_runtime_set_work_limits(self._handle,
                    self._limits["max_candidates"], self._limits["max_matches"],
                    self._limits["max_violations"]))
        for symbol, symbol_id in self._symbols.items():
            self._check(self._lib.dlp_runtime_add_symbol(self._handle, symbol_id, repr(symbol).encode()))
        groups = {}
        for term in ordered:
            term_id = self._terms[term]
            if isinstance(term, Skolem):
                args = (c.c_uint64 * len(term.args))(*(self._terms[arg] for arg in term.args))
                self._check(self._lib.dlp_runtime_add_skolem(self._handle, term_id,
                            self._symbols[term.symbol], args, len(args)))
            else:
                category = 0 if isinstance(term, URIRef) else 1 if isinstance(term, Literal) else 2
                key = _literal_key(term)
                group = groups.setdefault(key, len(groups) + 1) if key is not None else 0
                order = (type(term).__name__ + ":" + repr(term)).encode()
                self._check(self._lib.dlp_runtime_add_term(self._handle, term_id, category, order, group))
        for fact in sorted(self.asserted, key=repr):
            args = (c.c_uint64 * len(fact.args))(*(self._terms[arg] for arg in fact.args))
            self._check(self._lib.dlp_runtime_add_fact(self._handle,
                        self._predicates[fact.predicate], args, len(args)))
        for rule in self.rules:
            keepalive = []
            variables = set()
            for item in (*rule.body, *((rule.head,) if rule.head is not None else ())):
                for term in item.args:
                    variables.update(_variables(term))
            slots = {var: i for i, var in enumerate(sorted(variables, key=lambda var: var.name))}

            def expression(term):
                if isinstance(term, Var):
                    return _Expr(kind=1, reference=slots[term])
                if isinstance(term, Skolem):
                    children = (_Expr * len(term.args))(*(expression(arg) for arg in term.args))
                    keepalive.append(children)
                    return _Expr(kind=2, reference=self._symbols[term.symbol],
                                 arity=len(children), arguments=children)
                return _Expr(kind=0, reference=self._terms[term])

            def native_atom(item):
                args = (_Expr * len(item.args))(*(expression(term) for term in item.args))
                keepalive.append(args)
                return _Atom(self._predicates[item.predicate], len(args), args)

            body = (_Atom * len(rule.body))(*(native_atom(item) for item in rule.body))
            head = native_atom(rule.head) if rule.head is not None else None
            if not isinstance(rule.label, str) or "\0" in rule.label:
                raise ProfileError("Rule labels must be strings without NUL")
            self._check(self._lib.dlp_runtime_add_rule(self._handle,
                        c.byref(head) if head is not None else None, body, len(body),
                        len(slots), rule.label.encode()))

    def _stats(self):
        native = _Stats()
        self._check(self._lib.dlp_runtime_get_stats(self._handle, c.byref(native)))
        result = {name: getattr(native, name) for name, _ in _Stats._fields_ if name != "reserved"}
        result.update(complete=bool(native.complete), backend=self.backend,
                      strategy="naive", update_method="full-atomic",
                      materialized_facts=native.facts, asserted_facts=len(self.asserted))
        return result

    def _violations(self):
        result = []
        for index in range(self.stats["violations"]):
            message = c.c_char_p()
            self._check(self._lib.dlp_runtime_violation(self._handle, index, c.byref(message)))
            result.append(message.value.decode("utf-8", "replace"))
        return tuple(result)

    def _decode(self, term_id):
        if term_id in self._decoded:
            return self._decoded[term_id]
        kind, symbol, arity = c.c_uint32(), c.c_uint64(), c.c_size_t()
        self._check(self._lib.dlp_runtime_term(self._handle, term_id, c.byref(kind),
                    c.byref(symbol), None, 0, c.byref(arity)))
        if kind.value == 0:
            canonical = c.c_uint64()
            self._check(self._lib.dlp_runtime_normalize(self._handle, term_id, c.byref(canonical)))
            value = self._term_values[canonical.value]
        else:
            args = (c.c_uint64 * arity.value)()
            self._check(self._lib.dlp_runtime_term(self._handle, term_id, c.byref(kind),
                        c.byref(symbol), args, len(args), c.byref(arity)))
            value = Skolem(self._symbol_values[symbol.value], tuple(self._decode(arg) for arg in args))
        self._decoded[term_id] = value
        return value

    @property
    def facts(self):
        with self._lock:
            self._open()
            if self._facts is None:
                facts = set()
                for index in range(self.stats["facts"]):
                    predicate, arity = c.c_uint64(), c.c_size_t()
                    self._check(self._lib.dlp_runtime_fact(self._handle, index, c.byref(predicate),
                                None, 0, c.byref(arity)))
                    args = (c.c_uint64 * arity.value)()
                    self._check(self._lib.dlp_runtime_fact(self._handle, index, c.byref(predicate),
                                args, len(args), c.byref(arity)))
                    facts.add(Atom(self._predicate_values[predicate.value],
                                   tuple(self._decode(arg) for arg in args)))
                self._facts = frozenset(facts)
            return self._facts

    def _id(self, term):
        known = self._terms.get(term)
        if known is not None:
            return known
        if isinstance(term, Skolem) and term.symbol in self._symbols:
            children = [self._id(arg) for arg in term.args]
            if all(children):
                values = (c.c_uint64 * len(children))(*children)
                found = c.c_uint64()
                self._check(self._lib.dlp_runtime_find_skolem(self._handle,
                            self._symbols[term.symbol], values, len(values), c.byref(found)))
                return found.value
        return 0

    def normalize(self, term):
        with self._lock:
            self._open()
            term_id = self._id(term)
            if term_id:
                return self._decode(term_id)
            if isinstance(term, Skolem):
                return Skolem(term.symbol, tuple(self.normalize(arg) for arg in term.args))
            return term

    def materialize(self):
        """The constructor publishes a complete snapshot; this is idempotent."""
        with self._lock:
            self._open()
            return self

    def update(self, add=(), remove=(), *, add_rules=(), remove_rules=(), rules=None):
        with self._lock:
            self._open()
            if getattr(self, "_package_query_running", False):
                raise RuntimeError("Cannot update a snapshot during package query execution")
            asserted = (set(self.asserted) - set(remove)) | set(add)
            add_rules, remove_rules = tuple(add_rules), frozenset(remove_rules)
            if rules is not None and (add_rules or remove_rules):
                raise ValueError("Use rules or add_rules/remove_rules, not both")
            updated_rules = (list(rules) if rules is not None else
                             [rule for rule in self.rules if rule not in remove_rules] + list(add_rules))
            candidate = type(self)(Program(updated_rules, asserted, self.program.profile,
                                            list(self.program.warnings)), **self._limits)
            previous, previous_library = self._handle, self._lib
            revision = self._revision + 1
            # Publication changes one Python owner only after native completion.
            for name, value in candidate.__dict__.items():
                if name != "_lock":
                    setattr(self, name, value)
            self._revision = revision
            candidate._handle = c.c_void_p()
            previous_library.dlp_runtime_free(previous)
            return self

    def prepare_query(self, parameters=None, relations=None, **limits):
        """Prepare the local plan of a loaded .dlpn artifact on this snapshot."""
        from .native_package import NativePackageQuery
        return NativePackageQuery(self, parameters=parameters, relations=relations, **limits)

    def query(self, parameters=None, relations=None, *, deadline=None, cancel=None, **limits):
        """Execute a packaged local plan; return immutable named result relations."""
        with self.prepare_query(parameters, relations, **limits) as query:
            return query.run(deadline=deadline, cancel=cancel)

    def close(self):
        with self._lock:
            if getattr(self, "_package_query_running", False):
                raise RuntimeError("Cannot close a snapshot during package query execution")
            if self._handle:
                self._lib.dlp_runtime_free(self._handle)
                self._handle = c.c_void_p()
            self.complete = False

    def __enter__(self):
        self._open()
        return self

    def __exit__(self, *_):
        self.close()

    def __del__(self):
        if getattr(self, "_handle", None):
            self._lib.dlp_runtime_free(self._handle)
            self._handle = c.c_void_p()
