"""Concrete Appendix A syntax preserves axioms and the compiler's boundaries."""
import pytest
from rdflib import BNode, Literal, Namespace
from rdflib.namespace import OWL, RDF, RDFS, XSD

from dlp_reasoner import Reasoner
from dlp_reasoner.compiler import compile_graph
from dlp_reasoner.model import EQ, NEQ, TOP, Atom, ProfileError
from dlp_reasoner.parser import DLPParseError, parse_dlp


EX = Namespace("https://example.org/")
PREFIX = "Namespace(ex = <https://example.org/>)\n"


def parse(body):
    return parse_dlp(PREFIX + f"Ontology({body})")


def reason(body, profile="L2"):
    return Reasoner(parse(body), profile=profile)


def test_partial_complete_and_nested_boolean_descriptions_preserve_semantics():
    result = reason("""
      Class(ex:A partial ex:B ex:C)
      Class(ex:D complete ex:B ex:C)
      SubClassOf(intersectionOf(unionOf(ex:A ex:E) ex:C) ex:F)
      Individual(ex:a type(ex:A))
      Individual(ex:e type(ex:E) type(ex:C))
    """, "L0")
    assert result.instances(EX.D) == {EX.a}
    assert result.instances(EX.F) == {EX.a, EX.e}
    assert result.subsumes(EX.B, EX.D)
    assert not result.subsumes(EX.A, EX.D)


def test_multiple_restriction_components_are_conjoined_without_overwriting():
    graph = parse("""
      Class(ex:A partial restriction(ex:p allValuesFrom(ex:B) value(ex:b)
                                       maxCardinality(1)))
      Individual(ex:a type(ex:A) value(ex:p ex:c))
    """)
    restrictions = list(graph.subjects(RDF.type, OWL.Restriction))
    assert len(restrictions) == 3
    assert all(len(list(graph.objects(node, OWL.onProperty))) == 1 for node in restrictions)
    result = Reasoner(graph, profile="L1")
    assert result.entails(EX.b, OWL.sameAs, EX.c)
    assert result.entails(EX.b, RDF.type, EX.B)
    assert result.entails(EX.c, RDF.type, EX.B)


def test_local_domain_and_range_follow_table_5_4_filler_direction():
    result = reason("""
      Class(ex:A partial localdomain(ex:p ex:D) localrange(ex:p ex:R))
      Individual(ex:member type(ex:A) value(ex:p ex:filler))
      Individual(ex:subject value(ex:p ex:member))
      Individual(ex:unrelated value(ex:p ex:other))
    """, "L0")
    assert result.instances(EX.D) == {EX.subject}
    assert result.instances(EX.R) == {EX.filler}
    assert not result.entails(EX.member, RDF.type, EX.D)
    assert not result.entails(EX.unrelated, RDF.type, EX.D)


def test_property_axioms_and_characteristics_are_all_effective():
    result = reason("""
      ObjectProperty(ex:p super(ex:q) inverseOf(ex:inverse)
        Symmetric Transitive domain(ex:A) range(ex:B))
      EquivalentProperties(ex:q ex:r ex:s)
      SubPropertyOf(ex:s ex:t)
      Individual(ex:a value(ex:p ex:b))
      Individual(ex:b value(ex:p ex:c))
    """, "L0")
    assert result.entails(EX.a, EX.p, EX.c)
    assert result.entails(EX.c, EX.p, EX.a)
    assert result.entails(EX.c, EX.inverse, EX.a)
    assert result.entails(EX.a, EX.t, EX.c)
    assert result.entails(EX.a, RDF.type, EX.A)
    assert result.entails(EX.c, RDF.type, EX.B)


def test_equality_and_inequality_keep_every_pair_including_repetitions():
    program = compile_graph(parse("""
      SameIndividual(ex:a ex:b ex:c)
      DifferentIndividuals(ex:d ex:e ex:f)
      DifferentIndividuals(ex:x ex:x)
    """))
    assert {Atom(EQ, (EX.a, EX.b)), Atom(EQ, (EX.a, EX.c))} <= program.facts
    assert {Atom(NEQ, (EX.d, EX.e)), Atom(NEQ, (EX.d, EX.f)),
            Atom(NEQ, (EX.e, EX.f)), Atom(NEQ, (EX.x, EX.x))} <= program.facts
    assert Reasoner(parse("DifferentIndividuals(ex:x ex:x)")).consistency == "inconsistent"


