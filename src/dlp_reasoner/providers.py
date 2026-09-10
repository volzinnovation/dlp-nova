"""Versioned external computations and finite scans, outside native join loops.

Adapters are synchronous: at most one call is outstanding per caller. Deadline
and cancellation checks bracket every adapter call; cooperative adapters also
check the supplied Control during work. No background work is shared implicitly.
"""

from collections import OrderedDict
from dataclasses import dataclass, fields
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import heapq
import json
import math
import threading
import time
from typing import Any
from urllib import error as urlerror, request as urlrequest
from urllib.parse import urlsplit

from rdflib import BNode, Literal, URIRef

from . import domains


_CARRIERS = {cls.__name__: cls for cls in (
    domains.IntegerValue, domains.DecimalValue, domains.FloatValue, domains.DateValue,
    domains.InstantValue, domains.TimeValue, domains.DurationValue, domains.Point, domains.Interval,
    domains.Quantity,
)}


class Status(str, Enum):
    OK = "ok"
    NO_ROUTE = "no_route"
    NO_MATCH = "no_match"
    OUT_OF_REGION = "out_of_region"
    DOMAIN_ERROR = "domain_error"
    INCOMPLETE = "incomplete"
    UNAVAILABLE = "unavailable"
    CANCELLED = "cancelled"
    DEADLINE = "deadline"
    PROTOCOL_ERROR = "protocol_error"
    SNAPSHOT_CHANGED = "snapshot_changed"
    RESOURCE_LIMIT = "resource_limit"


class ProviderError(RuntimeError):
    def __init__(self, status, message):
        self.status = Status(status)
        super().__init__(message)


def _encode(value, _depth=0):
    """An exact typed immutable wire/cache value, never a process-local term ID."""
    if _depth > 64:
        raise ValueError("Provider value nesting limit exceeded")
    if isinstance(value, Literal):
        return ["literal", str(value), str(value.datatype) if value.datatype else None,
                value.language]
    if isinstance(value, URIRef):
        return ["iri", str(value)]
    if isinstance(value, BNode):
        return ["bnode", str(value)]
    if value is None:
        return ["null"]
    if type(value) is bool:
        return ["bool", value]
    if type(value) is int:
        return ["int", str(value)]
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("Provider floats must be finite")
        return ["float", value.hex()]
    if type(value) is str:
        return ["str", value]
    if type(value) is bytes:
        return ["bytes", value.hex()]
    if type(value) is Decimal:
        if not value.is_finite():
            raise ValueError("Provider decimals must be finite")
        sign, digits, exponent = value.as_tuple()
        digits = list(digits)
        while digits and digits[-1] == 0:
            digits.pop()
            exponent += 1
        return ["decimal", sign if digits else 0, digits or [0], exponent if digits else 0]
    if type(value) is datetime:
        if value.utcoffset() is None:
            raise ValueError("Provider instants need an explicit timezone offset")
        return ["datetime", value.isoformat()]
    if type(value) is date:
        return ["date", value.isoformat()]
    if type(value) is tuple:
        return ["tuple", [_encode(item, _depth + 1) for item in value]]
    if type(value) is ProviderResult:
        return ["provider-result", value.status.value, _encode(value.value, _depth + 1)]
    if type(value) in _CARRIERS.values():
        return ["domain", type(value).__name__, [_encode(getattr(value, field.name), _depth + 1)
                                               for field in fields(value)]]
    raise TypeError(f"Unsupported immutable provider value: {type(value).__name__}")


def _decode_unchecked(value, _depth):
    kind, *args = value
    if kind == "null":
        return None
    if kind == "literal":
        return Literal(args[0], datatype=URIRef(args[1]) if args[1] else None,
                       lang=args[2], normalize=False)
    if kind == "iri":
        return URIRef(args[0])
    if kind == "bnode":
        return BNode(args[0])
    if kind in {"bool", "str"}:
        return args[0]
    if kind == "int":
        return int(args[0])
    if kind == "float":
        return float.fromhex(args[0])
    if kind == "bytes":
        return bytes.fromhex(args[0])
    if kind == "decimal":
        return Decimal((args[0], tuple(args[1]), args[2]))
    if kind == "datetime":
        return datetime.fromisoformat(args[0])
    if kind == "date":
        return date.fromisoformat(args[0])
    if kind == "tuple":
        return tuple(_decode(item, _depth + 1) for item in args[0])
    if kind == "domain":
        return _CARRIERS[args[0]](*(_decode(item, _depth + 1) for item in args[1]))
    if kind == "provider-result":
        return ProviderResult(Status(args[0]), _decode(args[1], _depth + 1))
    raise ValueError(f"Unknown value tag: {kind!r}")


def _decode(value, _depth=0):
    if _depth > 64:
        raise ValueError("Provider value nesting limit exceeded")
    result = _decode_unchecked(value, _depth)
    if _encode(result) != value:
        raise ValueError("Noncanonical or malformed tagged value")
    return result


def _packed(value):
    return json.dumps(_encode(value), ensure_ascii=True, separators=(",", ":")).encode()


