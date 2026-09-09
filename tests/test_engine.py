"""Execution regressions independent of the RDF/OWL compiler."""

import random

import pytest
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import RDF, XSD

from dlp_reasoner import Reasoner
from dlp_reasoner.engine import Engine
from dlp_reasoner.model import Atom, EQ, NEQ, TOP, ProfileError, Program, Rule, Skolem, Var


x, y, z = Var("x"), Var("y"), Var("z")
a, b, c, d = (URIRef(f"urn:test:{name}") for name in "abcd")


def atom(predicate, *args):
    return Atom(predicate, args)


def run(rules=(), facts=(), **kwargs):
    return Engine(Program(list(rules), set(facts)), **kwargs).materialize()


@pytest.mark.parametrize("strategy", ["semi-naive", "naive"])
def test_indexed_join_repeated_variables_and_constants(strategy):
    rules = [Rule(atom("reach", x, y), (atom("edge", x, y),)),
             Rule(atom("reach", x, z), (atom("reach", x, y), atom("edge", y, z))),
             Rule(atom("loop", x), (atom("reach", x, x),)),
             Rule(atom("to_c", x), (atom("reach", x, c),)),
             Rule(atom("yes"), (atom("reach", a, c),))]
    engine = run(rules, [atom("edge", a, b), atom("edge", b, c), atom("edge", c, b)],
                 strategy=strategy)
    assert engine.complete
    assert atom("reach", a, c) in engine.facts
    assert atom("loop", b) in engine.facts
    assert atom("loop", a) not in engine.facts
    assert atom("to_c", a) in engine.facts
    assert atom("yes") in engine.facts


def test_semantics_without_unique_name_assumption():
    rule = Rule(atom("different", x, y), (atom("p", x), atom("p", y), atom(NEQ, x, y)))
    engine = run([rule], [atom("p", a), atom("p", b)])
    assert not any(f.predicate == "different" for f in engine.facts)
    engine.update(add=[atom(NEQ, a, b)])
    assert atom("different", a, b) in engine.facts
    assert atom("different", b, a) in engine.facts
    engine.update(add=[atom(EQ, a, b)])
    assert engine.violations


def test_nonempty_domain_rule_constants_and_empty_constraint():
    engine = run([Rule(None, (atom(TOP, x),), "empty universe is impossible")])
    assert engine.violations
    assert any(f.predicate == TOP for f in engine.facts)
    engine = run([Rule(atom("p", a))])
    assert atom(TOP, a) in engine.facts
    assert atom("p", a) in engine.facts
    assert run([Rule(None, (), "false")]).violations == ["false violated"]


def test_anonymous_domain_seed_cannot_alias_an_input_bnode_label():
    user_node = BNode("dlp-internal-nonempty-domain")
    engine = run(facts=[atom("p", user_node)])
    assert len(engine.terms) == 2


def test_equality_reindexes_old_joins_and_ground_equality_rules():
    rules = [Rule(atom("both", x), (atom("p", x), atom("q", x))),
             Rule(atom(EQ, y, z), (atom("r", x, y), atom("r", x, z))),
             Rule(atom("ground_result", c), (atom(EQ, a, b),))]
    engine = run(rules, [atom("p", a), atom("q", b), atom("r", c, a), atom("r", c, b)])
    representative = engine.normalize(a)
    assert representative == engine.normalize(b)
    assert atom("both", representative) in engine.facts
    assert atom("ground_result", c) in engine.facts
    assert {a, b} <= engine.equivalents(a)


def test_equality_can_bind_a_variable_from_a_known_side():
    engine = run([Rule(atom("q", y), (atom(EQ, x, y), atom("p", x)))], [atom("p", a)])
    assert atom("q", a) in engine.facts
    assert atom("p", b) in run([Rule(atom("p", x), (atom(EQ, x, b),))]).facts


@pytest.mark.parametrize("strategy", ["semi-naive", "naive"])
def test_function_congruence_after_late_equality(strategy):
    fa, fb = Skolem("f", (a,)), Skolem("f", (b,))
    rules = [Rule(atom("p", Skolem("f", (x,))), (atom("left", x),)),
             Rule(atom("q", Skolem("f", (x,))), (atom("right", x),)),
             Rule(atom("both", x), (atom("p", x), atom("q", x))),
             Rule(atom("late", x, y), (atom("merge", x, y),)),
             Rule(atom(EQ, x, y), (atom("late", x, y),))]
    engine = run(rules, [atom("left", a), atom("right", b), atom("merge", a, b)],
                 strategy=strategy)
    assert engine.normalize(fa) == engine.normalize(fb)
    assert atom("both", engine.normalize(fa)) in engine.facts
    assert {fa, fb} <= engine.equivalents(fa)


def test_function_congruence_reaches_nested_fixed_point():
    fa, fb = Skolem("f", (a,)), Skolem("f", (b,))
    ga, gb = Skolem("g", (fa,)), Skolem("g", (fb,))
    engine = run(facts=[atom("p", ga), atom("q", gb)])
    engine.update(add=[atom(EQ, a, b)])
    assert engine.normalize(ga) == engine.normalize(gb)
    engine.update(add=[atom(EQ, fa, c)])
    assert engine.normalize(ga) == engine.normalize(Skolem("g", (c,)))


