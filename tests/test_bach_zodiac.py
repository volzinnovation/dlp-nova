"""Matched Bach family tasks using the optional unmodified ZodiacEdge engine."""
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import subprocess
import sys

import pytest
from rdflib import Graph, OWL, RDF, RDFS

from benchmarks import bach_zodiac
from benchmarks.bach import BACH
from benchmarks.bach_zodiac import (ANCESTOR, INCLUSION, NEW_EDGE, OLD_EDGE, SOURCE,
                                    TRANSITIVE, incremental_worker, prepare_family,
                                    static_worker)

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "tmp/zodiac-native"


@pytest.fixture
def native_cache():
    if not (CACHE / "manifest.json").exists():
        pytest.skip("Optional pinned ZodiacEdge source has not been prepared")
    return CACHE


def queries():
    result = list(deepcopy(prepare_family().queries))
    result += [{"id": "all-ancestors", "method": "property_pairs", "arguments": ["ancestorOf"]},
               {"id": "all-dynasty", "method": "property_pairs", "arguments": ["inDynasty"]}]
    return result


def answers(state):
    return {query["id"]: query["answer"] for query in state["queries"]}


def test_family_translation_preserves_assertions_without_precomputing_consequences():
    prepared = prepare_family(require_original=True)
    assert len(prepared.facts) == 9
    assert set(prepared.rules) == {TRANSITIVE, INCLUSION}
    assert all(fact.predicate == ANCESTOR for fact in prepared.facts)
    assert OLD_EDGE in prepared.facts and NEW_EDGE not in prepared.facts
    assert len(prepared.queries) == 7


def test_full_table_2_5_is_rejected_instead_of_silently_projected():
    with pytest.raises(ValueError, match="Outside the positive Bach family contract"):
        prepare_family(ROOT / "examples/bach.ttl")


@pytest.mark.parametrize("scenario,ancestor_count,dynasty_count", [
    ("rule-remove", 24, 0), ("symmetry-insert", 24, 48),
])
def test_native_incremental_updates_and_reversals_preserve_exact_answers(
        native_cache, scenario, ancestor_count, dynasty_count):
    result = incremental_worker(native_cache, SOURCE, scenario, queries())
    initial, changed, restored = result["states"]
    assert result["all_exact_matches"]
    assert [(len(s["ancestor_pairs"]), len(s["dynasty_pairs"])) for s in result["states"]] == [
        (24, 24), (ancestor_count, dynasty_count), (24, 24)]
    assert initial["closure"] == restored["closure"]
    assert answers(initial) == answers(restored)
    assert answers(changed)["base-dynasty-not-transitive"] is False
    assert answers(changed)["base-ancestor-transitive"] is True
    assert answers(changed)["base-cross-branch-not-entailed"] is False
    assert answers(changed)["base-dynasty-not-symmetric"] == (scenario == "symmetry-insert")
    assert answers(changed)["all-ancestors"] == changed["ancestor_pairs"]
    assert answers(changed)["all-dynasty"] == changed["dynasty_pairs"]
    assert math.isclose(initial["task_seconds"], sum(initial[key] for key in (
        "input_seconds", "conversion_seconds", "input_index_seconds", "reasoning_seconds", "query_seconds")))
    for state in (changed, restored):
        assert math.isclose(state["task_seconds"], sum(state[key] for key in (
            "conversion_seconds", "update_seconds", "query_seconds")))
    assert math.isclose(result["full_task_seconds"], sum(s["task_seconds"] for s in result["states"]))
    assert result["worker_body_seconds"] >= result["full_task_seconds"]
    assert result["fact_replacement_atomic"] is False


@pytest.mark.parametrize("seed", [0, 1])
def test_native_fact_update_either_validates_or_exposes_the_known_lost_support(
        native_cache, seed):
    # These are semantic regression checks, not benchmark seed selection. Native
    # iteration also uses object identities, so a hash seed alone need not fix
    # the outcome. A successful trace must be exact; the observed native failure
    # must be rejected explicitly and retain its precise missing consequences.
    script = """
import json
from benchmarks.bach_zodiac import family_worker, NativeBachMismatch
try:
    result = family_worker('tmp/zodiac-native', scenario='fact-replace')
    print(json.dumps({'passed': True, 'result': result}))
except NativeBachMismatch as error:
    print(json.dumps({'passed': False, 'error': error.details}))
"""
    child = subprocess.run([sys.executable, "-c", script], cwd=ROOT, text=True, capture_output=True,
                           env={**os.environ, "PYTHONHASHSEED": str(seed)}, check=True)
    observation = json.loads(child.stdout)
    if observation["passed"]:
        initial, changed, restored = observation["result"]["states"]
        assert [(len(s["ancestor_pairs"]), len(s["dynasty_pairs"]))
                for s in (initial, changed, restored)] == [(24, 24), (25, 25), (24, 24)]
        assert answers(changed)["ambrosius-descendants"] == ["johann-christian", "johann-sebastian"]
        assert answers(changed)["johannes-reaches-wilhelm"] is True
    else:
        assert observation["error"]["state"] == "updated"
        assert observation["error"]["unexpected"] == []
        assert observation["error"]["missing"] == [
            [str(BACH.ancestorOf), ["johannes", "wilhelm-friedemann"]],
            [str(BACH.inDynasty), ["johannes", "wilhelm-friedemann"]],
        ]
        assert answers({"queries": observation["error"]["queries"]})["johannes-reaches-wilhelm"] is False


