#!/usr/bin/env python3
"""Executable DLP Nova extension tutorial; run from an installed checkout.

python examples/dlp_nova/extension-demo.py --backend both
python examples/dlp_nova/extension-demo.py --backend both --geos

Core WGS84 operations require a compatible domain library or a C++17 compiler.
The --geos option additionally requires the separately installed GEOS C library.
"""

import argparse
from contextlib import ExitStack
import json
from pathlib import Path

from rdflib import Literal, Namespace, XSD

from dlp_reasoner.domains import DomainRegistry, Point
from dlp_reasoner.providers import DirectedRoadProvider, ProviderRegistry, Status
from dlp_reasoner.query_runtime import QueryRuntime, QueryScope
from dlp_reasoner.spatial import PointIndex
from dlp_reasoner.windows import Event, WindowStore


N = Namespace("urn:example:dlp-nova:")
HERE = Path(__file__).resolve().parent


def typed(text, datatype):
    return Literal(text, datatype=datatype, normalize=False)


def instant(text):
    return typed(text, XSD.dateTimeStamp)


def core(backend):
    start = instant("2026-09-10T08:00:00Z")
    end = instant("2026-09-10T09:00:00Z")
    birth = typed("2000-02-29", XSD.date)
    inputs = {
        N.anniversary: {
            (N.person, birth, typed("2021-02-28", XSD.date)),
            (N.person, birth, typed("2021-03-01", XSD.date)),
        },
        N.shift: {(Literal("leap-day"), typed("2024-02-28", XSD.date),
                   typed("P1D", XSD.dayTimeDuration))},
        N.elapsed: {(Literal("fractional"), instant("2026-09-10T08:00:00Z"),
                     instant("2026-09-10T08:00:01.250000Z"))},
        N.location: {(N.anchor, Literal(0), Literal(0)),
                     (N.near, Literal("0.0001", datatype=XSD.decimal), Literal(0)),
                     (N.far, Literal("0.001", datatype=XSD.decimal), Literal(0))},
        N.sign: {(N.near,), (N.far,)},
        N.validity: {(N.near, start, end), (N.far, start, end)},
        N.search: {(N.anchor, Literal(50), start)},
    }
    with QueryRuntime((HERE / "extension-core.dlq").read_text(), backend=backend) as runtime:
        first = runtime.evaluate(inputs, scope=QueryScope("urn:tutorial:core", "1"))
        assert {int(row[2]) for row in first.rows(N.age)} == {20, 21}
        assert first.rows(N.shifted) == {(Literal("leap-day"), typed("2024-02-29", XSD.date))}
        assert first.rows(N.seconds) == {(Literal("fractional"), typed("1.25", XSD.decimal))}
        assert {row[0] for row in first.rows(N.nearbyValid)} == {N.near}
        distances = {str(row[0]).removeprefix(str(N)): float(row[1])
                     for row in first.rows(N.distance)}
        assert abs(distances["near"] - 11.131949079327358) < 1e-6
        inputs[N.search] = {(N.anchor, Literal(50), end)}
        second = runtime.evaluate(inputs, scope=QueryScope("urn:tutorial:core", "2"))
        assert not second.rows(N.nearbyValid)
        assert second.retractions[N.nearbyValid] == first.rows(N.nearbyValid)
        return {"execution_mode": runtime.stats["execution_mode"],
                "completed_years": [20, 21], "distance_metres": distances,
                "start_included_end_excluded": True}


INDEX_RULES = """version 1
prefix nova: <urn:example:dlp-nova:>
prefix sp: <urn:dlp:spatial:>
nova:within(?id) :- nova:request(?center, ?radius, ?pointRevision),
    scan sp:pointCandidates(?center, ?radius, ?pointRevision) as ?id,
    nova:indexPoint(?id, ?point),
    filter sp:dwithin(?center, ?point, ?radius).
"""


def indexed(backend):
    points = {N.near: Point(0.0001, 0.0), N.far: Point(0.001, 0.0)}
    providers = ProviderRegistry()
    with PointIndex(points, revision="points-1", backend=backend) as index:
        index.register(providers)
        with QueryRuntime(INDEX_RULES, providers=providers, backend=backend) as runtime:
            result = runtime.evaluate({
                N.request: {(Point(0.0, 0.0), Literal(50), Literal("points-1"))},
                N.indexPoint: set(points.items()),
            }, scope=QueryScope("urn:tutorial:index", "1"))
            assert result.rows(N.within) == {(N.near,)}
            return {"answers": ["near"], "execution_mode": runtime.stats["execution_mode"]}


