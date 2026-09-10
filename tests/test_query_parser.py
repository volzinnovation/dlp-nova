"""Versioned extension syntax never changes the thesis ontology parser."""
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from rdflib import Literal, URIRef, XSD

from dlp_reasoner.domains import DomainRegistry
from dlp_reasoner.model import EQ, NEQ, Var
from dlp_reasoner.query_ir import (
    Aggregate, Bind, Filter, ProviderScan, QueryProgram, QueryRule,
    QueryValidationError, RelationAtom, plan,
)
from dlp_reasoner.query_parser import QueryParseError, parse_query_program


PREFIX = "version 1\nprefix ex: <urn:test:>\nprefix n: <urn:dlp:numeric:>\n"


def parse(body):
    return parse_query_program(PREFIX + body, source="test.rules")


def prepare(body, **kwargs):
    return plan(parse(body), DomainRegistry(), **kwargs)


class Registry:
    def __init__(self, **operations):
        self.operations = operations

    def get(self, uri):
        if uri.startswith("urn:test:"):
            return self.operations[uri.removeprefix("urn:test:")]
        return DomainRegistry().get(uri)


def operation(inputs, result="boolean", *, cardinality="one", **kwargs):
    return SimpleNamespace(arity=len(inputs), input_types=tuple(inputs), result_type=result,
                           required_positions=tuple(range(len(inputs))), cardinality=cardinality,
                           determinism="pure", **kwargs)


def test_explicit_version_and_namespaces_are_immutable():
    program = parse("query values(?x) :- ex:source(?x).")
    assert program.version == 1
    assert program.rules[0].head.predicate == URIRef("urn:dlp:query:values")
    assert program.rules[0].body[0].predicate == URIRef("urn:test:source")
    with pytest.raises(TypeError):
        program.namespaces["ex"] = "bad"


def test_terms_preserve_rdf_lexical_identity_and_comments():
    program = parse(r'''# comment
        ex:out(?x) :- /* block */ ex:source(?x, "001"^^xsd:integer,
          "line\nquote\"slash\\"@en-GB, -3, +0.25, .5, 6e2, true, <urn:a#x>). // tail
    ''')
    args = program.rules[0].body[0].args
    assert str(args[1]) == "001" and args[1].datatype == XSD.integer
    assert str(args[2]) == 'line\nquote"slash\\' and args[2].language == "en-GB"
    assert [v.datatype for v in args[3:8]] == [XSD.integer, XSD.decimal, XSD.decimal,
                                               XSD.double, XSD.boolean]
    assert args[8] == URIRef("urn:a#x")


def test_keywords_are_not_confused_with_variable_names():
    result = prepare("query q(?MIN, ?AS, ?filter) :- ex:p(?MIN, ?AS, ?filter).")
    assert result.rules[0].head.args == (Var("MIN"), Var("AS"), Var("filter"))


def test_zero_arity_relations_and_empty_program():
    assert prepare("q() :- ex:ready().").rules[0].head.args == ()
    result = plan(parse_query_program("version 1."), DomainRegistry())
    assert result.strata == () and result.rules == ()


@pytest.mark.parametrize("text", [
    "q() :- p().", "version 2", "version 1.0", "version +1", "version true",
    "version 1 prefix ex: <relative> q() :- p().",
    "version 1 prefix ex: <urn:a> prefix ex: <urn:a>",
    "version 1 prefix xsd: <urn:wrong>",
    "version 1 q() :- unknown:p().", "version 1 q() :- p(plain).",
    'version 1 q() :- p("unterminated).',
    'version 1 q() :- p("\\q").', 'version 1 q() :- p("\\ud800").',
    'version 1 q() :- p("line\nline").', 'version 1 q() :- p("x"@bad_1).',
    "version 1 /* unfinished", "version 1 q() :- p(<urn:bad space>).",
    "version 1 q() :- p(<urn:no-end).", "version 1 q() :- p(?).",
    "version 1 q() :- p(1,).", "version 1 q() :- .", "version 1 q() :- p()",
    "version 1 q() given (?x, ?x) :- p().",
    "version 1 q() :- bind add(1, 2) as ?x.",
    "version 1 q() :- scan <urn:scan>() as ().",
])
def test_malformed_programs_have_source_diagnostics(text):
    with pytest.raises(QueryParseError) as exc:
        parse_query_program(text, source="bad.rules")
    assert str(exc.value).startswith("bad.rules:")
    assert exc.value.location.line >= 1 and exc.value.location.column >= 1


def test_source_line_and_column():
    with pytest.raises(QueryParseError) as exc:
        parse_query_program("version 1\n\nq() :- missing:p().", source="location.rules")
    assert (exc.value.location.line, exc.value.location.column) == (3, 8)


