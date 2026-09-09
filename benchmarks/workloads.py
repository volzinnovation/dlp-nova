"""Deterministic benchmark inputs; no network or external datasets."""
import random

from rdflib import BNode, Graph, Namespace, OWL, RDF, RDFS

EX = Namespace("https://example.org/benchmark#")


def taxonomy(depth=3, individuals_per_class=3, variant="P0", branching=3, seed=2004):
    rng = random.Random(seed)
    graph = Graph()
    count = (branching ** (depth + 1) - 1) // (branching - 1)
    individuals = []
    expected_types = 0
    previous = EX.i0_0
    for index in range(count):
        cls = EX[f"C{index}"]
        graph.add((cls, RDF.type, OWL.Class))
        if index:
            parent = (index - 1) // branching
            graph.add((cls, RDFS.subClassOf, EX[f"C{parent}"]))
            level, ancestor = 0, index
            while ancestor:
                level += 1
                ancestor = (ancestor - 1) // branching
            for j in range(individuals_per_class):
                individual = EX[f"i{index}_{j}"]
                graph.add((individual, RDF.type, cls))
                individuals.append(individual)
                expected_types += level + 1
                if variant == "P1" and j % 3 == 2:
                    graph.add((individual, EX[f"p{index}"], previous))
                elif variant == "PF":
                    graph.add((individual, EX[f"p{rng.randrange(200)}"], previous))
                previous = individual
        if variant == "P1":
            graph.add((EX[f"p{index}"], RDF.type, OWL.ObjectProperty))
    if variant == "PF":
        for index in range(200):
            graph.add((EX[f"p{index}"], RDF.type, OWL.ObjectProperty))
    return graph, {"classes": count, "individuals": len(individuals),
                   "expected_class_facts": expected_types, "depth": depth,
                   "individuals_per_class": individuals_per_class, "variant": variant,
                   "branching": branching, "seed": seed}


def equality(size=300):
    graph = Graph()
    graph.add((EX.key, RDF.type, OWL.InverseFunctionalProperty))
    graph.add((EX.A, RDFS.subClassOf, EX.B))
    for i in range(size):
        graph.add((EX[f"a{i}"], EX.key, EX[f"k{i}"]))
        graph.add((EX[f"alias{i}"], EX.key, EX[f"k{i}"]))
        graph.add((EX[f"a{i}"], RDF.type, EX.A))
    return graph


def existential(size=100):
    graph = Graph()
    for i in range(4):
        restriction = BNode(f"r{i}")
        graph.add((EX[f"C{i}"], RDFS.subClassOf, restriction))
        graph.add((restriction, OWL.onProperty, EX.p))
        graph.add((restriction, OWL.someValuesFrom, EX[f"C{i+1}"]))
    for i in range(size):
        graph.add((EX[f"a{i}"], RDF.type, EX.C0))
    return graph


def transitive(size=100):
    graph = Graph()
    graph.add((EX.p, RDF.type, OWL.TransitiveProperty))
    for i in range(size):
        graph.add((EX[f"a{i}"], EX.p, EX[f"a{i+1}"]))
    return graph
