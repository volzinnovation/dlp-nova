"""Source-grounded checks for the two distinct Bach examples in the thesis."""
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from rdflib import BNode, Graph, Namespace, OWL, RDF, RDFS
from rdflib.compare import isomorphic

from dlp_reasoner import ProfileError, Reasoner

# The benchmark runner is repository tooling rather than an installed package.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BACH = Namespace("http://www.jsbach.org/bach#")
EXAMPLES = ROOT / "examples"
JA = BACH["johann-ambrosius"]
JS = BACH["johann-sebastian"]
WF = BACH["wilhelm-friedemann"]
MB = BACH["maria-barbara"]
JC = BACH["johann-christian"]


@pytest.fixture(params=["bach.ttl", "bach.owl"])
def ontology(request):
    return Reasoner.from_file(EXAMPLES / request.param, profile="L3")


def test_bach_rdfxml_and_turtle_encode_the_same_ontology():
    turtle = Graph().parse(EXAMPLES / "bach.ttl", format="turtle")
    xml = Graph().parse(EXAMPLES / "bach.owl", format="xml")
    assert isomorphic(turtle, xml)


@pytest.mark.parametrize("filename", ["bach.ttl", "bach.owl"])
def test_full_bach_example_requires_l3(filename):
    with pytest.raises(ProfileError):
        Reasoner.from_file(EXAMPLES / filename, profile="L2")


def test_bach_named_class_answers_follow_table_2_5(ontology):
    assert ontology.complete
    assert ontology.consistency == "consistent"
    assert ontology.instances(BACH.Father) == {JA, JS}
    assert ontology.instances(BACH.Person) == {JA, JS, WF, MB, BACH["anna-magdalena"]}
    assert ontology.instances(BACH.Masterpiece) == {BACH.BWV248}
    assert ontology.instances(BACH.Composition) == {BACH.BWV213, BACH.BWV214, BACH.BWV248}
    assert ontology.instances(BACH.Homage) == {BACH.BWV213, BACH.BWV214}
    assert ontology.instances(BACH.LeipzigInhabitant) == {JS}
    assert ontology.subsumes(BACH.Person, BACH.Father)
    assert not ontology.subsumes(BACH.Father, BACH.Person)


def test_bach_existential_child_does_not_name_johann_sebastian(ontology):
    assert ontology.property_values(JA, BACH.hasChild) == set()
    witnesses = ontology.property_values(JA, BACH.hasChild, include_witnesses=True)
    assert witnesses and all(isinstance(child, BNode) for child in witnesses)
    assert any(ontology.entails(child, RDF.type, BACH.Man) for child in witnesses)
    assert not ontology.entails(JA, BACH.hasChild, JS)
    assert not ontology.entails(JA, BACH.ancestorOf, WF)
    assert ontology.property_values(JS, BACH.hasChild) == {WF}


def test_bach_symmetry_does_not_invent_wife_or_husband_classification(ontology):
    assert ontology.property_values(JS, BACH.marriedTo) == {MB, BACH["anna-magdalena"]}
    assert ontology.property_values(MB, BACH.marriedTo) == {JS}
    assert ontology.property_values(BACH["anna-magdalena"], BACH.marriedTo) == {JS}
    assert ontology.instances(BACH.Wife) == set()
    assert ontology.instances(BACH.Husband) == set()
    assert ontology.instances(BACH.Mother) == set()


def test_bach_composition_existentials_preserve_the_non_voice_constraint(ontology):
    voices = ontology.instances(BACH.Voice, include_witnesses=True)
    birthdays = ontology.instances(BACH.Birthday, include_witnesses=True)
    for cantata in (BACH.BWV213, BACH.BWV214, BACH.BWV248):
        instruments = ontology.property_values(cantata, BACH.forInstrument,
                                               include_witnesses=True)
        assert instruments & voices
        assert ontology.property_values(cantata, BACH.forInstrument) == set()
    for cantata in (BACH.BWV213, BACH.BWV214):
        assert ontology.property_values(cantata, BACH.forEvent,
                                        include_witnesses=True) & birthdays
    # T15 requires an instrument outside Voice. Making every individual a Voice
    # contradicts that existential; merely omitting a Voice assertion would not.
    ontology.update(add=[(BACH.Voice, OWL.equivalentClass, OWL.Thing)])
    assert ontology.consistency == "inconsistent"


def test_bach_universal_query_rejects_closed_world_reading(ontology):
    # T11 constrains composed works. Observed values cannot establish that
    # somebody has only masterpieces: universal antecedents are outside DLP.
    universal, = ontology.graph.subjects(OWL.allValuesFrom, BACH.Masterpiece)
    with pytest.raises(ProfileError):
        ontology.instances(universal)
    assert ontology.instances(BACH.Masterpiece) == {BACH.BWV248}
    assert not ontology.entails(JS, BACH.hasComposed, BACH.BWV213)