def _matches(value, expected):
    if expected == "any":
        return True
    if expected in {"string", "policy"}:
        return type(value) is str or (isinstance(value, Literal) and
                (value.datatype is None or str(value.datatype).endswith("#string")))
    if expected == "iri":
        return isinstance(value, URIRef)
    if expected == "tuple":
        return type(value) is tuple
    if expected == "date" and type(value) is date:
        return True
    if expected == "instant" and type(value) is datetime:
        return True
    try:
        decoded = domains.decode(value)
    except domains.DomainError:
        return False
    types = {
        "integer": (domains.IntegerValue,), "decimal": (domains.DecimalValue,),
        "float": (domains.FloatValue,), "float64": (domains.FloatValue,), "boolean": (bool,),
        "numeric": (domains.IntegerValue, domains.DecimalValue),
        "number": (domains.IntegerValue, domains.DecimalValue, domains.FloatValue),
        "date": (domains.DateValue,), "instant": (domains.InstantValue,),
        "time": (domains.TimeValue,), "duration": (domains.DurationValue,),
        "point": (domains.Point,), "interval": (domains.Interval,), "quantity": (domains.Quantity,),
        "temporal": (domains.DateValue, domains.InstantValue, domains.TimeValue, domains.DurationValue),
        "endpoint": (domains.DateValue, domains.InstantValue),
    }
    return type(decoded) in types.get(expected, ())


@dataclass(frozen=True)
class Snapshot:
    provider: str
    implementation: str
    dataset: str
    dependencies: tuple = ()

    def __post_init__(self):
        if not all(type(v) is str and v for v in (self.provider, self.implementation, self.dataset)):
            raise ValueError("Snapshot provider, implementation and dataset must be nonempty strings")
        if type(self.dependencies) is not tuple:
            raise TypeError("Snapshot dependencies must be an immutable tuple")
        if (any(type(pair) is not tuple or len(pair) != 2 or not all(type(v) is str for v in pair)
                for pair in self.dependencies)
                or len({pair[0] for pair in self.dependencies}) != len(self.dependencies)):
            raise ValueError("Snapshot dependencies require unique string key/value pairs")
        _packed(self.dependencies)


@dataclass(frozen=True)
class ProviderResult:
    status: Status
    value: Any = None

    def __post_init__(self):
        object.__setattr__(self, "status", Status(self.status))
        _packed(self.value)
        if self.status != Status.OK and self.value is not None:
            raise ValueError("Only OK provider results carry a value")


@dataclass(frozen=True)
class Request:
    row_id: int
    arguments: tuple


@dataclass(frozen=True)
class Reply:
    row_id: int
    result: ProviderResult


@dataclass(frozen=True)
class BatchReply:
    snapshot: Snapshot
    replies: tuple
    complete: bool = True


@dataclass(frozen=True)
class ScanPage:
    snapshot: Snapshot
    rows: tuple
    complete: bool
    continuation: str | None = None


class CancellationToken:
    def __init__(self):
        self._event = threading.Event()

    def cancel(self):
        self._event.set()

    @property
    def cancelled(self):
        return self._event.is_set()


@dataclass(frozen=True)
class Control:
    deadline: float | None = None  # absolute time.monotonic() seconds
    cancel: CancellationToken | None = None

    def __post_init__(self):
        if self.deadline is not None and (type(self.deadline) not in (int, float)
                                         or not math.isfinite(self.deadline)):
            raise ValueError("Deadline must be finite monotonic seconds")
        if self.cancel is not None and not isinstance(self.cancel, CancellationToken):
            raise TypeError("Expected CancellationToken")

    def check(self):
        if self.cancel is not None and self.cancel.cancelled:
            raise ProviderError(Status.CANCELLED, "Provider operation cancelled")
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise ProviderError(Status.DEADLINE, "Provider deadline exceeded")


@dataclass(frozen=True)
class ProviderOperation:
    uri: str
    version: str
    input_types: tuple
    result_type: str
    required_positions: tuple
    cardinality: str = "one"
    output_types: tuple = ()
    coverage: str = "exact"
    determinism: str = "snapshot"
    dependencies: tuple = ("provider",)
    batches: bool = True
    output_unit: str | None = None
    metric: str | None = None
    crs: str | None = None

    @property
    def arity(self):
        return len(self.input_types)


