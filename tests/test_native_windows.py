from dataclasses import replace
import ctypes as c
import random
import struct
import zlib

import pytest

from dlp_reasoner.native_windows import NativeWindowStore, _Config, _Event, _check, _input, _library, _output
from dlp_reasoner.windows import Event, ReplayGapError, WindowError, WindowResourceError, WindowStore


@pytest.mark.parametrize("test_name", [
    "test_half_open_boundaries_and_idle_expiry",
    "test_distinct_ids_duplicate_delivery_and_revised_correction",
    "test_late_correction_retracts_invented_entry_and_adds_true_entry",
    "test_expired_outside_predecessor_is_retained_and_missing_is_unknown",
    "test_equal_timestamp_order_and_key_isolation",
    "test_lateness_boundary_and_monotonic_clocks_transactional",
    "test_remove_tombstone_retry_and_reinsert_new_revision",
    "test_capacity_and_byte_limits_are_transactional",
    "test_forget_key_resets_predecessor_knowledge_explicitly",
    "test_source_offsets_gap_replay_and_checkpoint",
    "test_suspend_resume_matches_uninterrupted_rows_changes_and_entries",
])
def test_existing_window_contract_on_native_store(monkeypatch, test_name):
    import test_windows
    monkeypatch.setattr(test_windows, "WindowStore", NativeWindowStore)
    getattr(test_windows, test_name)()


def assert_same(native, reference):
    assert native.rows() == reference.rows()
    assert native.rows(include_predecessors=True) == reference.rows(include_predecessors=True)
    assert native.entry_rows(lambda e: e.values[0]) == reference.entry_rows(lambda e: e.values[0])
    assert native.revision == reference.revision
    assert native.offsets == reference.offsets
    left, right = native.info(), reference.info()
    for key in left.keys() - {"bytes"}:
        assert left[key] == right[key]


def test_seeded_differential_updates_corrections_removals_and_resume():
    rng = random.Random(49281)
    reference = WindowStore(20, allowed_lateness=35)
    native = NativeWindowStore(20, allowed_lateness=35)
    records = {}
    try:
        for step in range(350):
            choice = rng.randrange(5)
            if choice == 0:
                args = (reference.evaluation_time + rng.randrange(5),)
                method, options = "advance", {}
            elif choice == 1 and records:
                identity = rng.choice(list(records))
                method, args, options = "remove", (identity,), {"revision": records[identity].revision + 1}
            else:
                identity = str(rng.randrange(30))
                revision = records[identity].revision + 1 if identity in records else 0
                event = Event(identity, reference.evaluation_time + rng.randrange(-40, 15),
                              rng.choice(("a", "b", "c")), (bool(rng.randrange(2)),), revision)
                records[identity] = event
                method, args, options = "upsert", (event,), {}
            outcomes = []
            for store in (reference, native):
                try:
                    outcomes.append(getattr(store, method)(*args, **options))
                except WindowError as error:
                    outcomes.append(type(error))
            assert outcomes[0] == outcomes[1], (step, method, outcomes)
            assert_same(native, reference)
            if step % 25 == 0:
                restored = NativeWindowStore.restore(native.checkpoint())
                native.close()
                native = restored
    finally:
        native.close()


def test_python_numeric_key_and_row_equality_preserved_and_key_mirror_bounded():
    reference = WindowStore(10, allowed_lateness=20)
    with NativeWindowStore(10, allowed_lateness=20) as native:
        for event in (Event("a", 0, 1, (False,)), Event("b", 5, True, (True,))):
            assert reference.upsert(event) == native.upsert(event)
        assert reference.advance(10) == native.advance(10)
        assert_same(native, reference)
        duplicate = Event("a", 0, True, (0,))
        assert reference.upsert(duplicate) == native.upsert(duplicate)
        corrected = replace(duplicate, revision=1)
        assert reference.upsert(corrected) == native.upsert(corrected)
        assert_same(native, reference)
        assert len(native._keys) == 1
        with NativeWindowStore.restore(native.checkpoint()) as resumed:
            assert resumed.entry_rows(lambda e: e.values[0]) == reference.entry_rows(lambda e: e.values[0])
        native.forget_key(1)
        assert not native._keys and not native._counts


