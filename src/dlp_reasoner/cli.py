"""Command-line interface; exit codes: 0 success, 1 invalid, 2 inconsistent, 3 incomplete."""
from __future__ import annotations

import argparse
import json
import sys

from rdflib import URIRef

from .model import Atom, ProfileError, Skolem, Var
from .reasoner import Reasoner


_SCHEMA_QUERIES = {
    "equivalent-classes": ("equivalent_classes", ("left_class", "right_class")),
    "property-subsumes": ("property_subsumes", ("superproperty", "subproperty")),
    "equivalent-properties": ("equivalent_properties", ("left_property", "right_property")),
    "inverse-properties": ("inverse_properties", ("left_property", "right_property")),
    "is-symmetric": ("is_symmetric", ("property",)),
    "is-transitive": ("is_transitive", ("property",)),
    "has-domain": ("has_domain", ("property", "class_iri")),
    "has-range": ("has_range", ("property", "class_iri")),
}


def term_text(term):
    if isinstance(term, Var):
        return "?" + term.name
    if isinstance(term, Skolem):
        return term.symbol + "(" + ", ".join(map(term_text, term.args)) + ")"
    return term.n3() if hasattr(term, "n3") else str(term)


def atom_text(atom: Atom):
    return f"{term_text(atom.predicate)}({', '.join(map(term_text, atom.args))})"


def program_text(program):
    lines = ["# DLP " + program.profile + " Horn program"]
    for fact in sorted(program.facts, key=repr):
        lines.append(atom_text(fact) + ".")
    for rule in program.rules:
        head = atom_text(rule.head) if rule.head else "false"
        lines.append(head + (" :- " + ", ".join(map(atom_text, rule.body))
                             if rule.body else "") + ".")
    return "\n".join(lines) + "\n"


def parser():
    p = argparse.ArgumentParser(description="Volz thesis Description Logic Programs reasoner")
    sub = p.add_subparsers(dest="command", required=True)
    for command in ("validate", "materialize", "instances", "values", "types", "entails",
                    "subsumes", "rules", *_SCHEMA_QUERIES):
        item = sub.add_parser(command)
        item.add_argument("file", help="Local Turtle, RDF/XML, or N-Triples ontology")
        item.add_argument("--profile", choices=["L0", "L1", "L2", "L3"], default="L2")
        item.add_argument("--format", choices=["turtle", "nt", "xml", "n3"])
        item.add_argument("--strategy", choices=["semi-naive", "naive"], default="semi-naive")
        item.add_argument("--max-rounds", type=int, default=1000)
        item.add_argument("--max-facts", type=int, default=1000000)
        item.add_argument("--max-depth", type=int, default=32)
        if command == "materialize":
            item.add_argument("-o", "--output", required=True)
            item.add_argument("--output-format", choices=["turtle", "nt", "xml"], default="turtle")
            item.add_argument("--include-witnesses", action="store_true")
        elif command == "instances":
            item.add_argument("class_iri")
        elif command == "types":
            item.add_argument("subject")
        elif command == "values":
            item.add_argument("subject")
            item.add_argument("property")
        elif command == "entails":
            item.add_argument("subject")
            item.add_argument("property")
            item.add_argument("object", help="IRI, not a literal or blank node")
        elif command == "subsumes":
            item.add_argument("superclass")
            item.add_argument("subclass")
        elif command in _SCHEMA_QUERIES:
            for argument in _SCHEMA_QUERIES[command][1]:
                item.add_argument(argument)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        reasoner = Reasoner.from_file(
            args.file, format=args.format, profile=args.profile, strategy=args.strategy,
            max_rounds=args.max_rounds, max_facts=args.max_facts, max_depth=args.max_depth)
        if args.command == "rules":
            print(program_text(reasoner.program), end="")
            return 0
        if args.command == "validate":
            print(json.dumps(reasoner.stats, indent=2, sort_keys=True))
        elif reasoner.consistency != "consistent":
            print(json.dumps(reasoner.stats, indent=2, sort_keys=True))
        elif args.command == "materialize":
            reasoner.to_graph(include_witnesses=args.include_witnesses).serialize(
                destination=args.output, format=args.output_format)
            print(json.dumps(reasoner.stats, indent=2, sort_keys=True))
        else:
            if args.command == "instances":
                result = reasoner.instances(URIRef(args.class_iri))
            elif args.command == "types":
                result = reasoner.types(URIRef(args.subject))
            elif args.command == "values":
                result = reasoner.property_values(URIRef(args.subject), URIRef(args.property))
            elif args.command == "entails":
                result = reasoner.entails(*map(URIRef, (args.subject, args.property, args.object)))
            elif args.command in _SCHEMA_QUERIES:
                method, arguments = _SCHEMA_QUERIES[args.command]
                result = getattr(reasoner, method)(
                    *(URIRef(getattr(args, argument)) for argument in arguments))
            else:
                result = reasoner.subsumes(URIRef(args.superclass), URIRef(args.subclass))
            print(json.dumps(result if isinstance(result, bool) else sorted(map(str, result))))
        return 2 if reasoner.consistency == "inconsistent" else 3 if not reasoner.complete else 0
    except (ValueError, ProfileError, OSError, RuntimeError) as exc:
        print(json.dumps({"error": str(exc), "type": type(exc).__name__}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
