#!/usr/bin/env python3
"""Check selected thesis errata with Python's standard library only.

Run from any directory with Python 3.11 or later. This independently evaluates
the printed maintenance rules in Volltext.pdf; it neither imports this project's
reasoner nor tests the historical KAON implementation. Page numbers below are
printed pages, with the corresponding one-based PDF page in parentheses.
"""

from dataclasses import dataclass
from math import isclose, log


@dataclass(frozen=True)
class GroundRule:
    """A ground implication; negative atoms use stratified negation by failure."""

    head: str
    positive: tuple[str, ...] = ()
    negative: tuple[str, ...] = ()


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def evaluate(rules: tuple[GroundRule, ...], facts: set[str]) -> frozenset[str]:
    """Compute a finite ground program's least model, stratum by stratum.

    Determine strata from dependencies, requiring every negatively referenced
    atom to belong to a strictly lower stratum. Reject negative dependency cycles.
    Within each stratum, repeatedly fire rules until a fixed point is reached.
    """
    atoms = set(facts)
    for rule in rules:
        atoms.update((rule.head, *rule.positive, *rule.negative))
    strata = dict.fromkeys(atoms, 0)
    for _ in range(len(atoms) + 1):
        changed = False
        for rule in rules:
            minimum = max(
                (0, *(strata[a] for a in rule.positive), *(strata[a] + 1 for a in rule.negative))
            )
            if strata[rule.head] < minimum:
                strata[rule.head] = minimum
                changed = True
        if not changed:
            break
    else:
        raise ValueError("The ground program has a negative dependency cycle")

    result = set(facts)
    for level in sorted(set(strata.values())):
        current = [rule for rule in rules if strata[rule.head] == level]
        while True:
            additions = {
                rule.head
                for rule in current
                if all(a in result for a in rule.positive)
                and all(a not in result for a in rule.negative)
            } - result
            if not additions:
                break
            result.update(additions)
    return frozenset(result)


def check_rule_deletion() -> None:
    """Algorithm 6.1, p.163 (179): delete one of two rules defining P."""
    original = (GroundRule("P(a)", ("A(a)",)), GroundRule("P(a)", ("B(a)",)))
    facts = {"A(a)"}  # A and B are extensional predicates; B is empty.
    old = evaluate(original, facts)
    fresh = evaluate(original[1:], facts)  # Delete P(x) :- A(x).
    check("P(a)" in old and "P(a)" not in fresh, "Invalid counterexample setup")

    obsolete = GroundRule("PRed(a)", ("PDel(a)", "ANew(a)"))
    # The old maintenance program includes both rederivation rules. Because
    # P still has its rule over B, the last-rule branch in Algorithm 6.1 does
    # not remove the obsolete rederivation over A. Algorithm 6.2 does not
    # remove it either. Insertion/deletion rewrite replacement is computed
    # from the updated source rules, which now refer only to B.
    printed = (
        GroundRule("ANew(a)", ("A(a)",), ("ADel(a)",)),
        GroundRule("ANew(a)", ("AIns(a)",)),
        GroundRule("BNew(a)", ("B(a)",), ("BDel(a)",)),
        GroundRule("BNew(a)", ("BIns(a)",)),
        # Special replacements for the directly affected predicate P.
        GroundRule("PNew(a)", ("BNew(a)",)),
        GroundRule("PIns(a)", ("PNew(a)",)),
        GroundRule("PDel(a)", ("P(a)",)),
        obsolete,
        GroundRule("PRed(a)", ("PDel(a)", "BNew(a)")),
        # These old insertion/deletion rules also survive if rules(P) is
        # evaluated after updating LP, as the printed algorithm specifies.
        # This rule-only update introduces no AIns or ADel facts.
        GroundRule("PIns(a)", ("AIns(a)",)),
        GroundRule("PDel(a)", ("ADel(a)",)),
        # Grant the differential rules described on p.154 (170), despite
        # their omission from Table 6.2's aggregate generator on p.156 (172).
        # This isolates the separate stale-rederivation defect.
        GroundRule("PPlus(a)", ("PIns(a)",), ("P(a)",)),
        GroundRule("PMinus(a)", ("PDel(a)",), ("PIns(a)", "PRed(a)")),
    )

    def stored_p(result: frozenset[str]) -> set[str]:
        previous = {"a"}
        deletions = {"a"} if "PMinus(a)" in result else set()
        insertions = {"a"} if "PPlus(a)" in result else set()
        return (previous - deletions) | insertions

    actual = evaluate(printed, set(old))
    check("PNew(a)" not in actual, "The new P must be empty")
    check("PRed(a)" in actual, "The obsolete rule must rederive P(a)")
    check("PMinus(a)" not in actual, "Obsolete rederivation must suppress deletion")
    check(stored_p(actual) == {"a"}, "Printed update must incorrectly retain P(a)")

    repaired = tuple(rule for rule in printed if rule != obsolete)
    check(stored_p(evaluate(repaired, set(old))) == set(), "Removing stale support must work")
    supported = set(evaluate(original, {"A(a)", "B(a)"}))
    check(
        stored_p(evaluate(repaired, supported)) == {"a"},
        "A remaining true rule must still preserve P(a)",
    )
    print("PASS Algorithm 6.1: obsolete rederivation retains P(a); fresh closure is empty.")
    print("PASS Controls: remove obsolete rederivation -> deletion; keep B(a) -> retention.")