def test_bind_is_reordered_after_required_relations_and_filter_after_bind():
    result = prepare("""q(?x, ?sum) :- filter n:greaterThan(?sum, 2),
        bind n:add(?a, 1) as ?sum, ex:value(?x, ?a).""")
    assert [type(n) for n in result.rules[0].body] == [RelationAtom, Bind, Filter]
    assert json.loads(json.dumps(result.explain()))["strata"][-1]["rules"][0]["head"]


def test_filter_pushes_before_unrelated_ready_relation():
    result = prepare("q(?x) :- ex:p(?x, ?n), ex:other(?x), filter n:greaterThan(?n, 2).")
    assert [type(n) for n in result.rules[0].body] == [RelationAtom, Filter, RelationAtom]


def test_given_parameters_seed_binding_and_propagate_to_callers():
    result = prepare("""q(?sum) given (?n) :- bind n:add(?n, 1) as ?sum.
        answer(?sum) given (?n) :- q(?sum).""")
    assert result.rules[0].given == (Var("n"),)
    with pytest.raises(QueryValidationError, match="requires given"):
        prepare("q(?x) given (?n) :- ex:p(?x). a(?x) :- q(?x).")
    with pytest.raises(QueryValidationError, match="identical given"):
        prepare("q(?x) given (?n) :- ex:p(?x). q(?x) :- ex:q(?x).")


@pytest.mark.parametrize("body, message", [
    ("q(?x) :- ex:p(?y).", "Unsafe head"),
    ("q(?x) :- bind n:add(?n, 1) as ?x.", "unbound operation"),
    ("q() :- filter n:greaterThan(?n, 1).", "unbound operation"),
    ("q(?x) :- ex:p(?x), ex:p(?x, ?y).", "arity mismatch"),
    ("q(?x) :- ex:p(?x), bind n:add(1) as ?y.", "arity mismatch"),
    ("q() :- filter n:add(1, 2).", "must return a Boolean"),
    ("q() :- filter ex:unknown(1).", "Unavailable operation"),
    ('q(?x) :- bind n:add("not numeric", 1) as ?x.', "expects numeric"),
    ('q() :- bind n:add(1, 2) as "wrong".', "conflicts with string"),
    ("q(?x) :- bind n:add(1, 2) as ?x, filter <urn:dlp:temporal:before>(?x, ?x).",
     "expects temporal"),
])
def test_invalid_binding_arity_and_type_programs(body, message):
    with pytest.raises(QueryValidationError, match=message):
        prepare(body)


def test_extensional_arity_constraints_are_checked():
    with pytest.raises(QueryValidationError, match="arity mismatch"):
        prepare("q(?x) :- ex:p(?x).", relation_arities={URIRef("urn:test:p"): 2})


def test_unknown_custom_datatypes_defer_to_runtime_validation():
    result = prepare('q(?x) :- bind n:add("x"^^ex:unknownDatatype, 1) as ?x.')
    assert result.rules


def test_aggregate_only_exports_group_and_output_with_strict_stratum():
    result = prepare("""q(?p, ?minimum) :-
        MIN ?v GROUP_BY ?p FROM ex:source(?p, ?child, ?v) AS ?minimum.""")
    assert isinstance(result.rules[0].body[0], Aggregate)
    assert result.predicate_strata[URIRef("urn:dlp:query:q")] == 1
    assert result.predicate_strata[URIRef("urn:test:source")] == 0
    with pytest.raises(QueryValidationError, match="Unsafe head"):
        prepare("q(?child) :- MIN ?v GROUP_BY ?p FROM ex:s(?p, ?child, ?v) AS ?m.")


def test_global_min_and_multiple_group_variables():
    global_min = prepare("q(?m) :- MIN ?v GROUP_BY () FROM ex:s(?v) AS ?m.")
    assert global_min.rules[0].body[0].group_by == ()
    for group in ["?a, ?b", "(?a, ?b)"]:
        result = prepare(f"q(?a, ?b, ?m) :- MIN ?v GROUP_BY {group} FROM ex:s(?a, ?b, ?v) AS ?m.")
        assert result.rules[0].body[0].group_by == (Var("a"), Var("b"))


def test_aggregate_can_restrict_given_snapshot_but_not_accidental_correlated_var():
    assert prepare("""q(?m) given (?snapshot) :-
        MIN ?v GROUP_BY () FROM ex:s(?snapshot, ?v) AS ?m.""").rules
    with pytest.raises(QueryValidationError, match="correlated aggregate"):
        prepare("""q(?m) :- ex:fixed(?child),
            MIN ?v GROUP_BY () FROM ex:s(?child, ?v) AS ?m.""")


@pytest.mark.parametrize("body, message", [
    ("q(?m) :- MIN ?v GROUP_BY ?absent FROM ex:s(?v) AS ?m.", "must occur"),
    ("q(?m) :- MIN ?absent GROUP_BY () FROM ex:s(?v) AS ?m.", "must occur"),
    ("q(?v) :- MIN ?v GROUP_BY () FROM ex:s(?v) AS ?v.", "distinct from source"),
    ("q(?m) :- MIN ?v GROUP_BY (?x, ?x) FROM ex:s(?x, ?v) AS ?m.", "distinct group"),
])
def test_aggregate_invalid_variables(body, message):
    with pytest.raises(QueryValidationError, match=message):
        prepare(body)


