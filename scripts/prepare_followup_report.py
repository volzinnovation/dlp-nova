"""Validate saved follow-up observations and generate their manuscript tables."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import statistics
import tarfile

ROOT = Path(__file__).resolve().parents[1]
CONFIGURATIONS = ("b1254c4", "5531be4", "current-fixed", "candidate")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def median(values, expected=None):
    values = list(values)
    require(values and all(math.isfinite(v) and v >= 0 for v in values), "invalid timings")
    result = statistics.median(values)
    if expected is not None:
        require(math.isclose(result, expected, rel_tol=1e-12, abs_tol=1e-12),
                "stored summary differs from raw observations")
    return result


def prepare(table, output):
    inputs = []

    def load(name):
        inputs.append(name)
        report = json.loads((ROOT / name).read_text())
        protocol = Path(name).with_name(Path(name).stem + "-protocol.json").as_posix()
        require(hashlib.sha256((ROOT / protocol).read_bytes()).hexdigest()
                == report["protocol_sha256"], "protocol digest mismatch")
        inputs.append(protocol)
        return report

    zodiac = load("benchmarks/zodiac-results.json")
    manifest_name = "benchmarks/followup-source-manifest.json"
    manifest = json.loads((ROOT / manifest_name).read_text())
    inputs.extend([manifest_name, manifest["archive"], "benchmarks/zodiac-deletion-profile.json"])
    require(hashlib.sha256((ROOT / manifest["archive"]).read_bytes()).hexdigest()
            == manifest["archive_sha256"], "primary source archive changed")
    require(hashlib.sha256((ROOT / manifest["benchmark"]).read_bytes()).hexdigest()
            == manifest["benchmark_sha256"], "primary observation artifact changed")
    require(manifest["source_sha256"] == zodiac["source_sha256"]["candidate"],
            "primary archive source differs from measured source")
    with tarfile.open(ROOT / manifest["archive"], "r:gz") as archive:
        require(sorted(archive.getnames()) == sorted(manifest["source_sha256"]),
                "primary source archive member mismatch")
        for member in archive.getmembers():
            require(member.isfile(), "non-file in primary source archive")
            require(hashlib.sha256(archive.extractfile(member).read()).hexdigest()
                    == manifest["source_sha256"][member.name], "primary source archive payload mismatch")
    workers = zodiac["workers"]
    blocks = zodiac["protocol"]["blocks"]
    require(len(workers) == 4 * blocks, "missing Zodiac workers")
    require({(w["configuration"], w["block"]) for w in workers}
            == {(c, b) for c in CONFIGURATIONS for b in range(blocks)}, "Zodiac pairing mismatch")
    for worker in workers:
        require(worker["source_sha256"] == zodiac["source_sha256"][worker["configuration"]],
                "Zodiac source mismatch")
        for marker in ("*", "#"):
            for action, reference in (("initial", marker), ("insert", "full"), ("delete", marker)):
                require(worker["transactions"][marker][action]
                        == zodiac["fresh_naive_reference"][reference], "Zodiac closure mismatch")
        samples = worker["supplemental_fact_transactions"]
        require([sample["seed"] for sample in samples] == zodiac["protocol"]["fact_sample_seeds"],
                "supplemental sample selection mismatch")
        for sample in samples:
            require(sample["removed_assertions"] == 1000, "supplemental batch size mismatch")
            require(sample["delete"] == zodiac["fresh_naive_reference"]["facts-" + str(sample["seed"])],
                    "supplemental deletion closure mismatch")
            require(sample["insert"] == zodiac["fresh_naive_reference"]["full"],
                    "supplemental reinsertion closure mismatch")
    rows = []
    for marker in ("*", "#"):
        for configuration in CONFIGURATIONS:
            values = [w["transactions"][marker] for w in workers if w["configuration"] == configuration]
            summary = zodiac["summary"][configuration][marker]
            row = [r"$\ast$" if marker == "*" else r"$\#$", configuration]
            for metric in ("construct_and_materialize_seconds", "insert_seconds", "delete_seconds"):
                value = median((v[metric] for v in values), summary[metric]["median"])
                row.append(f"{value:.4f}")
            rows.append(row)
    table("zodiac-table.tex", "Author-supplied ZodiacEdge LUBM program: four fresh process "
          "blocks per configuration. Median seconds; initial includes engine construction "
          "and materialization. Parsing and outcome validation are outside these intervals.",
          "tab:zodiac", "llrrr", ["Subset", "Configuration", "Initial", "Insert rules", "Delete rules"], rows)

    ratios = {}
    for denominator in CONFIGURATIONS[:-1]:
        for marker in ("*", "#"):
            for metric in ("construct_and_materialize_seconds", "insert_seconds", "delete_seconds"):
                pairs = []
                for block in range(blocks):
                    pair = {w["configuration"]: w["transactions"][marker][metric]
                            for w in workers if w["block"] == block}
                    pairs.append(pair["candidate"] / pair[denominator])
                ratios[(denominator, marker, metric)] = median(
                    pairs, zodiac["paired_ratios"]["candidate/" + denominator][marker][metric]["median"])
    rows = []
    for configuration in CONFIGURATIONS:
        row = [configuration]
        for metric in ("delete_seconds", "insert_seconds"):
            raw = [sample[metric] for w in workers if w["configuration"] == configuration
                   for sample in w["supplemental_fact_transactions"]]
            value = median(raw, zodiac["supplemental_summary"][configuration][metric]["median"])
            row.append(f"{value:.4f}")
        rows.append(row)
    table("zodiac-facts-table.tex", "Supplemental 1,000-fact updates on the same author program. "
          "Median seconds across ten fixed subsets in each of four process blocks. These "
          "are forty correlated case/block observations per configuration.", "tab:zodiac-facts",
          "lrr", ["Configuration", "Delete facts", "Reinsert facts"], rows)

    tpch = load("benchmarks/external-tpch-results.json")
    require(len(tpch["workers"]) == 24, "missing TPC-H component workers")
    require(zodiac["source_sha256"]["candidate"] == tpch["current_source_sha256"],
            "follow-up studies measured different candidate sources")
    tpch_ratios = {}
    for metric, filename, label, title in (
            ("join_seconds", "tpch-joins-table.tex", "tab:tpch-joins", "Fully consumed join kernel"),
            ("component_end_to_end_seconds", "tpch-total-table.tex", "tab:tpch-total", "Cold component total")):
        rows = []
        for case, summaries in tpch["summary"].items():
            sample = summaries["candidate"]
            row = [f'{sample["scale_factor"]:g}', "Q" + str(sample["query_component"])]
            matching = [w for w in tpch["workers"] if w["scale_factor"] == sample["scale_factor"]]
            for configuration in CONFIGURATIONS:
                observations = [q for w in matching if w["configuration"] == configuration
                                for q in w["queries"] if q["query_component"] == sample["query_component"]]
                require(len(observations) == 3, "missing paired TPC-H observations")
                for q in observations:
                    require(q["exact_sql_match"] and q["exact_base_closure_match"], "TPC-H validation failed")
                    require(q["answers"] == q["sql_bag_rows"] and q["answer_sha256"] == sample["answer_sha256"],
                            "TPC-H answer mismatch")
                value = median((q[metric] for q in observations), summaries[configuration][metric]["median"])
                row.append(f"{1000*value:,.2f}")
            for denominator in CONFIGURATIONS[:-1]:
                paired = []
                for block in range(3):
                    pair = {w["configuration"]: next(q[metric] for q in w["queries"]
                            if q["query_component"] == sample["query_component"])
                            for w in matching if w["block"] == block}
                    paired.append(pair["candidate"] / pair[denominator])
                tpch_ratios[(case, metric, denominator)] = median(paired)
            row.append(f'{tpch_ratios[(case, metric, "current-fixed")]:.3f}')
            rows.append(row)
        table(filename, title + " for TPC-H-derived Q3/Q5/Q9 components (ms). "
              "Three fresh workers per scale/configuration. Final column is the median "
              "paired candidate/current-fixed ratio; smaller favors the candidate.", label, "llrrrrr",
              ["SF", "Join", "b1254c4", "5531be4", "Fixed", "Candidate", "Ratio"], rows)

    native = load("benchmarks/zodiac-native-results.json")
    require(native["candidate_source_sha256"] == zodiac["source_sha256"]["candidate"],
            "native comparison candidate source mismatch")
    if native.get("failure"):
        native_text = ("The native ZodiacEdge comparison did not complete its exact-closure "
                       "validation. The failure record is retained; no speed ratio is reported.\n")
    else:
        require(len(native["workers"]) == 8, "missing native paired workers")
        require({(w["arm"], w["block"]) for w in native["workers"]}
                == {(arm, block) for arm in ("native", "candidate") for block in range(4)},
                "native pairing mismatch")
        for worker in native["workers"]:
            for marker in ("*", "#"):
                for action, reference in (("initial", marker), ("insert", "full"), ("delete", marker)):
                    require(worker["transactions"][marker][action] == native["reference"][reference],
                            "native comparison closure mismatch")
        rows = []
        for marker in ("*", "#"):
            for metric, label in (("construct_and_materialize_seconds", "Initial"),
                                  ("insert_seconds", "Insert rules"), ("delete_seconds", "Delete rules")):
                row = [r"$\ast$" if marker == "*" else r"$\#$", label]
                for arm in ("native", "candidate"):
                    values = [w["transactions"][marker][metric] for w in native["workers"] if w["arm"] == arm]
                    row.append(f'{median(values, native["summary"][arm][marker][metric]["median"]):.4f}')
                pairs = []
                for block in range(4):
                    pair = {w["arm"]: w["transactions"][marker][metric]
                            for w in native["workers"] if w["block"] == block}
                    pairs.append(pair["candidate"] / pair["native"])
                ratio = median(pairs, native["paired_candidate_over_native"][marker][metric]["median"])
                row.append(f"{ratio:.3f}")
                rows.append(row)
        table("zodiac-native-table.tex", "Matched comparison with the unmodified author engine: "
              "four alternating paired blocks, seconds. Initial includes native input indexing. "
              "Final column is the median paired candidate/native ratio; below one favors our candidate.",
              "tab:zodiac-native", "llrrr", ["Subset", "Operation", "ZodiacEdge", "Candidate", "Ratio"], rows)
        native_text = r"\input{generated/zodiac-native-table.tex}" + "\n"
    text = r"""\subsection{Follow-up measurements}
