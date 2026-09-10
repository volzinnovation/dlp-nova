"""Authored .dlpn local query sections execute without a Python rule interpreter."""
import ctypes as c
import struct
import time
from pathlib import Path
import shutil
import subprocess

import pytest
from rdflib import Literal, Namespace, RDF, XSD

from dlp_reasoner.domains import DomainError, DomainRegistry
from dlp_reasoner.model import Atom, EQ, NEQ, Program, Rule, Var, IncompleteReasoningError
from dlp_reasoner.native_package import NativePackageError, dumps_native, loads_native
from dlp_reasoner.packages import CompiledPackage
from dlp_reasoner.query_ir import ProviderScan, QueryProgram, QueryRule, RelationAtom
from dlp_reasoner.query_parser import parse_query_program
from dlp_reasoner.query_runtime import QueryRuntime, QueryScope
from test_native_package import records, reframe

EX = Namespace("urn:package-query:")
PREFIX = "version 1 prefix ex: <urn:package-query:> prefix n: <urn:dlp:numeric:> "


def artifact(source, facts=(), rules=()):
    return dumps_native(CompiledPackage(Program(list(rules), set(facts)), parse_query_program(PREFIX + source)))


def test_arithmetic_min_and_filters_run_without_python_callbacks(monkeypatch):
    data = artifact("""
        ex:next(?id, ?m) :- ex:input(?id, ?n), bind n:add(?n, 1) as ?m.
        ex:best(?m) :- MIN ?n GROUP_BY() FROM ex:next(?id, ?n) AS ?m.
        ex:answer(?m) :- ex:best(?m), filter n:lessThan(?m, 100).
    """, [Atom(EX.input, (EX.a, Literal(9)))])
    def forbidden(*args, **kwargs):
        raise AssertionError("Package local query called Python interpreter")
    monkeypatch.setattr(DomainRegistry, "evaluate_batch", forbidden)
    monkeypatch.setattr(QueryRuntime, "_solutions", forbidden)
    with loads_native(data) as runtime:
        with runtime.prepare_query(relations={EX.input: {(EX.b, Literal(4))}}) as query:
            assert query.run()[EX.answer] == {(Literal(5),)}
            assert query.stats["domain_evaluations"] > 0


def test_given_parameters_dates_role_flags_and_new_values():
    data = artifact("""
        prefix t: <urn:dlp:temporal:> prefix policy: <urn:dlp:calendar-policy:>
        ex:age(?years) given (?date) :- ex:birth(?birth),
            bind t:completedYears(?birth, ?date, policy:march1) as ?years.
    """, [Atom(EX.birth, (Literal("2000-02-29", datatype=XSD.date),))])
    with loads_native(data) as runtime:
        with pytest.raises(NativePackageError, match="missing required"):
            runtime.query()
        assert runtime.query(parameters={"date": Literal("2021-02-28", datatype=XSD.date)})[EX.age] == {(Literal(20),)}
        assert runtime.query(parameters={Var("date"): Literal("2021-03-01", datatype=XSD.date)})[EX.age] == {(Literal(21),)}


def test_native_geodesic_and_quantity_operations_are_packaged():
    data = artifact("""
        prefix s: <urn:dlp:spatial:> prefix u: <urn:dlp:unit:>
        ex:distance(?d) :- bind s:wgs84Point(0, 0) as ?p,
          bind s:wgs84Point(0, 1) as ?q, bind s:wgs84Distance(?p, ?q) as ?d.
        ex:quantity(?q) :- bind n:quantity(2, u:metre) as ?q.
    """)
    with loads_native(data) as runtime:
        output = runtime.query()
        distance, = next(iter(output[EX.distance]))
        assert abs(float(distance) - 110574.38855779878) < 0.001
        quantity, = next(iter(output[EX.quantity]))
        assert quantity.unit == "urn:dlp:unit:metre"


def test_type_expansion_and_query_constants_do_not_change_horn_top():
    source = PREFIX + "prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> ex:classes(?type) :- rdf:type(ex:a, ?type)."
    base = Program(facts={Atom(EX.Musician, (EX.a,))})
    data = dumps_native(CompiledPackage(base, parse_query_program(source)))
    with loads_native(data) as runtime, loads_native(dumps_native(base)) as plain:
        assert runtime.facts == plain.facts
        assert runtime.query()[EX.classes] == {(EX.Musician,)}
        with QueryRuntime(source) as python:
            expected = python.evaluate({RDF.type: {(EX.a, EX.Musician)}}, scope=QueryScope(EX.scope, "1"))
            assert runtime.query() == expected.relations


