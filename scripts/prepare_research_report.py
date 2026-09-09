"""Generate manuscript tables from preserved observations; never run benchmarks."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import statistics

from prepare_followup_report import prepare as prepare_followup
from prepare_hermit_report import prepare as prepare_hermit
from prepare_lookahead_report import prepare as prepare_lookahead
from prepare_final_report import prepare as prepare_final
from prepare_scientific_summary import prepare as prepare_scientific
from prepare_bach_report import prepare as prepare_bach

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/paper/generated"


def load(name):
    return json.loads((ROOT / name).read_text())


def table(name, caption, label, columns, header, rows):
    text = [r"\begin{table}[ht]", "\\caption{" + caption + "}",
            "\\label{" + label + "}", r"\centering\small",
            "\\begin{tabular}{@{}" + columns + "@{}}", r"\toprule",
            " & ".join(header) + r" \\", r"\midrule"]
    text.extend(" & ".join(row) + r" \\" for row in rows)
    text.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}", ""])
    (OUT / name).write_text("\n".join(text))


def matched(report, selection):
    rows = [r for r in report["results"]
            if all(r["case"].get(k) == v for k, v in selection.items())]
    if len(rows) != 1:
        raise ValueError(f"ambiguous historical selection: {selection}")
    return rows[0]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    inputs = ["benchmarks/research-results.json", "benchmarks/research-support-replay.json",
              "benchmarks/research-thesis-results.json", "benchmarks/results.json",
              "benchmarks/baselines/b1254c4/results.json"]
    primary, replay, final, previous, baseline = map(load, inputs)
    unary, support, points = [], [], []
    for c in primary["cases"]:
        case = c["case"]
        if case["family"] == "unary":
            s = c["summary"]["adaptive-only"]
            before = {r["block"]: r["update_seconds"] for r in c["runs"]
                      if r["configuration"] == "fixed-dred"}
            after = {r["block"]: r["update_seconds"] for r in c["runs"]
                     if r["configuration"] == "adaptive-dred"}
            assert abs(statistics.median(after[k] / before[k] for k in before)
                       - s["median_ratio"]) < 1e-12
            lo, hi = s["descriptive_paired_bootstrap_95_interval"]
            unary.append([case["mode"], str(case["width"]),
                          f'{1000*s["before_median_seconds"]:.3f}',
                          f'{1000*s["after_median_seconds"]:.3f}',
                          f'{s["median_ratio"]:.4f}', f"[{lo:.4f}, {hi:.4f}]"])
    for i, c in enumerate(replay["cases"]):
        case, s = c["case"], c["summary"]
        ratios = [p["workers"]["fixed-support"]["update_seconds"]
                  / p["workers"]["fixed-dred"]["update_seconds"] for p in c["pairs"]]
        assert abs(statistics.median(ratios) - s["median_ratio"]) < 1e-12
        lo, hi = s["descriptive_paired_bootstrap_95_interval"]
        old = c["original_factorial_support_only_summary"]
        support.append([case["mode"], str(case["depth"]),
                        f'{old["median_ratio"]:.4f}', f'{s["median_ratio"]:.4f}',
                        f"[{lo:.4f}, {hi:.4f}]"])
        points.append((i, s["median_ratio"], lo, hi, case["mode"], case["depth"]))
    table("unary-table.tex", "Complete-update unary results (nine paired process blocks). "
          "Milliseconds; ratio below one favors adaptive planning. Intervals are descriptive.",
          "tab:unary", "lrrrrl", ["Shape", "Width", "Fixed", "Adaptive", "Ratio", "95\\% interval"],
          unary)
    table("support-table.tex", "Certificate update ratios in the primary study and "
          "independent post-hoc replication. Each uses nine paired blocks per case.",
          "tab:support", "lrrrl", ["Shape", "Depth", "Primary", "Replay", "Replay 95\\% interval"],
          support)
    labels = [f'{mode} ({depth})' for _, _, _, _, mode, depth in points]
    figure = [r"\begin{figure}[ht]", r"\centering", r"\begin{tikzpicture}",
              r"\begin{axis}[width=0.88\linewidth,height=5.5cm,xmode=log,",
              r"xmin=0.1,xmax=1.5,ymin=-0.6,ymax=7.6,",
              "ytick={" + ",".join(str(p[0]) for p in points) + "},",
              "yticklabels={" + ",".join(labels) + "},",
              r"yticklabel style={font=\small},y dir=reverse,",
              r"xlabel={Certificate / ordinary DRed update time (log scale)},",
              r"xtick={0.125,0.25,0.5,1},xticklabels={0.125,0.25,0.5,1},",
              r"xmajorgrids=true,grid style={gray!20}]",
              r"\addplot[gray,dashed] coordinates {(1,-0.6) (1,7.6)};",
              r"\addplot[only marks,mark=*,black,error bars/.cd,x dir=both,x explicit]",
              "coordinates {"]
    for i, ratio, lo, hi, _, _ in points:
        figure.append(f"({ratio:.9f},{i}) += ({hi-ratio:.9f},0) -= ({ratio-lo:.9f},0)")
    figure += ["};", r"\end{axis}", r"\end{tikzpicture}",
               r"\caption{Post-hoc support replication. Points are median paired ratios; "
               r"bars are descriptive paired-bootstrap intervals. Values left of one "
               r"favor certificates; unsupported cycles expose their overhead.}",
               r"\label{fig:support}", r"\end{figure}", ""]
    (OUT / "support-figure.tex").write_text("\n".join(figure))
    selections = [
        ("Factored unions, width 64", {"kind": "factored-unions", "pairs": 64}, "materialize_seconds"),
        ("Enumerations, width 64", {"kind": "factored-enumerations", "pairs": 64}, "materialize_seconds"),
        ("Taxonomy D7/I15/PF", {"kind": "taxonomy", "depth": 7, "ipc": 15, "variant": "PF"}, "materialize_seconds"),
        ("Same taxonomy: subsumption", {"kind": "taxonomy", "depth": 7, "ipc": 15, "variant": "PF"}, "subsumption_seconds"),
        ("Transitive, 100", {"kind": "transitive", "size": 100}, "materialize_seconds"),
        ("Cardinality D5/I3", {"kind": "cardinality", "depth": 5, "ipc": 3}, "materialize_seconds"),
    ]
    rows = []
    for label, selection, metric in selections:
        records = [matched(r, selection) for r in (baseline, previous, final)]
        assert len({r["input_sha256"] for r in records}) == 1
        values = [1000*r[metric]["median"] for r in records]
        rows.append([label, *[f"{v:,.3f}" for v in values]])
    selection = {"kind": "maintenance", "depth": 5, "change_percent": 10}
    records = [matched(r, selection) for r in (baseline, previous, final)]
    assert len({r["input_sha256"] for r in records}) == 1
    for operation in ["rule_insert", "rule_replace", "rule_delete", "atomic_mixed"]:
        values = [1000*r["maintenance_operations"][operation]["seconds"]["median"]
                  for r in records]
        rows.append(["D5/10\\% " + operation.replace("_", " "),
                     *[f"{v:,.3f}" for v in values]])
    table("historical-table.tex", "Selected historical medians (ms), five samples each. "
          "These are sequential local runs, not paired external-system comparisons. "
          "Materialization unless another operation is named.", "tab:historical", "lrrr",
          ["Workload/operation", "b1254c4", "8ce254f", "5531be4"], rows)
    inputs.append("benchmarks/lubm-results.json")
    lubm = load(inputs[-1])
    assert lubm["all_reference_answers_match"]
    lubm_rows = []
    for configuration in ("b1254c4", "current-fixed", "current-adaptive"):
        s = lubm["summary"][configuration]
        lubm_rows.append([configuration,
                          f'{s["parse_and_reasoner_seconds"]["median"]:.3f}',
                          f'{s["compile_seconds"]["median"]:.3f}',
                          f'{s["materialize_seconds"]["median"]:.3f}',
                          f'{1000*s["query_seconds"]["median"]:.3f}'])
    table("lubm-table.tex", "Official LUBM(1,0), three fresh processes per configuration. "
          "Loading/reasoning times are seconds; the fully consumed fourteen-query total "
          "is milliseconds. Earlier current state is commit 5531be4.", "tab:lubm", "lrrrr",
          ["Configuration", "Parse + reasoner", "Compile", "Materialize", "Queries (ms)"], lubm_rows)
    inputs.extend(prepare_followup(table, OUT))
    inputs.extend(prepare_hermit(table, OUT))
    inputs.extend(prepare_lookahead(table, OUT))
    inputs.extend(prepare_final(table, OUT))
    inputs.extend(prepare_scientific(OUT))
    inputs.extend(prepare_bach(table, OUT))
    manifest = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in inputs}
    (OUT / "input-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Generated {len(unary)} unary and {len(support)} support rows, "
          f"{len(rows)} historical comparisons")


if __name__ == "__main__":
    main()
