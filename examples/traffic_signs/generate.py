"""Deterministically render the reviewed traffic-sign crosswalk and fixtures.

Only this directory's retained inputs are read. The original CSV is provenance,
not a runtime dependency. No network requests or geometry providers are used.
"""

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent
SIGN = "https://example.org/traffic-sign#"
EXAMPLE = "https://example.org/traffic-sign/example#"
COUNTRIES = ("DE", "FR", "NL", "CH", "BE")
SOURCE_FILE = "source/panoramax-road_signs_mapping.csv"
SOURCE_SHA256 = "a1e7ad5d7e2829d3214226fd9f20e3778c90f4b8f532d82ba933d4e61c1395e9"
SOURCE_ORIGIN = (
    "/Users/raphaelvolz/Github/Woladen.de-analytics/deploy/prolix/"
    "class_maps/panoramax-road_signs_mapping.csv"
)


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def quoted(value):
    return json.dumps(value, ensure_ascii=False)


def local_name(prefix, value):
    """Readable names; callers reject collisions instead of overwriting them."""
    return prefix + re.sub(r"[^A-Za-z0-9_]", "_", value)


def code_tokens(cell):
    """An explicit semicolon separates alternatives; preserve exact raw tokens.

    This snapshot has no multi-code cells. Spaces/case/spelling are not silently
    normalized, and bracketed values such as FR:B14[30] remain one code. The
    original cell is retained independently, including blanks or empty tokens.
    """
    return [] if cell == "" else cell.split(";")


def ancestors(category, parents, active=()):
    if category in active:
        raise ValueError(f"Cyclic category hierarchy: {active + (category,)}")
    result = {category}
    for parent in parents[category]:
        result.update(ancestors(parent, parents, active + (category,)))
    return result


def categories_for(label, curation):
    return curation["label_categories"].get(label, ["UnclassifiedSign"])


