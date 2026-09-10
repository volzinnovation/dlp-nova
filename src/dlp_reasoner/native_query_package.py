"""Ahead-of-time encoder for the local-query records in DLPNPKG1.

This authoring module validates query IR and writes explicit little-endian wire
fields. It never loads a native library or serializes a ctypes structure layout.
Provider transport plans require a host capability and are rejected by this
initial standalone package profile.
"""
import struct

from rdflib import RDF, URIRef

from .domains import DomainRegistry
from .engine import _literal_key
from .model import EQ, NEQ, Var
from .query_ir import Aggregate, Bind, Filter, ProviderScan, RelationAtom, plan


class NativeQueryPackageError(ValueError):
    pass


def _predicate(value):
    return str(value) if str(value) in {EQ, NEQ} else value


def _prepared(query, program=None):
    for rule in query.rules:
        if any(isinstance(node, ProviderScan) for node in rule.body):
            raise NativeQueryPackageError("Native packages require local query plans; provider scans need a host adapter")
    registry = DomainRegistry()
    try:
        arities = {RDF.type: 2}
        if program is not None:
            for atom in (*program.facts, *(atom for rule in program.rules
                          for atom in (*rule.body, *((rule.head,) if rule.head else ())))):
                predicate = _predicate(atom.predicate)
                previous = arities.setdefault(predicate, len(atom.args))
                if previous != len(atom.args):
                    raise NativeQueryPackageError(f"Ontology relation {predicate} arity mismatch")
        prepared = plan(query, registry, relation_arities=arities)
        for rule in prepared.rules:
            for node in rule.body:
                if isinstance(node, (Bind, Filter)):
                    operation = registry.get(node.operation)
                    if not operation.opcode or operation.version != "1":
                        raise NativeQueryPackageError("Unsupported native query operation version")
        return prepared, registry
    except BaseException:
        registry.close()
        raise


def _unary_classes(program):
    return {atom.predicate for atom in (
        *program.facts,
        *(atom for rule in program.rules for atom in (*rule.body, *((rule.head,) if rule.head else ()))))
        if isinstance(atom.predicate, URIRef) and len(atom.args) == 1}


def query_symbols(query, program=None):
    """Return extra ground terms/predicates needed before assigning stable IDs."""
    prepared, registry = _prepared(query, program)
    terms, predicates = {RDF.type}, {RDF.type}
    try:
        for rule in prepared.rules:
            for node in (rule.head, *rule.body):
                actual = node.source if isinstance(node, Aggregate) else node
                if isinstance(actual, RelationAtom):
                    predicates.add(_predicate(actual.predicate))
                    if isinstance(actual.predicate, URIRef):
                        terms.add(actual.predicate)
                terms.update(term for term in actual.args if not isinstance(term, Var))
                if isinstance(node, Bind) and not isinstance(node.output, Var):
                    terms.add(node.output)
        if program is not None:
            terms.update(_unary_classes(program))
        return terms, predicates
    finally:
        registry.close()


def _text(value):
    data = value if isinstance(value, bytes) else value.encode("utf-8")
    if len(data) > 1024 * 1024:
        raise NativeQueryPackageError("Native query text exceeds one MiB")
    return struct.pack("<I", len(data)) + data


def encode_query_records(query, program, term_ids, predicate_ids):
    """Encode validated copied qx plans, typed metadata and RDF.type mappings.

    Record10: rule. Record11: term metadata including deterministic MIN identity
    keys. Record12: named unary ontology-predicate to class-term expansion.
    Constants refer to the package dictionary; variable slots are rule-local.
    """
    from .query_native import _term_metadata, term_order_keys, term_role_flags
    prepared, registry = _prepared(query, program)
    records = []
    try:
        literal_keys = {}
        for term, identifier in sorted(term_ids.items(), key=lambda pair: pair[1]):
            packed, decode_status, canonical = _term_metadata(term)
            key = _literal_key(term)
            group = {"number": 1, "boolean": 2, "string": 3, "lang": 4}.get(key[0], 0) if key else 0
            key_id = literal_keys.setdefault(key, len(literal_keys) + 1) if key else 0
            payload = struct.pack("<QiBIQ", identifier, decode_status, int(canonical), group, key_id)
            if decode_status == 0:
                payload += struct.pack("<IIqqqdd", packed.tag, packed.reserved,
                                       packed.a, packed.b, packed.c, packed.x, packed.y)
            identity, output_identity = term_order_keys(term)
            payload += _text(identity) + _text(output_identity)
            payload += struct.pack("<I", term_role_flags(term))
            records.append((11, payload))

        for stratum, rules in enumerate(prepared.strata):
            for rule in rules:
                variables = set(rule.given)
                for node in (rule.head, *rule.body):
                    actual = node.source if isinstance(node, Aggregate) else node
                    variables.update(t for t in actual.args if isinstance(t, Var))
                    if isinstance(node, Bind) and isinstance(node.output, Var):
                        variables.add(node.output)
                    if isinstance(node, Aggregate):
                        variables.update((*node.group_by, node.value, node.output))
                slots = {variable: i for i, variable in enumerate(sorted(variables, key=lambda v: v.name))}
                if len(slots) > 4096 or len(rule.body) > 10000:
                    raise NativeQueryPackageError("Native query slot/body limits exceeded")

                def arg(term):
                    return (struct.pack("<iQ", slots[term], 0) if isinstance(term, Var) else
                            struct.pack("<iQ", -1, term_ids[term]))

                payload = struct.pack("<QQI", stratum, predicate_ids[_predicate(rule.head.predicate)], len(rule.head.args))
                payload += b"".join(arg(term) for term in rule.head.args)
                payload += struct.pack("<I", len(slots))
                for variable in slots:
                    payload += _text(variable.name) + bytes([variable in rule.given])
                payload += struct.pack("<I", len(rule.body))
                for node in rule.body:
                    actual = node.source if isinstance(node, Aggregate) else node
                    opcode, predicate, groups, value_slot = 0, 0, (), -1
                    output = struct.pack("<iQ", -1, 0)
                    if isinstance(node, RelationAtom):
                        name = str(node.predicate)
                        kind = 1 if name == EQ else 2 if name == NEQ else 0
                        predicate = predicate_ids[_predicate(node.predicate)]
                    elif isinstance(node, Aggregate):
                        kind, predicate = 5, predicate_ids[_predicate(node.source.predicate)]
                        groups = tuple(slots[v] for v in node.group_by)
                        output, value_slot = arg(node.output), slots[node.value]
                    elif isinstance(node, (Bind, Filter)):
                        kind = 3 if isinstance(node, Filter) else 4
                        opcode = registry.get(node.operation).opcode
                        if isinstance(node, Bind):
                            output = arg(node.output)
                    else:
                        raise NativeQueryPackageError("Unsupported native query node")
                    payload += struct.pack("<IIQI", kind, opcode, predicate, len(actual.args))
                    payload += b"".join(arg(term) for term in actual.args)
                    payload += output + struct.pack("<I", len(groups))
                    payload += b"".join(struct.pack("<i", slot) for slot in groups)
                    payload += struct.pack("<i", value_slot)
                records.append((10, payload))

        classes = sorted(_unary_classes(program), key=str)
        expansion = struct.pack("<QI", predicate_ids[RDF.type], len(classes))
        for cls in classes:
            expansion += struct.pack("<QQ", predicate_ids[cls], term_ids[cls])
        records.append((12, expansion))
        return records
    except (KeyError, struct.error) as exc:
        raise NativeQueryPackageError(f"Incomplete/out-of-range native query dictionary: {exc}") from exc
    finally:
        registry.close()
