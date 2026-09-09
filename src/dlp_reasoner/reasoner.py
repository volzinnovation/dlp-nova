"""RDF-facing reasoning, queries and transactional ontology updates."""
from __future__ import annotations

import hashlib
import itertools
import time
import uuid
from collections import defaultdict
from functools import wraps
from pathlib import Path
from xml.sax import SAXParseException

from rdflib import BNode, Graph, Literal, OWL, RDF, RDFS, URIRef
from rdflib.term import Identifier
from rdflib.exceptions import ParserError

from .compiler import compile_graph
from .engine import Engine, _MISSING
from .model import (
    EQ, NEQ, TOP, Atom, IncompleteReasoningError, InconsistentOntologyError,
    ProfileError, Program, Skolem,
)
from .parser import parse_dlp
from .query_cache import AnswerCache, CACHE_MISS, RevisionMemory
from .schema import SchemaIndex


def copy_graph(graph: Graph) -> Graph:
    result = Graph(store=RevisionMemory())
    for prefix, namespace in graph.namespaces():
        result.bind(prefix, namespace)
    result += graph
    return result


def read_graph(path: str | Path, format: str | None = None) -> Graph:
    """Read a local RDF or thesis DLP document without fetching imports."""
    path = Path(path).expanduser().resolve(strict=True)
    if format is None:
        format = {".ttl": "turtle", ".nt": "nt", ".rdf": "xml", ".owl": "xml",
                  ".xml": "xml", ".n3": "n3", ".dlp": "dlp"}.get(path.suffix.lower())
    if format == "dlp":
        try:
            return parse_dlp(path.read_text(encoding="utf-8"), source=str(path))
        except UnicodeError as exc:
            raise ProfileError(f"Invalid UTF-8 DLP document {path.name}: {exc}") from exc
    if format not in {"turtle", "ttl", "nt", "xml", "n3"}:
        raise ProfileError("Choose format dlp, turtle, nt, xml (RDF/XML), or n3.")
    try:
        return Graph().parse(path, format=format)
    except (SyntaxError, ParserError, SAXParseException) as exc:
        raise ProfileError(f"Invalid {format} document {path.name}: {exc}") from exc


def rdf_term(term):
    if isinstance(term, Skolem):
        return BNode("w" + hashlib.sha256(repr(term).encode()).hexdigest()[:32])
    return term


def _cached_query(method):
    """Memoize completed scalar/set answers without retaining trial reasoners."""
    @wraps(method)
    def query(self, *args, **kwargs):
        self._guard(exhaustive=method.__name__ != "entails")
        self._sync_query_cache()
        if not self._query_cache_size:
            return method(self, *args, **kwargs)
        key = (method.__name__, args, tuple(sorted(kwargs.items())))
        try:
            hash(key)
        except TypeError:
            # Preserve the query's existing argument validation/error behavior.
            return method(self, *args, **kwargs)
        answer = self._answer_cache.get(key)
        if answer is not CACHE_MISS:
            return answer
        epoch = self._query_cache_epoch
        answer = method(self, *args, **kwargs)
        if (self.complete and not self.engine.violations
                and epoch == self._query_cache_token()):
            self._answer_cache.put(key, answer)
        return answer
    return query


