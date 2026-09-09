"""Positive schema shortcuts must agree with the original independent probes."""
import random

import pytest
from rdflib import BNode, Graph, Namespace, OWL, RDF, RDFS
from rdflib.collection import Collection

from dlp_reasoner import InconsistentOntologyError, ProfileError, Reasoner

EX = Namespace("https://example.org/schema#")
PREFIX = """@prefix : <https://example.org/schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
"""


def make(text, **options):
    return Reasoner(Graph().parse(data=PREFIX + text, format="turtle"), **options)


def no_probe(*args, **kwargs):
    raise AssertionError("A structural proof should not rebuild the ABox")


def test_positive_class_context_combines_conjunctions_and_cycles_without_probe(monkeypatch):
    r = make(""":C rdfs:subClassOf :A, :B.
      [owl:intersectionOf (:A :B)] rdfs:subClassOf :D.
      :D rdfs:subClassOf :E. :E rdfs:subClassOf :D.""", profile="L0")
    assert r._schema_cache is None
    assert r._subsumption_probe(EX.E, EX.C)
    monkeypatch.setattr(r, "_subsumption_probe", no_probe)
    assert r.subsumes(EX.E, EX.C)
    assert r.equivalent_classes(EX.D, EX.E)
    assert r._schema_cache is not None


def test_structural_hit_does_not_copy_even_a_large_abox(monkeypatch):
    import dlp_reasoner.reasoner as module

    r = make(":A rdfs:subClassOf :B.", profile="L0")
    r.update(add=[(EX[f"individual{i}"], RDF.type, EX.A) for i in range(1000)])
    original = set(r.engine.facts), r.stats
    monkeypatch.setattr(module, "copy_graph", no_probe)
    assert r.subsumes(EX.B, EX.A)
    assert r.subsumes(EX.B, EX.A)
    assert (set(r.engine.facts), r.stats) == original


def test_missing_structural_proof_runs_general_probe_for_negative_and_nominal_positive(monkeypatch):
    r = make(":C rdfs:subClassOf [owl:oneOf (:o)]. :o a :D. :A rdfs:subClassOf :B.")
    calls = []
    original = r._subsumption_probe

    def probe(superclass, subclass):
        calls.append((superclass, subclass))
        return original(superclass, subclass)

    monkeypatch.setattr(r, "_subsumption_probe", probe)
    assert r.subsumes(EX.D, EX.C)  # Requires nominal equality and an ABox assertion.
    assert not r.subsumes(EX.C, EX.D)
    assert calls == [(EX.D, EX.C), (EX.C, EX.D)]


def test_anonymous_and_unknown_queries_keep_their_original_semantics(monkeypatch):
    r = make(""":C rdfs:subClassOf :A, :B.
      :A rdfs:subClassOf :D.
      _:expression owl:intersectionOf (:A :B).""")
    expression = next(r.graph.subjects(OWL.intersectionOf, None))
    calls = []
    original = r._subsumption_probe

    def probe(superclass, subclass):
        calls.append((superclass, subclass))
        return original(superclass, subclass)

    monkeypatch.setattr(r, "_subsumption_probe", probe)
    assert r.subsumes(expression, EX.C)
    assert r.subsumes(EX.D, expression)
    assert not r.subsumes(EX.Unknown, EX.C)
    assert len(calls) == 3
    empty = make("", profile="L0")
    with pytest.raises(ProfileError):
        empty.subsumes(OWL.Thing, OWL.Thing)


def test_unsatisfiable_classes_and_empty_properties_still_use_semantic_probes():
    r = make(":Empty rdfs:subClassOf owl:Nothing. :empty rdfs:domain owl:Nothing.")
    assert not r._schema().proves_subsumption(EX.Arbitrary, EX.Empty)
    assert r.subsumes(EX.Arbitrary, EX.Empty)
    assert not r._schema().proves_transitivity(EX.empty)
    assert r.is_transitive(EX.empty)
    assert r.has_range(EX.empty, EX.Arbitrary)


def test_schema_update_invalidates_proofs_and_invalid_update_preserves_cache():
    r = make(":A rdfs:subClassOf :B. :B rdfs:subClassOf :C.", profile="L0")
    assert r.subsumes(EX.C, EX.A)
    original = r._schema_cache
    with pytest.raises(ProfileError):
        r.update(add=[(EX.A, OWL.hasKey, EX.B)])
    assert r._schema_cache is original
    assert r.subsumes(EX.C, EX.A)
    r.update(remove=[(EX.B, RDFS.subClassOf, EX.C)])
    assert r._schema_cache is None
    assert not r.subsumes(EX.C, EX.A)
    r.update(add=[(EX.B, RDFS.subClassOf, EX.C)])
    assert r.subsumes(EX.C, EX.A)


