"""Native-engine bridge tests; optional upstream code stays outside the repository."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from rdflib import BNode, Literal, URIRef
from rdflib.namespace import XSD

from benchmarks.research import finite_oracle
from benchmarks.zodiac import parse_marked_program
from benchmarks.zodiac_native import (encode_constant, native_api, native_closure,
                                       rule_text, translated_input, tuple_record)
from dlp_reasoner.model import Atom, Program, Rule, Var

ROOT = Path(__file__).resolve().parents[1]
X, Y, Z = (Var(name) for name in "xyz")


def atom(predicate, *values):
    return Atom(predicate, values)


def test_constant_encoding_preserves_rdf_term_identity():
    values = [URIRef("value"), BNode("value"), Literal("value"),
              Literal("value", datatype=XSD.string), Literal("value", lang="en"),
              Literal("value", lang="fr"), Literal("01", datatype=XSD.integer, normalize=False),
              Literal("1", datatype=XSD.integer, normalize=False)]
    assert len({encode_constant(value) for value in values}) == len(values)
    assert encode_constant(Literal("é\n<>")) == encode_constant(Literal("é\n<>"))


def test_rule_text_restricts_the_native_contract():
    assert rule_text(Rule(atom("q", X), (atom("p", X, Y),))) == "<q>(?x) :- <p>(?x, ?y) ."
    with pytest.raises(RuntimeError):
        rule_text(Rule(atom("q", "constant"), (atom("p", X),)))


@pytest.fixture
def api():
    cache = ROOT / "tmp/zodiac-native"
    if not (cache / "manifest.json").exists():
        pytest.skip("run python -m benchmarks.zodiac_native --prepare for optional upstream tests")
    return native_api(cache)


def test_actual_author_rule_parser_retains_all_128_rules(api):
    text = (ROOT / "tmp/zodiac-native/upstream/README.md").read_text()
    rules, groups = parse_marked_program(text)
    translated, facts, _, _ = translated_input(api, rules, set())
    assert len(set(translated.values())) == 128
    assert {name: len({translated[r] for r in selected}) for name, selected in groups.items()} == {
        "*": 8, "#": 16}
    assert not facts


def test_native_input_and_output_conversion_preserve_exact_facts(api):
    rules = [Rule(atom("p", X), (atom("src_p", X),)),
             Rule(atom("edge", X, Y), (atom("src_edge", X, Y),))]
    facts = {atom("src_p", URIRef("same")), atom("src_p", Literal("same")),
             atom("src_edge", BNode("same"), Literal("same", lang="en"))}
    _, native_facts, constants, arities = translated_input(api, rules, facts)
    data = api["DataStore"]()
    for triple in native_facts:
        data.add(*triple)
    program = SimpleNamespace(edb=data, idb=api["DataStore"]())
    assert native_closure(program, constants, arities) == facts
    assert tuple_record(native_closure(program, constants, arities)) == tuple_record(facts)


def test_unmodified_native_program_rule_updates_match_independent_oracle(api):
    rules = [Rule(atom("p", X), (atom("src_p", X),)),
             Rule(atom("edge", X, Y), (atom("src_edge", X, Y),)),
             Rule(atom("reach", X, Y), (atom("edge", X, Y),)),
             Rule(atom("reach", X, Z), (atom("reach", X, Y), atom("edge", Y, Z))),
             Rule(atom("p", Y), (atom("p", X), atom("reach", X, Y)))]
    facts = {atom("src_p", URIRef("a")), atom("src_edge", URIRef("a"), URIRef("b")),
             atom("src_edge", URIRef("b"), URIRef("c"))}
    native, native_facts, constants, arities = translated_input(api, rules, facts)
    data = api["DataStore"]()
    for triple in native_facts:
        data.add(*triple)
    partial, changed = rules[:3], rules[3:]
    engine = api["Program"](data=data, rules={native[r] for r in partial})
    assert native_closure(engine, constants, arities) == finite_oracle(Program(partial, facts))
    engine.add_rules({native[r] for r in changed})
    assert native_closure(engine, constants, arities) == finite_oracle(Program(rules, facts))
    engine.delete_rules({native[r] for r in changed})
    assert native_closure(engine, constants, arities) == finite_oracle(Program(partial, facts))
