"""Real traffic query rules combine inferred categories, indexes and providers."""
import importlib.util
import json
from pathlib import Path

import pytest
from rdflib import Literal
from rdflib.namespace import XSD

from dlp_reasoner.providers import DirectedRoadProvider, ProviderError, ProviderRegistry, StatusProvider
from dlp_reasoner.query_runtime import QueryRuntime, QueryScope
from dlp_reasoner.spatial import PointIndex


HERE = Path(__file__).resolve().parents[1] / "examples/traffic_signs"
spec = importlib.util.spec_from_file_location("traffic_query_example", HERE / "run_queries.py")
example = importlib.util.module_from_spec(spec)
spec.loader.exec_module(example)
EX, Q, SIGN, OSM = example.EX, example.Q, example.SIGN, example.OSM


@pytest.mark.parametrize("backend", ["python", "native"])
def test_all_worked_radius_and_geodesic_cases_execute_as_rules(backend):
    report = example.run(backend)
    assert report["production_spatial_rules_executed"]
    assert report["geodesic_cases_passed"] == 6


@pytest.mark.parametrize("backend", ["python", "native"])
def test_node_move_cannot_reuse_stale_spatial_or_query_cache(backend):
    reasoner, view, index, runtime = example.setup(backend)
    scope = QueryScope("urn:example:traffic", "1")
    try:
        inputs = dict(view.prepare(runtime.domains).relations)
        inputs[Q.search] = {(EX.stop_a, SIGN.StopSign, Literal(112), Literal(index.revision))}
        initial = runtime.evaluate(inputs, scope=scope)
        assert any(row[1] == EX.stop_b for row in initial.rows(Q.nearby))
        reasoner.update(remove=[(EX.node_b, OSM.longitude, Literal("0.001", datatype=XSD.decimal))],
                        add=[(EX.node_b, OSM.longitude, Literal("0.1", datatype=XSD.decimal))])
        with pytest.raises(ProviderError, match="Source changed|source changed"):
            runtime.evaluate(inputs, scope=scope)
        assert runtime.last_complete is initial and not runtime.complete
        fresh = PointIndex.from_location_view(view, revision="fixture-v2", backend=backend,
                                              domains=runtime.domains)
        try:
            fresh.register(runtime.providers)
            inputs = dict(view.prepare(runtime.domains).relations)
            inputs[Q.search] = {(EX.stop_a, SIGN.StopSign, Literal(112), Literal(fresh.revision))}
            changed = runtime.evaluate(inputs, scope=QueryScope(scope.name, "2"))
            assert not any(row[1] == EX.stop_b for row in changed.rows(Q.nearby))
            assert any(row[1] == EX.stop_b for row in changed.retractions[Q.nearby])
        finally:
            fresh.close()
    finally:
        runtime.close()
        index.close()


@pytest.mark.parametrize("backend", ["python", "native"])
def test_directed_road_distances_and_unreachable_statuses_execute_as_rules(backend):
    reasoner, view, index, unused = example.setup(backend)
    unused.close()
    index.close()
    cases = json.loads((HERE / "fixtures.json").read_text())["road_provider_reference"]
    roads = DirectedRoadProvider(((EX[e["from"]], EX[e["to"]], e["metres"]) for e in cases["edges"]),
                                  revision=cases["dataset_version"], profile=cases["profile"])
    providers = ProviderRegistry()
    roads.register(providers)
    StatusProvider().register(providers)
    scope = QueryScope("urn:example:roads", "1")
    with QueryRuntime((HERE / "road-queries.dlq").read_text(), reasoner=reasoner,
                      backend=backend, providers=providers) as runtime:
        for case in cases["cases"]:
            result = runtime.evaluate({Q.requestedRoadPair: {
                (EX[case["from"]], EX[case["to"]], Literal(cases["profile"]))}}, scope=scope)
            rows = result.rows(SIGN.roadDistance)
            if case["status"] == "OK":
                assert len(rows) == 1
                assert float(next(iter(rows))[2]) == pytest.approx(case["metres"])
            else:
                assert not rows
                assert next(iter(result.rows(Q.roadResult)))[2].status.value == "no_route"
