"""Deterministic benchmark inputs; no network or external datasets."""
import random

from rdflib import BNode, Graph, Literal, Namespace, OWL, RDF, RDFS, XSD

EX = Namespace("https://example.org/benchmark#")


def taxonomy(depth=3, individuals_per_class=3, variant="P0", branching=3, seed=2004,
             include_root=False):
    if depth < 1 or individuals_per_class < 1 or branching < 2:
        raise ValueError("Use positive depth/population and branching >= 2")
    if variant not in {"P0", "P1", "PF"}:
        raise ValueError("Unknown property variant")
    rng = random.Random(seed)
    graph = Graph()
    count = (branching ** (depth + 1) - 1) // (branching - 1)
    individuals = []
    expected_types = 0
    previous = None
    property_fillers = 0
    for index in range(count):
        cls = EX[f"C{index}"]
        graph.add((cls, RDF.type, OWL.Class))
        if index:
            parent = (index - 1) // branching
            graph.add((cls, RDFS.subClassOf, EX[f"C{parent}"]))
        if index or include_root:
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
                    graph.add((individual, EX[f"p{index}"], previous or individual))
                    property_fillers += 1
                elif variant == "PF":
                    graph.add((individual, EX[f"p{rng.randrange(200)}"], previous or individual))
                    property_fillers += 1
                previous = individual
        if variant == "P1":
            graph.add((EX[f"p{index}"], RDF.type, OWL.ObjectProperty))
    if variant == "PF":
        for index in range(200):
            graph.add((EX[f"p{index}"], RDF.type, OWL.ObjectProperty))
    return graph, {"classes": count, "individuals": len(individuals),
                   "expected_class_facts": expected_types, "depth": depth,
                   "individuals_per_class": individuals_per_class, "variant": variant,
                   "branching": branching, "seed": seed, "include_root": include_root,
                   "property_fillers": property_fillers}


def cardinality_taxonomy(depth=3, individuals_per_class=3):
    """Section 8.5.2 with the corrected 2:1 maximum-one/minimum-zero counts.

    Each internal class restricts its property's range to its first child. The
    first and third children have maximum one; the second has minimum zero.
    Two distinct filler names per directly restricted subject force equality.
    This deterministic ABox makes the equality workload explicit; it is not a
    reconstruction of the unavailable historical generator.
    """
    graph, meta = taxonomy(depth, individuals_per_class)
    internal = (3**depth - 1) // 2
    for parent in range(internal):
        prop = EX[f"cardinality_p{parent}"]
        universal = BNode(f"universal_{parent}")
        graph.add((EX[f"C{parent}"], RDFS.subClassOf, universal))
        graph.add((universal, RDF.type, OWL.Restriction))
        graph.add((universal, OWL.onProperty, prop))
        graph.add((universal, OWL.allValuesFrom, EX[f"C{3 * parent + 1}"]))
        for offset in range(1, 4):
            child = 3 * parent + offset
            restriction = BNode(f"cardinality_{child}")
            graph.add((EX[f"C{child}"], RDFS.subClassOf, restriction))
            graph.add((restriction, RDF.type, OWL.Restriction))
            graph.add((restriction, OWL.onProperty, prop))
            constructor = OWL.minCardinality if offset == 2 else OWL.maxCardinality
            bound = 0 if offset == 2 else 1
            graph.add((restriction, constructor, Literal(bound, datatype=XSD.nonNegativeInteger)))
            if offset == 2:
                continue
            level, ancestor = 0, child
            while ancestor:
                level += 1
                ancestor = (ancestor - 1) // 3
            for j in range(individuals_per_class):
                subject = EX[f"i{child}_{j}"]
                for side in ("left", "right"):
                    graph.add((subject, prop, EX[f"filler_{child}_{j}_{side}"]))
                # Both filler names denote one canonical individual, belonging
                # to the first child and its ancestors through the universal.
                meta["expected_class_facts"] += level + 1
    groups = 2 * internal * individuals_per_class
    meta.update(
        universal_restrictions=internal, maximum_one_restrictions=2 * internal,
        minimum_zero_restrictions=internal, equality_groups=groups,
        named_fillers=2 * groups, expected_root_answers=meta["individuals"] + 2 * groups,
        property_fillers=2 * groups, expected_equality_merges=groups,
    )
    return graph, meta