def test_disjoint_classes_means_all_pairs_and_repeated_class_is_empty():
    result = reason("""
      DisjointClasses(ex:A ex:B ex:C)
      Individual(ex:a type(ex:B) type(ex:C))
    """)
    assert result.consistency == "inconsistent"
    assert reason("DisjointClasses(ex:A ex:A) Individual(ex:a type(ex:A))").consistency == (
        "inconsistent")


def test_nested_and_empty_individuals_preserve_domain_and_anonymous_edges():
    graph = parse("""
      Individual(ex:a value(ex:p Individual(type(ex:A) value(ex:q ex:b))))
      Individual(ex:bare)
      Individual()
    """)
    anonymous = graph.value(EX.a, EX.p)
    assert isinstance(anonymous, BNode)
    result = Reasoner(graph, profile="L0")
    assert result.entails(anonymous, RDF.type, EX.A)
    assert result.entails(anonymous, EX.q, EX.b)
    assert Atom(TOP, (EX.bare,)) in result.program.facts
    assert len(list(graph.subjects(RDF.type, OWL.NamedIndividual))) == 2


def test_comments_unicode_names_literals_and_punctuation_in_strings():
    graph = parse_dlp(r'''
      // This URL is not a comment inside an IRI.
      Namespace(éx = <https://example.org/>)
      /* Multiline
         comment */ Ontology(<urn:example:ontology>
        Annotation(rdfs:label "An ontology"@en-us)
        Individual(éx:Änne annotation(rdfs:comment "quote \" and slash \\")
          value(éx:text ")") value(éx:url "https://example.org/a//b")
          value(éx:age "007"^^xsd:integer))
      )
    ''')
    person = EX["Änne"]
    assert (person, RDFS.comment, Literal('quote " and slash \\')) in graph
    assert (person, EX.text, Literal(")")) in graph
    assert (person, EX.url, Literal("https://example.org/a//b")) in graph
    assert (person, EX.age, Literal("007", datatype=XSD.integer, normalize=False)) in graph
    assert Literal("An ontology", lang="en-us") in graph.objects(None, RDFS.label)


def test_annotations_are_metadata_even_without_explicit_property_declaration():
    graph = parse("""
      Annotation(ex:note "ontology metadata")
      OntologyProperty(ex:provenance annotation(rdfs:label "source"))
      AnnotationProperty(ex:commentary)
      Class(ex:A Deprecated partial annotation(ex:note "class metadata"))
      Datatype(ex:kind Deprecated annotation(ex:note "datatype metadata"))
      Individual(ex:a annotation(ex:commentary "individual metadata") type(ex:A))
    """)
    result = Reasoner(graph, profile="L0")
    assert result.instances(EX.A) == {EX.a}
    assert not result.property_pairs(EX.note)
    assert not result.property_pairs(EX.commentary)
    assert (EX.A, RDF.type, OWL.DeprecatedClass) in graph
    assert (EX.kind, OWL.deprecated, Literal(True)) in graph


def test_literals_work_as_facts_without_enabling_datatype_range_reasoning():
    result = reason('DatatypeProperty(ex:age Functional) '
                    'Individual(ex:a value(ex:age "42"^^xsd:integer))', "L1")
    assert result.property_values(EX.a, EX.age) == {Literal(42)}
    with pytest.raises(ProfileError, match="Datatype"):
        compile_graph(parse("DatatypeProperty(ex:age range(xsd:integer))"))
    with pytest.raises(ProfileError, match="datatype"):
        compile_graph(parse('SubClassOf(oneOf("a" "b") ex:A)'))


@pytest.mark.parametrize("body", [
    'ObjectProperty(ex:p) Individual(ex:a value(ex:p "literal"))',
    'Individual(ex:a value(ex:p "literal")) ObjectProperty(ex:p)',
    'Individual(ex:a value(ex:p ex:b)) DatatypeProperty(ex:p)',
    'ObjectProperty(ex:p) DatatypeProperty(ex:p)',
    'DatatypeProperty(ex:p) ObjectProperty(ex:p)',
    'DatatypeProperty(ex:p range(ex:UnknownDatatype))',
    'Class(ex:A partial restriction(ex:p value(ex:b))) DatatypeProperty(ex:p)',
    'Class(ex:A partial restriction(ex:p value("b"))) ObjectProperty(ex:p)',
    'Class(ex:A partial restriction(ex:p allValuesFrom(ex:C))) DatatypeProperty(ex:p)',
    'Class(ex:A partial restriction(ex:p someValuesFrom(ex:C))) DatatypeProperty(ex:p)',
    'Class(ex:A partial restriction(ex:p minCardinality(1))) DatatypeProperty(ex:p)',
    'Class(ex:A partial localdomain(ex:p ex:B)) DatatypeProperty(ex:p)',
    'Class(ex:A partial localrange(ex:p ex:B)) DatatypeProperty(ex:p)',
    'ObjectProperty(ex:p super(ex:q)) DatatypeProperty(ex:q)',
    'DatatypeProperty(ex:p) EquivalentProperties(ex:p ex:q) ObjectProperty(ex:q)',
])
def test_explicit_property_kinds_are_checked_even_after_their_uses(body):
    with pytest.raises(DLPParseError):
        parse(body)


