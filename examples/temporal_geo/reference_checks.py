"""Check synthetic spatial/temporal expectations; does not invoke the DLP engine.

Only axis-aligned rectangles and projected Euclidean points are modeled here.
The finite event list is replayed directly: this is not a stream processor.
"""

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
import json
from math import dist, isclose
from pathlib import Path


def instant(value):
    """Read the offset-bearing, microsecond-resolution subset used by fixtures."""
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.utcoffset() is None:
        raise ValueError("A timezone offset is required")
    return result


def contains(interval, at):
    """Closed-open interval; null end denotes no upper bound."""
    start, end = interval
    return instant(start) <= at and (end is None or at < instant(end))


def nearby_stops(data, at, lane=None):
    context = data["spatial_context"]
    return sorted(
        sign["id"] for sign in data["signs"]
        if sign["kind"] == "StopSign"
        and contains(sign["valid"], at)
        and dist(context["center"], sign["point"]) <= context["radius"]
        and (lane is None or sign["lane"] == lane)
    )


def selected_events(data, identifiers):
    """Retries of an accepted ID do not create another observation."""
    by_id = {event["id"]: event for event in data["events"]}
    if len(by_id) != len(data["events"]):
        raise ValueError("Fixture event IDs must be unique")
    return [by_id[identifier] for identifier in set(identifiers)]


def window_members(data, identifiers, end):
    start = end - timedelta(seconds=data["window"]["width_seconds"])
    return sorted(
        event["id"] for event in selected_events(data, identifiers)
        if start <= instant(event["event_time"]) < end
    )


def entries(data, identifiers):
    """Observed entries require a known predecessor, including before a window."""
    context = data["spatial_context"]
    trajectories = defaultdict(list)
    for event in selected_events(data, identifiers):
        trajectories[event["vehicle"]].append(event)
    result = []
    for trajectory in trajectories.values():
        trajectory.sort(key=lambda event: (instant(event["event_time"]), event["id"]))
        previous_inside = None
        for event in trajectory:
            inside = dist(context["center"], event["point"]) <= context["radius"]
            if inside and previous_inside is False:
                result.append(event["id"])
            previous_inside = inside
    return sorted(result)


def check(data):
    checks = 0

    def equal(actual, expected, label):
        nonlocal checks
        if actual != expected:
            raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")
        checks += 1

    context = data["spatial_context"]
    for sign in data["signs"]:
        equal(isclose(dist(context["center"], sign["point"]), sign["distance"],
                      rel_tol=0, abs_tol=1e-8), True, f"distance/{sign['id']}")
    for case in data["snapshot_cases"]:
        at = instant(case["at"])
        equal(nearby_stops(data, at), case["nearby_stops"], f"nearby/{case['at']}")
        equal(nearby_stops(data, at, context["lane"]), case["lane_applicable"],
              f"lane/{case['at']}")

    topology = data["topology"]
    low, high = topology["rectangle_min"], topology["rectangle_max"]
    for case in topology["points"]:
        point = case["point"]
        strict = all(a < x < b for a, x, b in zip(low, point, high))
        inclusive = all(a <= x <= b for a, x, b in zip(low, point, high))
        equal(strict, case["contains"], f"rectangle-contains/{case['id']}")
        equal(inclusive, case["covers"], f"rectangle-covers/{case['id']}")

    adjacent = data["adjacent_intervals"]
    a, b = map(instant, adjacent["first"])
    c, d = map(instant, adjacent["second"])
    equal(b == c, adjacent["meets"], "interval-meets")
    equal(max(a, c) < min(b, d), adjacent["intersects"], "interval-intersects")
    for which in ("first", "second"):
        equal(contains(adjacent[which], instant(adjacent["probe"])),
              adjacent[f"{which}_contains_probe"], f"interval-contains/{which}")

    for case in data["bitemporal_cases"]:
        speeds = sorted(
            version["kmh"] for version in data["speed_versions"]
            if contains(version["valid"], instant(case["valid_at"]))
            and contains(version["recorded"], instant(case["recorded_at"]))
        )
        equal(speeds, case["kmh"], f"bitemporal/{case['recorded_at']}")

    window = data["window"]
    for case in window["cases"]:
        members = window_members(data, window[case["accepted"]], instant(case["end"]))
        equal(members, case["members"], f"window-members/{case['accepted']}/{case['end']}")
        equal(len(members), case["count"], f"window-count/{case['accepted']}/{case['end']}")
    repeated = window["corrected_ids"] + ["inside05"]
    equal(window_members(data, repeated, instant(window["cases"][1]["end"])),
          window["cases"][1]["members"], "duplicate-delivery")
    at_end = instant("2026-09-10T08:00:10Z")
    equal(window_members(data, window["initial_ids"], at_end),
          ["inside05", "outside00"], "window-right-end-exclusive")

    initial = entries(data, window["initial_ids"])
    corrected = entries(data, window["corrected_ids"])
    equal(initial, data["entry"]["initial_entries"], "initial-entry")
    equal(corrected, data["entry"]["corrected_entries"], "corrected-entry")
    equal(sorted(set(initial) - set(corrected)), data["entry"]["retract"], "entry-retract")
    equal(sorted(set(corrected) - set(initial)), data["entry"]["add"], "entry-add")
    # A window containing only inside samples cannot prove a new entry at its start.
    equal(entries(data, window["cases"][2]["members"]), [], "no-invented-predecessor")
    equal(entries(data, window["cases"][1]["members"]), [], "missing-outside-predecessor")

    arithmetic = data["arithmetic"]
    kmh = (Decimal(str(arithmetic["distance_metres"]))
           / Decimal(str(arithmetic["elapsed_seconds"])) * Decimal("3.6"))
    equal(kmh, Decimal(str(arithmetic["expected_kmh"])), "speed-arithmetic")
    equal(instant("2026-09-10T10:30:00+02:00"),
          instant("2026-09-10T08:30:00Z"), "offset-value-equality")
    return checks


if __name__ == "__main__":
    fixtures = json.loads(Path(__file__).with_name("fixtures.json").read_text())
    count = check(fixtures)
    print(f"PASS: {count} synthetic reference checks; DLP engine not invoked")
