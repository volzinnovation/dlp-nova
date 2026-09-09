"""Tamper and completeness checks, using synthetic observations, never new timings."""
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.research import (  # noqa: E402
    CONFIGURATIONS, build_cases, execution_orders, promotion_assessment, summarize,
)

SPEC = importlib.util.spec_from_file_location("artifact_validator", ROOT / "scripts/validate_research_artifacts.py")
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def make_archive(path, entries):
    with tarfile.open(path, "w:gz") as archive:
        for name, content, kind in entries:
            member = tarfile.TarInfo(name)
            if kind == "file":
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
            elif kind == "symlink":
                member.type = tarfile.SYMTYPE
                member.linkname = str(content)
                archive.addfile(member)
    return validator.sha256(path.read_bytes())


@pytest.fixture(scope="module")
def valid_bundle(tmp_path_factory):
    directory = tmp_path_factory.mktemp("research-artifacts")
    protocol = json.loads((ROOT / validator.PROTOCOL_PATH).read_text())
    protocol_bytes = json.dumps(protocol, indent=2).encode()
    source_bytes = {name: f"# Synthetic fixture for {name}\n".encode() for name in validator.SOURCE_PATHS}
    files = {**source_bytes, validator.PROTOCOL_PATH: protocol_bytes}
    archive_path = directory / "sources.tar.gz"
    archive_hash = make_archive(archive_path, [(name, data, "file") for name, data in files.items()])
    manifest = {"base_commit": validator.BASE_COMMIT, "archive": archive_path.name,
                "archive_sha256": archive_hash,
                "files_sha256": {name: validator.sha256(data) for name, data in files.items()}}
    report = {"status": "passed", "git_head": validator.BASE_COMMIT, "protocol": protocol,
              "protocol_sha256": validator.sha256(protocol_bytes),
              "source_sha256": {name: validator.sha256(data) for name, data in source_bytes.items()},
              "finite_oracle_checks": [{"case": case, "configurations": 4, "status": "passed"}
                                       for case in build_cases(small=True)], "cases": []}
    factors = dict(zip(CONFIGURATIONS, (1.0, 0.9, 0.8, 0.72)))
    for number, case in enumerate(build_cases()):
        orders = execution_orders(9)
        rows = []
        for block, order in enumerate(orders):
            for position, name in enumerate(order):
                initial = {"complete": True, "consistent": True, "operation": "materialize",
                           "strategy": "semi-naive", "seconds": 0.1, "materialized_facts": 90,
                           "asserted_facts": 50, "update_method": "full"}
                update = {"complete": True, "consistent": True, "operation": "update",
                          "strategy": "semi-naive", "seconds": 0.01, "materialized_facts": 100,
                          "asserted_facts": 60, "update_method": (
                              "incremental-insert" if case["family"] == "unary" else "dred-rules")}
                row = {"case": case, "configuration": name, "validation": "passed",
                       **{key: validator.sha256(f"{key}:{number}".encode()) for key in validator.HASH_FIELDS},
                       "final_facts": 100, "materialize_seconds": 0.1,
                       "update_seconds": (block + 1) * factors[name],
                       "initial_stats": initial, "update_stats": update,
                       "memory": None, "hash_seed": str(2004 + block), "rss_bytes": 1_000_000,
                       "worker_seconds": 10, "block": block, "position": position}
                rows.append(row)
        memories = []
        for name in CONFIGURATIONS:
            row = deepcopy(next(value for value in rows if value["configuration"] == name))
            row.pop("block")
            row.pop("position")
            row.update(materialize_seconds=None, update_seconds=None,
                       memory={"peak_python_bytes": 1000, "retained_python_bytes": 500,
                               "scope": "synthetic fixture"})
            memories.append(row)
        report["cases"].append({"case": case, "orders": orders, "runs": rows,
                                "memory_runs": memories, "summary": summarize(rows)})
    report["promotion_assessment"] = promotion_assessment(report["cases"])
    return report, manifest, archive_path, files


def check(bundle):
    report, manifest, archive_path, _ = bundle
    return validator.validate_data(report, manifest, archive_path)


def altered(bundle):
    report, manifest, archive_path, files = bundle
    return deepcopy(report), deepcopy(manifest), archive_path, files


def test_complete_synthetic_evidence_validates_without_executing_archived_sources(valid_bundle):
    result = check(valid_bundle)
    assert result == {"status": "passed", "cases": 18, "timed_workers": 648,
                      "memory_workers": 72, "finite_oracle_controls": 36, "archived_files": 11,
                      "adaptive_threshold_met": True, "support_threshold_met": True}


@pytest.mark.parametrize("stats", ["initial_stats", "update_stats"])
@pytest.mark.parametrize("field", ["complete", "consistent"])
@pytest.mark.parametrize("memory", [False, True])
def test_rejects_incomplete_initial_and_final_results_in_every_pass(valid_bundle, stats, field, memory):
    bundle = altered(valid_bundle)
    row = bundle[0]["cases"][0]["memory_runs" if memory else "runs"][0]
    row[stats][field] = False
    with pytest.raises(validator.ArtifactError, match="Incomplete/inconsistent"):
        check(bundle)


@pytest.mark.parametrize("kind", ["case", "timed", "memory", "oracle"])
def test_missing_records_cannot_be_declared_complete(valid_bundle, kind):
    bundle = altered(valid_bundle)
    report = bundle[0]
    collection = {"case": report["cases"], "timed": report["cases"][0]["runs"],
                  "memory": report["cases"][0]["memory_runs"],
                  "oracle": report["finite_oracle_checks"]}[kind]
    collection.pop()
    with pytest.raises(validator.ArtifactError, match="Missing|missing"):
        check(bundle)


