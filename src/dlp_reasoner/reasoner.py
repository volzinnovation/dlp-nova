"""RDF-facing reasoning, queries and transactional ontology updates."""
from __future__ import annotations

import hashlib
import itertools
import time
import uuid
from pathlib import Path
from xml.sax import SAXParseException

from rdflib import BNode, Graph, Literal, OWL, RDF, RDFS, URIRef
from rdflib.term import Identifier
from rdflib.exceptions import ParserError

from .compiler import compile_graph
from .engine import Engine
from .model import (
    EQ, NEQ, TOP, Atom, IncompleteReasoningError, InconsistentOntologyError,
    ProfileError, Program, Skolem,
)


def copy_graph(graph: Graph) -> Graph:
    result = Graph()
    for prefix, namespace in graph.namespaces():
        result.bind(prefix, namespace)
    result += graph
    return result


def read_graph(path: str | Path, format: str | None = None) -> Graph:
    """Read a local RDF document. Imports are not implicitly fetched."""
    path = Path(path).expanduser().resolve(strict=True)
    if format is None:
        format = {".ttl": "turtle", ".nt": "nt", ".rdf": "xml", ".owl": "xml",
                  ".xml": "xml", ".n3": "n3"}.get(path.suffix.lower())
    if format not in {"turtle", "ttl", "nt", "xml", "n3"}:
        raise ProfileError("Choose RDF format turtle, nt, xml (RDF/XML), or n3.")
    try:
        return Graph().parse(path, format=format)
    except (SyntaxError, ParserError, SAXParseException) as exc:
        raise ProfileError(f"Invalid {format} document {path.name}: {exc}") from exc


def rdf_term(term):
    if isinstance(term, Skolem):
        return BNode("w" + hashlib.sha256(repr(term).encode()).hexdigest()[:32])
    return term


