from contextlib import contextmanager
from dataclasses import replace
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import threading
import time

import pytest
from rdflib import Literal, URIRef, XSD

from dlp_reasoner.domains import IntegerValue, Point, Quantity
from dlp_reasoner.providers import (
    CancellationToken, DirectedRoadProvider, FakeProvider, HTTPJSONAdapter, LoopbackEndpoint,
    ProviderError, ProviderRegistry, ProviderResult, Reply, ScanPage, Status, StatusProvider,
)


def registry(fake=None, **limits):
    fake = fake or FakeProvider({"double": lambda x: x * 2}, {"items": lambda n: ((i,) for i in range(n))})
    result = ProviderRegistry(**limits)
    result.register("double", fake, input_types=("integer",), result_type="integer")
    result.register("items", fake, input_types=("integer",), cardinality="many", output_types=("integer",))
    return result, fake


def test_correlated_reordered_batches_and_exact_dedup():
    calls = []
    fake = FakeProvider({"double": lambda value: calls.append(value) or value * 2})
    store, _ = registry(fake, max_batch=2)
    assert [row.value for row in store.evaluate("double", [(3,), (1,), (3,), (2,)])] == [6, 2, 6, 4]
    assert calls == [3, 1, 2]
    assert fake.batch_calls == 2
    assert [row.value for row in store.evaluate("double", [(1,), (2,)])] == [2, 4]
    assert fake.batch_calls == 2


def test_false_and_complete_no_route_cache_distinctly():
    fake = FakeProvider({"false": lambda: False,
                         "route": lambda: ProviderResult(Status.NO_ROUTE)})
    store = ProviderRegistry()
    store.register("false", fake, result_type="boolean")
    store.register("route", fake, result_type="number")
    for _ in range(2):
        assert store.evaluate("false", [()]) == (ProviderResult(Status.OK, False),)
        assert store.evaluate("route", [()]) == (ProviderResult(Status.NO_ROUTE),)
    assert fake.batch_calls == 2


@pytest.mark.parametrize("fault", ["missing", "duplicate", "unknown", "incomplete", "revision", "type"])
def test_malformed_batches_never_publish_cache(fault):
    class Bad(FakeProvider):
        def evaluate_batch(self, *args):
            response = super().evaluate_batch(*args)
            a, b = response.replies
            if fault == "missing":
                return replace(response, replies=(a,))
            if fault == "duplicate":
                return replace(response, replies=(a, a))
            if fault == "unknown":
                return replace(response, replies=(a, Reply(999, b.result)))
            if fault == "incomplete":
                return replace(response, complete=False)
            if fault == "revision":
                return replace(response, snapshot=replace(response.snapshot, dataset="wrong"))
            return replace(response, replies=(a, Reply(b.row_id, ProviderResult(Status.OK, "wrong"))))

    store, _ = registry(Bad({"double": lambda x: x * 2}))
    with pytest.raises(ProviderError) as error:
        store.evaluate("double", [(1,), (2,)])
    assert error.value.status in {Status.PROTOCOL_ERROR, Status.INCOMPLETE}
    assert store.cache_info()["entries"] == 0


@pytest.mark.parametrize("status", [Status.DOMAIN_ERROR, Status.UNAVAILABLE, Status.CANCELLED,
                                    Status.INCOMPLETE, Status.DEADLINE])
def test_operational_failures_are_not_negative_results(status):
    store, _ = registry(FakeProvider({"double": lambda x: ProviderResult(status)}))
    with pytest.raises(ProviderError) as error:
        store.evaluate("double", [(1,)])
    assert error.value.status == status
    assert store.cache_info()["entries"] == 0


def test_revision_key_and_whole_view_invalidation_find_new_rows():
    values = []
    fake = FakeProvider(scans={"items": lambda n: iter(values)})
    store, _ = registry(fake)
    before = store.revision_key()
    assert list(store.scan("items", (0,))) == []
    assert list(store.scan("items", (0,))) == []
    assert fake.scan_calls == 1
    values.append((7,))
    fake.revision = "2"
    assert store.revision_key() != before
    assert list(store.scan("items", (0,))) == [(7,)]
    before = store.revision_key()
    store.invalidate("fake")
    assert store.revision_key() != before


def test_revision_changes_inside_batch_fail_before_any_publication():
    fake = FakeProvider()
    fake.scalars["double"] = lambda x: setattr(fake, "revision", "2") or x
    store, _ = registry(fake)
    with pytest.raises(ProviderError, match="revision"):
        store.evaluate("double", [(1,)])
    assert store.cache_info()["entries"] == 0


