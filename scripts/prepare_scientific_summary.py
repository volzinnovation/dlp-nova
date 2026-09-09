"""Generate the accessible findings overview from preserved experimental data.

This script checks the displayed comparisons against their original paired
observations. It never launches a reasoner or changes a benchmark artifact.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import random
import statistics

ROOT = Path(__file__).resolve().parents[1]
INPUTS = (
    "benchmarks/research-support-replay.json",
    "benchmarks/lubm-results.json",
    "benchmarks/zodiac-results.json",
    "benchmarks/zodiac-native-results.json",
    "benchmarks/external-lookahead-results.json",
    "benchmarks/owl-bridge-results.json",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def equal(actual, expected, message):
    require(math.isfinite(actual) and math.isfinite(expected)
            and math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12), message)


def paired(workers, before, after, metric, stored, arm_key="configuration"):
    """Pair by block; check the stored raw ratios and their median."""
    selected = [w for w in workers if w[arm_key] in (before, after)]
    blocks = sorted({w["block"] for w in selected})
    require(len(selected) == 2 * len(blocks), "Incomplete or duplicate paired observations")
    ratios = []
    for block in blocks:
        group = [w for w in selected if w["block"] == block]
        require(len(group) == 2 and {w[arm_key] for w in group} == {before, after},
                "Paired configurations differ")
        times = {w[arm_key]: metric(w) for w in group}
        require(all(math.isfinite(t) and t > 0 for t in times.values()), "Invalid timing")
        ratios.append(times[after] / times[before])
    saved = stored.get("raw", stored.get("ratios_by_block"))
    require(len(saved) == len(ratios), "Stored pair count differs")
    for actual, expected in zip(ratios, saved, strict=True):
        equal(actual, expected, "Stored paired ratio differs from raw observations")
    result = statistics.median(ratios)
    equal(result, stored["median"], "Stored paired median differs")
    return result


def support_points(report):
    modes = ("alternate-support", "mixed-new-support", "unique-signatures", "unsupported-cycle")
    expected_cases = {(mode, depth) for mode in modes for depth in (4, 32)}
    require(report["status"] == "passed" and report["validated_workers"] == 144,
            "Support replication did not complete")
    require(len(report["cases"]) == 8 and {
        (c["case"]["mode"], c["case"]["depth"]) for c in report["cases"]
    } == expected_cases, "Support case matrix differs")
    result = {}
    for case in report["cases"]:
        require(case["case"]["size"] == 256, "Support population differs")
        pairs = sorted(case["pairs"], key=lambda p: p["pair"])
        require([p["pair"] for p in pairs] == list(range(9)), "Support pairing differs")
        ratios, before, after = [], [], []
        for pair in pairs:
            require(pair["hash_seed"] == 3000 + pair["pair"], "Support paired seed differs")
            ordinary, shared = (pair["workers"][c] for c in ("fixed-dred", "fixed-support"))
            for worker in (ordinary, shared):
                require(worker["validation"] == "passed" and worker["case"] == case["case"],
                        "Support correctness check failed")
                require(worker["hash_seed"] == str(pair["hash_seed"]), "Support worker seed differs")
            for key in ("input_sha256", "initial_sha256", "final_sha256", "final_facts",
                        "final_assertions_sha256", "final_rules_sha256"):
                require(ordinary[key] == shared[key], "Support paired inputs or answers differ")
            before.append(ordinary["update_seconds"])
            after.append(shared["update_seconds"])
            require(all(math.isfinite(t) and t > 0 for t in (before[-1], after[-1])),
                    "Invalid support timing")
            ratios.append(after[-1] / before[-1])
        summary = case["summary"]
        for actual, expected in zip(ratios, summary["paired_ratios"], strict=True):
            equal(actual, expected, "Support stored paired ratio differs")
        center = statistics.median(ratios)
        equal(center, summary["median_ratio"], "Support median differs")
        equal(statistics.median(before), summary["before_median_seconds"], "Support time differs")
        equal(statistics.median(after), summary["after_median_seconds"], "Support time differs")
        randomizer = random.Random(2004)
        resampled = sorted(statistics.median(randomizer.choices(ratios, k=9)) for _ in range(2000))
        interval = (resampled[50], resampled[1949])
        for actual, expected in zip(interval, summary["descriptive_paired_bootstrap_95_interval"], strict=True):
            equal(actual, expected, "Support bootstrap interval differs")
        result[(case["case"]["mode"], case["case"]["depth"])] = (center, *interval)
    return modes, result


def prepare(output):
    """Write the scientific overview and return its unmodified input filenames."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    support, lubm, zodiac, native, lookahead, hermit = (
        json.loads((ROOT / name).read_text()) for name in INPUTS
    )
    modes, points = support_points(support)

    require(len(lubm["workers"]) == 9 and lubm["all_reference_answers_match"],
            "LUBM evaluation incomplete")
    require({(w["configuration"], w["block"]) for w in lubm["workers"]}
            == {(c, b) for c in ("b1254c4", "current-fixed", "current-adaptive") for b in range(3)},
            "LUBM repetitions differ")
    for worker in lubm["workers"]:
        require(len(worker["queries"]) == 14 and {q["query"] for q in worker["queries"]}
                == set(range(1, 15)), "LUBM query set differs")
        require(all(q["exact_match"] and q["missing"] == q["unexpected"] == 0
                    for q in worker["queries"]), "LUBM reference answer mismatch")

    require(len(zodiac["workers"]) == 16
            and all(w["all_complete_tuple_digests_match_naive"] for w in zodiac["workers"]),
            "Local rule-update evaluation incomplete")
    local = {}
    for marker in ("*", "#"):
        for operation in ("insert_seconds", "delete_seconds"):
            local[(marker, operation)] = paired(
                zodiac["workers"], "b1254c4", "candidate",
                lambda w, m=marker, op=operation: w["transactions"][m][op],
                zodiac["paired_ratios"]["candidate/b1254c4"][marker][operation])

    require(len(native["workers"]) == 8 and all(w["all_closures_match"] for w in native["workers"]),
            "External rule-update evaluation incomplete")
    native_insert = paired(native["workers"], "native", "candidate",
                           lambda w: w["transactions"]["*"]["insert_seconds"],
                           native["paired_candidate_over_native"]["*"]["insert_seconds"], "arm")
    native_delete = paired(native["workers"], "native", "candidate",
                           lambda w: w["transactions"]["#"]["delete_seconds"],
                           native["paired_candidate_over_native"]["#"]["delete_seconds"], "arm")

    query_ratios = {}
    for case in ("sf0.1-q5", "control-unique", "control-nonselective", "control-skewed", "control-empty-cycle"):
        workers = [w for w in lookahead["workers"] if w["case"] == case]
        require(len(workers) == 9, "Query comparison incomplete")
        for worker in workers:
            require(len(worker["queries"]) == 1, "More than one query in an observation")
            query = worker["queries"][0]
            correctness_key = "exact_independent_match" if case.startswith("control-") else "exact_sql_match"
            require(query[correctness_key] and query["exact_base_closure_match"],
                    "Query reference answer mismatch")
        query_ratios[case] = paired(workers, "compiled", "lookahead",
                                   lambda w: w["queries"][0]["join_seconds"],
                                   lookahead["paired_ratios"][case]["compiled"]["join_seconds"])

    hermit_ratios = []
    require(len(hermit["workers"]) == 27, "HermiT evaluation incomplete")
    for n in (100, 1000, 10000):
        workers = [w for w in hermit["workers"] if w["population"] == n]
        require(len(workers) == 9 and all(w["exact_match"] and w["consistent"]
                and w["positive_count"] == n and w["negative_count"] == 0 for w in workers),
                "HermiT reference answer mismatch")
        hermit_ratios.append(paired(workers, "hermit", "candidate", lambda w: w["task_seconds"],
                                   hermit["paired_ratios"][str(n)]["candidate/hermit"]["task_seconds"]))

    labels = ("Existing explanation survives", "Replacement explanation arrives",
              "Different starting facts", "No explanation survives")
    lines = [
        "% Generated from preserved paired observations. Do not edit by hand.",
        r"\begin{figure}[htbp]",
        r"\centering",
        r"\begin{tikzpicture}",
        r"\begin{axis}[width=0.70\linewidth,height=6.3cm,xmode=log,",
        r"xmin=0.1,xmax=1.6,ymin=-0.48,ymax=3.48,y dir=reverse,",
        r"ytick={0,1,2,3},",
        "yticklabels={" + ",".join("{" + label + "}" for label in labels) + "},",
        r"yticklabel style={font=\small},",
        r"xlabel={Relative update time (logarithmic scale)},",
        r"xtick={0.125,0.25,0.5,1},xticklabels={1/8,1/4,1/2,1},",
        r"xmajorgrids=true,grid style={gray!20},",
        r"legend style={at={(0.5,-0.28)},anchor=north,draw=none,font=\small,column sep=4pt},",
        r"legend columns=2]",
        r"\addplot[gray,dashed,forget plot] coordinates {(1,-0.48) (1,3.48)};",
    ]
    for depth, offset, marker in ((4, -0.12, "*"), (32, 0.12, "square*")):
        color = "black" if depth == 4 else "blue!65!black"
        lines += [rf"\addplot[only marks,mark={marker},{color},error bars/.cd,x dir=both,x explicit]",
                  "coordinates {"]
        for group, mode in enumerate(modes):
            center, low, high = points[(mode, depth)]
            lines.append(f"({center:.9f},{group + offset:.2f}) += ({high-center:.9f},0) -= ({center-low:.9f},0)")
        legend = "Shorter chain" if depth == 4 else "Longer chain"
        lines += ["};", "\\addlegendentry{" + legend + "}"]
    lines += [
        r"\end{axis}", r"\end{tikzpicture}",
        r"\caption{Sharing explanations reduces the cost of updating knowledge when conclusions "
        r"remain justified, but adds work when their justification disappears. "
        r"The experiment changes facts and rules in cyclic chains concerning 256 individuals; "
        r"the shorter and longer chains have four and 32 links before the cycle closes. "
        r"Points show median time with shared explanations divided by ordinary maintenance "
        r"time, from nine paired repetitions per case in an independent replication. "
        r"Bars show descriptive 95\% paired bootstrap intervals (2,000 resamples). "
        r"Values left of the dashed line indicate faster updating.}",
        r"\label{fig:scientific-support}", r"\end{figure}", "",
    ]
    additions = [1 / local[(m, "insert_seconds")] for m in ("*", "#")]
    removals = [1 / local[(m, "delete_seconds")] for m in ("*", "#")]
    adverse = [100 * (v - 1) for k, v in query_ratios.items() if k.startswith("control-")]
    hermit_speedups = [1 / v for v in hermit_ratios]
    rows = [
        ("University ontology", "Full LUBM ontology and its 14 standard questions.",
         "All reference answers recovered in every repetition."),
        ("Changes to rules", "Established university rule program, compared with the reference version.",
         f"Rule additions {min(additions):.1f}--{max(additions):.1f}\\,$\\times$ faster; "
         f"removals {min(removals):.1f}--{max(removals):.1f}\\,$\\times$ faster."),
        ("External rule reasoner", "The same rule changes, compared with ZodiacEdge.",
         f"One addition {1/native_insert:.1f}\\,$\\times$ faster; "
         f"one removal {native_delete:.0f}\\,$\\times$ slower."),
        ("Order of reasoning", "A difficult TPC-H Q5 component and four deliberately adverse controls.",
         f"Q5 needs {100*(1-query_ratios['sf0.1-q5']):.0f}\\% less query time; "
         f"controls need {min(adverse):.0f}--{max(adverse):.0f}\\% more."),
        ("Broader OWL reasoner", "Selected DLP L3 task, compared with HermiT at three data sizes.",
         f"{min(hermit_speedups):.1f}--{max(hermit_speedups):.1f}\\,$\\times$ faster; "
         "the tested family also belongs to OWL 2 EL."),
    ]
    lines += [
        r"\begin{table}[htbp]", r"\centering\small",
        r"\caption{The principal comparisons answer different scientific questions; they "
        r"do not establish an overall ranking of reasoning systems. Performance changes "
        r"are derived from median paired time ratios on the same machine. "
        r"Query timings in the fourth row exclude data preparation.}",
        r"\label{tab:scientific-evidence}",
        r"\begin{tabularx}{\linewidth}{@{}>{\raggedright\arraybackslash}p{0.19\linewidth}>{\raggedright\arraybackslash}X>{\raggedright\arraybackslash}X@{}}",
        r"\toprule", r"Evidence & Comparison & Principal finding \\", r"\midrule",
    ]
    lines.extend(" & ".join(row) + r" \\[4pt]" for row in rows)
    lines += [r"\bottomrule", r"\end{tabularx}", r"\end{table}", ""]
    (output / "scientific-findings.tex").write_text("\n".join(lines))
    return list(INPUTS)


if __name__ == "__main__":
    prepare(ROOT / "docs/paper/generated")