def test_pure_recursive_relations_and_filters_are_legal():
    result = prepare("""q(?a, ?b) :- ex:edge(?a, ?b).
        q(?a, ?c) :- q(?a, ?b), ex:edge(?b, ?c), filter n:greaterThan(2, 1).""")
    assert result.recursive_predicates == {URIRef("urn:dlp:query:q")}
    assert len(result.strata) == 1


@pytest.mark.parametrize("body", [
    "q(?b) :- q(?a), bind n:add(?a, 1) as ?b.",
    "q(?m) :- MIN ?v GROUP_BY () FROM q(?v) AS ?m.",
    "q(?x) :- p(?x). p(?b) :- q(?a), bind n:add(?a, 1) as ?b.",
])
def test_aggregate_and_generation_cycles_are_rejected(body):
    with pytest.raises(QueryValidationError, match="Dependency cycle"):
        prepare(body)


def test_scan_descriptor_multiple_outputs_and_cycle():
    registry = Registry(scan=operation(("integer",), "iri", cardinality="many",
                                       output_types=("iri", "integer")))
    result = plan(parse("q(?x, ?n) :- scan ex:scan(1) as (?x, ?n)."), registry)
    assert isinstance(result.rules[0].body[0], ProviderScan)
    with pytest.raises(QueryValidationError, match="output arity"):
        plan(parse("q(?x) :- scan ex:scan(1) as ?x."), registry)
    with pytest.raises(QueryValidationError, match="Dependency cycle"):
        plan(parse("q(?x, ?n) :- q(?old, ?n), scan ex:scan(?n) as (?x, ?new)."), registry)


def test_scan_and_scalar_cardinalities_cannot_be_interchanged():
    registry = Registry(scan=operation((), "iri", cardinality="many"))
    with pytest.raises(QueryValidationError, match="non-scalar cardinality"):
        plan(parse("q(?x) :- bind ex:scan() as ?x."), registry)
    with pytest.raises(QueryValidationError, match="many-row"):
        prepare("q(?x) :- scan n:add(1, 2) as ?x.")


def test_nonpure_filters_cannot_participate_in_recursion():
    descriptor = operation(())
    descriptor.determinism = "snapshot"
    with pytest.raises(QueryValidationError, match="non-pure filter"):
        plan(parse("q(?x) :- q(?x), filter ex:state()."), Registry(state=descriptor))


def test_equality_bindings_and_inequality_required_bindings():
    x = Var("x")
    eq = RelationAtom(EQ, (x, Literal(1)))
    neq = RelationAtom(NEQ, (x, Literal(2)))
    head = RelationAtom(URIRef("urn:q"), (x,))
    result = plan(QueryProgram((QueryRule(head, (neq, eq)),)), DomainRegistry())
    assert result.rules[0].body == (eq, neq)
    with pytest.raises(QueryValidationError, match="unbound"):
        plan(QueryProgram((QueryRule(head, (RelationAtom(EQ, (x, Var("y"))),)),)), DomainRegistry())
    with pytest.raises(QueryValidationError, match="cannot be query-rule heads"):
        plan(QueryProgram((QueryRule(eq, (eq,)),)), DomainRegistry())


def test_manual_ir_invalid_nodes_and_versions_fail_explicitly():
    program = parse("q(?x) :- ex:p(?x).")
    for version in [True, 2, "1"]:
        with pytest.raises(QueryValidationError, match="version 1"):
            plan(replace(program, version=version), DomainRegistry())
    rule = program.rules[0]
    with pytest.raises(QueryValidationError, match="Unsupported query body node"):
        plan(replace(program, rules=(replace(rule, body=(object(),)),)), DomainRegistry())
    with pytest.raises(QueryValidationError, match="RDF IRI/literal"):
        plan(replace(program, rules=(replace(rule, head=RelationAtom(rule.head.predicate, (4,))),)),
             DomainRegistry())


def test_existing_bach_proposed_rules_parse_and_stratify_without_execution():
    path = Path(__file__).resolve().parents[1] / "examples/bach_temporal/queries.rules.proposed"
    result = plan(parse_query_program("version 1\n" + path.read_text(), source=str(path)),
                  DomainRegistry())
    assert len(result.rules) == 8
    assert sorted(map(len, result.strata)) == [1, 3, 4]
    assert not result.recursive_predicates


def test_existing_traffic_proposal_parses_but_requires_registered_providers():
    path = Path(__file__).resolve().parents[1] / "examples/traffic_signs/queries.rules.proposed"
    program = parse_query_program("version 1\n" + path.read_text(), source=str(path))
    assert len(program.rules) == 8
    with pytest.raises(QueryValidationError, match="Unavailable operation"):
        plan(program, DomainRegistry())