def test_declared_datatype_has_value_restriction_retains_literal_semantics():
    result = reason('Class(ex:A partial restriction(ex:p value("literal"))) '
                    'Individual(ex:a type(ex:A)) DatatypeProperty(ex:p)', "L0")
    assert result.property_values(EX.a, EX.p) == {Literal("literal")}


def test_chapter_5_l3_extensions_create_distinct_witnesses():
    body = """
      Class(ex:A partial restriction(ex:p someValuesFrom(ex:B))
                         restriction(ex:q minCardinality(2)))
      Class(ex:C complete restriction(ex:r someValuesFrom(ex:D)))
      Individual(ex:a type(ex:A))
    """
    with pytest.raises(ProfileError, match="L3"):
        reason(body, "L2")
    result = reason(body, "L3")
    assert len(result.property_values(EX.a, EX.p, include_witnesses=True)) == 1
    witnesses = result.property_values(EX.a, EX.q, include_witnesses=True)
    assert len(witnesses) == 2
    left, right = witnesses
    assert result.entails(left, OWL.differentFrom, right)


@pytest.mark.parametrize("body", [
    "SubClassOf(ex:A unionOf(ex:B ex:C))",
    "SubClassOf(restriction(ex:p allValuesFrom(ex:A)) ex:B)",
    "SubClassOf(ex:A oneOf(ex:a ex:b))",
    "Class(ex:A partial restriction(ex:p maxCardinality(2)))",
])
def test_parser_does_not_silently_drop_non_horn_constructs(body):
    graph = parse(body)
    with pytest.raises(ProfileError):
        compile_graph(graph, "L3")


def test_empty_intersection_and_singleton_enumeration_follow_the_thesis():
    result = reason("""
      Class(ex:Universal complete)
      EnumeratedClass(ex:Only ex:a)
      EquivalentClasses(ex:Unconstrained)
      Individual(ex:b)
    """, "L1")
    assert result.entails(EX.a, RDF.type, EX.Only)
    assert result.entails(EX.b, RDF.type, EX.Universal)
    assert not result.entails(EX.b, RDF.type, EX.Unconstrained)


def test_repeated_enumerated_class_definitions_conjoin_instead_of_overwriting():
    result = reason('EnumeratedClass(ex:Only ex:a) EnumeratedClass(ex:Only ex:a) '
                    'EnumeratedClass(ex:Only ex:b)', "L1")
    assert result.entails(EX.a, OWL.sameAs, EX.b)
    assert result.entails(EX.a, RDF.type, EX.Only)


@pytest.mark.parametrize("body", [
    "SubClassOf(ex:A)", "SubClassOf(ex:A ex:B ex:C)",
    "SubPropertyOf(ex:p)", "SubPropertyOf(ex:p ex:q ex:r)",
    "EquivalentClasses()", "EquivalentProperties(ex:p)",
    "SameIndividual(ex:a)", "DifferentIndividuals(ex:a)", "DisjointClasses(ex:A)",
    "EnumeratedClass(ex:A)", "EnumeratedClass(ex:A ex:a ex:b)",
    "Class(ex:A)", 'Class(ex:A "partial")',
    "Class(ex:A partial complementOf(ex:B ex:C))",
    "Class(ex:A partial restriction(ex:p))",
    "Class(ex:A partial restriction(ex:p minCardinality(-1)))",
    "Class(ex:A partial restriction(ex:p cardinality(1 ex:B)))",
    "Class(ex:A complete localrange(ex:p ex:B))",
    "ObjectProperty(ex:p inverseOf(ex:q ex:r))",
    "ObjectProperty(ex:p Transitive Transitive)",
    'ObjectProperty(ex:p "Functional")',
    "DatatypeProperty(ex:p Symmetric)",
    "Individual(ex:a value(ex:p ex:b ex:c))",
    "Individual(ex:a value(ex:p ex:b) type(ex:A))",
    "Individual(ex:a type())", "Individual(ex:a value(ex:p))",
    'Annotation(rdfs:label "one" "two")',
    "Imports(<https://example.org/remote>)",
    "Class(ex:A partial nonsense(ex:B))",
])
def test_malformed_constructs_are_errors(body):
    with pytest.raises(DLPParseError):
        parse(body)


