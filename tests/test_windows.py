from dataclasses import replace
import hashlib
import json

import pytest
from rdflib import URIRef

from dlp_reasoner.domains import Point
from dlp_reasoner.windows import (
    Event, EventRevisionError, LateEventError, ReplayGapError, WindowError,
    WindowResourceError, WindowStore,
)


def test_half_open_boundaries_and_idle_expiry():
    store = WindowStore(10, allowed_lateness=20)
    events = [Event(f"e{time}", time, "vehicle", (time,)) for time in (0, 5, 10)]
    for event in events:
        store.upsert(event)
    change = store.advance(10)
    assert change.added == {events[0].row, events[1].row}
    assert events[2].row not in store.rows()
    change = store.advance(15)
    assert change.removed == {events[0].row}
    assert change.added == {events[2].row}
    change = store.advance(30)
    assert change.removed == {events[1].row, events[2].row}
    assert store.rows() == frozenset()
    assert store.rows(include_predecessors=True) == {events[2].row}


def test_distinct_ids_duplicate_delivery_and_revised_correction():
    store = WindowStore(10, allowed_lateness=20)
    first = Event("a", 5, "car", (False,))
    same_values = Event("b", 5, "car", (False,))
    store.upsert(first)
    revision = store.revision
    assert store.upsert(first).revision == revision
    store.upsert(same_values)
    store.advance(10)
    assert len(store.rows()) == 2
    corrected = replace(first, values=(True,), revision=1)
    change = store.upsert(corrected)
    assert change.added == {corrected.row} and change.removed == {first.row}
    with pytest.raises(EventRevisionError):
        store.upsert(first)
    with pytest.raises(EventRevisionError):
        store.upsert(replace(corrected, values=(False,)))


def test_late_correction_retracts_invented_entry_and_adds_true_entry():
    store = WindowStore(10, allowed_lateness=20)
    outside = Event("outside", 0, "car", (False,))
    late_inside = Event("late", 3, "car", (True,))
    inside = Event("inside", 5, "car", (True,))
    store.upsert(outside)
    store.upsert(inside)
    store.advance(10)
    before = store.entry_rows(lambda event: event.values[0])
    assert before == {inside.row}
    change = store.upsert(late_inside)
    after = store.entry_rows(lambda event: event.values[0])
    assert change.added == {late_inside.row}
    assert before - after == {inside.row} and after - before == {late_inside.row}
    store.advance(14)
    assert outside.row not in store.rows(include_predecessors=True)
    assert late_inside.row in store.rows(include_predecessors=True)
    assert store.entry_rows(lambda event: event.values[0]) == set()


def test_expired_outside_predecessor_is_retained_and_missing_is_unknown():
    store = WindowStore(10, allowed_lateness=100)
    outside = Event("old", 0, "car", (False,))
    inside = Event("new", 20, "car", (True,))
    lone = Event("lone", 20, "another", (True,))
    for event in (outside, inside, lone):
        store.upsert(event)
    store.advance(25)
    assert store.predecessor("new") == outside
    assert store.entry_rows(lambda event: event.values[0]) == {inside.row}
    store.advance(200)
    assert store.info()["events"] == 2
    future = Event("future", 205, "car", (True,))
    store.upsert(future)
    store.advance(210)
    assert store.entry_rows(lambda event: event.values[0]) == set()


def test_equal_timestamp_order_and_key_isolation():
    store = WindowStore(10, allowed_lateness=20)
    for event in (Event("z", 5, "a", (True,)), Event("a", 5, "a", (False,)),
                  Event("b", 4, "b", (False,))):
        store.upsert(event)
    store.advance(10)
    assert {row[0] for row in store.entry_rows(lambda event: event.values[0])} == {"z"}


def test_lateness_boundary_and_monotonic_clocks_transactional():
    store = WindowStore(10, allowed_lateness=5)
    store.advance(20)
    store.upsert(Event("boundary", 15, "car"))
    snapshot = store.checkpoint()
    with pytest.raises(LateEventError):
        store.upsert(Event("old", 14, "car"))
    for end, watermark in ((19, 19), (25, 19), (25, 26)):
        with pytest.raises(WindowError):
            store.advance(end, watermark=watermark)
    assert store.checkpoint() == snapshot


def test_remove_tombstone_retry_and_reinsert_new_revision():
    store = WindowStore(10, allowed_lateness=20)
    event = Event("a", 5, "car")
    store.upsert(event)
    store.advance(10)
    assert store.remove("a", revision=1).removed == {event.row}
    revision = store.revision
    assert store.remove("a", revision=1).revision == revision
    with pytest.raises(EventRevisionError):
        store.upsert(event)
    replacement = replace(event, revision=2)
    assert store.upsert(replacement).added == {event.row}
    with pytest.raises(ReplayGapError):
        store.remove("missing", revision=1)


