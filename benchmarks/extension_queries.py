"""Matched selective-radius benchmark; keeps thesis result artifacts unchanged.

Both paths use the same exact native ellipsoidal metric and preloaded points.
Reports index construction separately from complete answer latency, compares
exact answer sets, and counts refinements. This is not an end-to-end ontology,
network-routing or phone benchmark.
"""
import argparse
import hashlib
import json
import platform
import statistics
import time

from rdflib import URIRef

from dlp_reasoner.domains import DomainRegistry, Point, SPATIAL
from dlp_reasoner.spatial import PointIndex


def run(side=100, repeats=5):
    if not 2 <= side <= 1000 or not 1 <= repeats <= 100:
        raise ValueError("Use side in [2,1000] and repeats in [1,100]")
    points = {URIRef(f"urn:grid:{x}:{y}"): Point(8.4 + (x-side//2)*0.001,
                                               48.8 + (y-side//2)*0.001)
              for x in range(side) for y in range(side)}
    center, radius = Point(8.4, 48.8), 150
    fingerprint = hashlib.sha256(json.dumps([(str(key), vars(point)) for key, point in points.items()],
                                            sort_keys=True).encode()).hexdigest()
    report = dict(workload="selective-radius-v1", platform=platform.platform(),
                  processor=platform.machine(), points=len(points), repeats=repeats,
                  input_sha256=fingerprint, radius_metres=radius, metric="WGS84 ellipsoidal")
    with DomainRegistry(backend="native", native_value_capacity=len(points) * 3 + 16) as domains:
        # Exclude compile/load latency and keep it explicit in the report.
        start = time.perf_counter()
        domains.evaluate(SPATIAL + "wgs84Distance", (center, center))
        report["domain_load_ms"] = 1000 * (time.perf_counter() - start)

        def exhaustive():
            result = set()
            items = tuple(points.items())
            for offset in range(0, len(items), 256):
                chunk = items[offset:offset+256]
                replies = domains.evaluate_batch(SPATIAL + "wgs84Distance",
                                                 [(center, point) for _, point in chunk])
                for (identifier, _), reply in zip(chunk, replies):
                    if not reply.ok:
                        raise reply.error
                    if float(reply.value) <= radius:
                        result.add(identifier)
            return frozenset(result)

        start = time.perf_counter()
        expected = exhaustive()
        report["exhaustive_first_ms"] = 1000 * (time.perf_counter() - start)
        observations = []
        for _ in range(repeats):
            start = time.perf_counter()
            assert exhaustive() == expected
            observations.append(1000 * (time.perf_counter() - start))
        report["exhaustive_warm_ms"] = observations
        report["exhaustive_exact_evaluations_per_query"] = len(points)
        report["answers"] = len(expected)
        report["indexes"] = []
        for backend in ("python", "native"):
            start = time.perf_counter()
            with PointIndex(points, revision=fingerprint, backend=backend) as index:
                build_ms = 1000 * (time.perf_counter() - start)
                times = []
                for _ in range(repeats):
                    start = time.perf_counter()
                    assert index.within(center, radius, domains=domains) == expected
                    times.append(1000 * (time.perf_counter() - start))
                report["indexes"].append(dict(backend=backend, build_ms=build_ms,
                    complete_answer_ms=times,
                    median_speedup_vs_warm_exhaustive=statistics.median(observations)/statistics.median(times),
                    exact_evaluations_per_query=index.stats["exact_evaluations"]/repeats,
                    candidates_per_query=index.stats["candidates"]/repeats))
        report["native_values"] = domains.native_stats()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--side", type=int, default=100)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output")
    args = parser.parse_args()
    text = json.dumps(run(args.side, args.repeats), indent=2) + "\n"
    if args.output:
        from pathlib import Path
        Path(args.output).write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