class Reasoner:
    """Materialize the thesis DLP fragment, with explicit completeness status.

    Negative query answers mean 'not entailed', never closed-world negation.
    Exhaustive queries require a completed, consistent materialization.
    """

    def __init__(self, graph: Graph | None = None, profile: str = "L2", **engine_options):
        self.graph = copy_graph(graph if graph is not None else Graph())
        self.profile = profile.upper()
        self.engine_options = engine_options
        started = time.perf_counter()
        self.program = compile_graph(self.graph, profile=self.profile)
        self.compile_seconds = time.perf_counter() - started
        started = time.perf_counter()
        self.engine = Engine(self.program, **self.engine_options).materialize()
        self.materialize_seconds = time.perf_counter() - started
        self._witness_terms = None
        self._query_terms = set()

    @classmethod
    def from_file(cls, path, *, format=None, profile="L2", **options):
        return cls(read_graph(path, format), profile=profile, **options)

    @property
    def complete(self):
        return self.engine.complete

    @property
    def consistency(self):
        if self.engine.violations:
            return "inconsistent"
        return "consistent" if self.complete else "unknown"

    @property
    def stats(self):
        return {**self.engine.stats, "profile": self.profile,
                "consistency": self.consistency, "complete": self.complete,
                "rdf_triples": len(self.graph), "rules": len(self.program.rules),
                "asserted_facts": len(self.program.facts),
                "materialized_facts": len(self.engine.facts),
                "compile_seconds": self.compile_seconds,
                "materialize_seconds": self.materialize_seconds,
                "warnings": self.program.warnings,
                "violations": [str(v) for v in self.engine.violations]}

    def _guard(self, exhaustive=True):
        if self.engine.violations:
            raise InconsistentOntologyError(
                "The ontology is inconsistent; inspect consistency/stats. "
                "Ordinary query results are not meaningful under classical explosion.")
        if exhaustive and not self.complete:
            raise IncompleteReasoningError(
                "Materialization reached a resource limit; the complete answer is unknown.")

    def _aliases(self, term, include_witnesses=False):
        aliases = self.engine.equivalents(term)
        return {rdf_term(t) for t in aliases
                if isinstance(t, (URIRef, Literal)) or
                (isinstance(t, BNode) and t in self.graph.all_nodes()) or
                (include_witnesses and isinstance(t, (Skolem, BNode)))}

    def _internal_term(self, term):
        """Map an exported witness identifier back to its existential term."""
        if not isinstance(term, BNode) or term in self.engine.terms:
            return term
        if self._witness_terms is None:
            terms = self.engine.terms | {t for f in self.engine.facts for t in f.args}
            self._witness_terms = {rdf_term(t): t for t in terms if isinstance(t, Skolem)}
        return self._witness_terms.get(term, term)

    def _with_query_terms(self, *terms):
        """Interpret fresh query names without changing the live active domain.

        Universal axioms constrain every denotation, including names not present
        in the ontology. A temporary domain extension supplies those denotations.
        """
        missing = {t for t in terms if t not in self._query_terms and t not in self.engine.terms and
                   self.engine.normalize(t) not in self.engine.terms}
        if not missing:
            return self
        query = object.__new__(Reasoner)
        query.graph = copy_graph(self.graph)
        for term in missing:
            if isinstance(term, (URIRef, BNode)):
                query.graph.add((term, RDF.type, OWL.NamedIndividual))
        query.profile, query.engine_options = self.profile, self.engine_options
        query.program = Program(list(self.program.rules),
                                self.program.facts | {Atom(TOP, (t,)) for t in missing},
                                self.profile, list(self.program.warnings))
        query.compile_seconds = 0.0
        started = time.perf_counter()
        query.engine = Engine(query.program, **self.engine_options).materialize()
        query.materialize_seconds = time.perf_counter() - started
        query._witness_terms = None
        query._query_terms = self._query_terms | missing
        return query

    def _predicate(self, concept):
        return TOP if concept == OWL.Thing else concept

    def _expression_query(self, concept):
        # A fresh one-way definition realizes section 5.4's LHS query translation.
        graph = copy_graph(self.graph)
        marker = URIRef("urn:dlp:query:" + uuid.uuid4().hex)
        graph.add((concept, RDFS.subClassOf, marker))
        return Reasoner(graph, profile=self.profile, **self.engine_options), marker

    def instances(self, concept, *, include_witnesses=False):
        self._guard()
        if isinstance(concept, BNode):
            query, marker = self._expression_query(concept)
            return query.instances(marker, include_witnesses=include_witnesses)
        predicate = self._predicate(concept)
        result = set()
        for fact in self.engine.facts:
            if fact.predicate == predicate and len(fact.args) == 1:
                result.update(self._aliases(fact.args[0], include_witnesses))
        return {term for term in result if not isinstance(term, Literal)}

    def types(self, individual):
        self._guard()
        individual = self._internal_term(individual)
        query = self._with_query_terms(individual)
        if query is not self:
            return query.types(individual)
        individual = self.engine.normalize(individual)
        return {OWL.Thing if f.predicate == TOP else f.predicate
                for f in self.engine.facts if len(f.args) == 1 and
                f.args[0] == individual and
                (f.predicate == TOP or isinstance(f.predicate, URIRef))}

    def property_values(self, subject, predicate, *, include_witnesses=False):
        self._guard()
        subject = self._internal_term(subject)
        query = self._with_query_terms(subject)
        if query is not self:
            return query.property_values(subject, predicate, include_witnesses=include_witnesses)
        subject = self.engine.normalize(subject)
        result = set()
        for fact in self.engine.facts:
            if fact.predicate == predicate and len(fact.args) == 2 and fact.args[0] == subject:
                result.update(self._aliases(fact.args[1], include_witnesses))
        return result

    def property_pairs(self, predicate, *, include_witnesses=False):
        self._guard()
        result = set()
        for fact in self.engine.facts:
            if fact.predicate == predicate and len(fact.args) == 2:
                result.update(itertools.product(*(self._aliases(t, include_witnesses)
                                                  for t in fact.args)))
        return result

    def entails(self, subject, predicate, obj):
        self._guard(exhaustive=False)
        subject = self._internal_term(subject)
        if predicate != RDF.type:
            obj = self._internal_term(obj)
        query = self._with_query_terms(subject, *(() if predicate == RDF.type else (obj,)))
        if query is not self:
            return query.entails(subject, predicate, obj)
        if predicate == RDF.type and obj == OWL.Thing:
            answer = True
        elif predicate == OWL.sameAs:
            answer = self.engine.normalize(subject) == self.engine.normalize(obj)
        elif predicate == RDF.type and isinstance(obj, BNode):
            query, marker = self._expression_query(obj)
            return query.entails(subject, RDF.type, marker)
        else:
            if predicate == RDF.type:
                atom = Atom(self._predicate(obj), (subject,))
            elif predicate == OWL.differentFrom:
                atom = Atom(NEQ, (subject, obj))
            else:
                atom = Atom(predicate, (subject, obj))
            atom = Atom(atom.predicate, tuple(self.engine.normalize(t) for t in atom.args))
            answer = atom in self.engine.facts
            if predicate == OWL.differentFrom:
                answer = answer or Atom(NEQ, tuple(reversed(atom.args))) in self.engine.facts
        if not answer:
            self._guard()
        return answer

    def subsumes(self, superclass, subclass):
        """Test C ⊑ D by a fresh C instance (not by comparing existing extensions)."""
        self._guard()
        graph = copy_graph(self.graph)
        probe = BNode("probe" + uuid.uuid4().hex)
        graph.add((probe, RDF.type, subclass))
        marker = URIRef("urn:dlp:query:" + uuid.uuid4().hex)
        graph.add((superclass, RDFS.subClassOf, marker))
        query = Reasoner(graph, profile=self.profile, **self.engine_options)
        if query.consistency == "inconsistent":
            return True
        return query.entails(probe, RDF.type, marker)

    def is_satisfiable(self, concept):
        self._guard()
        graph = copy_graph(self.graph)
        graph.add((BNode(), RDF.type, concept))
        query = Reasoner(graph, profile=self.profile, **self.engine_options)
        if query.consistency == "inconsistent":
            return False
        query._guard()
        return True

    def update(self, *, add=(), remove=()):
        """Apply an RDF delta after validating its entire candidate ontology.

        ABox deltas use the engine's incremental maintenance. Schema changes are
        atomically recompiled and rematerialized, including equality splitting.
        """
        candidate = copy_graph(self.graph)
        for triple in remove:
            candidate.remove(triple)
        for triple in add:
            candidate.add(triple)
        started = time.perf_counter()
        program = compile_graph(candidate, profile=self.profile)
        compile_seconds = time.perf_counter() - started
        started = time.perf_counter()
        if set(program.rules) == set(self.program.rules):
            self.engine.update(add=program.facts - self.program.facts,
                               remove=self.program.facts - program.facts)
        else:
            engine = Engine(program, **self.engine_options).materialize()
            engine.stats["update_method"] = "schema-rematerialization"
            self.engine = engine
        self.graph, self.program = candidate, program
        self._witness_terms = None
        self.compile_seconds = compile_seconds
        self.materialize_seconds = time.perf_counter() - started
        return self

    def to_graph(self, *, include_schema=True, expand_equality=True,
                 include_witnesses=False):
        """Export the completed materialization as RDF, optionally expanding aliases."""
        self._guard()
        graph = copy_graph(self.graph) if include_schema else Graph()
        for fact in self.engine.facts:
            if fact.predicate == EQ:
                continue
            if fact.predicate == TOP:
                predicate, is_type = OWL.Thing, True
            elif fact.predicate == NEQ:
                predicate, is_type = OWL.differentFrom, False
            elif isinstance(fact.predicate, URIRef):
                predicate, is_type = fact.predicate, len(fact.args) == 1
            else:
                continue
            alternatives = [self._aliases(t, include_witnesses) if expand_equality else
                            {rdf_term(t)} if self._aliases(t, include_witnesses) else set()
                            for t in fact.args]
            for args in itertools.product(*alternatives):
                if not isinstance(args[0], (URIRef, BNode)):
                    continue
                if is_type:
                    graph.add((args[0], RDF.type, predicate))
                else:
                    graph.add((args[0], predicate, args[1]))
                    if fact.predicate == NEQ and isinstance(args[1], (URIRef, BNode)):
                        graph.add((args[1], predicate, args[0]))
        if expand_equality:
            exported_classes = set()
            for term in self.engine.terms:
                representative = self.engine.normalize(term)
                if representative in exported_classes:
                    continue
                exported_classes.add(representative)
                for a, b in itertools.product(self._aliases(term, include_witnesses), repeat=2):
                    if isinstance(a, (URIRef, BNode)) and isinstance(b, Identifier):
                        graph.add((a, OWL.sameAs, b))
        return graph