def _rdf_list(graph, values, prefix):
    cells = [BNode(f"{prefix}_{i}") for i in range(len(values))]
    for i, value in enumerate(values):
        graph.add((cells[i], RDF.first, value))
        graph.add((cells[i], RDF.rest, cells[i + 1] if i + 1 < len(cells) else RDF.nil))
    return cells[0] if cells else RDF.nil


def factored_unions(pairs=16, individuals=128):
    """Linear-size conjunction of binary unions; explicit DNF has 2**pairs branches."""
    if pairs < 1 or individuals < 1:
        raise ValueError("Use at least one pair and one individual")
    graph = Graph()
    unions = []
    for i in range(pairs):
        union = BNode(f"union_{i}")
        graph.add((union, OWL.unionOf, _rdf_list(graph, [EX[f"A{i}"], EX[f"B{i}"]],
                                               f"union_list_{i}")))
        unions.append(union)
    expression = BNode("conjunction_of_unions")
    graph.add((expression, OWL.intersectionOf, _rdf_list(graph, unions, "intersection")))
    graph.add((expression, RDFS.subClassOf, EX.Selected))
    for j in range(individuals):
        individual = EX[f"union_subject_{j}"]
        graph.add((individual, RDF.type, OWL.NamedIndividual))
        for i in range(pairs):
            if j % 4 == 0 and i == pairs - 1:
                continue
            graph.add((individual, RDF.type, EX[f"{'A' if (i + j) % 2 else 'B'}{i}"]))
    return graph, {
        "pairs": pairs, "individuals": individuals,
        "expected_answers": sum(j % 4 != 0 for j in range(individuals)),
        "unfactored_dnf_branches": 2**pairs,
        "expression_nodes": 4 * pairs - 1,
    }


def factored_enumerations(pairs=16, individuals=128):
    """Conjunction of oneOf pairs, the compiler's former exponential case.

    Every Ai denotes the common individual. Half the query aliases denote that
    individual; the others denote B0, which need not belong to the other pairs.
    """
    if pairs < 2 or individuals < 1:
        raise ValueError("Use at least two pairs and one query alias")
    graph = Graph()
    enumerations = []
    for i in range(pairs):
        enumeration = BNode(f"enumeration_{i}")
        graph.add((enumeration, OWL.oneOf, _rdf_list(
            graph, [EX[f"nominal_A{i}"], EX[f"nominal_B{i}"]], f"enumeration_list_{i}")))
        graph.add((EX[f"nominal_A{i}"], OWL.sameAs, EX.nominal_common))
        enumerations.append(enumeration)
    expression = BNode("conjunction_of_enumerations")
    graph.add((expression, OWL.intersectionOf, _rdf_list(graph, enumerations, "nominal_intersection")))
    graph.add((expression, RDFS.subClassOf, EX.SelectedNominal))
    for j in range(individuals):
        target = EX[f"nominal_A{j % pairs}"] if j % 2 == 0 else EX.nominal_B0
        graph.add((EX[f"nominal_alias_{j}"], OWL.sameAs, target))
    return graph, {
        "pairs": pairs, "individuals": individuals,
        "expected_answers": 1 + pairs + (individuals + 1) // 2,
        "expected_equality_merges": pairs + individuals,
        "unfactored_dnf_branches": 2**pairs, "expression_nodes": 4 * pairs - 1,
        "nominal_constants": 2 * pairs,
    }


def maintenance(depth=4, change_percent=10, seed=2004):
    """Five-way taxonomy, five individuals in every class, plus support cycles."""
    if change_percent not in {10, 15}:
        raise ValueError("The maintenance matrix uses 10% and 15% changes")
    graph, meta = taxonomy(depth, 5, branching=5, seed=seed, include_root=True)
    for source, target in [(EX.C1, EX.MaintShared), (EX.C2, EX.MaintShared),
                           (EX.MaintEmpty, EX.MaintShared),
                           (EX.MaintShared, EX.MaintCycle), (EX.MaintCycle, EX.MaintShared)]:
        graph.add((source, RDFS.subClassOf, target))
    meta.update(change_percent=change_percent,
                changed_assertions=meta["individuals"] * change_percent // 100,
                support_cycle=True, alternate_supports=True,
                operation_protocol="facts-delete-insert_rules-insert-delete-replace_atomic-mixed-v2")
    return graph, meta


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