def test_registry_invalidation_inside_batch_and_between_yields():
    store, fake = registry()
    fake.scalars["double"] = lambda x: store.invalidate() or x
    with pytest.raises(ProviderError) as error:
        store.evaluate("double", [(1,)])
    assert error.value.status == Status.SNAPSHOT_CHANGED
    cursor = store.scan("items", (4,))
    assert next(cursor) == (0,)
    store.invalidate()
    with pytest.raises(ProviderError) as error:
        next(cursor)
    assert error.value.status == Status.SNAPSHOT_CHANGED
    assert fake.closed_cursors == 1


def test_early_scan_close_is_not_complete_and_does_not_cache_partial_rows():
    store, fake = registry(max_page=2)
    with store.scan("items", (5,)) as cursor:
        assert next(cursor) == (0,)
    assert cursor.closed and not cursor.complete
    assert fake.closed_cursors == 1 and store.cache_info()["entries"] == 0
    with store.scan("items", (5,)) as cursor:
        assert list(cursor) == [(0,), (1,), (2,), (3,), (4,)]
        assert cursor.complete
    assert list(store.scan("items", (5,))) == [(0,), (1,), (2,), (3,), (4,)]
    assert fake.scan_calls == 2


@pytest.mark.parametrize("page", [
    ScanPage(None, (), False),
    ScanPage(None, ((1,),), True, "extra"),
    ScanPage(None, (("wrong",),), True),
])
def test_bad_scan_pages_are_not_empty_success(page):
    class Bad(FakeProvider):
        def open_scan(self, operation, arguments, snapshot, control):
            class Cursor:
                def next_page(self, limit, control):
                    return replace(page, snapshot=snapshot)

                def close(self):
                    pass
            return Cursor()
    store, _ = registry(Bad())
    with pytest.raises(ProviderError):
        list(store.scan("items", (1,)))
    assert store.cache_info()["entries"] == 0


def test_scan_page_and_row_limits_cannot_claim_complete():
    store, _ = registry(max_page=1, max_pages=2)
    cursor = store.scan("items", (10,))
    with pytest.raises(ProviderError) as error:
        list(cursor)
    assert error.value.status == Status.INCOMPLETE and not cursor.complete
    store, _ = registry(max_rows=2)
    with pytest.raises(ProviderError) as error:
        list(store.scan("items", (3,)))
    assert error.value.status == Status.RESOURCE_LIMIT


def test_cancel_deadline_and_deadline_after_noncooperative_adapter():
    store, fake = registry()
    cancel = CancellationToken()
    cancel.cancel()
    with pytest.raises(ProviderError) as error:
        store.evaluate("double", [(1,)], cancel=cancel)
    assert error.value.status == Status.CANCELLED and fake.batch_calls == 0
    with pytest.raises(ProviderError) as error:
        store.scan("items", (1,), deadline=time.monotonic() - 1)
    assert error.value.status == Status.DEADLINE
    fake.scalars["double"] = lambda x: time.sleep(0.02) or x
    with pytest.raises(ProviderError) as error:
        store.evaluate("double", [(1,)], deadline=time.monotonic() + 0.005)
    assert error.value.status == Status.DEADLINE
    assert store.cache_info()["entries"] == 0


def test_cache_bounds_and_exact_argument_types():
    fake = FakeProvider({"identity": lambda x: x})
    store = ProviderRegistry(max_entries=2, max_bytes=3000)
    store.register("identity", fake, input_types=("any",))
    for value in (False, 0, "0", Decimal("0")):
        assert store.evaluate("identity", [(value,)])[0].value == value
    assert fake.batch_calls == 4
    assert store.cache_info()["entries"] <= 2 and store.cache_info()["bytes"] <= 3000
    store.evaluate("identity", [("x" * 4000,)])
    assert store.cache_info()["bypasses"] > 0
    store.clear_cache()
    assert store.cache_info()["entries"] == 0


def test_disabled_cache_work_bounds_and_mutable_values():
    store, fake = registry(max_entries=0)
    store.evaluate("double", [(1,)])
    store.evaluate("double", [(1,)])
    assert fake.batch_calls == 2
    with pytest.raises(ProviderError):
        store.evaluate("double", [([1],)])
    store, _ = registry(max_work_bytes=1)
    with pytest.raises(ProviderError) as error:
        store.evaluate("double", [(1,)])
    assert error.value.status == Status.RESOURCE_LIMIT


