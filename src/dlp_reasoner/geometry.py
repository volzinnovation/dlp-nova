"""Resident projected geometries through the reentrant GEOS C API.

This optional provider owns all GEOS handles and prepared geometries. Rules pass
stable geometry identifiers, not pointers. Its CRS contract explicitly declares
projected coordinates and conversion to metres; it never treats longitude and
latitude as planar metre coordinates. GEOS is an optional preinstalled dependency.
"""
from __future__ import annotations

import ctypes as c
from ctypes.util import find_library
from dataclasses import dataclass
import math
from pathlib import Path
import shutil
import subprocess
import threading

from rdflib import Literal, URIRef

from .domains import DecimalValue, FloatValue, IntegerValue, decode
from .providers import (BatchReply, ProviderError, ProviderResult, Reply, Snapshot,
                        Status)


@dataclass(frozen=True)
class ProjectedCRS:
    identifier: str
    metres_per_unit: float = 1.0

    def __post_init__(self):
        if not isinstance(self.identifier, str) or not self.identifier:
            raise ValueError("A projected CRS identifier is required")
        if self.identifier.upper() in {"EPSG:4326", "EPSG:4269", "OGC:CRS84", "CRS84"}:
            raise ValueError("Geographic coordinates require an ellipsoidal operation")
        if (type(self.metres_per_unit) not in {float, int}
                or not math.isfinite(self.metres_per_unit) or self.metres_per_unit <= 0):
            raise ValueError("Projected coordinate-unit conversion must be positive and finite")


def _library(path):
    target = path or find_library("geos_c")
    if not target and shutil.which("pkg-config"):
        probe = subprocess.run(["pkg-config", "--variable=libdir", "geos"],
                               capture_output=True, text=True, timeout=10)
        if probe.returncode == 0:
            for name in ("libgeos_c.dylib", "libgeos_c.so", "geos_c.dll"):
                candidate = Path(probe.stdout.strip()) / name
                if candidate.is_file():
                    target = str(candidate)
                    break
    if not target:
        raise ProviderError(Status.UNAVAILABLE, "GEOS C API library is not available")
    try:
        library = c.CDLL(target)
        signatures = {
            "GEOSversion": (c.c_char_p, []),
            "GEOS_init_r": (c.c_void_p, []),
            "GEOS_finish_r": (None, [c.c_void_p]),
            "GEOSWKTReader_create_r": (c.c_void_p, [c.c_void_p]),
            "GEOSWKTReader_destroy_r": (None, [c.c_void_p, c.c_void_p]),
            "GEOSWKTReader_read_r": (c.c_void_p, [c.c_void_p, c.c_void_p, c.c_char_p]),
            "GEOSGeom_destroy_r": (None, [c.c_void_p, c.c_void_p]),
            "GEOSisValid_r": (c.c_byte, [c.c_void_p, c.c_void_p]),
            "GEOSisEmpty_r": (c.c_byte, [c.c_void_p, c.c_void_p]),
            "GEOSGeom_getCoordinateDimension_r": (c.c_int, [c.c_void_p, c.c_void_p]),
            "GEOSPrepare_r": (c.c_void_p, [c.c_void_p, c.c_void_p]),
            "GEOSPreparedGeom_destroy_r": (None, [c.c_void_p, c.c_void_p]),
            "GEOSPreparedContains_r": (c.c_byte, [c.c_void_p, c.c_void_p, c.c_void_p]),
            "GEOSPreparedCovers_r": (c.c_byte, [c.c_void_p, c.c_void_p, c.c_void_p]),
            "GEOSPreparedIntersects_r": (c.c_byte, [c.c_void_p, c.c_void_p, c.c_void_p]),
            "GEOSDistance_r": (c.c_int, [c.c_void_p, c.c_void_p, c.c_void_p, c.POINTER(c.c_double)]),
        }
        for name, (result, arguments) in signatures.items():
            function = getattr(library, name)
            function.restype, function.argtypes = result, arguments
        return library
    except (OSError, AttributeError) as exc:
        raise ProviderError(Status.UNAVAILABLE, f"Cannot load compatible GEOS C API: {exc}") from exc


