"""Validate preserved Bach observations and generate scientific-paper evidence."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import statistics
import tarfile

from rdflib import Graph, Namespace

ROOT = Path(__file__).resolve().parents[1]
ARMS = ("b1254c4", "candidate", "hermit", "zodiac-native")
NAMESPACE = "http://www.jsbach.org/bach#"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    if isinstance(value, bool):
        return value
    def iri(v):
        if v.startswith("owl:"):
            return "http://www.w3.org/2002/07/owl#" + v[4:]
        return v if ":" in v else NAMESPACE + v
    return sorted(([iri(v) for v in item] if isinstance(item, list) else iri(item)
                   for item in value), key=lambda row: json.dumps(row))


def prepare(table, output):
    names = ["benchmarks/bach-external-results.json", "benchmarks/bach-external-results-protocol.json"]
    raw, protocol = [json.loads((ROOT / name).read_text()) for name in names]
    require(raw["protocol_sha256"] == digest(ROOT / names[1]), "Bach protocol digest mismatch")
    require(protocol["workers"] == [], "Bach protocol must precede measurements")
    for key, value in protocol.items():
        if key != "workers":
            require(raw[key] == value, "Bach frozen field changed: " + key)
    require(raw["baseline_commit"] == "b1254c441731ca4fdf32ea83570ff99aaa84ac2a", "Bach baseline changed")
    require(raw["blocks"] == 12, "Unexpected Bach block count")
    manifest = json.loads((ROOT / "examples/bach-queries.json").read_text())
    require(raw["metadata"]["expected"]["ontology"] == {
        q["id"]: canonical(q["expected"]) for q in manifest["queries"] if q["variant"] == "ontology"},
        "Full Bach expected answers differ from source manifest")
    ns = Namespace(NAMESPACE)
    edges = {(str(a), str(b)) for a, b in Graph().parse(ROOT / "examples/bach-family.ttl").subject_objects(ns.ancestorOf)}
    for scenario in ("initial", "fact-replace", "rule-remove", "symmetry-insert"):
        ancestor = set(edges)
        if scenario == "fact-replace":
            ancestor.remove((str(ns["johann-sebastian"]), str(ns["wilhelm-friedemann"])))
            ancestor.add((str(ns["johann-sebastian"]), str(ns["johann-christian"])))
        while True:
            enlarged = ancestor | {(a, d) for a, b in ancestor for c, d in ancestor if b == c}
            if enlarged == ancestor:
                break
            ancestor = enlarged
        dynasty = set() if scenario == "rule-remove" else set(ancestor)
        if scenario == "symmetry-insert":
            dynasty |= {(b, a) for a, b in dynasty}
        answers = {}
        pairs = {"ancestorOf": ancestor, "inDynasty": dynasty}
        for query in raw["metadata"]["queries"]["family"]:
            args, method = query["arguments"], query["method"]
            if method == "property_pairs":
                value = sorted([list(p) for p in pairs[args[0]]])
            elif method == "property_values":
                value = sorted(b for a, b in pairs[args[1]] if a == NAMESPACE + args[0])
            elif method == "entails":
                value = (NAMESPACE + args[0], NAMESPACE + args[2]) in pairs[args[1]]
            elif method == "is_symmetric":
                value = args[0] == "inDynasty" and scenario == "symmetry-insert"
            elif method == "is_transitive":
                value = args[0] == "ancestorOf"
            else:
                raise ValueError("Unknown family question")
            answers[query["id"]] = canonical(value)
        require(answers == raw["metadata"]["expected"][scenario], "Independent family oracle mismatch")
    names.extend(raw["driver_sha256"])
    names.extend(raw["source_inputs_sha256"])
    for key in ("driver_sha256", "source_inputs_sha256"):
        for name, expected in raw[key].items():
            require(digest(ROOT / name) == expected, "Bach source drift: " + name)
    lock = "benchmarks/hermit-dependencies.json"
    names.append(lock)
    require(digest(ROOT / lock) == raw["metadata"]["runtime"]["dependency_lock_sha256"], "HermiT dependency drift")
    require(raw["metadata"]["native"]["commit"] == "e15721161d1055f019c4b8f9ac1bd8648417f154"
            and raw["metadata"]["native"]["archive_sha256"] ==
            "49e371017fa0a4d0602b941f2b4860823836414e7f2439059db81ac1d3e80ebe", "Native revision drift")
    baseline_name = "benchmarks/baselines/b1254c4/results.json"
    names.append(baseline_name)
    require(digest(ROOT / baseline_name) == raw["baseline_saved_sha256"], "Saved baseline changed")
    for key in ("candidate_archive", "inputs_archive"):
        name = raw[key]
        names.append(name)
        require(digest(ROOT / name) == raw[key + "_sha256"], "Bach archive drift")
        with tarfile.open(ROOT / name, "r:gz") as archive:
            actual = {m.name: hashlib.sha256(archive.extractfile(m).read()).hexdigest()
                      for m in archive.getmembers() if m.isfile()}
        expected = (raw["metadata"]["source_sha256"]["candidate"] if key == "candidate_archive"
                    else {Path(p).name: h for p, h in raw["input_sha256"].items()})
        require(actual == expected, "Bach archive member mismatch")
    workers = raw["workers"]
    expected_jobs = {(block, mode, case, arm) for block in range(12)
                     for mode, case, arms in raw["protocol"]["jobs"] for arm in arms}
    require(len(workers) == len(expected_jobs) == 336 and
            {(w["block"], w["mode"], w["case"], w["arm"]) for w in workers} == expected_jobs,
            "Incomplete or duplicated Bach run series")
    checked = 0
    failures = []
    for worker in workers:
        job = next((i, arms) for i, (mode, case, arms) in enumerate(raw["protocol"]["jobs"])
                   if mode == worker["mode"] and case == worker["case"])
        offset = (worker["block"] + job[0]) % len(job[1])
        order = job[1][offset:] + job[1][:offset]
        require(order[worker["position"]] == worker["arm"], "Bach arm order drift")
        if worker["status"] == "failed":
            require(bool(worker.get("stderr") or worker.get("error")), "Missing failure diagnostics")
            require((worker["arm"], worker["mode"], worker["case"]) ==
                    ("zodiac-native", "incremental", "fact-replace"), "Uninterpreted failure category")
            details = json.loads(worker["stderr"].rsplit("Native Bach closure differs: ", 1)[1])
            require(details["state"] == "updated" and details["unexpected"] == [] and
                    details["missing"] == [[NAMESPACE + p, ["johannes", "wilhelm-friedemann"]]
                                           for p in ("ancestorOf", "inDynasty")], "Uninterpreted native failure")
            failures.append({**{k: worker[k] for k in ("block", "mode", "case", "arm", "error")},
                             "diagnostic": details})
            continue
        require(worker["status"] == "validated", "Unknown Bach status")
        if worker["arm"] in ("b1254c4", "candidate"):
            require(worker["source_sha256"] == raw["metadata"]["source_sha256"][worker["arm"]],
                    "Wrong Bach package measured")
            require(worker["pythonhashseed"] == str(7100 + worker["block"]), "Bach hashseed drift")
        keys = [worker["case"]] if worker["mode"] == "static" else ["initial", worker["case"], "initial"]
        require(len(worker["states"]) == len(keys), "Missing Bach state")
        for state, key in zip(worker["states"], keys, strict=True):
            expected = raw["metadata"]["expected"][key]
            require(len(state["queries"]) == len(expected), "Incomplete Bach queries")
            answers = {q["id"]: canonical(q["answer"]) for q in state["queries"]}
            require(answers == expected, "Bach answer mismatch")
            require(state["exact_answers_match"] and state.get("consistent", True)
                    and state.get("complete", True), "Incomplete Bach computation")
            timings = [q["seconds"] for q in state["queries"]]
            require(all(math.isfinite(t) and t >= 0 for t in timings), "Invalid query timing")
            require(math.isclose(sum(timings), state["query_seconds"], rel_tol=1e-12), "Query phase mismatch")
            require(math.isfinite(state["task_seconds"]) and state["task_seconds"] >= sum(timings)
                    and worker["process_seconds"] >= state["task_seconds"], "Invalid task interval")
            if worker["arm"] == "zodiac-native":
                phases = (("input_seconds", "conversion_seconds", "input_index_seconds", "reasoning_seconds")
                          if "input_seconds" in state else ("conversion_seconds", "update_seconds"))
            else:
                phases = (("query_preparation_seconds", "load_seconds", "construct_seconds", "consistency_seconds")
                          if "load_seconds" in state else ("update_seconds", "consistency_seconds"))
            require(math.isclose(sum(state[p] for p in (*phases, "query_seconds")),
                                 state["task_seconds"], rel_tol=1e-12), "Bach task phase mismatch")
            checked += len(expected)
    rows, ratios = [], {}
    for name, saved in raw["summary"].items():
        mode, case = name.split("/")
        selected = [w for w in workers if w["mode"] == mode and w["case"] == case]
        values = []
        for arm in ARMS:
            cohort = [w for w in selected if w["arm"] == arm]
            if not cohort:
                values.append("--")
                continue
            failed = sum(w["status"] == "failed" for w in cohort)
            if failed:
                require(saved[arm] == {"n": 12, "failed": failed, "performance_ranked": False},
                        "Incorrect Bach failure exclusion")
                values.append(f"Failed ({failed}/12)")
                continue
            index = 0 if mode == "static" else 1
            timings = [w["states"][index]["task_seconds"] for w in cohort]
            median = statistics.median(timings)
            require(math.isclose(median, saved[arm]["median_seconds"], rel_tol=1e-12), "Bach median changed")
            values.append(f"{median * 1000:.2f}")
            if arm != "candidate":
                candidate = {w["block"]: w for w in selected if w["arm"] == "candidate"}
                paired = statistics.median(w["states"][index]["task_seconds"] /
                                           candidate[w["block"]]["states"][index]["task_seconds"] for w in cohort)
                require(math.isclose(paired, saved[arm]["paired_ratio_over_candidate"], rel_tol=1e-12),
                        "Bach paired ratio changed")
                ratios[name + "/" + arm] = paired
        labels = {"ontology": "Full ontology", "initial": "Original family", "fact-replace": "Fact replacement",
                  "rule-remove": "Rule removal", "symmetry-insert": "Symmetry addition"}
        rows.append([("Rebuild: " if mode == "static" else "Update: ") + labels[case], *values])
    table("bach-comparison-table.tex", "Dissertation Bach examples, twelve repeated blocks. "
          "Median complete-task milliseconds, including all 25 full-ontology or nine family questions. "
          "Rebuilds include input preparation; updates exclude original-state setup. "
          "A failed configuration/task receives no timing ranking.", "tab:bach-comparison", "lrrrr",
          ["Task", "Earlier baseline", "Current", "HermiT", "ZodiacEdge"], rows)
    process_rows = []
    for name, saved in raw["summary"].items():
        if not name.startswith("static/"):
            continue
        cells = []
        for arm in ARMS:
            if arm not in saved:
                cells.append("--")
                continue
            if saved[arm].get("failed"):
                cells.append("Failed")
                continue
            cohort = [w for w in workers if w["mode"] == "static" and
                      w["case"] == name.split("/")[1] and w["arm"] == arm]
            value = statistics.median(w["process_seconds"] for w in cohort)
            require(math.isclose(value, saved[arm]["process_median_seconds"], rel_tol=1e-12), "Process median drift")
            cells.append(f"{value * 1000:.1f}")
        process_rows.append([labels[name.split("/")[1]], *cells])
    table("bach-process-table.tex", "Fresh-process wall time for the original Bach tasks, milliseconds. "
          "These intervals additionally include runtime startup, validation, serialization, and shutdown. "
          "Filesystem caches were not cleared.", "tab:bach-process", "lrrrr",
          ["Static task", "Earlier baseline", "Current", "HermiT", "ZodiacEdge"], process_rows)
    full = raw["summary"]["static/ontology"]
    family = raw["summary"]["static/initial"]
    failed_native = raw["summary"]["incremental/fact-replace"]["zodiac-native"].get("failed", 0)
    require(not any(w["status"] == "failed" and (w["arm"] != "zodiac-native" or
                w["mode"] != "incremental" or w["case"] != "fact-replace") for w in workers),
            "New failure category requires scientific interpretation before generating prose")
    require(failed_native * 2 == raw["blocks"],
            "Revisit every-second-process wording if the recorded failure fraction changes")
    text = ("The full Bach ontology gave identical answers to all 25 questions in the three "
            "supported systems. Median complete-task time was "
            f"{full['candidate']['median_seconds'] * 1000:.1f} ms for the current reasoner, "
            f"{full['b1254c4']['median_seconds'] * 1000:.1f} ms for the preserved earlier implementation, "
            f"and {full['hermit']['median_seconds'] * 1000:.1f} ms for HermiT.\n\n"
            "All four systems agreed on the complete family answers when each resulting "
            "state was computed from scratch. During incremental fact replacement, however, "
            "the pinned ZodiacEdge implementation failed exact-answer validation in every second "
            f"({failed_native}/{raw['blocks']}) process. This task therefore "
            "receives no ZodiacEdge timing ranking. The current and earlier implementations "
            "passed every tested update and restoration. Detailed phase and process times "
            "are given in the supplement.\n\n"
            "ZodiacEdge had lower task times on all four family reconstructions and both "
            "rule changes. For the original family, its median task time was "
            f"{family['zodiac-native']['median_seconds'] * 1000:.1f} ms, compared with "
            f"{family['candidate']['median_seconds'] * 1000:.1f} ms for the current reasoner. "
            "Including process startup, checking and shutdown, the corresponding medians were "
            f"{family['zodiac-native']['process_median_seconds'] * 1000:.1f} and "
            f"{family['candidate']['process_median_seconds'] * 1000:.1f} ms. "
            "The timing boundary therefore matters on these small inputs.\n")
    (output / "bach-findings.tex").write_text(text)
    check = {"workers": len(workers), "validated_workers": len(workers) - len(failures),
             "failed_workers": len(failures), "exact_query_answers_checked": checked,
             "failures": failures, "paired_ratio_over_candidate": ratios}
    (output / "bach-validation.json").write_text(json.dumps(check, indent=2) + "\n")
    return list(dict.fromkeys(names))
