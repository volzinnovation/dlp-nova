"""Standalone kernel parity, transactional updates and a CPython-free driver."""
import ctypes as c
from pathlib import Path
import random
import shutil
import subprocess

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD

from dlp_reasoner.compiler import compile_graph
from dlp_reasoner.engine import Engine
from dlp_reasoner.model import Atom, EQ, NEQ, TOP, IncompleteReasoningError, ProfileError, Program, Rule, Skolem, Var
from dlp_reasoner.standalone import NativeRuntime, NativeRuntimeError, _library

X, Y, Z = map(Var, "xyz")
A, B, C = map(URIRef, ("urn:a", "urn:b", "urn:c"))


def parity(program, **limits):
    expected = Engine(program, strategy="naive", **limits).materialize()
    assert expected.complete
    actual = NativeRuntime(program, **limits)
    assert actual.complete
    assert actual.facts == expected.facts
    assert bool(actual.violations) == bool(expected.violations)
    return actual


def test_zero_arity_empty_conjunction_and_repeated_variables():
    parity(Program(facts={Atom("p", (A, A)), Atom("p", (A, B)), Atom("yes", ())}, rules=[
        Rule(Atom("diagonal", (X,)), (Atom("p", (X, X)),)),
        Rule(Atom("q", (A,)), (Atom("yes", ()),)), Rule(Atom("always", ()), ())]))
    empty = parity(Program())
    assert len(empty.facts) == 1  # Nonempty-domain seed TOP fact.


@pytest.mark.parametrize("name,profile", [("family", "L2"), ("bach", "L3"),
                                         ("bach-family", "L2"), ("existential", "L3"),
                                         ("inconsistent", "L2")])
def test_compiled_examples(name, profile):
    parity(compile_graph(Graph().parse(f"examples/{name}.ttl"), profile))


def test_equality_binding_datatype_identity_and_inequality():
    one = Literal("01", datatype=XSD.integer, normalize=False)
    decimal = Literal("1.0", datatype=XSD.decimal, normalize=False)
    two = Literal("2", datatype=XSD.integer)
    runtime = parity(Program(facts={Atom("p", (A, one)), Atom("p", (B, decimal)),
                                   Atom("p", (C, two)), Atom(NEQ, (A, B))}, rules=[
        Rule(Atom("eq", (X, Y)), (Atom("p", (X, Z)), Atom(EQ, (Y, Z)))),
        Rule(Atom("different", (X,)), (Atom("p", (X, Z)), Atom(NEQ, (Z, two))))]))
    assert runtime.normalize(one) == runtime.normalize(decimal)
    assert Atom(NEQ, (B, A)) in runtime.facts


def test_witnesses_congruence_and_named_representative():
    program = Program(facts={Atom("p", (A,)), Atom("p", (B,)), Atom("join", (A, B))}, rules=[
        Rule(Atom("r", (X, Skolem("f", (X,)))), (Atom("p", (X,)),)),
        Rule(Atom(EQ, (X, Y)), (Atom("join", (X, Y)),)),
        Rule(Atom("nested", (Skolem("g", (Skolem("f", (X,)),)),)), (Atom("p", (X,)),))])
    runtime = parity(program)
    assert runtime.normalize(Skolem("f", (B,))) == Skolem("f", (A,))
    runtime.update(add=[Atom(EQ, (Skolem("f", (A,)), C))])
    assert runtime.normalize(Skolem("f", (B,))) == C
    assert any(atom.predicate == "nested" and atom.args == (Skolem("g", (C,)),)
               for atom in runtime.facts)



def test_witness_canonical_order_is_structural_not_creation_order():
    parity(Program(facts={Atom("p", (B,)), Atom("q", (A,))}, rules=[
        Rule(Atom("f", (Skolem("f", (X,)),)), (Atom("p", (X,)),)),
        Rule(Atom("g", (Skolem("f", (X,)),)), (Atom("q", (X,)),)),
        Rule(Atom(EQ, (X, Y)), (Atom("f", (X,)), Atom("g", (Y,))))]))
    witnesses = [Skolem(symbol, (A,)) for symbol in "abcdefghijkl"]
    parity(Program(facts={Atom("p", (value,)) for value in witnesses}
                   | {Atom(EQ, (witnesses[1], witnesses[9]))}))


def test_equality_cycle_prefers_shallow_function():
    ground = Skolem("f", (A,))
    runtime = parity(Program(facts={Atom("p", (ground,)), Atom(EQ, (ground, Skolem("f", (ground,))))}))
    assert runtime.normalize(ground) == ground


def test_explicit_difference_and_constraint_violations():
    runtime = parity(Program(facts={Atom(EQ, (A, B)), Atom(NEQ, (A, B))}, rules=[
        Rule(None, (Atom(TOP, (X,)),), "nonempty")]))
    assert any("different" in message for message in runtime.violations)
    assert any("nonempty violated" in message for message in runtime.violations)
    parity(Program(facts={Atom(EQ, (Literal(1), Literal(2)))}))


