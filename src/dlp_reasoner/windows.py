"""Finite event-time windows with explicit clocks, corrections and recovery.

Mutation is serialized by the owning runtime. Each operation returns its change
publication; no unbounded event/change log or implicit wall clock is retained.
"""

from dataclasses import dataclass
import hashlib
import json

from .providers import _decode, _encode, _packed


class WindowError(ValueError):
    pass


class LateEventError(WindowError):
    pass


class WindowResourceError(WindowError):
    pass


class EventRevisionError(WindowError):
    pass


class ReplayGapError(WindowError):
    pass


def _integer(value, name, *, minimum=-(1 << 63)):
    if type(value) is not int or not minimum <= value < 1 << 63:
        raise WindowError(f"{name} must be a bounded integer >= {minimum}")
    return value


@dataclass(frozen=True)
class Event:
    event_id: str
    event_time: int
    key: object
    values: tuple = ()
    revision: int = 0

    def __post_init__(self):
        if type(self.event_id) is not str or not self.event_id:
            raise WindowError("Event identity must be a nonempty string")
        _integer(self.event_time, "event_time")
        _integer(self.revision, "event revision", minimum=0)
        if type(self.values) is not tuple:
            raise WindowError("Event values must be an immutable tuple")
        _packed((self.key, self.values))
        hash(self.key)

    @property
    def row(self):
        return self.event_id, self.event_time, self.key, *self.values


@dataclass(frozen=True)
class WindowChange:
    revision: int
    added: frozenset = frozenset()
    removed: frozenset = frozenset()
    history_added: frozenset = frozenset()
    history_removed: frozenset = frozenset()


