#!/usr/bin/env python3
"""Execute validity, GEOS radius and corrected event-window rules.

Requires the optional GEOS C library. The WindowStore supplies finite active and
predecessor relations; QueryRuntime executes all classification/entry rules.
"""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path

from rdflib import Literal, Namespace, XSD

from dlp_reasoner.domains import decode
from dlp_reasoner.geometry import GeometryProvider, ProjectedCRS
from dlp_reasoner.providers import ProviderRegistry
from dlp_reasoner.query_runtime import QueryRuntime, QueryScope
from dlp_reasoner.windows import Event, WindowStore


HERE = Path(__file__).resolve().parent
Q = Namespace("urn:dlp:event-query:")
HISTORY = Namespace("urn:dlp:history-query:")
EX = Namespace("urn:example:event:")


def instant(text):
    return Literal(text, datatype=XSD.dateTime, normalize=False)


def ticks(text):
    return decode(instant(text)).microseconds


def window_relations(window):
    active = window.rows()
    previous = set()
    for event_id, _, _, _ in active:
        before = window.predecessor(event_id)
        if before is not None:
            previous.add((Literal(event_id), before.values[0]))
    return {Q.active: {(Literal(identity), Literal(at), vehicle, geometry)
                       for identity, at, vehicle, geometry in active},
            Q.previous: previous}


def run_history(backend):
    fixture = json.loads((HERE / "fixtures.json").read_text())
    source = {HISTORY.closedVersion: set(), HISTORY.openVersion: set()}
    for version in fixture["speed_versions"]:
        row = (EX[version["id"]], EX[version["sign"]], Literal(version["kmh"]),
               *(instant(value) for value in version["valid"]), instant(version["recorded"][0]))
        if version["recorded"][1] is None:  # fixture explicitly declares infinity
            source[HISTORY.openVersion].add(row)
        else:
            source[HISTORY.closedVersion].add((*row, instant(version["recorded"][1])))
    reports = []
    with QueryRuntime((HERE / "history.dlq").read_text(), backend=backend) as runtime:
        for index, case in enumerate(fixture["bitemporal_cases"]):
            result = runtime.evaluate({**source, HISTORY.probe: {
                (instant(case["valid_at"]), instant(case["recorded_at"]))}},
                scope=QueryScope("urn:example:speed-history", str(index)))
            values = sorted(int(row[1]) for row in result.rows(HISTORY.speed))
            assert values == case["kmh"]
            reports.append({**case, "result": values})
        assert runtime.stats["execution_mode"] == backend
        return dict(cases=reports, execution=runtime.stats)


