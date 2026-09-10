"""Finite, stratified rule execution with atomic result publication.

The ontology keeps its existing L0–L3 evaluator. This separately versioned
extension consumes its completed, canonical relations and explicit scoped input
relations. Native execution uses resident relation indexes and batched domain
operations. Locally supported plans execute their strata in C++; provider or
custom-operation plans explicitly retain host orchestration.
"""
from __future__ import annotations

from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field, is_dataclass
from itertools import chain
import sys
from types import MappingProxyType
from typing import Mapping
import weakref

from rdflib import Literal, RDF, URIRef

from .domains import DomainRegistry, compare_values, identity_key
from .engine import _Index, _MISSING, _SEED
from .joins import RelationalPlan
from .model import Atom, EQ, NEQ, Rule, Var
from .query_ir import Aggregate, Bind, Filter, ProviderScan, RelationAtom, plan
from .query_parser import parse_query_program
from .query_cache import _SCALARS, _estimate_bytes


_CACHE_MISS = object()
_CACHE_TYPES = _SCALARS | {Literal, type(_SEED)}


def _cache_bytes(key, value, limit):
    """Bound retained entries, including metadata, without copying their payload.

    Reuse the answer-cache scalar/RDF estimator. Extend its supported containers
    to immutable query/domain/provider descriptors and mappings. Unknown custom
    objects bypass caching because their shallow size cannot bound owned memory.
    """
    total, seen, stack = 256, set(), [iter((key, value))]
    while stack:
        try:
            item = next(stack[-1])
        except StopIteration:
            stack.pop()
            continue
        if id(item) in seen:
            continue
        seen.add(id(item))
        kind = type(item)
        if kind in {tuple, list, set, frozenset}:
            total += sys.getsizeof(item)
            stack.append(iter(item))
        elif kind in {dict, MappingProxyType}:
            # MappingProxyType's shallow size excludes its owned underlying dict.
            total += max(sys.getsizeof(item), 128 + 72 * len(item))
            stack.append(chain.from_iterable(item.items()))
        elif is_dataclass(item) and kind.__module__ in {
                __name__, "dlp_reasoner.domains", "dlp_reasoner.providers"}:
            total += sys.getsizeof(item) + sys.getsizeof(vars(item))
            stack.append(iter(vars(item).values()))
        elif kind is type(_SEED):
            total += sys.getsizeof(item) + 128
        elif isinstance(item, type) and (item in _CACHE_TYPES or
                (item.__module__ == "dlp_reasoner.domains" and is_dataclass(item)
                 and getattr(sys.modules[item.__module__], item.__name__, None) is item)):
            # Registered classes already live in their owning module; a cache
            # type tag adds only a reference. Unknown user classes bypass below.
            total += 64
        else:
            estimated = _estimate_bytes((), item, max(0, limit - total))
            if estimated is None:
                return None
            total += estimated
        if total > limit:
            return total
    return total


class _ByteCache:
    def __init__(self, max_entries, max_bytes):
        self.max_entries, self.max_bytes = max_entries, max_bytes
        self.entries, self.bytes = OrderedDict(), 0
        self.hits = self.misses = self.evictions = self.bypasses = 0

    def __len__(self):
        return len(self.entries)

    def get(self, key, default=_CACHE_MISS):
        entry = self.entries.get(key, _CACHE_MISS)
        if entry is _CACHE_MISS:
            self.misses += 1
            return default
        self.hits += 1
        self.entries.move_to_end(key)
        return entry[0]

    def put(self, key, value):
        size = _cache_bytes(key, value, self.max_bytes) if self.max_entries and self.max_bytes else None
        if size is None or size > self.max_bytes:
            self.bypasses += 1
            return False
        old = self.entries.pop(key, None)
        if old is not None:
            self.bytes -= old[1]
        while self.entries and (len(self.entries) >= self.max_entries or self.bytes + size > self.max_bytes):
            _, removed = self.entries.popitem(last=False)
            self.bytes -= removed[1]
            self.evictions += 1
        self.entries[key] = value, size
        self.bytes += size
        return True

    def clear(self):
        self.entries.clear()
        self.bytes = 0

    def info(self):
        return dict(entries=len(self), estimated_bytes=self.bytes, hits=self.hits, misses=self.misses,
                    evictions=self.evictions, bypasses=self.bypasses,
                    max_entries=self.max_entries, max_bytes=self.max_bytes)


