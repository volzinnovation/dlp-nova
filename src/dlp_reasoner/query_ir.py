"""Versioned query IR and conservative binding/stratification validation.

This module deliberately does not alter the thesis Horn-rule representation.
Operation descriptors are supplied by a registry; planning never evaluates them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from rdflib import Literal, URIRef, XSD

from .model import EQ, NEQ, ProfileError, Var


@dataclass(frozen=True)
class SourceLocation:
    source: str = "<string>"
    line: int = 1
    column: int = 1


class QueryLanguageError(ProfileError):
    def __init__(self, message, location=None):
        self.location = location
        self.message = message
        prefix = (f"{location.source}:{location.line}:{location.column}: " if location else "")
        super().__init__(prefix + message)


class QueryValidationError(QueryLanguageError):
    """A well-formed query uses an unsafe or unsupported execution plan."""


@dataclass(frozen=True)
class RelationAtom:
    predicate: URIRef
    args: tuple
    location: SourceLocation | None = field(default=None, compare=False, kw_only=True)


@dataclass(frozen=True)
class Filter:
    operation: URIRef
    args: tuple
    location: SourceLocation | None = field(default=None, compare=False, kw_only=True)


@dataclass(frozen=True)
class Bind:
    operation: URIRef
    args: tuple
    output: object
    location: SourceLocation | None = field(default=None, compare=False, kw_only=True)


@dataclass(frozen=True)
class Aggregate:
    source: RelationAtom
    group_by: tuple[Var, ...]
    value: Var
    output: Var
    kind: str = "min"
    location: SourceLocation | None = field(default=None, compare=False, kw_only=True)


@dataclass(frozen=True)
class ProviderScan:
    operation: URIRef
    args: tuple
    outputs: tuple[Var, ...]
    location: SourceLocation | None = field(default=None, compare=False, kw_only=True)


@dataclass(frozen=True)
class QueryRule:
    head: RelationAtom
    body: tuple
    label: str = ""
    given: tuple[Var, ...] = ()
    location: SourceLocation | None = field(default=None, compare=False, kw_only=True)


@dataclass(frozen=True)
class QueryProgram:
    rules: tuple[QueryRule, ...]
    namespaces: Mapping[str, str] = field(default_factory=dict)
    version: int = 1

    def __post_init__(self):
        object.__setattr__(self, "namespaces", MappingProxyType(dict(self.namespaces)))


def variables(terms):
    return {term for term in terms if isinstance(term, Var)}


def _term_data(term):
    if isinstance(term, Var):
        return {"variable": term.name}
    if isinstance(term, URIRef):
        return {"iri": str(term)}
    if isinstance(term, Literal):
        return {"literal": str(term), "datatype": str(term.datatype) if term.datatype else None,
                "language": term.language}
    return {"constant": str(term)}


def _node_data(node):
    result = {"kind": type(node).__name__}
    if isinstance(node, Aggregate):
        result.update(aggregate=node.kind, source=_node_data(node.source),
                      group_by=[v.name for v in node.group_by], value=node.value.name,
                      output=node.output.name)
    else:
        key = "predicate" if isinstance(node, RelationAtom) else "operation"
        result[key] = str(getattr(node, key))
        result["args"] = [_term_data(term) for term in node.args]
        if isinstance(node, Bind):
            result["output"] = _term_data(node.output)
        elif isinstance(node, ProviderScan):
            result["outputs"] = [v.name for v in node.outputs]
    return result


@dataclass(frozen=True)
class QueryPlan:
    program: QueryProgram
    rules: tuple[QueryRule, ...]
    strata: tuple[tuple[QueryRule, ...], ...]
    predicate_strata: Mapping[URIRef, int]
    recursive_predicates: frozenset[URIRef]

    def explain(self):
        return {"version": self.program.version,
                "recursive_predicates": sorted(map(str, self.recursive_predicates)),
                "strata": [{"level": level, "rules": [
                    {"label": rule.label, "given": [v.name for v in rule.given],
                     "head": _node_data(rule.head), "body": [_node_data(n) for n in rule.body]}
                    for rule in rules]} for level, rules in enumerate(self.strata)]}


_INTEGER_TYPES = {str(XSD[name]) for name in (
    "integer", "int", "long", "short", "byte", "nonPositiveInteger", "negativeInteger",
    "nonNegativeInteger", "positiveInteger", "unsignedLong", "unsignedInt", "unsignedShort",
    "unsignedByte")}


def _constant_type(term):
    if isinstance(term, URIRef):
        return "iri"
    if not isinstance(term, Literal):
        return None
    datatype = str(term.datatype or "")
    if datatype in _INTEGER_TYPES:
        return "integer"
    return {str(XSD.decimal): "decimal", str(XSD.double): "float", str(XSD.float): "float",
            str(XSD.boolean): "boolean", str(XSD.date): "date", str(XSD.dateTime): "instant",
            str(XSD.dateTimeStamp): "instant", str(XSD.time): "time",
            str(XSD.duration): "duration", str(XSD.dayTimeDuration): "duration",
            str(XSD.yearMonthDuration): "duration", str(XSD.string): "string",
            "": "string"}.get(datatype)


def _compatible(actual, expected):
    aliases = {"bool": "boolean", "number": "numeric", "double": "float",
               "any": "any", "term": "any"}
    actual, expected = aliases.get(actual, actual), aliases.get(expected, expected)
    if actual is None or expected == "any" or actual == expected:
        return True
    groups = {"numeric": {"integer", "decimal"},
              "coordinate": {"integer", "decimal", "float"},
              "comparable_numeric": {"integer", "decimal", "float"},
              "temporal": {"date", "instant", "time", "duration"},
              "endpoint": {"date", "instant"}, "policy": {"iri", "string", "policy"},
              "unit": {"iri", "string", "unit"}}
    # A broad operation result may narrow at runtime; reject only disjoint types.
    return bool(groups.get(actual, {actual}) & groups.get(expected, {expected}))


def plan(program, registry, *, relation_arities=None):
    """Validate and order version-1 rules, returning explicit evaluation strata.

    Registry.get(uri) must return descriptors with arity, input_types,
    result_type, required_positions and cardinality. Scans additionally may
    declare output_types; otherwise they have one output of result_type.
    Unknown operations fail here, never becoming ordinary stored relations.
    """
    def fail(message, node=None):
        raise QueryValidationError(message, getattr(node, "location", None))

    if not isinstance(program, QueryProgram) or type(program.version) is not int or program.version != 1:
        fail("Only query language version 1 is supported")
    arities = dict(relation_arities or {})
    definitions = {}
    for rule in program.rules:
        if not isinstance(rule, QueryRule) or not isinstance(rule.head, RelationAtom):
            fail("Expected QueryRule with a relation head", rule)
        if str(rule.head.predicate) in {EQ, NEQ}:
            fail("Equality/inequality cannot be query-rule heads", rule)
        if any(not isinstance(v, Var) for v in rule.given) or len(set(rule.given)) != len(rule.given):
            fail("given requires distinct variables", rule)
        old_given = definitions.setdefault(rule.head.predicate, rule.given)
        if old_given != rule.given:
            fail(f"Definitions of {rule.head.predicate} must have identical given parameters", rule)

    descriptors = {}

    def atom_check(atom):
        if not isinstance(atom, RelationAtom) or not isinstance(atom.predicate, (URIRef, str)):
            fail("Expected a named relation", atom)
        if any(not isinstance(t, (Var, URIRef, Literal)) for t in atom.args):
            fail("Relation arguments must be variables or RDF IRI/literal constants", atom)
        size = 2 if str(atom.predicate) in {EQ, NEQ} else len(atom.args)
        previous = arities.setdefault(atom.predicate, size)
        if previous != len(atom.args):
            fail(f"Relation {atom.predicate} arity mismatch: expected {previous}, got {len(atom.args)}",
                 atom)

    def operation_check(node):
        if any(not isinstance(t, (Var, URIRef, Literal)) for t in node.args):
            fail("Operation arguments must be variables or RDF IRI/literal constants", node)
        try:
            descriptor = registry.get(str(node.operation))
        except (KeyError, ValueError, RuntimeError) as exc:
            fail(f"Unavailable operation {node.operation}: {exc}", node)
        if descriptor is None:
            fail(f"Unavailable operation {node.operation}", node)
        if len(node.args) != descriptor.arity:
            fail(f"Operation {node.operation} arity mismatch: expected {descriptor.arity}, "
                 f"got {len(node.args)}", node)
        if len(descriptor.input_types) != descriptor.arity:
            fail(f"Invalid registry descriptor for {node.operation}", node)
        required = descriptor.required_positions
        if any(type(i) is not int or not 0 <= i < len(node.args) for i in required):
            fail(f"Invalid required positions for {node.operation}", node)
        if isinstance(node, Filter) and descriptor.result_type not in {"bool", "boolean"}:
            fail(f"Filter {node.operation} must return a Boolean", node)
        if isinstance(node, ProviderScan):
            if descriptor.cardinality != "many":
                fail(f"Scan {node.operation} requires a many-row provider descriptor", node)
            outputs = getattr(descriptor, "output_types", (descriptor.result_type,))
            if len(node.outputs) != len(outputs):
                fail(f"Scan {node.operation} output arity mismatch", node)
            if not node.outputs or any(not isinstance(v, Var) for v in node.outputs):
                fail("Scan outputs must be variables", node)
        elif descriptor.cardinality not in {"one", "zero_or_one"}:
            fail(f"Scalar operation {node.operation} has non-scalar cardinality", node)
        if isinstance(node, Bind) and not isinstance(node.output, (Var, URIRef, Literal)):
            fail("Bind output must be a variable or RDF constant", node)
        descriptors[id(node)] = descriptor

    edges = []  # (head, source, strict boundary, diagnostic node)
    reordered = []
    for rule in program.rules:
        atom_check(rule.head)
        given = set(rule.given)
        for node in rule.body:
            if isinstance(node, (Filter, Bind, ProviderScan)):
                operation_check(node)
        generating = any(
            isinstance(node, (Bind, ProviderScan)) or
            (isinstance(node, Filter) and
             getattr(descriptors[id(node)], "determinism", "pure") != "pure")
            for node in rule.body)
        for node in rule.body:
            if isinstance(node, RelationAtom):
                atom_check(node)
                dependency = node
            elif isinstance(node, Aggregate):
                atom_check(node.source)
                if str(node.source.predicate) in {EQ, NEQ}:
                    fail("Aggregate source must be a stored/derived relation", node)
                if node.kind != "min":
                    fail("Only MIN aggregates are supported", node)
                if (any(not isinstance(v, Var) for v in node.group_by)
                        or len(set(node.group_by)) != len(node.group_by)
                        or not isinstance(node.value, Var) or not isinstance(node.output, Var)):
                    fail("MIN group/value/output positions require distinct group variables", node)
                if not (set(node.group_by) | {node.value}) <= variables(node.source.args):
                    fail("MIN value and group variables must occur in its source", node)
                if node.output in variables(node.source.args):
                    fail("MIN output must be distinct from source variables", node)
                dependency = node.source
            elif isinstance(node, (Filter, Bind, ProviderScan)):
                continue
            else:
                fail(f"Unsupported query body node {type(node).__name__}", rule)
            inherited = set(definitions.get(dependency.predicate, ()))
            if not inherited <= given:
                missing = ", ".join("?" + v.name for v in sorted(inherited - given, key=lambda v: v.name))
                fail(f"Calling {dependency.predicate} requires given parameters {missing}", node)
            if str(dependency.predicate) not in {EQ, NEQ}:
                edges.append((rule.head.predicate, dependency.predicate,
                              isinstance(node, Aggregate) or generating, node))

        bound = set(given)
        types = {}
        pending = list(rule.body)
        body = []
        while pending:
            def ready(node):
                if isinstance(node, RelationAtom):
                    needed = variables(node.args)
                    if str(node.predicate) == NEQ:
                        return needed <= bound
                    if str(node.predicate) == EQ:
                        return not needed or any(not isinstance(t, Var) or t in bound
                                                for t in node.args)
                    return True
                if isinstance(node, Aggregate):
                    # A whole-relation group MIN exports only group/output slots.
                    # Other source vars must remain local, avoiding correlated MIN.
                    return not ((variables(node.source.args) - set(node.group_by)) & (bound - given))
                return variables(node.args) <= bound

            eligible = [node for node in pending if ready(node)]
            if not eligible:
                fail(f"Rule {rule.label or rule.head.predicate} has unbound operation inputs "
                     "or a correlated aggregate source", pending[0])
            # Prefer a ready filter; other nodes retain source order for predictable plans.
            node = next((n for n in eligible if isinstance(n, Filter)), eligible[0])
            pending.remove(node)
            if isinstance(node, RelationAtom):
                bound.update(variables(node.args))
                if str(node.predicate) == EQ:
                    known = next((types.get(t) if isinstance(t, Var) else _constant_type(t)
                                  for t in node.args
                                  if (types.get(t) if isinstance(t, Var) else _constant_type(t))), None)
                    if known:
                        for term in variables(node.args):
                            types.setdefault(term, known)
            elif isinstance(node, Aggregate):
                bound.update(node.group_by)
                bound.add(node.output)
            else:
                descriptor = descriptors[id(node)]
                for term, expected in zip(node.args, descriptor.input_types):
                    actual = types.get(term) if isinstance(term, Var) else _constant_type(term)
                    if not _compatible(actual, expected):
                        fail(f"Operation {node.operation} expects {expected}, got {actual}", node)
                    if isinstance(term, Var):
                        types.setdefault(term, expected)
                pairs = ([(node.output, descriptor.result_type)] if isinstance(node, Bind) else
                         list(zip(node.outputs, getattr(descriptor, "output_types",
                                                        (descriptor.result_type,))))
                         if isinstance(node, ProviderScan) else [])
                for term, result_type in pairs:
                    actual = types.get(term) if isinstance(term, Var) else _constant_type(term)
                    if not _compatible(actual, result_type):
                        fail(f"Output of {node.operation} conflicts with {actual}", node)
                    if isinstance(term, Var):
                        bound.add(term)
                        types[term] = result_type
            body.append(node)
        unsafe = variables(rule.head.args) - bound
        if unsafe:
            names = ", ".join("?" + v.name for v in sorted(unsafe, key=lambda v: v.name))
            fail(f"Unsafe head variables: {names}", rule)
        reordered.append(QueryRule(rule.head, tuple(body), rule.label, rule.given,
                                   location=rule.location))

    # Longest-path constraints detect a cycle that crosses a strict boundary.
    # Pure positive SCCs have zero weight and converge without raising levels.
    predicates = set(arities)
    levels = dict.fromkeys(predicates, 0)
    for iteration in range(len(predicates) + 1):
        changed = False
        for head, source, strict, node in edges:
            required_level = levels[source] + int(strict)
            if levels[head] < required_level:
                levels[head] = required_level
                changed = True
                if iteration == len(predicates):
                    fail("Dependency cycle crosses an aggregate, Bind, scan or non-pure filter boundary", node)
        if not changed:
            break
    # A reachability check records positive recursion without rejecting it.
    graph = {p: set() for p in predicates}
    for head, source, _, _ in edges:
        graph[head].add(source)
    recursive = set()
    for predicate in predicates:
        pending = list(graph[predicate])
        seen = set()
        while pending:
            item = pending.pop()
            if item == predicate:
                recursive.add(predicate)
                break
            if item not in seen:
                seen.add(item)
                pending.extend(graph[item])
    count = max((levels[rule.head.predicate] for rule in reordered), default=-1) + 1
    strata = tuple(tuple(rule for rule in reordered if levels[rule.head.predicate] == level)
                   for level in range(count))
    return QueryPlan(program, tuple(rule for group in strata for rule in group), strata,
                     MappingProxyType(levels), frozenset(recursive))