def test_type_expansion_uses_normalized_class_term_for_constant_joins():
    data = artifact("prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> "
                    "ex:answer(?x) :- rdf:type(?x, ex:A).",
                    [Atom(EX.B, (EX.person,)), Atom(EQ, (EX.A, EX.B))])
    with loads_native(data) as runtime:
        assert runtime.query()[EX.answer] == {(EX.person,)}


def test_reserved_predicate_aliases_and_typed_scalar_identity():
    from rdflib import URIRef
    data = artifact("prefix d: <urn:dlp:internal:> "
                    "ex:answer(?x,?y) :- ex:input(?x,?y), d:neq(?x,?y).")
    with loads_native(data) as runtime:
        for predicate in (NEQ, URIRef(NEQ)):
            assert runtime.query(relations={EX.input: {(EX.a, EX.b)}, predicate: {(EX.a, EX.b)}})[EX.answer] == {(EX.a, EX.b)}
    data = artifact("ex:answer(?y) :- ex:input(?x), bind n:add(?x, 1) as ?y.",
                    [Atom(EX.aux, (1,))])
    with loads_native(data) as runtime:
        with pytest.raises(DomainError) as error:
            runtime.query(relations={EX.input: {(True,)}})
        assert error.value.code == "TYPE_ERROR"


def test_generated_scalar_preserves_canonical_rdf_output_identity():
    padded = Literal("01", datatype=XSD.integer, normalize=False)
    data = artifact("ex:answer(?y) :- ex:input(?x), bind n:add(?x, 0) as ?y.",
                    [Atom(EX.input, (padded,)), Atom(EX.aux, (Literal(1),))])
    with loads_native(data) as runtime:
        assert runtime.normalize(Literal(1)) == padded
        assert runtime.query()[EX.answer] == {(Literal(1),)}


def test_hashable_mutable_objects_are_not_admitted_as_query_values():
    class Mutable:
        pass
    with loads_native(artifact("ex:answer(?x) :- ex:input(?x).")) as runtime:
        with pytest.raises(NativePackageError, match="immutable"):
            runtime.query(relations={EX.input: {(Mutable(),)}})


def test_minimum_replacement_and_empty_zero_arity_outputs():
    data = artifact("""
        ex:min(?v) :- MIN ?x GROUP_BY() FROM ex:value(?x) AS ?v.
        ex:found() :- ex:min(?x).
    """)
    with loads_native(data) as runtime:
        assert runtime.query(relations={EX.value: {(Literal(3),), (Literal(1),)}})[EX.min] == {(Literal(1),)}
        assert runtime.query(relations={EX.value: {(Literal(3),)}})[EX.min] == {(Literal(3),)}
        assert runtime.query(relations={EX.value: set()}) == {EX.min: frozenset(), EX.found: frozenset()}


def test_result_export_streams_all_rows_past_one_batch():
    data = artifact("ex:answer(?x) :- ex:input(?x).")
    rows = {(Literal(value),) for value in range(1500)}
    with loads_native(data) as runtime:
        assert runtime.query(relations={EX.input: rows})[EX.answer] == rows


def test_inconsistent_horn_snapshot_remains_inspectable_but_queries_reject():
    data = artifact("ex:answer(?x) :- ex:bad(?x).", [Atom(EX.bad, (EX.a,))],
                    [Rule(None, (Atom(EX.bad, (Var("x"),)),), "contradiction")])
    with loads_native(data) as runtime:
        assert runtime.complete and runtime.violations and runtime.facts
        with pytest.raises(NativePackageError, match="consistent"):
            runtime.prepare_query()


def test_query_plan_lifetime_and_snapshot_updates_are_explicit():
    data = artifact("ex:answer(?x) :- ex:input(?x).", [Atom(EX.input, (EX.a,))])
    with loads_native(data) as runtime:
        with runtime.prepare_query() as query:
            runtime.update(add=[Atom(EX.input, (EX.b,))])
            with pytest.raises(NativePackageError, match="changed or closed"):
                query.run()
        with pytest.raises(NativePackageError, match="active packaged"):
            runtime.prepare_query()
        assert Atom(EX.input, (EX.b,)) in runtime.facts