class QueryExecutionError(RuntimeError):
    """The candidate query revision failed; no complete answer was published."""


@dataclass(frozen=True)
class QueryScope:
    name: str
    revision: str

    def __post_init__(self):
        if not isinstance(self.name, str) or ":" not in self.name:
            raise ValueError("scope name must be an absolute identifier")
        if not isinstance(self.revision, str) or not self.revision:
            raise ValueError("scope revision must be a nonempty string")


@dataclass(frozen=True)
class Diagnostic:
    subject: object
    code: str
    detail: str = ""


@dataclass(frozen=True)
class QueryResult:
    scope: QueryScope
    revision: int
    relations: Mapping
    additions: Mapping
    retractions: Mapping
    diagnostics: tuple = ()
    metadata: Mapping = field(default_factory=dict)
    complete: bool = True

    def rows(self, predicate):
        return self.relations.get(URIRef(predicate), frozenset())


class _Registry:
    def __init__(self, domains, providers):
        self.domains, self.providers = domains, providers

    def get(self, operation):
        try:
            return self.domains.get(operation)
        except (KeyError, ValueError):
            if self.providers is None:
                raise
            return self.providers.get(operation)


def _freeze(relations):
    return MappingProxyType({URIRef(predicate): frozenset(rows)
                             for predicate, rows in relations.items() if rows})


def minimum_identity_key(value):
    """Deterministic original-term representative when typed MIN values tie."""
    if isinstance(value, Literal):
        return "literal", str(value.datatype or ""), value.language or "", str(value)
    return "value", type(value).__module__ + "." + type(value).__qualname__, repr(value)


