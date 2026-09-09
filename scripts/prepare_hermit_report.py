"""Validate saved finite-L3 bridge evidence and generate manuscript tables."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]
CONFIGURATIONS = ("b1254c4", "candidate", "hermit")
POPULATIONS = (100, 1000, 10000)
PHASES = ("load_seconds", "construct_seconds", "consistency_seconds",
          "positive_query_seconds", "negative_query_seconds")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def equal_number(actual, expected, message):
    require(math.isfinite(actual) and math.isfinite(expected)
            and math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12), message)


def answer_digest(rows):
    # Independent serialization of the task's IRI-string answers, not engine output.
    payload = "\n".join(sorted(json.dumps(row, ensure_ascii=False, separators=(",", ":"))
                               for row in rows))
    return hashlib.sha256(payload.encode()).hexdigest()


def prepare(table, output):
    inputs = []

    def load(name):
        inputs.append(name)
        return json.loads((ROOT / name).read_text())

    raw_name = "benchmarks/owl-bridge-results.json"
    protocol_name = "benchmarks/owl-bridge-results-protocol.json"
    raw = load(raw_name)
    protocol = load(protocol_name)
    require(hashlib.sha256((ROOT / protocol_name).read_bytes()).hexdigest()
            == raw["protocol_sha256"], "HermiT protocol digest mismatch")
    require(protocol["workers"] == [], "HermiT protocol already contains observations")
    for name, value in protocol.items():
        if name != "workers":
            require(raw[name] == value, "HermiT frozen protocol field changed: " + name)
    require(not raw.get("failure"), "HermiT study contains a failed worker")
    require(raw["baseline_commit"] == "b1254c441731ca4fdf32ea83570ff99aaa84ac2a",
            "HermiT baseline changed")
    require(raw["protocol"]["blocks"] == 3
            and raw["protocol"]["populations"] == list(POPULATIONS)
            and raw["protocol"]["configurations"] == list(CONFIGURATIONS),
            "unexpected HermiT experiment design")
    workers = raw["workers"]
    require(len(workers) == 27 and {(w["block"], w["population"], w["configuration"]) for w in workers}
            == {(b, n, c) for b in range(3) for n in POPULATIONS for c in CONFIGURATIONS},
            "HermiT worker pairing mismatch")
    for worker in workers:
        n, configuration = worker["population"], worker["configuration"]
        offset = (worker["block"] + POPULATIONS.index(n)) % 3
        expected_order = CONFIGURATIONS[offset:] + CONFIGURATIONS[:offset]
        require(expected_order[worker["position"]] == configuration, "HermiT execution order mismatch")
        require(worker["exact_match"] and worker["consistent"]
                and worker["positive_count"] == n and worker["negative_count"] == 0,
                "HermiT answer validation failed")
        expected = answer_digest(f"urn:owl-bridge:a{i}" for i in range(n))
        require(worker["positive_sha256"] == expected
                and worker["negative_sha256"] == answer_digest([]), "HermiT answer digest mismatch")
        require(raw["metadata"]["inputs"][str(n)]["expected_positive_sha256"] == expected,
                "HermiT expected answer metadata mismatch")
        if configuration == "hermit":
            require(worker["reasoner_version"] == "1.4.1.513", "HermiT API-reported version changed")
        else:
            require(worker["source_sha256"] == raw["source_sha256"][configuration],
                    "HermiT comparison imported a different Python package")
            require(worker["pythonhashseed"] == str(raw["protocol"]["seeds"][worker["block"]]),
                    "HermiT comparison Python hash seed changed")
        require(all(math.isfinite(worker[key]) and worker[key] >= 0
                    for key in (*PHASES, "task_seconds", "process_seconds")), "invalid HermiT timing")
        equal_number(sum(worker[key] for key in PHASES), worker["task_seconds"],
                     "HermiT task timing does not equal phase sum")
        require(worker["process_seconds"] >= worker["task_seconds"], "invalid process timing boundary")

    manifest = load("benchmarks/followup-source-manifest.json")
    inputs.append(manifest["archive"])
    archive_digest = hashlib.sha256((ROOT / manifest["archive"]).read_bytes()).hexdigest()
    require(archive_digest == manifest["archive_sha256"] == raw["candidate_archive_sha256"]
            and manifest["source_sha256"] == raw["source_sha256"]["candidate"],
            "HermiT candidate differs from the frozen follow-up source")
    for name, expected in raw["driver_sha256"].items():
        if name not in inputs:
            inputs.append(name)
        require(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected,
                "HermiT measured adapter changed: " + name)
    lock_name = "benchmarks/hermit-dependencies.json"
    lock = json.loads((ROOT / lock_name).read_text())
    require(hashlib.sha256((ROOT / lock_name).read_bytes()).hexdigest()
            == raw["metadata"]["dependency_lock_sha256"], "HermiT dependency lock changed")
    require(lock["distribution"] == raw["metadata"]["distribution"]
            == "net.sourceforge.owlapi:org.semanticweb.hermit:1.4.5.519"
            and lock["owlapi"] == raw["metadata"]["owlapi_version"] == "5.1.9",
            "HermiT artifact identity changed")
    require(len(raw["metadata"]["classpath"]) == 43
            and set(raw["metadata"]["classpath"]) == set(raw["metadata"]["classpath_sha256"]),
            "HermiT classpath manifest incomplete")
    for artifact in lock["artifacts"]:
        require(raw["metadata"]["classpath_sha256"]["current-hermit/" + artifact["name"]]
                == artifact["sha256"], "HermiT published jar digest mismatch")

    smoke = load("benchmarks/owl-bridge-smoke.json")
    require(smoke["baseline_commit"] == raw["baseline_commit"]
            and smoke["candidate_archive_sha256"] == raw["candidate_archive_sha256"],
            "HermiT smoke check source mismatch")
    require(len(smoke["checks"]) == 9
            and {(c["configuration"], c["omitted_gci"]) for c in smoke["checks"]}
            == {(c, omit) for c in CONFIGURATIONS for omit in (None, "existential", "bridge")},
            "HermiT semantic controls incomplete")
    for check in smoke["checks"]:
        expected = [f"urn:owl-bridge:a{i}" for i in range(3)] if check["omitted_gci"] is None else []
        require(check["consistent"] and check["positive"] == expected and check["negative"] == [],
                "HermiT semantic control failed")

    rows, ratio_rows, checked_ratios = [], [], {}
    for n in POPULATIONS:
        for configuration in CONFIGURATIONS:
            selected = [w for w in workers if w["population"] == n and w["configuration"] == configuration]
            for metric in (*PHASES, "task_seconds", "process_seconds"):
                values = [w[metric] for w in selected]
                summary = raw["summary"][str(n)][configuration][metric]
                for key, function in (("median", statistics.median), ("minimum", min), ("maximum", max)):
                    equal_number(function(values), summary[key], "HermiT stored summary differs from raw data")
            rows.append([f"{n:,}", "HermiT" if configuration == "hermit" else configuration,
                         f'{statistics.median(w["task_seconds"] for w in selected):.6f}',
                         f'{statistics.median(w["process_seconds"] for w in selected):.6f}'])
        for denominator in ("b1254c4", "hermit"):
            ratio_key = "candidate/" + denominator
            row = [f"{n:,}", "HermiT" if denominator == "hermit" else denominator]
            for metric in ("task_seconds", "process_seconds"):
                values = []
                for block in range(3):
                    pair = {w["configuration"]: w[metric] for w in workers
                            if w["population"] == n and w["block"] == block}
                    values.append(pair["candidate"] / pair[denominator])
                stored = raw["paired_ratios"][str(n)][ratio_key][metric]
                require(len(stored["raw"]) == 3, "HermiT paired ratio count mismatch")
                for actual, expected in zip(values, stored["raw"], strict=True):
                    equal_number(actual, expected, "HermiT stored ratio differs from its pair")
                center = statistics.median(values)
                equal_number(center, stored["median"], "HermiT paired median mismatch")
                checked_ratios[f"{n}/{ratio_key}/{metric}"] = {
                    "median": center, "minimum": min(values), "maximum": max(values), "raw": values}
                row.append(f"{center:.6f} [{min(values):.6f}, {max(values):.6f}]")
            ratio_rows.append(row)
    table("hermit-table.tex", "Finite DLP L3 bridge task on identical RDF/XML inputs: median seconds "
          "over three fresh process blocks. Task includes loading, construction, consistency and "
          "both complete named-instance queries; process additionally includes runtime startup, "
          "answer serialization and exit.", "tab:hermit", "rlrr",
          ["Named A instances", "Configuration", "Task", "Process"], rows)
    table("hermit-ratios-table.tex", "Within-block candidate/comparator ratios: median "
          "[minimum, maximum] over three pairs. Values below one favor the candidate. "
          "Ranges describe the measured pairs and are not confidence intervals.", "tab:hermit-ratios", "rlll",
          ["N", "Comparator", "Task ratio [range]", "Process ratio [range]"], ratio_rows)
    (output / "hermit-paired-ratios.json").write_text(json.dumps(checked_ratios, indent=2) + "\n")
    return inputs