def test_family_input_preserves_the_nine_figure_6_2_edges():
    family = Reasoner.from_file(EXAMPLES / "bach-family.ttl", profile="L0")
    assert family.complete and family.consistency == "consistent"
    assert set(family.graph.subject_objects(BACH.ancestorOf)) == {
        (BACH.johannes, BACH.heinrich), (BACH.johannes, BACH.christoph),
        (BACH.heinrich, BACH["johann-christoph"]),
        (BACH["johann-christoph"], BACH["johann-michael"]),
        (BACH["johann-michael"], MB), (MB, WF), (JS, WF), (JA, JS),
        (BACH.christoph, JA),
    }
    assert len(family.property_pairs(BACH.ancestorOf)) == 24
    assert family.property_pairs(BACH.inDynasty) == family.property_pairs(BACH.ancestorOf)
    assert not family.is_symmetric(BACH.inDynasty)
    assert not family.is_transitive(BACH.inDynasty)


def test_family_fact_transaction_retracts_only_unsupported_ancestry():
    family = Reasoner.from_file(EXAMPLES / "bach-family.ttl", profile="L0")
    before = family.property_pairs(BACH.ancestorOf)
    family.update(remove=[(JS, BACH.ancestorOf, WF)], add=[(JS, BACH.ancestorOf, JC)])
    after = family.property_pairs(BACH.ancestorOf)
    assert before - after == {(JS, WF), (JA, WF), (BACH.christoph, WF)}
    assert after - before == {(JS, JC), (JA, JC), (BACH.christoph, JC), (BACH.johannes, JC)}
    assert family.entails(BACH.johannes, BACH.ancestorOf, WF)
    assert family.property_pairs(BACH.inDynasty) == after
    assert family.engine.facts == Reasoner(family.graph, profile="L0").engine.facts


def test_family_rule_deletion_and_symmetry_match_the_corrected_thesis_example():
    family = Reasoner.from_file(EXAMPLES / "bach-family.ttl", profile="L0")
    ancestors = family.property_pairs(BACH.ancestorOf)
    inclusion = (BACH.ancestorOf, RDFS.subPropertyOf, BACH.inDynasty)
    family.update(remove=[inclusion])
    assert family.property_pairs(BACH.inDynasty) == set()
    assert family.property_pairs(BACH.ancestorOf) == ancestors
    family.update(add=[inclusion, (BACH.inDynasty, RDF.type, OWL.SymmetricProperty)])
    assert family.property_pairs(BACH.inDynasty) == ancestors | {(b, a) for a, b in ancestors}
    assert family.entails(BACH["johann-christoph"], BACH.inDynasty, BACH.johannes)
    assert not family.entails(BACH["johann-christoph"], BACH.inDynasty, BACH.christoph)
    assert not family.is_transitive(BACH.inDynasty)
    assert family.engine.facts == Reasoner(family.graph, profile="L0").engine.facts


@pytest.fixture(scope="module")
def benchmark_results():
    from benchmarks.bach import build_bach_cases
    from benchmarks.run import worker

    return {(case["variant"], case["format"]): worker({**case, "repeats": 2})
            for case in build_bach_cases()}


def test_bach_suite_selects_both_ontology_syntaxes_and_the_separate_family():
    from benchmarks.bach import build_bach_cases
    from benchmarks.run import build_cases

    expected = [
        {"kind": "bach", "variant": "ontology", "format": "turtle"},
        {"kind": "bach", "variant": "ontology", "format": "xml"},
        {"kind": "bach", "variant": "family", "format": "turtle"},
    ]
    assert build_bach_cases() == expected
    assert build_cases("bach") == expected


@pytest.mark.parametrize("variant,syntax,profile", [
    ("ontology", "turtle", "L3"), ("ontology", "xml", "L3"), ("family", "turtle", "L0"),
])
def test_bach_benchmark_records_validated_query_answers_and_each_repetition(
        benchmark_results, variant, syntax, profile):
    result = benchmark_results[variant, syntax]
    assert result["validation"] == "passed"
    assert result["workload"]["profile"] == profile
    assert result["workload"]["rdf_format"] == syntax
    for phase in ("parse", "compile", "materialize", "query"):
        assert len(result[f"{phase}_seconds"]["samples"]) == 2
        assert all(value >= 0 for value in result[f"{phase}_seconds"]["samples"])
    assert len(result["materialized_fact_counts"]) == 2
    assert len(set(result["materialized_fact_counts"])) == 1
    queries = result["queries"]
    assert len(queries) == result["workload"]["query_count"] > 0
    assert len({query["id"] for query in queries}) == len(queries)
    for query in queries:
        assert query["method"] and query["source"]
        assert query["validation"] == "passed"
        expected = query["expected"]
        if isinstance(expected, list):
            expected = sorted(expected, key=json.dumps)
        assert query["actual"] == expected
        assert len(query["seconds"]["samples"]) == 2


def test_bach_hashes_identify_graph_and_original_documents_separately(benchmark_results):
    turtle = benchmark_results["ontology", "turtle"]
    xml = benchmark_results["ontology", "xml"]
    assert turtle["input_sha256"] == xml["input_sha256"]
    assert turtle["input_file_sha256"] != xml["input_file_sha256"]
    for result in benchmark_results.values():
        document = ROOT / result["workload"]["source_file"]
        assert result["input_file_sha256"] == hashlib.sha256(document.read_bytes()).hexdigest()
        assert len(result["input_sha256"]) == 64
        assert int(result["input_sha256"], 16) >= 0
        manifest = ROOT / result["workload"]["query_manifest"]
        assert result["workload"]["query_manifest_sha256"] == hashlib.sha256(
            manifest.read_bytes()).hexdigest()


