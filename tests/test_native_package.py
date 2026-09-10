"""Portable native authoring/loader parity and malformed-byte boundary checks."""
import ctypes as c
import hashlib
from pathlib import Path
import random
import shutil
import struct
import subprocess

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD

from dlp_reasoner.compiler import compile_graph
from dlp_reasoner.engine import Engine
from dlp_reasoner.model import Atom, EQ, Program, Rule, Skolem, Var, IncompleteReasoningError
from dlp_reasoner.native_package import (NativePackageError, _HEADER, _Reader, _library,
    _Options, dumps_native, loads_native, dump_native, load_native)
from dlp_reasoner.packages import CompiledPackage
from dlp_reasoner.query_parser import parse_query_program
from dlp_reasoner.standalone import _Limits

X = Var("subject")
A, B = URIRef("urn:a"), URIRef("urn:b")


def program():
    return Program(facts={Atom("p", (A,))}, rules=[Rule(Atom("q", (X,)), (Atom("p", (X,)),), "copy")])


def frame(payload):
    return _HEADER.pack(b"DLPNPKG1", len(payload), hashlib.sha256(payload).digest()) + payload


def records(data):
    reader = _Reader(data[48:])
    reader.number(4)
    for _ in range(3):
        reader.text()
    for _ in range(4):
        reader.number(8)
    header = reader.data[:reader.offset]
    result = []
    while reader.offset < len(reader.data):
        code, size = reader.number(1), reader.number(8)
        result.append((code, reader.data[reader.offset:reader.offset + size]))
        reader.offset += size
    return header, result


def reframe(header, records):
    return frame(header + b"".join(bytes([code]) + struct.pack("<Q", len(data)) + data
                                  for code, data in records))


@pytest.mark.parametrize("example,profile", [("family", "L2"), ("bach", "L3"),
                                             ("bach-family", "L2"), ("existential", "L3"),
                                             ("inconsistent", "L2")])
def test_native_packages_match_compiled_examples(example, profile):
    source = compile_graph(Graph().parse(f"examples/{example}.ttl"), profile)
    expected = Engine(source).materialize()
    with loads_native(dumps_native(source, context={"data_revision": "fixture-1"})) as actual:
        assert actual.facts == expected.facts
        assert actual.program.rules == source.rules
        assert actual.program.facts == source.facts
        assert bool(actual.violations) == bool(expected.violations)
        assert actual.package_context["context"]["data_revision"] == "fixture-1"