class ProviderRegistry:
    """Pinned batches/scans with bounded exact memoization and explicit errors.

    A scalar batch is staged and validated in full before results or cache entries
    are published. Scans stream provisionally: consumers must exhaust or observe
    cursor.complete before treating the enumeration as a complete answer.
    """

    def __init__(self, *, max_entries=256, max_bytes=16 * 1024 * 1024,
                 max_rows=50000, max_batch=256, max_page=256, max_pages=10000,
                 max_work_bytes=16 * 1024 * 1024):
        for name, value in locals().copy().items():
            if name != "self" and (type(value) is not int or value < 0):
                raise ValueError(f"{name} must be a nonnegative integer")
        if min(max_rows, max_batch, max_page, max_pages, max_work_bytes) < 1:
            raise ValueError("Row, batch and page limits must be positive")
        self.max_entries, self.max_bytes = max_entries, max_bytes
        self.max_rows, self.max_batch, self.max_page = max_rows, max_batch, max_page
        self.max_pages = max_pages
        self.max_work_bytes = max_work_bytes
        self._operations = {}
        self._cache = OrderedDict()
        self._bytes = 0
        self._generation = 0
        self._counters = dict(hits=0, misses=0, evictions=0, bypasses=0)

    def register(self, operation, adapter, *, version="1", input_types=(), result_type="any",
                 required_positions=None, cardinality="one", output_types=(), coverage="exact",
                 output_unit=None, metric=None, crs=None):
        if cardinality not in {"one", "many"} or coverage not in {"exact", "candidate_superset"}:
            raise ValueError("Invalid provider cardinality or coverage")
        if any(value is not None and (type(value) is not str or not value)
               for value in (output_unit, metric, crs)):
            raise ValueError("Provider unit, metric and CRS must be nonempty strings when declared")
        inputs = tuple(input_types)
        positions = tuple(range(len(inputs))) if required_positions is None else tuple(required_positions)
        if set(positions) != set(range(len(inputs))):
            raise ValueError("This first provider boundary requires every input position bound")
        descriptor = ProviderOperation(str(operation), str(version), inputs, result_type,
                                       positions, cardinality, tuple(output_types), coverage,
                                       output_unit=output_unit, metric=metric, crs=crs)
        self._operations[str(operation)] = descriptor, adapter
        self._generation += 1
        self.clear_cache()
        return descriptor

    def get(self, operation):
        entry = self._operations.get(str(operation))
        return entry[0] if entry else None

    def _entry(self, operation):
        try:
            return self._operations[str(operation)]
        except KeyError:
            raise ProviderError(Status.UNAVAILABLE, f"Unregistered provider operation: {operation}") from None

    def snapshot(self, operation):
        _, adapter = self._entry(operation)
        snapshot = self._invoke(adapter.snapshot)
        if not isinstance(snapshot, Snapshot):
            raise ProviderError(Status.PROTOCOL_ERROR, "Adapter did not return a Snapshot")
        return snapshot

    def revision_key(self):
        return self._generation, tuple((uri, self.snapshot(uri)) for uri in sorted(self._operations))

    def invalidate(self, provider=None):
        """Whole-revision invalidation: maintained consumers must re-enumerate.

        This intentionally does not restrict invalidation to previous positive
        witnesses; a provider change may introduce previously absent rows.
        """
        if provider is not None and not any(self.snapshot(uri).provider == provider
                                            for uri in self._operations):
            raise KeyError(provider)
        self._generation += 1
        self.clear_cache()

    def clear_cache(self):
        self._cache.clear()
        self._bytes = 0

    def cache_info(self):
        return dict(self._counters, entries=len(self._cache), bytes=self._bytes,
                    generation=self._generation)

    def _cache_get(self, key):
        if key not in self._cache:
            self._counters["misses"] += 1
            return None
        self._counters["hits"] += 1
        self._cache.move_to_end(key)
        return self._cache[key][0]

    def _cache_put(self, key, value):
        # Wire length bounds retained payload and key size; fixed/per-row margins
        # account conservatively for container/scalar overhead in this cache.
        if (not self.max_entries or not self.max_bytes
                or isinstance(value, ProviderResult) and value.status not in {Status.OK, Status.NO_ROUTE}):
            self._counters["bypasses"] += 1
            return
        if isinstance(value, ProviderResult):
            payload = _packed((value.status.value, value.value))
            items = 1
        else:
            payload, items = _packed(value), len(value)
        size = len(key) * 2 + len(payload) * 4 + 256 + 128 * items
        if not self.max_entries or size > self.max_bytes:
            self._counters["bypasses"] += 1
            return
        if key in self._cache:
            self._bytes -= self._cache.pop(key)[1]
        while self._cache and (len(self._cache) >= self.max_entries or self._bytes + size > self.max_bytes):
            self._bytes -= self._cache.popitem(last=False)[1][1]
            self._counters["evictions"] += 1
        self._cache[key] = value, size
        self._bytes += size

    @staticmethod
    def _invoke(function, *args):
        try:
            return function(*args)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(Status.UNAVAILABLE, f"Provider adapter failed: {exc}") from exc

    def _validate(self, operation, arguments, cardinality):
        descriptor, adapter = self._entry(operation)
        if descriptor.cardinality != cardinality:
            raise ProviderError(Status.DOMAIN_ERROR, f"{operation} is not a {cardinality} operation")
        if type(arguments) is not tuple or len(arguments) != descriptor.arity:
            raise ProviderError(Status.DOMAIN_ERROR, f"{operation} requires {descriptor.arity} bound inputs")
        try:
            _packed(arguments)
        except (ValueError, TypeError) as exc:
            raise ProviderError(Status.DOMAIN_ERROR, str(exc)) from exc
        if any(not _matches(value, expected) for value, expected in
               zip(arguments, descriptor.input_types)):
            raise ProviderError(Status.DOMAIN_ERROR, f"{operation} input type mismatch")
        return descriptor, adapter

    def _pin(self, operation, snapshot, control):
        control.check()
        current = self.snapshot(operation)
        control.check()
        if snapshot is not None and current != snapshot:
            raise ProviderError(Status.SNAPSHOT_CHANGED, "Provider revision changed during evaluation")
        descriptor = self._entry(operation)[0]
        advertised = dict(current.dependencies)
        for key, expected in (("unit", descriptor.output_unit), ("metric", descriptor.metric),
                              ("crs", descriptor.crs)):
            if expected is not None and advertised.get(key) != expected:
                raise ProviderError(Status.PROTOCOL_ERROR, f"Provider {key} contract mismatch")
        return current

    def _key(self, descriptor, snapshot, arguments, mode):
        normalized = []
        for argument, expected in zip(arguments, descriptor.input_types):
            if expected not in {"any", "string", "policy", "iri", "tuple"}:
                try:
                    argument = domains.decode(argument)
                except domains.DomainError:
                    pass  # Explicit Python calendar/instant forms retain their typed encoding.
            normalized.append(argument)
        return _packed((self._generation, descriptor.uri, descriptor.version, mode,
                        snapshot.provider, snapshot.implementation, snapshot.dataset,
                        snapshot.dependencies, tuple(normalized)))

    def evaluate(self, operation, rows, *, snapshot=None, deadline=None, cancel=None):
        control = Control(deadline, cancel)
        generation = self._generation
        pinned = self._pin(operation, snapshot, control)
        descriptor, adapter = self._entry(operation)
        if descriptor.cardinality != "one":
            raise ProviderError(Status.DOMAIN_ERROR, f"{operation} is not a one operation")
        requests, keys, original = [], {}, []
        work_bytes = 0
        for row in rows:
            control.check()
            if len(original) >= self.max_rows:
                raise ProviderError(Status.RESOURCE_LIMIT, "Provider input row limit exceeded")
            descriptor, adapter = self._validate(operation, row, "one")
            key = self._key(descriptor, pinned, row, "scalar")
            original.append(key)
            work_bytes += len(key) + 64
            if work_bytes > self.max_work_bytes:
                raise ProviderError(Status.RESOURCE_LIMIT, "Provider input byte limit exceeded")
            if key in keys:
                continue
            cached = self._cache_get(key)
            keys[key] = cached
            if cached is None:
                requests.append((key, Request(len(requests), row)))
        staged = []
        advertised_batch = getattr(adapter, "max_batch", self.max_batch)
        if type(advertised_batch) is not int or advertised_batch < 1:
            raise ProviderError(Status.PROTOCOL_ERROR, "Invalid adapter batch limit")
        batch_size = min(self.max_batch, advertised_batch)
        for offset in range(0, len(requests), batch_size):
            if generation != self._generation:
                raise ProviderError(Status.SNAPSHOT_CHANGED, "Provider registry invalidated")
            self._pin(operation, pinned, control)
            chunk = requests[offset:offset + batch_size]
            response = self._invoke(adapter.evaluate_batch, str(operation),
                                    tuple(request for _, request in chunk), pinned, control)
            self._pin(operation, pinned, control)
            if not isinstance(response, BatchReply) or response.snapshot != pinned:
                raise ProviderError(Status.PROTOCOL_ERROR, "Invalid batch snapshot/envelope")
            if response.complete is not True:
                raise ProviderError(Status.INCOMPLETE, "Provider batch is incomplete")
            expected = {request.row_id: key for key, request in chunk}
            seen = set()
            if type(response.replies) is not tuple or len(response.replies) != len(expected):
                raise ProviderError(Status.PROTOCOL_ERROR, "Missing or extra provider replies")
            for reply in response.replies:
                if (not isinstance(reply, Reply) or type(reply.row_id) is not int
                        or reply.row_id not in expected or reply.row_id in seen
                        or not isinstance(reply.result, ProviderResult)):
                    raise ProviderError(Status.PROTOCOL_ERROR, "Invalid or duplicate provider row ID")
                seen.add(reply.row_id)
                result = reply.result
                if result.status not in {Status.OK, Status.NO_ROUTE, Status.OUT_OF_REGION}:
                    raise ProviderError(result.status, f"Provider failed for row {reply.row_id}")
                if result.status == Status.OK and not _matches(result.value, descriptor.result_type):
                    raise ProviderError(Status.PROTOCOL_ERROR, "Provider output type mismatch")
                if (result.status == Status.OK and isinstance(result.value, domains.Quantity)
                        and descriptor.output_unit is not None and result.value.unit != descriptor.output_unit):
                    raise ProviderError(Status.PROTOCOL_ERROR, "Provider quantity unit mismatch")
                work_bytes += len(_packed(result.value)) * 4 + 128
                if work_bytes > self.max_work_bytes:
                    raise ProviderError(Status.RESOURCE_LIMIT, "Provider output byte limit exceeded")
                key = expected[reply.row_id]
                keys[key] = result
                staged.append((key, result))
        self._pin(operation, pinned, control)
        if generation != self._generation:
            raise ProviderError(Status.SNAPSHOT_CHANGED, "Provider registry invalidated")
        for key, result in staged:
            self._cache_put(key, result)
        return tuple(keys[key] for key in original)

    def scan(self, operation, arguments, *, snapshot=None, deadline=None, cancel=None):
        descriptor, adapter = self._validate(operation, arguments, "many")
        control = Control(deadline, cancel)
        pinned = self._pin(operation, snapshot, control)
        return ProviderCursor(self, descriptor, adapter, arguments, pinned, control)


