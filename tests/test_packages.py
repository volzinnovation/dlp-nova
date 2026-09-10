"""Portable compiled packages preserve semantics and reject incompatible state."""
import hashlib
import json
from pathlib import Path

import pytest
from rdflib import Graph, Literal, Namespace
from rdflib.compare import isomorphic
from rdflib.namespace import RDFS, XSD

from dlp_reasoner import parse_dlp
from dlp_reasoner.packages import PackageError, compile_package, dumps, loads, _HEADER, _MAGIC
from dlp_reasoner.query_runtime import QueryRuntime, QueryScope


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("backend", ["python", "native"])
@pytest.mark.parametrize("name,profile", [("family", "L2"), ("existential", "L3"),
                                         ("bach", "L3"), ("inconsistent", "L2")])
def test_compiled_package_round_trip(name, profile, backend):
    graph = parse_dlp((ROOT / "examples" / (name + ".dlp")).read_text())
    graph.add((Namespace("urn:test:").subject, RDFS.label, Literal("sprachlich", lang="de")))
    package = compile_package(graph, profile=profile, context={"data_revision": "test-v1"})
    restored = loads(dumps(package))
    assert restored.program == package.program
    assert isomorphic(graph, restored.source_graph())
    assert dumps(restored) == dumps(package)
    before, after = package.engine(backend=backend), restored.engine(backend=backend)
    assert before.facts == after.facts
    assert before.complete == after.complete
    assert before.violations == after.violations


def test_query_ir_and_literal_lexical_form_roundtrip():
    graph = Graph()
    lexical = Literal("001", datatype=XSD.integer, normalize=False)
    graph.add((Namespace("urn:test:").subject, Namespace("urn:test:").number, lexical))
    source = """version 1
    prefix ex: <urn:test:>
    prefix num: <urn:dlp:numeric:>
    ex:answer(?x) :- ex:input(?n), bind num:add(?n, 1) as ?x.
    """
    restored = loads(dumps(compile_package(graph, queries=source)))
    assert lexical in set(restored.source_graph().objects())
    with QueryRuntime(restored.query_program) as runtime:
        result = runtime.evaluate({"urn:test:input": {(Literal(2),)}},
                                  scope=QueryScope("urn:test:scope", "1"))
        assert result.rows("urn:test:answer") == {(Literal(3),)}


def test_query_arity_is_checked_against_ontology_when_authoring_and_loading():
    ex = Namespace("urn:test:")
    graph = Graph()
    graph.add((ex.a, ex.property, ex.b))
    with pytest.raises(ValueError, match="arity mismatch"):
        compile_package(graph, queries="version 1 <urn:test:answer>(?x) :- <urn:test:property>(?x).")
    valid = dumps(compile_package(graph, queries=(
        "version 1 <urn:test:answer>(?x) :- <urn:test:property>(?x, ?y).")))
    with pytest.raises(PackageError, match="arity mismatch"):
        loads(rewrite(valid, lambda body: body["query"]["rules"][0][1][0][1][1].pop()))


def rewrite(data, change):
    body = json.loads(data[_HEADER.size:])
    change(body)
    payload = json.dumps(body, sort_keys=True, ensure_ascii=True, allow_nan=False,
                         separators=(",", ":")).encode()
    return _HEADER.pack(_MAGIC, len(payload), hashlib.sha256(payload).digest()) + payload


def test_truncated_corrupted_unknown_and_oversized_packages_rejected():
    original = dumps(compile_package(Graph()))
    for position in (0, 1, 10, _HEADER.size - 1, _HEADER.size, len(original) - 1):
        with pytest.raises(PackageError):
            loads(original[:position])
    with pytest.raises(PackageError):
        loads(original + b"trailing")
    with pytest.raises(PackageError):
        loads(original[:-1] + b"X")
    with pytest.raises(PackageError):
        loads(original, max_bytes=1)
    for field, value in (("version", 2), ("profile", "OWL-FULL"), ("domain_profile", "other"),
                         ("requirements", [["urn:unavailable:op", "1"]])):
        with pytest.raises(PackageError):
            loads(rewrite(original, lambda body: body.update({field: value})))


def test_reject_invalid_ir_and_missing_operation_requirements():
    source = """version 1
    prefix ex: <urn:test:>
    prefix num: <urn:dlp:numeric:>
    ex:answer(?x) :- ex:input(?n), bind num:add(?n, 1) as ?x.
    """
    original = dumps(compile_package(Graph(), queries=source))
    with pytest.raises(PackageError, match="undeclared"):
        loads(rewrite(original, lambda body: body.update(requirements=[])))
    with pytest.raises(PackageError, match="version"):
        loads(rewrite(original, lambda body: body["requirements"][0].__setitem__(1, "999")))
    with pytest.raises(PackageError):
        loads(rewrite(original, lambda body: body.update(facts=[[["iri", "urn:p"], [["var", "x"]]]])))
