"""Explicit nonmonotonic input selection and externally certified scopes."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType

from rdflib import Literal, URIRef
from rdflib.namespace import XSD

from .domains import DateValue, DomainError, decode
from .query_runtime import Diagnostic, QueryScope


SELECTION_POLICY = "accepted-exact-records-v1"


def _identity(term):
    return json.dumps([type(term).__name__, term.n3() if hasattr(term, "n3") else repr(term)])


@dataclass(frozen=True)
class CompletenessCertificate:
    """Host-supplied assertion of completeness; never inferred from RDF absence."""
    parent: object
    scope: QueryScope
    evidence_digest: str
    issuer: str
    selection_policy: str = SELECTION_POLICY


@dataclass(frozen=True)
class SelectedView:
    relations: object
    diagnostics: tuple
    metadata: object


class BirthDateView:
    """Select one valid exact birthdate per canonical identity in a scope.

    Reuse the selected records while the ontology revision is unchanged. A new
    revision rebuilds the view, so conflicts, identity merges/splits and corrected
    parent dates retract/restore accepted rows. QueryRuntime maintains result deltas.
    """

    def __init__(self, reasoner, *, child_property, birth_property,
                 accepted_property, certificate_property, trusted_issuers=()):
        self.reasoner = reasoner
        self.child_property, self.birth_property = URIRef(child_property), URIRef(birth_property)
        self.accepted_property = URIRef(accepted_property)
        self.certificate_property = URIRef(certificate_property)
        self.trusted_issuers = frozenset(trusted_issuers)
        self._snapshot_key, self._selected = None, None
        self.stats = {"selection_builds": 0, "selection_cache_hits": 0}

    def _key(self):
        return self.reasoner._query_cache_token(), self.child_property, self.birth_property

    def _snapshot(self):
        self.reasoner._guard(exhaustive=True)
        key = self._key()
        if key == self._snapshot_key:
            self.stats["selection_cache_hits"] += 1
            return self._selected
        normalize = self.reasoner.engine.normalize
        children = {}
        for parent, child in self.reasoner.property_pairs(self.child_property):
            children.setdefault(normalize(parent), set()).add(normalize(child))
        dates = {}
        for person, value in self.reasoner.property_pairs(self.birth_property):
            dates.setdefault(normalize(person), set()).add(value)
        persons = set(dates) | set(children)
        for members in children.values():
            persons.update(members)
        accepted, diagnostics = {}, []
        for person in persons:
            values = dates.get(person, ())
            if not values:
                diagnostics.append(Diagnostic(person, "missing_date"))
                continue
            decoded, invalid = set(), False
            for value in values:
                try:
                    actual = decode(value)
                    if not isinstance(actual, DateValue):
                        raise DomainError("TYPE_ERROR", "birthdate must be an exact Gregorian date")
                    decoded.add(actual)
                except DomainError:
                    invalid = True
            if invalid:
                diagnostics.append(Diagnostic(person, "invalid_date"))
            elif len(decoded) != 1:
                diagnostics.append(Diagnostic(person, "conflicting_dates"))
            else:
                actual = next(iter(decoded))
                accepted[person] = Literal(
                    f"{actual.year:04d}-{actual.month:02d}-{actual.day:02d}",
                    datatype=XSD.date, normalize=False)
        if key != self._key():
            raise DomainError("STALE_SOURCE", "Birthdate source changed during selection")
        self._selected = (MappingProxyType({p: frozenset(v) for p, v in children.items()}),
                          MappingProxyType({p: frozenset(v) for p, v in dates.items()}),
                          MappingProxyType(accepted), tuple(diagnostics))
        self._snapshot_key = key
        self.stats["selection_builds"] += 1
        return self._selected

    def _evidence(self, parent, children, dates):
        engine = self.reasoner.engine
        parent = engine.normalize(parent)
        members = {parent, *children.get(parent, ())}
        rows = [(_identity(parent), "child", _identity(child)) for child in children.get(parent, ())]
        for person in members:
            rows.append((_identity(person), "member", "parent" if person == parent else "child"))
            rows.extend((_identity(person), "identity", _identity(alias)) for alias in engine.equivalents(person))
            rows.extend((_identity(person), "date", value.n3()) for value in dates.get(person, ()))
        return hashlib.sha256(json.dumps(sorted(rows), ensure_ascii=False).encode()).hexdigest()

    def evidence_digest(self, parent):
        """Return the local evidence fingerprint for an external certifier."""
        children, dates, _, _ = self._snapshot()
        key = self._snapshot_key
        result = self._evidence(parent, children, dates)
        if key != self._key():
            raise DomainError("STALE_SOURCE", "Birthdate source changed during certification")
        return result

    def prepare(self, scope, *, certificates=()):
        if not isinstance(scope, QueryScope):
            raise TypeError("scope must be QueryScope")
        certificates = tuple(certificates)
        children, dates, accepted, diagnostics = self._snapshot()
        key = self._snapshot_key
        diagnostics = list(diagnostics)
        certified, certificates_by_parent = set(), {}
        normalize = self.reasoner.engine.normalize
        for certificate in certificates:
            if not isinstance(certificate, CompletenessCertificate):
                raise TypeError("certificates must be CompletenessCertificate values")
            parent = normalize(certificate.parent)
            certificates_by_parent.setdefault(parent, []).append(certificate)
        for parent in children:
            valid = False
            candidates = certificates_by_parent.get(parent, ())
            for certificate in candidates:
                if certificate.issuer not in self.trusted_issuers:
                    diagnostics.append(Diagnostic(parent, "untrusted_certificate"))
                elif (certificate.scope != scope or certificate.selection_policy != SELECTION_POLICY
                      or certificate.evidence_digest != self._evidence(parent, children, dates)):
                    diagnostics.append(Diagnostic(parent, "stale_certificate"))
                elif not {parent, *children[parent]} <= accepted.keys():
                    diagnostics.append(Diagnostic(parent, "invalid_complete_scope"))
                else:
                    valid = True
            if valid:
                certified.add(parent)
            else:
                diagnostics.append(Diagnostic(parent, "scope_not_certified_complete"))
        relations = {
            self.accepted_property: frozenset(accepted.items()),
            self.certificate_property: frozenset(
                (parent, URIRef(scope.name), Literal(scope.revision)) for parent in certified),
        }
        if key != self._key():
            raise DomainError("STALE_SOURCE", "Birthdate source changed during certification")
        return SelectedView(MappingProxyType(relations),
                            tuple(sorted(set(diagnostics), key=lambda d: (str(d.subject), d.code))),
                            MappingProxyType({"selection_policy": SELECTION_POLICY,
                                              "selected_view_complete": True,
                                              "certified_parents": frozenset(certified),
                                              "family_history_complete": set(children) <= certified}))


class LocationView:
    """Require one node and one valid coordinate pair per sign before joins."""

    def __init__(self, reasoner, *, sign_class, location_property, latitude_property,
                 longitude_property, validated_property):
        self.reasoner = reasoner
        self.sign_class, self.location_property = URIRef(sign_class), URIRef(location_property)
        self.latitude_property, self.longitude_property = URIRef(latitude_property), URIRef(longitude_property)
        self.validated_property = URIRef(validated_property)

    def prepare(self, registry):
        from .domains import value_key
        self.reasoner._guard(exhaustive=True)
        key = self.reasoner._query_cache_token()
        accepted, diagnostics = set(), []
        normalize = self.reasoner.engine.normalize
        for sign in {normalize(sign) for sign in self.reasoner.instances(self.sign_class)}:
            nodes = {normalize(node) for node in self.reasoner.property_values(sign, self.location_property)}
            if len(nodes) != 1:
                diagnostics.append(Diagnostic(sign, "missing_location" if not nodes else "conflicting_locations"))
                continue
            node = next(iter(nodes))
            latitudes = self.reasoner.property_values(node, self.latitude_property)
            longitudes = self.reasoner.property_values(node, self.longitude_property)
            try:
                if not latitudes or not longitudes:
                    raise DomainError("DOMAIN_ERROR", "missing coordinates")
                if len({value_key(v) for v in latitudes}) != 1 or len({value_key(v) for v in longitudes}) != 1:
                    raise DomainError("DOMAIN_ERROR", "conflicting coordinates")
                registry.evaluate("urn:dlp:spatial:wgs84Point",
                                  (next(iter(longitudes)), next(iter(latitudes))))
                accepted.add((sign, node))
            except DomainError as exc:
                if exc.code not in {"TYPE_ERROR", "DOMAIN_ERROR", "OVERFLOW", "INEXACT"}:
                    raise
                diagnostics.append(Diagnostic(sign, "invalid_location", str(exc)))
        if key != self.reasoner._query_cache_token():
            raise DomainError("STALE_SOURCE", "Location source changed during selection")
        return SelectedView(MappingProxyType({self.validated_property: frozenset(accepted)}),
                            tuple(diagnostics), MappingProxyType({"selection_policy": "accepted-location-v1"}))
