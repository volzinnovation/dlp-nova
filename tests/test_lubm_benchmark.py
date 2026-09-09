"""Safety/semantic checks for the external LUBM adapter; no network needed."""
import json
import zipfile

import pytest
from rdflib import RDF, URIRef
from rdflib.plugins.sparql import prepareQuery

from benchmarks.lubm import (
    ONTOLOGY, OLD_NAMESPACE, digest_rows, normalized_queries, read_answers, validate_inputs,
)


def test_published_punctuation_repair_preserves_basic_graph_pattern():
    query = f'''PREFIX rdf: <{RDF}>
PREFIX ub: <{OLD_NAMESPACE}>
SELECT ?X, ?Y
WHERE {{?X rdf:type ub:Student .
?X ub:takesCourse http://www.Department0.University0.edu/GraduateCourse0 .
<http://www.Department0.University0.edu/Professor0>, ub:teacherOf, ?Y}}'''
    raw = "\n".join(f"# Query{i}\n{query}" for i in range(1, 15))
    parsed = normalized_queries(raw)
    for q in parsed.values():
        algebra = prepareQuery(q).algebra
        assert [str(v) for v in algebra.PV] == ["X", "Y"]
        triples = algebra.p.p.triples
        assert len(triples) == 3
        assert {t[1] for t in triples} == {
            RDF.type, URIRef(ONTOLOGY + "#takesCourse"), URIRef(ONTOLOGY + "#teacherOf")}
        assert any(t[2] == URIRef(
            "http://www.Department0.University0.edu/GraduateCourse0") for t in triples)


def test_missing_official_query_block_is_rejected():
    with pytest.raises(RuntimeError, match="precisely 14"):
        normalized_queries("# Query1\nSELECT ?X WHERE {?X ?P ?Y}")


def write_answers(path, change=None):
    with zipfile.ZipFile(path, "w") as archive:
        for number in range(1, 15):
            data = "NO ANSWERS.\n" if number == 2 else "X\nurn:a\nurn:b\n"
            if number == 1 and change:
                data = change
            archive.writestr(f"answers_query{number}.txt", data)


def test_official_empty_answer_marker_and_exact_tuples(tmp_path):
    path = tmp_path / "answers.zip"
    write_answers(path)
    answers = read_answers(path)
    assert answers[2] == ((), set())
    assert answers[1] == (("X",), {("urn:a",), ("urn:b",)})
    # Same cardinality alone is not sufficient to pass the closure/answer digest.
    assert digest_rows(answers[1][1]) != digest_rows({("urn:a",), ("urn:c",)})


@pytest.mark.parametrize("payload", ["X\nurn:a\nurn:a\n", "X Y\nurn:a\n"])
def test_invalid_reference_answer_files_fail(tmp_path, payload):
    path = tmp_path / "answers.zip"
    write_answers(path, payload)
    with pytest.raises(RuntimeError):
        read_answers(path)


def test_tampered_inputs_fail_before_measurement(tmp_path):
    (tmp_path / "ontology.owl").write_text("altered input")
    manifest = {"artifacts": {"ontology.owl": {"sha256": "0" * 64}},
                "department_files": {}}
    # JSON round trip matches the persisted manifest contract.
    with pytest.raises(RuntimeError, match="input changed"):
        validate_inputs(tmp_path, json.loads(json.dumps(manifest)))


def test_native_bgp_adapter_matches_join_and_excludes_witness_bindings():
    from dlp_reasoner.engine import Engine
    from dlp_reasoner.model import Atom, Program, Skolem
    from benchmarks.lubm import prepare_native_query, native_answers
    student = URIRef(ONTOLOGY + "#Student")
    course = URIRef(ONTOLOGY + "#Course")
    takes = URIRef(ONTOLOGY + "#takesCourse")
    x, y, other = URIRef("urn:x"), URIRef("urn:y"), URIRef("urn:other")
    witness = Skolem("urn:w", (x,))
    engine = Engine(Program([], {
        Atom(student, (x,)), Atom(course, (y,)), Atom(takes, (x, y)),
        Atom(course, (witness,)), Atom(takes, (x, witness)), Atom(takes, (other, y)),
    })).materialize()
    variables, rule = prepare_native_query(f'''PREFIX ub: <{ONTOLOGY}#>
SELECT ?X ?Y WHERE {{?X a ub:Student . ?Y a ub:Course . ?X ub:takesCourse ?Y}}''')
    before = engine.facts.copy()
    assert native_answers(engine, variables, rule) == {("urn:x", "urn:y")}
    assert engine.facts == before


@pytest.mark.parametrize("query", [
    "SELECT ?X WHERE {?X ?P ?Y}",
    "SELECT ?X WHERE {?X a ?Y}",
    "SELECT ?X WHERE {{?X <urn:p> ?Y} UNION {?X <urn:q> ?Y}}",
])
def test_native_adapter_rejects_unhandled_sparql(query):
    from benchmarks.lubm import prepare_native_query
    with pytest.raises(RuntimeError):
        prepare_native_query(query)