class ProviderCursor:
    def __init__(self, registry, descriptor, adapter, arguments, snapshot, control):
        self.registry, self.descriptor, self.adapter = registry, descriptor, adapter
        self.snapshot, self.control = snapshot, control
        self.complete, self.closed = False, False
        self._key = registry._key(descriptor, snapshot, arguments, "scan")
        self._generation = registry._generation
        self._cached = registry._cache_get(self._key)
        self._source = None
        self._iterator = self._iterate(arguments)

    def __iter__(self):
        return self

    def __next__(self):
        if self.closed:
            raise StopIteration
        try:
            return next(self._iterator)
        except BaseException:
            try:
                self.close()
            except Exception:
                pass
            raise

    def _check(self):
        if self.registry._generation != self._generation:
            raise ProviderError(Status.SNAPSHOT_CHANGED, "Provider registry invalidated")
        self.registry._pin(self.descriptor.uri, self.snapshot, self.control)

    def _iterate(self, arguments):
        self._check()
        if self._cached is not None:
            for row in self._cached:
                self._check()
                yield row
            self._check()
            self.complete = True
            return
        self._source = self.registry._invoke(self.adapter.open_scan, self.descriptor.uri,
                                            arguments, self.snapshot, self.control)
        saved, count, retained_bytes, previous_token = [], 0, 0, None
        cacheable = bool(self.registry.max_entries)
        for _ in range(self.registry.max_pages):
            self._check()
            advertised_page = getattr(self.adapter, "max_page", self.registry.max_page)
            if type(advertised_page) is not int or advertised_page < 1:
                raise ProviderError(Status.PROTOCOL_ERROR, "Invalid adapter page limit")
            page_size = min(self.registry.max_page, advertised_page)
            page = self.registry._invoke(self._source.next_page, page_size, self.control)
            self._check()
            if (not isinstance(page, ScanPage) or page.snapshot != self.snapshot
                    or type(page.rows) is not tuple or len(page.rows) > page_size
                    or type(page.complete) is not bool):
                raise ProviderError(Status.PROTOCOL_ERROR, "Invalid scan page")
            if not page.complete and (not isinstance(page.continuation, str)
                                      or not page.continuation or page.continuation == previous_token):
                raise ProviderError(Status.INCOMPLETE, "Scan has no advancing continuation")
            if page.complete and page.continuation is not None:
                raise ProviderError(Status.PROTOCOL_ERROR, "Completed page has continuation")
            previous_token = page.continuation
            try:
                page_bytes = sum(len(_packed(row)) * 4 + 128 for row in page.rows)
            except (ValueError, TypeError) as exc:
                raise ProviderError(Status.PROTOCOL_ERROR, str(exc)) from exc
            if page_bytes > self.registry.max_work_bytes:
                raise ProviderError(Status.RESOURCE_LIMIT, "Scan page byte limit exceeded")
            for row in page.rows:
                if type(row) is not tuple:
                    raise ProviderError(Status.PROTOCOL_ERROR, "Scan rows must be immutable tuples")
                try:
                    payload = _packed(row)
                except (ValueError, TypeError) as exc:
                    raise ProviderError(Status.PROTOCOL_ERROR, str(exc)) from exc
                if self.descriptor.output_types and len(row) != len(self.descriptor.output_types):
                    raise ProviderError(Status.PROTOCOL_ERROR, "Wrong scan output arity")
                if any(not _matches(value, expected) for value, expected in
                       zip(row, self.descriptor.output_types)):
                    raise ProviderError(Status.PROTOCOL_ERROR, "Wrong scan output type")
                if len(payload) * 4 + 128 > self.registry.max_work_bytes:
                    raise ProviderError(Status.RESOURCE_LIMIT, "Scan row byte limit exceeded")
                count += 1
                if count > self.registry.max_rows:
                    raise ProviderError(Status.RESOURCE_LIMIT, "Scan row limit exceeded")
                retained_bytes += len(payload) * 4 + 128
                if cacheable and retained_bytes + len(self._key) * 2 + 256 <= self.registry.max_bytes:
                    saved.append(row)
                elif cacheable:
                    saved.clear()
                    cacheable = False
                self._check()
                yield row
            if page.complete:
                self._check()
                self.complete = True
                if cacheable:
                    self.registry._cache_put(self._key, tuple(saved))
                return
        raise ProviderError(Status.INCOMPLETE, "Scan page limit reached without exhaustion")

    def close(self):
        if not self.closed:
            self.closed = True
            self._iterator.close()
            if self._source is not None:
                self._source.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