def test_authoring_does_not_execute_rules_or_require_a_native_compiler(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("authoring executed a runtime")
    monkeypatch.setattr(Engine, "materialize", forbidden)
    import dlp_reasoner.native_package as package
    monkeypatch.setattr(package, "_library", forbidden)
    assert dumps_native(program()).startswith(b"DLPNPKG1")


def test_exact_rdf_identity_and_witnesses_roundtrip_and_update(tmp_path):
    one = Literal("01", datatype=XSD.integer, normalize=False)
    equivalent = Literal("1.0", datatype=XSD.decimal, normalize=False)
    witness = Skolem("f_😀", (A,))
    source = Program(facts={Atom("p", (A, one)), Atom("p", (B, equivalent)),
                            Atom("witness", (witness,)), Atom(EQ, (A, B))}, rules=[
        Rule(Atom("r", (X, Skolem("g", (X,)))), (Atom("witness", (X,)),))])
    path = tmp_path / "fixture.dlpn"
    dump_native(CompiledPackage(source, context={"revision": "2026-09"}), path)
    with load_native(path) as loaded:
        assert loaded.program == source
        assert loaded.facts == Engine(source).materialize().facts
        loaded.update(remove=[Atom(EQ, (A, B))])
        assert loaded.normalize(A) != loaded.normalize(B)


def test_deterministic_bytes_and_local_query_roundtrip():
    source = program()
    assert dumps_native(source) == dumps_native(Program(list(source.rules), set(reversed(tuple(source.facts)))))
    query = parse_query_program("version 1\nprefix ex: <urn:x:>\nex:q(?x) :- ex:p(?x).")
    with loads_native(dumps_native(CompiledPackage(source, query))) as loaded:
        assert loaded.query() == {URIRef("urn:x:q"): frozenset()}


@pytest.mark.parametrize("corruption", ["magic", "length", "checksum", "trailing", "version", "profile"])
def test_framing_and_semantic_profile_rejection(corruption):
    data = bytearray(dumps_native(program()))
    if corruption == "magic":
        data[0] ^= 1
    elif corruption == "length":
        data[8] ^= 1
    elif corruption == "checksum":
        data[16] ^= 1
    elif corruption == "trailing":
        data += b"x"
    elif corruption == "version":
        data = bytearray(frame(struct.pack("<I", 2) + data[52:]))
    else:
        payload = bytes(data[48:]).replace(b"dlp-domains-v1", b"dlp-domains-v9", 1)
        data = bytearray(frame(payload))
    with pytest.raises(NativePackageError):
        loads_native(bytes(data))


@pytest.mark.parametrize("corruption", ["unknown", "no-end", "truncated", "duplicate-term-id",
                                       "duplicate-term-value", "duplicate-predicate", "bad-utf8"])
def test_record_validation_after_recomputed_checksum(corruption):
    header, commands = records(dumps_native(program()))
    if corruption == "unknown":
        commands.insert(-1, (99, b""))
    elif corruption == "no-end":
        commands.pop()
    elif corruption == "truncated":
        code, data = commands[0]
        commands[0] = code, data[:-1]
    elif corruption in {"duplicate-term-id", "duplicate-term-value"}:
        item = next(command for command in commands if command[0] == 2)
        if corruption == "duplicate-term-value":
            item = item[0], struct.pack("<Q", 999) + item[1][8:]
        commands.insert(-1, item)
    elif corruption == "duplicate-predicate":
        item = next(command for command in commands if command[0] == 6)
        commands.insert(-1, (6, struct.pack("<Q", 999) + item[1][8:]))
    else:
        for index, (code, data) in enumerate(commands):
            if code == 6 and b"urn:dlp" in data:
                commands[index] = code, data.replace(b"urn:", b"\xffrn:", 1)
                break
    with pytest.raises(NativePackageError):
        loads_native(reframe(header, commands))


def test_native_resource_failure_publishes_no_partial_runtime():
    with pytest.raises(IncompleteReasoningError, match="max_facts"):
        loads_native(dumps_native(program()), max_facts=2)
    with pytest.raises(IncompleteReasoningError, match="max_rounds"):
        loads_native(dumps_native(program()), max_rounds=1)


def test_header_truncations_and_random_corruption_reject_safely():
    data = dumps_native(program())
    for size in (*range(48), 49, len(data) - 1):
        with pytest.raises(NativePackageError):
            loads_native(data[:size])
    randomizer = random.Random(501)
    for _ in range(30):
        edited = bytearray(data)
        edited[randomizer.randrange(48, len(data))] ^= 1
        with pytest.raises(NativePackageError):
            loads_native(bytes(edited))
    # Exercise the C boundary directly, independent of Python byte-size guards.
    library = _library()
    result = c.c_void_p()
    options = _Options(_Limits(10, 100, 100, 4), 1000, 1000, 1000)
    assert library.dlp_native_package_load(None, 48, c.byref(options), c.byref(result)) == -1
    assert not result


def test_native_loader_cpp_driver_without_cpython_and_sanitizers(tmp_path):
    compiler = shutil.which("clang++") or shutil.which("g++")
    assert compiler
    source = Path(__file__).resolve().parents[1] / "src" / "dlp_reasoner"
    artifact = tmp_path / "fixture.dlpn"
    dump_native(program(), artifact, context={"revision": "fixture1"})
    driver = tmp_path / "driver.cpp"
    driver.write_text(r'''
#include "native_package.h"
#include <cassert>
#include <fstream>
#include <iterator>
#include <vector>
#include <cstring>
int main(int argc,char**argv) {
 assert(argc==2);std::ifstream file(argv[1],std::ios::binary);
 std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(file)),{});
 dlp_native_package_options options{{20,100,100,4},10000,10000,1000};
 dlp_native_package *package=nullptr;
 assert(dlp_native_package_load(bytes.data(),bytes.size(),&options,&package)==0);
 assert(std::strcmp(dlp_native_package_profile(package),"L2")==0);
 size_t terms=0,predicates=0,symbols=0;
 assert(dlp_native_package_counts(package,&terms,&predicates,&symbols)==0);
 assert(terms==2&&predicates==5&&symbols==0);
 dlp_package_term_view term{};assert(dlp_native_package_term(package,0,&term)==0);
 assert(term.kind==1&&term.lexical_size==5&&std::memcmp(term.lexical,"urn:a",5)==0);
 const uint8_t*context=nullptr;size_t context_size=0;
 assert(dlp_native_package_context(package,&context,&context_size)==0&&context_size>0);
 dlp_runtime*runtime=nullptr;assert(dlp_native_package_runtime(package,&runtime)==0);
 dlp_runtime_stats stats{};assert(dlp_runtime_get_stats(runtime,&stats)==0&&stats.complete&&stats.facts==4);
 assert(dlp_native_package_take_runtime(package,&runtime)==0);
 dlp_native_package_free(package);dlp_runtime_free(runtime);
 bytes.back()^=1;package=nullptr;
 assert(dlp_native_package_load(bytes.data(),bytes.size(),&options,&package)==-1&&!package);
}
''')
    executable = tmp_path / "driver"
    subprocess.run([compiler, "-std=c++17", "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                    "-I", str(source), str(driver), str(source / "native_package.cpp"),
                    str(source / "native_runtime.cpp"), str(source / "native_query.cpp"),
                    str(source / "native_domains.cpp"), "-o", str(executable)],
                   check=True, capture_output=True, text=True, timeout=120)
    subprocess.run([str(executable), str(artifact)], check=True, capture_output=True, text=True, timeout=30)