def run(backend):
    if backend == "native":
        from dlp_reasoner.native_windows import NativeWindowStore
        window_type = NativeWindowStore
    else:
        window_type = WindowStore
    fixture = json.loads((HERE / "fixtures.json").read_text())
    history = run_history(backend)
    context = fixture["spatial_context"]
    crs = ProjectedCRS(context["crs"])
    providers = ProviderRegistry()
    with GeometryProvider(revision="event-fixture-v1") as geometries, ExitStack() as owners:
        for record in [dict(id="center", point=context["center"]),
                       *fixture["signs"], *fixture["events"]]:
            x, y = record["point"]
            geometries.put(EX[record["id"]], f"POINT ({x} {y})", crs=crs)
        geometries.register(providers)
        base = {
            Q.fence: {(EX["center"], Literal(context["radius"]))},
            Q.requestedLane: {(Literal(context["lane"]),)},
            Q.falseValue: {(Literal(False),)},
            Q.sign: {(EX[s["id"]], EX[s["id"]], Literal(s["lane"]),
                      instant(s["valid"][0]), instant(s["valid"][1])) for s in fixture["signs"]},
            Q.stop: {(EX[s["id"]],) for s in fixture["signs"] if s["kind"] == "StopSign"},
        }
        with QueryRuntime((HERE / "queries.dlq").read_text(), backend=backend,
                          providers=providers) as runtime:
            snapshots = []
            for number, case in enumerate(fixture["snapshot_cases"]):
                answer = runtime.evaluate({**base, Q.probe: {(instant(case["at"]),)}},
                                          scope=QueryScope("urn:example:snapshot", str(number)))
                nearby = sorted(str(row[0]).removeprefix(str(EX)) for row in answer.rows(Q.nearbyStop))
                applicable = sorted(str(row[0]).removeprefix(str(EX)) for row in answer.rows(Q.applicableStop))
                assert nearby == case["nearby_stops"]
                assert applicable == case["lane_applicable"]
                snapshots.append(dict(at=case["at"], nearby=nearby, applicable=applicable))

            start = ticks("2026-09-10T08:00:00Z")
            window = window_type(10_000_000, allowed_lateness=30_000_000,
                                 evaluation_time=start, watermark=start,
                                 context=(("map", "event-fixture-v1"),))
            if hasattr(window, "close"):
                owners.callback(window.close)
            events = {row["id"]: Event(row["id"], ticks(row["event_time"]),
                                      EX[row["vehicle"]], (EX[row["id"]],))
                      for row in fixture["events"]}
            for offset, name in enumerate(fixture["window"]["initial_ids"]):
                window.upsert(events[name], source="fixture", offset=offset)

            def evaluate():
                return runtime.evaluate({**base, **window_relations(window)},
                    scope=QueryScope("urn:example:window", str(window.revision)),
                    metadata={"window": "[end-10s,end)", "watermark": window.watermark,
                              "event_time": window.evaluation_time, "provisional": True})

            window.advance(start + 12_000_000, watermark=start)
            initial = evaluate()
            assert {str(row[0]) for row in initial.rows(Q.inside)} == {"inside05", "inside10"}
            assert {str(row[0]) for row in initial.rows(Q.entry)} == {"inside05"}
            window.upsert(events["late03"], source="fixture", offset=3)
            corrected = evaluate()
            assert {str(row[0]) for row in corrected.rows(Q.inside)} == {"inside05", "inside10", "late03"}
            assert {str(row[0]) for row in corrected.rows(Q.entry)} == {"late03"}
            assert corrected.additions[Q.entry] == {(Literal("late03"), EX.vehicle_a)}
            assert corrected.retractions[Q.entry] == {(Literal("inside05"), EX.vehicle_a)}
            restored = window_type.restore(window.checkpoint(), expected_context=window.context)
            if hasattr(restored, "close"):
                owners.callback(restored.close)
            assert restored.rows(include_predecessors=True) == window.rows(include_predecessors=True)
            if hasattr(window, "close"):
                window.close()
            window = restored
            window.advance(start + 15_000_000, watermark=start + 5_000_000)
            later = evaluate()
            assert {str(row[0]) for row in later.rows(Q.inside)} == {"inside05", "inside10"}
            assert not later.rows(Q.entry)  # retained predecessor late03 was already inside
            window.advance(start + 30_000_000, watermark=start + 20_000_000)
            expired = evaluate()
            assert not expired.rows(Q.inside)
            assert len(expired.retractions[Q.inside]) == 2
            report = dict(backend=backend, production_temporal_spatial_rules_executed=True,
                        window_backend="native" if backend == "native" else "python",
                        bitemporal_history=history,
                        geometry_library=geometries.version, snapshots=snapshots,
                        corrected_entry={"remove": ["inside05"], "add": ["late03"]},
                        idle_expiration_verified=True, checkpoint_recovery_verified=True,
                        window=window.info(), execution=runtime.stats)
            if hasattr(window, "close"):
                window.close()
            return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("python", "native", "both"), default="python")
    args = parser.parse_args()
    backends = ("python", "native") if args.backend == "both" else (args.backend,)
    print(json.dumps([run(backend) for backend in backends], indent=2))
