"""Execution regressions independent of the RDF/OWL compiler."""

import random
from itertools import product

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


def test_rule_insertion_propagates_and_rule_deletion_uses_dred():
    first = Rule(atom("q", x), (atom("p", x),))
    second = Rule(atom("r", x), (atom("q", x),))
    engine = run([second], [atom("p", a)])
    engine.update_rules(add=[first])
    assert engine.stats["update_method"] == "incremental-rules"
    assert atom("r", a) in engine.facts
    engine.update_rules(remove=[first])
    assert engine.stats["update_method"] == "dred-rules"
    assert atom("r", a) not in engine.facts


@pytest.mark.parametrize("strategy", ["semi-naive", "naive"])
def test_rule_deletion_removes_stale_support_and_unsupported_recursive_cycle(strategy):
    source = Rule(atom("p", x), (atom("seed", x),))
    alternate = Rule(atom("p", x), (atom("alternative", x),))
    cycle = [Rule(atom("q", x), (atom("p", x),)),
             Rule(atom("p", x), (atom("q", x),))]
    unrelated = Rule(atom("unrelated", x), (atom("other", x),))
    facts = {atom("seed", a), atom("other", b)}
    engine = run([source, alternate, *cycle, unrelated], facts, strategy=strategy)
    engine.update_rules(remove=[source])
    assert engine.stats["update_method"] == "dred-rules"
    assert engine.stats["overdeleted_facts"] == 2
    assert atom("p", a) not in engine.facts
    assert atom("q", a) not in engine.facts
    assert atom("unrelated", b) in engine.facts
    assert engine.facts == run([alternate, *cycle, unrelated], facts).facts
    # The removed rule must also disappear from future insertion propagation.
    engine.update(add=[atom("seed", c)])
    assert atom("p", c) not in engine.facts
    engine.update_rules(add=[source])
    assert {atom("q", a), atom("q", c)} <= engine.facts


def test_rule_deletion_preserves_assertions_and_alternative_rule_owners():
    first = Rule(atom("p", x), (atom("seed", x),), "axiom-one")
    second = Rule(atom("p", x), (atom("seed", x),), "axiom-two")
    child = Rule(atom("q", x), (atom("p", x),))
    facts = {atom("seed", a), atom("p", b)}
    engine = run([first, first, second, child], facts)
    engine.update_rules(remove=[first])
    assert engine.stats["update_method"] == "dred-rules"
    assert engine.facts == run([second, child], facts).facts
    assert {atom("q", a), atom("q", b)} <= engine.facts
    engine.update_rules(remove=[second])
    assert atom("q", a) not in engine.facts
    assert atom("q", b) in engine.facts
    assert engine.facts == run([child], facts).facts


def test_deleted_rule_head_can_become_asserted_in_same_transaction():
    source = Rule(atom("p", x), (atom("seed", x),))
    child = Rule(atom("q", x), (atom("p", x),))
    engine = run([source, child], [atom("seed", a)])
    engine.update(remove_rules=[source], add=[atom("p", a)])
    assert engine.stats["update_method"] == "dred-rules"
    assert atom("q", a) in engine.facts
    assert engine.stats["overdeleted_facts"] == 0
    assert engine.facts == run([child], [atom("seed", a), atom("p", a)]).facts


def test_mixed_rule_fact_transaction_and_addition_wins_overlap():
    old = Rule(atom("p", x), (atom("seed", x),))
    new = Rule(atom("p", y), (atom("edge", x, y), atom("seed", x)))
    cycle = Rule(atom("p", x), (atom("p", x),))
    child = Rule(atom("q", x), (atom("p", x),))
    engine = run([old, cycle, child], [atom("seed", a), atom("seed", b)])
    engine.update(add=[atom("edge", b, c), atom("seed", b)],
                  remove=[atom("seed", a), atom("seed", b)],
                  add_rules=[new, child], remove_rules=[old, child])
    expected_facts = {atom("seed", b), atom("edge", b, c)}
    assert engine.stats["update_method"] == "dred-rules"
    assert engine.facts == run([cycle, child, new], expected_facts).facts
    assert atom("q", a) not in engine.facts
    assert atom("q", c) in engine.facts
    assert set(engine.program.rules) == {cycle, child, new}
    assert engine.program.facts == expected_facts


def test_rule_constants_enter_and_leave_domain_without_fact_changes():
    universal = Rule(atom("all", x), (atom(TOP, x),))
    old = Rule(atom("old", a), (atom("absent"),))
    new = Rule(atom("new", b), (atom("absent"),))
    unconditional = Rule(atom("unconditional", c))
    engine = run([universal, old])
    assert atom("all", a) in engine.facts
    engine.update_rules(remove=[old], add=[new, unconditional])
    assert engine.stats["update_method"] == "dred-rules"
    assert a not in engine.terms and {b, c} <= engine.terms
    assert atom("all", a) not in engine.facts
    assert {atom("all", b), atom("all", c), atom("unconditional", c)} <= engine.facts
    fresh = run([universal, new, unconditional])
    assert engine.facts == fresh.facts
    assert engine.terms == fresh.terms
    # The final defining rule can disappear entirely, including its constant.
    engine.update_rules(remove=[unconditional])
    assert c not in engine.terms
    assert engine.facts == run([universal, new]).facts


