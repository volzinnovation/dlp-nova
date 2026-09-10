#!/usr/bin/env python3
"""Author the small portable Horn/query smoke package; Python is only an authoring tool."""
import argparse
from pathlib import Path

from rdflib import Literal, Namespace

from dlp_reasoner.model import Atom, Program, Rule, Var
from dlp_reasoner.native_package import dumps_native
from dlp_reasoner.packages import CompiledPackage
from dlp_reasoner.query_parser import parse_query_program


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    ex = Namespace("urn:package-query:")
    n = Var("n")
    horn = Program([Rule(Atom(ex.input, (n,)), (Atom(ex.raw, (n,)),), "raw-input")],
                   {Atom(ex.raw, (Literal(2),)), Atom(ex.raw, (Literal(9),))})
    query = parse_query_program("""
        version 1
        prefix ex: <urn:package-query:>
        prefix n: <urn:dlp:numeric:>
        ex:next(?m) :- ex:input(?n), bind n:add(?n, 1) as ?m.
        ex:best(?m) :- MIN ?n GROUP_BY() FROM ex:next(?n) AS ?m.
        ex:answer(?m) :- ex:best(?m), filter n:lessThan(?m, 100).
    """)
    data = dumps_native(CompiledPackage(horn, query))
    path = Path(__file__).parent / "fixtures" / "query.dlpn"
    if args.check:
        if not path.exists() or path.read_bytes() != data:
            parser.error("Smoke package is stale; run mobile/generate_fixture.py")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    print(path)


if __name__ == "__main__":
    main()
