# Temporal and geographic design fixtures

These are **synthetic reference examples for a proposed extension**. They do not run through the current DLP engine, and `queries.rules.proposed` is **unsupported design notation**, not new parser syntax. The ordinary thesis examples elsewhere in `examples/` retain their existing meaning.

Run the independent, standard-library checker from the repository root:

```sh
python3 examples/temporal_geo/reference_checks.py
```

The checker evaluates only the finite fixtures in `fixtures.json`. It is neither an implementation of GeoSPARQL nor a stream processor, and a passing result is not engine conformance. It has no production dependencies or network access. It checks the listed outcomes, not execution of the proposed queries.

## Spatial and snapshot cases

Coordinates are synthetic **EPSG:25832 easting/northing in metres**. Distance is Euclidean in that projected coordinate plane, not a WGS84 geodesic or a surveyed ground-distance assertion. The center is `(500000,5400000)`. Radius membership is inclusive: distance `<= 100` metres. The opposite-lane sign is 10 metres west, at offset `(-10,0)`.

| Sign | Distance | Consequence |
| --- | ---: | --- |
| `stop_near` | 50 m | A valid nearby stop sign |
| `stop_opposite` | 10 m | Nearby, but explicitly assigned to the westbound lane |
| `speed_near` | 60 m | Excluded by the requested StopSign type |
| `stop_expired` | 10 m | Its validity ended at 08:00 |
| `stop_boundary` | 100 m | Included at the radius boundary; valid from 08:00 to before 09:00 |
| `stop_outside` | 100.1 m | Excluded by distance |

At `2026-09-10T08:30:00Z`, the nearby stop set is `{stop_near, stop_opposite, stop_boundary}`. At exactly `09:00:00Z`, it is `{stop_near, stop_opposite}`. Requiring eastbound applicability removes `stop_opposite` from each answer. Lane applicability is an explicit assertion in this small example; real traffic applicability would need road association and direction semantics.

The rectangle example distinguishes a point strictly inside from a point on the boundary: `contains` excludes the boundary while `covers` includes it. This is separate from the circular distance boundary. Adjacent validity intervals `[08:00,09:00)` and `[09:00,10:00)` meet but do not intersect; at 09:00 only the second contains the instant.

The speed record has two historical versions. A 50 km/h value was valid from 08:00 to 10:00 and recorded from 08:00 to 09:05. At 09:05 it was corrected to 30 km/h for the same valid period. Thus a query about 08:30 returns 50 using record time 09:04:59, and 30 using record time 09:05. The open-ended record interval uses JSON `null` only as an explicit infinity marker, not an unknown value.

## Event-time cases and corrections

Three initially accepted observations occur at seconds 00, 05, and 10 after 08:00. A fourth observation at second 03 is received at second 13. The fixture assumes the correction policy accepts it. Event time chooses window membership; record time explains when the observation became available.

For the 10-second window `[end-10s,end)`:

| State | Window | Members | Count |
| --- | --- | --- | ---: |
| Before the late observation | `[08:00:02,08:00:12)` | 05, 10 | 2 |
| Corrected earlier result | `[08:00:02,08:00:12)` | 03, 05, 10 | 3 |
| Later current window | `[08:00:05,08:00:15)` | 05, 10 | 2 |

The sample at 05 is retained at the last window's inclusive start. The sample at 10 is excluded from a window ending exactly at 10. Repeated delivery of the same event ID does not increase the count. No watermark generator or lateness scheduler is implemented here: a production adapter would need an explicit allowed-lateness and finality policy to decide whether the correction is accepted.

The vehicle is outside the circular fence at 00 and inside at 03, 05, and 10. Initially the observed entry is associated with event 05. Accepting late event 03 changes it to entry03: emit **retract(entry05), add(entry03)**. This means a transition between observed samples, not the exact physical boundary-crossing time. The checker orders observations by `(event_time,event_id)`; that tie rule is deterministic but does not assert an order of simultaneous physical events.

Entry detection needs the outside predecessor at 00, even though it precedes the active window starting at 02. At the later window starting at 05, dropping predecessor03 must not invent a new entry05. Window membership, predecessor state, and historical events have distinct lifetimes. This is why `PREVIOUS` is a separate stateful operator in the design sketch.

The arithmetic fixture checks `50 metres / 5 seconds * 3.6 = 36 km/h` independently of the trajectory coordinates. It illustrates units and binding order; it is not an asserted speed of one of the listed trajectory segments.

## Proposed notation

Additional worked ontologies are available for
[Bach birthdates and first-child ages](../bach_temporal/README.md),
[OpenStreetMap elements/tags](../osm/README.md), and
[PROLIX traffic-sign categories and sign distances](../traffic_signs/README.md).
The [implementation specification](../../docs/ENGINE_EXTENSION_SPEC.md) ties
these fixtures to the remaining engine work. Their current DLP classifications
and standalone extended computations are reported separately.

`queries.rules.proposed` contains five snapshot queries and five stream queries. Pure custom builtins use `sp:`, `time:`, and `num:` URNs. In this file, **`time:` is not the OWL-Time namespace**. Standard `geo:` and `geof:` namespaces are reserved separately; the custom `sp:dwithin` and projected `sp:distance` names do not claim standardized GeoSPARQL function behavior.

`WINDOW`, `MEMBER`, `COUNT_DISTINCT`, `PREVIOUS`, and `EMIT CHANGES` are proposed stateful operators, not scalar builtins. Function arguments must already be bound by query inputs, positive facts, or prior binds. External clocks, source completeness, and accepted revisions belong to the query/runtime context. No ordinary failed ontology query is treated as proof of event absence.

See the [temporal evidence and architectural boundaries](../../docs/research/temporal-stream-evidence.md) for source-backed standards and research, and the [main research report](../../docs/TEMPORAL_GEOSPATIAL_RESEARCH.md) for the integrated design. These fixtures offer reviewable expected answers before any language or runtime implementation is selected.