def test_mixed_constraints_are_rechecked_and_removed_violations_clear():
    first = Rule(None, (atom("p", x),), "forbid-p")
    second = Rule(None, (atom("q", x),), "forbid-q")
    derive = Rule(atom("q", x), (atom("seed", x),))
    engine = run([first], [atom("p", a)])
    assert engine.violations
    engine.update(add=[atom("seed", b)], remove_rules=[first], add_rules=[second, derive])
    assert engine.stats["update_method"] == "dred-rules"
    assert engine.violations == run([second, derive], [atom("p", a), atom("seed", b)]).violations
    assert all("forbid-p" not in violation for violation in engine.violations)
    engine.update_rules(remove=[derive])
    assert not engine.violations


def test_rule_dred_tracks_symmetric_difference_facts_and_constraints():
    derived = Rule(atom(NEQ, x, y), (atom("different", x, y),))
    use = Rule(atom("distinct", x, y), (atom("pair", x, y), atom(NEQ, x, y)))
    facts = {atom("different", a, b), atom("pair", a, b), atom("pair", b, a)}
    engine = run([derived, use], facts)
    assert {atom("distinct", a, b), atom("distinct", b, a)} <= engine.facts
    engine.update_rules(remove=[derived])
    assert engine.stats["update_method"] == "dred-rules"
    assert engine.facts == run([use], facts).facts


def test_mixed_update_validation_is_atomic():
    original = Rule(atom("q", x), (atom("p", x),))
    engine = run([original], [atom("p", a)])
    before = set(engine.facts), set(engine.asserted), list(engine.rules), dict(engine.stats)
    with pytest.raises(ProfileError, match="Unsafe"):
        engine.update(remove=[atom("p", a)], remove_rules=[original],
                      add_rules=[Rule(atom("unbound", x))])
    assert (engine.facts, engine.asserted, engine.rules, engine.stats) == before


def test_rule_deletion_rebuilds_for_equality_functions_and_incomplete_closure():
    merge = Rule(atom(EQ, x, y), (atom("merge", x, y),))
    engine = run([merge], [atom("merge", a, b), atom("p", a), atom("p", b)])
    engine.update_rules(remove=[merge])
    assert engine.stats["update_method"] == "rematerialize-rules"
    assert engine.normalize(a) != engine.normalize(b)
    witness = Rule(atom("q", Skolem("f", (x,))), (atom("p", x),))
    engine = run([witness], [atom("p", a)])
    engine.update_rules(remove=[witness])
    assert engine.stats["update_method"] == "rematerialize-rules"
    assert engine.facts == run(facts=[atom("p", a)]).facts
    recursive = Rule(atom("p", Skolem("f", (x,))), (atom("p", x),))
    engine = run([recursive], [atom("p", a)], max_depth=2)
    assert not engine.complete
    engine.update_rules(remove=[recursive])
    assert engine.complete
    assert engine.stats["update_method"] == "rematerialize-rules"


def test_mixed_dred_cannot_merge_new_datatype_representatives():
    old = Rule(atom("q", x), (atom("p", x),))
    integer, decimal = Literal("1", datatype=XSD.integer), Literal("1.0", datatype=XSD.decimal)
    engine = run([old], [atom("p", integer)])
    engine.update(remove_rules=[old], add=[atom("p", decimal)])
    assert engine.stats["update_method"] == "rematerialize-rules"
    assert engine.facts == run(facts=[atom("p", integer), atom("p", decimal)]).facts


@pytest.mark.parametrize("new_rule", [
    Rule(atom(EQ, a, b)),
    Rule(atom("witness", Skolem("f", (x,))), (atom("seed", x),)),
])
def test_mixed_transaction_checks_new_rules_before_choosing_dred(new_rule):
    source = Rule(atom("p", x), (atom("seed", x),))
    engine = run([source], [atom("seed", a)])
    engine.update(remove=[atom("seed", a)], add=[atom("seed", b)], add_rules=[new_rule])
    assert engine.stats["update_method"] == "rematerialize-rules"
    fresh = run([source, new_rule], [atom("seed", b)])
    assert engine.facts == fresh.facts
    assert engine.terms == fresh.terms


def test_dred_prunes_literal_identity_cache_with_departed_constants():
    plain, typed = Literal("hello"), Literal("hello", datatype=XSD.string)
    engine = run(facts=[atom("p", plain)])
    engine.update(remove=[atom("p", plain)])
    engine.update(add=[atom("p", typed)])
    assert engine.facts == run(facts=[atom("p", typed)]).facts
    assert plain not in engine.terms
    assert engine.normalize(typed) == typed


