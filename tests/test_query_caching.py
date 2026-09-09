"""Query memoization and selection preserve the live reasoner's semantics."""
import random
import shutil

import pytest
from rdflib import BNode, Graph, Literal, Namespace, OWL, RDF, RDFS

from dlp_reasoner import (
    IncompleteReasoningError, InconsistentOntologyError, ProfileError, Reasoner,
)
from dlp_reasoner.model import Atom


EX = Namespace("urn:query-cache:")
PREFIX = """@prefix ex: <urn:query-cache:> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
"""


@pytest.fixture(params=["python", "native"])
def backend(request):
    if request.param == "native":
        if not any(shutil.which(name) for name in ("clang++", "g++", "c++")):
            pytest.skip("Native execution requires an installed C++17 compiler")
        from dlp_reasoner.native import build_native
        build_native()
    return request.param


def reason(text="", *, backend="python", **options):
    graph = Graph().parse(data=PREFIX + text, format="turtle")
    return Reasoner(graph, backend=backend, **options)


def count_probe_constructions(monkeypatch):
    original = Reasoner.__init__
    created = []

    def traced(self, *args, **kwargs):
        original(self, *args, **kwargs)
        created.append(self)

    monkeypatch.setattr(Reasoner, "__init__", traced)
    return created


def test_repeated_boolean_probe_is_cached_without_retaining_or_rebuilding_probe_engine(
        backend, monkeypatch):
    ontology = reason("ex:A rdfs:subClassOf ex:B.", backend=backend)
    created = count_probe_constructions(monkeypatch)
    assert not ontology.subsumes(EX.A, EX.B)
    first = len(created)
    assert first == 1
    assert not ontology.subsumes(EX.A, EX.B)
    assert len(created) == first
    assert ontology.query_cache_info["hits"] >= 1
    assert ontology.query_cache_info["entries"] >= 1


def test_first_query_still_computes_and_disabled_cache_repeats_the_probe(backend, monkeypatch):
    ontology = reason("ex:A rdfs:subClassOf ex:B.", backend=backend, query_cache_size=0)
    created = count_probe_constructions(monkeypatch)
    assert not ontology.subsumes(EX.A, EX.B)
    assert not ontology.subsumes(EX.A, EX.B)
    assert len(created) == 2
    assert ontology.query_cache_info["entries"] == 0


@pytest.mark.parametrize("method,args,expected", [
    ("subsumes", (EX.A, EX.B), False),
    ("property_subsumes", (EX.p, EX.q), False),
    ("is_transitive", (EX.p,), False),
    ("is_symmetric", (EX.p,), False),
    ("is_satisfiable", (EX.A,), True),
    ("has_domain", (EX.p, EX.A), False),
    ("has_range", (EX.p, EX.A), False),
    ("equivalent_classes", (EX.A, EX.B), False),
    ("equivalent_properties", (EX.p, EX.q), False),
    ("inverse_properties", (EX.p, EX.q), False),
])
def test_boolean_query_families_reuse_complete_answers(method, args, expected, monkeypatch):
    ontology = reason("ex:A rdfs:subClassOf ex:B. ex:p rdfs:subPropertyOf ex:q.")
    created = count_probe_constructions(monkeypatch)
    assert getattr(ontology, method)(*args) is expected
    first = len(created)
    assert first > 0
    assert getattr(ontology, method)(*args) is expected
    assert len(created) == first


def test_retrieval_results_are_fresh_mutable_sets_and_options_are_separate(backend):
    ontology = reason("""ex:a a ex:A; ex:p ex:b, "literal". ex:b a ex:B.
        ex:A rdfs:subClassOf [owl:onProperty ex:q; owl:someValuesFrom ex:B].""",
                      profile="L3", backend=backend)
    calls = [("instances", (EX.A,)), ("types", (EX.a,)),
             ("property_values", (EX.a, EX.p)), ("property_pairs", (EX.p,))]
    for method, args in calls:
        first = getattr(ontology, method)(*args)
        expected = set(first)
        first.clear()
        first.add(EX.poison)
        assert getattr(ontology, method)(*args) == expected
    assert ontology.property_values(EX.a, EX.q) == set()
    witnesses = ontology.property_values(EX.a, EX.q, include_witnesses=True)
    assert witnesses and all(isinstance(value, BNode) for value in witnesses)
    assert ontology.property_values(EX.a, EX.q) == set()
    assert Literal("literal") in ontology.property_values(EX.a, EX.p)