class FakeProvider:
    """Deterministic adapter with explicit revisions; useful for tests and examples."""

    def __init__(self, scalars=None, scans=None, *, name="fake", revision="1", reverse_replies=True):
        self.scalars, self.scans = dict(scalars or {}), dict(scans or {})
        self.name, self.revision = name, str(revision)
        self.reverse_replies = reverse_replies
        self.batch_calls = self.scan_calls = self.closed_cursors = 0

    def snapshot(self):
        return Snapshot(self.name, "fake-v1", self.revision)

    def evaluate_batch(self, operation, requests, snapshot, control):
        self.batch_calls += 1
        replies = []
        for request in requests:
            control.check()
            value = self.scalars[operation](*request.arguments)
            result = value if isinstance(value, ProviderResult) else ProviderResult(Status.OK, value)
            replies.append(Reply(request.row_id, result))
        if self.reverse_replies:
            replies.reverse()
        return BatchReply(snapshot, tuple(replies))

    def open_scan(self, operation, arguments, snapshot, control):
        self.scan_calls += 1
        control.check()
        provider = self
        iterator = iter(self.scans[operation](*arguments))

        class Cursor:
            closed = False
            page = 0

            def next_page(self, limit, control):
                if self.closed:
                    raise ProviderError(Status.CANCELLED, "Cursor closed")
                rows = []
                for _ in range(limit):
                    control.check()
                    try:
                        rows.append(next(iterator))
                    except StopIteration:
                        return ScanPage(snapshot, tuple(rows), True)
                self.page += 1
                return ScanPage(snapshot, tuple(rows), False, str(self.page))

            def close(self):
                if not self.closed:
                    self.closed = True
                    provider.closed_cursors += 1
                    close = getattr(iterator, "close", None)
                    if close:
                        close()

        return Cursor()


