"""Regenerate examples/bach.owl from the source ontology examples/bach.ttl.

Run ``uv run python scripts/generate_bach_owl.py`` from the repository root.
Default paths are resolved relative to this script, so any working directory
works. Canonical blank nodes and sorted RDF/XML traversal keep output stable.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from rdflib import Graph
from rdflib.compare import isomorphic, to_canonical_graph


ROOT = Path(__file__).resolve().parents[1]


class OrderedGraph(Graph):
    """Give RDFLib's XML serializer deterministic subject and predicate order."""

    def subjects(self, *args, **kwargs):
        return iter(sorted(set(super().subjects(*args, **kwargs)), key=lambda term: term.n3()))

    def predicate_objects(self, *args, **kwargs):
        return iter(sorted(super().predicate_objects(*args, **kwargs),
                           key=lambda pair: tuple(term.n3() for term in pair)))


def render(source: Path) -> str:
    """Return verified RDF/XML without changing either source or destination."""
    graph = Graph().parse(source, format="turtle")
    ordered = OrderedGraph(bind_namespaces="none")
    for prefix, uri in sorted(graph.namespaces()):
        ordered.bind(prefix, uri)
    ordered += to_canonical_graph(graph)
    xml = ordered.serialize(format="xml")
    xml = xml.replace(
        "?>\n",
        "?>\n<!-- Generated from bach.ttl: RDFLib canonical blank nodes, sorted triples, RDF/XML.\n"
        "     Source: Volz (2004), Table 2.5, p. 35; DLP L3. -->\n",
        1,
    )
    if not isomorphic(graph, Graph().parse(data=xml, format="xml")):
        raise ValueError("Generated RDF/XML is not isomorphic to the Turtle source")
    return xml


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "examples" / "bach.ttl")
    parser.add_argument("--output", type=Path, default=ROOT / "examples" / "bach.owl")
    args = parser.parse_args(argv)
    xml = render(args.source)
    args.output.write_text(xml, encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