def mapping():
    content = (ROOT / SOURCE_FILE).read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if digest != SOURCE_SHA256:
        raise ValueError("Source snapshot changed; review it and update its pinned SHA-256")
    reader = csv.DictReader(io.StringIO(content.decode("utf-8"), newline=""))
    if reader.fieldnames != ["YOLO", *COUNTRIES]:
        raise ValueError(f"Unexpected CSV columns: {reader.fieldnames!r}")
    raw_rows = list(reader)
    if any(set(row) != set(reader.fieldnames) or None in row.values() for row in raw_rows):
        raise ValueError("Malformed CSV row")
    curation_bytes = (ROOT / "curation.json").read_bytes()
    curation = json.loads(curation_bytes)
    parents = curation["parents"]
    for name in parents:
        if "TrafficSign" not in ancestors(name, parents):
            raise ValueError(f"Category has no TrafficSign ancestor: {name}")
    labels = sorted({row["YOLO"] for row in raw_rows})
    if "" in labels:
        raise ValueError("An empty YOLO label requires explicit review")
    obsolete = set(curation["label_categories"]) - set(labels)
    if obsolete:
        raise ValueError(f"Curated labels absent from snapshot: {sorted(obsolete)}")
    label_records = {}
    seen_names = set(parents)
    for label in labels:
        name = local_name("Type_", label)
        if name in seen_names:
            raise ValueError(f"Generated class name collision: {name}")
        seen_names.add(name)
        categories = categories_for(label, curation)
        inherited = set().union(*(ancestors(c, parents) for c in categories))
        label_records[label] = {
            "label": label, "class": SIGN + name, "categories": categories,
            "ancestor_categories": sorted(inherited), "csv_lines": [],
            "curated": label in curation["label_categories"],
        }
    codes = defaultdict(lambda: {"labels": set(), "csv_lines": []})
    rows = []
    for line, row in enumerate(raw_rows, 2):
        label_records[row["YOLO"]]["csv_lines"].append(line)
        tokens = {country: code_tokens(row[country]) for country in COUNTRIES}
        rows.append({"csv_line": line, "raw": row, "code_tokens": tokens})
        for country in COUNTRIES:
            for code in tokens[country]:
                if not code:  # retained as a token, never promoted into a code class
                    continue
                codes[country, code]["labels"].add(row["YOLO"])
                codes[country, code]["csv_lines"].append(line)
    code_records = []
    for (country, code), entry in sorted(codes.items()):
        name = local_name(f"Code_{country}_", code)
        if name in seen_names:
            raise ValueError(f"Generated class name collision: {name}")
        seen_names.add(name)
        candidates = sorted(entry["labels"])
        common = set.intersection(*(
            set(label_records[label]["ancestor_categories"]) for label in candidates
        ))
        # Keep the most specific common categories in this curated DAG.
        specific = sorted(c for c in common if not any(
            c != other and c in ancestors(other, parents) for other in common
        ))
        inferred = ([label_records[candidates[0]]["class"]] if len(candidates) == 1
                    else [SIGN + c for c in specific])
        code_records.append({
            "country": country, "code": code, "class": SIGN + name,
            "candidate_labels": candidates, "csv_lines": entry["csv_lines"],
            "ambiguous": len(candidates) > 1, "common_categories": sorted(common),
            "direct_superclasses": inferred,
        })
    source = {
        "snapshot": SOURCE_FILE, "original_path": SOURCE_ORIGIN,
        "sha256": digest, "bytes": len(content), "encoding": "UTF-8",
        "captured_on": "2026-09-10", "columns": reader.fieldnames,
        "curation_sha256": hashlib.sha256(curation_bytes).hexdigest(),
        "source_role": "Crosswalk associations, not a hierarchy or legal authority",
        "license": "No license declaration supplied in this CSV; no license inferred",
        "multi_code_policy": "Split semicolons only; retain exact raw cells and tokens",
    }
    manifest = {"schema_version": 1, "source": source, "rows": rows,
                "labels": list(label_records.values()), "codes": code_records}
    summary = {
        "schema_version": 1, "source": source,
        "rows": len(rows), "distinct_yolo_labels": len(labels),
        "curated_labels": sum(record["curated"] for record in label_records.values()),
        "fallback_labels": [label for label, record in label_records.items()
                            if not record["curated"]],
        "category_count": len(parents), "national_code_classes": len(code_records),
        "blank_cells_by_country": {c: sum(row[c] == "" for row in raw_rows)
                                   for c in COUNTRIES},
        "multi_code_cells": [{"csv_line": row["csv_line"], "country": c,
                              "raw": row["raw"][c]} for row in rows for c in COUNTRIES
                             if len(row["code_tokens"][c]) > 1],
        "duplicate_labels": {label: count for label, count in
                             sorted(Counter(row["YOLO"] for row in raw_rows).items())
                             if count > 1},
        "ambiguous_codes": [record for record in code_records if record["ambiguous"]],
        "source_review_notes": [
            "pedestrian:start occurs twice; both rows and their mappings are retained.",
            "Zone:30:end, hazard:include:down and the FR-column value Fr:A8 are exact source spellings.",
            "Repeated national codes have candidate sets; no OWL equivalences or candidate intersections.",
            "Missing cells mean no mapping supplied; they are not negative assertions.",
        ],
    }
    return manifest, summary, curation


def taxonomy(manifest, curation):
    lines = [
        "// Generated by generate.py from the pinned crosswalk and explicit curation.json.",
        "// Crosswalk associations are not legal equivalences; missing mappings are unknown.",
        f"Namespace(sign = <{SIGN}>)", "Namespace(osm = <https://example.org/osm#>)", "",
        "Ontology(",
        '  Annotation(rdfs:label "Project-curated traffic-sign crosswalk taxonomy")',
        "  ObjectProperty(sign:locatedAtNode domain(sign:TrafficSign) range(osm:Node))",
        "  ObjectProperty(sign:onRoadSegment domain(sign:TrafficSign) range(osm:RoadSegment))",
        "  DatatypeProperty(sign:observedYoloLabel domain(sign:TrafficSign))",
        "  DatatypeProperty(sign:observedCountry domain(sign:TrafficSign))",
        "  DatatypeProperty(sign:observedNationalCode domain(sign:TrafficSign))",
    ]
    for category, parents in sorted(curation["parents"].items()):
        suffix = " ".join("sign:" + parent for parent in parents)
        lines.append(f"  Class(sign:{category} partial {suffix})")
    for record in manifest["labels"]:
        name = record["class"][len(SIGN):]
        categories = " ".join("sign:" + category for category in record["categories"])
        lines.extend([
            f"  Class(sign:{name} partial",
            f"    annotation(rdfs:label {quoted(record['label'])}) {categories})",
            "  SubClassOf(restriction(sign:observedYoloLabel value("
            f"{quoted(record['label'])})) sign:{name})",
        ])
    for record in manifest["codes"]:
        name = record["class"][len(SIGN):]
        supers = " ".join("sign:" + iri[len(SIGN):] for iri in record["direct_superclasses"])
        lines.extend([
            f"  Class(sign:{name} partial",
            f"    annotation(rdfs:label {quoted(record['country'] + ' mapping: ' + record['code'])}) {supers})",
            "  SubClassOf(intersectionOf(sign:TrafficSign",
            f"    restriction(sign:observedCountry value({quoted(record['country'])}))",
            f"    restriction(sign:observedNationalCode value({quoted(record['code'])})))",
            f"    sign:{name})",
        ])
    lines.append(")")
    return "\n".join(lines) + "\n"