class Reasoner:
    """Materialize the thesis DLP fragment, with explicit completeness status.

    Negative query answers mean 'not entailed', never closed-world negation.
    Exhaustive queries require a completed, consistent materialization.
    """

    def __init__(self, graph: Graph | None = None, profile: str = "L2", *,
                 query_cache_size: int = 256, **engine_options):
        if isinstance(query_cache_size, bool) or not isinstance(query_cache_size, int):
            raise ValueError("query_cache_size must be a nonnegative integer")
        if query_cache_size < 0:
            raise ValueError("query_cache_size must be a nonnegative integer")
        self._query_cache_size = query_cache_size
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
        self._schema_cache = None
        self._init_query_cache()

    def _init_query_cache(self):
        self._answer_cache = AnswerCache(max_entries=self._query_cache_size)
        self._types_index = None
        self._graph_nodes = None
        self._query_cache_epoch = self._query_cache_token()

    def _query_cache_token(self):
        graph = self.graph
        # Owned graph copies track store mutations in O(1), including parse,
        # set, addN and edits through graph.store. Replacing graph with an
        # arbitrary external store retains correctness using an exact snapshot.
        revision = (graph.store.revision if isinstance(graph.store, RevisionMemory)
                    else frozenset(graph))
        return (id(graph), graph, revision, id(self.engine), self.engine,
                self.engine._revision, self.engine.complete, self.profile,
                tuple(sorted(self.engine_options.items())))

    def _sync_query_cache(self):
        epoch = self._query_cache_token()
        if epoch != self._query_cache_epoch:
            self._answer_cache.clear()
            self._types_index = self._graph_nodes = self._witness_terms = None
            self._schema_cache = None
            self._query_cache_epoch = epoch

    def clear_query_cache(self):
        """Release cached answers and query views; preserve reasoning/proofs."""
        self._sync_query_cache()
        self._answer_cache.clear()
        self._types_index = self._graph_nodes = self._witness_terms = None
        self._query_cache_epoch = self._query_cache_token()

    @property
    def query_cache_info(self):
        """Query-cache counters and capacity, separate from reasoning timings."""
        self._sync_query_cache()
        return self._answer_cache.info()

    def _new_query_reasoner(self, graph):
        return Reasoner(graph, profile=self.profile, query_cache_size=self._query_cache_size,
                        **self.engine_options)

    def _query_rows(self, predicate, values):
        index = self.engine._index
        if index.arity(predicate) != len(values):
            return ()
        return index.lookup(predicate, values)

    @classmethod
    def from_file(cls, path, *, format=None, profile="L2", **options):
        return cls(read_graph(path, format), profile=profile, **options)

    @classmethod
    def from_dlp(cls, text: str, *, profile="L2", **options):
        """Parse thesis concrete syntax and materialize it under the selected profile."""
        return cls(parse_dlp(text), profile=profile, **options)

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
                (isinstance(t, BNode) and self._is_graph_node(t)) or
                (include_witnesses and isinstance(t, (Skolem, BNode)))}

    def _is_graph_node(self, term):
        if self._graph_nodes is None:
            self._graph_nodes = self.graph.all_nodes()
        return term in self._graph_nodes

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
        query._schema_cache = None
        query._query_cache_size = self._query_cache_size
        query._init_query_cache()
        return query

    def _predicate(self, concept):
        return TOP if concept == OWL.Thing else concept

    def _expression_query(self, concept):
        # A fresh one-way definition realizes section 5.4's LHS query translation.
        graph = copy_graph(self.graph)
        marker = URIRef("urn:dlp:query:" + uuid.uuid4().hex)
        graph.add((concept, RDFS.subClassOf, marker))
        return self._new_query_reasoner(graph), marker

    @_cached_query
    def instances(self, concept, *, include_witnesses=False):
        self._guard()
        if isinstance(concept, BNode):
            query, marker = self._expression_query(concept)
            return query.instances(marker, include_witnesses=include_witnesses)
        predicate = self._predicate(concept)
        result = set()
        for (term,) in self._query_rows(predicate, (_MISSING,)):
            result.update(self._aliases(term, include_witnesses))
        return {term for term in result if not isinstance(term, Literal)}

    @_cached_query
    def types(self, individual):
        self._guard()
        individual = self._internal_term(individual)
        query = self._with_query_terms(individual)
        if query is not self:
            return query.types(individual)
        individual = self.engine.normalize(individual)
        if self._types_index is None:
            self._types_index = defaultdict(set)
            for fact in self.engine.facts:
                if (len(fact.args) == 1
                        and (fact.predicate == TOP or isinstance(fact.predicate, URIRef))):
                    self._types_index[fact.args[0]].add(
                        OWL.Thing if fact.predicate == TOP else fact.predicate)
        return set(self._types_index.get(individual, ()))

    @_cached_query
    def property_values(self, subject, predicate, *, include_witnesses=False):
        self._guard()
        subject = self._internal_term(subject)
        query = self._with_query_terms(subject)
        if query is not self:
            return query.property_values(subject, predicate, include_witnesses=include_witnesses)
        subject = self.engine.normalize(subject)
        result = set()
        for _, target in self._query_rows(predicate, (subject, _MISSING)):
            result.update(self._aliases(target, include_witnesses))
        return result

    @_cached_query
    def property_pairs(self, predicate, *, include_witnesses=False):
        self._guard()
        result = set()
        for row in self._query_rows(predicate, (_MISSING, _MISSING)):
            result.update(itertools.product(*(self._aliases(t, include_witnesses) for t in row)))
        return result

    @_cached_query
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

    def _schema(self):
        if self._schema_cache is None:
            self._schema_cache = SchemaIndex(self.program.rules)
        return self._schema_cache

    @_cached_query
    def subsumes(self, superclass, subclass):
        """Prove a schema consequence or use an isolated fresh-instance probe.

        The index supplies only positive proofs over a supported rule subset.
        A missing proof never stands in for a negative semantic answer.
        """
        self._guard()
        if (isinstance(superclass, URIRef) and isinstance(subclass, URIRef)
                and self._schema().proves_subsumption(superclass, subclass)):
            return True
        return self._subsumption_probe(superclass, subclass)

    def _subsumption_probe(self, superclass, subclass):
        """General semantic fallback, independent of the schema index."""
        self._guard()
        graph = copy_graph(self.graph)
        probe = BNode("probe" + uuid.uuid4().hex)
        graph.add((probe, RDF.type, subclass))
        marker = URIRef("urn:dlp:query:" + uuid.uuid4().hex)
        graph.add((superclass, RDFS.subClassOf, marker))
        query = self._new_query_reasoner(graph)
        if query.consistency == "inconsistent":
            return True
        return query.entails(probe, RDF.type, marker)

    @_cached_query
    def equivalent_classes(self, left, right):
        """Test class equivalence with two independent subsumption probes.

        Combining both assumptions in one trial is unsound with nominals:
        fresh names can become equal and contaminate the other direction.
        """
        return self.subsumes(left, right) and self.subsumes(right, left)

    def _property_probe(self, assertions, conclusion):
        """Check a universal property implication using isolated fresh names.

        An inconsistent trial means the antecedent is impossible, so the
        implication holds vacuously. Exhausted probes never return a negative
        answer. Property arguments are named RDF properties.
        """
        self._guard()
        for _, predicate, _ in (*assertions, conclusion):
            if not isinstance(predicate, URIRef):
                raise ProfileError("Property probes require named RDF property IRIs")
        graph = copy_graph(self.graph)
        for assertion in assertions:
            graph.add(assertion)
        query = self._new_query_reasoner(graph)
        if query.consistency == "inconsistent":
            return True
        return query.entails(*conclusion)

    @_cached_query
    def property_subsumes(self, superproperty, subproperty):
        """Return whether every subproperty edge is a superproperty edge."""
        self._guard()
        if self._schema().proves_property_inclusion(superproperty, subproperty):
            return True
        a, b = BNode(), BNode()
        return self._property_probe(((a, subproperty, b),), (a, superproperty, b))

    @_cached_query
    def equivalent_properties(self, left, right):
        """Test exact property equivalence in independent trial ontologies."""
        return self.property_subsumes(left, right) and self.property_subsumes(right, left)

    @_cached_query
    def inverse_properties(self, left, right):
        """Test exact inverse equality, not merely inverse inclusion."""
        self._guard()
        schema = self._schema()
        if (schema.proves_property_inclusion(right, left, inverse=True)
                and schema.proves_property_inclusion(left, right, inverse=True)):
            return True
        a, b = BNode(), BNode()
        forward = self._property_probe(((a, left, b),), (b, right, a))
        return forward and self._property_probe(((a, right, b),), (b, left, a))

    @_cached_query
    def is_symmetric(self, predicate):
        """Test symmetry by assuming one fresh edge and checking its reverse."""
        self._guard()
        if self._schema().proves_symmetry(predicate):
            return True
        a, b = BNode(), BNode()
        return self._property_probe(((a, predicate, b),), (b, predicate, a))

    @_cached_query
    def is_transitive(self, predicate):
        """Test transitivity on a fresh two-edge path, regardless of ABox shape."""
        self._guard()
        if self._schema().proves_transitivity(predicate):
            return True
        a, b, c = BNode(), BNode(), BNode()
        return self._property_probe(((a, predicate, b), (b, predicate, c)),
                                    (a, predicate, c))

    @_cached_query
    def has_domain(self, predicate, concept):
        """Return whether every subject of predicate belongs to concept."""
        self._guard()
        if isinstance(concept, URIRef) and self._schema().proves_domain(predicate, concept):
            return True
        a, b = BNode(), BNode()
        return self._property_probe(((a, predicate, b),), (a, RDF.type, concept))

    @_cached_query
    def has_range(self, predicate, concept):
        """Return whether every object of predicate belongs to concept."""
        self._guard()
        if (isinstance(concept, URIRef)
                and self._schema().proves_domain(predicate, concept, position=1)):
            return True
        a, b = BNode(), BNode()
        return self._property_probe(((a, predicate, b),), (b, RDF.type, concept))

    @_cached_query
    def is_satisfiable(self, concept):
        self._guard()
        graph = copy_graph(self.graph)
        graph.add((BNode(), RDF.type, concept))
        query = self._new_query_reasoner(graph)
        if query.consistency == "inconsistent":
            return False
        query._guard()
        return True

    def update(self, *, add=(), remove=()):
        """Apply an RDF delta after validating its entire candidate ontology.

        Recompile the complete candidate before applying fact and rule deltas
        together. The engine selects incremental maintenance or a guarded
        rebuild when equality, functions, or incomplete reasoning require it.
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
        current_rules, candidate_rules = set(self.program.rules), set(program.rules)
        self.clear_query_cache()
        schema = self._schema_cache
        try:
            self.engine.update(add=program.facts - self.program.facts,
                               remove=self.program.facts - program.facts,
                               add_rules=candidate_rules - current_rules,
                               remove_rules=current_rules - candidate_rules)
        finally:
            # Also discard reentrant answers if a partially applied operation
            # raises; no old answer may be mistaken for the resulting state.
            self.clear_query_cache()
            self._schema_cache = None
        self.graph, self.program = candidate, program
        # Do not retain answers/views computed reentrantly during the update.
        self.clear_query_cache()
        self._schema_cache = schema if current_rules == candidate_rules else None
        self.compile_seconds = compile_seconds
        self.materialize_seconds = time.perf_counter() - started
        return self

    def to_graph(self, *, include_schema=True, expand_equality=True,
                 include_witnesses=False):
        """Export the completed materialization as RDF, optionally expanding aliases."""
        self._guard()
        self._sync_query_cache()
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