\input{generated/zodiac-table.tex}
\input{generated/zodiac-facts-table.tex}
\input{generated/tpch-joins-table.tex}
\input{generated/tpch-total-table.tex}

\subsection{An actual external engine on the same host}
The comparator uses the pinned, unmodified ZodiacEdge Program API and parser.
Its unary atoms use physical RDF type triples, whereas our store uses unary
relations. An injective encoding retains RDF term identity, and both outputs
are decoded to the same typed tuples for complete closure checks. Native input
index creation is included in initial compute. Conversion is recorded separately
and excluded from both implementations' compute intervals. Native whole-process
RSS includes adapter allocations, so it is not an isolated engine-memory ranking.
The program has no predicate variables; fixed predicate labels and injectively
encoded data constants occupy separate namespaces. Translating unary atoms to
type triples and binary atoms to property triples therefore gives a bijection
between rule substitutions. This validates the adapter's semantic contract;
full-run checks still test the engines' actual computation.
""" + native_text
    (output / "followup-results.tex").write_text(text)
    (output / "followup-paired-ratios.json").write_text(json.dumps({
        "zodiac": {"/".join(key): value for key, value in ratios.items()},
        "tpch": {"/".join(key): value for key, value in tpch_ratios.items()},
    }, indent=2) + "\n")
    return inputs