def test_queries_using_a_predicate_of_the_other_arity_return_empty_answers(backend):
    ontology = reason("ex:a a ex:A; ex:p ex:b.", backend=backend)
    for _ in range(2):
        assert ontology.instances(EX.p) == set()
        assert ontology.property_values(EX.a, EX.A) == set()
        assert ontology.property_pairs(EX.A) == set()


def test_cache_disabled_retrievals_use_indexes_without_scanning_the_fact_set(backend):
    ontology = reason("ex:a a ex:A; ex:p ex:b. ex:b a ex:B.", backend=backend,
                      query_cache_size=0)

    class NoIteration(set):
        def __iter__(self):
            raise AssertionError("Selective queries must not scan the complete fact set")

    # Build the shared reverse type view once, then probe a different known
    # individual to distinguish view reuse from a memoized query answer.
    assert ontology.types(EX.a) == {EX.A, OWL.Thing}
    ontology.engine.facts = NoIteration(ontology.engine.facts)
    assert ontology.instances(EX.A) == {EX.a}
    assert ontology.property_values(EX.a, EX.p) == {EX.b}
    assert ontology.property_pairs(EX.p) == {(EX.a, EX.b)}
    assert ontology.types(EX.b) == {EX.B, OWL.Thing}


def test_query_cache_capacity_clear_and_statistics_do_not_change_reasoning(backend):
    ontology = reason("ex:a a ex:A.", backend=backend, query_cache_size=2)
    for concept in (EX.A, EX.B, EX.C, EX.D):
        ontology.instances(concept)
        assert ontology.query_cache_info["entries"] <= 2
    before = dict(ontology.stats)
    ontology.clear_query_cache()
    assert ontology.query_cache_info["entries"] == 0
    assert ontology.stats == before
    assert ontology.instances(EX.A) == {EX.a}


def test_successful_updates_invalidate_answers_and_reuse_unchanged_schema_proofs(backend):
    ontology = reason("ex:A rdfs:subClassOf ex:B. ex:a a ex:A.", backend=backend)
    assert ontology.subsumes(EX.B, EX.A)
    schema = ontology._schema()
    assert ontology.instances(EX.B) == {EX.a}
    ontology.update(add=[(EX.b, RDF.type, EX.A)])
    assert ontology._schema() is schema
    assert ontology.instances(EX.B) == {EX.a, EX.b}
    ontology.update(remove=[(EX.A, RDFS.subClassOf, EX.B)])
    assert ontology._schema() is not schema
    assert ontology.instances(EX.B) == set()
    assert not ontology.subsumes(EX.B, EX.A)


def test_rejected_update_preserves_answers_and_can_still_hit_the_cache(backend):
    ontology = reason("ex:a a ex:A.", backend=backend)
    assert ontology.instances(EX.A) == {EX.a}
    before = dict(ontology.query_cache_info)
    node = BNode()
    with pytest.raises(ProfileError):
        ontology.update(add=[(EX.A, RDFS.subClassOf, node), (node, OWL.onProperty, EX.p),
                             (node, OWL.someValuesFrom, EX.A)])
    assert ontology.instances(EX.A) == {EX.a}
    assert ontology.query_cache_info["hits"] > before["hits"]


def test_direct_engine_transactions_invalidate_retrieval_answers(backend):
    ontology = reason("ex:a a ex:A.", backend=backend)
    assert ontology.instances(EX.A) == {EX.a}
    ontology.engine.update(add=[Atom(EX.A, (EX.b,))])
    assert ontology.instances(EX.A) == {EX.a, EX.b}
    ontology.engine.update(remove=[Atom(EX.A, (EX.a,))])
    assert ontology.instances(EX.A) == {EX.b}
    ontology.engine.materialize()
    assert ontology.instances(EX.A) == {EX.b}


