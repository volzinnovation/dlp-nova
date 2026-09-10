"""Run real DLP classification and separate, deliberately small distance references."""

import argparse
from collections import defaultdict
from decimal import Decimal
import heapq
import json
import math

from rdflib import Graph, Literal, Namespace, OWL, RDF, URIRef

from dlp_reasoner import Reasoner, parse_dlp

from generate import ROOT, SIGN, categories_for, code_tokens, mapping, outputs


S = Namespace(SIGN)
E = Namespace("https://example.org/traffic-sign/example#")
OSM = Namespace("https://example.org/osm#")


class Checks:
    def __init__(self):
        self.count = 0

    def equal(self, actual, expected, label):
        if actual != expected:
            raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")
        self.count += 1

    def close(self, actual, expected, label):
        self.equal(math.isclose(actual, expected, rel_tol=0, abs_tol=1e-6), True, label)


def equatorial_distance(lat1, lon1, lat2, lon2):
    """Analytic WGS84 ellipsoidal distance for short equatorial arcs ONLY.

    Fail outside this reference's scope instead of quietly substituting a sphere
    or an unreliable general inverse approximation. Production uses an ellipsoid
    inverse provider such as GeographicLib; DLP does not call this function.
    """
    values = tuple(map(float, (lat1, lon1, lat2, lon2)))
    if not all(math.isfinite(v) for v in values):
        raise ValueError("Finite coordinates required")
    lat1, lon1, lat2, lon2 = values
    if lat1 != 0 or lat2 != 0 or abs(lon1) > 180 or abs(lon2) > 180:
        raise ValueError("This analytic reference requires equatorial WGS84 coordinates")
    difference = abs(math.remainder(lon2 - lon1, 360))
    if difference > 1:
        raise ValueError("This analytic reference is limited to arcs of at most one degree")
    return 6378137.0 * math.radians(difference)


def road_distance(edges, start, end):
    """Shortest sum of supplied nonnegative edge weights, in a tiny directed graph.

    This fixture oracle does not implement or call the proposed routing provider.
    None denotes no route in this complete toy graph, not a provider failure.
    """
    adjacency = defaultdict(list)
    vertices = set()
    for edge in edges:
        weight = edge["metres"]
        if not math.isfinite(weight) or weight < 0:
            raise ValueError("Finite nonnegative reference edge weights required")
        adjacency[edge["from"]].append((edge["to"], weight))
        vertices.update((edge["from"], edge["to"]))
    if start not in vertices or end not in vertices:
        raise ValueError("No matched reference graph vertex")
    best = {start: 0}
    pending = [(0, start)]
    while pending:
        cost, node = heapq.heappop(pending)
        if cost != best[node]:
            continue
        if node == end:
            return cost
        for target, weight in adjacency[node]:
            candidate = cost + weight
            if candidate < best.get(target, math.inf):
                best[target] = candidate
                heapq.heappush(pending, (candidate, target))
    return None


def load_graph():
    graph = Graph()
    for path in (ROOT.parent / "osm" / "ontology.dlp", ROOT / "taxonomy.dlp",
                 ROOT / "fixtures.dlp"):
        graph += parse_dlp(path.read_text(encoding="utf-8"), source=str(path))
    return graph


def check_provenance():
    checks = Checks()
    for name, generated in outputs().items():
        checks.equal((ROOT / name).read_bytes(), generated.encode("utf-8"), f"deterministic/{name}")
    manifest, summary, curation = mapping()
    checks.equal(summary["rows"], 225, "complete CSV row coverage")
    checks.equal(summary["distinct_yolo_labels"], 224, "distinct YOLO coverage")
    checks.equal(summary["curated_labels"], 224, "explicit category coverage")
    checks.equal(summary["fallback_labels"], [], "snapshot fully reviewed")
    checks.equal(summary["duplicate_labels"], {"pedestrian:start": 2}, "duplicate row retention")
    checks.equal(summary["multi_code_cells"], [], "no invented multi-code cells")
    checks.equal(code_tokens(""), [], "blank code has no candidates")
    checks.equal(code_tokens("DE:1;DE:2;; DE:3"), ["DE:1", "DE:2", "", " DE:3"],
                 "multi-code raw token retention")
    checks.equal(categories_for("unseen_example_label", curation), ["UnclassifiedSign"],
                 "explicit ingest fallback")
    labels = {record["label"]: record for record in manifest["labels"]}
    checks.equal(len(labels["pedestrian:start"]["csv_lines"]), 2, "duplicate label union")
    checks.equal({row["raw"]["NL"] for row in manifest["rows"]
                  if row["raw"]["YOLO"] == "pedestrian:start"}, {"NL:G07", "NL:B01"},
                 "both conflicting pedestrian mappings retained")
    checks.equal(next(row["raw"]["FR"] for row in manifest["rows"]
                      if row["raw"]["YOLO"] == "hazard:train"), "Fr:A8",
                 "source case is not silently corrected")
    codes = {(row["country"], row["code"]): row for row in manifest["codes"]}
    checks.equal(codes["BE", "BE:C27"]["candidate_labels"], ["maxheight", "maxwidth"],
                 "dimension ambiguity retained")
    checks.equal(codes["BE", "BE:C27"]["direct_superclasses"],
                 [SIGN + "DimensionRestrictionSign"], "conservative ambiguity superclass")
    return checks.count, manifest, curation


