"""Context/profile boundary tests for the thesis-to-Horn translator."""
import pytest
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL

from dlp_reasoner.compiler import compile_graph
from dlp_reasoner.model import EQ, NEQ, Atom, ProfileError, Skolem

EX = Namespace("http://example.org/")
PREFIX = """@prefix : <http://example.org/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
"""


def compile_ttl(text, profile="L2"):
    return compile_graph(Graph().parse(data=PREFIX + text, format="turtle"), profile)


def predicates(program):
    return {atom.predicate for rule in program.rules for atom in
            (*rule.body, *((rule.head,) if rule.head else ()))}


@pytest.mark.parametrize("profile", ["L0", "L1", "L2", "L3"])
def test_basic_subsumption_assertions_and_declarations(profile):
    program = compile_ttl(":A a owl:Class; rdfs:subClassOf :B. :a a :A. :a :p :b.", profile)
    assert Atom(EX.A, (EX.a,)) in program.facts
    assert Atom(EX.p, (EX.a, EX.b)) in program.facts
    assert not any(f.predicate == OWL.Class for f in program.facts)
    assert len(program.rules) == 1
    rule = program.rules[0]
    assert rule.head.predicate == EX.B
    assert rule.body[0].predicate == EX.A
    assert rule.head.args == rule.body[0].args


def test_lloyd_topor_intersection_union_existential_universal():
    program = compile_ttl("""
      [owl:intersectionOf (:A [owl:unionOf (:B :C)]
           [a owl:Restriction; owl:onProperty :p; owl:someValuesFrom :D])]
      rdfs:subClassOf [owl:intersectionOf (:E
           [a owl:Restriction; owl:onProperty :q; owl:allValuesFrom :F])].
    """, "L0")
    assert len(program.rules) == 6
    assert {r.head.predicate for r in program.rules if isinstance(r.head.predicate, URIRef)} == {
        EX.E, EX.F}
    assert {EX.p, EX.q, EX.D}.issubset(predicates(program))


def test_named_constructor_keeps_named_predicate():
    program = compile_ttl(":A owl:intersectionOf (:B :C). :a a :A.")
    assert {r.head.predicate for r in program.rules if isinstance(r.head.predicate, URIRef)} == {
        EX.A, EX.B, EX.C}
    assert Atom(EX.A, (EX.a,)) in program.facts


@pytest.mark.parametrize("text,minimum", [
    (":a owl:sameAs :b.", 1),
    (":a owl:differentFrom :b.", 2),
    (":p a owl:FunctionalProperty.", 1),
    (":p a owl:InverseFunctionalProperty.", 1),
    (":A rdfs:subClassOf owl:Thing.", 1),
    (":A rdfs:subClassOf owl:Nothing.", 2),
    (":A owl:disjointWith :B.", 2),
    (":A rdfs:subClassOf [owl:complementOf :B].", 2),
    (":A rdfs:subClassOf [owl:oneOf (:a)].", 1),
    (":A rdfs:subClassOf [owl:onProperty :p; owl:maxCardinality 1].", 1),
    (":A rdfs:subClassOf [owl:onProperty :p; owl:maxCardinality 0].", 2),
    (":A rdfs:subClassOf [owl:onProperty :p; owl:someValuesFrom :B].", 3),
    (":A rdfs:subClassOf [owl:onProperty :p; owl:minCardinality 2].", 3),
    (":A rdfs:subClassOf [owl:onProperty :p; owl:cardinality 1].", 3),
    (":A rdfs:subClassOf [owl:onProperty :p; owl:cardinality 0].", 2),
])
def test_profile_boundaries(text, minimum):
    for level in range(4):
        if level < minimum:
            with pytest.raises(ProfileError):
                compile_ttl(text, f"L{level}")
        else:
            compile_ttl(text, f"L{level}")


