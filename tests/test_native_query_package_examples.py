"""Worked ontology/query sources round-trip through the standalone C++ loader."""
import json
from pathlib import Path

import pytest
from rdflib import Graph, Literal, Namespace, URIRef, XSD

from dlp_reasoner import Reasoner
from dlp_reasoner.model import Atom, Program, Rule, Var
from dlp_reasoner.native_package import dumps_native, loads_native
from dlp_reasoner.packages import CompiledPackage, compile_package
from dlp_reasoner.query_parser import parse_query_program
from dlp_reasoner.query_runtime import QueryRuntime, QueryScope
from dlp_reasoner.scoped_views import BirthDateView


ROOT = Path(__file__).resolve().parents[1]
BACH = Namespace("http://www.jsbach.org/bach#")
BT = Namespace("https://example.org/bach-temporal#")
Q = Namespace("urn:dlp:query:")
HISTORY = Namespace("urn:dlp:history-query:")
EX = Namespace("urn:example:event:")


def test_actual_bach_package_with_explicit_selected_dates():
    directory = ROOT / "examples/bach_temporal"
    reasoner = Reasoner.from_file(directory / "bach-temporal.dlp", profile="L0")
    source = (directory / "queries.dlq").read_text()
    scope = QueryScope("urn:example:bach:accepted-exact-records-v1", "1")
    selection = BirthDateView(reasoner, child_property=BACH.hasChild,
                              birth_property=BT.birthDate, accepted_property=BT.acceptedBirthDate,
                              certificate_property=BT.validatedCompleteChildDates).prepare(scope)
    package = compile_package(reasoner.graph, profile="L0", queries=source,
                              context={"data_revision": scope.revision})
    with loads_native(dumps_native(package)) as native, QueryRuntime(source, reasoner=reasoner) as python:
        expected = python.evaluate(selection.relations, scope=scope)
        with native.prepare_query(parameters={"scope": URIRef(scope.name), "revision": Literal(scope.revision)},
                                  relations=selection.relations) as query:
            result = query.run()
            assert result == {predicate: expected.rows(predicate) for predicate in result}
            assert result[Q.fatherAtAgeKnown] == {(BACH["johann-sebastian"], Literal(23))}
            assert result[Q.motherAtAgeKnown] == {(BACH["maria-barbara"], Literal(24))}
            assert not result[Q.fatherAtAge] and not result[Q.motherAtAge]
            assert query.stats["domain_evaluations"] > 0
            assert query.run() == result  # Prepared native inputs remain resident.


def test_actual_bitemporal_package_at_both_time_axes():
    directory = ROOT / "examples/temporal_geo"
    fixture = json.loads((directory / "fixtures.json").read_text())
    source = (directory / "history.dlq").read_text()
    package = compile_package(Graph(), profile="L0", queries=source)
    relations = {HISTORY.closedVersion: set(), HISTORY.openVersion: set()}

    def instant(value):
        return Literal(value, datatype=XSD.dateTime, normalize=False)

    for version in fixture["speed_versions"]:
        row = (EX[version["id"]], EX[version["sign"]], Literal(version["kmh"]),
               *(instant(value) for value in version["valid"]), instant(version["recorded"][0]))
        if version["recorded"][1] is None:
            relations[HISTORY.openVersion].add(row)
        else:
            relations[HISTORY.closedVersion].add((*row, instant(version["recorded"][1])))
    with loads_native(dumps_native(package)) as native, QueryRuntime(source) as python:
        for index, case in enumerate(fixture["bitemporal_cases"]):
            inputs = {**relations, HISTORY.probe: {
                (instant(case["valid_at"]), instant(case["recorded_at"]))}}
            actual = native.query(relations=inputs)
            expected = python.evaluate(inputs, scope=QueryScope(EX.history, str(index)))
            assert actual == {predicate: expected.rows(predicate) for predicate in actual}
            assert sorted(int(row[1]) for row in actual[HISTORY.speed]) == case["kmh"]


@pytest.mark.parametrize("asserted", [False, True])
def test_authoring_checks_horn_relation_arities_including_empty_predicates(asserted):
    program = (Program(facts={Atom(EX.source, (EX.a,))}) if asserted else
               Program(rules=[Rule(Atom(EX.source, (Var("x"),)),
                                   (Atom(EX.absent, (Var("x"),)),))]))
    query = parse_query_program("""version 1 prefix ex: <urn:example:event:>
        ex:answer(?x, ?y) :- ex:source(?x, ?y).
    """)
    with pytest.raises(ValueError, match="arity mismatch"):
        dumps_native(CompiledPackage(program, query))
