# Native event-window state

`NativeWindowStore` implements the `WindowStore` protocol while retaining event
records in C++ memory. It supports identified deliveries, increasing event
revisions, late corrections/removals, strict source offsets, explicit evaluation
time and watermark, idle expiry, predecessor retention, bounded exports and
checkpoint recovery. The Python implementation remains the reference backend.

```python
from dlp_reasoner.native_windows import NativeWindowStore
from dlp_reasoner.windows import Event

with NativeWindowStore(10_000_000, allowed_lateness=2_000_000,
                       context=(("map", "revision-17"),)) as window:
    window.upsert(Event("e1", 1_000_000, "vehicle-1", (False,)))
    window.upsert(Event("e2", 5_000_000, "vehicle-1", (True,)))
    change = window.advance(6_000_000)
    entered = window.entry_rows(lambda event: event.values[0])
    checkpoint = window.checkpoint()

with NativeWindowStore.restore(checkpoint,
        expected_context=(("map", "revision-17"),)) as restored:
    restored.advance(20_000_000)  # expire active rows even without new events
```

Times/durations are signed 64-bit microseconds. The active window is
`[evaluation_time-width,evaluation_time)`; C++ uses extended precision for the
boundary subtraction. Late-data acceptance uses `watermark-allowed_lateness`.
Time and watermark advance monotonically; there is no implicit wall clock.
The predecessor is the latest retained earlier observation of the same key,
ordered by `(event_time,event_id)`. Missing predecessor remains unknown.
`entry_rows` calls a host-supplied pure predicate on recorded values; Python
callbacks do not execute inside C++. Mobile C callers can consume the same
active/history records and evaluate their compiled predicates independently.

`native_windows.h` is a standalone C ABI. Event IDs, grouping keys and row
payloads are copied byte strings. The C contract uses byte equality and
lexicographic ID ordering. A logical change is identified by `(id,time,key,row)`;
revision-only corrections do not produce duplicate active-row changes. Distinct
IDs with identical payloads remain distinct observations. Every mutation returns
six streams: active and history additions/removals plus retained-record
additions/removals. Exports retain immutable records and remain valid after the
store is changed or closed. Callers must free exports/publications; only eight
can be live per store. One worker serializes native handle operations.

The Python adapter transfers only the incoming event on each update and decodes
the returned changes. It keeps a bounded dictionary of retained **keys**, which
preserves Python hashing/equality, including `True == 1`. It retains no Python
event table. Query methods decode bounded snapshots on demand; returned sets are
independent values. Event IDs and source names must encode as valid UTF-8.
If native publication decoding fails after a successful commit, the adapter
closes the store so a stale key dictionary cannot produce further answers.

Retained records/tombstones, keys, bytes and sources are bounded. Native byte
accounting conservatively charges `(id_bytes+key_bytes+row_bytes)*4+256` per event,
plus context/tombstone/source storage. It differs from the Python reference's
object estimate. Mutations copy bounded maps of shared immutable records for
transactional validation and compute publication differences. They currently
scan retained records; this is native residency with a simple bounded update
algorithm, not a claim of constant-time insertion. Published exports and a
candidate transaction consume additional bounded memory, so choose limits below
the application's overall memory budget.

Native checkpoints use the separate deterministic `DLPWIN01` binary format:
little-endian length-delimited fields and CRC32. CRC detects accidental corruption;
it is not authentication. The reader validates frame lengths, host caps, record
counts, duplicate identities, policies, offsets, retention and context before
publishing a handle. It charges strings and records before allocating retained
storage. Explicit expected context is compared as exact typed wire bytes before
record loading. Reopening under another map/model revision therefore fails.
Python JSON `WindowStore` checkpoints and native checkpoints are distinct formats;
there is currently no automatic cross-format migration.

The default loader lazily compiles `native_windows.cpp` into the external
content-addressed cache. Set `DLP_WINDOWS_LIBRARY=/absolute/path/to/libdlp_native`
with the platform suffix to use the aggregate precompiled library without a
compiler. The CMake/mobile distribution installs `native_windows.h` and includes
the implementation. No new third-party window library is required.

Validation includes the existing reference scenarios on the native adapter,
350 seeded mixed updates with periodic checkpoint/resume, direct ABI identity
regressions, signed-clock boundaries, export lifetimes, corruption/cap failures,
and a standalone C++ smoke run under AddressSanitizer/UndefinedBehaviorSanitizer.
Run `.venv/bin/python -m pytest -q tests/test_windows.py tests/test_native_windows.py`
and `mobile/smoke_host.sh tmp/mobile-host` from the repository root.
