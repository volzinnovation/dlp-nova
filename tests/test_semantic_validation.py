"""Independent semantic checks, deliberately separate from engine unit tests.

OWL RL comparisons cover only named ground assertions in the shared fragment.
The finite-model oracle interprets monadic axioms directly and never compiles
rules or calls a closure algorithm.
"""
from itertools import product
import random

import pytest
from owlrl import DeductiveClosure, OWLRL_Semantics
from rdflib import BNode, Graph, Namespace, OWL, RDF, RDFS
from rdflib.collection import Collection

from dlp_reasoner import InconsistentOntologyError, ProfileError, Reasoner

EX = Namespace("urn:semantic-validation:")
PREFIX = """@prefix : <urn:semantic-validation:> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
"""
INDIVIDUALS = (EX.a, EX.b, EX.c, EX.d)
CLASSES = (EX.A, EX.B, EX.C, EX.D, EX.E)
PROPERTIES = (EX.p, EX.q, EX.r, EX.s)


def graph_from(text):
    graph = Graph().parse(data=PREFIX + text, format="turtle")
    for individual in INDIVIDUALS:
        graph.add((individual, RDF.type, OWL.NamedIndividual))
    return graph


def named_candidates(individuals=INDIVIDUALS, classes=CLASSES, properties=PROPERTIES):
    return (
        [(a, RDF.type, c) for a, c in product(individuals, classes)]
        + [(a, p, b) for a, p, b in product(individuals, properties, individuals)]
        + [(a, OWL.sameAs, b) for a, b in product(individuals, repeat=2)]
    )


def assert_owlrl_agreement(graph):
    expected = Graph()
    expected += graph
    DeductiveClosure(OWLRL_Semantics, axiomatic_triples=False,
                     datatype_axioms=False).expand(expected)
    actual = Reasoner(graph, profile="L2")
    assert actual.complete and actual.consistency == "consistent"
    for triple in named_candidates():
        assert actual.entails(*triple) == (triple in expected), triple


@pytest.mark.parametrize("ontology", [
    """:A rdfs:subClassOf :B . :B rdfs:subClassOf :C .
       :a a :A . :b a :D . :D owl:equivalentClass :E .""",
    """:p rdfs:subPropertyOf :q . :q a owl:TransitiveProperty .
       :q owl:inverseOf :r . :r rdfs:subPropertyOf :s .
       :q rdfs:domain :A ; rdfs:range :B . :a :p :b . :b :q :c .""",
    """:C owl:equivalentClass [ owl:intersectionOf (:A :B) ] .
       [ owl:unionOf (:C :D) ] rdfs:subClassOf :E .
       :a a :A, :B . :b a :A . :c a :D . :d a :C .""",
    """:A rdfs:subClassOf [ owl:onProperty :p; owl:allValuesFrom :B ] .
       [ owl:onProperty :p; owl:someValuesFrom :B ] rdfs:subClassOf :C .
       :a a :A ; :p :b . :c :p :d . :d a :B .""",
    """:A rdfs:subClassOf [ owl:onProperty :p; owl:hasValue :b ] .
       [ owl:onProperty :p; owl:hasValue :b ] rdfs:subClassOf :C .
       [ owl:oneOf (:a :d) ] rdfs:subClassOf :D .
       :a a :A . :c :p :b . :d owl:sameAs :b .""",
    """:p a owl:FunctionalProperty . :a :p :b, :c . :b a :A .
       :q a owl:InverseFunctionalProperty . :c :q :d . :b :q :a .
       :B rdfs:subClassOf [ owl:onProperty :r; owl:maxCardinality 1 ] .
       :d a :B ; :r :a, :c . :s owl:equivalentProperty :q .""",
    """:a owl:sameAs :c . :a a :A .
       :a :p :b . :c :q :d . :b owl:sameAs :d .
       :p owl:inverseOf :r . :B rdfs:subClassOf :C . :a a :B .""",
], ids=["taxonomy", "properties", "booleans", "restriction-scopes",
        "values-and-nominals", "derived-equality", "explicit-equality-and-aliases"])
def test_shared_fragment_against_owlrl(ontology):
    assert_owlrl_agreement(graph_from(ontology))


@pytest.mark.parametrize("seed", range(8))
def test_seeded_shared_fragment_against_owlrl(seed):
    rng = random.Random(seed)
    graph = graph_from(""" :A rdfs:subClassOf :B . :B rdfs:subClassOf :C .
        :p rdfs:subPropertyOf :q . :q owl:inverseOf :r .
        :p a owl:TransitiveProperty . :s a owl:SymmetricProperty .
        :q rdfs:domain :D; rdfs:range :E . """)
    for _ in range(9):
        graph.add((rng.choice(INDIVIDUALS), rng.choice(PROPERTIES), rng.choice(INDIVIDUALS)))
    for _ in range(4):
        graph.add((rng.choice(INDIVIDUALS), RDF.type, rng.choice(CLASSES)))
    if seed % 2:
        graph.add((EX.a, OWL.sameAs, EX.b))
    assert_owlrl_agreement(graph)


