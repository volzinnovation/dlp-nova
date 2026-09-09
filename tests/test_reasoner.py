import json

import pytest
from rdflib import BNode, Graph, Namespace, OWL, RDF, RDFS

from dlp_reasoner import (
    Reasoner, ProfileError, IncompleteReasoningError, InconsistentOntologyError,
)
from dlp_reasoner.cli import main

EX = Namespace("https://example.org/test#")
PREFIX = """@prefix : <https://example.org/test#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
"""


def make(text, **options):
    return Reasoner(Graph().parse(data=PREFIX + text, format="turtle"), **options)


def test_family_end_to_end():
    r = Reasoner.from_file("examples/family.ttl")
    ns = Namespace("https://example.org/family#")
    assert r.consistency == "consistent"
    assert r.entails(ns.jsbach, RDF.type, ns.Composer)
    assert r.entails(ns.johann, ns.ancestorOf, ns.grandchild)
    assert r.entails(ns.wilhelm, ns.hasParent, ns.jsbach)
    assert r.instances(ns.Parent) == {ns.johann, ns.jsbach}
    assert r.property_values(ns.jsbach, ns.hasChild) == {ns.wilhelm}
    assert r.subsumes(ns.Person, ns.Composer)
    assert not r.subsumes(ns.Composer, ns.Person)


def test_subsumption_is_not_accidental_abox_overlap():
    r = make(":a a :A, :B . :A rdfs:subClassOf :C .")
    assert not r.subsumes(EX.B, EX.A)
    assert r.subsumes(EX.C, EX.A)
    assert r.is_satisfiable(EX.A)


def test_unsatisfiable_class_does_not_make_empty_kb_inconsistent():
    r = make(":A rdfs:subClassOf :B . :A owl:disjointWith :B .")
    assert r.consistency == "consistent"
    assert not r.is_satisfiable(EX.A)
    assert r.subsumes(EX.Z, EX.A)


def test_open_world_no_negation_by_absence():
    r = make(":a :p :b . :A rdfs:subClassOf [ owl:onProperty :p; owl:maxCardinality 1 ] .")
    assert not r.entails(EX.a, RDF.type, EX.A)
    assert not r.entails(EX.a, OWL.differentFrom, EX.b)


def test_update_retracts_equality_and_preserves_other_supports():
    r = make(":a a :A . :a owl:sameAs :b . :A rdfs:subClassOf :B .")
    assert r.entails(EX.b, RDF.type, EX.B)
    r.update(remove=[(EX.a, OWL.sameAs, EX.b)])
    assert not r.entails(EX.b, RDF.type, EX.B)
    assert r.entails(EX.a, RDF.type, EX.B)
    r.update(add=[(EX.B, RDFS.subClassOf, EX.C)])
    assert r.entails(EX.a, RDF.type, EX.C)
    r.update(remove=[(EX.A, RDFS.subClassOf, EX.B)])
    assert not r.entails(EX.a, RDF.type, EX.C)


def test_bad_update_does_not_mutate_original():
    r = make(":a a :A .")
    restriction = BNode()
    additions = [(EX.A, RDFS.subClassOf, restriction),
                 (restriction, OWL.onProperty, EX.p),
                 (restriction, OWL.someValuesFrom, EX.B)]
    with pytest.raises(ProfileError):
        r.update(add=additions)
    assert len(r.graph) == 1
    assert r.entails(EX.a, RDF.type, EX.A)


def test_round_trip_formats(tmp_path):
    r = make(":a a :A . :A rdfs:subClassOf :B .")
    for suffix, fmt in [("ttl", "turtle"), ("rdf", "xml"), ("nt", "nt")]:
        path = tmp_path / ("ontology." + suffix)
        r.to_graph().serialize(path, format=fmt, encoding="utf-8")
        result = Reasoner.from_file(path)
        assert result.entails(EX.a, RDF.type, EX.B)


def test_constraint_error_and_cli_status(capsys):
    r = Reasoner.from_file("examples/inconsistent.ttl")
    assert r.consistency == "inconsistent"
    with pytest.raises(InconsistentOntologyError):
        r.instances(EX.A)
    assert main(["validate", "examples/inconsistent.ttl"]) == 2
    assert json.loads(capsys.readouterr().out)["consistency"] == "inconsistent"


def test_l3_bound_is_unknown_not_negative():
    r = make(":a a :A . :A rdfs:subClassOf [ owl:onProperty :p; owl:someValuesFrom :A ] .",
             profile="L3", max_depth=3)
    assert not r.complete
    assert r.consistency == "unknown"
    assert r.entails(EX.a, RDF.type, EX.A)
    with pytest.raises(IncompleteReasoningError):
        r.entails(EX.a, RDF.type, EX.B)
    with pytest.raises(IncompleteReasoningError):
        r.instances(EX.A)


def test_expression_query():
    r = make(":a a :A . :a :p :b . :b a :B . :Query owl:equivalentClass [ owl:intersectionOf (:A :C) ] .")
    expr = BNode()
    r.graph.add((expr, OWL.onProperty, EX.p))
    r.graph.add((expr, OWL.someValuesFrom, EX.B))
    assert r.instances(expr) == {EX.a}


def test_existential_witness_visibility():
    r = Reasoner.from_file("examples/existential.ttl", profile="L3")
    ns = Namespace("https://example.org/existential#")
    assert r.complete
    assert not r.property_values(ns.alice, ns.hasChild)
    assert len(r.property_values(ns.alice, ns.hasChild, include_witnesses=True)) == 1


@pytest.mark.parametrize("suffix,text", [("ttl", "this is not Turtle"), ("rdf", "<not-xml>"), ("nt", "bad triple")])
def test_cli_parse_errors_are_structured(tmp_path, capsys, suffix, text):
    path = tmp_path / ("bad." + suffix)
    path.write_text(text)
    assert main(["validate", str(path)]) == 1
    error = json.loads(capsys.readouterr().err)
    assert error["type"] == "ProfileError"
    assert "Invalid" in error["error"]