def test_loss_of_an_alternatively_supported_consequence_is_rejected(native_cache, monkeypatch):
    original = bach_zodiac.native_closure
    calls = 0

    def lose_alternative_support(*args):
        nonlocal calls
        calls += 1
        result = original(*args)
        if calls == 2:
            result -= {bach_zodiac.relation(predicate, BACH.johannes, BACH["wilhelm-friedemann"])
                       for predicate in (BACH.ancestorOf, BACH.inDynasty)}
        return result

    monkeypatch.setattr(bach_zodiac, "native_closure", lose_alternative_support)
    with pytest.raises(bach_zodiac.NativeBachMismatch) as failure:
        incremental_worker(native_cache, SOURCE, "fact-replace", queries())
    assert failure.value.details["missing"] == [
        [str(BACH.ancestorOf), ["johannes", "wilhelm-friedemann"]],
        [str(BACH.inDynasty), ["johannes", "wilhelm-friedemann"]],
    ]
    assert failure.value.details["unexpected"] == []


@pytest.mark.parametrize("scenario,counts", [
    ("initial", (24, 24)), ("fact-replace", (25, 25)),
    ("rule-remove", (24, 0)), ("symmetry-insert", (24, 48)),
])
def test_native_static_rdfxml_scenarios_are_materialized_from_their_assertions(
        native_cache, tmp_path, scenario, counts):
    graph = Graph().parse(SOURCE)
    selected_queries = queries()
    if scenario == "fact-replace":
        graph.remove((OLD_EDGE.args[0], BACH.ancestorOf, OLD_EDGE.args[1]))
        graph.add((NEW_EDGE.args[0], BACH.ancestorOf, NEW_EDGE.args[1]))
        for query in selected_queries:
            if query["id"] == "johannes-descendants":
                query["expected"].append("johann-christian")
            elif query["id"] == "ambrosius-descendants":
                query["expected"] = ["johann-christian", "johann-sebastian"]
    elif scenario == "rule-remove":
        graph.remove((BACH.ancestorOf, RDFS.subPropertyOf, BACH.inDynasty))
    elif scenario == "symmetry-insert":
        graph.add((BACH.inDynasty, RDF.type, OWL.SymmetricProperty))
        for query in selected_queries:
            if query["id"] == "base-dynasty-not-symmetric":
                query["expected"] = True
    source = tmp_path / (scenario + ".owl")
    graph.serialize(source, format="xml")
    result = static_worker(native_cache, source, selected_queries)
    assert len(result["states"]) == 1
    state, = result["states"]
    assert (len(state["ancestor_pairs"]), len(state["dynasty_pairs"])) == counts
    assert len(state["queries"]) == 9
    assert result["input_was_prepared"] is False
    assert result["all_exact_matches"]


def test_native_schema_queries_do_not_infer_universals_from_observed_pairs(native_cache):
    result = static_worker(native_cache, SOURCE, queries())
    state, = result["states"]
    assert state["ancestor_pairs"] == state["dynasty_pairs"]
    assert answers(state)["base-ancestor-transitive"] is True
    assert answers(state)["base-dynasty-not-transitive"] is False


def test_native_fact_replacement_uses_both_public_calls_without_an_intermediate_query(
        native_cache, monkeypatch):
    api = bach_zodiac.native_api(native_cache)
    calls = []

    class TracedProgram(api["Program"]):
        def delete_data(self, data):
            calls.append("delete")
            return super().delete_data(data)

        def add_data(self, data):
            calls.append("add")
            return super().add_data(data)

        def query(self, *args):
            calls.append("query")
            return super().query(*args)

    monkeypatch.setattr(bach_zodiac, "native_api", lambda cache: {**api, "Program": TracedProgram})
    try:
        incremental_worker(native_cache, SOURCE, "fact-replace", queries())
    except bach_zodiac.NativeBachMismatch as error:
        assert error.details["state"] == "updated"
        assert error.details["missing"] == [
            [str(BACH.ancestorOf), ["johannes", "wilhelm-friedemann"]],
            [str(BACH.inDynasty), ["johannes", "wilhelm-friedemann"]],
        ]
    updates = [i for i, call in enumerate(calls) if call == "delete"]
    assert len(updates) in (1, 2) and all(calls[index + 1] == "add" for index in updates)


def test_native_adapter_fails_if_the_supplied_expected_state_is_wrong(native_cache):
    with pytest.raises(RuntimeError, match="supplied state contract"):
        static_worker(native_cache, SOURCE, queries(), {"initial": {"facts": 0, "sha256": "wrong"}})


def test_native_adapter_rejects_unsupported_query_instead_of_fabricating_an_answer(native_cache):
    with pytest.raises(ValueError, match="Unsupported native Bach query"):
        static_worker(native_cache, SOURCE, [{"id": "unsupported", "method": "is_satisfiable",
                                               "arguments": ["Father"]}])
