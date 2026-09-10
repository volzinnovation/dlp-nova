"""Real GEOS computations retain CRS, units, boundary and ownership contracts."""
import pytest
from rdflib import Literal, Namespace

from dlp_reasoner.geometry import GeometryProvider, ProjectedCRS, _library
from dlp_reasoner.providers import ProviderError, ProviderRegistry
from dlp_reasoner.query_runtime import QueryRuntime, QueryScope


@pytest.fixture(autouse=True)
def require_geos():
    try:
        _library(None)
    except ProviderError as exc:
        pytest.skip(str(exc))


EX = Namespace("urn:test:geometry:")
SP = "urn:dlp:spatial:"
CRS = ProjectedCRS("EPSG:3857")


def result(registry, name, *values):
    return registry.evaluate(SP + name, [values])[0].value.toPython()


def test_projected_distance_units_boundaries_and_cache_revision():
    with GeometryProvider() as geos:
        registry = ProviderRegistry()
        geos.register(registry)
        geos.put(EX.origin, "POINT (0 0)", crs=CRS)
        geos.put(EX.point, "POINT (30 40)", crs=CRS)
        assert result(registry, "planarDistance", EX.origin, EX.point) == 50
        assert result(registry, "planarDwithin", EX.origin, EX.point, Literal(50))
        assert not result(registry, "planarDwithin", EX.origin, EX.point, Literal(49))
        prepared, calls = geos.preparations, geos.calls
        assert result(registry, "planarDistance", EX.origin, EX.point) == 50
        assert geos.preparations == prepared and geos.calls == calls
        geos.put(EX.point, "POINT (0 0)", crs=CRS)
        assert result(registry, "planarDistance", EX.origin, EX.point) == 0
        feet = ProjectedCRS("urn:test:projected-feet", 0.3048)
        geos.put(EX.feetA, "POINT (0 0)", crs=feet)
        geos.put(EX.feetB, "POINT (100 0)", crs=feet)
        assert result(registry, "planarDistance", EX.feetA, EX.feetB) == pytest.approx(30.48)
        with pytest.raises(ProviderError, match="CRS"):
            result(registry, "planarDistance", EX.origin, EX.feetB)


def test_contains_covers_and_intersects_have_different_boundary_behavior():
    with GeometryProvider() as geos:
        registry = ProviderRegistry()
        geos.register(registry)
        geos.put(EX.polygon, "POLYGON ((0 0,10 0,10 10,0 10,0 0))", crs=CRS)
        geos.put(EX.boundary, "POINT (0 5)", crs=CRS)
        assert not result(registry, "contains", EX.polygon, EX.boundary)
        assert result(registry, "covers", EX.polygon, EX.boundary)
        assert result(registry, "intersects", EX.polygon, EX.boundary)


def test_invalid_empty_three_dimensional_and_bad_crs_inputs_rejected_atomically():
    with GeometryProvider() as geos:
        geos.put(EX.point, "POINT (0 0)", crs=CRS)
        snapshot = geos.snapshot()
        for wkt in ("POINT EMPTY", "bad input", "POINT Z (0 0 1)",
                    "POLYGON ((0 0,1 1,1 0,0 1,0 0))"):
            with pytest.raises(ProviderError):
                geos.put(EX.point, wkt, crs=CRS)
            assert geos.snapshot() == snapshot
    with pytest.raises(ProviderError, match="closed"):
        geos.snapshot()
    with pytest.raises(ValueError, match="Geographic"):
        ProjectedCRS("EPSG:4326")


@pytest.mark.parametrize("backend", ["python", "native"])
def test_geometry_provider_is_executed_from_real_rules(backend):
    source = """version 1
    prefix ex: <urn:test:geometry:>
    prefix sp: <urn:dlp:spatial:>
    ex:near(?a, ?b) :- ex:pair(?a, ?b), filter sp:planarDwithin(?a, ?b, 50).
    """
    with GeometryProvider() as geos:
        registry = ProviderRegistry()
        geos.register(registry)
        geos.put(EX.origin, "POINT (0 0)", crs=CRS)
        geos.put(EX.point, "POINT (30 40)", crs=CRS)
        with QueryRuntime(source, providers=registry, backend=backend) as runtime:
            args = {EX.pair: {(EX.origin, EX.point)}}
            scope = QueryScope("urn:test:scope", "1")
            assert runtime.evaluate(args, scope=scope).rows(EX.near) == {(EX.origin, EX.point)}
            geos.put(EX.point, "POINT (100 100)", crs=CRS)
            changed = runtime.evaluate(args, scope=scope)
            assert not changed.rows(EX.near)
            assert changed.retractions[EX.near] == {(EX.origin, EX.point)}