def roads():
    providers = ProviderRegistry()
    router = DirectedRoadProvider([(N.a, N.b, 30), (N.b, N.c, 40)],
                                  nodes=(N.isolated,), revision="roads-1", profile="car")
    router.register(providers)
    answers = providers.evaluate(router.operation, [
        (N.a, N.c, Literal("car")),
        (N.c, N.a, Literal("car")),
        (N.a, N.unknown, Literal("car")),
    ])
    assert float(answers[0].value) == 70
    assert [reply.status for reply in answers] == [Status.OK, Status.NO_ROUTE, Status.OUT_OF_REGION]
    return {"forward_metres": 70, "reverse": "NO_ROUTE", "unknown": "OUT_OF_REGION"}


def windows(backend):
    if backend == "native":
        from dlp_reasoner.native_windows import NativeWindowStore
        window_type = NativeWindowStore
    else:
        window_type = WindowStore
    context = (("map", "tutorial-map-1"),)
    with ExitStack() as owners:
        window = window_type(10_000_000, allowed_lateness=20_000_000, context=context)
        if hasattr(window, "close"):
            owners.callback(window.close)
        window.upsert(Event("outside", 1_000_000, "car", (False,)))
        window.upsert(Event("inside", 5_000_000, "car", (True,)))
        window.advance(10_000_000, watermark=0)
        assert {row[0] for row in window.entry_rows(lambda event: event.values[0])} == {"inside"}
        # An accepted late event changes which observation establishes entry.
        window.upsert(Event("late-inside", 3_000_000, "car", (True,)))
        assert {row[0] for row in window.entry_rows(lambda event: event.values[0])} == {"late-inside"}
        restored = window_type.restore(window.checkpoint(), expected_context=context)
        if hasattr(restored, "close"):
            owners.callback(restored.close)
        assert restored.rows() == window.rows()
        removed = restored.advance(30_000_000).removed
        assert len(removed) == 3 and not restored.rows()
        return {"initial_entry": "inside", "corrected_entry": "late-inside",
                "checkpoint_roundtrip": True, "idle_expiry_rows": len(removed)}


GEOMETRY_RULES = """version 1
prefix nova: <urn:example:dlp-nova:>
prefix sp: <urn:dlp:spatial:>
nova:contained(?polygon, ?point) :- nova:pair(?polygon, ?point),
    filter sp:contains(?polygon, ?point).
nova:covered(?polygon, ?point) :- nova:pair(?polygon, ?point),
    filter sp:covers(?polygon, ?point).
nova:distance(?a, ?b, ?metres) :- nova:distancePair(?a, ?b),
    bind sp:planarDistance(?a, ?b) as ?metres.
"""


def geometry(backend):
    from dlp_reasoner.geometry import GeometryProvider, ProjectedCRS
    providers = ProviderRegistry()
    crs = ProjectedCRS("urn:example:local-metre-grid")
    with GeometryProvider(revision="geometry-1") as geos:
        geos.put(N.square, "POLYGON ((0 0,10 0,10 10,0 10,0 0))", crs=crs)
        geos.put(N.edge, "POINT (0 5)", crs=crs)
        geos.put(N.origin, "POINT (0 0)", crs=crs)
        geos.put(N.point34, "POINT (30 40)", crs=crs)
        geos.register(providers)
        with QueryRuntime(GEOMETRY_RULES, providers=providers, backend=backend) as runtime:
            result = runtime.evaluate({N.pair: {(N.square, N.edge)},
                                       N.distancePair: {(N.origin, N.point34)}},
                                      scope=QueryScope("urn:tutorial:geometry", "1"))
            assert not result.rows(N.contained)
            assert result.rows(N.covered) == {(N.square, N.edge)}
            assert {float(row[2]) for row in result.rows(N.distance)} == {50.0}
            return {"geos_version": geos.version, "boundary_contains": False,
                    "boundary_covers": True, "planar_metres": 50,
                    "execution_mode": runtime.stats["execution_mode"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("python", "native", "both"), default="python")
    parser.add_argument("--geos", action="store_true", help="also exercise optional GEOS")
    args = parser.parse_args()
    reports = []
    for backend in (("python", "native") if args.backend == "both" else (args.backend,)):
        with DomainRegistry(backend) as domains:
            equal = domains.evaluate("urn:dlp:temporal:equal", [
                instant("2026-09-10T10:00:00+02:00"), instant("2026-09-10T08:00:00Z")])
            assert bool(equal)
        report = {"backend": backend, "core": core(backend), "index": indexed(backend),
                  "windows": windows(backend), "roads": roads()}
        if args.geos:
            report["geometry"] = geometry(backend)
        reports.append(report)
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
