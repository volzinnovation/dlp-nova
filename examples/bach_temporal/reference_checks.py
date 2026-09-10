#!/usr/bin/env python3
"""Current DLP closure checks plus a SEPARATE finite temporal reference oracle.

No proposed query is parsed/executed here. No temporal library is installed.
Synthetic tests below describe the future contract, not production support.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rdflib import Literal, Namespace  # noqa: E402
from rdflib.namespace import RDF, XSD  # noqa: E402

from dlp_reasoner import Reasoner, parse_dlp  # noqa: E402

BACH = Namespace("http://www.jsbach.org/bach#")
BT = Namespace("https://example.org/bach-temporal#")
SYN = Namespace("urn:example:bach-temporal:synthetic:")
HERE = Path(__file__).resolve().parent
PARENTS = tuple(BACH[name] for name in (
    "johann-sebastian", "maria-barbara", "anna-magdalena"))


def local(term):
    return str(term).rsplit("#", 1)[-1].rsplit(":", 1)[-1]


def exact_date(value):
    """Fixture profile: exact timezone-free Gregorian xsd:date, years 0001–9999."""
    if (not isinstance(value, Literal) or value.datatype != XSD.date
            or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", str(value))):
        raise ValueError("Expected normalized exact Gregorian xsd:date")
    return date.fromisoformat(str(value))


def accepted_birth(values):
    if not values:
        return None, "missing_date"
    try:
        decoded = {exact_date(value) for value in values}
    except ValueError:
        return None, "invalid_date"
    if len(decoded) != 1:
        return None, "conflicting_dates"
    return next(iter(decoded)), None


def completed_years(birth, event, leap_policy="march1"):
    """Completed Gregorian years; March 1 is the chosen Feb-29 anniversary."""
    if leap_policy != "march1":
        raise ValueError("Unsupported leap-day policy")
    if event < birth:
        raise ValueError("Child birth precedes parent birth")
    return event.year - birth.year - ((event.month, event.day) < (birth.month, birth.day))


def normalize_fixture_date(lexical, calendar):
    """Narrow checked fixture conversion; NOT a general calendar library.

    The Julian/Gregorian difference is exactly 10 days throughout 1600–1699.
    Restricting this helper prevents accidentally applying that offset in 1700+.
    """
    parsed = date.fromisoformat(lexical)
    if calendar == "Gregorian":
        return parsed
    if calendar == "Julian" and 1600 <= parsed.year <= 1699:
        return parsed + timedelta(days=10)
    raise ValueError("Unsupported or unknown fixture calendar/range")


def evidence_key(reasoner, parent):
    """Bind the EXPLICIT synthetic certificate to this exact parent evidence."""
    children = reasoner.property_values(parent, BACH.hasChild)
    rows = [(str(parent), "role", name) for name in ("Father", "Mother")
            if parent in reasoner.instances(BACH[name])]
    for person in {parent, *children}:
        rows.append((str(person), "member", "parent" if person == parent else "child"))
        rows.extend((str(person), "birthDate", value.n3())
                    for value in reasoner.property_values(person, BT.birthDate))
    return hashlib.sha256(json.dumps(sorted(rows)).encode()).hexdigest()


def answer(reasoner, parent, certificates=None):
    """Finite reference computation over current materialized DLP input relations.

    A certificate is an external assertion of complete family/date coverage,
    bound to exact evidence. No certificate is inferred from absence of records.
    """
    if not reasoner.complete or reasoner.consistency != "consistent":
        raise ValueError("Reasoning must be complete and consistent")
    role = "father" if parent in reasoner.instances(BACH.Father) else "mother"
    if role == "mother" and parent not in reasoner.instances(BACH.Mother):
        raise ValueError("Parent has no Father/Mother role in this fixture")
    issues = []
    candidates = []
    children = reasoner.property_values(parent, BACH.hasChild)
    for child in children:
        child_date, issue = accepted_birth(reasoner.property_values(child, BT.birthDate))
        if issue:
            issues.append(f"child:{local(child)}:{issue}")
        else:
            candidates.append((child_date, child))
    parent_date, issue = accepted_birth(reasoner.property_values(parent, BT.birthDate))
    if issue:
        issues.append(f"parent:{issue}")
    first_date = min((value for value, _ in candidates), default=None)
    first_children = sorted(local(child) for value, child in candidates if value == first_date)
    age = None
    if first_date is not None and parent_date is not None:
        try:
            age = completed_years(parent_date, first_date)
        except ValueError:
            issues.append("parent:birth_after_child")
    certified = bool(certificates and certificates.get(parent) == evidence_key(reasoner, parent))
    if not certified:
        issues.append("scope:not_certified_complete")
    elif issues:
        issues.append("scope:certificate_rejected_for_date_errors")
    return {
        "firstKnownChild": first_children,
        "earliestKnownBirth": first_date.isoformat() if first_date else None,
        f"{role}AtAgeKnown": age,
        f"{role}AtAge": age if certified and not issues else None,
        "diagnostics": sorted(issues),
    }


def age_projection(reasoner):
    return {local(parent): answer(reasoner, parent)[
        "fatherAtAgeKnown" if parent == PARENTS[0] else "motherAtAgeKnown"]
        for parent in PARENTS[:2]}


def check_historical(graph, backend, expected):
    reasoner = Reasoner(graph, profile="L0", backend=backend)
    assert reasoner.instances(BACH.Father) == {PARENTS[0]}
    assert reasoner.instances(BACH.Mother) == set(PARENTS[1:])
    assert reasoner.property_pairs(BT.fatherAtAge) == set()
    assert reasoner.property_pairs(BT.motherAtAge) == set()
    observed = {local(parent): answer(reasoner, parent) for parent in PARENTS}
    assert observed == expected["extended"], (backend, observed)
    full_closure = set(reasoner.engine.facts)

    # Actual current-engine fact insert/retract. Temporal outputs are recomputed
    # independently, not maintained by the current DRed implementation.
    edges = [(parent, BACH.hasChild, BACH["catharina-dorothea"]) for parent in PARENTS[:2]]
    reasoner.update(remove=edges)
    assert age_projection(reasoner) == expected["before_earlier_child"]
    reasoner.update(add=edges)
    assert age_projection(reasoner) == expected["after_earlier_child"]
    assert reasoner.engine.facts == full_closure
    reasoner.update(remove=edges)
    assert age_projection(reasoner) == expected["after_earlier_child_deleted"]
    reasoner.update(add=edges)

    # The independent extension also composes with the unmodified thesis L3 data.
    merged = parse_dlp((ROOT / "examples" / "bach.dlp").read_text()) + graph
    combined = Reasoner(merged, profile="L3", backend=backend)
    assert combined.complete and combined.consistency == "consistent"
    assert {local(parent): answer(combined, parent) for parent in PARENTS} == observed
    return full_closure, observed


def check_synthetic(backend):
    """Explicitly invented complete family, twins, partial/conflicting dates."""
    graph = parse_dlp((HERE / "bach-temporal.dlp").read_text())
    father, mother, twin_a, twin_b, later = (SYN[name] for name in
                                           ("father", "mother", "twin_a", "twin_b", "later"))
    for parent, sex, birth in ((father, BACH.Man, "1980-02-29"),
                               (mother, BACH.Woman, "1982-06-01")):
        graph.add((parent, RDF.type, sex))
        graph.add((parent, BT.birthDate, Literal(birth, datatype=XSD.date)))
        for child in (twin_a, twin_b, later):
            graph.add((parent, BACH.hasChild, child))
    for child, birth in ((twin_a, "2000-06-01"), (twin_b, "2000-06-01"),
                          (later, "2003-01-01")):
        graph.add((child, BT.birthDate, Literal(birth, datatype=XSD.date)))
    reasoner = Reasoner(graph, profile="L0", backend=backend)
    # Only this invented family has an explicit complete-child/date assertion.
    certificates = {parent: evidence_key(reasoner, parent) for parent in (father, mother)}
    assert answer(reasoner, father, certificates)["fatherAtAge"] == 20
    assert answer(reasoner, mother, certificates)["motherAtAge"] == 18
    assert answer(reasoner, father)["fatherAtAge"] is None
    assert answer(reasoner, father, certificates)["firstKnownChild"] == ["twin_a", "twin_b"]

    reasoner.update(remove=[(father, BACH.hasChild, twin_a)])
    assert answer(reasoner, father)["firstKnownChild"] == ["twin_b"]
    assert answer(reasoner, father)["fatherAtAgeKnown"] == 20
    assert answer(reasoner, father, certificates)["fatherAtAge"] is None  # stale certificate
    reasoner.update(remove=[(father, BACH.hasChild, twin_b)])
    assert answer(reasoner, father)["firstKnownChild"] == ["later"]
    assert answer(reasoner, father)["fatherAtAgeKnown"] == 22
    # Preserve an explicit role to query the genuinely empty aggregate group.
    reasoner.update(add=[(father, RDF.type, BACH.Father)],
                    remove=[(father, BACH.hasChild, later)])
    assert reasoner.property_values(father, BACH.hasChild) == set()
    empty = answer(reasoner, father)
    assert empty["firstKnownChild"] == []
    assert empty["earliestKnownBirth"] is None and empty["fatherAtAgeKnown"] is None

    unknown = SYN.unknown
    reasoner.update(add=[(mother, BACH.hasChild, unknown)])
    refreshed = {mother: evidence_key(reasoner, mother)}
    result = answer(reasoner, mother, refreshed)
    assert result["motherAtAge"] is None
    assert "child:unknown:missing_date" in result["diagnostics"]
    conflicting = Literal("1999-01-01", datatype=XSD.date)
    reasoner.update(add=[(twin_a, BT.birthDate, conflicting)])
    result = answer(reasoner, mother)
    assert result["firstKnownChild"] == ["twin_b"]
    assert "child:twin_a:conflicting_dates" in result["diagnostics"]
    reasoner.update(remove=[(twin_a, BT.birthDate, conflicting)])
    assert answer(reasoner, mother)["firstKnownChild"] == ["twin_a", "twin_b"]


def check_scalar_edges():
    assert completed_years(date(2000, 2, 29), date(2021, 2, 28)) == 20
    assert completed_years(date(2000, 2, 29), date(2021, 3, 1)) == 21
    assert completed_years(date(2000, 2, 29), date(2024, 2, 29)) == 24
    assert completed_years(date(1982, 6, 1), date(2000, 6, 1)) == 18
    assert completed_years(date(1982, 6, 1), date(2000, 5, 31)) == 17
    for birth, event, policy in ((date(2000, 1, 2), date(2000, 1, 1), "march1"),
                                  (date(2000, 1, 1), date(2020, 1, 1), "unknown")):
        try:
            completed_years(birth, event, policy)
        except ValueError:
            pass
        else:
            raise AssertionError("Expected date/policy error")
    assert accepted_birth({Literal("1708-12-27", datatype=XSD.date)})[1] is None
    assert accepted_birth({Literal("1708-12-27")})[1] == "invalid_date"
    assert accepted_birth({Literal("spring 1723")})[1] == "invalid_date"
    assert normalize_fixture_date("1685-03-21", "Julian") == date(1685, 3, 31)
    assert normalize_fixture_date("1684-10-20", "Julian") == date(1684, 10, 30)
    for lexical, calendar in (("1700-03-01", "Julian"), ("1685-03-21", "unknown"),
                              ("2023-02-29", "Gregorian")):
        try:
            normalize_fixture_date(lexical, calendar)
        except ValueError:
            pass
        else:
            raise AssertionError("Expected normalization error")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("python", "native", "both"), default="both")
    args = parser.parse_args()
    expected = json.loads((HERE / "expected.json").read_text())
    graph = parse_dlp((HERE / "bach-temporal.dlp").read_text())
    backends = ("python", "native") if args.backend == "both" else (args.backend,)
    closures = []
    for backend in backends:
        closure, observed = check_historical(graph, backend, expected)
        closures.append(closure)
        check_synthetic(backend)
        print(f"{backend}: real DLP closure and updates passed; separate temporal oracle passed")
    assert all(closure == closures[0] for closure in closures)
    check_scalar_edges()
    print(json.dumps({"reference_temporal_results": observed,
                      "production_temporal_operators_executed": False}, indent=2))


if __name__ == "__main__":
    main()
