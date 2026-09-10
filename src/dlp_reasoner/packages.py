"""Portable, bounded, versioned packages for ahead-of-time compiled programs.

The envelope uses explicit little-endian lengths and a SHA-256 payload checksum.
Its canonical UTF-8 JSON payload contains tagged values and rule IR, never Python
objects, process-local IDs, hashes, or native container layouts. This loader is
the desktop authoring path; mobile loaders must advertise this format explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import struct
from types import MappingProxyType

from rdflib import BNode, Graph, Literal, RDF, URIRef

from .compiler import compile_graph
from .domains import DomainRegistry, PROFILE
from .engine import Engine
from .model import Atom, Program, Rule, Skolem, Var
from .query_ir import (Aggregate, Bind, Filter, ProviderScan, QueryProgram, QueryRule,
                       RelationAtom, plan)
from .query_parser import parse_query_program


_MAGIC = b"DLPPKG\x00\x01"
_HEADER = struct.Struct("<8sQ32s")
_MAX_BYTES = 64 * 1024 * 1024


class PackageError(ValueError):
    """An incompatible, corrupted or resource-exceeding compiled package."""


@dataclass(frozen=True)
class CompiledPackage:
    program: Program
    query_program: QueryProgram | None = None
    requirements: tuple = ()
    context: object = field(default_factory=lambda: MappingProxyType({}))
    source_triples: tuple = ()

    def engine(self, *, backend="python", **limits):
        """Load compiled rules without recompiling the ontology."""
        return Engine(self.program, backend=backend, **limits).materialize()

    def source_graph(self):
        graph = Graph()
        for triple in self.source_triples:
            graph.add(triple)
        return graph

    def native_runtime(self, **limits):
        """Execute the compiled Horn program wholly in the standalone C++ core."""
        from .standalone import NativeRuntime
        return NativeRuntime(self.program, **limits)


def _term(value):
    if isinstance(value, Var):
        return ["var", value.name]
    if isinstance(value, Skolem):
        return ["skolem", value.symbol, [_term(term) for term in value.args]]
    if isinstance(value, URIRef):
        return ["iri", str(value)]
    if isinstance(value, BNode):
        return ["bnode", str(value)]
    if isinstance(value, Literal):
        return ["literal", str(value), str(value.datatype) if value.datatype and not value.language else None, value.language]
    if type(value) is str:
        return ["symbol", value]
    if type(value) is int:
        return ["integer", str(value)]
    raise PackageError(f"Unsupported term type {type(value).__name__}")


def _read_term(record, depth=0):
    if depth > 64 or not isinstance(record, list) or not record:
        raise PackageError("Invalid or excessively nested term")
    kind, *args = record
    if kind in {"var", "iri", "bnode", "symbol", "integer"}:
        if len(args) != 1 or type(args[0]) is not str or not args[0]:
            raise PackageError("Malformed term payload")
        if kind == "iri" and (":" not in args[0] or any(c.isspace() for c in args[0])):
            raise PackageError("Invalid absolute term IRI")
        constructors = {"var": Var, "iri": URIRef, "bnode": BNode, "symbol": str, "integer": int}
        value = constructors[kind](args[0])
    elif kind == "literal":
        if (len(args) != 3 or type(args[0]) is not str
                or (args[1] is not None and type(args[1]) is not str)
                or (args[2] is not None and type(args[2]) is not str)
                or (args[1] is not None and args[2] is not None)):
            raise PackageError("Malformed RDF literal")
        value = Literal(args[0], datatype=URIRef(args[1]) if args[1] else None,
                        lang=args[2], normalize=False)
    elif kind == "skolem":
        if len(args) != 2 or type(args[0]) is not str or not isinstance(args[1], list):
            raise PackageError("Malformed witness template")
        value = Skolem(args[0], tuple(_read_term(term, depth + 1) for term in args[1]))
    else:
        raise PackageError(f"Unknown term tag {kind!r}")
    if _term(value) != record:
        raise PackageError("Noncanonical or malformed term")
    return value


def _atom(atom):
    return [_term(atom.predicate), [_term(term) for term in atom.args]]


def _read_atom(record, *, query=False):
    if not isinstance(record, list) or len(record) != 2 or not isinstance(record[1], list):
        raise PackageError("Malformed atom")
    return (RelationAtom if query else Atom)(_read_term(record[0]), tuple(map(_read_term, record[1])))


def _node(node):
    if isinstance(node, RelationAtom):
        return ["relation", _atom(node)]
    if isinstance(node, Filter):
        return ["filter", _term(node.operation), list(map(_term, node.args))]
    if isinstance(node, Bind):
        return ["bind", _term(node.operation), list(map(_term, node.args)), _term(node.output)]
    if isinstance(node, ProviderScan):
        return ["scan", _term(node.operation), list(map(_term, node.args)), list(map(_term, node.outputs))]
    if isinstance(node, Aggregate):
        return ["aggregate", node.kind, _atom(node.source), list(map(_term, node.group_by)),
                _term(node.value), _term(node.output)]
    raise PackageError(f"Unsupported plan node {type(node).__name__}")


def _read_node(record):
    if not isinstance(record, list) or not record:
        raise PackageError("Malformed query node")
    kind, *args = record
    if kind == "relation" and len(args) == 1:
        node = _read_atom(args[0], query=True)
    elif kind in {"filter", "bind", "scan"} and len(args) == (2 if kind == "filter" else 3):
        operation, terms = _read_term(args[0]), tuple(map(_read_term, args[1]))
        node = (Filter(operation, terms) if kind == "filter" else
                Bind(operation, terms, _read_term(args[2])) if kind == "bind" else
                ProviderScan(operation, terms, tuple(map(_read_term, args[2]))))
    elif kind == "aggregate" and len(args) == 5:
        node = Aggregate(_read_atom(args[1], query=True), tuple(map(_read_term, args[2])),
                         _read_term(args[3]), _read_term(args[4]), args[0])
    else:
        raise PackageError("Unknown or malformed query node")
    if _node(node) != record:
        raise PackageError("Noncanonical query node")
    return node


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def _relation_arities(program):
    arities = {RDF.type: 2}
    for atom in (*program.facts, *(atom for rule in program.rules
                  for atom in (*rule.body, *((rule.head,) if rule.head else ())))):
        previous = arities.setdefault(atom.predicate, len(atom.args))
        if previous != len(atom.args):
            raise PackageError(f"Ontology relation {atom.predicate} arity mismatch")
    return arities


def compile_package(graph, *, profile="L2", queries=None, registry=None, context=None):
    program = compile_graph(graph, profile=profile)
    query_program = parse_query_program(queries) if isinstance(queries, str) else queries
    requirements = {}
    if query_program is not None:
        owns_registry = registry is None
        registry = registry if registry is not None else DomainRegistry()
        try:
            plan(query_program, registry, relation_arities=_relation_arities(program))
            for rule in query_program.rules:
                for node in rule.body:
                    if isinstance(node, (Bind, Filter, ProviderScan)):
                        operation = registry.get(node.operation)
                        requirements[str(node.operation)] = operation.version
        finally:
            if owns_registry:
                registry.close()
    return CompiledPackage(program, query_program, tuple(sorted(requirements.items())),
                           MappingProxyType(dict(context or {})), tuple(graph))


def dumps(package, *, max_bytes=_MAX_BYTES):
    program = package.program
    query = package.query_program
    body = {"format": "dlp-compiled", "version": 1, "domain_profile": PROFILE,
            "profile": program.profile, "context": dict(package.context),
            "requirements": [list(pair) for pair in package.requirements],
            "facts": sorted((_atom(fact) for fact in program.facts), key=_canonical),
            "rules": [[None if rule.head is None else _atom(rule.head),
                       [_atom(atom) for atom in rule.body], rule.label] for rule in program.rules],
            "warnings": list(program.warnings),
            "source": sorted(([ _term(term) for term in triple] for triple in package.source_triples),
                             key=_canonical),
            "query": None if query is None else {
                "version": query.version, "namespaces": dict(query.namespaces),
                "rules": [[_atom(rule.head), [_node(node) for node in rule.body], rule.label,
                           list(map(_term, rule.given))] for rule in query.rules]}}
    payload = _canonical(body)
    if len(payload) > max_bytes:
        raise PackageError("Package exceeds byte limit")
    return _HEADER.pack(_MAGIC, len(payload), hashlib.sha256(payload).digest()) + payload


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PackageError(f"Duplicate package field {key}")
        result[key] = value
    return result


def loads(data, *, registry=None, max_bytes=_MAX_BYTES, max_facts=1_000_000, max_rules=100_000):
    """Validate every section/capability before returning a loaded package."""
    if not isinstance(data, bytes) or len(data) < _HEADER.size:
        raise PackageError("Truncated package header")
    magic, size, digest = _HEADER.unpack_from(data)
    if magic != _MAGIC or size > max_bytes or size != len(data) - _HEADER.size:
        raise PackageError("Unsupported format, invalid length or package byte limit exceeded")
    payload = data[_HEADER.size:]
    if hashlib.sha256(payload).digest() != digest:
        raise PackageError("Package checksum mismatch")
    owns_registry = registry is None
    try:
        body = json.loads(payload, object_pairs_hook=_unique_object,
                          parse_constant=lambda value: (_ for _ in ()).throw(PackageError("Nonfinite JSON value")))
        expected = {"format", "version", "domain_profile", "profile", "context", "requirements",
                    "facts", "rules", "warnings", "source", "query"}
        if (not isinstance(body, dict) or set(body) != expected or body["format"] != "dlp-compiled"
                or type(body["version"]) is not int or body["version"] != 1
                or body["domain_profile"] != PROFILE or body["profile"] not in {"L0", "L1", "L2", "L3"}):
            raise PackageError("Unsupported package profile or fields")
        if _canonical(body) != payload:
            raise PackageError("Package payload must use canonical encoding")
        if not all(isinstance(body[key], list) for key in ("facts", "rules", "source", "requirements", "warnings")):
            raise PackageError("Malformed package sections")
        if len(body["facts"]) > max_facts or len(body["source"]) > max_facts or len(body["rules"]) > max_rules:
            raise PackageError("Package fact/rule limits exceeded")
        if not isinstance(body["context"], dict) or not all(type(w) is str for w in body["warnings"]):
            raise PackageError("Invalid context or warnings")
        requirements = []
        registry = registry if registry is not None else DomainRegistry()
        for requirement in body["requirements"]:
            if not isinstance(requirement, list) or len(requirement) != 2 or not all(type(x) is str for x in requirement):
                raise PackageError("Invalid capability requirement")
            uri, version = requirement
            if registry.get(uri).version != version:
                raise PackageError(f"Incompatible required operation {uri} version {version}")
            requirements.append((uri, version))
        if len(set(uri for uri, _ in requirements)) != len(requirements):
            raise PackageError("Duplicate operation requirement")
        facts = {_read_atom(fact) for fact in body["facts"]}
        rules = []
        for entry in body["rules"]:
            if not isinstance(entry, list) or len(entry) != 3 or not isinstance(entry[1], list) or type(entry[2]) is not str:
                raise PackageError("Malformed compiled rule")
            rules.append(Rule(None if entry[0] is None else _read_atom(entry[0]),
                              tuple(map(_read_atom, entry[1])), entry[2]))
        program = Program(rules, facts, body["profile"], body["warnings"])
        # Validate Horn safety, immutable ground terms, and predicate arities
        # without running the program or publishing any candidate context.
        Engine(program)
        query = body["query"]
        query_program = None
        if query is not None:
            if (not isinstance(query, dict) or set(query) != {"version", "namespaces", "rules"}
                    or type(query["version"]) is not int or query["version"] != 1
                    or not isinstance(query["namespaces"], dict) or not isinstance(query["rules"], list)
                    or len(query["rules"]) > max_rules):
                raise PackageError("Malformed query IR section")
            query_rules = []
            for entry in query["rules"]:
                if (not isinstance(entry, list) or len(entry) != 4 or type(entry[2]) is not str
                        or not isinstance(entry[1], list) or not isinstance(entry[3], list)):
                    raise PackageError("Malformed query rule")
                query_rules.append(QueryRule(_read_atom(entry[0], query=True),
                                              tuple(map(_read_node, entry[1])), entry[2],
                                              tuple(map(_read_term, entry[3]))))
            query_program = QueryProgram(tuple(query_rules), query["namespaces"], query["version"])
            plan(query_program, registry, relation_arities=_relation_arities(program))
            required = {str(node.operation) for rule in query_rules for node in rule.body
                        if isinstance(node, (Bind, Filter, ProviderScan))}
            if not required <= {uri for uri, _ in requirements}:
                raise PackageError("Query IR has undeclared operation requirements")
        triples = []
        for record in body["source"]:
            if not isinstance(record, list) or len(record) != 3:
                raise PackageError("Malformed source triple")
            triple = tuple(map(_read_term, record))
            if (not isinstance(triple[0], (URIRef, BNode)) or not isinstance(triple[1], URIRef)
                    or not isinstance(triple[2], (URIRef, BNode, Literal))):
                raise PackageError("Invalid RDF source triple")
            triples.append(triple)
        return CompiledPackage(program, query_program, tuple(requirements),
                               MappingProxyType(body["context"]), tuple(triples))
    except PackageError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as exc:
        raise PackageError(f"Invalid compiled package: {exc}") from exc
    finally:
        if owns_registry and registry is not None:
            registry.close()


def load(path, **options):
    path = Path(path)
    maximum = options.get("max_bytes", _MAX_BYTES) + _HEADER.size
    with path.open("rb") as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise PackageError("Package file exceeds byte limit")
    return loads(data, **options)


def dump(package, path, **options):
    Path(path).write_bytes(dumps(package, **options))


def dumps_native(package, **options):
    """Author a .dlpn artifact for the independent native loader."""
    from .native_package import dumps_native as author
    return author(package, **options)


def dump_native(package, path, **options):
    Path(path).write_bytes(dumps_native(package, **options))


def loads_native(data, **limits):
    """Validate/load/materialize a .dlpn package through the C++ runtime."""
    from .native_package import loads_native as read
    return read(data, **limits)


def load_native(path, **limits):
    from .native_package import load_native as read
    return read(path, **limits)


def main(argv=None):
    import argparse
    from .reasoner import read_graph
    parser = argparse.ArgumentParser(description="Compile and inspect portable DLP packages")
    commands = parser.add_subparsers(dest="command", required=True)
    compile_command = commands.add_parser("compile")
    compile_command.add_argument("ontologies", nargs="+")
    compile_command.add_argument("--profile", choices=("L0", "L1", "L2", "L3"), default="L2")
    compile_command.add_argument("--queries")
    compile_command.add_argument("--data-revision", required=True)
    compile_command.add_argument("--output", "-o", required=True)
    compile_command.add_argument("--format", choices=("portable", "native"), default="portable",
                                 help="portable=.dlppkg with optional query IR; native=.dlpn for C++/mobile")
    inspect_command = commands.add_parser("inspect")
    inspect_command.add_argument("path")
    native_command = commands.add_parser("run-native", help="Load and materialize a .dlpn artifact in C++")
    native_command.add_argument("path")
    args = parser.parse_args(argv)
    try:
        if args.command == "compile":
            graph = Graph()
            for path in args.ontologies:
                graph += read_graph(path)
            queries = Path(args.queries).read_text() if args.queries else None
            package = compile_package(graph, profile=args.profile, queries=queries,
                                      context={"data_revision": args.data_revision})
            (dump_native if args.format == "native" else dump)(package, args.output)
        elif args.command == "run-native":
            with load_native(args.path) as runtime:
                print(json.dumps({"format": "DLPNPKG1", "profile": runtime.program.profile,
                                  "complete": runtime.complete, "facts": len(runtime.facts),
                                  "violations": list(runtime.violations),
                                  "context": dict(runtime.package_context)}, indent=2))
            return 0
        else:
            package = load(args.path)
        print(json.dumps({"format": "DLPNPKG1" if args.command == "compile" and args.format == "native" else "dlp-compiled-v1", "profile": package.program.profile,
                          "rules": len(package.program.rules), "facts": len(package.program.facts),
                          "query_rules": len(package.query_program.rules) if package.query_program else 0,
                          "requirements": dict(package.requirements), "context": dict(package.context)}, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