class GeometryProvider:
    """Immutable geometry records with native preparation reused across queries.

    Empty/invalid geometries are rejected on ingestion. Contains excludes the
    boundary while covers includes it. Distance and dwithin use converted metres.
    Updates invalidate the provider revision atomically. Hosts serialize contexts;
    the local lock also prevents handle destruction during C calls.
    """

    OPERATIONS = {"planarDistance": "float", "planarDwithin": "boolean",
                  "contains": "boolean", "covers": "boolean", "intersects": "boolean"}

    def __init__(self, *, name="geos", revision="0", library=None,
                 max_geometries=100_000, max_wkt_bytes=64 * 1024 * 1024):
        if type(max_geometries) is not int or max_geometries < 1:
            raise ValueError("max_geometries must be a positive integer")
        if type(max_wkt_bytes) is not int or max_wkt_bytes < 1:
            raise ValueError("max_wkt_bytes must be a positive integer")
        self._lib = _library(library)
        self._ctx = self._lib.GEOS_init_r()
        if not self._ctx:
            raise ProviderError(Status.UNAVAILABLE, "Could not initialize GEOS context")
        self._geometries, self._bytes = {}, 0
        self._lock = threading.RLock()
        self.name, self.revision, self._generation = name, str(revision), 0
        self.max_geometries, self.max_wkt_bytes = max_geometries, max_wkt_bytes
        self.version = self._lib.GEOSversion().decode("ascii")
        self.preparations = self.calls = 0

    def _open(self):
        if self._ctx is None:
            raise ProviderError(Status.UNAVAILABLE, "GEOS context is closed")

    def snapshot(self):
        with self._lock:
            self._open()
            return Snapshot(self.name, "geos-c-" + self.version,
                            self.revision + ":" + str(self._generation),
                            (("metric", "planar-metres-v1"),))

    def _destroy(self, entry):
        geometry, prepared, _, _ = entry
        self._lib.GEOSPreparedGeom_destroy_r(self._ctx, prepared)
        self._lib.GEOSGeom_destroy_r(self._ctx, geometry)

    def put(self, identifier, wkt, *, crs, revision=None):
        if not isinstance(identifier, URIRef) or not isinstance(crs, ProjectedCRS):
            raise TypeError("Geometry requires an IRI identifier and ProjectedCRS declaration")
        if type(wkt) is not str or "\x00" in wkt:
            raise ValueError("WKT must be a string without NUL")
        encoded = wkt.encode("utf-8")
        with self._lock:
            self._open()
            old = self._geometries.get(identifier)
            size = self._bytes - (old[3] if old else 0) + len(encoded)
            if size > self.max_wkt_bytes or (old is None and len(self._geometries) >= self.max_geometries):
                raise ProviderError(Status.RESOURCE_LIMIT, "Geometry store capacity exceeded")
            reader = self._lib.GEOSWKTReader_create_r(self._ctx)
            if not reader:
                raise ProviderError(Status.RESOURCE_LIMIT, "Could not allocate WKT reader")
            try:
                geometry = self._lib.GEOSWKTReader_read_r(self._ctx, reader, encoded)
            finally:
                self._lib.GEOSWKTReader_destroy_r(self._ctx, reader)
            if not geometry:
                raise ProviderError(Status.DOMAIN_ERROR, "Invalid WKT geometry")
            prepared = None
            try:
                if self._lib.GEOSisValid_r(self._ctx, geometry) != 1:
                    raise ProviderError(Status.DOMAIN_ERROR, "Invalid geometry topology")
                if self._lib.GEOSisEmpty_r(self._ctx, geometry) != 0:
                    raise ProviderError(Status.DOMAIN_ERROR, "Empty geometries are unsupported")
                if self._lib.GEOSGeom_getCoordinateDimension_r(self._ctx, geometry) != 2:
                    raise ProviderError(Status.DOMAIN_ERROR, "This planar profile requires two dimensions")
                prepared = self._lib.GEOSPrepare_r(self._ctx, geometry)
                if not prepared:
                    raise ProviderError(Status.RESOURCE_LIMIT, "Could not prepare geometry")
            except BaseException:
                self._lib.GEOSGeom_destroy_r(self._ctx, geometry)
                raise
            self._geometries[identifier] = (geometry, prepared, crs, len(encoded))
            self._bytes = size
            self.preparations += 1
            self._generation += 1
            if revision is not None:
                self.revision = str(revision)
            if old:
                self._destroy(old)

    def remove(self, identifier, *, revision=None):
        with self._lock:
            self._open()
            entry = self._geometries.pop(identifier, None)
            if entry is not None:
                self._destroy(entry)
                self._bytes -= entry[3]
                self._generation += 1
            if revision is not None:
                self.revision = str(revision)

    def register(self, registry, *, namespace="urn:dlp:spatial:"):
        for name, result in self.OPERATIONS.items():
            registry.register(namespace + name, self, input_types=("iri", "iri") + (
                ("number",) if name == "planarDwithin" else ()), result_type=result)

    def evaluate_batch(self, operation, requests, snapshot, control):
        name = operation.rsplit(":", 1)[-1]
        if name not in self.OPERATIONS:
            raise ProviderError(Status.UNAVAILABLE, "Unknown planar operation")
        with self._lock:
            self._open()
            if snapshot != self.snapshot():
                raise ProviderError(Status.SNAPSHOT_CHANGED, "Geometry revision changed")
            replies = []
            for request in requests:
                control.check()
                try:
                    left, right = (self._geometries[value] for value in request.arguments[:2])
                except KeyError as exc:
                    raise ProviderError(Status.DOMAIN_ERROR, "Unknown geometry identifier") from exc
                if left[2] != right[2]:
                    raise ProviderError(Status.DOMAIN_ERROR, "Projected CRS/unit mismatch")
                if name in {"planarDistance", "planarDwithin"}:
                    distance = c.c_double()
                    ok = self._lib.GEOSDistance_r(self._ctx, left[0], right[0], c.byref(distance))
                    value = distance.value * left[2].metres_per_unit
                    if ok != 1 or not math.isfinite(value) or value < 0:
                        raise ProviderError(Status.DOMAIN_ERROR, "GEOS distance evaluation failed")
                    if name == "planarDwithin":
                        radius = decode(request.arguments[2])
                        if isinstance(radius, (FloatValue, IntegerValue)):
                            radius = float(radius.value)
                        elif isinstance(radius, DecimalValue):
                            radius = radius.coefficient / 10 ** radius.scale
                        else:
                            raise ProviderError(Status.DOMAIN_ERROR, "Radius must be numeric metres")
                        if not math.isfinite(radius) or radius < 0:
                            raise ProviderError(Status.DOMAIN_ERROR, "Radius must be finite nonnegative metres")
                        value = value <= radius
                else:
                    function = getattr(self._lib, "GEOSPrepared" + name.capitalize() + "_r")
                    value = function(self._ctx, left[1], right[0])
                    if value not in (0, 1):
                        raise ProviderError(Status.DOMAIN_ERROR, "GEOS predicate evaluation failed")
                    value = bool(value)
                replies.append(Reply(request.row_id, ProviderResult(Status.OK, Literal(value))))
                self.calls += 1
            return BatchReply(snapshot, tuple(replies))

    def close(self):
        with self._lock:
            if self._ctx is not None:
                for entry in self._geometries.values():
                    self._destroy(entry)
                self._geometries.clear()
                self._lib.GEOS_finish_r(self._ctx)
                self._ctx = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