def monadic_models(class_count, individual_count, implications, denials, assertions):
    """Enumerate interpretations of unary predicates over a fixed nonempty domain.

    No equality, nominals, existentials or roles occur in this fragment. Thus one
    element per named individual suffices: every model's unary truth assignments
    to the names can be restricted to those elements, and this enumeration also
    permits identical unary assignments for different names.
    """
    full = (1 << individual_count) - 1
    models = []
    for interpretation in product(range(full + 1), repeat=class_count):
        if any(not interpretation[c] & (1 << a) for a, c in assertions):
            continue
        valid = True
        for antecedent, consequent in implications:
            members = full
            for c in antecedent:
                members &= interpretation[c]
            if members & ~interpretation[consequent]:
                valid = False
                break
        if not valid:
            continue
        for disjoint in denials:
            members = full
            for c in disjoint:
                members &= interpretation[c]
            if members:
                valid = False
                break
        if valid:
            models.append(interpretation)
    return models


def add_intersection(graph, classes):
    if len(classes) == 1:
        return classes[0]
    expr, head = BNode(), BNode()
    Collection(graph, head, list(classes))
    graph.add((expr, OWL.intersectionOf, head))
    return expr


@pytest.mark.parametrize("seed", range(32))
def test_exhaustive_monadic_model_oracle(seed):
    rng = random.Random(seed)
    classes, individuals = CLASSES[:3], INDIVIDUALS[:2]
    implications = [((rng.randrange(3),), rng.randrange(3)) for _ in range(2)]
    implications += [(tuple(rng.sample(range(3), 2)), rng.randrange(3)) for _ in range(2)]
    denials = [tuple(rng.sample(range(3), 2)) for _ in range(seed % 3)]
    assertions = {(rng.randrange(2), rng.randrange(3)) for _ in range(seed % 4)}
    graph = Graph()
    for a in individuals:
        graph.add((a, RDF.type, OWL.NamedIndividual))
    for antecedent, consequent in implications:
        left = add_intersection(graph, [classes[c] for c in antecedent])
        graph.add((left, RDFS.subClassOf, classes[consequent]))
    for c, d in denials:
        graph.add((classes[c], OWL.disjointWith, classes[d]))
    for a, c in assertions:
        graph.add((individuals[a], RDF.type, classes[c]))
    models = monadic_models(3, 2, implications, denials, assertions)
    reasoner = Reasoner(graph, profile="L2")
    assert reasoner.complete
    assert reasoner.consistency == ("consistent" if models else "inconsistent")
    if not models:
        with pytest.raises(InconsistentOntologyError):
            reasoner.entails(individuals[0], RDF.type, classes[0])
        return
    for a, c in product(range(2), range(3)):
        expected = all(model[c] & (1 << a) for model in models)
        assert reasoner.entails(individuals[a], RDF.type, classes[c]) == expected


def direct_property_oracle(graph):
    """Direct relation algebra for the specific property schema used below."""
    nodes = tuple(EX[f"i{i}"] for i in range(6))
    relevant = {EX.base, EX.p, EX.inverse, EX.symmetric}
    facts = {(s, p, o) for s, p, o in graph if p in relevant}
    transitive = (EX.p, RDF.type, OWL.TransitiveProperty) in graph
    while True:
        result = set(facts)
        result.update((s, EX.p, o) for s, p, o in facts if p == EX.base)
        result.update((o, EX.inverse, s) for s, p, o in facts if p == EX.p)
        result.update((o, EX.p, s) for s, p, o in facts if p == EX.inverse)
        result.update((o, EX.symmetric, s) for s, p, o in facts if p == EX.symmetric)
        if transitive:
            edges = {(s, o) for s, p, o in facts if p == EX.p}
            result.update((s, EX.p, o) for s, m in edges for n, o in edges if m == n)
        if result == facts:
            return nodes, relevant, facts
        facts = result


def assert_property_oracle(reasoner, graph):
    nodes, properties, expected = direct_property_oracle(graph)
    assert reasoner.complete and reasoner.consistency == "consistent"
    for triple in product(nodes, properties, nodes):
        assert reasoner.entails(*triple) == (triple in expected), triple
    fresh = Reasoner(graph, profile="L0")
    assert reasoner.engine.facts == fresh.engine.facts


