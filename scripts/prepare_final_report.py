"""Generate the final production comparison without replacing any old evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import statistics

from prepare_followup_report import median, require

ROOT = Path(__file__).resolve().parents[1]


def prepare(table, output):
    names = ["benchmarks/followup-thesis-results.json", "benchmarks/research-thesis-results.json",
             "benchmarks/baselines/b1254c4/results.json"]
    final, previous, baseline = [json.loads((ROOT / n).read_text()) for n in names]
    require(hashlib.sha256((ROOT / names[-1]).read_bytes()).hexdigest()
            == "6f0bc493cae0fb96b474405eb9496dc9ce2c3155b313f2bcd3de49b3dc8b51e2",
            "fixed baseline changed")
    require(final["repeats"] == 5 and final["planned_cases"] == 54 and len(final["results"]) == 54,
            "final production suite incomplete")
    require(all(r["validation"] == "passed" for r in final["results"]), "production validation failed")
    require(final["source_integrity"]["verified"], "final source changed during measurement")
    archived = json.loads((ROOT / "benchmarks/external-lookahead-source-manifest.json").read_text())
    require(all(final["environment"]["source_sha256"][name] == digest
                for name, digest in archived["source_sha256"].items()),
            "final production package differs from the frozen follow-up package")
    comparison = final["comparison"]
    require(len(comparison["matched"]) == 51 and len(comparison["skipped"]) == 3,
            "unexpected historical coverage")
    require(all(r["correctness"]["verified"] for r in comparison["matched"]), "historical control mismatch")
    require(comparison["baseline_provenance"]["verified"], "unverified historical baseline")

    def matched(report, selection):
        records = [r for r in report["results"] if all(r["case"].get(k) == v for k, v in selection.items())]
        require(len(records) == 1, "ambiguous production table selection")
        return records[0]

    selections = [
        ("Unions, 64 pairs", {"kind": "factored-unions", "pairs": 64}, "materialize_seconds"),
        ("Enumerations, 64 pairs", {"kind": "factored-enumerations", "pairs": 64}, "materialize_seconds"),
        ("Taxonomy D7/I15/PF", {"kind": "taxonomy", "depth": 7, "ipc": 15, "variant": "PF"}, "materialize_seconds"),
        ("Same: subsumption", {"kind": "taxonomy", "depth": 7, "ipc": 15, "variant": "PF"}, "subsumption_seconds"),
        ("Transitive, 100", {"kind": "transitive", "size": 100}, "materialize_seconds"),
        ("Cardinality D5/I3", {"kind": "cardinality", "depth": 5, "ipc": 3}, "materialize_seconds"),
    ]
    rows = []
    for label, selection, metric in selections:
        records = [matched(r, selection) for r in (baseline, previous, final)]
        require(len({r["input_sha256"] for r in records}) == 1, "production input mismatch")
        values = [median(r[metric]["samples"], r[metric]["median"]) for r in records]
        rows.append([label, *[f"{1000*v:,.3f}" for v in values], f"{values[-1]/values[0]:.3f}"])
    selection = {"kind": "maintenance", "depth": 5, "change_percent": 10}
    records = [matched(r, selection) for r in (baseline, previous, final)]
    require(len({r["input_sha256"] for r in records}) == 1, "production maintenance input mismatch")
    for operation in ("rule_insert", "rule_replace", "rule_delete", "atomic_mixed"):
        values = [median(r["maintenance_operations"][operation]["seconds"]["samples"],
                         r["maintenance_operations"][operation]["seconds"]["median"]) for r in records]
        rows.append(["D5/10\\% " + operation.replace("_", " "),
                     *[f"{1000*v:,.3f}" for v in values], f"{values[-1]/values[0]:.3f}"])
    records = [matched(r, {"kind": "maintenance", "depth": 4, "change_percent": 15})
               for r in (baseline, previous, final)]
    require(len({r["input_sha256"] for r in records}) == 1, "production insertion input mismatch")
    values = [median(r["maintenance_operations"]["fact_insert"]["seconds"]["samples"],
                     r["maintenance_operations"]["fact_insert"]["seconds"]["median"]) for r in records]
    rows.append(["D4/15\\% fact insert", *[f"{1000*v:,.3f}" for v in values],
                 f"{values[-1]/values[0]:.3f}"])
    table("final-production-table.tex", "Final default configuration, selected historical "
          "medians in milliseconds (materialization unless specified). Five observations "
          "per case, sharing one worker. The ratio is final/b1254c4; these longitudinal "
          "observations are not an interleaved comparison.", "tab:final-production", "lrrrr",
          ["Workload/operation", "b1254c4", "5531be4", "Final", "Ratio"], rows)
    ratios = [r["phases"]["materialize_seconds"]["after_over_before"] for r in comparison["matched"]]
    worst = max(comparison["matched"], key=lambda r: r["phases"]["materialize_seconds"]["after_over_before"])
    (output / "final-production-summary.json").write_text(json.dumps({
        "matched_cases": 51, "new_cases": 3, "observations": 270,
        "materialization_case_geometric_mean_ratio": statistics.geometric_mean(ratios),
        "materialization_ratio_range": [min(ratios), max(ratios)],
        "worst_materialization_case": worst["case"],
    }, indent=2) + "\n")
    return names + ["benchmarks/followup-validation.json"]