def test_equality_split_and_rule_retraction_updates():
    equality = Atom(EQ, (A, B))
    rule = Rule(Atom("q", (X,)), (Atom("p", (X,)),))
    runtime = NativeRuntime(Program(facts={Atom("p", (B,)), equality}, rules=[rule]))
    assert Atom("q", (A,)) in runtime.facts
    runtime.update(remove=[equality])
    assert Atom("q", (B,)) in runtime.facts and Atom("q", (A,)) not in runtime.facts
    runtime.update(remove_rules=[rule])
    assert not any(f.predicate == "q" for f in runtime.facts)
    runtime.update(remove=[Atom("p", (B,))], add=[Atom("p", (A, B))])
    assert Atom("p", (A, B)) in runtime.facts


@pytest.mark.parametrize("failure", ["unsafe", "arity", "depth", "facts", "rounds"])
def test_failed_candidate_retains_old_snapshot(failure):
    runtime = NativeRuntime(Program(facts={Atom("p", (A,))}), max_facts=9, max_depth=2, max_rounds=2)
    old = runtime.facts, runtime.program, runtime.stats, runtime._revision
    options = {
        "unsafe": {"add_rules": [Rule(Atom("q", (X,)), ())]},
        "arity": {"add": [Atom("p", (A, B))]},
        "depth": {"add": [Atom("q", (Skolem("f", (Skolem("f", (Skolem("f", (A,)),)),)),))]},
        "facts": {"add": [Atom("q", (URIRef(f"urn:{i}"),)) for i in range(10)]},
        "rounds": {"add_rules": [Rule(Atom("q", (X,)), (Atom("p", (X,)),)),
                                  Rule(Atom("r", (X,)), (Atom("q", (X,)),))]},
    }
    with pytest.raises((ProfileError, IncompleteReasoningError)):
        runtime.update(**options[failure])
    assert runtime.complete
    assert (runtime.facts, runtime.program, runtime.stats, runtime._revision) == old


def test_recursive_witness_limit_is_explicit():
    recursive = Rule(Atom("p", (Skolem("f", (X,)),)), (Atom("p", (X,)),))
    with pytest.raises(IncompleteReasoningError, match="max_depth"):
        NativeRuntime(Program(facts={Atom("p", (A,))}, rules=[recursive]), max_depth=3)


