"""Actual HTTP OSRM protocol calls against a controlled versioned test server."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import threading
import time

import pytest
from rdflib import Namespace

from dlp_reasoner.domains import Point
from dlp_reasoner.osrm import OPERATION, OSRMRouteProvider
from dlp_reasoner.providers import CancellationToken, ProviderError, ProviderRegistry, Status
from dlp_reasoner.query_runtime import QueryRuntime, QueryScope


@pytest.fixture
def service():
    state = {"revision": "map-v1", "requests": [], "http_status": 200,
             "chunk_size": None, "chunk_delay": 0, "bytes_sent": 0,
             "body": {"code": "Ok", "routes": [{"distance": 150.0, "duration": 20.0}],
                      "waypoints": [{"location": [8, 49], "distance": 1.0},
                                    {"location": [8.001, 49], "distance": 2.0}]}}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state["requests"].append(self.path)
            self.send_response(state["http_status"])
            if state["revision"] is not None:
                self.send_header("X-DLP-Data-Revision", state["revision"])
            payload = state["body"] if isinstance(state["body"], bytes) else json.dumps(state["body"]).encode()
            self.send_header("Content-Length", str(state.get("content_length", len(payload))))
            self.end_headers()
            chunk = state["chunk_size"] or len(payload)
            for offset in range(0, len(payload), chunk):
                try:
                    self.wfile.write(payload[offset:offset + chunk])
                    self.wfile.flush()
                    state["bytes_sent"] += min(chunk, len(payload) - offset)
                    if state.get("cancel") is not None and state["bytes_sent"] >= 5:
                        state["cancel"].cancel()
                    if state["chunk_delay"]:
                        time.sleep(state["chunk_delay"])
                except (BrokenPipeError, ConnectionResetError):
                    break

        def log_message(self, *_):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01))
    thread.start()
    provider = OSRMRouteProvider(f"http://127.0.0.1:{server.server_port}",
                                implementation="osrm-test-5.27.1", revision="map-v1")
    registry = ProviderRegistry()
    provider.register(registry)
    try:
        yield state, provider, registry
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


PAIR = (Point(8.0, 49.0), Point(8.001, 49.0))


def test_correlated_distances_and_revision_caching(service):
    state, provider, registry = service
    result = registry.evaluate(OPERATION, [PAIR, PAIR])
    assert [r.value for r in result] == [150.0, 150.0]
    assert len(state["requests"]) == 1
    assert "radiuses=25;25" in state["requests"][0]
    assert "alternatives=false" in state["requests"][0]
    state["revision"] = provider.revision = "map-v2"
    state["body"]["routes"][0]["distance"] = 190.0
    assert registry.evaluate(OPERATION, [PAIR])[0].value == 190.0
    assert len(state["requests"]) == 2


@pytest.mark.parametrize("backend", ["python", "native"])
def test_osrm_provider_executes_inside_actual_query_rules(service, backend):
    _, _, registry = service
    source = """version 1
    prefix ex: <urn:osrm-example:>
    prefix road: <urn:dlp:road:>
    ex:route(?from, ?to, ?length) :- ex:pair(?from, ?to),
        bind road:osrmFastestRouteLength(?from, ?to) as ?length.
    """
    ex = Namespace("urn:osrm-example:")
    with QueryRuntime(source, providers=registry, backend=backend) as runtime:
        result = runtime.evaluate({ex.pair: {PAIR}}, scope=QueryScope("urn:osrm:test", "1"))
        assert result.rows(ex.route) == {(*PAIR, 150.0)}


def test_no_route_and_no_snap_are_different(service):
    state, _, registry = service
    state.update(body={"code": "NoRoute"}, http_status=400)
    assert registry.evaluate(OPERATION, [PAIR])[0].status is Status.NO_ROUTE
    assert registry.evaluate(OPERATION, [PAIR])[0].status is Status.NO_ROUTE
    assert len(state["requests"]) == 1
    registry.invalidate()
    state["body"] = {"code": "NoSegment"}
    with pytest.raises(ProviderError) as caught:
        registry.evaluate(OPERATION, [PAIR])
    assert caught.value.status is Status.NO_MATCH


@pytest.mark.parametrize("case,status", [("missing_revision", Status.SNAPSHOT_CHANGED),
    ("moved_revision", Status.SNAPSHOT_CHANGED), ("over_snap", Status.NO_MATCH),
    ("negative_length", Status.PROTOCOL_ERROR), ("bytes", Status.RESOURCE_LIMIT),
    ("duplicate_json", Status.PROTOCOL_ERROR)])
def test_response_failures_are_never_complete_empty_results(service, case, status):
    state, provider, registry = service
    if case == "missing_revision":
        state["revision"] = None
    elif case == "moved_revision":
        state["revision"] = "different-map"
    elif case == "over_snap":
        state["body"]["waypoints"][0]["distance"] = 26
    elif case == "negative_length":
        state["body"]["routes"][0]["distance"] = -1
    elif case == "bytes":
        provider.max_response_bytes = 10
    elif case == "duplicate_json":
        state["body"] = b'{"code":"NoRoute","code":"NoRoute"}'
    with pytest.raises(ProviderError) as caught:
        registry.evaluate(OPERATION, [PAIR])
    assert caught.value.status is status


def test_declared_outside_coverage_does_not_call_route_server(service):
    state, provider, registry = service
    provider.coverage = (9, 48, 10, 50)
    assert registry.evaluate(OPERATION, [PAIR])[0].status is Status.OUT_OF_REGION
    assert not state["requests"]


@pytest.mark.parametrize("mode", ["deadline", "cancel"])
def test_slow_stream_checks_deadline_and_cancellation_before_body_finishes(service, mode):
    state, provider, registry = service
    body = b'{"code":"NoRoute"}' + b' ' * 300
    state.update(body=body, chunk_size=1, chunk_delay=0.004)
    provider.timeout = 0.1
    options = {}
    if mode == "cancel":
        state["cancel"] = options["cancel"] = CancellationToken()
    start = time.monotonic()
    if mode == "deadline":
        options["deadline"] = start + 0.05
    with pytest.raises(ProviderError) as failure:
        registry.evaluate(OPERATION, [PAIR], **options)
    assert failure.value.status is (Status.DEADLINE if mode == "deadline" else Status.CANCELLED)
    # The complete body takes >1s. This margin tolerates scheduler jitter while
    # distinguishing bounded progress reads from waiting for the whole body.
    assert time.monotonic() - start < 0.5
    assert state["bytes_sent"] < len(body)
    assert registry.cache_info()["entries"] == 0


def test_oversized_snapped_coordinate_is_protocol_error_not_transport_unavailable(service):
    state, _, registry = service
    state["body"]["waypoints"][0]["location"][0] = 10**500
    with pytest.raises(ProviderError) as failure:
        registry.evaluate(OPERATION, [PAIR])
    assert failure.value.status is Status.PROTOCOL_ERROR


def test_truncated_http_body_never_publishes_complete_no_route(service):
    state, _, registry = service
    state.update(body=b'{"code":"NoRoute"}', content_length=100)
    with pytest.raises(ProviderError) as failure:
        registry.evaluate(OPERATION, [PAIR])
    assert failure.value.status is Status.PROTOCOL_ERROR