def check_benchmark_counts() -> None:
    """Check inconsistencies against the stated generators, not historical data."""
    for depth, classes in ((3, 40), (5, 364), (7, 3280)):
        check(sum(3**i for i in range(depth + 1)) == classes, "Wrong taxonomy size")
        parents = (classes - 1) // 3
        # Table 8.9, p.216 (232), exchanges the absolute <=1 and >=0 columns.
        expected_max_one, expected_min_zero = 2 * parents, parents
        check(expected_max_one == 2 * expected_min_zero, "Wrong restriction ratio")
        check(
            round(expected_max_one / classes, 2) in (0.65, 0.66, 0.67),
            "Corrected maximum-one counts must agree with printed relative counts",
        )
        print(
            f"PASS Table 8.9: {classes} classes -> "
            f"max-one {expected_max_one}, min-zero {expected_min_zero}."
        )
        # Table 8.7, p.208 (224): root excluded; fill every third individual.
        expected_fillers = tuple((classes - 1) * n // 3 for n in (3, 9, 15))
        printed_fillers = tuple(classes * n // 3 for n in (3, 9, 15))
        check(
            tuple(p - e for p, e in zip(printed_fillers, expected_fillers)) == (1, 3, 5),
            "The filler-count discrepancy must equal the root's contribution",
        )
        print(f"PASS Table 8.7: expected {expected_fillers}; printed {printed_fillers}.")

    medium_individuals = tuple((364 - 1) * n for n in (3, 9, 15))
    check(medium_individuals == (1089, 3267, 5445), "Wrong medium ABox sizes")
    check(medium_individuals[1:] == (3267, 5445), "Printed counts are shifted one variant")
    print("PASS Table 8.10: TM-IS/TM-IM require 1089/3267, not printed 3267/5445.")


def check_power_law() -> None:
    """Pages 204-205 (220-221): log(c*r**(-a)) = log(c) - a*log(r)."""
    c, exponent = 0.2, 1.7
    for rank in (2, 3, 10):
        value = log(c * rank ** (-exponent))
        check(isclose(value, log(c) - exponent * log(rank)), "Correct transform must agree")
        check(
            not isclose(value, log(c) + exponent * log(rank)),
            "Printed plus sign must disagree for rank greater than one",
        )
    intercept = log(c * 1 ** (-exponent))
    slope = (log(c * 10 ** (-exponent)) - intercept) / log(10)
    check(isclose(intercept, log(c)) and isclose(slope, -exponent), "Wrong coefficients")
    print("PASS Power law: intercept log(c), slope -a; printed coefficient labels are swapped.")


if __name__ == "__main__":
    check_rule_deletion()
    check_benchmark_counts()
    check_power_law()
    print("All checks passed. These checks make no claim about the historical KAON code or data.")
