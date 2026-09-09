"""The thesis syntax examples preserve the existing source-grounded RDF fixtures."""
from pathlib import Path

import pytest
from rdflib import BNode, Graph, Namespace, OWL, RDF, RDFS
from rdflib.compare import isomorphic

from dlp_reasoner import ProfileError, Reasoner
from dlp_reasoner.parser import parse_dlp

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
BACH = Namespace("http://www.jsbach.org/bach#")


def logical_graph(graph):
    """Ignore only optional vocabulary/individual declaration triples.

    Concrete Class/ObjectProperty directives declare their names; the small
    Turtle fixtures omit some declarations. Constructors and all annotations,
    property characteristics, axioms, assertions and RDF list order remain.
    """
    declarations = {OWL.Class, OWL.ObjectProperty, OWL.NamedIndividual}
    result = Graph()
    for subject, predicate, obj in graph:
        if predicate != RDF.type or obj not in declarations:
            result.add((subject, predicate, obj))
    return result


@pytest.mark.parametrize("name", ["family", "existential", "inconsistent", "bach", "bach-family"])
def test_dlp_examples_preserve_rdf_axioms_annotations_and_identifiers(name):
    path = EXAMPLES / f"{name}.dlp"
    dlp = parse_dlp(path.read_text(encoding="utf-8"), source=str(path))
    rdf = Graph().parse(EXAMPLES / f"{name}.ttl", format="turtle")
    assert isomorphic(logical_graph(dlp), logical_graph(rdf))


@pytest.mark.parametrize("name,profile", [
    ("family", "L2"), ("existential", "L3"), ("bach", "L3"), ("bach-family", "L0"),
])
def test_dlp_and_rdf_examples_have_isomorphic_materializations_including_witnesses(name, profile):
    dlp = Reasoner.from_file(EXAMPLES / f"{name}.dlp", profile=profile)
    rdf = Reasoner.from_file(EXAMPLES / f"{name}.ttl", profile=profile)
    assert dlp.complete and rdf.complete
    assert dlp.consistency == rdf.consistency == "consistent"
    # Existential names may differ between serializations. Blank-node
    # isomorphism checks their relationships and multiplicity without treating
    # implementation-specific witness identifiers as named individuals.
    assert isomorphic(
        dlp.to_graph(include_schema=False, include_witnesses=True),
        rdf.to_graph(include_schema=False, include_witnesses=True),
    )


def test_dlp_examples_keep_the_inconsistency_and_l3_profile_boundaries():
    assert Reasoner.from_file(EXAMPLES / "inconsistent.dlp").consistency == "inconsistent"
    for name in ("existential", "bach"):
        with pytest.raises(ProfileError):
            Reasoner.from_file(EXAMPLES / f"{name}.dlp", profile="L2")


def test_bach_dlp_keeps_the_unnamed_child_and_named_answers_from_table_2_5():
    reasoner = Reasoner.from_file(EXAMPLES / "bach.dlp", profile="L3")
    ambrosius = BACH["johann-ambrosius"]
    sebastian = BACH["johann-sebastian"]
    assert reasoner.instances(BACH.Father) == {ambrosius, sebastian}
    assert reasoner.instances(BACH.Masterpiece) == {BACH.BWV248}
    assert reasoner.property_values(ambrosius, BACH.hasChild) == set()
    children = reasoner.property_values(ambrosius, BACH.hasChild, include_witnesses=True)
    assert children and all(isinstance(child, BNode) for child in children)
    assert not reasoner.entails(ambrosius, BACH.hasChild, sebastian)
    assert reasoner.instances(BACH.Wife) == reasoner.instances(BACH.Husband) == set()


def test_bach_family_dlp_keeps_the_independent_chapter_6_maintenance_example():
    family = Reasoner.from_file(EXAMPLES / "bach-family.dlp", profile="L0")
    js, wf, jc = (BACH[name] for name in
                  ("johann-sebastian", "wilhelm-friedemann", "johann-christian"))
    assert len(set(family.graph.subject_objects(BACH.ancestorOf))) == 9
    assert not list(family.graph.triples((None, BACH.hasChild, None)))
    assert not family.property_values(js, BACH.ancestorOf) & {jc}
    assert len(family.property_pairs(BACH.ancestorOf)) == 24
    assert not family.is_symmetric(BACH.inDynasty)

    before = family.property_pairs(BACH.ancestorOf)
    family.update(remove=[(js, BACH.ancestorOf, wf)], add=[(js, BACH.ancestorOf, jc)])
    after = family.property_pairs(BACH.ancestorOf)
    assert len(before - after) == 3
    assert len(after - before) == 4
    assert family.entails(BACH.johannes, BACH.ancestorOf, wf)
    assert family.property_pairs(BACH.inDynasty) == after

    family.update(remove=[(BACH.ancestorOf, RDFS.subPropertyOf, BACH.inDynasty)])
    assert family.property_pairs(BACH.inDynasty) == set()
    assert family.property_pairs(BACH.ancestorOf) == after