class WindowStore:
    def __init__(self, width, *, allowed_lateness=0, max_events=10000,
                 max_bytes=16 * 1024 * 1024, max_keys=1000,
                 evaluation_time=0, watermark=None, retain_predecessor=True, context=(),
                 allow_offset_gaps=False):
        self.width = _integer(width, "width", minimum=1)
        self.allowed_lateness = _integer(allowed_lateness, "allowed_lateness", minimum=0)
        self.max_events = _integer(max_events, "max_events", minimum=1)
        self.max_bytes = _integer(max_bytes, "max_bytes", minimum=1)
        self.max_keys = _integer(max_keys, "max_keys", minimum=1)
        self.evaluation_time = _integer(evaluation_time, "evaluation_time")
        self.watermark = self.evaluation_time if watermark is None else _integer(watermark, "watermark")
        if self.watermark > self.evaluation_time:
            raise WindowError("Watermark must not exceed evaluation time")
        if (type(retain_predecessor) is not bool or type(context) is not tuple
                or type(allow_offset_gaps) is not bool):
            raise WindowError("Invalid predecessor policy or context")
        size = len(_packed(context)) * 4
        if size > self.max_bytes:
            raise WindowResourceError("Window context exceeds byte limit")
        self.retain_predecessor, self.context = retain_predecessor, context
        self.allow_offset_gaps = allow_offset_gaps
        self.revision = 0
        self._events = {}
        self._tombstones = {}  # event ID -> (latest removed revision, old event time)
        self._offsets = {}
        self._bytes = size

    @property
    def offsets(self):
        return dict(self._offsets)

    def info(self):
        return dict(revision=self.revision, events=len(self._events),
                    tombstones=len(self._tombstones), bytes=self._bytes,
                    evaluation_time=self.evaluation_time, watermark=self.watermark,
                    context=self.context, offsets=self.offsets)

    def _selected(self, events, end, include_predecessors=False):
        start = end - self.width
        selected = {event.row for event in events.values() if start <= event.event_time < end}
        if include_predecessors and self.retain_predecessor:
            previous = {}
            for event in events.values():
                if event.event_time < start:
                    old = previous.get(event.key)
                    if old is None or (event.event_time, event.event_id) > (old.event_time, old.event_id):
                        previous[event.key] = event
            selected.update(event.row for event in previous.values())
        return frozenset(selected)

    def rows(self, *, include_predecessors=False):
        return self._selected(self._events, self.evaluation_time, include_predecessors)

    def predecessor(self, event_id):
        target = self._events[event_id]
        prior = [event for event in self._events.values()
                 if event.key == target.key
                 and (event.event_time, event.event_id) < (target.event_time, target.event_id)]
        return max(prior, key=lambda event: (event.event_time, event.event_id), default=None)

    def entry_rows(self, predicate):
        """Observed false→true transitions for events inside the active window.

        predicate(Event) must be a pure function of the recorded values. Missing
        predecessor means unknown, not outside. Equal times use event ID order.
        """
        active = self.rows()
        result = set()
        for event in self._events.values():
            if event.row in active:
                previous = self.predecessor(event.event_id)
                if previous is not None and predicate(event) and not predicate(previous):
                    result.add(event.row)
        return frozenset(result)

    def _commit(self, events, tombstones, end, watermark, offsets):
        start = end - self.width
        cutoff = min(start, watermark - self.allowed_lateness)
        retained = {identity: event for identity, event in events.items() if event.event_time >= cutoff}
        if self.retain_predecessor:
            previous = {}
            for event in events.values():
                if event.event_time < start:
                    old = previous.get(event.key)
                    if old is None or (event.event_time, event.event_id) > (old.event_time, old.event_id):
                        previous[event.key] = event
            retained.update((event.event_id, event) for event in previous.values())
        tombstones = {identity: value for identity, value in tombstones.items() if value[1] >= cutoff}
        if len(retained) + len(tombstones) > self.max_events:
            raise WindowResourceError("Window event/tombstone capacity exceeded")
        if len({event.key for event in retained.values()}) > self.max_keys:
            raise WindowResourceError("Window key/predecessor capacity exceeded")
        size = sum(len(_packed((event.row, event.revision))) * 4 + 256 for event in retained.values())
        size += sum(len(identity.encode()) * 4 + 128 for identity in tombstones)
        size += len(_packed(self.context)) * 4 + sum(len(key.encode()) * 4 + 128 for key in offsets)
        if size > self.max_bytes or len(offsets) > 128:
            raise WindowResourceError("Window retained byte/source capacity exceeded")
        old_rows = self.rows()
        old_history = self.rows(include_predecessors=True)
        new_rows = self._selected(retained, end)
        new_history = self._selected(retained, end, True)
        changed = (retained != self._events or tombstones != self._tombstones
                   or end != self.evaluation_time or watermark != self.watermark
                   or offsets != self._offsets)
        self._events, self._tombstones, self._offsets = retained, tombstones, offsets
        self.evaluation_time, self.watermark, self._bytes = end, watermark, size
        if changed:
            self.revision += 1
        return WindowChange(self.revision, new_rows - old_rows, old_rows - new_rows,
                            new_history - old_history, old_history - new_history)

    def upsert(self, event, *, source=None, offset=None):
        if not isinstance(event, Event):
            raise WindowError("Expected Event")
        old = self._events.get(event.event_id)
        tombstone = self._tombstones.get(event.event_id)
        if (source is None) != (offset is None):
            raise WindowError("Source and offset must be supplied together")
        offsets = dict(self._offsets)
        if source is not None:
            if type(source) is not str or not source:
                raise WindowError("Source must be a nonempty string")
            _integer(offset, "offset", minimum=0)
            if offset <= offsets.get(source, -1):
                if old == event:
                    return WindowChange(self.revision)
                raise ReplayGapError("Offset replay differs from retained accepted event")
            if source in offsets and not self.allow_offset_gaps and offset != offsets[source] + 1:
                raise ReplayGapError("Source offset gap; missing accepted input must be recovered")
            offsets[source] = offset
        if old == event:
            return self._commit(dict(self._events), dict(self._tombstones),
                                self.evaluation_time, self.watermark, offsets)
        previous_revision = old.revision if old else tombstone[0] if tombstone else -1
        if event.revision <= previous_revision:
            raise EventRevisionError("Changed event must have a strictly greater revision")
        if min(event.event_time, old.event_time if old else event.event_time) < self.watermark - self.allowed_lateness:
            raise LateEventError("Event/correction is older than the accepted lateness boundary")
        events, tombstones = dict(self._events), dict(self._tombstones)
        events[event.event_id] = event
        tombstones.pop(event.event_id, None)
        return self._commit(events, tombstones, self.evaluation_time, self.watermark, offsets)

    def remove(self, event_id, *, revision):
        _integer(revision, "removal revision", minimum=0)
        old = self._events.get(event_id)
        tombstone = self._tombstones.get(event_id)
        if tombstone is not None and revision == tombstone[0]:
            return WindowChange(self.revision)
        if old is None:
            raise ReplayGapError("Cannot remove an unknown/forgotten event")
        if revision <= old.revision:
            raise EventRevisionError("Removal must have a strictly greater revision")
        if old.event_time < self.watermark - self.allowed_lateness:
            raise LateEventError("Removal is older than the accepted lateness boundary")
        events, tombstones = dict(self._events), dict(self._tombstones)
        del events[event_id]
        tombstones[event_id] = revision, old.event_time
        return self._commit(events, tombstones, self.evaluation_time, self.watermark, dict(self._offsets))

    def advance(self, end, *, watermark=None):
        end = _integer(end, "evaluation time")
        watermark = end if watermark is None else _integer(watermark, "watermark")
        if end < self.evaluation_time or watermark < self.watermark or watermark > end:
            raise WindowError("Evaluation time/watermark must advance monotonically, watermark <= end")
        return self._commit(dict(self._events), dict(self._tombstones), end, watermark, dict(self._offsets))

    def forget_key(self, key):
        """Explicitly release a key's history; its next event has unknown predecessor."""
        identities = {identity for identity, event in self._events.items() if event.key == key}
        events = {identity: event for identity, event in self._events.items() if identity not in identities}
        return self._commit(events, dict(self._tombstones), self.evaluation_time,
                            self.watermark, dict(self._offsets))

    def checkpoint(self):
        data = {
            "format": "dlp-window-v1", "width": self.width, "allowed_lateness": self.allowed_lateness,
            "max_events": self.max_events, "max_bytes": self.max_bytes, "max_keys": self.max_keys,
            "evaluation_time": self.evaluation_time, "watermark": self.watermark,
            "retain_predecessor": self.retain_predecessor, "context": _encode(self.context),
            "allow_offset_gaps": self.allow_offset_gaps,
            "revision": self.revision, "offsets": self._offsets,
            "events": [[event.event_id, event.event_time, _encode(event.key), _encode(event.values),
                        event.revision] for event in sorted(self._events.values(), key=lambda e: e.event_id)],
            "tombstones": self._tombstones,
        }
        payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
        return json.dumps({"sha256": hashlib.sha256(payload).hexdigest(), "payload": payload.decode()},
                          sort_keys=True, separators=(",", ":")).encode()

    @classmethod
    def restore(cls, checkpoint, *, max_checkpoint_bytes=64 * 1024 * 1024, expected_context=None,
                max_events=10000, max_bytes=16 * 1024 * 1024, max_keys=1000):
        if type(checkpoint) is not bytes or len(checkpoint) > max_checkpoint_bytes:
            raise WindowResourceError("Invalid or oversized window checkpoint")
        try:
            envelope = json.loads(checkpoint)
            payload = envelope["payload"].encode()
            if envelope["sha256"] != hashlib.sha256(payload).hexdigest():
                raise WindowError("Checkpoint checksum mismatch")
            data = json.loads(payload)
            if data.pop("format") != "dlp-window-v1":
                raise WindowError("Unsupported window checkpoint format")
            events, tombstones = data.pop("events"), data.pop("tombstones")
            revision, offsets = data.pop("revision"), data.pop("offsets")
            for name, limit in (("max_events", max_events), ("max_bytes", max_bytes), ("max_keys", max_keys)):
                _integer(limit, f"restore {name}", minimum=1)
                if data[name] > limit:
                    raise WindowResourceError(f"Checkpoint exceeds host {name} limit")
            if len(events) + len(tombstones) > max_events:
                raise WindowResourceError("Checkpoint record limit exceeded")
            data["context"] = _decode(data["context"])
            if expected_context is not None and data["context"] != expected_context:
                raise ReplayGapError("Checkpoint static-data context does not match")
            store = cls(**data)
            _integer(revision, "stored revision", minimum=0)
            records = [Event(identity, at, _decode(key), _decode(values), rev)
                       for identity, at, key, values, rev in events]
            if len({event.event_id for event in records}) != len(records):
                raise WindowError("Duplicate checkpoint event IDs")
            if any(type(key) is not str or not key for key in offsets):
                raise WindowError("Invalid checkpoint source")
            for value in offsets.values():
                _integer(value, "stored offset", minimum=0)
            for identity, (rev, at) in tombstones.items():
                if type(identity) is not str or not identity:
                    raise WindowError("Invalid tombstone identity")
                _integer(rev, "stored removal revision", minimum=0)
                _integer(at, "stored removal time")
            if set(tombstones) & {event.event_id for event in records}:
                raise WindowError("Checkpoint has both event and tombstone")
            store._commit({e.event_id: e for e in records},
                          {key: tuple(value) for key, value in tombstones.items()},
                          store.evaluation_time, store.watermark, dict(offsets))
            if len(store._events) != len(records) or len(store._tombstones) != len(tombstones):
                raise WindowError("Checkpoint contains records outside retention policy")
            store.revision = revision
            return store
        except WindowError:
            raise
        except (ValueError, TypeError, KeyError, IndexError, OverflowError, RecursionError) as exc:
            raise WindowError(f"Malformed window checkpoint: {exc}") from exc
