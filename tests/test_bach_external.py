"""Independent source-example and evidence-integrity controls; no timed engines."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from rdflib import OWL, RDF, RDFS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmarks import bach_external as bridge  # noqa: E402
from benchmarks.bach import BACH, QUERY_FILE  # noqa: E402


def family_queries():
    queries = [q for q in json.loads(QUERY_FILE.read_text())["queries"]
               if q["variant"] == "family"]
    return queries + [{"id": "all-" + prop, "method": "property_pairs", "arguments": [prop]}
                      for prop in ("ancestorOf", "inDynasty")]


def named_pair(left, right):
    return (str(BACH[left]), str(BACH[right]))


def pairs(answers, prop="ancestorOf"):
    return {tuple(row) for row in answers["all-" + prop]}


def initial_worker(arm="candidate", block=0, seconds=1.0):
    expected = bridge.family_answers("initial", family_queries())
    state = {"consistent": True, "complete": True, "task_seconds": seconds,
             "queries": [{"id": key, "answer": deepcopy(value), "seconds": 0.001}
                         for key, value in expected.items()]}
    return {"arm": arm, "mode": "static", "case": "initial", "block": block,
            "status": "validated", "states": [state], "process_seconds": seconds + 0.1}


def test_normalization_preserves_pair_orientation_and_supports_compact_names():
    forward = bridge.normalized({(BACH.johannes, BACH.heinrich)})
    assert forward == [[str(BACH.johannes), str(BACH.heinrich)]]
    assert bridge.normalized([["johannes", "heinrich"]]) == forward
    assert bridge.normalized([["heinrich", "johannes"]]) != forward
    assert bridge.normalized(["owl:Thing"]) == [str(OWL.Thing)]
    assert bridge.normalized(False) is False


@pytest.mark.parametrize("scenario,counts", [
    ("initial", (24, 24)), ("fact-replace", (25, 25)),
    ("rule-remove", (24, 0)), ("symmetry-insert", (24, 48)),
])
def test_family_oracle_counts_and_negative_schema_answers(scenario, counts):
    answer = bridge.family_answers(scenario, family_queries())
    assert (len(pairs(answer)), len(pairs(answer, "inDynasty"))) == counts
    assert answer["base-dynasty-not-transitive"] is False
    assert answer["base-ancestor-transitive"] is True
    assert answer["base-dynasty-not-symmetric"] is (scenario == "symmetry-insert")
    assert answer["base-cross-branch-not-entailed"] is False
    assert named_pair("johann-christoph", "christoph") not in pairs(answer, "inDynasty")


def test_original_oracle_agrees_with_all_seven_preserved_source_answers():
    queries = family_queries()
    expected = bridge.family_answers("initial", queries)
    for query in queries[:7]:
        assert expected[query["id"]] == bridge.normalized(query["expected"])


def test_fact_replacement_has_exact_three_losses_and_four_additions():
    original = bridge.family_answers("initial", family_queries())
    changed = bridge.family_answers("fact-replace", family_queries())
    removed = {named_pair(source, "wilhelm-friedemann")
               for source in ("christoph", "johann-ambrosius", "johann-sebastian")}
    added = {named_pair(source, "johann-christian")
             for source in ("johannes", "christoph", "johann-ambrosius", "johann-sebastian")}
    for prop in ("ancestorOf", "inDynasty"):
        before, after = pairs(original, prop), pairs(changed, prop)
        assert before - after == removed
        assert after - before == added
        # The other maternal branch still supplies this ancestor relationship.
        assert named_pair("johannes", "wilhelm-friedemann") in after


def test_rule_removal_and_symmetry_have_exact_distinct_logical_effects():
    original = bridge.family_answers("initial", family_queries())
    removed = bridge.family_answers("rule-remove", family_queries())
    symmetric = bridge.family_answers("symmetry-insert", family_queries())
    ancestors = pairs(original)
    assert pairs(removed) == pairs(symmetric) == ancestors
    assert pairs(removed, "inDynasty") == set()
    assert pairs(symmetric, "inDynasty") == ancestors | {(b, a) for a, b in ancestors}
    assert all(a != b for a, b in pairs(symmetric, "inDynasty"))


def test_each_scenario_changes_only_its_documented_source_triples_and_is_reversible():
    original = set(bridge.family_graph("initial"))
    for scenario in bridge.SCENARIOS[1:]:
        add, remove = bridge.changes(scenario)
        actual = set(bridge.family_graph(scenario))
        assert actual == (original - set(remove)) | set(add)
        assert (actual - set(add)) | set(remove) == original
    assert (BACH.inDynasty, RDF.type, OWL.SymmetricProperty) not in original
    assert (BACH.ancestorOf, RDFS.subPropertyOf, BACH.inDynasty) in original


@pytest.mark.parametrize("corruption", [
    "reversed-pair", "extra-pair", "duplicate-row", "missing-question", "duplicate-question",
    "false-positive", "inconsistent", "incomplete", "extra-state",
])
def test_validation_rejects_wrong_answers_and_incomplete_states(corruption):
    worker = initial_worker()
    state = worker["states"][0]
    by_id = {q["id"]: q for q in state["queries"]}
    if corruption == "reversed-pair":
        by_id["all-ancestorOf"]["answer"][0].reverse()
    elif corruption == "extra-pair":
        by_id["all-inDynasty"]["answer"].append(list(named_pair("johann-christoph", "christoph")))
    elif corruption == "duplicate-row":
        by_id["all-ancestorOf"]["answer"].append(by_id["all-ancestorOf"]["answer"][0])
    elif corruption == "missing-question":
        state["queries"].pop()
    elif corruption == "duplicate-question":
        state["queries"][-1] = deepcopy(state["queries"][0])
    elif corruption == "false-positive":
        by_id["base-cross-branch-not-entailed"]["answer"] = True
    elif corruption == "inconsistent":
        state["consistent"] = False
    elif corruption == "incomplete":
        state["complete"] = False
    else:
        worker["states"].append(deepcopy(state))
    with pytest.raises((ValueError, RuntimeError)):
        bridge.validate_worker(worker, [bridge.family_answers("initial", family_queries())])


@pytest.mark.parametrize("value", [0.0, -1.0, float("nan"), float("inf")])
def test_validation_rejects_nonpositive_or_nonfinite_task_time(value):
    worker = initial_worker(seconds=value)
    with pytest.raises((ValueError, RuntimeError), match="timing"):
        bridge.validate_worker(worker, [bridge.family_answers("initial", family_queries())])


def test_failed_observation_disqualifies_entire_arm_task_including_fast_success():
    workers = [initial_worker(block=0), initial_worker(block=1),
               initial_worker("zodiac-native", 0, 0.00001),
               {"arm": "zodiac-native", "mode": "static", "case": "initial",
                "block": 1, "status": "failed", "error": "wrong conclusions"}]
    summary = bridge.summaries(workers)["static/initial"]
    assert summary["zodiac-native"] == {"n": 2, "failed": 1, "performance_ranked": False}
    assert summary["candidate"]["median_seconds"] == 1.0


def test_failed_candidate_prevents_competitor_ratio():
    workers = [initial_worker(block=0),
               {"arm": "candidate", "mode": "static", "case": "initial",
                "block": 1, "status": "failed", "error": "wrong conclusions"},
               initial_worker("hermit", 0, 2.0), initial_worker("hermit", 1, 2.0)]
    summary = bridge.summaries(workers)["static/initial"]
    assert summary["candidate"]["performance_ranked"] is False
    assert "paired_ratio_over_candidate" not in summary["hermit"]


def test_summary_uses_median_of_paired_ratios_not_ratio_of_marginal_medians():
    workers = []
    for block, (candidate, other) in enumerate(zip([1.0, 10.0, 100.0], [2.0, 100.0, 200.0])):
        workers += [initial_worker("candidate", block, candidate), initial_worker("hermit", block, other)]
    summary = bridge.summaries(workers)["static/initial"]
    assert summary["hermit"]["paired_ratio_over_candidate"] == 2.0
    assert summary["hermit"]["median_seconds"] / summary["candidate"]["median_seconds"] == 10.0


@pytest.mark.parametrize("corruption", ["none", "wrong-answer", "wrong-source", "malformed-json"])
def test_execute_checks_frozen_import_and_preserves_failed_worker_evidence(tmp_path, monkeypatch, corruption):
    baseline = tmp_path / "frozen-baseline"
    expected = bridge.family_answers("initial", family_queries())
    metadata = {"inputs": {"initial": "example.owl"}, "queries": {"family": family_queries()},
                "sources": {"b1254c4": str(baseline), "candidate": str(tmp_path / "candidate")},
                "source_sha256": {"b1254c4": {"src/dlp_reasoner/engine.py": "frozen"}},
                "expected": {"initial": expected}}
    worker = initial_worker("b1254c4")
    worker["source_sha256"] = deepcopy(metadata["source_sha256"]["b1254c4"])
    if corruption == "wrong-answer":
        worker["states"][0]["queries"][0]["answer"] = []
    if corruption == "wrong-source":
        worker["source_sha256"] = {"src/dlp_reasoner/engine.py": "current"}
    stdout = "not JSON" if corruption == "malformed-json" else json.dumps(worker)

    def fake_run(command, **kwargs):
        assert command[:3] == [sys.executable, "-m", "benchmarks.bach_external"]
        assert kwargs["env"]["PYTHONPATH"].split(os.pathsep)[0] == str(baseline / "src")
        assert kwargs["env"]["PYTHONHASHSEED"] == "7100"
        return subprocess.CompletedProcess(command, 0, stdout, "retained diagnostic")

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)
    if corruption == "none":
        result = bridge.execute("b1254c4", "static", "initial", metadata, tmp_path,
                                tmp_path, tmp_path, 7100)
        assert result["states"][0]["exact_answers_match"] is True
    else:
        with pytest.raises(bridge.WorkerFailure) as failure:
            bridge.execute("b1254c4", "static", "initial", metadata, tmp_path,
                           tmp_path, tmp_path, 7100)
        assert failure.value.details
        assert "retained diagnostic" in json.dumps(failure.value.details)