def test_reentrant_input_mutation_and_control_close_are_safe():
    data = artifact("ex:answer(?x) :- ex:input(?x).", [Atom(EX.input, (EX.a,))])
    with loads_native(data) as runtime:
        def rows():
            runtime.update(add=[Atom(EX.input, (EX.b,))])
            yield (EX.b,)
        with pytest.raises(RuntimeError, match="Cannot update"):
            runtime.prepare_query(relations={EX.input: rows()})
        with runtime.prepare_query() as query:
            with pytest.raises(NativePackageError, match="Cannot close"):
                query.run(cancel=query.close)
        assert runtime.query()[EX.answer] == {(EX.a,)}


def test_limits_deadline_and_row_errors_publish_no_answer():
    data = artifact("ex:answer(?x) :- ex:input(?x).")
    with loads_native(data) as runtime:
        with pytest.raises(IncompleteReasoningError):
            runtime.prepare_query(relations={EX.input: ((Literal(n),) for n in range(100))}, max_rows=2)
        with runtime.prepare_query() as query:
            with pytest.raises(IncompleteReasoningError, match="deadline"):
                query.run(deadline=time.monotonic() - 1)
            assert not query.complete
    bad = artifact("ex:answer(?x) :- bind n:divide(1, 3) as ?x.")
    with loads_native(bad) as runtime, runtime.prepare_query() as query:
        with pytest.raises(DomainError):
            query.run()
        assert not query.complete


def test_completed_result_reuse_still_checks_cancellation():
    data = artifact("ex:answer(?x) :- ex:input(?x).", [Atom(EX.input, (EX.a,))])
    with loads_native(data) as runtime, runtime.prepare_query() as query:
        first = query.run()
        assert query.run() is first
        with pytest.raises(IncompleteReasoningError, match="cancelled"):
            query.run(cancel=lambda: True)
        assert not query.complete
        assert query.run() is first


def test_unsupported_provider_plan_is_never_silently_dropped():
    variable = Var("x")
    query = QueryProgram((QueryRule(RelationAtom(EX.answer, (variable,)),
                                    (ProviderScan(EX.provider, (), (variable,)),)),))
    with pytest.raises(ValueError, match="provider scans"):
        dumps_native(CompiledPackage(Program(), query))


def test_role_flags_and_rdf_class_map_tampering_rejects():
    data = artifact("ex:answer(?x) :- ex:Class(?x).", [Atom(EX.Class, (EX.a,))])
    header, commands = records(data)
    broken = [(code, payload[:-4] + struct.pack("<I", 16) if code == 11 else payload)
              for code, payload in commands]
    with pytest.raises(NativePackageError, match="role"):
        loads_native(reframe(header, broken))
    wrong = []
    for code, payload in commands:
        if code == 12:
            payload = payload[:20] + struct.pack("<Q", 1)
        wrong.append((code, payload))
    with pytest.raises(NativePackageError, match="identity mismatch"):
        loads_native(reframe(header, wrong))


def test_c_prepare_parameters_own_their_copied_storage():
    # Direct ABI caller can release its parameter strings immediately afterward.
    from dlp_reasoner.native_package import _Parameter
    from dlp_reasoner.query_native import _Limits, _Value, _CONTROL
    data = artifact("ex:answer(?x) given (?x) :- filter n:lessThan(?x, 8).")
    with loads_native(data) as runtime:
        library = runtime._package_owner.library
        fresh, handle = c.c_uint64(), c.c_void_p()
        assert library.dlp_native_package_next_term_id(runtime._package_owner.package, c.byref(fresh)) == 0
        parameter = _Parameter(b"x", fresh.value, _Value(2, 0, 7, 0, 0, 0, 0), 0, 1, 0, 0,
                                b"integer-seven", 13, b"integer-seven", 13, 0)
        limits = _Limits(100, 100, 10, 100, 1000)
        assert library.dlp_native_package_prepare_query(runtime._package_owner.package, c.byref(limits),
                    c.byref(parameter), 1, c.byref(handle)) == 0
        del parameter
        assert library.dlp_qx_run(handle, _CONTROL(), None) == 0
        library.dlp_qx_free(handle)