@pytest.mark.parametrize("source", [
    "Ontology() Ontology()", "Ontology(", "Ontology() extra", "/* unterminated",
    'Ontology(Annotation(rdfs:label "unterminated))',
    'Ontology(Annotation(rdfs:label "bad\\n"))',
    'Ontology(Annotation(rdfs:label "bad"@123))',
    "Namespace(ex = <relative>) Ontology()",
    "Namespace(ex = <https://example.org/with space>) Ontology()",
    "Namespace(ex2 = <https://example.org/>) Ontology()",
    "Namespace(ex = <https://example.org/>) Namespace(ex = <urn:other:>) Ontology()",
    "Ontology(Class(unknown:A partial))",
    PREFIX + "Ontology(Class(ex:has-hyphen partial))",
    PREFIX + "Ontology(Class(ex:123 partial))",
])
def test_malformed_lexical_input_is_located(source):
    with pytest.raises(DLPParseError) as failure:
        parse_dlp(source, source="bad.dlp")
    assert failure.value.source == "bad.dlp"
    assert failure.value.line >= 1 and failure.value.column >= 1
    assert str(failure.value).startswith("bad.dlp:")


def test_unknown_prefix_location_is_exact():
    with pytest.raises(DLPParseError) as failure:
        parse_dlp("Ontology(\n  Class(missing:A partial)\n)", source="error.dlp")
    assert failure.value.line == 2
    assert failure.value.column == 9
    assert "Undeclared namespace prefix" in str(failure.value)


@pytest.mark.parametrize("body", [
    'Class(ex:A partial annotation(ex:p "note")) Individual(ex:a value(ex:p ex:b))',
    'Individual(ex:a value(ex:p ex:b)) AnnotationProperty(ex:p)',
    'Class(ex:A partial annotation(rdfs:subClassOf ex:X)) SubClassOf(ex:A ex:B)',
    'AnnotationProperty(owl:sameAs) SameIndividual(ex:a ex:b)',
    'OntologyProperty(rdf:type)',
    'Annotation(owl:intersectionOf ex:A)',
    'Individual(ex:a value(rdfs:subClassOf ex:b))',
    'Individual(ex:a value(rdfs:label "not a logical fact"))',
    'ObjectProperty(owl:sameAs)',
])
def test_annotations_and_reserved_predicates_cannot_erase_or_change_logical_axioms(body):
    with pytest.raises(DLPParseError):
        parse(body)


@pytest.mark.parametrize("body", [
    "Individual(ex:a type(owl:Class))",
    "Individual(ex:a type(rdf:Property))",
    "Individual(ex:a type(owl:FunctionalProperty))",
    "Class(owl:Class partial ex:A)",
    "SubClassOf(owl:AnnotationProperty ex:A)",
    "SubClassOf(ex:A owl:AllDifferent)",
])
def test_reserved_declarations_cannot_be_reinterpreted_as_class_assertions(body):
    with pytest.raises(DLPParseError, match="class description"):
        parse(body)


def test_imports_are_rejected_without_fetching_any_iris():
    with pytest.raises(DLPParseError, match="imports"):
        parse('Annotation(owl:imports <https://example.org/never-fetch-this>)')


def test_excessive_nesting_has_a_located_error_not_a_python_traceback():
    body = "Class(ex:A partial " + "intersectionOf(" * 1500 + "ex:B" + ")" * 1500 + ")"
    with pytest.raises(DLPParseError, match="nesting exceeds"):
        parse(body)


def test_namespaces_and_ontology_ids_are_local_identifiers(monkeypatch):
    def disallow_network(*args, **kwargs):
        raise AssertionError("Parser attempted network access")

    monkeypatch.setattr("urllib.request.urlopen", disallow_network)
    graph = parse_dlp("Namespace(ex = <https://example.org/>) "
                      "Ontology(<https://example.org/ontology> Class(ex:A partial))")
    assert (EX.ontology, RDF.type, OWL.Ontology) in graph
    assert str(dict(graph.namespaces())["ex"]) == str(EX)
