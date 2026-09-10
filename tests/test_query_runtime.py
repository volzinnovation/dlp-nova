"""Actual extension rule execution, independent of example reference oracles."""
from pathlib import Path

import pytest
from rdflib import Graph, Literal, Namespace, RDF
from rdflib.namespace import OWL, XSD

from dlp_reasoner import Reasoner
from dlp_reasoner.domains import DomainError
from dlp_reasoner.query_runtime import QueryRuntime, QueryScope
from dlp_reasoner.scoped_views import BirthDateView, CompletenessCertificate


ROOT = Path(__file__).resolve().parents[1]
BACH = Namespace("http://www.jsbach.org/bach#")
BT = Namespace("https://example.org/bach-temporal#")
Q = Namespace("urn:dlp:query:")
EX = Namespace("urn:test:family:")
SCOPE = QueryScope("urn:test:scope", "1")
SOURCE = (ROOT / "examples/bach_temporal/queries.dlq").read_text()


def date(text):
    return Literal(text, datatype=XSD.date, normalize=False)


def view(reasoner):
    return BirthDateView(reasoner, child_property=BACH.hasChild, birth_property=BT.birthDate,
                         accepted_property=BT.acceptedBirthDate,
                         certificate_property=BT.validatedCompleteChildDates,
                         trusted_issuers={"test-fixture"})


def evaluate(runtime, selection, scope=SCOPE, certificates=()):
    selected = selection.prepare(scope, certificates=certificates)
    return runtime.evaluate(selected.relations, scope=scope,
                            diagnostics=selected.diagnostics, metadata=selected.metadata)


@pytest.mark.parametrize("backend", ["python", "native"])
def test_historical_bach_rules_execute_with_scoped_minimum(backend):
    reasoner = Reasoner.from_file(ROOT / "examples/bach_temporal/bach-temporal.dlp",
                                  profile="L0", backend=backend)
    with QueryRuntime(SOURCE, reasoner=reasoner, backend=backend) as runtime:
        result = evaluate(runtime, view(reasoner))
        assert result.rows(Q.fatherAtAgeKnown) == {(BACH["johann-sebastian"], Literal(23))}
        assert result.rows(Q.motherAtAgeKnown) == {(BACH["maria-barbara"], Literal(24))}
        assert not result.rows(Q.fatherAtAge)
        assert not result.rows(Q.motherAtAge)
        assert len(result.rows(Q.firstKnownChild)) == 2
        assert not result.metadata["family_history_complete"]
        assert any(d.subject == BACH["anna-magdalena"] and d.code == "missing_date"
                   for d in result.diagnostics)
        again = evaluate(runtime, view(reasoner))
        assert runtime.cache_hits == 1
        assert not again.additions and not again.retractions


def family(backend):
    graph = Graph()
    for triple in (
        (EX.father, RDF.type, BACH.Father), (EX.mother, RDF.type, BACH.Mother),
        (EX.father, BT.birthDate, date("1980-02-29")),
        (EX.mother, BT.birthDate, date("1982-02-28")),
        (EX.first, BT.birthDate, date("2000-03-01")),
        (EX.later, BT.birthDate, date("2002-01-01")),
        (EX.father, BACH.hasChild, EX.first), (EX.father, BACH.hasChild, EX.later),
        (EX.mother, BACH.hasChild, EX.first),
    ):
        graph.add(triple)
    return Reasoner(graph, backend=backend)