@pytest.mark.parametrize("text", [
    ":A rdfs:subClassOf [owl:unionOf (:B :C)].",
    "[owl:onProperty :p; owl:allValuesFrom :A] rdfs:subClassOf :B.",
    ":A rdfs:subClassOf [owl:oneOf (:a :b)].",
    ":A rdfs:subClassOf [owl:onProperty :p; owl:maxCardinality 2].",
    "[owl:onProperty :p; owl:minCardinality 2] rdfs:subClassOf :A.",
    ":A owl:complementOf :B.",
    ":p owl:propertyChainAxiom (:q :r).",
    ":p a owl:ReflexiveProperty.",
    ":A owl:hasKey (:p).",
    ":p rdfs:range xsd:integer.",
    ":A rdfs:subClassOf [owl:onProperty :p; owl:someValuesFrom xsd:string].",
    ":o owl:imports <http://example.org/remote>.",
    "_:x owl:onDatatype xsd:integer; owl:withRestrictions ().",
])
def test_rejects_nonhorn_or_unsupported_semantics(text):
    with pytest.raises(ProfileError):
        compile_ttl(text, "L3")


@pytest.mark.parametrize("text", [
    "_:r a owl:Restriction; owl:onProperty :p.",
    "_:r owl:someValuesFrom :A.",
    "_:r owl:onProperty :p, :q; owl:someValuesFrom :A.",
    "_:r owl:onProperty :p; owl:someValuesFrom :A; owl:allValuesFrom :B.",
    "_:r owl:onProperty :p; owl:minCardinality -1.",
    "_:r owl:onProperty :p; owl:minCardinality true.",
    "_:r owl:onProperty :p; owl:minCardinality 1.5.",
    "_:r owl:intersectionOf _:list. _:list rdf:first :A; rdf:rest _:list.",
    "_:r owl:intersectionOf _:list. _:list rdf:first :A.",
    "_:r owl:intersectionOf (_:r).",
    "_:r owl:intersectionOf (:A); owl:unionOf (:B).",
    ":a a _:r.",
])
def test_rejects_malformed_rdf_expressions(text):
    with pytest.raises(ProfileError):
        compile_ttl(text)


def test_nominal_lhs_and_hasvalue_both_sides():
    program = compile_ttl("""
      [owl:oneOf (:a :b)] rdfs:subClassOf :A.
      :B owl:equivalentClass [owl:onProperty :p; owl:hasValue :c].
    """, "L1")
    assert len(program.rules) == 4
    assert any(a.predicate == EQ for r in program.rules for a in r.body)
    assert any(r.head.predicate == EX.p for r in program.rules)


def test_all_different_and_disjoint_members():
    program = compile_ttl("""
      [] a owl:AllDifferent; owl:distinctMembers (:a :b :c).
      [] a owl:AllDisjointClasses; owl:members (:A :B :C).
    """)
    assert len([f for f in program.facts if f.predicate == NEQ]) == 3
    assert len(program.rules) == 3
    assert all(r.head is None for r in program.rules)


def test_property_axioms_and_inverse_expression():
    program = compile_ttl("""
      :p a owl:TransitiveProperty, owl:SymmetricProperty;
          rdfs:subPropertyOf :q; owl:equivalentProperty :r; owl:inverseOf :s;
          rdfs:domain :A; rdfs:range :B.
      :A rdfs:subClassOf [owl:onProperty [owl:inverseOf :p]; owl:hasValue :a].
    """, "L0")
    assert len(program.rules) == 10
    inverse = [r for r in program.rules if r.head.predicate == EX.p and
               EX.a in r.head.args]
    assert len(inverse) == 1
    assert inverse[0].head.args[0] == EX.a


def test_arbitrary_expression_assertion():
    program = compile_ttl(""":a a [owl:intersectionOf (:A
      [owl:onProperty :p; owl:allValuesFrom :B])]. :a :p :b.""")
    assert Atom(EX.A, (EX.a,)) in program.facts
    rule = program.rules[0]
    assert rule.head.predicate == EX.B
    assert rule.body[0].args[0] == EX.a


def test_metadata_and_literal_facts():
    program = compile_ttl("""
      :p a owl:DatatypeProperty. :note a owl:AnnotationProperty.
      :A a owl:Class; rdfs:label "A"; :note "metadata".
      :a :p 42.
    """)
    assert program.facts == {Atom(EX.p, (EX.a, Literal(42)))}


