"""Independent count and update checks for the corrected benchmark inputs."""
import hashlib
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from rdflib import OWL, RDF

# Benchmarks are repository tooling, deliberately excluded from the installed wheel.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmarks.run import build_cases, compare_baseline, worker  # noqa: E402
from benchmarks.workloads import (  # noqa: E402
    EX, cardinality_taxonomy, factored_enumerations, factored_unions, maintenance, taxonomy,
)


@pytest.mark.parametrize("depth,ipc", [(3, 3), (3, 9), (3, 15), (5, 3), (7, 3)])
@pytest.mark.parametrize("variant", ["P0", "P1", "PF"])
def test_taxonomy_population_and_property_counts(depth, ipc, variant):
    graph, meta = taxonomy(depth, ipc, variant)
    classes = set(graph.subjects(RDF.type, OWL.Class))
    individuals = {subject for subject, cls in graph.subject_objects(RDF.type) if cls in classes}
    fillers = [(s, p, o) for s, p, o in graph if str(p).startswith(str(EX) + "p")]
    expected_classes = sum(3**level for level in range(depth + 1))
    assert len(classes) == expected_classes
    assert len(individuals) == (expected_classes - 1) * ipc == meta["individuals"]
    expected_fillers = 0 if variant == "P0" else (
        (expected_classes - 1) * (ipc // 3) if variant == "P1" else len(individuals))
    assert len(fillers) == expected_fillers == meta["property_fillers"]
    assert all(subject in individuals and obj in individuals for subject, _, obj in fillers)
    assert meta["expected_class_facts"] == sum(
        3**level * ipc * (level + 1) for level in range(1, depth + 1))


@pytest.mark.parametrize("depth,universal,max_one,min_zero", [
    (3, 13, 26, 13), (5, 121, 242, 121), (7, 1093, 2186, 1093),
])
def test_corrected_thesis_cardinality_counts(depth, universal, max_one, min_zero):
    graph, meta = cardinality_taxonomy(depth, 1)
    for predicate, expected in [(OWL.allValuesFrom, universal), (OWL.maxCardinality, max_one),
                                (OWL.minCardinality, min_zero)]:
        assert len(list(graph.subject_objects(predicate))) == expected
    assert meta["maximum_one_restrictions"] == 2 * meta["minimum_zero_restrictions"]
    assert meta["equality_groups"] == max_one
    assert all(int(value) == 1 for value in graph.objects(None, OWL.maxCardinality))
    assert all(int(value) == 0 for value in graph.objects(None, OWL.minCardinality))


def test_cardinality_workload_exercises_inferred_equality_and_universal_types():
    result = worker({"kind": "cardinality", "depth": 2, "ipc": 2, "repeats": 1})
    assert result["validation"] == "passed"
    assert result["engine_stats"][0]["equality_merges"] == 16
    assert result["workload"]["expected_root_answers"] == 24 + 32


def test_factored_unions_scale_past_exponential_rule_budget():
    small_graph, _ = factored_unions(16, 16)
    large_graph, meta = factored_unions(32, 16)
    assert meta["unfactored_dnf_branches"] == 4_294_967_296
    assert len(large_graph) < 2 * len(small_graph) + 20
    result = worker({"kind": "factored-unions", "pairs": 32, "size": 16, "repeats": 1})
    assert result["validation"] == "passed"
    assert result["program_shapes"][0]["compiled_rules"] < 200


def test_factored_enumerations_keep_positive_and_negative_alias_answers():
    result = worker({"kind": "factored-enumerations", "pairs": 32, "size": 16, "repeats": 1})
    assert result["validation"] == "passed"
    assert result["program_shapes"][0]["compiled_rules"] < 200
    assert result["workload"]["expected_answers"] == 41
    assert result["engine_stats"][0]["equality_merges"] == 48


@pytest.mark.parametrize("generator,args", [
    (taxonomy, (3, 3, "PF")), (cardinality_taxonomy, (2, 2)), (factored_unions, (8, 16)),
    (factored_enumerations, (8, 16)),
])
def test_inputs_have_reproducible_hashes(generator, args):
    def digest():
        graph, _ = generator(*args)
        serialized = "\n".join(sorted(graph.serialize(format="nt").splitlines()))
        return hashlib.sha256(serialized.encode()).hexdigest()
    assert digest() == digest()


@pytest.mark.parametrize("depth,classes", [(3, 156), (4, 781), (5, 3906)])
@pytest.mark.parametrize("change_percent", [10, 15])
def test_maintenance_counts_include_the_root_as_in_page_221(depth, classes, change_percent):
    graph, meta = maintenance(depth, change_percent)
    assert meta["classes"] == classes
    assert meta["individuals"] == classes * 5
    assert meta["changed_assertions"] == classes * 5 * change_percent // 100
    assert len(list(graph.subjects(RDF.type, EX.C0))) == 5


def test_maintenance_protocol_checks_deletion_cycles_and_mixed_updates():
    result = worker({"kind": "maintenance", "depth": 1, "change_percent": 10, "repeats": 1})
    operations = result["maintenance_operations"]
    assert set(operations) == {
        "fact_delete", "fact_insert", "rule_insert", "rule_delete", "rule_replace", "atomic_mixed",
    }
    for name in ("rule_delete", "rule_replace", "atomic_mixed"):
        assert operations[name]["samples"][0]["stats"]["update_method"] == "dred-rules"
    assert all(op["samples"][0]["validation"] == "matches-fresh-closure"
               for op in operations.values())


def test_suite_retains_taxonomy_matrix_and_adds_all_maintenance_controls():
    cases = build_cases("thesis")
    assert len(cases) == 51
    taxonomy_controls = {(c["depth"], c["ipc"], c["variant"]) for c in cases
                         if c["kind"] == "taxonomy" and "strategy" not in c}
    assert len(taxonomy_controls) == 27
    assert {(c["depth"], c["change_percent"]) for c in cases if c["kind"] == "maintenance"} == {
        (3, 10), (3, 15), (4, 10), (4, 15), (5, 10), (5, 15),
    }


def test_baseline_comparison_requires_matching_inputs_but_allows_new_source():
    case = {"kind": "taxonomy", "depth": 3, "ipc": 3, "variant": "P0", "repeats": 5}
    baseline = {"timestamp": "before", "environment": {"source_sha256": {"engine.py": "old"}},
                "results": [{"case": case, "input_sha256": "same-input",
                             "materialize_seconds": {"median": 2.0}}]}
    report = deepcopy(baseline)
    report["environment"]["source_sha256"]["engine.py"] = "new"
    report["results"][0]["materialize_seconds"]["median"] = 1.0
    matched = compare_baseline(report, baseline, "baseline.json")
    assert matched["matched"][0]["phases"]["materialize_seconds"]["after_over_before"] == 0.5
    report["results"][0]["input_sha256"] = "changed-input"
    skipped = compare_baseline(report, baseline, "baseline.json")
    assert not skipped["matched"]
    assert skipped["skipped"][0]["reason"] == "input hash changed"