@pytest.mark.parametrize("backend", ["python", "native"])
def test_minimum_ties_conflicts_corrections_and_certificates(backend):
    reasoner = family(backend)
    selection = view(reasoner)
    with QueryRuntime(SOURCE, reasoner=reasoner, backend=backend) as runtime:
        cert = CompletenessCertificate(EX.father, SCOPE, selection.evidence_digest(EX.father),
                                       "test-fixture")
        first = evaluate(runtime, selection, certificates=[cert])
        assert first.rows(Q.fatherAtAge) == {(EX.father, Literal(20))}
        assert first.rows(Q.motherAtAgeKnown) == {(EX.mother, Literal(18))}

        # A twin preserves the minimum/age and contributes a separate child.
        reasoner.update(add=[(EX.father, BACH.hasChild, EX.twin),
                             (EX.twin, BT.birthDate, date("2000-03-01"))])
        twins = evaluate(runtime, selection, certificates=[cert])
        assert len([r for r in twins.rows(Q.firstKnownChild) if r[0] == EX.father]) == 2
        assert not twins.rows(Q.fatherAtAge)
        assert (EX.father, Literal(20)) in twins.retractions[Q.fatherAtAge]
        assert any(d.code == "stale_certificate" for d in twins.diagnostics)

        # An earlier child retracts the old minimum; removing it exposes twins.
        earlier = [(EX.father, BACH.hasChild, EX.earlier),
                   (EX.earlier, BT.birthDate, date("1999-02-28"))]
        reasoner.update(add=earlier)
        changed = evaluate(runtime, selection)
        assert changed.rows(Q.fatherAtAgeKnown) == {(EX.father, Literal(18))}
        assert (EX.father, Literal(20)) in changed.retractions[Q.fatherAtAgeKnown]
        reasoner.update(remove=earlier)
        assert evaluate(runtime, selection).rows(Q.fatherAtAgeKnown) == {(EX.father, Literal(20))}

        # A conflicting date retracts the accepted record, even when later.
        conflict = (EX.first, BT.birthDate, date("2005-01-01"))
        reasoner.update(add=[conflict])
        conflict_result = evaluate(runtime, selection)
        assert (EX.father, EX.first, date("2000-03-01")) not in conflict_result.rows(Q.firstKnownChild)
        assert (EX.father, EX.twin, date("2000-03-01")) in conflict_result.rows(Q.firstKnownChild)
        assert any(d.subject == EX.first and d.code == "conflicting_dates"
                   for d in conflict_result.diagnostics)
        reasoner.update(remove=[conflict, (EX.father, BACH.hasChild, EX.twin),
                                (EX.father, BACH.hasChild, EX.first)])
        assert evaluate(runtime, selection).rows(Q.fatherAtAgeKnown) == {(EX.father, Literal(21))}

        # Parent correction affects age independently of the child minimum.
        reasoner.update(remove=[(EX.father, BT.birthDate, date("1980-02-29"))],
                        add=[(EX.father, BT.birthDate, date("1981-03-01"))])
        assert evaluate(runtime, selection).rows(Q.fatherAtAgeKnown) == {(EX.father, Literal(20))}


@pytest.mark.parametrize("backend", ["python", "native"])
def test_date_selection_rebuilds_on_equality_merge_and_split(backend):
    reasoner = family(backend)
    selection = view(reasoner)
    with QueryRuntime(SOURCE, reasoner=reasoner, backend=backend) as runtime:
        assert evaluate(runtime, selection).rows(Q.fatherAtAgeKnown)
        same = (EX.first, OWL.sameAs, EX.later)
        reasoner.update(add=[same])
        assert not evaluate(runtime, selection).rows(Q.fatherAtAgeKnown)
        reasoner.update(remove=[same])
        assert evaluate(runtime, selection).rows(Q.fatherAtAgeKnown) == {(EX.father, Literal(20))}


@pytest.mark.parametrize("backend", ["python", "native"])
def test_operator_failure_retains_last_complete_snapshot(backend):
    source = """version 1
    prefix ex: <urn:test:>
    prefix num: <urn:dlp:numeric:>
    ex:answer(?x) :- ex:input(?n), bind num:divide(1, ?n) as ?x.
    """
    with QueryRuntime(source, backend=backend) as runtime:
        good = runtime.evaluate({"urn:test:input": {(Literal(2),)}}, scope=SCOPE)
        with pytest.raises(DomainError) as failure:
            runtime.evaluate({"urn:test:input": {(Literal(0),)}}, scope=SCOPE)
        assert failure.value.code == "DOMAIN_ERROR"
        assert not runtime.complete
        assert runtime.last_complete is good
        again = runtime.evaluate({"urn:test:input": {(Literal(2),)}}, scope=SCOPE)
        assert again.complete and runtime.cache_hits == 1


