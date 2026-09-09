"""Check the post-hoc single-component study and generate all reported tables."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tarfile

from prepare_followup_report import median, require

ROOT = Path(__file__).resolve().parents[1]


def prepare(table, output):
    name = "benchmarks/external-lookahead-results.json"
    protocol_name = "benchmarks/external-lookahead-results-protocol.json"
    report = json.loads((ROOT / name).read_text())
    require(hashlib.sha256((ROOT / protocol_name).read_bytes()).hexdigest()
            == report["protocol_sha256"], "lookahead protocol changed")
    protocol = json.loads((ROOT / protocol_name).read_text())
    for key in ("protocol", "source_sha256", "driver_sha256", "source_archive", "manifest"):
        require(report[key] == protocol[key], "lookahead frozen protocol changed")
    require(hashlib.sha256((ROOT / report["discovery_report"]).read_bytes()).hexdigest()
            == report["discovery_sha256"], "discovery artifact changed")
    archive = report["source_archive"]
    require(hashlib.sha256((ROOT / archive["archive"]).read_bytes()).hexdigest()
            == archive["archive_sha256"], "lookahead source archive changed")
    hashes = {**archive["source_sha256"], **archive["driver_sha256"]}
    with tarfile.open(ROOT / archive["archive"], "r:gz") as source:
        require(sorted(source.getnames()) == sorted(hashes), "source archive member mismatch")
        for member in source.getmembers():
            require(member.isfile(), "non-file in source archive")
            require(hashlib.sha256(source.extractfile(member).read()).hexdigest()
                    == hashes[member.name], "source archive payload mismatch")
    configurations = ("b1254c4", "compiled", "lookahead")
    cases = [f"sf{scale}-q{query}" for scale in (0.01, 0.1) for query in (3, 5, 9)]
    controls = ["control-" + c for c in ("unique", "nonselective", "skewed", "empty-cycle")]
    blocks = report["protocol"]["blocks"]
    workers = report["workers"]
    require(blocks == 3 and len(workers) == 90, "unexpected lookahead study size")
    require({(w["case"], w["configuration"], w["block"]) for w in workers}
            == {(case, c, b) for case in cases + controls for c in configurations for b in range(blocks)},
            "lookahead pairing mismatch")
    baseline_sources = {}
    pairs = {}
    rows, control_rows = [], []
    for case in cases + controls:
        selected = [w for w in workers if w["case"] == case]
        reference = selected[0]["queries"][0]
        for worker in selected:
            require(len(worker["queries"]) == 1, "component process reused")
            query = worker["queries"][0]
            require(query["exact_base_closure_match"] and query[
                "exact_independent_match" if case in controls else "exact_sql_match"],
                "lookahead semantic validation failed")
            input_key = "source_facts_sha256" if case in controls else "relation_sha256"
            require(query["answer_sha256"] == reference["answer_sha256"]
                    and query[input_key] == reference[input_key], "lookahead input/answer drift")
            median([sum(query[k] for k in ("filter_projection_seconds", "encoding_seconds",
                                          "index_materialization_seconds", "join_seconds"))],
                   query["component_end_to_end_seconds"])
            if worker["configuration"] == "b1254c4":
                baseline_sources.setdefault("hashes", worker["source_sha256"])
                require(worker["source_sha256"] == baseline_sources["hashes"], "baseline source drift")
            else:
                require(worker["source_sha256"] == report["source_sha256"], "candidate source drift")
                flags = worker["engine_flags"]
                require(all(flags[k] for k in ("_compiled_joins_enabled", "_incremental_index_enabled",
                                              "_incremental_validation_enabled")), "adopted flags differ")
                require(flags["_join_lookahead_enabled"] == (worker["configuration"] == "lookahead"),
                        "lookahead flag differs")
                stats = query["stats"]
                require(stats.get("lookahead_probe_lookups", 0) <= 1024
                        and stats.get("lookahead_hint_entries", 0) <= 1024
                        and stats.get("lookahead_sample_rows", 0) <= 8192, "lookahead budget exceeded")
            require(worker["driver_sha256"] == report["driver_sha256"]["benchmarks/external_lookahead.py"],
                    "wrong lookahead driver")
        pairs[case] = {}
        for denominator in ("b1254c4", "compiled"):
            pairs[case][denominator] = {}
            for metric in ("join_seconds", "component_end_to_end_seconds", "subprocess_wall_seconds"):
                values = []
                for block in range(blocks):
                    pair = {w["configuration"]: w for w in selected if w["block"] == block}
                    def timing(w):
                        return w[metric] if metric == "subprocess_wall_seconds" else w["queries"][0][metric]
                    values.append(timing(pair["lookahead"]) / timing(pair[denominator]))
                saved = report["paired_ratios"][case][denominator][metric]
                require(values == saved["ratios_by_block"], "lookahead paired raw ratio differs")
                ratio = median(values, saved["median"])
                require(min(values) == saved["minimum"] and max(values) == saved["maximum"],
                        "lookahead paired range differs")
                pairs[case][denominator][metric] = ratio
        label = case.replace("control-", "").replace("sf", "").replace("-q", "/Q")
        row = [label]
        for configuration in configurations:
            raw = [w["queries"][0]["join_seconds"] for w in selected if w["configuration"] == configuration]
            value = median(raw, report["summary"][case][configuration]["join_seconds"]["median"])
            row.append(f"{1000*value:,.3f}")
        row += [f'{pairs[case]["compiled"][metric]:.3f}' for metric in
                ("join_seconds", "component_end_to_end_seconds", "subprocess_wall_seconds")]
        (control_rows if case in controls else rows).append(row)
    header = ["Case", "b1254c4", "Compiled", "Lookahead", "Join", "Total", "Process"]
    caption = ("Single-component fresh-process study: median join milliseconds, followed by "
               "paired lookahead/compiled time ratios for join, component total, and complete "
               "process. Three balanced blocks; ratios below one favor lookahead.")
    table("lookahead-table.tex", caption, "tab:lookahead", "lrrrrrr", header, rows)
    table("lookahead-controls-table.tex", "Synthetic adverse controls using the same protocol and "
          "columns as Table~\\ref{tab:lookahead}. All planning and complete result enumeration "
          "are charged to the join interval.", "tab:lookahead-controls", "lrrrrrr", header, control_rows)
    (output / "lookahead-paired-ratios.json").write_text(json.dumps(pairs, indent=2) + "\n")
    return [name, protocol_name, archive["archive"], "benchmarks/external-lookahead-source-manifest.json"]
