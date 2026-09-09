#!/usr/bin/env python3
"""Reproduce selected thesis errata using only Python's standard library.

Run with: python3 scripts/check_thesis_logic.py

The checks interpret finite sets, relations, and truth values directly. They do
not import the DLP reasoner or use it as an oracle. A concrete countermodel can
refute a universal claim; agreement over these small domains cannot prove a
general theorem. The size checks illustrate finite members of expression
families whose general growth arguments are explained in docs/THESIS_ERRATA.md.

References use printed thesis pages; add 16 for one-based PDF page numbers.
"""

from __future__ import annotations

from itertools import product
from typing import TypeAlias

Relation: TypeAlias = set[tuple[int, int]]
Expression: TypeAlias = str | tuple["Expression", "Expression"]


def require(condition: bool, message: str) -> None:
    """Keep checks active even if Python is invoked with -O."""
    if not condition:
        raise AssertionError(message)


def subsets(domain: range) -> list[set[int]]:
    return [
        {element for element, present in zip(domain, mask) if present}
        for mask in product((False, True), repeat=len(domain))
    ]


def check_equivalence_probe() -> None:
    """Section 5.4.4.2, p. 136: joint probes can contaminate each other."""
    for size in (1, 2, 3):
        domain = range(size)
        extensions = subsets(domain)
        base_models = non_equivalent_models = joint_models = 0
        c_probe_countermodels = d_probe_countermodels = 0
        for c, d, o in product(extensions, extensions, domain):
            # TBox: C is a subset of {o}; D is a subset of {o}.
            if not (c <= {o} and d <= {o}):
                continue
            base_models += 1
            non_equivalent_models += c != d
            # All assignments of fresh names are allowed, including a = b = o.
            # Fresh syntax does not introduce a unique-name assumption.
            for a, b in product(domain, repeat=2):
                if a in c and b in d:
                    joint_models += 1
                    require(a == b == o, "Joint probe must identify its names")
                    require(a in d and b in c, "Both queried conclusions must hold")
                if a in c and a not in d:
                    c_probe_countermodels += 1
                if b in d and b not in c:
                    d_probe_countermodels += 1
        require(base_models == 4 * size, "Unexpected base-model enumeration")
        require(non_equivalent_models > 0, "Original TBox must not entail C = D")
        require(joint_models > 0, "Joint probe must remain consistent")
        require(c_probe_countermodels > 0, "Separate C probe must refute C <= D")
        require(d_probe_countermodels > 0, "Separate D probe must refute D <= C")
        print(
            f"PASS p136, domain {size}: {base_models} TBox models, "
            f"{non_equivalent_models} with C != D; all {joint_models} joint-probe "
            "models satisfy both queried conclusions; separate probes have countermodels"
        )


def inverse(relation: Relation) -> Relation:
    return {(right, left) for left, right in relation}


def composition(left: Relation, right: Relation) -> Relation:
    return {(x, z) for x, y in left for y2, z in right if y == y2}


def check_inverse_and_transitivity() -> None:
    """Equations (5.13)-(5.14), p. 140: inclusion is not inverse equality."""
    domain = range(3)
    p: Relation = {(0, 1), (1, 2)}
    q: Relation = set(product(domain, repeat=2))
    require(p < q, "P must be a strict subproperty of Q")
    require(q == inverse(q), "Q must be its own inverse")
    require(composition(q, q) <= q, "Q must be transitive")
    require(p != inverse(q), "Q's inverse must not equal P")
    require(composition(p, p) - p == {(0, 2)}, "P must fail transitivity")

    # Execute only the displayed meta-rules on their asserted metadata. Actual
    # relational semantics above remains the independent correctness criterion.
    subproperty = {("P", "Q")}
    inverse_metadata = {("Q", "Q")}
    transitive_metadata = {"Q"}
    while True:
        next_inverses = inverse_metadata | {(y, x) for x, y in inverse_metadata}
        next_inverses |= {(x, z) for x, y in subproperty for y2, z in inverse_metadata if y == y2}
        next_transitive = transitive_metadata | {
            x for x, y in next_inverses if y in transitive_metadata
        }
        if next_inverses == inverse_metadata and next_transitive == transitive_metadata:
            break
        inverse_metadata, transitive_metadata = next_inverses, next_transitive
    require(("P", "Q") in inverse_metadata, "Equation (5.13) must infer inverse(P,Q)")
    require("P" in transitive_metadata, "Equation (5.14) must infer transitive(P)")
    print(
        "PASS p140: displayed meta-rules infer inverse(P,Q) and transitive(P), "
        "but the finite model refutes both; missing transitive edge is (0,2)"
    )