def test_rule_dred_limits_rebuild_before_returning_any_stale_facts():
    first = Rule(atom("p", x), (atom("seed", x),))
    rest = [Rule(atom("q", x), (atom("p", x),)),
            Rule(atom("r", x), (atom("q", x),))]
    engine = run([first, *rest], [atom("seed", a)])
    engine.max_rounds = 1
    engine.update_rules(remove=[first])
    assert engine.stats["update_method"] == "rematerialize-rules-after-dred-limit"
    assert engine.complete
    assert engine.facts == run(rest, [atom("seed", a)]).facts


def test_rule_dred_rederivation_and_candidate_limits_leave_sound_partial_results():
    old = Rule(atom("p", x), (atom("seed", x),))
    replacement = [Rule(atom("q", x), (atom("seed", x),)),
                   Rule(atom("p", x), (atom("q", x),))]
    engine = run([old], [atom("seed", a)])
    engine.max_rounds = 1
    engine.update_rules(remove=[old], add=replacement)
    assert not engine.complete
    assert engine.facts <= run(replacement, [atom("seed", a)]).facts
    engine = run(facts=[atom("p", a)])
    engine.max_facts = len(engine.facts) + 2
    many = [Rule(atom(f"q{i}", x), (atom("p", x),)) for i in range(12)]
    engine.update_rules(add=many)
    assert not engine.complete
    assert "max_facts" in engine.stats["limit_reason"]
    assert len(engine.facts) <= engine.max_facts
    assert engine.facts <= run(many, [atom("p", a)]).facts


def _independent_ground_closure(rules, facts):
    """Exhaustively ground ordinary positive Datalog, without engine helpers."""
    atoms = [*facts, *(item for rule in rules for item in (*rule.body, rule.head))]
    domain = {term for item in atoms for term in item.args if not isinstance(term, Var)}
    grounded = []
    for rule in rules:
        variables = sorted({term for item in (*rule.body, rule.head) for term in item.args
                            if isinstance(term, Var)}, key=lambda term: term.name)
        for values in product(domain, repeat=len(variables)):
            binding = dict(zip(variables, values))

            def ground(item):
                return Atom(item.predicate, tuple(binding.get(term, term) for term in item.args))

            grounded.append((ground(rule.head), {ground(item) for item in rule.body}))
    result = set(facts)
    while True:
        following = result | {head for head, body in grounded if body <= result}
        if following == result:
            return result
        result = following


@pytest.mark.parametrize("seed", [204163, 20260909, 41007])
@pytest.mark.parametrize("strategy", ["semi-naive", "naive"])
def test_seeded_mixed_updates_match_fresh_and_independent_closure(seed, strategy):
    rng = random.Random(seed)
    domain = [a, b, c]
    candidates = [
        Rule(atom("reach", x, y), (atom("edge", x, y),)),
        Rule(atom("reach", x, z), (atom("reach", x, y), atom("edge", y, z))),
        Rule(atom("reach", y, x), (atom("reach", x, y),)),
        Rule(atom("p", x), (atom("seed", x),), "owner-one"),
        Rule(atom("p", x), (atom("seed", x),), "owner-two"),
        Rule(atom("p", y), (atom("p", x), atom("reach", x, y))),
        Rule(atom("q", x), (atom("p", x),)),
        Rule(atom("p", x), (atom("q", x),)),
        Rule(atom("q", x), (atom("p", x), atom("seed", x))),
        Rule(atom("loop", x), (atom("reach", x, x),)),
        Rule(atom("p", a)),
        Rule(atom("flag"), (atom("q", a),)),
        Rule(atom("p", b), (atom("flag"),)),
    ]
    universe = ([atom("edge", s, o) for s in domain for o in domain]
                + [atom(predicate, s) for predicate in ("seed", "p", "q") for s in domain])
    rules, facts = set(rng.sample(candidates, 7)), set(rng.sample(universe, 7))
    engine = run(rules, facts, strategy=strategy)
    paths = set()
    for _ in range(45):
        additions = set(rng.sample(universe, rng.randrange(4)))
        removals = set(rng.sample(universe, rng.randrange(4)))
        add_rules = set(rng.sample(candidates, rng.randrange(4)))
        remove_rules = set(rng.sample(candidates, rng.randrange(4)))
        facts = (facts - removals) | additions
        rules = (rules - remove_rules) | add_rules
        engine.update(add=additions, remove=removals, add_rules=add_rules, remove_rules=remove_rules)
        paths.add(engine.stats["update_method"])
        fresh = run(rules, facts)
        assert engine.complete
        assert engine.facts == fresh.facts
        assert engine.terms == fresh.terms
        ordinary = {fact for fact in engine.facts if fact.predicate != TOP}
        assert ordinary == _independent_ground_closure(rules, facts)
    assert "dred-rules" in paths
    assert not any(path.startswith("rematerialize") for path in paths)


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