@pytest.mark.parametrize("mutation", ["add", "addN", "parse", "store_add", "set"])
def test_direct_graph_mutation_invalidates_boolean_probe_answers(mutation):
    ontology = reason("ex:A rdfs:subClassOf ex:B.")
    assert ontology.is_satisfiable(EX.A)
    triple = EX.A, OWL.disjointWith, EX.B
    if mutation == "add":
        ontology.graph.add(triple)
    elif mutation == "addN":
        ontology.graph.addN([(*triple, ontology.graph)])
    elif mutation == "parse":
        ontology.graph.parse(data=PREFIX + "ex:A owl:disjointWith ex:B.", format="turtle")
    elif mutation == "store_add":
        ontology.graph.store.add(triple, ontology.graph, quoted=False)
    else:
        ontology.graph.set(triple)
    assert not ontology.is_satisfiable(EX.A)


@pytest.mark.parametrize("mutation", ["remove", "store_remove", "set", "replace_graph"])
def test_same_size_swaps_and_graph_replacement_do_not_reuse_stale_answers(mutation):
    ontology = reason("ex:A rdfs:subClassOf ex:B; owl:disjointWith ex:B.")
    assert not ontology.is_satisfiable(EX.A)
    old, new = (EX.A, RDFS.subClassOf, EX.B), (EX.A, RDFS.subClassOf, EX.C)
    size = len(ontology.graph)
    if mutation == "replace_graph":
        replacement = Graph()
        replacement += ontology.graph
        replacement.remove(old)
        replacement.add(new)
        ontology.graph = replacement
    elif mutation == "set":
        ontology.graph.set(new)
    elif mutation == "store_remove":
        ontology.graph.store.remove(old, ontology.graph)
        ontology.graph.store.add(new, ontology.graph, quoted=False)
    else:
        ontology.graph.remove(old)
        ontology.graph.add(new)
    assert len(ontology.graph) == size
    assert ontology.is_satisfiable(EX.A)


def test_anonymous_expression_cache_key_tracks_its_changed_structure(backend):
    ontology = reason("""ex:a ex:p ex:b. ex:b a ex:B.
        ex:Query owl:equivalentClass [owl:onProperty ex:p; owl:someValuesFrom ex:B].""",
                      backend=backend, profile="L3")
    expression = ontology.graph.value(EX.Query, OWL.equivalentClass)
    assert ontology.instances(expression) == {EX.a}
    count = len(ontology.graph)
    ontology.graph.set((expression, OWL.someValuesFrom, EX.C))
    assert len(ontology.graph) == count
    assert ontology.instances(expression) == set()


def test_equality_split_and_nominal_changes_invalidate_cached_answers(backend):
    ontology = reason("""ex:a a ex:A; owl:sameAs ex:b.
        ex:Nominal owl:oneOf (ex:a).""", backend=backend)
    assert ontology.instances(EX.A) == {EX.a, EX.b}
    assert ontology.entails(EX.a, OWL.sameAs, EX.b)
    assert ontology.instances(EX.Nominal) == {EX.a, EX.b}
    ontology.update(remove=[(EX.a, OWL.sameAs, EX.b)])
    assert ontology.instances(EX.A) == {EX.a}
    assert not ontology.entails(EX.a, OWL.sameAs, EX.b)
    assert ontology.instances(EX.Nominal) == {EX.a}


def test_mixed_updates_match_fresh_uncached_reasoner_for_all_retrievals(backend):
    ontology = reason("""ex:a a ex:A. ex:A rdfs:subClassOf ex:B.
        ex:p a owl:TransitiveProperty; rdfs:subPropertyOf ex:q.
        ex:a ex:p ex:b. ex:b ex:p ex:c.""", backend=backend)
    rng = random.Random(302)
    terms = [EX.a, EX.b, EX.c, EX.d]
    pool = [(left, EX.p, right) for left in terms for right in terms]
    pool += [(term, RDF.type, EX.A) for term in terms]
    pool += [(EX.p, RDFS.subPropertyOf, EX.q), (EX.A, RDFS.subClassOf, EX.B)]
    for _ in range(12):
        ontology.update(add=rng.sample(pool, 2), remove=rng.sample(pool, 3))
        fresh = Reasoner(ontology.graph, backend=backend, query_cache_size=0)
        for _ in range(2):
            assert ontology.instances(EX.B) == fresh.instances(EX.B)
            assert ontology.property_pairs(EX.p) == fresh.property_pairs(EX.p)
            assert ontology.property_pairs(EX.q) == fresh.property_pairs(EX.q)
            for term in terms:
                assert ontology.types(term) == fresh.types(term)
                assert ontology.property_values(term, EX.p) == fresh.property_values(term, EX.p)
                assert ontology.entails(term, RDF.type, EX.A) == fresh.entails(term, RDF.type, EX.A)


