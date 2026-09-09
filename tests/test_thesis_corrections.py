"""Semantic regressions from the independently checked thesis errata."""
import pytest
from rdflib import Graph, Namespace, OWL, RDF, RDFS

from dlp_reasoner import IncompleteReasoningError, Reasoner
from dlp_reasoner.compiler import compile_graph

EX = Namespace("https://example.org/corrections#")
PREFIX = """@prefix : <https://example.org/corrections#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
"""


def graph(text):
    return Graph().parse(data=PREFIX + text, format="turtle")


def make(text, **options):
    return Reasoner(graph(text), **options)


def snapshot(reasoner):
    return set(reasoner.graph), set(reasoner.engine.facts), reasoner.stats


def test_table_5_3_inclusion_and_transitivity_have_the_correct_direction():
    r = make(""":p rdfs:subPropertyOf :q; a owl:TransitiveProperty.
      :a :p :b. :b :p :c. :x :q :y.""", profile="L0")
    assert r.entails(EX.a, EX.p, EX.c)
    assert r.entails(EX.a, EX.q, EX.c)
    assert not r.entails(EX.x, EX.p, EX.y)
    assert not r.entails(EX.a, EX.p, EX.a)
    assert not r.entails(EX.b, EX.p, EX.a)


def test_table_7_1_conjunction_requires_both_classes():
    r = make("""[owl:intersectionOf (:C :D)] rdfs:subClassOf :E.
      :left a :C. :right a :D. :both a :C, :D.""", profile="L0")
    assert r.instances(EX.E) == {EX.both}


def test_example_5_2_1_atomic_head_is_independent_of_universal_successors():
    r = make("""
      [owl:intersectionOf (:A [owl:onProperty :r; owl:someValuesFrom :C])]
        rdfs:subClassOf [owl:intersectionOf (:B
          [owl:onProperty :p; owl:allValuesFrom :D])].
      :withoutP a :A; :r :c. :withP a :A; :r :c; :p :d. :c a :C.
    """, profile="L0")
    assert r.instances(EX.B) == {EX.withoutP, EX.withP}
    assert r.instances(EX.D) == {EX.d}
    assert not r.entails(EX.c, RDF.type, EX.D)


def test_query_restriction_scope_distinguishes_subject_and_filler():
    r = make("""
      :SubjectMatch owl:equivalentClass [owl:intersectionOf (
        [owl:onProperty :r; owl:someValuesFrom :A] :B)].
      :FillerMatch owl:equivalentClass [owl:onProperty :r;
        owl:someValuesFrom [owl:intersectionOf (:A :B)]].
      :subject a :B; :r :filler. :filler a :A.
      :other :r :both. :both a :A, :B.
    """, profile="L3")
    assert r.instances(EX.SubjectMatch) == {EX.subject}
    assert r.instances(EX.FillerMatch) == {EX.other}


def test_nominals_do_not_contaminate_independent_equivalence_probes():
    r = make(":C rdfs:subClassOf [owl:oneOf (:o)]. "
             ":D rdfs:subClassOf [owl:oneOf (:o)].", profile="L1")
    original = snapshot(r)
    assert not r.equivalent_classes(EX.C, EX.D)
    assert not r.subsumes(EX.C, EX.D)
    assert not r.subsumes(EX.D, EX.C)
    assert snapshot(r) == original
    # The thesis's combined trial makes the unrelated test names equal.
    joint = Reasoner(r.graph + graph(":a a :C. :b a :D."), profile="L1")
    assert joint.entails(EX.a, OWL.sameAs, EX.b)
    assert joint.entails(EX.a, RDF.type, EX.D)
    assert joint.entails(EX.b, RDF.type, EX.C)


def test_equivalence_handles_declared_equivalence_and_empty_classes():
    r = make(":C owl:equivalentClass :D. "
             ":Empty rdfs:subClassOf owl:Nothing. "
             ":AlsoEmpty rdfs:subClassOf owl:Nothing.")
    assert r.equivalent_classes(EX.C, EX.D)
    assert r.equivalent_classes(EX.Empty, EX.AlsoEmpty)
    assert not r.equivalent_classes(EX.C, EX.Empty)


def test_domain_and_range_probes_follow_superclasses_not_subclasses():
    r = make(""":p rdfs:domain :Person; rdfs:range :Place.
      :Student rdfs:subClassOf :Person. :Person rdfs:subClassOf :Agent.
      :Town rdfs:subClassOf :Place. :Place rdfs:subClassOf :Region.
      :a :p :b.""", profile="L0")
    original = snapshot(r)
    assert r.has_domain(EX.p, EX.Person)
    assert r.has_domain(EX.p, EX.Agent)
    assert not r.has_domain(EX.p, EX.Student)
    assert r.has_range(EX.p, EX.Place)
    assert r.has_range(EX.p, EX.Region)
    assert not r.has_range(EX.p, EX.Town)
    assert r.entails(EX.a, RDF.type, EX.Agent)
    assert not r.entails(EX.a, RDF.type, EX.Student)
    assert snapshot(r) == original


