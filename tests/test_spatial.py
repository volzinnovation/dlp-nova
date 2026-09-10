"""Candidate completeness, exact refinement and pinned native/provider lifetime."""
from dataclasses import replace
import random

import pytest
from rdflib import Literal, URIRef

from dlp_reasoner.domains import DomainError, DomainRegistry, Point, SPATIAL
from dlp_reasoner.providers import ProviderError, ProviderRegistry, Status
from dlp_reasoner.spatial import POINT_CANDIDATES, PointIndex, PointProvider


@pytest.fixture(params=["python", "native"])
def backend(request):
    return request.param


def point(lon, lat):
    return Point(float(lon), float(lat))


def test_antimeridian_poles_and_inclusive_distance_boundaries(backend):
    points = {URIRef("urn:" + name): value for name, value in {
        "west": point(-179.999, 0), "east": point(179.999, 0),
        "north_a": point(0, 90), "north_b": point(180, 90),
        "south": point(90, -90), "zero": point(0, 0), "degree": point(1, 0)}.items()}
    registry = DomainRegistry(backend=backend)
    with PointIndex(points, revision="edge-cases", backend=backend) as index:
        assert index.within(point(180, 0), 120, domains=registry) == {URIRef("urn:west"), URIRef("urn:east")}
        assert index.within(point(45, 90), 0, domains=registry) == {URIRef("urn:north_a"), URIRef("urn:north_b")}
        distance = float(registry.evaluate(SPATIAL + "wgs84Distance", (point(0, 0), point(1, 0))))
        assert abs(distance - 111319.49079327357) < 1e-7
        assert URIRef("urn:degree") in index.within(point(0, 0), distance, domains=registry)
        assert URIRef("urn:degree") not in index.within(point(0, 0), distance - 1e-6, domains=registry)


def test_indexed_answers_equal_complete_exhaustive_reference(backend):
    rng = random.Random(6491)
    points = {URIRef(f"urn:p:{i}"): point(rng.uniform(-180, 180), rng.uniform(-90, 90))
              for i in range(160)}
    registry = DomainRegistry(backend=backend)
    with PointIndex(points, revision="random-v1", backend=backend) as index:
        native_handle = None if index._native is None else index._native.handle.value
        for center, radius in [(point(179.9, 89.99), 30_000), (point(-179.9, -89.9), 200_000),
                               (point(0, 0), 0), (point(0, 0), 30_000_000)] + [
                (point(rng.uniform(-180, 180), rng.uniform(-90, 90)), rng.uniform(10, 15_000_000))
                for _ in range(16)]:
            replies = registry.evaluate_batch(SPATIAL + "wgs84Distance", [(center, p) for p in points.values()])
            assert all(reply.ok for reply in replies)
            expected = {identifier for identifier, reply in zip(points, replies) if float(reply.value) <= radius}
            assert expected <= set(index.candidates(center, radius))
            assert index.within(center, radius, domains=registry) == expected
        if native_handle is not None:
            assert index._native.handle.value == native_handle


def test_selective_query_refines_only_candidates_and_retains_index(backend):
    points = {URIRef(f"urn:p:{i}"): point(i / 100, 0) for i in range(1000)}
    with PointIndex(points, revision="static", backend=backend) as index:
        axes, native = index._axes, index._native
        assert index.within(point(0, 0), 100) == {URIRef("urn:p:0")}
        assert index.stats["exact_evaluations"] == 1
        assert index.within(point(.01, 0), 100) == {URIRef("urn:p:1")}
        assert index.stats["exact_evaluations"] == 2
        assert index._axes is axes and index._native is native


@pytest.mark.parametrize("radius", [-1, float("nan"), float("inf"), Literal("bad"), True, 10 ** 1000])
def test_invalid_radius_is_never_an_empty_answer(radius):
    with PointIndex({}, revision="empty") as index:
        with pytest.raises(DomainError):
            list(index.candidates(point(0, 0), radius))


def test_early_close_and_explicit_index_close_during_cursor(backend):
    with PointIndex({URIRef(f"urn:{i}"): point(0, 0) for i in range(1000)}, revision="one", backend=backend) as index:
        cursor = index.candidates(point(0, 0), 1)
        next(cursor)
        cursor.close()
        assert len(list(index.candidates(point(0, 0), 1))) == 1000
        suspended = index.candidates(point(0, 0), 1)
        next(suspended)
        index.close()
        with pytest.raises(DomainError, match="closed"):
            next(suspended)


def test_provider_snapshot_paging_cache_and_mutation(backend):
    points = {URIRef(f"urn:{i}"): point(0, 0) for i in range(20)}
    first = PointIndex(points, revision="one", backend=backend)
    second = PointIndex(points, revision="two", backend=backend)
    current = [first]
    adapter = PointProvider(lambda: current[0])
    registry = ProviderRegistry(max_page=3)
    registry.register(POINT_CANDIDATES, adapter, input_types=("point", "number", "any"),
                      cardinality="many", output_types=("iri",), coverage="candidate_superset")
    try:
        arguments = (point(0, 0), Literal(1), Literal("one"))
        cursor = registry.scan(POINT_CANDIDATES, arguments)
        assert set(cursor) == {(identifier,) for identifier in points}
        assert cursor.complete and registry.cache_info()["entries"] == 1
        assert set(registry.scan(POINT_CANDIDATES, arguments)) == {(identifier,) for identifier in points}
        assert registry.cache_info()["hits"] == 1
        cursor = registry.scan(POINT_CANDIDATES, arguments)
        next(cursor)
        current[0] = second
        with pytest.raises(ProviderError) as error:
            next(cursor)
        assert error.value.status == Status.SNAPSHOT_CHANGED
        assert not cursor.complete
        with pytest.raises(ProviderError, match="snapshot does not match"):
            list(registry.scan(POINT_CANDIDATES, arguments))
    finally:
        first.close()
        second.close()


def test_location_view_source_invalidation(backend):
    from rdflib import Graph
    from dlp_reasoner import Reasoner
    from dlp_reasoner.scoped_views import LocationView
    graph = Graph().parse(data='''@prefix ex: <urn:ex:> . @prefix owl: <http://www.w3.org/2002/07/owl#> .
        ex:Sign a owl:Class . ex:location a owl:ObjectProperty .
        ex:lat a owl:DatatypeProperty . ex:lon a owl:DatatypeProperty .
        ex:a a ex:Sign ; ex:location ex:node . ex:node ex:lat 0.0 ; ex:lon 0.0 .''', format="turtle")
    reasoner = Reasoner(graph, backend=backend)
    view = LocationView(reasoner, sign_class="urn:ex:Sign", location_property="urn:ex:location",
        latitude_property="urn:ex:lat", longitude_property="urn:ex:lon", validated_property="urn:ex:valid")
    with PointIndex.from_location_view(view, revision="one", backend=backend) as index:
        assert index.within(point(0, 0), 1) == {URIRef("urn:ex:a")}
        reasoner.graph.add((URIRef("urn:ex:node"), URIRef("urn:ex:lat"), Literal(1)))
        with pytest.raises(DomainError, match="source changed"):
            list(index.candidates(point(0, 0), 1))


def test_reject_invalid_index_entries_and_point_limit():
    with pytest.raises(TypeError):
        PointIndex({"not-an-iri": point(0, 0)}, revision="v1")
    with pytest.raises(ValueError):
        PointIndex({URIRef("urn:a"): point(0, 0), URIRef("urn:b"): point(0, 0)}, revision="v1", max_points=1)
    with pytest.raises(DomainError):
        replace(point(0, 0), crs="EPSG:3857")