def test_native_loader_rejects_bad_query_plan_before_horn_publication():
    from dlp_reasoner.native_package import _Reader
    data = artifact("ex:answer(?x) :- bind n:add(1, 2) as ?x.")
    header, commands = records(data)
    changed = []
    for opcode, payload in commands:
        if opcode == 10:
            reader = _Reader(payload)
            reader.number(8)
            reader.number(8)
            head_arity = reader.number(4)
            reader.offset += head_arity * 12
            for _ in range(reader.number(4)):
                reader.text()
                reader.number(1)
            reader.number(4)
            offset = reader.offset + 4  # operation opcode after node kind
            payload = payload[:offset] + struct.pack("<I", 999) + payload[offset + 4:]
        changed.append((opcode, payload))
    with pytest.raises(NativePackageError, match="opcode"):
        loads_native(reframe(header, changed))


def test_c_loader_rejects_arity_conflict_for_an_empty_horn_predicate():
    from dlp_reasoner.native_package import _Reader
    variable = Var("x")
    data = artifact("ex:answer(?x) :- ex:input(?x).", rules=[
        Rule(Atom(EX.pair, (variable, variable)), (Atom(EX.input, (variable,)),))])
    header, commands = records(data)
    pair_id = None
    for opcode, payload in commands:
        if opcode == 6:
            reader = _Reader(payload)
            identifier = reader.number(8)
            if reader.term() == EX.pair:
                pair_id = identifier
    assert pair_id is not None
    altered = [(opcode, payload[:8] + struct.pack("<Q", pair_id) + payload[16:]
                if opcode == 10 else payload) for opcode, payload in commands]
    with pytest.raises(NativePackageError, match="arity conflicts with Horn"):
        loads_native(reframe(header, altered))


def test_pure_cpp_loader_executes_authored_query_without_python(tmp_path):
    compiler = shutil.which("clang++") or shutil.which("g++")
    if not compiler:
        pytest.skip("C++ compiler unavailable")
    artifact_path = tmp_path / "query.dlpn"
    artifact_path.write_bytes(artifact("ex:answer(?m) :- ex:input(?n), bind n:add(?n, 1) as ?m.",
                                      [Atom(EX.input, (Literal(2),))]))
    driver = tmp_path / "query.cpp"
    driver.write_text(r'''
#include "native_package.h"
#include <cassert>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>
int main(int argc,char**argv) {
 assert(argc==2);std::ifstream file(argv[1],std::ios::binary);
 std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(file)),{});
 dlp_native_package_options options{{20,100,100,4},10000,10000,1000};
 dlp_native_package*package=nullptr;
 assert(dlp_native_package_load(bytes.data(),bytes.size(),&options,&package)==0);
 size_t terms=0,predicates=0,symbols=0;
 assert(dlp_native_package_counts(package,&terms,&predicates,&symbols)==0);
 uint64_t answer=0;
 for(size_t i=0;i<predicates;++i){dlp_package_term_view view{};
   assert(dlp_native_package_predicate(package,i,&view)==0);
   if(std::string(view.lexical,view.lexical_size)=="urn:package-query:answer")answer=view.id;}
 assert(answer);dlp_qx_limits limits{100,100,20,100,10000};dlp_qx_context*query=nullptr;
 assert(dlp_native_package_prepare_query(package,&limits,nullptr,0,&query)==0);
 dlp_native_package_free(package); // query owns its copied data/plan now
 assert(dlp_qx_run(query,nullptr,nullptr)==0);
 uint64_t output=0;size_t written=0;int done=0;
 assert(dlp_qx_result(query,answer,1,0,&output,1,&written,&done)==0&&written==1&&done);
 dlp_domain_value value{};assert(dlp_qx_value(query,output,&value)==0);
 assert(value.tag==2&&value.a==3);dlp_qx_free(query);
}
''')
    source = Path(__file__).resolve().parents[1] / "src/dlp_reasoner"
    executable = tmp_path / "query"
    subprocess.run([compiler, "-std=c++17", "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                    "-I", str(source), str(driver), *(str(source / name) for name in
                    ("native_package.cpp", "native_runtime.cpp", "native_query.cpp", "native_domains.cpp")),
                    "-o", str(executable)], check=True, capture_output=True, text=True, timeout=120)
    subprocess.run([str(executable), str(artifact_path)], check=True, capture_output=True,
                   text=True, timeout=30)
