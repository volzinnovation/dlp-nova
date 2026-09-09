"""Bounded answer storage and mutation tracking for owned RDF graphs.

These helpers do not decide when a reasoner answer is valid. The caller supplies
an exact key containing the relevant graph, engine, and query state and checks
consistency/completeness before using an answer. Only immutable answer snapshots
are retained; callers always receive their own mutable result sets.
"""

from collections import OrderedDict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from fractions import Fraction
import sys

from rdflib import BNode, Literal, URIRef
from rdflib.plugins.stores.memory import Memory
from rdflib.term import Variable as RDFVariable

from .model import Skolem, Var


CACHE_MISS = object()
_ENTRY_OVERHEAD = 192
_SCALARS = frozenset((str, bytes, bool, int, float, complex, type(None), Decimal,
                     date, datetime, time, timedelta, BNode, URIRef, RDFVariable))
_SET_BASE_BYTES = sys.getsizeof(frozenset())


class RevisionMemory(Memory):
    """RDFLib Memory with a conservative token for every mutation route.

    ``revision`` is an invalidation token, not a count of changed triples.
    Even duplicate additions, empty removals, and failed writes invalidate it.
    Incrementing before a write covers callbacks and partial failures; the
    final increment also invalidates answers computed reentrantly by RDFLib's
    pre-insertion events. Graph.addN/parse/SPARQL and direct store operations
    all eventually reach these methods. Namespace bindings do not change RDF
    triples and consequently do not advance this token.
    """

    def __init__(self, *args, **kwargs):
        self._revision = 0
        super().__init__(*args, **kwargs)

    @property
    def revision(self):
        return self._revision

    def add(self, triple, context, quoted=False):
        self._revision += 1
        try:
            return super().add(triple, context, quoted=quoted)
        finally:
            self._revision += 1

    def addN(self, quads):
        self._revision += 1
        try:
            return super().addN(quads)
        finally:
            self._revision += 1

    def remove(self, triple_pattern, context=None):
        # Memory.remove mutates directly rather than calling Store.remove;
        # listening only for TripleRemovedEvent would miss these changes.
        self._revision += 1
        try:
            return super().remove(triple_pattern, context=context)
        finally:
            self._revision += 1

    def add_graph(self, graph):
        self._revision += 1
        try:
            return super().add_graph(graph)
        finally:
            self._revision += 1

    def remove_graph(self, graph):
        self._revision += 1
        try:
            return super().remove_graph(graph)
        finally:
            self._revision += 1

    def update(self, update, initNs, initBindings, queryGraph, **kwargs):
        # Memory delegates to Store.update, which requests RDFLib's normal
        # SPARQL fallback. Invalidate before that dispatch as well as in each
        # subsequent add/remove performed by the fallback evaluator.
        self._revision += 1
        try:
            return super().update(update, initNs, initBindings, queryGraph, **kwargs)
        finally:
            self._revision += 1


def _estimate_bytes(key, value, limit):
    """Conservatively estimate one retained entry without expanding copies.

    Large strings, pair sets, nested keys, and RDF literal value objects count
    toward the budget. Unknown custom objects are deliberately uncacheable:
    their shallow Python size gives no useful bound on retained memory. Sharing
    within one entry is counted once, while sharing across entries is counted
    again, so this estimate errs toward retaining fewer entries.
    """
    total = _ENTRY_OVERHEAD
    seen = set()
    # Iterators keep auxiliary space proportional to nesting depth, including
    # for an unusually large tuple key. A visited set also handles shared nodes.
    stack = [iter((key, value))]
    while stack:
        try:
            item = next(stack[-1])
        except StopIteration:
            stack.pop()
            continue
        identity = id(item)
        if identity in seen:
            continue
        seen.add(identity)
        size = sys.getsizeof(item)
        if item is value and type(item) is set:
            # The retained frozenset may choose a different table capacity.
            # Budget a conservative table allowance before making its copy.
            size = max(size, _SET_BASE_BYTES + 64 * len(item))
        total += size
        if total > limit:
            return total
        if type(item) is Literal:
            stack.append(iter((item.datatype, item.language, item.value)))
        elif type(item) in {tuple, set, frozenset}:
            stack.append(iter(item))
        elif type(item) is Skolem:
            total += sys.getsizeof(item.__dict__)
            stack.append(iter(item.__dict__.values()))
        elif type(item) is Var:
            total += sys.getsizeof(item.__dict__)
            stack.append(iter(item.__dict__.values()))
        elif type(item) is Fraction:
            stack.append(iter((item.numerator, item.denominator)))
        elif type(item) not in _SCALARS:
            # Even a subclass of str/tuple can retain an arbitrarily large
            # attribute payload that its shallow size does not account for.
            return None
    return total


class AnswerCache:
    """An LRU of boolean/frozenset answers bounded by entries, values and bytes.

    ``get`` returns ``CACHE_MISS`` on a miss, preserving cached ``False`` and
    empty sets distinctly. ``put`` accepts bool, set, or frozenset and returns
    whether it retained an immutable snapshot. Oversized sets bypass before
    any snapshot copy. ``clear`` retains cumulative instrumentation counters.
    """

    def __init__(self, *, max_entries=256, max_values=50_000, max_bytes=16 * 1024 * 1024):
        for name, limit in (("max_entries", max_entries), ("max_values", max_values),
                            ("max_bytes", max_bytes)):
            if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        self.max_entries = max_entries
        self.max_values = max_values
        self.max_bytes = max_bytes
        self._entries = OrderedDict()
        self._values = 0
        self._bytes = 0
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._bypasses = 0

    def get(self, key):
        entry = self._entries.get(key, CACHE_MISS)
        if entry is CACHE_MISS:
            self._misses += 1
            return CACHE_MISS
        self._hits += 1
        self._entries.move_to_end(key)
        value = entry[0]
        return set(value) if isinstance(value, frozenset) else value

    def put(self, key, value):
        if type(value) is not bool and not isinstance(value, (set, frozenset)):
            raise TypeError("Cached answers must be bool, set, or frozenset")
        previous = self._entries.pop(key, None)
        if previous is not None:
            self._values -= previous[1]
            self._bytes -= previous[2]
        values = 1 if type(value) is bool else len(value)
        if not self.max_entries or values > self.max_values or not self.max_bytes:
            self._bypasses += 1
            return False
        estimated = _estimate_bytes(key, value, self.max_bytes)
        if estimated is None or estimated > self.max_bytes:
            self._bypasses += 1
            return False
        # Freeze only after cheap value/entry bounds and the retained-memory
        # estimate have accepted this answer; never retain the caller's set.
        snapshot = value if type(value) is bool else frozenset(value)
        while self._entries and (len(self._entries) >= self.max_entries
                                 or self._values + values > self.max_values
                                 or self._bytes + estimated > self.max_bytes):
            _, removed = self._entries.popitem(last=False)
            self._values -= removed[1]
            self._bytes -= removed[2]
            self._evictions += 1
        self._entries[key] = snapshot, values, estimated
        self._values += values
        self._bytes += estimated
        return True

    def clear(self):
        self._entries.clear()
        self._values = 0
        self._bytes = 0

    def info(self):
        return {"hits": self._hits, "misses": self._misses, "evictions": self._evictions,
                "bypasses": self._bypasses, "entries": len(self._entries),
                "values": self._values, "estimated_bytes": self._bytes,
                "max_entries": self.max_entries, "max_values": self.max_values,
                "max_bytes": self.max_bytes}
