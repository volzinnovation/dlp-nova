"""Independent count and update checks for the corrected benchmark inputs."""
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from rdflib import OWL, RDF

# Benchmarks are repository tooling, deliberately excluded from the installed wheel.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmarks import run as benchmark_run  # noqa: E402
from benchmarks.run import (  # noqa: E402
    BASELINE_COMMIT, BASELINE_RESULTS_SHA256, DEFAULT_BASELINE,
    bootstrap_ratio, build_cases, compare_baseline, compare_timing, correctness_comparison,
    load_baseline, markdown, protect_output, source_hashes, worker,
)
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
    assert len(cases) == 54
    taxonomy_controls = {(c["depth"], c["ipc"], c["variant"]) for c in cases
                         if c["kind"] == "taxonomy" and "strategy" not in c}
    assert len(taxonomy_controls) == 27
    assert {(c["depth"], c["change_percent"]) for c in cases if c["kind"] == "maintenance"} == {
        (3, 10), (3, 15), (4, 10), (4, 15), (5, 10), (5, 15),
    }


def test_baseline_comparison_requires_matching_inputs_but_allows_new_source():
    case = {"kind": "taxonomy", "depth": 3, "ipc": 3, "variant": "P0", "repeats": 5}
    baseline = {"timestamp": "before", "measurement_protocol": "phase-timings-v1",
                "environment": {"source_sha256": {"engine.py": "old"}},
                "results": [{"case": case, "input_sha256": "same-input",
                             "validation": "passed",
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


def test_immutable_default_is_the_exact_b1254c4_report_and_sources():
    baseline, provenance = load_baseline()
    assert provenance["verified"] and provenance["git_objects_verified"]
    assert provenance["baseline_commit"] == BASELINE_COMMIT
    assert provenance["results_sha256"] == BASELINE_RESULTS_SHA256
    assert len(baseline["results"]) == 51
    assert source_hashes()["benchmarks/workloads.py"] == baseline["environment"]["source_sha256"][
        "benchmarks/workloads.py"]


@pytest.mark.parametrize("change", ["results", "commit", "sources", "controls"])
def test_pinned_reference_rejects_tampering(tmp_path, monkeypatch, change):
    copied = tmp_path / "results.json"
    copied.write_bytes(DEFAULT_BASELINE.read_bytes())
    manifest = json.loads(DEFAULT_BASELINE.with_name("manifest.json").read_text())
    if change == "results":
        copied.write_bytes(copied.read_bytes() + b"\n")
    elif change == "commit":
        manifest["baseline_commit"] = "0" * 40
    elif change == "sources":
        manifest["source_sha256"]["src/dlp_reasoner/engine.py"] = "0" * 64
    else:
        manifest["case_count"] = 50
    copied.with_name("manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(benchmark_run, "DEFAULT_BASELINE", copied)
    with pytest.raises(ValueError):
        load_baseline(copied)


def test_outputs_cannot_overwrite_baselines_or_file_aliases(tmp_path):
    with pytest.raises(ValueError, match="immutable"):
        protect_output(DEFAULT_BASELINE, None)
    symlink = tmp_path / "alias.json"
    symlink.symlink_to(DEFAULT_BASELINE)
    with pytest.raises(ValueError):
        protect_output(symlink, DEFAULT_BASELINE)
    custom = tmp_path / "custom.json"
    custom.write_text("{}")
    hardlink = tmp_path / "hardlink.json"
    hardlink.hardlink_to(custom)
    with pytest.raises(ValueError, match="overwrite"):
        protect_output(hardlink, custom)
    protect_output(tmp_path / "new-report.json", DEFAULT_BASELINE)


def test_bootstrap_intervals_are_reproducible_and_do_not_invent_zero_time_ratios():
    assert bootstrap_ratio((2.0,) * 5, (1.0,) * 5) == (0.5, 0.5)
    varying = ((1.0, 1.1, 0.9, 1.2, 1.0), (0.5, 0.6, 0.45, 0.55, 0.5))
    first = bootstrap_ratio(*varying)
    bootstrap_ratio.cache_clear()
    assert bootstrap_ratio(*varying) == first
    assert first[0] < 0.5 < first[1]
    assert bootstrap_ratio((0.0,) * 5, (0.0,) * 5) is None
    assert compare_timing({"median": 0, "samples": [0] * 5},
                          {"median": 1, "samples": [1] * 5})["after_over_before"] is None


def test_all_51_reference_controls_compare_including_36_maintenance_operations():
    baseline, provenance = load_baseline()
    report = deepcopy(baseline)
    report["environment"]["source_sha256"] = source_hashes()
    comparison = compare_baseline(report, baseline, DEFAULT_BASELINE, provenance)
    assert len(comparison["matched"]) == 51 and not comparison["skipped"]
    assert all(row["correctness"]["verified"] for row in comparison["matched"])
    assert sum(len(row["maintenance_operations"]) for row in comparison["matched"]) == 36
    for row in comparison["matched"]:
        for operation in row["maintenance_operations"].values():
            assert operation["update_seconds"]["after_over_before"] == 1
            assert operation["work_counters"]["overdeleted_facts"]["after_over_before"] in {None, 1}
    report["comparison"] = comparison
    rendered = markdown(report)
    assert "51/51" in rendered
    assert "Parsing, compilation and public query calls" in rendered
    assert "Maintenance compared with the pinned implementation" in rendered
    assert "descriptive sensitivity" in rendered


def test_comparison_flags_changed_results_and_excludes_changed_operation_controls():
    baseline, _ = load_baseline()
    original = next(row for row in baseline["results"] if row["case"]["kind"] == "maintenance")
    changed = deepcopy(original)
    changed["materialized_fact_counts"][0] += 1
    assert not correctness_comparison(original, changed)["verified"]
    changed = deepcopy(original)
    changed["maintenance_operations"]["rule_delete"]["samples"][0]["removed_rules"] += 1
    report = {**baseline, "results": [changed]}
    comparison = compare_baseline(report, baseline, DEFAULT_BASELINE)
    row = comparison["matched"][0]
    assert "rule_delete" not in row["maintenance_operations"]
    assert row["maintenance_skipped"]["rule_delete"] == "operation fact/rule counts changed"


def test_comparison_rejects_unvalidated_results():
    baseline, _ = load_baseline()
    changed = deepcopy(baseline["results"][0])
    changed["validation"] = "failed"
    comparison = compare_baseline({**baseline, "results": [changed]}, baseline, DEFAULT_BASELINE)
    assert not comparison["matched"]
    assert comparison["skipped"][0]["reason"] == "current case did not validate"


def test_comparison_checks_current_protocol_and_marks_new_counters_unavailable_before():
    baseline, _ = load_baseline()
    changed = deepcopy(baseline["results"][0])
    for stats in changed["engine_stats"]:
        stats["unary_intersections"] = 42
    comparison = compare_baseline({**baseline, "results": [changed]}, baseline, DEFAULT_BASELINE)
    counters = comparison["matched"][0]["materialization_counters"]["unary_intersections"]
    assert counters["before"] is None and counters["after"] == 42
    assert counters["baseline_available"] is False
    comparison = compare_baseline({**baseline, "results": [changed], "measurement_protocol": "different"},
                                  baseline, DEFAULT_BASELINE)
    assert not comparison["matched"]
    assert comparison["skipped"][0]["reason"] == "measurement boundaries differ"
