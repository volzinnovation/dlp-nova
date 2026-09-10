"""Resident WGS84 point candidate indexes and pinned finite provider scans.

Earth-centered XYZ boxes are conservative: Euclidean chord length is no greater
than surface geodesic length. Exact answers always refine through the explicitly
available GeographicLib WGS84 operation; candidates alone are not radius answers.
"""
from bisect import bisect_left, bisect_right
from itertools import islice
import math
from types import MappingProxyType

from rdflib import Literal, URIRef

from .domains import (DecimalValue, DomainError, DomainRegistry, FloatValue, IntegerValue,
                      Point, SPATIAL, decode)

POINT_CANDIDATES = SPATIAL + "pointCandidates"


def radius_metres(value):
    if type(value) is float:
        result = value
    elif type(value) is int:
        try:
            result = float(value)
        except OverflowError as exc:
            raise DomainError("DOMAIN_ERROR", "Radius exceeds finite binary64 range") from exc
    else:
        decoded = decode(value)
        if type(decoded) in (IntegerValue, FloatValue):
            result = float(decoded.value)
        elif type(decoded) is DecimalValue:
            result = decoded.coefficient / 10 ** decoded.scale
        else:
            raise DomainError("TYPE_ERROR", "Radius must be a finite numeric metre value")
    if not math.isfinite(result) or result < 0:
        raise DomainError("DOMAIN_ERROR", "Radius must be finite and nonnegative metres")
    return result


def _xyz(point):
    if type(point) is not Point:
        raise DomainError("TYPE_ERROR", "Expected a validated WGS84 Point")
    longitude, latitude = math.radians(point.longitude), math.radians(point.latitude)
    a, flattening = 6378137.0, 1 / 298.257223563
    e2 = flattening * (2 - flattening)
    sin_lat, cos_lat = math.sin(latitude), math.cos(latitude)
    n = a / math.sqrt(1 - e2 * sin_lat * sin_lat)
    return (n * cos_lat * math.cos(longitude), n * cos_lat * math.sin(longitude),
            n * (1 - e2) * sin_lat)