@pytest.mark.parametrize("seed", range(6))
def test_seeded_property_updates_against_relation_oracle_and_rebuild(seed):
    rng = random.Random(seed)
    graph = Graph()
    graph.add((EX.base, RDFS.subPropertyOf, EX.p))
    graph.add((EX.p, RDF.type, OWL.TransitiveProperty))
    graph.add((EX.p, OWL.inverseOf, EX.inverse))
    graph.add((EX.symmetric, RDF.type, OWL.SymmetricProperty))
    nodes = tuple(EX[f"i{i}"] for i in range(6))
    for a in nodes:
        graph.add((a, RDF.type, OWL.NamedIndividual))
    possible = list(product(nodes, (EX.base, EX.p, EX.symmetric), nodes))
    for triple in rng.sample(possible, 9):
        graph.add(triple)
    reasoner = Reasoner(graph, profile="L0")
    assert_property_oracle(reasoner, graph)
    for step in range(12):
        triple = ((EX.p, RDF.type, OWL.TransitiveProperty) if step in (3, 7)
                  else rng.choice(possible))
        if triple in graph:
            graph.remove(triple)
            reasoner.update(remove=[triple])
        else:
            graph.add(triple)
            reasoner.update(add=[triple])
        assert_property_oracle(reasoner, graph)


def test_universal_and_existential_variables_are_independent():
    reasoner = Reasoner(graph_from("""
       [ owl:intersectionOf (:A [owl:onProperty :p; owl:someValuesFrom :B]) ]
           rdfs:subClassOf [ owl:intersectionOf (:C [owl:onProperty :q; owl:allValuesFrom :D]) ] .
       :a a :A; :p :b; :q :c . :b a :B . :d a :A; :q :b .
    """))
    assert reasoner.entails(EX.a, RDF.type, EX.C)
    assert reasoner.entails(EX.c, RDF.type, EX.D)
    assert not reasoner.entails(EX.b, RDF.type, EX.D)
    assert not reasoner.entails(EX.d, RDF.type, EX.C)


def test_dred_does_not_preserve_an_unsupported_cycle():
    reasoner = Reasoner(graph_from("""
       :A rdfs:subClassOf :B . :B rdfs:subClassOf :A, :C . :a a :A .
    """))
    reasoner.update(remove=[(EX.a, RDF.type, EX.A)])
    for concept in (EX.A, EX.B, EX.C):
        assert not reasoner.entails(EX.a, RDF.type, concept)


def test_dred_preserves_independent_support_then_removes_last_support():
    reasoner = Reasoner(graph_from("""
       :A rdfs:subClassOf :C . :B rdfs:subClassOf :C . :C rdfs:subClassOf :D .
       :a a :A, :B, :C .
    """))
    for concept in (EX.A, EX.C):
        reasoner.update(remove=[(EX.a, RDF.type, concept)])
        assert reasoner.entails(EX.a, RDF.type, EX.C)
        assert reasoner.entails(EX.a, RDF.type, EX.D)
    reasoner.update(remove=[(EX.a, RDF.type, EX.B)])
    assert not reasoner.entails(EX.a, RDF.type, EX.C)
    assert not reasoner.entails(EX.a, RDF.type, EX.D)


def test_nonempty_domain_makes_top_bottom_inconsistent():
    graph = Graph()
    graph.add((OWL.Thing, RDFS.subClassOf, OWL.Nothing))
    assert Reasoner(graph).consistency == "inconsistent"


def test_constraints_fire_after_equality_substitution():
    reasoner = Reasoner(graph_from("""
       :A rdfs:subClassOf :B . :B owl:disjointWith :C .
       :a a :A . :b a :C . :p a owl:FunctionalProperty . :c :p :a, :b .
    """))
    assert reasoner.consistency == "inconsistent"


def test_equality_retraction_splits_derived_property_aliases():
    reasoner = Reasoner(graph_from("""
       :p a owl:FunctionalProperty . :a :p :b, :c . :b :q :d . :c a :A .
    """))
    assert reasoner.entails(EX.c, EX.q, EX.d)
    reasoner.update(remove=[(EX.p, RDF.type, OWL.FunctionalProperty)])
    assert not reasoner.entails(EX.c, EX.q, EX.d)
    assert not reasoner.entails(EX.b, RDF.type, EX.A)
    assert reasoner.entails(EX.b, EX.q, EX.d)