def test_inverse_and_transitivity_do_not_inherit_to_strict_subproperties():
    r = make(""":p rdfs:subPropertyOf :q.
      :q owl:inverseOf :r; a owl:TransitiveProperty.
      :alias owl:equivalentProperty :q.
      :a :p :b. :b :p :c.""", profile="L0")
    original = snapshot(r)
    assert r.property_subsumes(EX.q, EX.p)
    assert not r.property_subsumes(EX.p, EX.q)
    assert r.equivalent_properties(EX.q, EX.alias)
    assert not r.equivalent_properties(EX.p, EX.q)
    assert r.inverse_properties(EX.q, EX.r)
    assert r.inverse_properties(EX.alias, EX.r)
    assert not r.inverse_properties(EX.p, EX.r)
    assert r.is_transitive(EX.q)
    assert r.is_transitive(EX.r)
    assert not r.is_transitive(EX.p)
    assert not r.entails(EX.a, EX.p, EX.c)
    assert snapshot(r) == original


def test_bach_example_symmetry_does_not_connect_separate_branches():
    r = make(""":ancestor a owl:TransitiveProperty; rdfs:subPropertyOf :dynasty.
      :dynasty a owl:SymmetricProperty.
      :j :ancestor :h, :c. :h :ancestor :jc1.""", profile="L0")
    assert r.is_symmetric(EX.dynasty)
    assert not r.is_transitive(EX.dynasty)
    assert r.entails(EX.jc1, EX.dynasty, EX.j)
    assert not r.entails(EX.jc1, EX.dynasty, EX.c)


def test_property_queries_use_semantics_not_accidental_finite_abox_shape():
    r = make(""":a :p :b. :b :p :a. :a :p :a. :b :p :b.
      :declared a owl:SymmetricProperty, owl:TransitiveProperty.""", profile="L0")
    assert not r.is_symmetric(EX.p)
    assert not r.is_transitive(EX.p)
    assert not r.is_symmetric(EX.absent)
    assert not r.is_transitive(EX.absent)
    assert r.is_symmetric(EX.declared)
    assert r.is_transitive(EX.declared)


def test_empty_property_implications_are_vacuously_true():
    r = make(":empty rdfs:domain owl:Nothing. :otherEmpty rdfs:range owl:Nothing.")
    original = snapshot(r)
    assert r.is_symmetric(EX.empty)
    assert r.is_transitive(EX.empty)
    assert r.property_subsumes(EX.unknown, EX.empty)
    assert not r.property_subsumes(EX.empty, EX.unknown)
    assert r.inverse_properties(EX.empty, EX.otherEmpty)
    assert r.has_domain(EX.empty, EX.AnyClass)
    assert r.has_range(EX.empty, EX.AnyClass)
    assert snapshot(r) == original


def test_incomplete_fresh_probe_raises_and_leaves_original_untouched():
    r = make("", profile="L0", max_facts=1)
    original = snapshot(r)
    with pytest.raises(IncompleteReasoningError):
        r.is_transitive(EX.p)
    assert snapshot(r) == original


@pytest.mark.parametrize("constructor", ["unionOf", "oneOf"])
def test_conjunction_of_disjunctions_has_linear_compiled_size(constructor):
    programs = []
    for count in (10, 20):
        pairs = " ".join(f"[owl:{constructor} (:common :Other{i})]"
                         for i in range(count))
        data = f"[owl:intersectionOf ({pairs})] rdfs:subClassOf :Match."
        if constructor == "unionOf":
            data += " :item a :common. :nonmatch a :Other0."
        r = make(data, profile="L1")
        assert len(r.program.rules) <= 2 * count + 2
        assert r.instances(EX.Match) == {EX.item if constructor == "unionOf" else EX.common}
        programs.append(r.program)
    assert len(programs[1].rules) < 2 * len(programs[0].rules)


def test_unchanged_rules_survive_unrelated_axiom_insertion():
    original = graph(":C rdfs:subClassOf :D. :p a owl:TransitiveProperty.")
    before = compile_graph(original, "L0")
    original.add((EX.A, RDFS.subClassOf, EX.B))
    after = compile_graph(original, "L0")
    assert set(before.rules) < set(after.rules)


def test_nested_existentials_and_nominals_keep_independent_fillers_and_equality():
    r = make("""
      [owl:intersectionOf (
        [owl:onProperty :p; owl:someValuesFrom [owl:intersectionOf (
          :Marker [owl:oneOf (:a :b)])]]
        [owl:onProperty :q; owl:someValuesFrom [owl:oneOf (:c :d)]])]
        rdfs:subClassOf :Match.
      :aliasA owl:sameAs :a; a :Marker. :b a :Marker.
      :aliasC owl:sameAs :c.
      :s :p :aliasA; :q :aliasC. :t :p :b; :q :d.
      :wrongFiller :p :a; :q :a. :missingP :q :c.
    """, profile="L1")
    assert r.instances(EX.Match) == {EX.s, EX.t}


def test_shared_rule_from_surviving_axiom_keeps_its_consequences():
    r = make(":C rdfs:subClassOf :P; owl:equivalentClass :P. :a a :C.", profile="L0")
    r.update(remove=[(EX.C, RDFS.subClassOf, EX.P)])
    assert r.instances(EX.P) == {EX.a}
    assert r.stats["update_method"] == "dred-rules"
    assert r.engine.facts == Reasoner(r.graph, profile="L0").engine.facts


def test_rdf_rule_and_fact_deltas_preserve_only_current_support():
    r = make(":A rdfs:subClassOf :P. :B rdfs:subClassOf :P. :a a :A.", profile="L0")
    r.update(remove=[(EX.A, RDFS.subClassOf, EX.P)], add=[(EX.b, RDF.type, EX.B)])
    assert r.instances(EX.P) == {EX.b}
    assert r.stats["update_method"] == "dred-rules"
    assert r.engine.facts == Reasoner(r.graph, profile="L0").engine.facts
