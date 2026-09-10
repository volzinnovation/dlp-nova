#!/usr/bin/env python3
"""Execute indexed geospatial rules against the PROLIX class hierarchy."""
import argparse
import json
from pathlib import Path

from rdflib import Graph, Literal, Namespace

from dlp_reasoner import Reasoner, parse_dlp
from dlp_reasoner.domains import DomainRegistry
from dlp_reasoner.providers import ProviderRegistry
from dlp_reasoner.query_runtime import QueryRuntime, QueryScope
from dlp_reasoner.scoped_views import LocationView
from dlp_reasoner.spatial import PointIndex


HERE = Path(__file__).resolve().parent
SIGN = Namespace("https://example.org/traffic-sign#")
OSM = Namespace("https://example.org/osm#")
EX = Namespace("https://example.org/traffic-sign/example#")
Q = Namespace("urn:dlp:traffic-query:")


def setup(backend):
    graph = Graph()
    for name in ("taxonomy.dlp", "fixtures.dlp"):
        graph += parse_dlp((HERE / name).read_text())
    reasoner = Reasoner(graph, profile="L0", backend=backend)
    domains = DomainRegistry(backend=backend)
    view = LocationView(reasoner, sign_class=SIGN.TrafficSign, location_property=SIGN.locatedAtNode,
                        latitude_property=OSM.latitude, longitude_property=OSM.longitude,
                        validated_property=Q.validatedLocation)
    index = PointIndex.from_location_view(view, revision="fixture-v1", backend=backend, domains=domains)
    providers = ProviderRegistry()
    index.register(providers)
    runtime = QueryRuntime((HERE / "queries.dlq").read_text(), reasoner=reasoner, backend=backend,
                           domains=domains, providers=providers)
    return reasoner, view, index, runtime


def run(backend):
    fixture = json.loads((HERE / "fixtures.json").read_text())
    reasoner, view, index, runtime = setup(backend)
    scope = QueryScope("urn:example:traffic-signs", "fixture-v1")
    reports = []
    try:
        selected = view.prepare(runtime.domains)
        for case in fixture["nearby_cases"]:
            inputs = dict(selected.relations)
            inputs[Q.search] = {(EX[case["anchor"]], SIGN[case["class"]],
                                 Literal(case["radius_metres"]), Literal(index.revision))}
            result = runtime.evaluate(inputs, scope=scope, diagnostics=selected.diagnostics)
            hits = sorted(str(sign).split("#")[-1] for anchor, sign, distance in result.rows(Q.nearby)
                          if not case["exclude_anchor"] or sign != anchor)
            assert hits == case["expected"], (case, hits)
            reports.append({"anchor": case["anchor"], "category": case["class"],
                            "radius_metres": case["radius_metres"], "hits": hits})
        for case in fixture["geodesic_cases"]:
            inputs = dict(selected.relations)
            inputs[Q.requestedPair] = {(EX[case["from"]], EX[case["to"]])}
            result = runtime.evaluate(inputs, scope=scope)
            distance = next(iter(result.rows(SIGN.signDistance)))[2]
            assert abs(float(distance) - case["metres"]) < 1e-6
        return {"backend": backend, "production_spatial_rules_executed": True,
                "metric": "WGS84 ellipsoidal geodesic metres", "queries": reports,
                "geodesic_cases_passed": len(fixture["geodesic_cases"]),
                "spatial_index": index.stats, "execution": runtime.stats}
    finally:
        runtime.close()
        index.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("python", "native", "both"), default="python")
    args = parser.parse_args()
    backends = ("python", "native") if args.backend == "both" else (args.backend,)
    print(json.dumps([run(backend) for backend in backends], indent=2))
