"""Bounded OSRM route-service adapter with explicit revision and snapping policy.

OSRM selects a fastest route for its configured profile. Its returned length is
not a proof of the shortest-distance route. Production use requires a controlled
endpoint which attaches the configured data-revision header to every response.
No public demonstration endpoint is assumed to have repeatable map revisions.
"""
import json
from http.client import HTTPException
import math
import re
import time
from urllib import request as http, error as errors
from urllib.parse import urlsplit

from .domains import Point
from .providers import BatchReply, ProviderError, ProviderResult, Reply, Snapshot, Status


OPERATION = "urn:dlp:road:osrmFastestRouteLength"


def _finite(value, label):
    try:
        valid = type(value) in {float, int} and math.isfinite(value) and value >= 0
    except OverflowError:
        valid = False
    if not valid:
        raise ProviderError(Status.PROTOCOL_ERROR, f"Invalid OSRM {label}")
    return float(value)


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate OSRM response key")
        result[key] = value
    return result


def _read_response(response, max_bytes, timeout, control):
    """Read bounded progress chunks, with a remaining deadline per socket wait.

    urllib's HTTP responses expose HTTPResponse.read1, which performs at most
    one underlying buffered read. Plain read(n) can wait indefinitely for n
    bytes from a peer that continuously sends data before each socket timeout.
    HTTPError wraps the same response when OSRM sends its structured HTTP400.
    The socket path is an explicit stdlib transport capability: fail closed if
    a substituted transport cannot enforce the remaining per-read timeout.
    """
    stream = response.fp if isinstance(response, errors.HTTPError) else response
    read = getattr(stream, "read1", None)
    if not callable(read):
        raise ProviderError(Status.UNAVAILABLE, "OSRM transport lacks bounded streaming reads")
    payload = bytearray()
    while True:
        control.check()
        remaining = timeout if control.deadline is None else min(timeout, control.deadline-time.monotonic())
        if remaining <= 0:
            raise ProviderError(Status.DEADLINE, "OSRM response deadline exceeded")
        if stream.isclosed():
            if stream.length not in (None, 0):
                raise ProviderError(Status.PROTOCOL_ERROR, "Truncated OSRM response body")
            break
        sock = getattr(getattr(getattr(stream, "fp", None), "raw", None), "_sock", None)
        if sock is None or not callable(getattr(sock, "settimeout", None)):
            raise ProviderError(Status.UNAVAILABLE, "OSRM transport lacks deadline-aware socket reads")
        sock.settimeout(remaining)
        try:
            chunk = read(min(64 * 1024, max_bytes + 1 - len(payload)))
        except HTTPException as exc:
            raise ProviderError(Status.PROTOCOL_ERROR, "Malformed OSRM HTTP response framing") from exc
        control.check()
        if not chunk:
            if stream.length not in (None, 0):
                raise ProviderError(Status.PROTOCOL_ERROR, "Truncated OSRM response body")
            break
        payload.extend(chunk)
        if len(payload) > max_bytes:
            raise ProviderError(Status.RESOURCE_LIMIT, "OSRM response byte limit exceeded")
    return payload