def test_datatype_value_equality_and_distinction():
    integer = Literal("1", datatype=XSD.integer)
    decimal = Literal("1.0", datatype=XSD.decimal)
    engine = run(facts=[atom("p", integer), atom("q", decimal)])
    assert engine.normalize(integer) == engine.normalize(decimal)
    assert not engine.violations
    engine.update(add=[atom(EQ, integer, Literal("2", datatype=XSD.integer))])
    assert any("distinct datatype values" in v for v in engine.violations)
    assert run(facts=[atom(EQ, Literal(False), Literal(0))]).violations
    assert not run(facts=[atom(EQ, a, b)]).violations


@pytest.mark.parametrize("left,right", [
    (Literal("urn:a", datatype=XSD.anyURI), Literal("urn:a", datatype=XSD.string)),
    (Literal("1", datatype=XSD.float), Literal("1", datatype=XSD.double)),
    (Literal("1", datatype=XSD.float), Literal("1", datatype=XSD.decimal)),
    (Literal("1", datatype=XSD.double), Literal("1", datatype=XSD.decimal)),
    (Literal("61", datatype=XSD.hexBinary), Literal("YQ==", datatype=XSD.base64Binary)),
    (Literal("abc", datatype=XSD.normalizedString), Literal("abc", datatype=XSD.string)),
    (Literal("abc", datatype=XSD.token), Literal("abc", datatype=XSD.string)),
])
def test_opaque_datatypes_do_not_gain_automatic_value_identity(left, right):
    engine = run(facts=[atom("p", left), atom("q", right)])
    assert engine.normalize(left) != engine.normalize(right)
    assert engine.stats["equality_merges"] == 0


def test_ill_typed_integer_subtype_has_no_understood_value_identity():
    invalid = Literal("999", datatype=XSD.unsignedByte)
    valid = Literal("999", datatype=XSD.integer)
    assert invalid.ill_typed is True
    engine = run(facts=[atom("p", invalid), atom("q", valid)])
    assert engine.normalize(invalid) != engine.normalize(valid)


def test_plain_and_xsd_string_identity_and_language_distinction():
    plain = Literal("hello")
    typed = Literal("hello", datatype=XSD.string)
    english = Literal("hello", lang="en")
    engine = run(facts=[atom("p", plain), atom("q", typed), atom("r", english)])
    assert engine.normalize(plain) == engine.normalize(typed)
    assert engine.normalize(plain) != engine.normalize(english)


def test_anyuri_cannot_trigger_string_hasvalue_classification():
    graph = Graph().parse(data='''
        @prefix : <urn:test:> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
        :a :p "urn:value"^^xsd:anyURI .
        [ owl:onProperty :p; owl:hasValue "urn:value"^^xsd:string ]
            rdfs:subClassOf :StringValue .
        ''', format="turtle")
    reasoner = Reasoner(graph)
    assert not reasoner.entails(a, RDF.type, URIRef("urn:test:StringValue"))
    assert not reasoner.entails(a, URIRef("urn:test:p"), Literal("urn:value", datatype=XSD.string))


def test_literal_value_distinction_in_rule_body():
    engine = run([Rule(atom("different", x, y), (atom("p", x), atom("p", y), atom(NEQ, x, y)))],
                 [atom("p", Literal(1)), atom("p", Literal(2))])
    assert atom("different", Literal(1), Literal(2)) in engine.facts


@pytest.mark.parametrize("rule", [
    Rule(atom("p", x), ()),
    Rule(atom("p", x), (atom(EQ, x, y),)),
    Rule(atom("p", x), (atom(NEQ, x, a),)),
    Rule(atom("p", x), (atom("q", Skolem("f", (x,))),)),
])
def test_unsafe_or_unsupported_rules_fail_explicitly(rule):
    with pytest.raises(ProfileError):
        run([rule])


def test_arity_and_ground_fact_validation():
    with pytest.raises(ProfileError, match="arity"):
        run(facts=[atom("p", a), atom("p", a, b)])
    with pytest.raises(ProfileError, match="ground"):
        run(facts=[atom("p", x)])


def test_depth_and_round_bounds_leave_explicit_partial_results():
    rules = [Rule(atom("p", Skolem("f", (x,))), (atom("p", x),))]
    engine = run(rules, [atom("p", a)], max_depth=3)
    assert not engine.complete
    assert "max_depth" in engine.stats["limit_reason"]
    assert atom("p", a) in engine.facts
    engine = run([Rule(atom("q", x), (atom("p", x),)),
                  Rule(atom("r", x), (atom("q", x),))], [atom("p", a)], max_rounds=1)
    assert not engine.complete
    assert "max_rounds" in engine.stats["limit_reason"]


def test_fact_bound_cannot_silently_drop_a_batch():
    rules = [Rule(atom(f"q{i}", x), (atom("p", x),)) for i in range(20)]
    engine = run(rules, [atom("p", a)], max_facts=6)
    assert not engine.complete
    assert len(engine.facts) <= 6
    assert "max_facts" in engine.stats["limit_reason"]


