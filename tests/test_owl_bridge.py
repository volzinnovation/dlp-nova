"""Controls for the exact entailment task used in the finite L3 comparison."""
from pathlib import Path
import hashlib
import json
import sys
import zipfile

import pytest
from rdflib import Graph, OWL, RDF, RDFS, URIRef

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmarks.owl_bridge import (  # noqa: E402
    CONFIGURATIONS, document, execution_order, expected_answers, worker,
)
import benchmarks.owl_bridge as bridge  # noqa: E402
from dlp_reasoner import Reasoner  # noqa: E402
from dlp_reasoner.model import ProfileError  # noqa: E402


def parsed(population, omit=None):
    return Graph().parse(data=document(population, omit), format="xml",
                         publicID="urn:owl-bridge:document")


def test_fixed_tbox_has_exact_existential_bridge_and_no_asserted_answers():
    graph = parsed(3)
    a, b, c = [URIRef("urn:owl-bridge:" + name) for name in "ABC"]
    restriction = next(graph.subjects(RDF.type, OWL.Restriction))
    assert (a, RDFS.subClassOf, restriction) in graph
    assert (restriction, OWL.someValuesFrom, b) in graph
    assert (restriction, RDFS.subClassOf, c) in graph
    assert len(list(graph.subjects(RDF.type, a))) == 3
    assert list(graph.subjects(RDF.type, c)) == []
    assert document(3) == document(3)
    with pytest.raises(ProfileError):
        Reasoner(graph, profile="L2")


@pytest.mark.parametrize("population", [1, 3])
def test_bridge_answers_match_independent_gci_argument_and_negative_control(population):
    reasoner = Reasoner(parsed(population), profile="L3")
    positive, negative = expected_answers(population)
    assert reasoner.complete and reasoner.consistency == "consistent"
    assert sorted(map(str, reasoner.instances(URIRef("urn:owl-bridge:C")))) == positive
    assert sorted(map(str, reasoner.instances(URIRef("urn:owl-bridge:D")))) == negative
    assert "urn:owl-bridge:negative-b" not in positive


@pytest.mark.parametrize("omitted", ["existential", "bridge"])
def test_each_existential_axiom_is_essential_to_named_c_entailment(omitted):
    reasoner = Reasoner(parsed(3, omitted), profile="L3")
    assert reasoner.complete and reasoner.consistency == "consistent"
    assert reasoner.instances(URIRef("urn:owl-bridge:C")) == set()


@pytest.mark.parametrize("population_position", range(3))
def test_three_blocks_balance_every_configuration_position(population_position):
    orders = [execution_order(block, population_position) for block in range(3)]
    for position in range(3):
        assert {order[position] for order in orders} == set(CONFIGURATIONS)


def test_python_worker_reports_identical_named_answer_contract(tmp_path):
    path = tmp_path / "bridge.owl"
    path.write_bytes(document(3))
    result = worker(path, "b1254c4")
    assert result["positive"] == expected_answers(3)[0]
    assert result["negative"] == [] and result["consistent"]
    for key in ("load_seconds", "construct_seconds", "consistency_seconds",
                "positive_query_seconds", "negative_query_seconds"):
        assert result[key] >= 0


def test_runtime_expands_pinned_bundles_and_rejects_cached_drift(tmp_path, monkeypatch):
    runtime = tmp_path / "current-hermit"
    runtime.mkdir()
    jar = runtime / "bundle.jar"
    with zipfile.ZipFile(jar, "w") as archive:
        archive.writestr("lib/required.jar", b"nested dependency bytes")
        archive.writestr("lib/excluded.jar", b"duplicate dependency")
    digest = hashlib.sha256(jar.read_bytes()).hexdigest()
    lock = tmp_path / "dependencies.json"
    lock.write_text(json.dumps({"distribution": "test:bundle:1", "owlapi": "test",
                                "artifacts": [{"name": jar.name, "sha256": digest}],
                                "nested_jar_exclusions": ["lib/excluded.jar"]}))
    monkeypatch.setattr(bridge, "DEPENDENCIES", lock)
    metadata = bridge.prepare_runtime(tmp_path)
    assert len(metadata["classpath"]) == 2
    assert (runtime / "nested/bundle/required.jar").read_bytes() == b"nested dependency bytes"
    assert not (runtime / "nested/bundle/excluded.jar").exists()
    jar.write_bytes(b"changed artifact")
    with pytest.raises(RuntimeError, match="cached jar drift"):
        bridge.prepare_runtime(tmp_path)