def test_capacity_and_byte_limits_are_transactional():
    store = WindowStore(10, allowed_lateness=20, max_events=2, max_keys=1)
    store.upsert(Event("a", 1, "one"))
    before = store.checkpoint()
    with pytest.raises(WindowResourceError):
        store.upsert(Event("b", 2, "two"))
    assert store.checkpoint() == before
    store.upsert(Event("b", 2, "one"))
    before = store.checkpoint()
    with pytest.raises(WindowResourceError):
        store.upsert(Event("c", 3, "one"))
    assert store.checkpoint() == before
    store = WindowStore(10, max_bytes=1024)
    before = store.checkpoint()
    with pytest.raises(WindowResourceError):
        store.upsert(Event("big", 1, "a", ("x" * 1000,)))
    assert store.checkpoint() == before


def test_forget_key_resets_predecessor_knowledge_explicitly():
    store = WindowStore(10, allowed_lateness=100)
    store.upsert(Event("a", 0, "car", (False,)))
    store.advance(30)
    assert store.rows(include_predecessors=True)
    assert store.forget_key("car").history_removed
    store.upsert(Event("b", 31, "car", (True,)))
    store.advance(35)
    assert store.entry_rows(lambda event: event.values[0]) == set()


def test_source_offsets_gap_replay_and_checkpoint():
    store = WindowStore(10, allowed_lateness=20)
    a, b = Event("a", 1, "car"), Event("b", 2, "car")
    store.upsert(a, source="partition0", offset=40)
    before = store.checkpoint()
    with pytest.raises(ReplayGapError):
        store.upsert(b, source="partition0", offset=42)
    assert store.checkpoint() == before
    store.upsert(b, source="partition0", offset=41)
    assert store.upsert(a, source="partition0", offset=40).revision == store.revision
    assert store.offsets == {"partition0": 41}
    restored = WindowStore.restore(store.checkpoint())
    assert restored.offsets == store.offsets
    with pytest.raises(ReplayGapError):
        restored.upsert(replace(a, values=(1,), revision=1), source="partition0", offset=40)
    gaps = WindowStore(10, allow_offset_gaps=True)
    gaps.upsert(a, source="filtered", offset=40)
    gaps.upsert(b, source="filtered", offset=90)
    assert WindowStore.restore(gaps.checkpoint()).allow_offset_gaps


def test_suspend_resume_matches_uninterrupted_rows_changes_and_entries():
    store = WindowStore(10, allowed_lateness=20, context=(("map", "v1"),))
    store.upsert(Event("a", 0, URIRef("urn:car"), (Point(8.4, 49.0), False)))
    store.upsert(Event("b", 5, URIRef("urn:car"), (Point(8.4, 49.1), True)))
    store.advance(10)
    payload = store.checkpoint()
    resumed = WindowStore.restore(payload, expected_context=(("map", "v1"),))
    assert resumed.checkpoint() == payload
    correction = Event("late", 3, URIRef("urn:car"), (Point(8.4, 49.05), True))
    assert store.upsert(correction) == resumed.upsert(correction)
    assert store.advance(15) == resumed.advance(15)
    assert store.entry_rows(lambda event: event.values[1]) == resumed.entry_rows(lambda event: event.values[1])
    assert store.checkpoint() == resumed.checkpoint()
    with pytest.raises(ReplayGapError):
        WindowStore.restore(payload, expected_context=(("map", "v2"),))


def corrupt(payload, mutation):
    envelope = json.loads(payload)
    data = json.loads(envelope["payload"])
    mutation(data)
    envelope["payload"] = json.dumps(data, sort_keys=True, separators=(",", ":"))
    envelope["sha256"] = hashlib.sha256(envelope["payload"].encode()).hexdigest()
    return json.dumps(envelope).encode()


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(format="unknown"), lambda d: d.update(width=0),
    lambda d: d.update(revision=-1), lambda d: d["events"].append(d["events"][0]),
    lambda d: d.update(context=["bool", "false"]),
    lambda d: d.update(offsets={"source": -1}),
    lambda d: d.update(watermark=d["evaluation_time"] + 1),
    lambda d: d.update(tombstones={"a": [1, 0]}),
])
def test_checkpoint_rejects_invalid_or_incompatible_payload(mutation):
    store = WindowStore(10)
    store.upsert(Event("a", 1, "car"))
    with pytest.raises(WindowError):
        WindowStore.restore(corrupt(store.checkpoint(), mutation))


def test_checkpoint_truncation_and_size_limits():
    payload = WindowStore(10).checkpoint()
    with pytest.raises(WindowError):
        WindowStore.restore(payload[:-1])
    with pytest.raises(WindowResourceError):
        WindowStore.restore(payload, max_checkpoint_bytes=1)
    with pytest.raises(WindowResourceError):
        WindowStore.restore(corrupt(payload, lambda d: d.update(max_events=10001)))


@pytest.mark.parametrize("arguments", [("", 0, "car"), ("a", True, "car"),
                                       ("a", 0, []), ("a", 0, "car", []),
                                       ("a", 0, "car", (float("nan"),))])
def test_events_reject_mutable_or_invalid_values(arguments):
    with pytest.raises((ValueError, TypeError)):
        Event(*arguments)