def _snapshot_wire(snapshot):
    return _encode((snapshot.provider, snapshot.implementation, snapshot.dataset, snapshot.dependencies))


def _snapshot_read(value):
    return Snapshot(*_decode(value))


class HTTPJSONAdapter:
    """Host-configured HTTP/JSON transport; endpoints never appear in logic rules.

    Requests/replies use this module's tagged wire protocol, not a vendor's API.
    Calls have socket timeouts and byte limits. Cancellation is checked before
    and after blocking I/O; it does not claim to preempt a blocked OS socket.
    """

    def __init__(self, endpoint, *, timeout=5.0, max_bytes=16 * 1024 * 1024):
        parts = urlsplit(endpoint)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.fragment:
            raise ValueError("Expected a configured HTTP(S) endpoint")
        if not math.isfinite(timeout) or timeout <= 0 or type(max_bytes) is not int or max_bytes < 1:
            raise ValueError("Positive HTTP timeout and byte bound required")
        self.endpoint, self.timeout, self.max_bytes = endpoint, timeout, max_bytes

    def _request(self, data, control=None):
        control = control or Control()
        control.check()
        timeout = self.timeout
        if control.deadline is not None:
            timeout = min(timeout, max(0.000001, control.deadline - time.monotonic()))
        body = json.dumps(dict(data, timeout_seconds=timeout), separators=(",", ":"), ensure_ascii=True).encode()
        if len(body) > self.max_bytes:
            raise ProviderError(Status.RESOURCE_LIMIT, "HTTP provider request exceeds byte limit")
        request = urlrequest.Request(self.endpoint, body, {"Content-Type": "application/json"}, method="POST")
        try:
            with urlrequest.urlopen(request, timeout=timeout) as response:
                payload = response.read(self.max_bytes + 1)
            control.check()
            if len(payload) > self.max_bytes:
                raise ProviderError(Status.RESOURCE_LIMIT, "HTTP provider reply exceeds byte limit")
            reply = json.loads(payload)
            if not isinstance(reply, dict):
                raise ValueError("Reply envelope must be an object")
            if "error" in reply:
                raise ProviderError(reply["error"], str(reply.get("message", "Provider failed")))
            return reply
        except ProviderError:
            raise
        except (TimeoutError, urlerror.URLError, OSError) as exc:
            control.check()
            raise ProviderError(Status.UNAVAILABLE, "HTTP provider unavailable") from exc
        except (ValueError, TypeError, KeyError, RecursionError) as exc:
            raise ProviderError(Status.PROTOCOL_ERROR, f"Invalid HTTP reply: {exc}") from exc

    def snapshot(self):
        try:
            return _snapshot_read(self._request({"action": "snapshot"})["snapshot"])
        except (ValueError, TypeError, KeyError) as exc:
            raise ProviderError(Status.PROTOCOL_ERROR, "Invalid HTTP snapshot") from exc

    def evaluate_batch(self, operation, requests, snapshot, control):
        response = self._request({"action": "batch", "operation": operation,
                                  "snapshot": _snapshot_wire(snapshot),
                                  "rows": [[row.row_id, _encode(row.arguments)] for row in requests]}, control)
        try:
            return BatchReply(_snapshot_read(response["snapshot"]),
                              tuple(Reply(identity, ProviderResult(status, _decode(value)))
                                    for identity, status, value in response["rows"]), response["complete"])
        except (ValueError, TypeError, KeyError) as exc:
            raise ProviderError(Status.PROTOCOL_ERROR, "Invalid HTTP batch reply") from exc

    def open_scan(self, operation, arguments, snapshot, control):
        response = self._request({"action": "open", "operation": operation,
                                  "arguments": _encode(arguments), "snapshot": _snapshot_wire(snapshot)}, control)
        try:
            if _snapshot_read(response["snapshot"]) != snapshot or type(response["cursor"]) is not str:
                raise ValueError("Invalid cursor snapshot/ID")
            identity = response["cursor"]
        except (ValueError, TypeError, KeyError) as exc:
            raise ProviderError(Status.PROTOCOL_ERROR, "Invalid HTTP scan handle") from exc
        adapter = self

        class Cursor:
            closed = False

            def next_page(self, limit, control):
                response = adapter._request({"action": "next", "cursor": identity, "limit": limit}, control)
                try:
                    return ScanPage(_snapshot_read(response["snapshot"]),
                                    tuple(_decode(row) for row in response["rows"]),
                                    response["complete"], response.get("continuation"))
                except (ValueError, TypeError, KeyError) as exc:
                    raise ProviderError(Status.PROTOCOL_ERROR, "Invalid HTTP page") from exc

            def close(self):
                if not self.closed:
                    self.closed = True
                    adapter._request({"action": "close", "cursor": identity},
                                     Control(time.monotonic() + min(adapter.timeout, 1)))

        return Cursor()