def test_bach_benchmark_records_all_three_independent_maintenance_scenarios(benchmark_results):
    operations = benchmark_results["family", "turtle"]["maintenance_operations"]
    assert set(operations) == {"facts_update", "rule_delete", "symmetry_insert"}
    expected_methods = {
        "facts_update": "dred", "rule_delete": "dred-rules",
        "symmetry_insert": "incremental-rules",
    }
    for name, operation in operations.items():
        assert len(operation["seconds"]["samples"]) == 2
        assert len(operation["rebuild_seconds"]["samples"]) == 2
        assert len(operation["samples"]) == 2
        for sample in operation["samples"]:
            assert sample["validation"] == "matches-reachability-and-fresh-closure"
            assert sample["stats"]["update_method"] == expected_methods[name]
    assert len(operations["facts_update"]["samples"][0]["ancestor_added"]) == 4
    assert len(operations["facts_update"]["samples"][0]["ancestor_removed"]) == 3
    assert operations["rule_delete"]["samples"][0]["dynasty_pairs"] == []
    assert len(operations["symmetry_insert"]["samples"][0]["dynasty_pairs"]) == 48


def test_bach_benchmark_fails_when_a_query_result_disagrees(monkeypatch):
    from benchmarks.run import worker

    # An empty result must fail the positive Father check, never silently
    # produce a timing report labeled as validated.
    monkeypatch.setattr(Reasoner, "instances", lambda *args, **kwargs: set())
    with pytest.raises(AssertionError):
        worker({"kind": "bach", "variant": "ontology", "format": "turtle", "repeats": 1})


@pytest.fixture
def bach_report(benchmark_results):
    return {
        "timestamp": "test", "suite": "bach", "repeats": 2, "planned_cases": 3,
        "output_file": "bach-results.json", "measurement_protocol": "phase-timings-v1",
        "environment": {"source_sha256": {}, "python": "test", "platform": "test"},
        "results": deepcopy(list(benchmark_results.values())),
    }


def test_bach_comparison_accepts_identical_answers_and_rdf_maintenance(bach_report):
    from benchmarks.bach import markdown_report
    from benchmarks.run import compare_baseline

    comparison = compare_baseline(bach_report, deepcopy(bach_report), "baseline.json")
    assert len(comparison["matched"]) == 3
    assert not comparison["skipped"]
    assert all(row["correctness"]["verified"] for row in comparison["matched"])
    family = comparison["matched"][2]
    assert set(family["maintenance_operations"]) == {
        "facts_update", "rule_delete", "symmetry_insert",
    }
    assert not family["maintenance_skipped"]
    bach_report["comparison"] = comparison
    assert "passed | 1.000 | 1.000" in markdown_report(bach_report)


@pytest.mark.parametrize("field,value", [
    ("actual", []), ("expected", []), ("arguments", ["Mother"]), ("method", "types"),
    ("expression", "[ owl:intersectionOf ( :Man :Person ) ]"),
    ("validation", "failed"),
])
def test_bach_comparison_rejects_changed_query_evidence(bach_report, field, value):
    from benchmarks.bach import markdown_report
    from benchmarks.run import compare_baseline

    baseline = deepcopy(bach_report)
    bach_report["results"][0]["queries"][0][field] = value
    comparison = compare_baseline(bach_report, baseline, "baseline.json")
    assert not comparison["matched"][0]["correctness"]["verified"]
    assert not comparison["matched"][0]["correctness"]["expected_query_answers_match"]
    bach_report["comparison"] = comparison
    assert "FAILED" in markdown_report(bach_report)


@pytest.mark.parametrize("field,value", [
    ("ancestor_pairs", []), ("dynasty_pairs", []), ("ancestor_added", []),
    ("ancestor_removed", []), ("added_triples", 2), ("removed_triples", 2),
    ("closure_facts", 0), ("validation", "failed"),
])
def test_bach_comparison_checks_every_maintenance_sample(bach_report, field, value):
    from benchmarks.run import compare_baseline

    baseline = deepcopy(bach_report)
    operation = bach_report["results"][2]["maintenance_operations"]["facts_update"]
    operation["samples"][1][field] = value
    comparison = compare_baseline(bach_report, baseline, "baseline.json")
    assert not comparison["matched"][2]["correctness"]["verified"]


def test_bach_comparison_rejects_missing_query_and_maintenance_repetitions(bach_report):
    from benchmarks.run import compare_baseline

    baseline = deepcopy(bach_report)
    bach_report["results"][0]["queries"][0]["seconds"]["samples"].pop()
    bach_report["results"][2]["maintenance_operations"]["rule_delete"]["samples"].pop()
    comparison = compare_baseline(bach_report, baseline, "baseline.json")
    assert not comparison["matched"][0]["correctness"]["verified"]
    assert not comparison["matched"][2]["correctness"]["verified"]