def test_duplicate_worker_with_unchanged_count_is_rejected(valid_bundle):
    bundle = altered(valid_bundle)
    rows = bundle[0]["cases"][0]["runs"]
    rows[1] = deepcopy(rows[0])
    with pytest.raises(validator.ArtifactError, match="block-position"):
        check(bundle)


@pytest.mark.parametrize("memory", [False, True])
def test_equal_count_different_full_answer_hash_is_rejected(valid_bundle, memory):
    bundle = altered(valid_bundle)
    row = bundle[0]["cases"][0]["memory_runs" if memory else "runs"][1]
    row["final_sha256"] = "f" * 64
    with pytest.raises(validator.ArtifactError, match="Full outcome"):
        check(bundle)


@pytest.mark.parametrize("value", [0, -0.1, float("nan"), float("inf"), True])
def test_ordinary_timings_must_be_positive_finite_numbers(valid_bundle, value):
    bundle = altered(valid_bundle)
    bundle[0]["cases"][0]["runs"][0]["update_seconds"] = value
    with pytest.raises(validator.ArtifactError, match="timing"):
        check(bundle)


def test_memory_timings_cannot_be_mixed_into_ordinary_measurements(valid_bundle):
    bundle = altered(valid_bundle)
    bundle[0]["cases"][0]["memory_runs"][0]["update_seconds"] = 1
    with pytest.raises(validator.ArtifactError, match="Instrumented memory timing"):
        check(bundle)


def test_silent_rebuild_and_unpaired_hash_seed_are_rejected(valid_bundle):
    bundle = altered(valid_bundle)
    bundle[0]["cases"][0]["runs"][0]["update_stats"]["update_method"] = "rematerialize"
    with pytest.raises(validator.ArtifactError, match="changed algorithm"):
        check(bundle)
    bundle = altered(valid_bundle)
    bundle[0]["cases"][0]["runs"][0]["hash_seed"] = "999"
    with pytest.raises(validator.ArtifactError, match="hash seed"):
        check(bundle)


def test_summary_and_promotion_are_recomputed_from_raw_observations(valid_bundle):
    bundle = altered(valid_bundle)
    bundle[0]["cases"][0]["summary"]["combined"]["median_ratio"] *= 0.5
    with pytest.raises(validator.ArtifactError, match="recomputed summary"):
        check(bundle)
    bundle = altered(valid_bundle)
    bundle[0]["promotion_assessment"]["adaptive_threshold_met"] = False
    with pytest.raises(validator.ArtifactError, match="recomputed promotion"):
        check(bundle)


def test_source_archive_hash_and_content_hash_both_matter(valid_bundle, tmp_path):
    report, manifest, _, files = altered(valid_bundle)
    archive_path = tmp_path / manifest["archive"]
    changed = dict(files)
    changed["src/dlp_reasoner/engine.py"] += b"# changed\n"
    new_hash = make_archive(archive_path, [(name, data, "file") for name, data in changed.items()])
    with pytest.raises(validator.ArtifactError, match="archive SHA-256"):
        validator.validate_data(report, manifest, archive_path)
    manifest["archive_sha256"] = new_hash
    with pytest.raises(validator.ArtifactError, match="content SHA-256"):
        validator.validate_data(report, manifest, archive_path)


@pytest.mark.parametrize("extra", [("../outside", b"bad", "file"),
                                    ("link", "../outside", "symlink"),
                                    ("benchmarks/research.py", b"duplicate", "file")])
def test_archive_never_extracts_unsafe_links_paths_or_duplicate_members(valid_bundle, tmp_path, extra):
    report, manifest, _, files = altered(valid_bundle)
    archive_path = tmp_path / manifest["archive"]
    manifest["archive_sha256"] = make_archive(
        archive_path, [(name, data, "file") for name, data in files.items()] + [extra])
    with pytest.raises(validator.ArtifactError, match="unsafe|duplicate"):
        validator.validate_data(report, manifest, archive_path)
    assert not (tmp_path.parent / "outside").exists()


def test_archived_protocol_must_match_what_the_report_claims(valid_bundle):
    bundle = altered(valid_bundle)
    bundle[0]["protocol"]["primary_endpoint"] = "a different operation"
    with pytest.raises(validator.ArtifactError, match="archived protocol"):
        check(bundle)


def test_manifest_cannot_replace_measured_inventory(valid_bundle):
    bundle = altered(valid_bundle)
    del bundle[1]["files_sha256"]["src/dlp_reasoner/support.py"]
    with pytest.raises(validator.ArtifactError, match="Manifest files"):
        check(bundle)


def test_json_parser_rejects_duplicate_keys_and_nonfinite_constants():
    with pytest.raises(validator.ArtifactError, match="Duplicate JSON"):
        validator.decode_json('{"status":"passed","status":"failed"}')
    with pytest.raises(validator.ArtifactError, match="Nonfinite JSON"):
        validator.decode_json('{"seconds":NaN}')


def test_file_wrapper_turns_malformed_evidence_into_concise_validation_failure(valid_bundle, tmp_path):
    _, manifest, archive, _ = valid_bundle
    report_path, manifest_path = tmp_path / "report.json", tmp_path / "manifest.json"
    report_path.write_text('["wrong top-level type"]')
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(validator.ArtifactError, match="Malformed"):
        validator.validate_artifacts(report_path, manifest_path, archive)