def test_probe_queries_leave_live_state_unchanged():
    reasoner = Reasoner(graph_from("""
       :A rdfs:subClassOf :B . :B owl:disjointWith :C . :a a :A .
    """))
    facts, triples, stats = set(reasoner.engine.facts), set(reasoner.graph), dict(reasoner.stats)
    assert reasoner.subsumes(EX.B, EX.A)
    assert not reasoner.subsumes(EX.C, EX.A)
    assert reasoner.is_satisfiable(EX.C)
    assert reasoner.engine.facts == facts
    assert set(reasoner.graph) == triples
    assert reasoner.stats == stats


@pytest.mark.parametrize("definition", [
    ":A rdfs:subClassOf [owl:complementOf [owl:complementOf :B]] .",
    ":A rdfs:subClassOf [owl:intersectionOf (:B owl:Thing)] .",
])
def test_normalization_before_profile_validation(definition):
    reasoner = Reasoner(graph_from(definition + " :a a :A ."), profile="L0")
    assert reasoner.entails(EX.a, RDF.type, EX.B)


def test_hasvalue_normalization_is_available_in_l0():
    reasoner = Reasoner(graph_from("""
       :A rdfs:subClassOf [owl:onProperty :p; owl:someValuesFrom [owl:oneOf (:b)]] .
       :a a :A .
    """), profile="L0")
    assert reasoner.entails(EX.a, EX.p, EX.b)


def test_general_union_consequent_is_rejected():
    with pytest.raises(ProfileError):
        Reasoner(graph_from(":A rdfs:subClassOf [owl:unionOf (:B :C)] ."), profile="L3")


def test_singleton_consequent_equality_beyond_owlrl_oracle():
    # The OWL RL reference does not implement equality from a nominal consequent.
    # Direct FOL: A(a), A subset {c} implies a=c and all alias substitutions.
    reasoner = Reasoner(graph_from("""
       :A rdfs:subClassOf [ owl:oneOf (:c) ] . :a a :A .
       :a :p :b . :c :q :d . :b owl:sameAs :d .
    """))
    assert reasoner.entails(EX.a, OWL.sameAs, EX.c)
    assert reasoner.entails(EX.c, RDF.type, EX.A)
    assert reasoner.entails(EX.c, EX.p, EX.d)
    assert reasoner.entails(EX.a, EX.q, EX.b)


def test_fresh_query_individual_receives_top_consequences():
    graph = Graph()
    graph.add((OWL.Thing, RDFS.subClassOf, EX.A))
    graph.add((EX.A, RDFS.subClassOf, EX.B))
    reasoner = Reasoner(graph)
    before = set(reasoner.graph), set(reasoner.engine.facts)
    assert reasoner.entails(EX.fresh, RDF.type, EX.A)
    assert reasoner.entails(EX.fresh, RDF.type, EX.B)
    assert {OWL.Thing, EX.A, EX.B} <= reasoner.types(EX.fresh)
    assert (set(reasoner.graph), set(reasoner.engine.facts)) == before


def test_fresh_query_individual_obeys_universal_singleton_domain():
    graph = Graph().parse(data=PREFIX + """
        owl:Thing rdfs:subClassOf [ owl:oneOf (:a) ] .
    """, format="turtle")
    reasoner = Reasoner(graph)
    # The ontology forces every domain element to denote the same individual.
    assert reasoner.entails(EX.fresh, OWL.sameAs, EX.a)


def test_returned_existential_witness_can_be_queried():
    reasoner = Reasoner(graph_from("""
       :a a :A . :A rdfs:subClassOf [ owl:onProperty :p; owl:someValuesFrom :B ] .
       :B rdfs:subClassOf [ owl:onProperty :q; owl:hasValue :c ] .
    """), profile="L3")
    witness, = reasoner.property_values(EX.a, EX.p, include_witnesses=True)
    assert isinstance(witness, BNode)
    assert reasoner.entails(EX.a, EX.p, witness)
    assert reasoner.entails(witness, RDF.type, EX.B)
    assert EX.B in reasoner.types(witness)
    assert reasoner.property_values(witness, EX.q) == {EX.c}


def test_cli_invalid_turtle_reports_structured_error(tmp_path, capsys):
    import json
    from dlp_reasoner.cli import main

    path = tmp_path / "invalid.ttl"
    path.write_text("this is invalid turtle", encoding="utf-8")
    assert main(["validate", str(path)]) == 1
    response = json.loads(capsys.readouterr().err)
    assert response["error"]


def test_fresh_query_domain_limit_reports_incomplete_without_recursing():
    from dlp_reasoner import IncompleteReasoningError

    reasoner = Reasoner(max_facts=1)
    with pytest.raises(IncompleteReasoningError):
        reasoner.entails(EX.fresh_a, OWL.sameAs, EX.fresh_b)
