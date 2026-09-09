"""Run the Bach family example through unchanged native ZodiacEdge APIs.

The contract is the complete positive family example in chapter 6, not the
existential/constraint ontology in Table 2.5. Only its two object properties are
represented as relations. RDF annotations and vocabulary declarations do not
become relation tuples. No inference is performed during input translation.

Each worker runs one independent scenario from the original input. The native
API has separate fact deletion and insertion methods, so a mixed replacement
uses both calls, with no intervening query; it is not an atomic transaction.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import resource
import sys
import time

from rdflib import Graph, OWL, RDF, RDFS, URIRef

from benchmarks.bach import BACH, QUERY_FILE, compact, reachability, term
from benchmarks.lubm import require
from benchmarks.zodiac_native import (encode_constant, native_api, native_closure,
                                      rule_text, translated_input, tuple_record)
from dlp_reasoner.model import Atom, Rule, Var

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "examples/bach-family.ttl"
ANCESTOR = str(BACH.ancestorOf)
DYNASTY = str(BACH.inDynasty)
SCENARIOS = ("initial", "fact-replace", "rule-remove", "symmetry-insert")
X, Y, Z = (Var(name) for name in "xyz")


def relation(predicate, *values):
    return Atom(str(predicate), values)


TRANSITIVE = Rule(relation(ANCESTOR, X, Z),
                  (relation(ANCESTOR, X, Y), relation(ANCESTOR, Y, Z)))
INCLUSION = Rule(relation(DYNASTY, X, Y), (relation(ANCESTOR, X, Y),))
SYMMETRY = Rule(relation(DYNASTY, Y, X), (relation(DYNASTY, X, Y),))
OLD_EDGE = relation(ANCESTOR, BACH["johann-sebastian"], BACH["wilhelm-friedemann"])
NEW_EDGE = relation(ANCESTOR, BACH["johann-sebastian"], BACH["johann-christian"])


@dataclass(frozen=True)
class FamilyInput:
    facts: frozenset[Atom]
    rules: tuple[Rule, ...]
    queries: tuple[dict, ...]
    source_sha256: str
    source_triples: int
    query_manifest_sha256: str


class NativeBachMismatch(RuntimeError):
    """Preserve a native correctness failure instead of reporting a speedup."""

    def __init__(self, state, actual, expected, queries):
        self.details = {
            "state": state,
            "missing": sorted([[str(f.predicate), compact(f.args)] for f in expected - actual]),
            "unexpected": sorted([[str(f.predicate), compact(f.args)] for f in actual - expected]),
            "actual_closure": tuple_record(actual), "expected_closure": tuple_record(expected),
            "queries": queries,
        }
        super().__init__("Native Bach closure differs: " + json.dumps(self.details, sort_keys=True))


def prepare_family(source=SOURCE, queries=None, require_original=False):
    """Parse a family snapshot and translate its axioms without deriving facts."""
    source = Path(source)
    payload = source.read_bytes()
    graph = Graph().parse(source)
    semantic = set()
    facts = set()
    metadata_types = {OWL.Ontology, OWL.ObjectProperty}
    for subject, predicate, obj in graph:
        if predicate in (RDFS.label, RDFS.comment):
            continue
        if predicate == RDF.type and obj in metadata_types:
            continue
        if predicate == RDF.type and obj == OWL.TransitiveProperty and subject == BACH.ancestorOf:
            semantic.add(TRANSITIVE)
        elif predicate == RDF.type and obj == OWL.SymmetricProperty and subject == BACH.inDynasty:
            semantic.add(SYMMETRY)
        elif (subject, predicate, obj) == (BACH.ancestorOf, RDFS.subPropertyOf, BACH.inDynasty):
            semantic.add(INCLUSION)
        elif predicate == BACH.ancestorOf:
            require(isinstance(subject, URIRef) and isinstance(obj, URIRef),
                    "Bach family assertions must connect named individuals")
            facts.add(relation(ANCESTOR, subject, obj))
        else:
            raise ValueError("Outside the positive Bach family contract: " + repr((subject, predicate, obj)))
    require(TRANSITIVE in semantic, "The family requires ancestor transitivity")
    if require_original:
        require(semantic == {TRANSITIVE, INCLUSION}, "The original family requires exactly T0 and T1")
        require(OLD_EDGE in facts and NEW_EDGE not in facts, "The original family update context differs")
    manifest_payload = QUERY_FILE.read_bytes()
    if queries is None:
        queries = [q for q in json.loads(manifest_payload)["queries"] if q["variant"] == "family"]
    require(len({q["id"] for q in queries}) == len(queries), "Duplicate family query identifiers")
    rules = tuple(rule for rule in (TRANSITIVE, INCLUSION, SYMMETRY) if rule in semantic)
    return FamilyInput(frozenset(facts), rules, tuple(queries),
                       hashlib.sha256(payload).hexdigest(), len(graph),
                       hashlib.sha256(manifest_payload).hexdigest())


def expected_closure(facts, rules):
    """Independent graph-traversal oracle; used only after timed engine calls."""
    require(set(rules) <= {TRANSITIVE, INCLUSION, SYMMETRY} and TRANSITIVE in rules,
            "Oracle covers only the Bach family rules")
    edges = {fact.args for fact in facts}
    require(all(fact.predicate == ANCESTOR and len(fact.args) == 2 for fact in facts),
            "Oracle expects asserted ancestor pairs")
    ancestors = reachability(edges)
    dynasty = ancestors if INCLUSION in rules else set()
    if SYMMETRY in rules:
        dynasty = dynasty | {(right, left) for left, right in dynasty}
    return {relation(ANCESTOR, *edge) for edge in ancestors} | {
        relation(DYNASTY, *edge) for edge in dynasty}


def _data_store(api, native_facts):
    data = api["DataStore"]()
    for triple in native_facts:
        data.add(*triple)
    return data


def _native_atom(api, atom, constants):
    require(atom.predicate in (ANCESTOR, DYNASTY) and len(atom.args) == 2,
            "Only the family binary properties are supported")
    values = []
    for value in atom.args:
        encoded = encode_constant(value)
        require(encoded not in constants or constants[encoded] == value, "RDF encoding collision")
        constants[encoded] = value
        values.append(api["Term"].getTerm(encoded, "constant"))
    return (values[0], api["Term"].getTerm(atom.predicate, "constant"), values[1])


def _query_pattern(api, program, constants, predicate, left=None, right=None):
    """Consume the author's query result, decode RDF terms, and apply set semantics."""
    require(str(predicate) in (ANCESTOR, DYNASTY), "Query predicate outside family contract")
    def parameter(value, name):
        if value is None:
            return api["Term"].getTerm(name, "variable")
        return api["Term"].getTerm(encode_constant(value), "constant")
    result = program.query(parameter(left, "?bach_query_left"),
                           api["Term"].getTerm(str(predicate), "constant"),
                           parameter(right, "?bach_query_right"))
    if left is not None and right is not None:
        require(result is None or isinstance(result, bool), "Native ground query returned bindings")
        return bool(result)
    if not result:
        return set()
    require(not isinstance(result, bool), "Native variable query returned a boolean")
    width = int(left is None) + int(right is None)
    require(len(result.variables) == width, "Native query binding width differs")
    rows = set()
    for row in result.res:
        require(len(row) == width, "Native query row width differs")
        values = tuple(constants[value.name] for value in row)
        rows.add(values[0] if width == 1 else values)
    return rows