def classification(backend, data, manifest, curation):
    checks = Checks()
    graph = load_graph()
    # Exhaustive coverage probes are distinct individuals, not production facts.
    for index, record in enumerate(manifest["labels"]):
        graph.add((E[f"coverage_label_{index}"], S.observedYoloLabel, Literal(record["label"])))
    for index, record in enumerate(manifest["codes"]):
        probe = E[f"coverage_code_{index}"]
        graph.add((probe, S.observedCountry, Literal(record["country"])))
        graph.add((probe, S.observedNationalCode, Literal(record["code"])))
    reasoner = Reasoner(graph, profile="L0", backend=backend)
    checks.equal(reasoner.consistency, "consistent", f"{backend}/consistent")
    checks.equal(reasoner.stats["complete"], True, f"{backend}/complete")
    fixture_ids = {E[sign["id"]] for sign in data["signs"]}
    fixture_types = {}
    for sign in data["signs"]:
        subject = E[sign["id"]]
        actual = reasoner.types(subject)
        fixture_types[sign["id"]] = sorted(str(value) for value in actual)
        for name in sign["expected_classes"]:
            checks.equal(S[name] in actual, True, f"{backend}/{sign['id']}/{name}")
        for name in sign["forbidden_classes"]:
            checks.equal(S[name] in actual, False, f"{backend}/{sign['id']}/not-{name}")
        checks.equal(reasoner.property_values(subject, S.locatedAtNode), {E[sign["node"]]},
                     f"{backend}/{sign['id']}/node")
        checks.equal(reasoner.property_values(subject, S.onRoadSegment), {E[sign["segment"]]},
                     f"{backend}/{sign['id']}/road-segment")
    for category, expected in data["expected_queries"].items():
        checks.equal(reasoner.instances(S[category]) & fixture_ids, {E[name] for name in expected},
                     f"{backend}/instances/{category}")
    for node in data["nodes"]:
        checks.equal(reasoner.entails(E[node["id"]], RDF.type, OSM.Node), True, "OSM node")
        for coordinate in ("latitude", "longitude"):
            # The reasoner may expose value-equal integer/decimal aliases.
            values = reasoner.property_values(E[node["id"]], OSM[coordinate])
            checks.equal(bool(values), True, f"node {coordinate} present")
            checks.equal({value.toPython() for value in values}, {Decimal(node[coordinate])},
                         f"node {coordinate} numeric value")
    for index, segment in enumerate(data["segments"]):
        checks.equal(reasoner.entails(E[segment["id"]], RDF.type, OSM.Way), True, "segment is Way")
        checks.equal(reasoner.property_values(E[segment["id"]], OSM.partOfRoad),
                     {E[data["road_route"]["id"]]}, "explicit road association")
        checks.equal(reasoner.property_values(E[f"route_member_{index}"], OSM.memberType),
                     {Literal("way")}, "explicit relation member type")
    checks.equal(reasoner.entails(E[data["road_route"]["id"]], RDF.type, OSM.Relation),
                 True, "road route is Relation")
    for index, record in enumerate(manifest["labels"]):
        actual = reasoner.types(E[f"coverage_label_{index}"])
        expected = {URIRef(record["class"])} | {S[c] for c in record["ancestor_categories"]}
        checks.equal(actual & {S[c] for c in curation["parents"]},
                     expected - {URIRef(record["class"])}, f"all-label categories/{record['label']}")
        checks.equal(URIRef(record["class"]) in actual, True, f"all-label type/{record['label']}")
        checks.equal(any(str(value).startswith(SIGN + "Code_") for value in actual), False,
                     "YOLO classification does not invent national observations")
    for index, record in enumerate(manifest["codes"]):
        actual = reasoner.types(E[f"coverage_code_{index}"])
        checks.equal(URIRef(record["class"]) in actual, True, "exact observed country/code")
        inferred_types = {str(value) for value in actual if str(value).startswith(SIGN + "Type_")}
        expected_types = set() if record["ambiguous"] else {record["direct_superclasses"][0]}
        checks.equal(inferred_types, expected_types, f"code candidates/{record['country']}/{record['code']}")
        checks.equal(actual & {S[c] for c in curation["parents"]},
                     {S[c] for c in record["common_categories"]}, "common categories only")
    # No mapping equivalences are emitted. No cross-country assertion follows
    # merely from recognizing a visual type or a different country's code.
    taxonomy = parse_dlp((ROOT / "taxonomy.dlp").read_text(encoding="utf-8"))
    checks.equal(list(taxonomy.triples((None, OWL.equivalentClass, None))), [], "no code equivalences")
    return {"backend": backend, "checks": checks.count, "complete": True,
            "rules": reasoner.stats["rules"], "fixture_types": fixture_types}