def test_dred_alternate_proof_and_unsupported_recursive_cycle():
    rules = [Rule(atom("p", x), (atom("seed", x),)),
             Rule(atom("p", x), (atom("alternate", x),)),
             Rule(atom("q", x), (atom("p", x),)),
             Rule(atom("p", x), (atom("q", x),))]
    engine = run(rules, [atom("seed", a), atom("alternate", a)])
    engine.update(remove=[atom("seed", a)])
    assert engine.stats["update_method"] == "dred"
    assert engine.stats["overdeleted_facts"] >= 3
    assert engine.stats["rederived_facts"] >= 2
    assert atom("q", a) in engine.facts
    engine.update(remove=[atom("alternate", a)])
    assert atom("p", a) not in engine.facts
    assert atom("q", a) not in engine.facts
    assert engine.facts == run(rules).facts


def test_dred_preserves_asserted_derivations_and_prunes_domain():
    rules = [Rule(atom("q", x), (atom("p", x),)),
             Rule(atom("universal", x), (atom(TOP, x),))]
    engine = run(rules, [atom("p", a), atom("q", a)])
    engine.update(remove=[atom("p", a)])
    assert atom("q", a) in engine.facts
    engine.update(remove=[atom("q", a)])
    assert a not in engine.terms
    assert atom("universal", a) not in engine.facts
    assert engine.facts == run(rules).facts


def test_dred_removes_stale_constraint_violations():
    engine = run([Rule(None, (atom("p", x), atom("q", x)), "disjoint")],
                 [atom("p", a), atom("q", a)])
    assert engine.violations
    engine.update(remove=[atom("q", a)])
    assert not engine.violations
    assert engine.complete


def test_interrupted_dred_never_returns_unsupported_positive_facts():
    rules = [Rule(atom("p", x), (atom("seed", x),)),
             Rule(atom("q", x), (atom("p", x),)),
             Rule(atom("r", x), (atom("q", x),))]
    engine = run(rules, [atom("seed", a)])
    engine.max_rounds = 1
    engine.update(remove=[atom("seed", a)])
    assert engine.stats["update_method"] == "rematerialize-after-dred-limit"
    assert not any(f.predicate in {"seed", "p", "q", "r"} for f in engine.facts)
    assert engine.complete


def test_equality_and_witness_deletions_rematerialize():
    engine = run(facts=[atom("p", a), atom("p", b), atom(EQ, a, b)])
    engine.update(remove=[atom(EQ, a, b)])
    assert engine.stats["update_method"] == "rematerialize"
    assert engine.normalize(a) != engine.normalize(b)
    witness_rule = Rule(atom("q", Skolem("f", (x,))), (atom("p", x),))
    engine = run([witness_rule], [atom("p", a)])
    engine.update(remove=[atom("p", a)])
    assert engine.stats["update_method"] == "rematerialize"
    assert not any(f.predicate == "q" for f in engine.facts)


def test_equivalence_cache_invalidates_after_registration_and_merge():
    engine = run(facts=[atom(EQ, a, b)])
    assert engine.equivalents(a) == {a, b}
    engine.update(add=[atom(EQ, b, c)])
    assert engine.equivalents(a) == {a, b, c}
    engine.update(remove=[atom(EQ, b, c)])
    assert engine.equivalents(a) == {a, b}


def test_rule_insertion_propagates_and_rule_deletion_rebuilds():
    first = Rule(atom("q", x), (atom("p", x),))
    second = Rule(atom("r", x), (atom("q", x),))
    engine = run([second], [atom("p", a)])
    engine.update_rules(add=[first])
    assert engine.stats["update_method"] == "incremental-rules"
    assert atom("r", a) in engine.facts
    engine.update_rules(remove=[first])
    assert engine.stats["update_method"] == "rematerialize-rules"
    assert atom("r", a) not in engine.facts


def test_differential_naive_seminaive_and_dred_random_updates():
    rng = random.Random(20260909)
    domain = [a, b, c, d]
    rules = [Rule(atom("reach", x, y), (atom("edge", x, y),)),
             Rule(atom("reach", x, z), (atom("reach", x, y), atom("edge", y, z))),
             Rule(atom("p", x), (atom("seed", x),)),
             Rule(atom("p", y), (atom("p", x), atom("reach", x, y))),
             Rule(atom("q", x), (atom("p", x),)),
             Rule(atom("p", x), (atom("q", x),))]
    universe = [atom("edge", s, o) for s in domain for o in domain] + [atom("seed", s) for s in domain]
    facts = set(rng.sample(universe, 9))
    incremental = run(rules, facts)
    for _ in range(40):
        additions = set(rng.sample(universe, rng.randrange(4)))
        removals = set(rng.sample(universe, rng.randrange(4)))
        facts = (facts - removals) | additions
        incremental.update(add=additions, remove=removals)
        naive = run(rules, facts, strategy="naive")
        assert incremental.complete
        assert incremental.facts == naive.facts
        assert incremental.terms == naive.terms