def _schema_probe(api, rules, method, arguments):
    """Use canonical fresh facts, not observed family pairs, for universal queries.

    For these equality-free positive rules, failure to derive the tested edge
    in the finite least model supplies a countermodel to the queried universal
    implication. Fresh terms are distinct from the original individuals. This
    is a query reduction to native reasoning, not an OWL interface supplied by
    ZodiacEdge. Its conversion, construction, and reasoning are timed as query
    work by the caller.
    """
    a, b, c = (URIRef("urn:bach:zodiac:universal-probe:" + name) for name in "abc")
    if method == "is_symmetric":
        predicate, = arguments
        facts, goal = {relation(predicate, a, b)}, relation(predicate, b, a)
    elif method == "is_transitive":
        predicate, = arguments
        facts = {relation(predicate, a, b), relation(predicate, b, c)}
        goal = relation(predicate, a, c)
    elif method == "property_subsumes":
        sup, sub = arguments
        facts, goal = {relation(sub, a, b)}, relation(sup, a, b)
    else:
        raise ValueError("Unsupported schema query: " + method)
    # Translate only the active rules. The query may mention a property with no
    # current defining rule; its known binary arity does not require adding rules.
    native = {rule: api["parse_rule"](rule_text(rule)) for rule in rules}
    constants = {}
    triples = [_native_atom(api, fact, constants) for fact in facts]
    probe = api["Program"](data=_data_store(api, triples), rules={native[r] for r in rules})
    return _query_pattern(api, probe, constants, goal.predicate, *goal.args)