def test_fact_and_equality_changes_invalidate_without_contaminating_probes():
    r = make(":A rdfs:subClassOf :B. :C rdfs:subClassOf [owl:oneOf (:o)]. "
             ":o owl:sameAs :alias. :alias a :D.")
    assert r.subsumes(EX.B, EX.A)
    assert r.subsumes(EX.D, EX.C)
    r.update(remove=[(EX.o, OWL.sameAs, EX.alias)])
    assert r._schema_cache is None
    assert not r.subsumes(EX.D, EX.C)
    assert r.subsumes(EX.B, EX.A)
    r.update(add=[(EX.o, RDF.type, EX.D)])
    assert r._schema_cache is None
    assert r.subsumes(EX.D, EX.C)
    assert not r.instances(EX.C)


def test_consistency_guard_precedes_all_cached_positive_answers():
    r = make(":A rdfs:subClassOf :B. :p a owl:TransitiveProperty.")
    assert r.subsumes(EX.B, EX.A)
    assert r.is_transitive(EX.p)
    r.update(add=[(EX.x, RDF.type, OWL.Nothing)])
    with pytest.raises(InconsistentOntologyError):
        r.subsumes(EX.B, EX.A)
    with pytest.raises(InconsistentOntologyError):
        r.is_transitive(EX.p)


def test_transient_query_domain_gets_its_own_schema_cache():
    r = make(":A rdfs:subClassOf :B.")
    original = set(r.graph), set(r.engine.facts), r.stats
    trial = r._with_query_terms(EX.fresh)
    assert trial is not r
    assert trial._schema_cache is None
    assert trial.subsumes(EX.B, EX.A)
    assert trial._schema_cache is not None
    assert r._schema_cache is None
    assert trial.entails(EX.fresh, RDF.type, OWL.Thing)
    assert (set(r.graph), set(r.engine.facts), r.stats) == original


def test_top_bottom_and_fresh_class_names_retain_profile_semantics():
    r = make(":A rdfs:subClassOf :B.")
    for superclass, subclass in ((OWL.Thing, EX.A), (EX.A, OWL.Nothing),
                                  (EX.Fresh, EX.Fresh), (OWL.Nothing, EX.A),
                                  (EX.A, OWL.Thing)):
        assert r.subsumes(superclass, subclass) == r._subsumption_probe(superclass, subclass)
    r = make(":A rdfs:subClassOf :B.", profile="L0")
    for unsupported in (OWL.Thing, OWL.Nothing):
        with pytest.raises(ProfileError):
            r.subsumes(unsupported, unsupported)


@pytest.mark.parametrize("invalid", [BNode(), None, "not-an-RDF-IRI", []])
def test_invalid_property_arguments_are_not_accepted_by_shortcuts(invalid):
    r = make(":p a owl:TransitiveProperty, owl:SymmetricProperty; rdfs:domain :C.")
    for call in (lambda: r.is_transitive(invalid), lambda: r.is_symmetric(invalid),
                 lambda: r.property_subsumes(EX.p, invalid),
                 lambda: r.inverse_properties(EX.p, invalid),
                 lambda: r.has_domain(invalid, EX.C)):
        with pytest.raises(ProfileError):
            call()
    with pytest.raises(ProfileError):
        r.is_transitive(OWL.topObjectProperty)


def test_nominal_domains_do_not_turn_two_properties_into_exact_inverses():
    r = make("""
      :p rdfs:domain [owl:oneOf (:a)]; rdfs:range [owl:oneOf (:b)].
      :q rdfs:domain [owl:oneOf (:b)]; rdfs:range [owl:oneOf (:a)].
      :C rdfs:subClassOf [owl:oneOf (:a)].
      :D rdfs:subClassOf [owl:oneOf (:a)].
    """, profile="L1")
    original = set(r.graph), set(r.engine.facts)
    assert not r.inverse_properties(EX.p, EX.q)
    assert not r.equivalent_classes(EX.C, EX.D)
    assert (set(r.graph), set(r.engine.facts)) == original
    joint = Reasoner(r.graph, profile="L1")
    joint.update(add=[(EX.u, EX.p, EX.v), (EX.w, EX.q, EX.z)])
    assert joint.entails(EX.v, EX.q, EX.u)
    assert joint.entails(EX.z, EX.p, EX.w)


def test_signed_property_closure_and_domain_conjunctions_avoid_probes(monkeypatch):
    r = make(""":p rdfs:subPropertyOf :q.
      :q owl:equivalentProperty :alias; owl:inverseOf :inverse;
         rdfs:domain :A, :B; rdfs:range :Range; a owl:TransitiveProperty.
      [owl:intersectionOf (:A :B)] rdfs:subClassOf :Both.
      :Both rdfs:subClassOf :Ancestor.
      :symmetric a owl:SymmetricProperty.""", profile="L0")
    monkeypatch.setattr(r, "_property_probe", no_probe)
    assert r.property_subsumes(EX.q, EX.p)
    assert r.equivalent_properties(EX.q, EX.alias)
    assert r.inverse_properties(EX.alias, EX.inverse)
    assert r.is_transitive(EX.inverse)
    assert r.is_transitive(EX.alias)
    assert r.is_symmetric(EX.symmetric)
    assert r.has_domain(EX.p, EX.Both)
    assert r.has_domain(EX.p, EX.Ancestor)
    assert r.has_range(EX.inverse, EX.Both)
    assert r.has_domain(EX.inverse, EX.Range)