class OSRMRouteProvider:
    """HTTP route length in metres, over a pinned server/profile/map snapshot.

    ``coverage`` is an optional (west,south,east,north) source-coverage rectangle;
    west > east represents an antimeridian crossing. Outside coverage is an
    explicit OUT_OF_REGION result. NoSegment is NO_MATCH, never NO_ROUTE.
    Each pair is a separate bounded route request; no all-pairs request is made.
    """
    def __init__(self, endpoint, *, implementation, revision, profile="driving",
                 max_snapping_metres=25.0, coverage=None, timeout=5.0,
                 max_response_bytes=1024*1024, max_batch_rows=256,
                 revision_header="X-DLP-Data-Revision"):
        url = urlsplit(endpoint)
        if (url.scheme not in {"http", "https"} or not url.netloc or url.username
                or url.password or url.query or url.fragment):
            raise ValueError("OSRM endpoint must be an HTTP(S) base URL without credentials/query")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", profile):
            raise ValueError("Invalid OSRM profile path")
        if not implementation or not revision or not isinstance(implementation, str) or not isinstance(revision, str):
            raise ValueError("Explicit implementation and data revision are required")
        if not isinstance(revision_header, str) or not re.fullmatch(r"[A-Za-z0-9-]+", revision_header):
            raise ValueError("Invalid revision header")
        if type(timeout) not in {int, float} or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        if type(max_snapping_metres) not in {int, float} or not math.isfinite(max_snapping_metres) or max_snapping_metres < 0:
            raise ValueError("Snapping radius must be finite and nonnegative")
        if any(type(v) is not int or v < 1 for v in (max_response_bytes, max_batch_rows)):
            raise ValueError("Response and batch bounds must be positive integers")
        if coverage is not None:
            if (type(coverage) is not tuple or len(coverage) != 4 or
                    any(type(v) not in {int, float} or not math.isfinite(v) for v in coverage)):
                raise ValueError("Coverage requires four finite rectangle coordinates")
            west, south, east, north = coverage
            if not (-180 <= west <= 180 and -180 <= east <= 180 and -90 <= south <= north <= 90):
                raise ValueError("Invalid coverage rectangle")
        self.endpoint, self.implementation, self.revision = endpoint.rstrip("/"), implementation, revision
        self.profile, self.coverage = profile, coverage
        self.max_snapping_metres, self.timeout = float(max_snapping_metres), float(timeout)
        self.max_response_bytes, self.max_batch_rows = max_response_bytes, max_batch_rows
        self.revision_header, self.calls = revision_header, 0

    def snapshot(self):
        return Snapshot("osrm:" + self.endpoint, self.implementation, self.revision,
            (("profile", self.profile), ("metric", "fastest-route-length-metres-v1"),
             ("unit", "metre"), ("crs", "EPSG:4326"),
             ("snap-radius-metres", self.max_snapping_metres.hex()),
             ("coverage", repr(self.coverage)), ("revision-header", self.revision_header)))

    def register(self, registry):
        registry.register(OPERATION, self, input_types=("point", "point"), result_type="float",
                          output_unit="metre", metric="fastest-route-length-metres-v1", crs="EPSG:4326")

    def _covered(self, point):
        if self.coverage is None:
            return True
        west, south, east, north = self.coverage
        return south <= point.latitude <= north and (
            west <= point.longitude <= east if west <= east else
            point.longitude >= west or point.longitude <= east)

    def _route(self, left, right, snapshot, control):
        if type(left) is not Point or type(right) is not Point:
            raise ProviderError(Status.DOMAIN_ERROR, "OSRM route inputs require WGS84 points")
        if not self._covered(left) or not self._covered(right):
            return ProviderResult(Status.OUT_OF_REGION)
        coords = ";".join(f"{p.longitude:.17g},{p.latitude:.17g}" for p in (left, right))
        radius = f"{self.max_snapping_metres:.17g}"
        url = f"{self.endpoint}/route/v1/{self.profile}/{coords}?alternatives=false&steps=false&overview=false&radiuses={radius};{radius}"
        control.check()
        timeout = self.timeout if control.deadline is None else min(self.timeout, control.deadline-time.monotonic())
        if timeout <= 0:
            raise ProviderError(Status.DEADLINE, "OSRM request deadline exceeded")
        try:
            self.calls += 1
            try:
                response = http.urlopen(http.Request(url, headers={"Accept": "application/json"}), timeout=timeout)
            except errors.HTTPError as exc:
                # OSRM may use HTTP 400 for a structured NoRoute/NoSegment reply.
                if exc.code != 400:
                    exc.close()
                    raise ProviderError(Status.UNAVAILABLE, f"OSRM HTTP {exc.code}") from exc
                response = exc
            with response:
                if response.headers.get(self.revision_header) != snapshot.dataset:
                    raise ProviderError(Status.SNAPSHOT_CHANGED, "OSRM response has missing/changed data revision")
                payload = _read_response(response, self.max_response_bytes, self.timeout, control)
        except (OSError, errors.URLError, TimeoutError) as exc:
            control.check()
            raise ProviderError(Status.UNAVAILABLE, f"OSRM transport failed: {type(exc).__name__}") from exc
        control.check()
        if self.snapshot() != snapshot:
            raise ProviderError(Status.SNAPSHOT_CHANGED, "OSRM configuration changed during request")
        try:
            body = json.loads(payload, object_pairs_hook=_object,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
            if not isinstance(body, dict) or type(body.get("code")) is not str:
                raise ValueError("Missing OSRM response code")
            if body["code"] == "NoRoute":
                return ProviderResult(Status.NO_ROUTE)
            if body["code"] == "NoSegment":
                raise ProviderError(Status.NO_MATCH, "OSRM could not snap an input within the declared radius")
            if body["code"] != "Ok":
                raise ProviderError(Status.DOMAIN_ERROR, f"OSRM rejected route: {body['code'][:64]}")
            routes, waypoints = body["routes"], body["waypoints"]
            if not isinstance(routes, list) or len(routes) != 1 or not isinstance(waypoints, list) or len(waypoints) != 2:
                raise ValueError("Unexpected OSRM route/waypoint count")
            for waypoint in waypoints:
                distance = _finite(waypoint["distance"], "snapping distance")
                if distance > self.max_snapping_metres + 1e-7:
                    raise ProviderError(Status.NO_MATCH, "OSRM snapping exceeds the declared radius")
                location = waypoint["location"]
                if (not isinstance(location, list) or len(location) != 2 or
                        any(type(v) not in {int, float} for v in location)):
                    raise ValueError("Invalid OSRM snapped location")
                Point(float(location[0]), float(location[1]))
            length = _finite(routes[0]["distance"], "route distance")
            _finite(routes[0]["duration"], "route duration")
            return ProviderResult(Status.OK, length)
        except (ValueError, TypeError, KeyError, IndexError, RecursionError, OverflowError) as exc:
            raise ProviderError(Status.PROTOCOL_ERROR, f"Malformed OSRM response: {exc}") from exc

    def evaluate_batch(self, operation, requests, snapshot, control):
        if operation != OPERATION:
            raise ProviderError(Status.UNAVAILABLE, "Unknown OSRM operation")
        if snapshot != self.snapshot():
            raise ProviderError(Status.SNAPSHOT_CHANGED, "OSRM snapshot changed")
        if len(requests) > self.max_batch_rows:
            raise ProviderError(Status.RESOURCE_LIMIT, "OSRM batch limit exceeded")
        replies = []
        for request in requests:
            control.check()
            if len(request.arguments) != 2:
                raise ProviderError(Status.DOMAIN_ERROR, "OSRM route arity must be two")
            result = self._route(*request.arguments, snapshot, control)
            replies.append(Reply(request.row_id, result))
        return BatchReply(snapshot, tuple(replies), True)