def test_l3_witnesses_stable_and_distinct():
    text = ":A rdfs:subClassOf [owl:onProperty :p; owl:minCardinality 3]."
    first, second = compile_ttl(text, "L3"), compile_ttl(text, "L3")
    first_skolems = {r.head.args[1].symbol for r in first.rules if r.head.predicate == EX.p}
    second_skolems = {r.head.args[1].symbol for r in second.rules if r.head.predicate == EX.p}
    assert first_skolems == second_skolems
    assert len(first_skolems) == 3
    assert len([r for r in first.rules if r.head.predicate == NEQ]) == 3


def test_l3_nested_restrictions_do_not_require_body_term_unification():
    program = compile_ttl("""
      :A rdfs:subClassOf [owl:onProperty :p; owl:someValuesFrom
        [owl:onProperty :q; owl:allValuesFrom [owl:onProperty :r; owl:maxCardinality 1]]].
    """, "L3")
    assert any(isinstance(t, Skolem) for r in program.rules if r.head for t in r.head.args)
    assert not any(isinstance(t, Skolem) for r in program.rules for a in r.body for t in a.args)
    assert EQ in predicates(program)


def test_empty_union_and_bottom_assertions():
    program = compile_ttl(":a a [owl:unionOf ()].")
    assert len(program.rules) == 1
    assert program.rules[0].head is None and not program.rules[0].body


def test_invalid_profile():
    with pytest.raises(ProfileError, match="Unknown DLP profile"):
        compile_graph(Graph(), "OWL-FULL")


def test_structural_factoring_prevents_exponential_dnf():
    unions = " ".join(f"[owl:unionOf (:A{i} :B{i})]" for i in range(15))
    program = compile_ttl(f"[owl:intersectionOf ({unions})] rdfs:subClassOf :C.", "L0")
    assert len(program.rules) == 32  # 30 union branches + intersection + inclusion.
    assert max(len(rule.body) for rule in program.rules) == 15


def test_normalized_negation_keeps_horn_integrity_constraints():
    from dlp_reasoner import Reasoner
    text = ":A rdfs:subClassOf [owl:complementOf [owl:intersectionOf (:B :C)]]."
    graph = Graph().parse(data=PREFIX + text + " :a a :A,:B,:C.", format="turtle")
    assert Reasoner(graph).consistency == "inconsistent"


def test_dead_inclusion_does_not_suppress_witness_filler_definitions():
    from dlp_reasoner import Reasoner
    text = """
      owl:Nothing rdfs:subClassOf [owl:onProperty :p; owl:someValuesFrom
         [owl:onProperty :q; owl:hasValue :b]].
      :A rdfs:subClassOf [owl:onProperty :p; owl:someValuesFrom
         [owl:onProperty :q; owl:hasValue :b]].
      :a a :A.
    """
    graph = Graph().parse(data=PREFIX + text, format="turtle")
    reasoner = Reasoner(graph, profile="L3")
    witnesses = reasoner.property_values(EX.a, EX.p, include_witnesses=True)
    assert len(witnesses) == 1
    output = reasoner.to_graph(include_witnesses=True)
    assert (next(iter(witnesses)), EX.q, EX.b) in output


def test_annotations_on_axioms_and_annotation_property_range_are_metadata():
    program = compile_ttl("""
      :note a owl:AnnotationProperty; rdfs:range xsd:string.
      :A rdfs:subClassOf :B.
      [] a owl:Axiom; owl:annotatedSource :A; owl:annotatedProperty rdfs:subClassOf;
           owl:annotatedTarget :B; :note "explanation".
    """, "L0")
    assert len(program.rules) == 1
    assert not program.facts


def test_literal_enumerations_are_rejected_as_datatype_constraints():
    with pytest.raises(ProfileError, match="datatype restriction"):
        compile_ttl("[owl:oneOf (1 2)] rdfs:subClassOf :A.")


def test_duplicate_nominals_simplify_to_a_singleton():
    program = compile_ttl(":A rdfs:subClassOf [owl:oneOf (:a :a)].", "L1")
    assert len(program.rules) == 1
    assert program.rules[0].head.predicate == EQ


def test_excessive_cardinality_fails_before_allocating_witnesses():
    with pytest.raises(ProfileError, match="compilation budget"):
        compile_ttl(":A rdfs:subClassOf [owl:onProperty :p; owl:minCardinality 1000000000].", "L3")