def distances(data):
    checks = Checks()
    nodes = {node["id"]: node for node in data["nodes"]}
    signs = {sign["id"]: sign for sign in data["signs"]}

    def distance(first, second):
        left, right = (nodes[signs[name]["node"]] for name in (first, second))
        return equatorial_distance(left["latitude"], left["longitude"],
                                   right["latitude"], right["longitude"])

    results = []
    for case in data["geodesic_cases"]:
        metres = distance(case["from"], case["to"])
        checks.close(metres, case["metres"], f"ellipsoid/{case['from']}/{case['to']}")
        results.append({"from": case["from"], "to": case["to"], "metres": metres})
    for case in data["nearby_cases"]:
        actual = sorted(name for name in data["expected_queries"][case["class"]]
                        if not (case["exclude_anchor"] and name == case["anchor"])
                        and distance(case["anchor"], name) <= case["radius_metres"])
        checks.equal(actual, case["expected"], "reference category plus distance filter")
    checks.equal(distance("stop_a", "stop_a"), 0, "self distance")
    checks.close(equatorial_distance(0, 179.999, 0, -179.999), 222.63898158654715,
                 "short equatorial antimeridian arc")
    for coordinates in ((1, 0, 0, 0), (0, 0, 0, 2), (0, 181, 0, 0), (0, 0, 0, math.nan)):
        try:
            equatorial_distance(*coordinates)
        except ValueError:
            checks.count += 1
        else:
            raise AssertionError("Analytic reference accepted unsupported coordinates")
    road = data["road_provider_reference"]
    road_results = []
    for case in road["cases"]:
        metres = road_distance(road["edges"], signs[case["from"]]["node"],
                               signs[case["to"]]["node"])
        status = "UNREACHABLE" if metres is None else "OK"
        checks.equal(status, case["status"], "reference route status")
        checks.equal(metres, case["metres"], "reference route distance")
        road_results.append({"from": case["from"], "to": case["to"], "status": status,
                             "metres": metres})
    # Same RoadRoute membership has no bearing on connectivity in the reference.
    checks.equal(road_results[3]["status"], "UNREACHABLE", "disconnected road relation")
    return {"checks": checks.count, "dlp_builtins_executed": False,
            "geodesic_reference": "analytic short equatorial WGS84 arcs",
            "geodesic_results": results, "road_reference": road["provider"],
            "road_results": road_results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("python", "native", "both"), default="python")
    args = parser.parse_args()
    provenance_checks, manifest, curation = check_provenance()
    data = json.loads((ROOT / "fixtures.json").read_text(encoding="utf-8"))
    backends = ("python", "native") if args.backend == "both" else (args.backend,)
    engine = [classification(backend, data, manifest, curation) for backend in backends]
    if len(engine) == 2 and engine[0]["fixture_types"] != engine[1]["fixture_types"]:
        raise AssertionError("Python/native fixture classification differs")
    for result in engine:
        del result["fixture_types"]
    print(json.dumps({"status": "PASS", "provenance_checks": provenance_checks,
                      "dlp_classification": engine, "separate_distance_references": distances(data)},
                     indent=2))


if __name__ == "__main__":
    main()