def fixture_dlp(data):
    lines = ["// Generated from fixtures.json. All coordinates and OSM IDs are synthetic.",
             f"Namespace(ex = <{EXAMPLE}>)", f"Namespace(sign = <{SIGN}>)",
             "Namespace(osm = <https://example.org/osm#>)", "", "Ontology("]
    for node in data["nodes"]:
        lines.extend([
            f"  Individual(ex:{node['id']} type(osm:Node)",
            f"    value(osm:osmId {quoted(str(node['osm_id']))}^^xsd:integer)",
            f"    value(osm:latitude {quoted(node['latitude'])}^^xsd:decimal)",
            f"    value(osm:longitude {quoted(node['longitude'])}^^xsd:decimal))",
        ])
    lines.append(f"  Individual(ex:{data['road_route']['id']} type(osm:RoadRoute)"
                 f" value(osm:osmId {quoted(str(data['road_route']['osm_id']))}^^xsd:integer))")
    for index, segment in enumerate(data["segments"]):
        lines.extend([
            f"  Individual(ex:{segment['id']} type(osm:RoadSegment)",
            f"    value(osm:osmId {quoted(str(segment['osm_id']))}^^xsd:integer)",
            f"    value(osm:partOfRoad ex:{data['road_route']['id']}))",
            f"  Individual(ex:route_member_{index} type(osm:RelationMembership)",
            f"    value(osm:ownerRelation ex:{data['road_route']['id']})",
            f"    value(osm:memberElement ex:{segment['id']})",
            '    value(osm:memberType "way")',
            f"    value(osm:position {quoted(str(index))}^^xsd:integer)",
            '    value(osm:role ""))',
        ])
        for position, node in enumerate(segment["nodes"]):
            lines.extend([
                f"  Individual(ex:{segment['id']}_node_{position} type(osm:WayNode)",
                f"    value(osm:ownerWay ex:{segment['id']}) value(osm:memberNode ex:{node})",
                f"    value(osm:position {quoted(str(position))}^^xsd:integer))",
            ])
    for sign in data["signs"]:
        extra_types = "".join(f" type(sign:{category})"
                              for category in sign.get("asserted_categories", []))
        lines.extend([
            f"  Individual(ex:{sign['id']} type(sign:TrafficSign){extra_types}",
            f"    value(sign:locatedAtNode ex:{sign['node']})",
            f"    value(sign:onRoadSegment ex:{sign['segment']})",
        ])
        if "yolo_label" in sign:
            lines.append(f"    value(sign:observedYoloLabel {quoted(sign['yolo_label'])})")
        if "country" in sign:
            lines.append(f"    value(sign:observedCountry {quoted(sign['country'])})")
        if "national_code" in sign:
            lines.append(f"    value(sign:observedNationalCode {quoted(sign['national_code'])})")
        lines[-1] += ")"
    lines.append(")")
    return "\n".join(lines) + "\n"


def outputs():
    manifest, summary, curation = mapping()
    fixture = json.loads((ROOT / "fixtures.json").read_text(encoding="utf-8"))
    return {"taxonomy.dlp": taxonomy(manifest, curation), "mapping.json": json_text(manifest),
            "mapping-summary.json": json_text(summary), "fixtures.dlp": fixture_dlp(fixture)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check retained output without writing")
    args = parser.parse_args()
    stale = []
    for name, text in outputs().items():
        path = ROOT / name
        if args.check:
            if not path.exists() or path.read_bytes() != text.encode("utf-8"):
                stale.append(name)
        else:
            path.write_bytes(text.encode("utf-8"))
    if stale:
        parser.exit(1, f"Stale generated artifacts: {', '.join(stale)}\n")
    print("PASS: generated traffic-sign artifacts match" if args.check
          else "Generated taxonomy, mapping manifest/summary and fixture DLP")


if __name__ == "__main__":
    main()