def test_no_python_semantic_callback(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Python Engine used by standalone runtime")
    monkeypatch.setattr(Engine, "materialize", forbidden)
    monkeypatch.setattr(Engine, "_solutions", forbidden)
    runtime = NativeRuntime(Program(facts={Atom("p", (A,))}, rules=[
        Rule(Atom("q", (X,)), (Atom("p", (X,)),))]))
    assert Atom("q", (A,)) in runtime.facts


def test_random_recursive_closures():
    randomizer = random.Random(372)
    constants = tuple(URIRef(f"urn:n{i}") for i in range(9))
    for _ in range(25):
        facts = {Atom("edge", (a, b)) for a in constants for b in constants if randomizer.random() < .14}
        parity(Program(facts=facts, rules=[
            Rule(Atom("reach", (X, Y)), (Atom("edge", (X, Y)),)),
            Rule(Atom("reach", (X, Z)), (Atom("reach", (X, Y)), Atom("edge", (Y, Z)))),
            Rule(Atom("cycle", (X,)), (Atom("reach", (X, X)),))]))


def test_close_context_and_native_argument_failure():
    with NativeRuntime(Program()) as runtime:
        assert runtime.materialize() is runtime
    with pytest.raises(NativeRuntimeError, match="closed"):
        _ = runtime.facts
    runtime.close()
    lib = _library()
    result = c.c_uint64()
    assert lib.dlp_runtime_normalize(None, 1, c.byref(result)) == -1
    assert lib.dlp_runtime_error_code() == 1



def test_ground_witness_interning_and_generator_rule_updates():
    ground = Skolem("f", (A,))
    rules = [Rule(Atom("p", (ground,)), ()), Rule(Atom("q", (ground,)), ())]
    runtime = NativeRuntime(Program(rules=rules), max_terms=3)
    assert runtime.stats["terms"] == 3  # seed, A, f(A): one ground application.
    runtime.update(remove_rules=(rule for rule in rules))
    assert not any(f.predicate in ("p", "q") for f in runtime.facts)


def test_export_has_no_fixed_result_cap():
    count = 1500
    runtime = NativeRuntime(Program(facts={Atom("p", (URIRef(f"urn:n{i}"),)) for i in range(count)}))
    assert len([f for f in runtime.facts if f.predicate == "p"]) == count
    assert len(runtime.facts) == count * 2 + 1



@pytest.mark.parametrize("option", ["max_candidates", "max_matches", "max_violations"])
def test_constraint_work_limits_are_explicit_and_atomic(option):
    runtime = NativeRuntime(Program(facts={Atom("p", (A,)), Atom("p", (B,))}), **{option: 2})
    previous = runtime.facts
    rule = Rule(None, (Atom("p", (X,)), Atom("p", (Y,))), "cross-product")
    with pytest.raises(IncompleteReasoningError, match=option):
        runtime.update(add_rules=[rule])
    assert runtime.complete and runtime.facts == previous


def test_builder_applies_fact_limit_before_materialize():
    from dlp_reasoner.standalone import _Limits
    lib = _library()
    handle = c.c_void_p()
    limits = _Limits(10, 2, 20, 2)
    assert lib.dlp_runtime_new(1, 2, 3, 1, c.byref(limits), c.byref(handle)) == 0
    try:
        for index in range(1, 5):
            assert lib.dlp_runtime_add_term(handle, index, 2, str(index).encode(), 0) == 0
        for index in (1, 2, 1):
            row = (c.c_uint64 * 1)(index)
            assert lib.dlp_runtime_add_fact(handle, 4, row, 1) == 0
        row = (c.c_uint64 * 1)(3)
        assert lib.dlp_runtime_add_fact(handle, 4, row, 1) == -1
        assert lib.dlp_runtime_error_code() == 2
    finally:
        lib.dlp_runtime_free(handle)


def test_update_frees_handle_through_its_owning_library(monkeypatch):
    import dlp_reasoner.standalone as standalone
    real_library = standalone._library()
    freed = []

    class Library:
        def __init__(self, name):
            self.name = name
        def __getattr__(self, name):
            return getattr(real_library, name)
        def dlp_runtime_free(self, handle):
            freed.append((self.name, handle.value))
            return real_library.dlp_runtime_free(handle)

    first, second = Library("old"), Library("new")
    monkeypatch.setattr(standalone, "_library", lambda: first)
    runtime = NativeRuntime(Program())
    old_id = runtime._handle.value
    monkeypatch.setattr(standalone, "_library", lambda: second)
    runtime.update(add=[Atom("p", (A,))])
    assert ("old", old_id) in freed
    assert ("new", old_id) not in freed
    runtime.close()


def test_standalone_cpp_driver_and_sanitizers(tmp_path):
    compiler = shutil.which("clang++") or shutil.which("g++")
    assert compiler, "native test requires a C++17 compiler"
    source = Path(__file__).resolve().parents[1] / "src" / "dlp_reasoner"
    driver = tmp_path / "driver.cpp"
    driver.write_text(r'''
#include "native_runtime.h"
#include <cassert>
#include <thread>
#include <atomic>
int main() {
 dlp_runtime *r=nullptr; dlp_runtime_limits limits{20,100,100,4};
 assert(dlp_runtime_new(1,2,3,1,&limits,&r)==0);
 assert(dlp_runtime_add_term(r,1,2,"seed",0)==0);
 assert(dlp_runtime_add_term(r,2,0,"a",0)==0);
 uint64_t row[]{2}; assert(dlp_runtime_add_fact(r,4,row,1)==0);
 dlp_runtime_expr x{1,0,0,0,nullptr};
 dlp_runtime_atom head{5,1,&x}, body{4,1,&x};
 assert(dlp_runtime_add_rule(r,&head,&body,1,1,"copy")==0);
 assert(dlp_runtime_materialize(r)==0);
 dlp_runtime_stats stats{}; assert(dlp_runtime_get_stats(r,&stats)==0);
 assert(stats.complete && stats.facts==4 && stats.body_matches==2);
 uint64_t canonical=0; assert(dlp_runtime_normalize(r,2,&canonical)==0 && canonical==2);
 assert(dlp_runtime_add_fact(r,4,row,1)==-1);
 assert(dlp_runtime_error_code()==1);
 assert(dlp_runtime_fact(r,99,&canonical,nullptr,0,nullptr)==-1);
 dlp_runtime_free(r);
 // A separate worker can cancel without acquiring the evaluator's lock.
 limits={1000,10000,10000,4};
 assert(dlp_runtime_new(1,2,3,1,&limits,&r)==0);
 for(uint64_t i=1;i<=1000;++i){
   assert(dlp_runtime_add_term(r,i,2,"individual",0)==0);
   assert(dlp_runtime_add_fact(r,4,&i,1)==0);
 }
 dlp_runtime_expr y{1,0,1,0,nullptr};
 dlp_runtime_atom constraint_body[2]{{4,1,&x},{4,1,&y}};
 assert(dlp_runtime_add_rule(r,nullptr,constraint_body,2,2,"cross product")==0);
 std::atomic<bool> started{false};
 std::thread canceller([&]{while(!started.load())std::this_thread::yield();assert(dlp_runtime_cancel(r)==0);});
 started.store(true);
 assert(dlp_runtime_materialize(r)==-1);
 assert(dlp_runtime_error_code()==5);
 canceller.join();
 assert(dlp_runtime_get_stats(r,&stats)==0&&!stats.complete);
 dlp_runtime_free(r);
}
''')
    output = tmp_path / "driver"
    subprocess.run([compiler, "-std=c++17", "-pthread", "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                    "-g", "-I", str(source), str(driver), str(source / "native_runtime.cpp"),
                    "-o", str(output)], check=True, capture_output=True, text=True, timeout=120)
    subprocess.run([str(output)], check=True, capture_output=True, text=True, timeout=30)