def test_transitivity_and_exact_inverse_shortcuts_require_equivalence(monkeypatch):
    r = make(":p rdfs:subPropertyOf :q. :q a owl:TransitiveProperty; owl:inverseOf :r.",
             profile="L0")
    calls = []
    original = r._property_probe

    def probe(assertions, conclusion):
        calls.append(conclusion)
        return original(assertions, conclusion)

    monkeypatch.setattr(r, "_property_probe", probe)
    assert not r.is_transitive(EX.p)
    assert not r.inverse_properties(EX.p, EX.r)
    assert not r.property_subsumes(EX.p, EX.q)
    assert len(calls) == 4
    r.update(add=[(EX.q, RDFS.subPropertyOf, EX.p)])
    assert r.is_transitive(EX.p)
    assert r.inverse_properties(EX.p, EX.r)
    assert len(calls) == 4
    r.update(remove=[(EX.q, RDFS.subPropertyOf, EX.p)])
    assert not r.is_transitive(EX.p)


def test_lhs_existential_domain_shortcut_does_not_move_filler_types_to_subject():
    r = make("""
      [owl:onProperty :p; owl:someValuesFrom :A] rdfs:subClassOf :Parent.
      :p rdfs:range :A. :A rdfs:subClassOf :B.
    """, profile="L0")
    # The generic probe combines a range axiom and the existential condition.
    assert r.has_domain(EX.p, EX.Parent)
    assert not r.has_domain(EX.p, EX.A)
    assert r.has_range(EX.p, EX.B)


@pytest.mark.parametrize("seed", range(3))
def test_all_small_class_answers_match_original_independent_probes(seed):
    rng = random.Random(seed)
    names = [EX[f"C{i}"] for i in range(6)]
    graph = Graph()
    for name in names:
        graph.add((name, RDF.type, OWL.Class))
    for _ in range(8):
        graph.add((rng.choice(names), RDFS.subClassOf, rng.choice(names)))
    for _ in range(4):
        expression, members = BNode(), BNode()
        Collection(graph, members, rng.sample(names, 2))
        graph.add((expression, OWL.intersectionOf, members))
        graph.add((expression, RDFS.subClassOf, rng.choice(names)))
    r = Reasoner(graph, profile="L0")
    for left in names:
        for right in names:
            assert r.subsumes(left, right) == r._subsumption_probe(left, right)


@pytest.mark.parametrize("seed", range(3))
def test_property_shortcuts_match_original_probes_on_small_mixed_schemas(seed):
    rng = random.Random(seed)
    props = [EX[f"p{i}"] for i in range(4)]
    graph = Graph()
    for _ in range(5):
        left, right = rng.sample(props, 2)
        graph.add((left, rng.choice([RDFS.subPropertyOf, OWL.inverseOf]), right))
    graph.add((props[0], RDF.type, OWL.TransitiveProperty))
    graph.add((props[1], RDF.type, OWL.SymmetricProperty))
    graph.add((props[2], RDFS.domain, EX.C))
    graph.add((props[3], RDFS.range, EX.D))
    r = Reasoner(graph, profile="L0")
    a, b, c = BNode(), BNode(), BNode()
    for prop in props:
        assert r.is_symmetric(prop) == r._property_probe(((a, prop, b),), (b, prop, a))
        assert r.is_transitive(prop) == r._property_probe(
            ((a, prop, b), (b, prop, c)), (a, prop, c))
        assert r.has_domain(prop, EX.C) == r._property_probe(((a, prop, b),), (a, RDF.type, EX.C))
        assert r.has_range(prop, EX.D) == r._property_probe(((a, prop, b),), (b, RDF.type, EX.D))
        for other in props:
            assert r.property_subsumes(prop, other) == r._property_probe(
                ((a, other, b),), (a, prop, b))
            expected = r._property_probe(((a, prop, b),), (b, other, a)) and r._property_probe(
                ((a, other, b),), (b, prop, a))
            assert r.inverse_properties(prop, other) == expected


def test_context_cache_is_bounded_and_does_not_require_all_pairs_closure():
    graph = Graph()
    for number in range(140):
        graph.add((EX[f"C{number}"], RDFS.subClassOf, EX[f"C{number + 1}"]))
    r = Reasoner(graph, profile="L0")
    assert r._schema_cache is None
    for number in range(140):
        assert r.subsumes(EX.C140, EX[f"C{number}"])
    assert len(r._schema_cache._class_cache) == 128