@contextmanager
def loopback(fake):
    endpoint = LoopbackEndpoint(fake)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            size = int(self.headers.get("Content-Length", 0))
            if size > 1_000_000:
                self.send_error(413)
                return
            result = endpoint.dispatch(json.loads(self.rfile.read(size)))
            data = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    worker.start()
    try:
        yield HTTPJSONAdapter(f"http://127.0.0.1:{server.server_port}", timeout=0.5)
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=1)
        endpoint.close()
        assert not worker.is_alive()


def test_real_http_loopback_roundtrip_exact_values_and_paging():
    fake = FakeProvider({"identity": lambda value: value}, {"items": lambda n: ((i,) for i in range(n))})
    with loopback(fake) as adapter:
        store = ProviderRegistry(max_page=2)
        store.register("identity", adapter, input_types=("any",))
        store.register("items", adapter, input_types=("integer",), cardinality="many", output_types=("integer",))
        values = [Decimal("123456789.012345678"), Literal("001", datatype=XSD.integer, normalize=False),
                  URIRef("urn:example:a"), Point(8.4, 49.0), False, b"\0\xff"]
        result = store.evaluate("identity", [(value,) for value in values])
        assert [row.value for row in result] == values
        assert str(result[1].value) == "001"
        cursor = store.scan("items", (5,))
        assert list(cursor) == [(0,), (1,), (2,), (3,), (4,)]
        assert cursor.complete and fake.closed_cursors == 1


def test_http_reply_byte_limits_and_unavailable():
    with loopback(FakeProvider({"large": lambda: "x" * 10000})) as adapter:
        adapter.max_bytes = 2000
        store = ProviderRegistry()
        store.register("large", adapter)
        with pytest.raises(ProviderError) as error:
            store.evaluate("large", [()])
        assert error.value.status == Status.RESOURCE_LIMIT
    with pytest.raises(ProviderError) as error:
        adapter.snapshot()
    assert error.value.status == Status.UNAVAILABLE


def test_descriptor_metadata_and_invalid_modes():
    store, _ = registry()
    descriptor = store.get("items")
    assert descriptor.arity == 1 and descriptor.required_positions == (0,)
    assert descriptor.cardinality == "many" and descriptor.output_types == ("integer",)
    assert store.get("missing") is None
    with pytest.raises(ProviderError):
        store.evaluate("items", [(1,)])
    with pytest.raises(ProviderError):
        store.scan("double", (1,))


@pytest.mark.parametrize("wire", [
    ["bool", "false"], ["bool", 1], ["bool", False, 0], ["str", 10],
    ["float", "nan"], ["float", "inf"], ["int", "01"], ["null", 0],
    ["tuple", [["bool", "false"]]], ["unknown", 1],
    ["domain", "Point", [["float", "0x0.0p+0"], ["float", "0x1.6c00000000000p+6"],
                           ["str", "EPSG:4326"], ["str", "wgs84-v1"]]],
])
def test_strict_wire_value_corpus(wire):
    from dlp_reasoner.providers import _decode
    with pytest.raises((ValueError, TypeError, KeyError)):
        _decode(wire)


def test_road_direction_unreachable_coverage_and_changed_reachability():
    a, b, c, outside = map(URIRef, ("urn:a", "urn:b", "urn:c", "urn:outside"))
    road = DirectedRoadProvider([(a, b, 100), (b, c, 20), (a, c, 150)])
    store = ProviderRegistry()
    road.register(store)
    assert store.evaluate(road.operation, [(a, c, "car")])[0].value == 120.0
    assert store.evaluate(road.operation, [(c, a, "car")])[0].status == Status.NO_ROUTE
    assert store.evaluate(road.operation, [(a, a, "car")])[0].value == 0.0
    result = store.evaluate(road.operation, [(a, outside, "car")])
    assert result[0].status == Status.OUT_OF_REGION
    before = store.revision_key()
    road.replace_graph([(c, a, 10)], nodes=(b,), revision="2")
    assert store.revision_key() != before
    assert store.evaluate(road.operation, [(c, a, "car")])[0].value == 10.0
    assert store.evaluate(road.operation, [(b, a, "car")])[0].status == Status.NO_ROUTE