class PointIndex:
    """Immutable point revision. Old indexes stay valid until explicitly closed.

    ``backend='native'`` retains XYZ columns in C++; each query streams a bounded
    cursor instead of allocating every candidate. Python uses the same three
    sorted columns and chooses the smallest axis interval.
    """
    def __init__(self, points, *, revision, backend="python", max_points=1_000_000):
        if type(revision) is not str or not revision:
            raise ValueError("Point index requires a nonempty revision")
        if backend not in {"python", "native"}:
            raise ValueError("backend must be python or native")
        if type(max_points) is not int or max_points < 1 or len(points) > max_points:
            raise ValueError("Point index point limit exceeded or invalid")
        if any(not isinstance(identifier, URIRef) or type(point) is not Point
               for identifier, point in points.items()):
            raise TypeError("Point index entries require RDF IRI identifiers and validated Points")
        self.points = MappingProxyType(dict(points))
        self.revision, self.backend = revision, backend
        self._identifiers = tuple(self.points)
        self._xyz = tuple(map(_xyz, self.points.values()))
        self._native, self._closed, self._source_check = None, False, None
        self.stats = {"queries": 0, "candidates": 0, "exact_evaluations": 0}
        if backend == "native":
            from .spatial_native import NativePointIndex
            self._native = NativePointIndex(self._xyz)
            self._axes = ()
        else:
            self._axes = tuple(tuple(sorted((point[axis], i) for i, point in enumerate(self._xyz)))
                               for axis in range(3))

    @classmethod
    def from_location_view(cls, view, *, revision, backend="python", domains=None,
                           max_points=1_000_000):
        registry = domains if domains is not None else DomainRegistry(backend=backend)
        selected = view.prepare(registry)
        token = view.reasoner._query_cache_token()
        points = {}
        for identifier, node in selected.relations[view.validated_property]:
            if len(points) >= max_points:
                raise DomainError("RESOURCE_LIMIT", "Accepted location point limit exceeded")
            longitude = next(iter(view.reasoner.property_values(node, view.longitude_property)))
            latitude = next(iter(view.reasoner.property_values(node, view.latitude_property)))
            points[identifier] = registry.evaluate(SPATIAL + "wgs84Point", (longitude, latitude))
        if view.reasoner._query_cache_token() != token:
            raise DomainError("STALE_SOURCE", "Location source changed while building index")
        index = cls(points, revision=revision, backend=backend, max_points=max_points)
        index._source_check = lambda: view.reasoner._query_cache_token() == token
        index.diagnostics = selected.diagnostics
        return index

    def _check(self):
        if self._closed:
            raise DomainError("CLOSED", "Point index is closed")
        if self._source_check is not None and not self._source_check():
            raise DomainError("STALE_SOURCE", "Location source changed; rebuild the point index")

    def candidates(self, point, radius):
        self._check()
        center = _xyz(point)
        # At most Earth's diameter is needed; the margin covers binary64 ECEF
        # conversion error and includes coincident poles/antimeridian endpoints.
        bound = min(radius_metres(radius), 2 * 6378137.0) + 1e-6
        lower = tuple(value - bound for value in center)
        upper = tuple(value + bound for value in center)
        self.stats["queries"] += 1
        if self._native is not None:
            iterator = self._native.candidates(lower, upper)
        else:
            ranges = [(bisect_left(axis, (lower[j], -1)),
                       bisect_right(axis, (upper[j], len(self.points))))
                      for j, axis in enumerate(self._axes)]
            axis = min(range(3), key=lambda j: ranges[j][1] - ranges[j][0])
            start, end = ranges[axis]
            iterator = (self._axes[axis][offset][1] for offset in range(start, end))
        try:
            while True:
                self._check()
                try:
                    index = next(iterator)
                except StopIteration:
                    break
                if all(low <= value <= high for low, value, high in
                       zip(lower, self._xyz[index], upper)):
                    self.stats["candidates"] += 1
                    yield self._identifiers[index]
        finally:
            iterator.close()

    def within(self, point, radius, *, domains=None):
        registry = domains if domains is not None else DomainRegistry(backend=self.backend)
        bound, result = radius_metres(radius), set()
        candidates = self.candidates(point, bound)
        try:
            while chunk := tuple(islice(candidates, 256)):
                replies = registry.evaluate_batch(SPATIAL + "wgs84Distance",
                    [(point, self.points[identifier]) for identifier in chunk])
                self.stats["exact_evaluations"] += len(chunk)
                for identifier, reply in zip(chunk, replies):
                    if not reply.ok:
                        raise reply.error
                    if float(reply.value) <= bound:
                        result.add(identifier)
        finally:
            candidates.close()
        self._check()
        return frozenset(result)

    def register(self, registry, *, operation=POINT_CANDIDATES):
        adapter = PointProvider(self)
        registry.register(operation, adapter, input_types=("point", "number", "any"),
                          cardinality="many", output_types=("iri",), coverage="candidate_superset")
        return adapter

    def close(self):
        self._closed = True
        if self._native is not None:
            self._native.close()

    def __enter__(self):
        self._check()
        return self

    def __exit__(self, *_):
        self.close()


class PointProvider:
    """Provider adapter for an index or callable returning the current index."""
    def __init__(self, index):
        self._index = index if callable(index) else lambda: index

    def snapshot(self):
        from .providers import Snapshot
        index = self._index()
        index._check()
        return Snapshot("dlp-point-index", "ecef-box-v1-" + index.backend, index.revision)

    def open_scan(self, operation, arguments, snapshot, control):
        from .providers import ProviderError, Status
        control.check()
        index = self._index()
        if self.snapshot() != snapshot:
            raise ProviderError(Status.SNAPSHOT_CHANGED, "Point index revision changed")
        point, radius, revision = arguments
        if not isinstance(revision, (str, URIRef, Literal)) or str(revision) != index.revision:
            raise ProviderError(Status.SNAPSHOT_CHANGED, "Requested point snapshot does not match index")
        return _PointCursor(index.candidates(point, radius), snapshot)


class _PointCursor:
    def __init__(self, iterator, snapshot):
        self.iterator, self.snapshot, self.offset, self.closed = iterator, snapshot, 0, False

    def next_page(self, limit, control):
        from .providers import ScanPage
        control.check()
        if self.closed:
            raise RuntimeError("Spatial cursor is closed")
        rows = []
        for _ in range(limit):
            control.check()
            try:
                rows.append((next(self.iterator),))
            except StopIteration:
                self.close()
                return ScanPage(self.snapshot, tuple(rows), True)
        self.offset += len(rows)
        return ScanPage(self.snapshot, tuple(rows), False, str(self.offset))

    def close(self):
        if not self.closed:
            self.closed = True
            self.iterator.close()