class QueryRuntime:
    """Reuse a prepared extension plan against explicit finite snapshots.

    ``evaluate`` rebuilds affected derived views on a changed input snapshot.
    This conservative policy handles deletions, equality splits, nonmonotonic
    selection and MIN safely. Unchanged snapshots reuse bounded complete results.
    A context is serialized by its host; reentrant evaluation is rejected.
    """

    def __init__(self, program, *, reasoner=None, backend="python", domains=None,
                 providers=None, max_rounds=1000, max_rows=1_000_000,
                 max_bindings=1_000_000, batch_size=512, cache_size=32,
                 operation_cache_size=4096, max_cache_bytes=16 * 1024 * 1024,
                 max_operation_cache_bytes=4 * 1024 * 1024, max_terms=1_000_000,
                 max_native_terms=2_000_000, max_input_rows=2_000_000,
                 max_native_work=100_000_000):
        if backend not in {"python", "native"}:
            raise ValueError("backend must be python or native")
        for name, value in (("max_rounds", max_rounds), ("max_rows", max_rows),
                            ("max_bindings", max_bindings), ("batch_size", batch_size),
                            ("max_terms", max_terms), ("max_native_terms", max_native_terms),
                            ("max_input_rows", max_input_rows), ("max_native_work", max_native_work)):
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if type(cache_size) is not int or cache_size < 0:
            raise ValueError("cache_size must be a nonnegative integer")
        if type(operation_cache_size) is not int or operation_cache_size < 0:
            raise ValueError("operation_cache_size must be a nonnegative integer")
        for name, value in (("max_cache_bytes", max_cache_bytes),
                            ("max_operation_cache_bytes", max_operation_cache_bytes)):
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        self.program = parse_query_program(program) if isinstance(program, str) else program
        self.reasoner, self.backend = reasoner, backend
        self._owns_domains = domains is None
        self.domains = domains if domains is not None else DomainRegistry(backend=backend)
        self.providers = providers
        self.registry = _Registry(self.domains, providers)
        self.max_rounds, self.max_rows = max_rounds, max_rows
        self.max_bindings, self.batch_size = max_bindings, batch_size
        self.cache_size = cache_size
        self.max_cache_bytes, self.max_operation_cache_bytes = max_cache_bytes, max_operation_cache_bytes
        self._cache = _ByteCache(cache_size, max_cache_bytes)
        self.operation_cache_size = operation_cache_size
        self._operation_cache = _ByteCache(operation_cache_size, max_operation_cache_bytes)
        self.max_terms, self.max_native_terms = max_terms, max_native_terms
        self.max_input_rows, self.max_native_work = max_input_rows, max_native_work
        self._current_terms, self._current_predicates = set(), set()
        self._source_objects, self._source_epoch = None, 0
        self._native_compactions = 0
        self.last_complete = None
        self.complete, self._running, self._closed = False, False, False
        self._revision, self.cache_hits = 0, 0
        self._native = None
        self._native_query = None
        self._force_python_indexes = False
        self._index_mode = None
        self._host_fallback_reasons = ()
        self._index = None
        self._indexed_facts = set()
        self._index_dirty = False
        self.stats = {}
        if backend == "native":
            self._native = self._new_native_context()

    def _new_native_context(self):
        from .native import NativeContext
        limit = self.max_native_terms

        class BoundedContext(NativeContext):
            def _reserve(self, value, dictionary):
                if value not in dictionary and len(self._terms) + len(self._predicates) >= limit:
                    raise QueryExecutionError("max_native_terms exceeded; no complete result published")

            def term_id(self, term):
                self._reserve(term, self._terms)
                return super().term_id(term)

            def predicate_id(self, predicate):
                self._reserve(predicate, self._predicates)
                return super().predicate_id(predicate)

        return BoundedContext(_MISSING)

    def cache_info(self):
        """Cumulative bounded-cache counters; byte estimates are not process RSS."""
        native = None if self._native is None else self._native.stats()
        return {"results": self._cache.info(), "operations": self._operation_cache.info(),
                "native_operations": ({"entries": 0, "estimated_bytes": 0} if self._native_query is None
                                      else self._native_query.memo_info()),
                "native_dictionary_entries": 0 if native is None else
                    native["native_terms"] + native["native_predicates"],
                "native_compactions": self._native_compactions,
                "max_terms": self.max_terms, "max_native_terms": self.max_native_terms}

    def clear_cache(self):
        if self._running:
            raise QueryExecutionError("cannot clear caches during evaluation")
        self._cache.clear()
        self._operation_cache.clear()
        if self._native_query is not None:
            self._native_query.clear_memo()

    def _detached_source_key(self, token):
        if self.reasoner is None:
            return None
        graph, engine = self.reasoner.graph, self.reasoner.engine
        if self._source_objects is None or self._source_objects[0]() is not graph or self._source_objects[1]() is not engine:
            self._source_epoch += 1
            self._source_objects = weakref.ref(graph), weakref.ref(engine)
        # The live guard token retains owners for this evaluation only. Cached
        # revision keys use a monotonic weak identity epoch, avoiding both pinned
        # historical engines and object-ID reuse collisions.
        return tuple(("source-owner", self._source_epoch, "graph") if item is graph else
                     ("source-owner", self._source_epoch, "engine") if item is engine else item
                     for item in token)

    def _remember(self, values=(), predicate=None):
        limit = min(self.max_terms, self.max_native_terms) if self._native is not None else self.max_terms
        for value, target in chain(((term, self._current_terms) for term in values),
                                  () if predicate is None else ((predicate, self._current_predicates),)):
            if value not in target:
                if len(self._current_terms) + len(self._current_predicates) >= limit:
                    raise QueryExecutionError("max_terms exceeded by current query terms/predicates")
                target.add(value)

    def _remember_plan(self, prepared, initial):
        self._remember(initial.values())
        for rule in prepared.rules:
            for node in (rule.head, *rule.body):
                if isinstance(node, Aggregate):
                    node = node.source
                values = tuple(term for term in node.args if not isinstance(term, Var))
                self._remember((self.normalize(term) for term in values),
                               node.predicate if isinstance(node, RelationAtom) else None)
                if isinstance(node, Bind) and not isinstance(node.output, Var):
                    self._remember((self.normalize(node.output),))

    def _input_execution_mode(self, prepared, inputs, initial):
        """Avoid the legacy native dictionary's Python-equality alias boundary."""
        if self._native is None:
            return
        seen = {}
        values = [initial.values()]
        values.extend(row for rows in inputs.values() for row in rows)
        for rule in prepared.rules:
            for node in (rule.head, *rule.body):
                actual = node.source if isinstance(node, Aggregate) else node
                values.append(tuple(self.normalize(term) for term in actual.args if not isinstance(term, Var)))
                if isinstance(node, Bind) and not isinstance(node.output, Var):
                    values.append((self.normalize(node.output),))
        ambiguous = False
        for group in values:
            for value in group:
                key = identity_key(value)
                if value in seen and seen[value] != key:
                    ambiguous = True
                seen[value] = key
                old = self._native._terms.get(value)
                if old is not None and identity_key(self._native._values[old]) != key:
                    ambiguous = True
        self._force_python_indexes = ambiguous
        self._host_fallback_reasons = (("equal Python values have distinct scalar identities; Python relation indexes required",)
                                      if ambiguous else ())

    def _compact_native(self):
        if self._native is None:
            return
        stale = (len(self._native._terms.keys() - self._current_terms) +
                 len(self._native._predicates.keys() - self._current_predicates))
        reserve = min(self.max_terms, self.max_native_terms)
        if stale <= self.max_native_terms - reserve:
            return
        if self._native.stats()["native_active_cursors"]:
            raise QueryExecutionError("cannot compact a native context with active cursors")
        replacement = self._new_native_context()
        if self._native_query is not None:
            self._native_query.close()
            self._native_query = None
        previous = self._native
        self._native, self._index = replacement, None
        self._indexed_facts.clear()
        self._index_dirty = False
        previous.close()
        self._native_compactions += 1

    def normalize(self, term):
        if self.reasoner is not None:
            return self.reasoner.engine.normalize(term)
        return term

    def _source_key(self):
        if self.reasoner is None:
            return None
        return self.reasoner._query_cache_token()

    def _provider_key(self):
        return None if self.providers is None else self.providers.revision_key()

    def _domain_key(self):
        if getattr(self.domains, "_closed", False):
            from .domains import DomainError
            raise DomainError("UNAVAILABLE", "Domain registry is closed")
        return tuple(sorted(self.domains.operations.items()))

    def _inputs(self, relations):
        result = defaultdict(set)
        count = consumed = 0

        def add(predicate, row):
            nonlocal count, consumed
            consumed += 1
            if consumed > self.max_input_rows:
                raise QueryExecutionError("max_input_rows exceeded by input stream")
            predicate = str(predicate) if str(predicate) in {EQ, NEQ} else URIRef(predicate)
            self._remember(row, predicate)
            rows = result[predicate]
            if row not in rows:
                if count >= self.max_rows:
                    raise QueryExecutionError("max_rows exceeded by input snapshot")
                rows.add(row)
                count += 1
            self._check_budget(0)

        if self.reasoner is not None:
            self.reasoner._guard(exhaustive=True)
            for fact in self.reasoner.engine.facts:
                add(fact.predicate, fact.args)
                if isinstance(fact.predicate, URIRef) and len(fact.args) == 1:
                    add(RDF.type, (fact.args[0], fact.predicate))
        for predicate, rows in relations.items():
            for row in rows:
                if not isinstance(row, tuple) or any(isinstance(value, Var) for value in row):
                    raise QueryExecutionError("input rows must be ground immutable tuples")
                try:
                    hash(row)
                except TypeError as exc:
                    raise QueryExecutionError("input rows must contain immutable values") from exc
                add(predicate, tuple(self.normalize(value) for value in row))
        return result

    def explain(self, *, relation_arities=None):
        prepared = plan(self.program, self.registry, relation_arities=relation_arities)
        explanation = prepared.explain()
        if self.backend == "native":
            from .query_native import hybrid_reasons
            reasons = hybrid_reasons(prepared, self.domains)
            explanation["execution"] = {"mode": "hybrid" if reasons else "native",
                                        "host_orchestration_reasons": list(reasons),
                                        "input_dependent_fallback": "equal Python values with distinct scalar identities use Python indexes"}
        else:
            explanation["execution"] = {"mode": "python", "host_orchestration_reasons": []}
        return explanation

    def _new_index(self, relations):
        facts = (Atom(predicate, row) for predicate, rows in relations.items() for row in rows)
        if self._native is None or self._force_python_indexes:
            return _Index(facts)
        from .native import NativeIndex
        return NativeIndex(self._native, facts)

    def _prepare_index(self, relations):
        """Retain static native rows while replacing query inputs/old results."""
        wanted = {Atom(predicate, row) for predicate, rows in relations.items() for row in rows}
        mode = "native" if self._native is not None and not self._force_python_indexes else "python"
        if self._index_mode != mode:
            if self._index is not None and hasattr(self._index, "close"):
                self._index.close()
            self._index, self._index_mode = None, mode
            self._indexed_facts.clear()
        # A source can replace raw 1 with True, or +0.0 with -0.0, while
        # ordinary Python set differences stay empty. Rebuild this rare alias
        # transition so later scalar operations observe the actual source type.
        if self._index is not None:
            previous = {fact: fact for fact in self._indexed_facts}
            for fact in wanted:
                old = previous.get(fact)
                if old is not None and any(identity_key(a) != identity_key(b) for a, b in zip(old.args, fact.args)):
                    self._index_dirty = True
                    break
        if self._index is None or self._index_dirty:
            if self._index is not None and hasattr(self._index, "close"):
                self._index.close()
            self._index = self._new_index(relations)
            self._indexed_facts = wanted
            self._index_dirty = False
            self.stats["index_additions"] = len(wanted)
            self.stats["index_removals"] = 0
            return
        removed, added = self._indexed_facts - wanted, wanted - self._indexed_facts
        self._index_dirty = True
        for fact in removed:
            self._index.discard(fact)
        for fact in added:
            self._index.add(fact)
        self._indexed_facts = wanted
        self._index_dirty = False
        self.stats["index_additions"], self.stats["index_removals"] = len(added), len(removed)

    def _check_budget(self, count):
        if count > self.max_bindings:
            raise QueryExecutionError("max_bindings exceeded; no complete result published")
        if self._cancel is not None and self._cancel.cancelled:
            raise QueryExecutionError("query cancelled")
        if self._deadline is not None:
            from time import monotonic
            if monotonic() >= self._deadline:
                raise QueryExecutionError("query deadline exceeded")

    def _join(self, atoms, bindings):
        """Contiguous ordinary atoms run as one compiled native/Python join."""
        if not atoms:
            return bindings
        if any(str(atom.predicate) in {EQ, NEQ} for atom in atoms):
            result = bindings
            for atom in atoms:
                if str(atom.predicate) not in {EQ, NEQ}:
                    result = self._join((atom,), result)
                    continue
                following = []
                for binding in result:
                    if str(atom.predicate) == EQ:
                        left, right = atom.args
                        left_open = isinstance(left, Var) and left not in binding
                        right_open = isinstance(right, Var) and right not in binding
                        if left_open or right_open:
                            if left_open and right_open:
                                raise QueryExecutionError("EQ needs at least one bound argument")
                            target, source = (left, right) if left_open else (right, left)
                            following.append({**binding, target: self._value(source, binding)})
                            continue
                    values = tuple(self._value(term, binding) for term in atom.args)
                    if str(atom.predicate) == EQ:
                        matched = values[0] == values[1]
                    else:
                        from .engine import _distinct_literals
                        matched = ((values in self._index.rows.get(NEQ, ()))
                                   or (values[::-1] in self._index.rows.get(NEQ, ()))
                                   or _distinct_literals(*values))
                    if matched:
                        following.append(binding)
                result = following
            return result
        compiled = RelationalPlan(Rule(None, tuple(Atom(a.predicate, a.args) for a in atoms)))
        result = []
        for binding in bindings:
            iterator = (compiled.solutions(self, _MISSING, initial=binding)
                        if self._native is None or self._force_python_indexes else
                        self._index.solutions(compiled, self, _MISSING, initial=binding))
            try:
                for row in iterator:
                    result.append(row)
                    self._check_budget(len(result))
            finally:
                iterator.close()
        return result

    def _value(self, term, binding):
        if isinstance(term, Var):
            if term not in binding:
                raise QueryExecutionError(f"unbound variable ?{term.name}")
            return binding[term]
        return self.normalize(term)

    def _assign(self, binding, target, value):
        if not isinstance(target, Var):
            return binding if self._agree(self.normalize(target), value) else None
        if target in binding:
            return binding if self._agree(binding[target], value) else None
        return {**binding, target: value}

    @staticmethod
    def _agree(left, right):
        if left == right:
            return True
        try:
            return compare_values(left, right) == 0
        except (ValueError, TypeError):
            return False

    def _domain_operation(self, operation):
        try:
            self.domains.get(operation)
            return True
        except (KeyError, ValueError):
            return False

    def _apply(self, node, bindings):
        result = []
        for start in range(0, len(bindings), self.batch_size):
            batch = bindings[start:start + self.batch_size]
            arguments = [tuple(self._value(term, row) for term in node.args) for row in batch]
            self._check_budget(len(result))
            if self._domain_operation(node.operation):
                operation = self.domains.get(node.operation)
                keys = [(operation, tuple(identity_key(value) for value in row)) for row in arguments]
                missing = {}
                resolved = {}
                for key, args in zip(keys, arguments):
                    cached = self._operation_cache.get(key)
                    if cached is not _CACHE_MISS:
                        resolved[key] = cached
                        self.stats["operation_cache_hits"] += 1
                    else:
                        missing[key] = args
                replies = self.domains.evaluate_batch(node.operation, list(missing.values()))
                if len(replies) != len(missing):
                    raise QueryExecutionError("domain batch returned the wrong number of rows")
                for key, reply in zip(missing, replies):
                    if not reply.ok:
                        raise reply.error
                    resolved[key] = reply.value
                for key in missing:
                    self._operation_cache.put(key, resolved[key])
                self.stats["domain_evaluations"] += len(missing)
                values = [resolved[key] for key in keys]
            else:
                replies = self.providers.evaluate(
                    node.operation, arguments, snapshot=self._snapshots[node.operation],
                    deadline=self._deadline, cancel=self._cancel)
                values = []
                for reply in replies:
                    # Domain statuses such as complete NO_ROUTE remain visible
                    # values; only OK scalars can satisfy ordinary numeric ops.
                    status = getattr(reply.status, "value", reply.status)
                    values.append(reply.value if str(status).lower() == "ok" else reply)
            if len(values) != len(batch):
                raise QueryExecutionError("operation batch returned the wrong number of rows")
            self.stats["operation_rows"] += len(batch)
            for binding, value in zip(batch, values):
                self._remember((value,))
                if isinstance(node, Filter):
                    actual = value.toPython() if isinstance(value, Literal) else value
                    if type(actual) is not bool:
                        raise QueryExecutionError("filter operation returned a non-Boolean value")
                    if actual:
                        result.append(binding)
                else:
                    extended = self._assign(binding, node.output, value)
                    if extended is not None:
                        result.append(extended)
        return result

    def _aggregate(self, node, bindings):
        output = []
        if node.kind.lower() != "min":
            raise QueryExecutionError(f"unsupported aggregate {node.kind}")
        for binding in bindings:
            rows = self._join((node.source,), [binding])
            groups = {}
            for row in rows:
                key = tuple(self._value(term, row) for term in node.group_by)
                value = self._value(node.value, row)
                # Validate a singleton too: unsupported values cannot acquire an
                # accidental order merely because their group contains one row.
                compare_values(value, value)
                compared = -1 if key not in groups else compare_values(value, groups[key])
                if compared < 0 or (compared == 0 and minimum_identity_key(value) < minimum_identity_key(groups[key])):
                    groups[key] = value
            for key, value in groups.items():
                extended = dict(binding)
                for term, actual in zip(node.group_by, key):
                    extended = self._assign(extended, term, actual)
                    if extended is None:
                        break
                if extended is not None:
                    extended = self._assign(extended, node.output, value)
                if extended is not None:
                    output.append(extended)
                    self._check_budget(len(output))
        return output

    def _scan(self, node, bindings):
        if self.providers is None:
            raise QueryExecutionError(f"provider unavailable for {node.operation}")
        output = []
        for binding in bindings:
            args = tuple(self._value(term, binding) for term in node.args)
            cursor = self.providers.scan(node.operation, args,
                                         snapshot=self._snapshots[node.operation],
                                         deadline=self._deadline, cancel=self._cancel)
            try:
                for row in cursor:
                    self._remember(row)
                    if len(row) != len(node.outputs):
                        raise QueryExecutionError("provider scan output arity mismatch")
                    extended = binding
                    for target, value in zip(node.outputs, row):
                        extended = self._assign(extended, target, value)
                        if extended is None:
                            break
                    if extended is not None:
                        output.append(extended)
                        self._check_budget(len(output))
            finally:
                if hasattr(cursor, "close"):
                    cursor.close()
        return output

    def _solutions(self, rule, initial):
        bindings, offset = [dict(initial)], 0
        while offset < len(rule.body) and bindings:
            node = rule.body[offset]
            if isinstance(node, RelationAtom):
                end = offset + 1
                while end < len(rule.body) and isinstance(rule.body[end], RelationAtom):
                    end += 1
                bindings = self._join(rule.body[offset:end], bindings)
                offset = end
                continue
            if isinstance(node, (Bind, Filter)):
                bindings = self._apply(node, bindings)
            elif isinstance(node, Aggregate):
                bindings = self._aggregate(node, bindings)
            elif isinstance(node, ProviderScan):
                bindings = self._scan(node, bindings)
            else:
                raise QueryExecutionError(f"unsupported plan node {type(node).__name__}")
            offset += 1
        return bindings

    def _publish(self, scope, derived, diagnostics, metadata):
        old = {} if self.last_complete is None else self.last_complete.relations
        predicates = old.keys() | derived.keys()
        additions = {p: derived.get(p, frozenset()) - old.get(p, frozenset()) for p in predicates}
        removals = {p: old.get(p, frozenset()) - derived.get(p, frozenset()) for p in predicates}
        self._revision += 1
        result = QueryResult(scope, self._revision, _freeze(derived), _freeze(additions),
                             _freeze(removals), tuple(diagnostics), MappingProxyType(dict(metadata)))
        self.last_complete, self.complete = result, True
        return result

    def _native_evaluate(self, prepared, inputs, initial):
        from .query_native import NativeQueryContext, hybrid_reasons
        reasons = (*hybrid_reasons(prepared, self.domains), *self._host_fallback_reasons)
        self.stats["execution_mode"] = "hybrid" if reasons else "native"
        self.stats["hybrid_reasons"] = reasons
        if reasons:
            if self._native_query is not None:
                self._native_query.clear_memo()
            return None
        self._operation_cache.clear()
        if self._native_query is None or not self._native_query.handle:
            self._native_query = NativeQueryContext(self)
        derived = self._native_query.evaluate(prepared, inputs, initial)
        # Keep the existing resident input index coherent for subsequent delta
        # synchronization and supported host-side inspection. Only new output
        # facts cross this boundary; scalar intermediate bindings stay in C++.
        for predicate, rows in derived.items():
            for row in rows:
                self._remember(row, predicate)
                fact = Atom(predicate, row)
                if fact not in self._indexed_facts:
                    self._index_dirty = True
                    self._index.add(fact)
                    self._indexed_facts.add(fact)
                    self._index_dirty = False
        return derived

    def evaluate(self, relations=None, *, scope, parameters=None, diagnostics=(),
                 metadata=None, deadline=None, cancel=None):
        """Return only a complete result, or raise and retain ``last_complete``.

        ``scope`` identifies this input selection, not a claim of real-world
        completeness. Selection diagnostics and completeness metadata travel with
        the answer. Providers pin independent implementation/data revisions.
        """
        if self._closed or self._running:
            raise QueryExecutionError("query runtime is closed or already running")
        if not isinstance(scope, QueryScope):
            raise TypeError("scope must be QueryScope")
        self._running, self.complete = True, False
        self._cancel, self._deadline = cancel, deadline
        self.stats = {"candidate_rows": 0, "body_matches": 0, "operation_rows": 0, "rounds": 0,
                      "operation_cache_hits": 0, "domain_evaluations": 0}
        try:
            self._current_terms, self._current_predicates = set(), set()
            self._check_budget(0)
            diagnostics = tuple(diagnostics)
            metadata = dict(metadata or {})
            source_key, provider_key = self._source_key(), self._provider_key()
            domain_key = self._domain_key()
            inputs = self._inputs(relations or {})
            arities = {}
            for predicate, rows in inputs.items():
                sizes = {len(row) for row in rows}
                if len(sizes) > 1:
                    raise QueryExecutionError(f"inconsistent input arities for {predicate}")
                if sizes:
                    arities[predicate] = next(iter(sizes))
            prepared = plan(self.program, self.registry, relation_arities=arities)
            initial = {Var("scope"): URIRef(scope.name), Var("revision"): Literal(scope.revision)}
            for name, value in (parameters or {}).items():
                variable = name if isinstance(name, Var) else Var(str(name).lstrip("?"))
                if variable in initial and initial[variable] != value:
                    raise QueryExecutionError(f"parameter ?{variable.name} conflicts with scope")
                initial[variable] = self.normalize(value)
            for rule in prepared.rules:
                for variable in rule.given:
                    if variable not in initial:
                        raise QueryExecutionError(f"missing given parameter ?{variable.name}")
            self._remember_plan(prepared, initial)
            self._compact_native()
            self._input_execution_mode(prepared, inputs, initial)
            key = (scope, self._detached_source_key(source_key), provider_key, domain_key,
                   frozenset((p, frozenset(tuple(identity_key(v) for v in row) for row in rows))
                             for p, rows in inputs.items()),
                   frozenset((variable, identity_key(value)) for variable, value in initial.items()))
            cached = self._cache.get(key)
            if cached is not _CACHE_MISS:
                for predicate, rows in cached.items():
                    for row in rows:
                        self._remember(row, predicate)
                self._check_budget(0)
                if (source_key != self._source_key() or provider_key != self._provider_key()
                        or domain_key != self._domain_key()):
                    raise QueryExecutionError("snapshot changed during evaluation; retry with new revisions")
                self.cache_hits += 1
                self.stats["cache_hit"] = True
                if self._native is not None:
                    from .query_native import hybrid_reasons
                    reasons = (*hybrid_reasons(prepared, self.domains), *self._host_fallback_reasons)
                    self.stats.update(execution_mode="hybrid" if reasons else "native", hybrid_reasons=reasons)
                    if reasons and self._native_query is not None:
                        self._native_query.clear_memo()
                    elif not reasons:
                        self._operation_cache.clear()
                else:
                    self.stats["execution_mode"] = "python"
                return self._publish(scope, cached, diagnostics, metadata or {})
            self._snapshots = {}
            for rule in prepared.rules:
                for node in rule.body:
                    if isinstance(node, (Bind, Filter, ProviderScan)) and (
                            isinstance(node, ProviderScan) or
                            not self._domain_operation(node.operation)):
                        self._snapshots[node.operation] = self.providers.snapshot(node.operation)
            self._prepare_index(inputs)
            if self._native is not None:
                native_result = self._native_evaluate(prepared, inputs, initial)
                if native_result is not None:
                    self._check_budget(0)
                    if (source_key != self._source_key() or provider_key != self._provider_key()
                            or domain_key != self._domain_key()):
                        raise QueryExecutionError("snapshot changed during evaluation; retry with new revisions")
                    result = self._publish(scope, native_result, diagnostics, metadata or {})
                    self._cache.put(key, result.relations)
                    return result
            else:
                self.stats["execution_mode"] = "python"
            derived = defaultdict(set)
            total_rows = sum(map(len, inputs.values()))
            for stratum in prepared.strata:
                changed = True
                while changed:
                    self._check_budget(0)
                    self.stats["rounds"] += 1
                    if self.stats["rounds"] > self.max_rounds:
                        raise QueryExecutionError("max_rounds exceeded")
                    pending = set()
                    for rule in stratum:
                        for binding in self._solutions(rule, initial):
                            row = tuple(self._value(term, binding) for term in rule.head.args)
                            self._remember(row, rule.head.predicate)
                            if row not in inputs.get(rule.head.predicate, ()):
                                pending.add(Atom(rule.head.predicate, row))
                            if total_rows + len(pending) > self.max_rows:
                                raise QueryExecutionError("max_rows exceeded by derived relations")
                    changed = bool(pending)
                    for fact in pending:
                        inputs[fact.predicate].add(fact.args)
                        derived[fact.predicate].add(fact.args)
                        self._index_dirty = True
                        self._index.add(fact)
                        self._indexed_facts.add(fact)
                        self._index_dirty = False
                    total_rows += len(pending)
            self._check_budget(0)
            if (source_key != self._source_key() or provider_key != self._provider_key()
                    or domain_key != self._domain_key()):
                raise QueryExecutionError("snapshot changed during evaluation; retry with new revisions")
            derived = {rule.head.predicate: inputs.get(rule.head.predicate, set())
                       for rule in prepared.rules}
            result = self._publish(scope, derived, diagnostics, metadata or {})
            self._cache.put(key, result.relations)
            return result
        except BaseException:
            self.complete = False
            raise
        finally:
            self._running = False

    def close(self):
        if self._running:
            raise QueryExecutionError("cannot close an executing query context")
        if self._index is not None and hasattr(self._index, "close"):
            self._index.close()
        if self._native is not None:
            self._native.close()
        if self._native_query is not None:
            self._native_query.close()
        if self._owns_domains and hasattr(self.domains, "close"):
            self.domains.close()
        self._cache.clear()
        self._operation_cache.clear()
        self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