def check_domain_inheritance() -> None:
    """Section 5.4.4.6, p. 139: domains inherit upward to superclasses."""
    student, person, agent = {1}, {0, 1}, {0, 1, 2}
    relation: Relation = {(0, 2)}
    subjects = {subject for subject, _ in relation}
    require(student < person < agent, "Class inclusions must be strict")
    require(subjects <= person, "Person must be a domain of the property")
    require(subjects <= agent, "Superclass Agent must also be a domain")
    require(not subjects <= student, "Subclass Student must not be a domain")
    print("PASS p139: Person domain implies Agent domain; Student domain is false")


def check_distributivity() -> None:
    """Section 5.4.2.2, p. 133: check all eight Boolean assignments."""
    counterexamples = []
    for f, g, h in product((False, True), repeat=3):
        printed_left = f or (g and h)
        printed_right = (f and g) or (f and h)
        if printed_left and not printed_right:
            counterexamples.append((f, g, h))
        corrected_left = f and (g or h)
        require(corrected_left == printed_right, "Correct distribution must be equivalent")
    require((False, True, True) in counterexamples, "Expected counterexample must occur")
    print(
        f"PASS p133: printed implication fails on {len(counterexamples)}/8 assignments; "
        "corrected distributivity holds on all 8"
    )


def balanced_conjunction(names: list[str]) -> Expression:
    if len(names) == 1:
        return names[0]
    middle = len(names) // 2
    return balanced_conjunction(names[:middle]), balanced_conjunction(names[middle:])


def expression_size(expression: Expression) -> tuple[int, int]:
    """Return (depth, total syntax nodes), counting an atom as depth zero."""
    if isinstance(expression, str):
        return 0, 1
    left_depth, left_nodes = expression_size(expression[0])
    right_depth, right_nodes = expression_size(expression[1])
    return 1 + max(left_depth, right_depth), 1 + left_nodes + right_nodes


def check_size_claims() -> None:
    """Pages 133/143: count DNF alternatives and balanced-tree syntax nodes."""
    for pairs in range(1, 13):
        # Expand (A1 or B1) and ... and (An or Bn) by Cartesian product.
        alternatives = [(f"A{i}", f"B{i}") for i in range(pairs)]
        terms = {frozenset(choices) for choices in product(*alternatives)}
        require(len(terms) == 2**pairs, "DNF must contain 2**n distinct terms")
        require(all(len(term) == pairs for term in terms), "Each term must select n atoms")
        # Distinct terms have the same size, so none absorbs another by inclusion.
    print("PASS p133: 12 pairs / 11 conjunctions expand into 4096 distinct DNF terms")
    for depth in range(13):
        names = [f"A{i}" for i in range(2**depth)]
        actual_depth, nodes = expression_size(balanced_conjunction(names))
        require(actual_depth == depth, "Balanced expression has unexpected depth")
        require(nodes == 2 ** (depth + 1) - 1, "Balanced expression has unexpected size")
    print("PASS p143: depth 12 conjunction has 4096 distinct atoms and 8191 syntax nodes")


def main() -> None:
    check_equivalence_probe()
    check_inverse_and_transitivity()
    check_domain_inheritance()
    check_distributivity()
    check_size_claims()
    print("All finite counterexample checks passed; this is not a general theorem prover.")


if __name__ == "__main__":
    main()
