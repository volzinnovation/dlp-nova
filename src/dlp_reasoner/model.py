"""Small, immutable Horn-rule intermediate representation."""
from dataclasses import dataclass, field
from typing import Hashable

EQ = "urn:dlp:internal:eq"
NEQ = "urn:dlp:internal:neq"
TOP = "urn:dlp:internal:top"


@dataclass(frozen=True)
class Var:
    name: str


@dataclass(frozen=True)
class Skolem:
    symbol: str
    args: tuple


@dataclass(frozen=True)
class Atom:
    predicate: Hashable
    args: tuple


@dataclass(frozen=True)
class Rule:
    head: Atom | None
    body: tuple[Atom, ...] = ()
    label: str = ""


@dataclass
class Program:
    rules: list[Rule] = field(default_factory=list)
    facts: set[Atom] = field(default_factory=set)
    profile: str = "L2"
    warnings: list[str] = field(default_factory=list)


class ProfileError(ValueError):
    """The ontology is malformed or outside the selected supported fragment."""


class IncompleteReasoningError(RuntimeError):
    """A resource bound prevented a complete answer."""


class InconsistentOntologyError(RuntimeError):
    """Querying a contradictory ontology requires explicit classical semantics."""
