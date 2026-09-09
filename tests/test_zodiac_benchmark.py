"""Semantic safeguards for the frozen author-rule benchmark adapter."""
import json
from pathlib import Path
import sys

import pytest
from rdflib import Graph, Literal, OWL, RDF, URIRef

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmarks import zodiac  # noqa: E402
from benchmarks.lubm import digest_rows, term_record  # noqa: E402
from benchmarks.research import finite_oracle  # noqa: E402
from dlp_reasoner.model import Atom, Program  # noqa: E402


def test_positive_parser_preserves_shared_variables_and_transaction_overlap():
    text = """| * | # | rule |
| * | # |\\<p>(?X, ?Z) :- \\<p>(?X, ?Y) and \\<p>(?Y, ?Z) . |
| | |\\<p>(?X, ?Y) :- \\<src_p>(?X, ?Y) . |
"""
    rules, groups = zodiac.parse_marked_program(text, expected=(2, 1, 1))
    assert groups["*"] == groups["#"] == rules[:1]
    facts = {Atom("src_p", ("a", "b")), Atom("src_p", ("b", "c"))}
    result = finite_oracle(Program(rules, facts))
    assert Atom("p", ("a", "c")) in result
    assert Atom("p", ("c", "a")) not in result


@pytest.mark.parametrize("text", [
    "<p>(?X) :- not <q>(?X) .", "<p>(?X) :- <q>(?X) and COMP(?X, !=, ?Y) .",
    "<p>(?X) :- aggregate(<q>(?X)) .", "<p>(?X) :- <q>(<constant>) .",
    "<p>(?X) :- <q>(?Y) .", "<p>(?X) :- <q>(?X)",
])
def test_parser_rejects_unsupported_or_unsafe_author_rules(text):
    with pytest.raises(RuntimeError):
        zodiac.parse_rule(text)


def test_parser_cannot_silently_drop_or_duplicate_rules():
    row = "| * | |<p>(?X) :- <src_p>(?X) . |"
    with pytest.raises(RuntimeError, match="counts"):
        zodiac.parse_marked_program(row)
    with pytest.raises(RuntimeError, match="duplicate"):
        zodiac.parse_marked_program(row + "\n" + row, expected=(2, 2, 0))
    with pytest.raises(RuntimeError, match="marker"):
        zodiac.parse_marked_program(row.replace(" * ", " ! "), expected=(1, 1, 0))


def test_abox_encoding_retains_literal_identity_and_only_removes_document_metadata():
    namespace = zodiac.ONTOLOGY + "#"
    rules = [zodiac.parse_rule("<Person>(?X) :- <src_Person>(?X) ."),
             zodiac.parse_rule("<name>(?X, ?Y) :- <src_name>(?X, ?Y) .")]
    person, document = URIRef("urn:person"), URIRef("urn:document")
    name = Literal("Ada", lang="en")
    graph = Graph()
    for triple in [(person, RDF.type, URIRef(namespace + "Person")),
                   (person, URIRef(namespace + "name"), name),
                   (document, RDF.type, OWL.Ontology),
                   (document, OWL.imports, URIRef(zodiac.ONTOLOGY))]:
        graph.add(triple)
    facts, metadata = zodiac.encode_assertions(graph, rules)
    assert facts == {Atom("src_Person", (person,)), Atom("src_name", (person, name))}
    assert metadata == {"ontology_declarations": 1, "imports": 1}
    graph.add((person, URIRef(namespace + "unsupportedProperty"), name))
    with pytest.raises(RuntimeError, match="do not cover"):
        zodiac.encode_assertions(graph, rules)


def test_supplemental_fact_samples_are_deterministic_and_use_distinct_seeds():
    facts = {Atom("p", (URIRef(f"urn:{i}"),)) for i in range(30)}
    first = zodiac.fact_subsets(facts, 10, size=4)
    assert first == zodiac.fact_subsets(set(reversed(list(facts))), 10, size=4)
    assert len({frozenset(sample) for _, sample in first}) == 10
    assert [seed for seed, _ in first] == list(range(9100, 9110))
    assert all(len(sample) == 4 and sample <= facts for _, sample in first)


@pytest.mark.parametrize("configuration", zodiac.CONFIGURATIONS)
def test_all_configurations_restore_exact_closures_after_recursive_rule_updates(
        monkeypatch, tmp_path, configuration):
    rules = [zodiac.parse_rule(text) for text in (
        "<Source>(?X) :- <src_Source>(?X) .",
        "<Seen>(?X) :- <Source>(?X) .",
        "<Loop>(?X) :- <Seen>(?X) .",
        "<Seen>(?X) :- <Loop>(?X) .",
        "<Seen>(?X) :- <Alt>(?X) .",
        "<Tail>(?X) :- <Seen>(?X) .")]
    groups = {"*": [rules[1]], "#": [rules[4]]}
    facts = {Atom("src_Source", (URIRef("urn:a"),)), Atom("Alt", (URIRef("urn:b"),))}
    monkeypatch.setattr(zodiac, "load_program", lambda *_: (rules, groups, facts, {}))
    references = {}
    for key, removed in [("full", [])] + list(groups.items()):
        closure = finite_oracle(Program([rule for rule in rules if rule not in removed], facts))
        references[key] = {"facts": len(closure), "sha256": digest_rows([
            [term_record(f.predicate), [term_record(a) for a in f.args]] for f in closure])}
    result = zodiac.worker(tmp_path, tmp_path, configuration, references, fact_samples=0)
    assert result["all_complete_tuple_digests_match_naive"]
    for key in groups:
        assert result["transactions"][key]["initial"] == result["transactions"][key]["delete"]
        assert result["transactions"][key]["insert"] == references["full"]
    # An equal-count, wrong-tuple reference must fail rather than pass on counts.
    wrong = json.loads(json.dumps(references))
    wrong["*"]["sha256"] = "0" * 64
    with pytest.raises(RuntimeError, match="closure differs"):
        zodiac.worker(tmp_path, tmp_path, configuration, wrong, fact_samples=0)