class LoopbackEndpoint:
    """Bounded local wire dispatcher for an explicitly owned test HTTP server.

    This object starts no server/thread. Host code supplies request size limits,
    HTTP lifecycle and serialization. It must call close() on shutdown. Cursor
    count is bounded; an actual service additionally needs leases/authentication.
    """

    def __init__(self, adapter, *, max_cursors=32, max_batch=256, max_page=256):
        self.adapter = adapter
        self.max_cursors, self.max_batch, self.max_page = max_cursors, max_batch, max_page
        self._cursors = {}
        self._next_id = 0

    def dispatch(self, request):
        try:
            timeout = request.get("timeout_seconds", 5.0)
            if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
                raise ValueError("Invalid loopback timeout")
            control = Control(time.monotonic() + timeout)
            action = request["action"]
            if action == "snapshot":
                return {"snapshot": _snapshot_wire(self.adapter.snapshot())}
            if action in {"batch", "open"}:
                snapshot = _snapshot_read(request["snapshot"])
                if snapshot != self.adapter.snapshot():
                    raise ProviderError(Status.SNAPSHOT_CHANGED, "Loopback revision changed")
            if action == "batch":
                rows = request["rows"]
                if len(rows) > self.max_batch:
                    raise ProviderError(Status.RESOURCE_LIMIT, "Loopback batch limit")
                result = self.adapter.evaluate_batch(request["operation"],
                                                     tuple(Request(identity, _decode(args)) for identity, args in rows),
                                                     snapshot, control)
                return {"snapshot": _snapshot_wire(result.snapshot), "complete": result.complete,
                        "rows": [[row.row_id, row.result.status.value, _encode(row.result.value)]
                                 for row in result.replies]}
            if action == "open":
                if len(self._cursors) >= self.max_cursors:
                    raise ProviderError(Status.RESOURCE_LIMIT, "Loopback cursor limit")
                cursor = self.adapter.open_scan(request["operation"], _decode(request["arguments"]),
                                                snapshot, control)
                identity = str(self._next_id)
                self._next_id += 1
                self._cursors[identity] = cursor
                return {"cursor": identity, "snapshot": _snapshot_wire(snapshot)}
            if action == "next":
                limit = request["limit"]
                if type(limit) is not int or not 1 <= limit <= self.max_page:
                    raise ProviderError(Status.RESOURCE_LIMIT, "Loopback page limit")
                result = self._cursors[request["cursor"]].next_page(limit, control)
                return {"snapshot": _snapshot_wire(result.snapshot), "complete": result.complete,
                        "continuation": result.continuation, "rows": [_encode(row) for row in result.rows]}
            if action == "close":
                cursor = self._cursors.pop(request["cursor"], None)
                if cursor is not None:
                    cursor.close()
                return {"closed": True}
            raise ProviderError(Status.PROTOCOL_ERROR, "Unknown loopback action")
        except ProviderError as exc:
            return {"error": exc.status.value, "message": str(exc)}
        except (ValueError, TypeError, KeyError) as exc:
            return {"error": Status.PROTOCOL_ERROR.value, "message": str(exc)}

    def close(self):
        for cursor in self._cursors.values():
            cursor.close()
        self._cursors.clear()