def evaluate_query(api, program, constants, rules, query):
    arguments = [term(value) for value in query["arguments"]]
    method = query["method"]
    if method == "property_values":
        subject, predicate = arguments
        return _query_pattern(api, program, constants, predicate, left=subject)
    if method == "property_pairs":
        predicate, = arguments
        return _query_pattern(api, program, constants, predicate)
    if method == "entails":
        subject, predicate, obj = arguments
        return _query_pattern(api, program, constants, predicate, subject, obj)
    if method in ("is_symmetric", "is_transitive", "property_subsumes"):
        return _schema_probe(api, rules, method, arguments)
    raise ValueError("Unsupported native Bach query: " + method)


def _oracle_answer(closure, rules, query):
    """Check named answers and the finite family schema independently of native APIs."""
    args = [term(value) for value in query["arguments"]]
    method = query["method"]
    if method == "property_values":
        subject, predicate = args
        return {fact.args[1] for fact in closure if fact.predicate == str(predicate)
                and fact.args[0] == subject}
    if method == "property_pairs":
        return {fact.args for fact in closure if fact.predicate == str(args[0])}
    if method == "entails":
        subject, predicate, obj = args
        return relation(predicate, subject, obj) in closure
    if method == "is_symmetric":
        return str(args[0]) == DYNASTY and SYMMETRY in rules
    if method == "is_transitive":
        return str(args[0]) == ANCESTOR and TRANSITIVE in rules
    if method == "property_subsumes":
        sup, sub = map(str, args)
        return sup == sub or (sup == DYNASTY and sub == ANCESTOR and INCLUSION in rules)
    raise ValueError("Unsupported oracle query: " + method)