def test_bind_checks_previously_bound_output():
    source = """version 1
    prefix ex: <urn:test:>
    prefix num: <urn:dlp:numeric:>
    ex:answer(?x) :- ex:input(?x), bind num:add(1, 1) as ?x.
    """
    with QueryRuntime(source) as runtime:
        result = runtime.evaluate({"urn:test:input": {(Literal(2),), (Literal(3),)}}, scope=SCOPE)
        assert result.rows("urn:test:answer") == {(Literal(2),)}


def test_explicit_equality_binds_without_inventing_inequality():
    source = """version 1
    prefix ex: <urn:test:>
    prefix internal: <urn:dlp:internal:>
    ex:copy(?x, ?y) :- ex:input(?x), internal:eq(?x, ?y).
    ex:different(?x) :- ex:input(?x), internal:neq(?x, ex:other).
    """
    with QueryRuntime(source) as runtime:
        value = Namespace("urn:test:").one
        result = runtime.evaluate({"urn:test:input": {(value,)}}, scope=SCOPE)
        assert result.rows("urn:test:copy") == {(value, value)}
        assert not result.rows("urn:test:different")


@pytest.mark.parametrize("backend", ["python", "native"])
def test_provider_revision_invalidates_maintained_rules(backend):
    from dlp_reasoner.providers import FakeProvider, ProviderRegistry

    source = """version 1
    prefix ex: <urn:test:>
    ex:answer(?x) :- ex:input(?n), bind ex:external(?n) as ?x.
    """
    adapter = FakeProvider({"urn:test:external": lambda n: Literal(int(n) + 1)})
    providers = ProviderRegistry()
    providers.register("urn:test:external", adapter, input_types=("integer",), result_type="integer")
    with QueryRuntime(source, providers=providers, backend=backend) as runtime:
        inputs = {"urn:test:input": {(Literal(1),)}}
        assert runtime.evaluate(inputs, scope=SCOPE).rows("urn:test:answer") == {(Literal(2),)}
        adapter.scalars["urn:test:external"] = lambda n: Literal(int(n) + 2)
        adapter.revision = "2"
        changed = runtime.evaluate(inputs, scope=SCOPE)
        assert changed.rows("urn:test:answer") == {(Literal(3),)}
        assert changed.retractions[Namespace("urn:test:").answer] == {(Literal(2),)}
        assert adapter.batch_calls == 2


@pytest.mark.parametrize("backend", ["python", "native"])
def test_window_rules_expire_without_new_events_and_resume(backend):
    from dlp_reasoner.windows import Event, WindowStore

    source = """version 1
    prefix ex: <urn:test:>
    prefix num: <urn:dlp:numeric:>
    ex:speeding(?id, ?vehicle) :- ex:window(?id, ?at, ?vehicle, ?speed),
        filter num:greaterThan(?speed, 50).
    """
    window = WindowStore(10, allowed_lateness=20, evaluation_time=20, watermark=10,
                         context=("map-v1",))
    window.upsert(Event("first", 12, "vehicle", (Literal(60),)))
    window.upsert(Event("second", 18, "vehicle", (Literal(40),)))
    with QueryRuntime(source, backend=backend) as runtime:
        first = runtime.evaluate({"urn:test:window": window.rows()}, scope=SCOPE)
        assert first.rows("urn:test:speeding") == {("first", "vehicle")}
        restored = WindowStore.restore(window.checkpoint())
        restored.advance(23, watermark=20)
        changed = runtime.evaluate({"urn:test:window": restored.rows()}, scope=SCOPE)
        assert not changed.rows("urn:test:speeding")
        assert changed.retractions[Namespace("urn:test:").speeding] == {("first", "vehicle")}


def test_cancelled_query_cannot_hit_complete_cache():
    from dlp_reasoner.providers import CancellationToken
    from dlp_reasoner.query_runtime import QueryExecutionError
    source = "version 1\nprefix ex: <urn:test:>\nex:answer(?x) :- ex:input(?x)."
    with QueryRuntime(source) as runtime:
        relations = {"urn:test:input": {(Literal(1),)}}
        complete = runtime.evaluate(relations, scope=SCOPE)
        cancel = CancellationToken()
        cancel.cancel()
        with pytest.raises(QueryExecutionError, match="cancelled"):
            runtime.evaluate(relations, scope=SCOPE, cancel=cancel)
        assert runtime.last_complete is complete and not runtime.complete