def test_road_failed_replacement_is_atomic_and_bounded():
    a, b = URIRef("urn:a"), URIRef("urn:b")
    road = DirectedRoadProvider([(a, b, 10)], max_nodes=2, max_edges=1)
    before = road.snapshot()
    for edges in ([(a, b, -1)], [(a, b, float("nan"))], [(a, b, 1), (b, a, 2)]):
        with pytest.raises((ValueError, ProviderError)):
            road.replace_graph(edges, revision="2")
        assert road.snapshot() == before
    with pytest.raises(ValueError):
        road.replace_graph([], revision="1")
    with pytest.raises(ProviderError):
        DirectedRoadProvider([(a, b, 1)], max_bytes=1)


def test_normalized_numeric_arguments_reuse_exact_value_cache():
    calls = []
    fake = FakeProvider({"number": lambda value: calls.append(value) or 1})
    store = ProviderRegistry()
    store.register("number", fake, input_types=("integer",), result_type="integer")
    values = [Literal("001", datatype=XSD.integer, normalize=False), IntegerValue(1), 1]
    assert len(store.evaluate("number", [(value,) for value in values])) == 3
    assert len(calls) == 1


def test_unit_metric_crs_and_quantity_contract_mismatches_fail():
    from dlp_reasoner.providers import Snapshot

    class Spatial(FakeProvider):
        def snapshot(self):
            return Snapshot("spatial", "v1", "map1", (("unit", "urn:dlp:unit:metre"),
                                                       ("metric", "planar"), ("crs", "EPSG:25832")))

    fake = Spatial({"length": lambda: Quantity(IntegerValue(1), "urn:dlp:unit:second")})
    store = ProviderRegistry()
    store.register("length", fake, result_type="quantity", output_unit="urn:dlp:unit:metre")
    with pytest.raises(ProviderError, match="unit"):
        store.evaluate("length", [()])
    store.register("length", fake, result_type="quantity", metric="ellipsoidal")
    with pytest.raises(ProviderError, match="metric"):
        store.evaluate("length", [()])
    store.register("length", fake, result_type="quantity", crs="EPSG:4326")
    with pytest.raises(ProviderError, match="crs"):
        store.evaluate("length", [()])


def test_http_cancellation_and_duplicate_reply_are_failures():
    cancel = CancellationToken()
    fake = FakeProvider({"cancel": lambda: cancel.cancel() or False})
    with loopback(fake) as adapter:
        store = ProviderRegistry()
        store.register("cancel", adapter, result_type="boolean")
        with pytest.raises(ProviderError) as error:
            store.evaluate("cancel", [()], cancel=cancel)
        assert error.value.status == Status.CANCELLED
        assert store.cache_info()["entries"] == 0

    class Duplicate(FakeProvider):
        def evaluate_batch(self, *args):
            response = super().evaluate_batch(*args)
            return replace(response, replies=(response.replies[0], response.replies[0]))

    with loopback(Duplicate({"value": lambda x: x})) as adapter:
        store = ProviderRegistry()
        store.register("value", adapter, input_types=("integer",))
        with pytest.raises(ProviderError) as error:
            store.evaluate("value", [(1,), (2,)])
        assert error.value.status == Status.PROTOCOL_ERROR
        assert store.cache_info()["entries"] == 0


def test_explicit_status_operations_and_http_carrier():
    store = ProviderRegistry()
    status = StatusProvider()
    status.register(store)
    outcomes = (7, False, ProviderResult(Status.NO_ROUTE), ProviderResult(Status.OUT_OF_REGION))
    assert [r.value for r in store.evaluate("urn:dlp:provider:isOK", [(r,) for r in outcomes])] == [True, True, False, False]
    assert store.evaluate("urn:dlp:provider:value", [(7,)])[0].value == 7
    with pytest.raises(ProviderError):
        store.evaluate("urn:dlp:provider:value", [(outcomes[2],)])
    with loopback(status) as adapter:
        remote = ProviderRegistry()
        remote.register("urn:dlp:provider:isOK", adapter, input_types=("any",), result_type="boolean")
        assert remote.evaluate("urn:dlp:provider:isOK", [(outcomes[2],)])[0].value is False


def test_out_of_region_status_is_not_cached_as_negative_answer():
    fake = FakeProvider({"coverage": lambda: ProviderResult(Status.OUT_OF_REGION)})
    store = ProviderRegistry()
    store.register("coverage", fake)
    for _ in range(2):
        assert store.evaluate("coverage", [()])[0].status == Status.OUT_OF_REGION
    assert fake.batch_calls == 2 and store.cache_info()["entries"] == 0