def family_worker(native_cache, source=SOURCE, scenario="initial", queries=None,
                  expected_states=None, prepared=None):
    """Run one native scenario and return phase times, complete answers, and checks.

    Optional ``prepared`` is a FamilyInput from prepare_family; its input loading
    is then outside this worker's task clock and reported as such. A caller may
    provide expected_states mapping state names to tuple_record dictionaries;
    the independent reachability check remains mandatory. Every changing
    scenario restores the original state after its primary update.
    """
    require(scenario in SCENARIOS, "Unknown Bach native scenario")
    worker_started = time.perf_counter()
    started = time.perf_counter()
    api = native_api(Path(native_cache))
    bootstrap_seconds = time.perf_counter() - started
    started = time.perf_counter()
    input_was_prepared = prepared is not None
    prepared = (prepare_family(source, queries, require_original=scenario != "initial")
                if prepared is None else prepared)
    input_seconds = time.perf_counter() - started
    require(isinstance(prepared, FamilyInput), "Expected a prepared FamilyInput")
    active_facts, active_rules = set(prepared.facts), set(prepared.rules)
    if scenario != "initial":
        require(active_rules == {TRANSITIVE, INCLUSION}
                and OLD_EDGE in active_facts and NEW_EDGE not in active_facts,
                "Incremental scenarios must start from the original family")
    started = time.perf_counter()
    native_rules, native_facts, constants, arities = translated_input(api, prepared.rules, active_facts)
    arities.update({ANCESTOR: 2, DYNASTY: 2})
    conversion_seconds = time.perf_counter() - started
    started = time.perf_counter()
    data = _data_store(api, native_facts)
    require(len(data) == len(active_facts), "Native input lost family assertions")
    index_seconds = time.perf_counter() - started
    started = time.perf_counter()
    program = api["Program"](data=data, rules={native_rules[r] for r in active_rules})
    initial_reasoning_seconds = time.perf_counter() - started
    states = []
    correctness_seconds = 0.0

    def observe(name):
        nonlocal correctness_seconds
        observations = []
        for query in prepared.queries:
            started = time.perf_counter()
            answer = compact(evaluate_query(api, program, constants, active_rules, query))
            elapsed = time.perf_counter() - started
            observations.append({"id": query["id"], "method": query["method"],
                                 "seconds": elapsed, "answer": answer})
        query_seconds = sum(q["seconds"] for q in observations)
        started = time.perf_counter()
        actual = native_closure(program, constants, arities)
        expected = expected_closure(active_facts, active_rules)
        if actual != expected:
            raise NativeBachMismatch(name, actual, expected, observations)
        record = tuple_record(actual)
        if expected_states is not None:
            require(name in expected_states and record == expected_states[name],
                    "Native closure differs from supplied state contract: " + name)
        for query, observation in zip(prepared.queries, observations, strict=True):
            answer = compact(_oracle_answer(expected, active_rules, query))
            require(observation["answer"] == answer, "Native Bach query differs: " + query["id"])
            if name in ("initial", "restored") and "expected" in query:
                # Some original manifest lists are not lexicographically ordered.
                saved = query["expected"]
                if isinstance(saved, list):
                    saved = sorted(saved, key=lambda item: json.dumps(item))
                require(answer == saved, "Source manifest differs: " + query["id"])
            observation["exact_match"] = True
        correctness_seconds += time.perf_counter() - started
        return {"state": name, "closure": record,
                "ancestor_pairs": compact({f.args for f in actual if f.predicate == ANCESTOR}),
                "dynasty_pairs": compact({f.args for f in actual if f.predicate == DYNASTY}),
                "queries": observations, "query_seconds": query_seconds,
                "exact_closure_match": True, "all_queries_match": True}

    initial = observe("initial")
    initial.update(input_seconds=input_seconds, conversion_seconds=conversion_seconds,
                   input_index_seconds=index_seconds, reasoning_seconds=initial_reasoning_seconds)
    initial["task_seconds"] = (input_seconds + conversion_seconds + index_seconds
                               + initial_reasoning_seconds + initial["query_seconds"])
    states.append(initial)
    actions = {
        "initial": [],
        "fact-replace": [("updated", "facts", OLD_EDGE, NEW_EDGE),
                         ("restored", "facts", NEW_EDGE, OLD_EDGE)],
        "rule-remove": [("updated", "delete_rule", INCLUSION, None),
                        ("restored", "add_rule", INCLUSION, None)],
        "symmetry-insert": [("updated", "add_rule", SYMMETRY, None),
                            ("restored", "delete_rule", SYMMETRY, None)],
    }[scenario]
    for name, operation, old, new in actions:
        started = time.perf_counter()
        if operation == "facts":
            remove_store = _data_store(api, [_native_atom(api, old, constants)])
            add_store = _data_store(api, [_native_atom(api, new, constants)])
        else:
            changed = {api["parse_rule"](rule_text(old))}
        update_conversion = time.perf_counter() - started
        started = time.perf_counter()
        if operation == "facts":
            program.delete_data(remove_store)
            program.add_data(add_store)
        elif operation == "delete_rule":
            program.delete_rules(changed)
        else:
            program.add_rules(changed)
        update_seconds = time.perf_counter() - started
        if operation == "facts":
            active_facts.remove(old)
            active_facts.add(new)
        elif operation == "delete_rule":
            active_rules.remove(old)
        else:
            active_rules.add(old)
        state = observe(name)
        state.update(operation=operation, conversion_seconds=update_conversion,
                     update_seconds=update_seconds)
        state["task_seconds"] = update_conversion + update_seconds + state["query_seconds"]
        states.append(state)
    return {
        "arm": "zodiac-native", "scenario": scenario,
        "source_sha256": prepared.source_sha256,
        "source_triples": prepared.source_triples,
        "query_manifest_sha256": prepared.query_manifest_sha256,
        "query_contract_sha256": hashlib.sha256(json.dumps(
            prepared.queries, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "input_assertions": len(prepared.facts), "initial_rules": len(prepared.rules),
        "input_was_prepared": input_was_prepared,
        "native_bootstrap_seconds": bootstrap_seconds,
        "states": states, "full_task_seconds": sum(s["task_seconds"] for s in states),
        "correctness_seconds": correctness_seconds,
        "worker_body_seconds": time.perf_counter() - worker_started,
        "all_exact_matches": True,
        "fact_replacement_atomic": False,
        "schema_query_method": "fresh canonical positive-rule probes via native Program",
        "timing_boundary": "task includes RDF input loading unless prepared, native conversion, "
                           "indexing, reasoning or update, and fully consumed queries; native "
                           "bootstrap/source verification and correctness checks are separate",
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                          * (1 if sys.platform == "darwin" else 1024),
    }


def static_worker(native_cache, ontology_path, queries, expected_states=None):
    """Materialize one complete scenario RDF file and answer its query contract."""
    return family_worker(native_cache, ontology_path, "initial", queries, expected_states)


def incremental_worker(native_cache, original_path, scenario, queries, expected_states=None):
    """Update the original family, answer queries, then restore its original state."""
    require(scenario != "initial", "Use static_worker for an unchanged snapshot")
    return family_worker(native_cache, original_path, scenario, queries, expected_states)


def direct_native_deletion_check(native_cache):
    """Untimed native-API reproducer, with no compiler or schema-query adapter.

    This independently encodes the nine source edges and the two source rules,
    and queries the retained Johannes--Wilhelm consequence directly after the
    deletion and insertion calls. In particular, no canonical schema probe is
    created. A false answer after deletion exposes loss of the other branch.
    """
    api = native_api(Path(native_cache))
    terms = api["Term"]
    names = {short: BACH[name] for short, name in (
        ("j", "johannes"), ("h", "heinrich"), ("c", "christoph"),
        ("jc1", "johann-christoph"), ("jm", "johann-michael"),
        ("mb", "maria-barbara"), ("wf", "wilhelm-friedemann"),
        ("js", "johann-sebastian"), ("ja", "johann-ambrosius"),
        ("jc2", "johann-christian"))}
    constants = {short: terms.getTerm(encode_constant(iri), "constant") for short, iri in names.items()}
    ancestor = terms.getTerm(ANCESTOR, "constant")
    dynasty = terms.getTerm(DYNASTY, "constant")
    rules = {
        api["parse_rule"](f"<{ANCESTOR}>(?x, ?z) :- <{ANCESTOR}>(?x, ?y) and <{ANCESTOR}>(?y, ?z) ."),
        api["parse_rule"](f"<{DYNASTY}>(?x, ?y) :- <{ANCESTOR}>(?x, ?y) ."),
    }
    data = api["DataStore"]()
    for left, right in (("j", "h"), ("j", "c"), ("h", "jc1"), ("jc1", "jm"),
                        ("jm", "mb"), ("mb", "wf"), ("js", "wf"), ("ja", "js"), ("c", "ja")):
        data.add(constants[left], ancestor, constants[right])
    program = api["Program"](data=data, rules=rules)

    def check():
        return {"ancestorOf": bool(program.query(constants["j"], ancestor, constants["wf"])),
                "inDynasty": bool(program.query(constants["j"], dynasty, constants["wf"]))}

    result = {"initial": check()}
    deleting = api["DataStore"]()
    deleting.add(constants["js"], ancestor, constants["wf"])
    program.delete_data(deleting)
    result["after_delete"] = check()
    adding = api["DataStore"]()
    adding.add(constants["js"], ancestor, constants["jc2"])
    program.add_data(adding)
    result["after_insert"] = check()
    result["expected_all_states"] = {"ancestorOf": True, "inDynasty": True}
    result["retained_asserted_path"] = [str(names[n]) for n in ("j", "h", "jc1", "jm", "mb", "wf")]
    result["missing_named_consequences"] = {
        state: [[str(names["j"]), str(BACH[predicate]), str(names["wf"])]
                for predicate, answer in result[state].items() if not answer]
        for state in ("initial", "after_delete", "after_insert")}
    return result