class DirectedRoadProvider:
    """Finite directed graph with explicit, nonnegative edge lengths in metres.

    This exact minimum-supplied-length capability has no map matcher, turn-state
    restrictions, traffic model, lane rules or vendor data loader. Each graph is
    for one declared vehicle/profile; node membership defines regional coverage.
    """

    operation = "urn:dlp:road:shortestDistance"

    def __init__(self, edges, *, nodes=(), revision="1", profile="car", name="directed-road",
                 max_nodes=100000, max_edges=500000, max_bytes=64 * 1024 * 1024):
        if any(type(value) is not int or value < 1 for value in (max_nodes, max_edges, max_bytes)):
            raise ValueError("Road graph limits must be positive integers")
        self.max_nodes, self.max_edges = max_nodes, max_edges
        self.max_bytes = max_bytes
        self.profile, self.name = str(profile), str(name)
        self._revision = None
        self.replace_graph(edges, nodes=nodes, revision=revision)

    def replace_graph(self, edges, *, nodes=(), revision):
        if type(revision) is not str or not revision or revision == self._revision:
            raise ValueError("Replacement graph needs a new nonempty revision")
        vertices, adjacency = set(), {}
        retained_bytes = 0
        for node in nodes:
            if not isinstance(node, URIRef):
                raise TypeError("Road nodes must be stable URIRefs")
            if node not in vertices:
                retained_bytes += len(str(node).encode()) * 4 + 256
                vertices.add(node)
            if len(vertices) > self.max_nodes:
                raise ProviderError(Status.RESOURCE_LIMIT, "Road node limit")
            if retained_bytes > self.max_bytes:
                raise ProviderError(Status.RESOURCE_LIMIT, "Road graph byte limit")
        for index, (start, end, metres) in enumerate(edges):
            if index >= self.max_edges:
                raise ProviderError(Status.RESOURCE_LIMIT, "Road edge limit")
            if not isinstance(start, URIRef) or not isinstance(end, URIRef):
                raise TypeError("Road endpoints must be stable URIRefs")
            if type(metres) not in (int, float) or not math.isfinite(metres) or metres < 0:
                raise ValueError("Road weights must be finite nonnegative metre values")
            for node in (start, end):
                if node not in vertices:
                    retained_bytes += len(str(node).encode()) * 4 + 256
                    vertices.add(node)
            retained_bytes += 128
            if len(vertices) > self.max_nodes:
                raise ProviderError(Status.RESOURCE_LIMIT, "Road node limit")
            if retained_bytes > self.max_bytes:
                raise ProviderError(Status.RESOURCE_LIMIT, "Road graph byte limit")
            adjacency.setdefault(start, []).append((end, float(metres)))
        self._nodes = frozenset(vertices)
        self._adjacency = {node: tuple(outgoing) for node, outgoing in adjacency.items()}
        self._revision = revision
        self.retained_bytes = retained_bytes

    def snapshot(self):
        return Snapshot(self.name, "directed-dijkstra-v1", self._revision,
                        (("profile", self.profile), ("objective", "minimum-supplied-edge-length"),
                         ("unit", "metre")))

    def register(self, registry):
        return registry.register(self.operation, self, input_types=("iri", "iri", "string"),
                                 result_type="float64", output_unit="metre")

    def _distance(self, start, end, profile, control):
        if str(profile) != self.profile:
            return ProviderResult(Status.DOMAIN_ERROR)
        if start not in self._nodes or end not in self._nodes:
            return ProviderResult(Status.OUT_OF_REGION)
        pending, best, sequence = [(0.0, 0, start)], {start: 0.0}, 0
        while pending:
            control.check()
            cost, _, node = heapq.heappop(pending)
            if cost != best[node]:
                continue
            if node == end:
                return ProviderResult(Status.OK, cost)
            for target, length in self._adjacency.get(node, ()):
                control.check()
                candidate = cost + length
                if not math.isfinite(candidate):
                    return ProviderResult(Status.DOMAIN_ERROR)
                if candidate < best.get(target, math.inf):
                    best[target] = candidate
                    sequence += 1
                    heapq.heappush(pending, (candidate, sequence, target))
        return ProviderResult(Status.NO_ROUTE)

    def evaluate_batch(self, operation, requests, snapshot, control):
        if operation != self.operation:
            raise ProviderError(Status.UNAVAILABLE, "Unsupported road operation")
        replies = tuple(Reply(row.row_id, self._distance(*row.arguments, control)) for row in requests)
        return BatchReply(snapshot, replies)


class StatusProvider(FakeProvider):
    """Explicit status inspection for query bindings that retain domain outcomes."""

    def __init__(self):
        def value(result):
            if isinstance(result, ProviderResult):
                if result.status != Status.OK:
                    return ProviderResult(Status.DOMAIN_ERROR)
                return result.value
            return result

        super().__init__({
            "urn:dlp:provider:isOK": lambda result: (not isinstance(result, ProviderResult)
                                                    or result.status == Status.OK),
            "urn:dlp:provider:value": value,
        }, name="provider-status")

    def register(self, registry):
        registry.register("urn:dlp:provider:isOK", self, input_types=("any",), result_type="boolean")
        registry.register("urn:dlp:provider:value", self, input_types=("any",), result_type="any")