def test_individual_equality_must_not_alias_class_or_property_cache_arguments(backend):
    ontology = reason("""ex:A owl:sameAs ex:B. ex:a a ex:A.
        ex:p owl:sameAs ex:q. ex:a ex:p ex:b.""", backend=backend)
    assert ontology.instances(EX.A) == {EX.a}
    assert ontology.instances(EX.B) == set()
    assert ontology.property_values(EX.a, EX.p) == {EX.b}
    assert ontology.property_values(EX.a, EX.q) == set()


def test_fresh_name_queries_repeat_without_mutating_the_live_domain(backend, monkeypatch):
    ontology = reason("ex:A rdfs:subClassOf ex:B.", backend=backend)
    before = set(ontology.engine.terms), set(ontology.graph)
    assert ontology.types(EX.fresh) == {OWL.Thing}
    hits = ontology.query_cache_info["hits"]
    assert ontology.types(EX.fresh) == {OWL.Thing}
    assert ontology.query_cache_info["hits"] > hits
    assert (set(ontology.engine.terms), set(ontology.graph)) == before


def test_inconsistent_and_incomplete_guards_run_before_cached_answers(backend):
    ontology = reason("ex:a a ex:A.", backend=backend)
    assert ontology.instances(EX.A) == {EX.a}
    assert not ontology.entails(EX.a, RDF.type, EX.B)
    ontology.engine.complete = False
    with pytest.raises(IncompleteReasoningError):
        ontology.instances(EX.A)
    with pytest.raises(IncompleteReasoningError):
        ontology.entails(EX.a, RDF.type, EX.B)
    ontology.engine.complete = True
    ontology.engine.violations.append("deliberate consistency state change")
    with pytest.raises(InconsistentOntologyError):
        ontology.instances(EX.A)


def test_positive_incomplete_entailment_is_not_cached_as_a_complete_answer(backend):
    ontology = reason("""ex:a a ex:A.
        ex:A rdfs:subClassOf [owl:onProperty ex:p; owl:someValuesFrom ex:A].""",
                      backend=backend, profile="L3", max_depth=2)
    assert not ontology.complete
    assert ontology.entails(EX.a, RDF.type, EX.A)
    assert ontology.query_cache_info["entries"] == 0
    with pytest.raises(IncompleteReasoningError):
        ontology.is_satisfiable(EX.A)
    assert ontology.query_cache_info["entries"] == 0


def test_changed_probe_limits_invalidate_previous_boolean_answer(backend):
    ontology = reason("ex:A rdfs:subClassOf [owl:onProperty ex:p; owl:someValuesFrom ex:B].",
                      backend=backend, profile="L3")
    assert ontology.is_satisfiable(EX.A)
    ontology.engine_options["max_depth"] = 0
    with pytest.raises(IncompleteReasoningError):
        ontology.is_satisfiable(EX.A)


def test_changed_profile_does_not_reuse_a_probe_from_a_more_permissive_profile():
    ontology = reason("ex:A rdfs:subClassOf [owl:onProperty ex:p; owl:someValuesFrom ex:B].",
                      profile="L3")
    assert ontology.is_satisfiable(EX.A)
    ontology.profile = "L2"
    with pytest.raises(ProfileError):
        ontology.is_satisfiable(EX.A)


def test_cache_does_not_retain_failed_probe_as_false():
    ontology = reason("ex:A rdfs:subClassOf [owl:onProperty ex:p; owl:someValuesFrom ex:A].",
                      profile="L3", max_depth=2)
    for _ in range(2):
        with pytest.raises(IncompleteReasoningError):
            ontology.is_satisfiable(EX.A)
    assert ontology.query_cache_info["entries"] == 0