def test_native_checkpoint_corruption_caps_and_strict_framing():
    with NativeWindowStore(10, max_events=100, max_bytes=2000) as store:
        store.upsert(Event("a", 0, "car", (True,)))
        data = store.checkpoint()
        assert data.startswith(b"DLPWIN01")
        for payload in (data[:-1], data + b"x", b"X" + data[1:], data[:20] + b"wrong" + data[25:]):
            with pytest.raises(WindowError):
                NativeWindowStore.restore(payload)
        with pytest.raises(WindowResourceError):
            NativeWindowStore.restore(data, max_checkpoint_bytes=1)
        with pytest.raises(WindowResourceError):
            NativeWindowStore.restore(data, max_events=99)
        # Valid checksum does not authorize an excessive retained-state budget.
        bad = bytearray(data[:-4])
        struct.pack_into("<Q", bad, 8 + 5 * 8, 1 << 62)  # max_bytes
        bad.extend(struct.pack("<I", zlib.crc32(bad)))
        with pytest.raises(WindowResourceError):
            NativeWindowStore.restore(bytes(bad))
        with pytest.raises(ReplayGapError):
            NativeWindowStore.restore(data, expected_context=(("map", "different"),))


def test_int64_boundary_clock_arithmetic_and_closed_owner():
    minimum, maximum = -(1 << 63), (1 << 63) - 1
    with NativeWindowStore(maximum, evaluation_time=minimum, allowed_lateness=maximum) as native:
        native.upsert(Event("a", minimum, "car", (False,)))
        native.advance(minimum + 1)
        assert len(native.rows()) == 1
        native.advance(maximum)
        assert not native.rows()
        assert len(native.rows(include_predecessors=True)) == 1
        assert native.info()["events"] == 1
    native.close()
    with pytest.raises(WindowError, match="closed"):
        native.rows()


def test_raw_abi_distinct_ids_and_time_correction_with_equal_opaque_payload():
    lib = _library()
    cfg = _Config(10, 20, 10, 10, 100, 10000, 10, 1, 0)
    handle = c.c_void_p()
    _check(lib, lib.dlp_windows_new(c.byref(cfg), _input(b"opaque-host-v1"), c.byref(handle)))
    try:
        for identity, time, revision in ((b"a", 1, 0), (b"b", 1, 0), (b"a", 2, 1)):
            event = _Event(_input(identity), _input(b"key"), _input(b"same-payload"), time, revision)
            change = c.c_void_p()
            _check(lib, lib.dlp_windows_upsert(handle, c.byref(event), _input(b""), -1, c.byref(change)))
            try:
                output, count, done = (_Event * 4)(), c.c_size_t(), c.c_int()
                _check(lib, lib.dlp_windows_change_next(change, 0, output, 4, c.byref(count), c.byref(done)))
                assert count.value == 1 and _output(output[0].id) == identity and output[0].time == time
                _check(lib, lib.dlp_windows_change_next(change, 1, output, 4, c.byref(count), c.byref(done)))
                assert count.value == (1 if revision else 0)
            finally:
                lib.dlp_windows_change_free(change)
    finally:
        lib.dlp_windows_free(handle)


def test_raw_exports_are_bounded_and_outlive_store():
    lib, handle = _library(), c.c_void_p()
    cfg = _Config(10, 10, 0, 0, 100, 10000, 10, 1, 0)
    _check(lib, lib.dlp_windows_new(c.byref(cfg), _input(b""), c.byref(handle)))
    exports = []
    try:
        for _ in range(8):
            cursor = c.c_void_p()
            _check(lib, lib.dlp_windows_rows(handle, 0, c.byref(cursor)))
            exports.append(cursor)
        cursor = c.c_void_p()
        with pytest.raises(WindowResourceError):
            _check(lib, lib.dlp_windows_rows(handle, 0, c.byref(cursor)))
        lib.dlp_windows_free(handle)
        handle = None
        rows, count, done = (_Event * 1)(), c.c_size_t(), c.c_int()
        _check(lib, lib.dlp_windows_next(exports[0], rows, 1, c.byref(count), c.byref(done)))
        assert done.value and not count.value
    finally:
        if handle:
            lib.dlp_windows_free(handle)
        for cursor in exports:
            lib.dlp_windows_rows_free(cursor)


def test_precompiled_window_path_never_compiles(monkeypatch):
    from dlp_reasoner import native_windows
    path = native_windows.build_native_windows()
    monkeypatch.setenv("DLP_WINDOWS_LIBRARY", str(path))
    monkeypatch.setattr(native_windows, "build_native_windows", lambda: pytest.fail("Unexpected compiler"))
    with NativeWindowStore(10) as store:
        assert store.info()["events"] == 0
