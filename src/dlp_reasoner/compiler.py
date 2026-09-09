"""Strict, context-sensitive RDF/OWL to Horn translation (thesis §§4.5–5.2).

The parser deliberately rejects logical OWL syntax outside the selected DLP
fragment. Annotation triples and vocabulary declarations carry no ABox facts.
Datatypes may occur as literal values, but datatype range reasoning is excluded.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from itertools import combinations, product

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

from .model import EQ, NEQ, TOP, Atom, ProfileError, Program, Rule, Skolem, Var


@dataclass(frozen=True)
class _Expr:
    kind: str
    args: tuple = ()


_CONSTRUCTORS = {
    OWL.intersectionOf: "and", OWL.unionOf: "or", OWL.complementOf: "not",
    OWL.oneOf: "oneof",
}
_RESTRICTIONS = {
    OWL.someValuesFrom: "some", OWL.allValuesFrom: "all", OWL.hasValue: "value",
    OWL.minCardinality: "min", OWL.maxCardinality: "max", OWL.cardinality: "exact",
}
_STRUCTURAL = set(_CONSTRUCTORS) | set(_RESTRICTIONS) | {
    OWL.onProperty, RDF.first, RDF.rest, OWL.members, OWL.distinctMembers,
}
MAX_COMPILED_RULES = 100_000


_ANNOTATIONS = {
    RDFS.label, RDFS.comment, RDFS.seeAlso, RDFS.isDefinedBy,
    OWL.versionInfo, OWL.priorVersion, OWL.backwardCompatibleWith,
    OWL.incompatibleWith, OWL.versionIRI, OWL.deprecated,
    OWL.annotatedSource, OWL.annotatedProperty, OWL.annotatedTarget,
}
_DECLARATIONS = {
    OWL.Class, RDFS.Class, OWL.Restriction, OWL.ObjectProperty, OWL.DatatypeProperty,
    OWL.AnnotationProperty, RDF.Property, OWL.Ontology, RDF.List, RDFS.Datatype,
    OWL.Axiom, OWL.Annotation, OWL.DeprecatedClass, OWL.DeprecatedProperty,
}
_CHARACTERISTICS = {
    OWL.TransitiveProperty, OWL.SymmetricProperty, OWL.FunctionalProperty,
    OWL.InverseFunctionalProperty,
}
_AXIOMS = {
    RDFS.subClassOf, OWL.equivalentClass, OWL.disjointWith, RDFS.subPropertyOf,
    OWL.equivalentProperty, OWL.inverseOf, RDFS.domain, RDFS.range,
    OWL.sameAs, OWL.differentFrom,
}
_DATATYPES = {RDFS.Literal, RDF.langString, RDF.XMLLiteral, RDF.HTML, OWL.real, OWL.rational}


class _Compiler:
    def __init__(self, graph: Graph, profile: str):
        if not isinstance(profile, str):
            raise ProfileError("DLP profile must be L0, L1, L2, or L3")
        profile = profile.upper()
        if profile not in {"L0", "L1", "L2", "L3"}:
            raise ProfileError(f"Unknown DLP profile {profile!r}; choose L0, L1, L2, or L3")
        self.graph = graph
        self.level = int(profile[1])
        self.program = Program(profile=profile)
        self.counter = 0
        self.cache: dict[tuple, _Expr] = {}
        self.annotation_properties = set(graph.subjects(RDF.type, OWL.AnnotationProperty))
        self.datatypes = set(graph.subjects(RDF.type, RDFS.Datatype))
        self.auxiliary_definitions: set[_Expr] = set()
        self.body_definitions: set[_Expr] = set()
        self.expressions = set(graph.subjects(RDF.type, OWL.Restriction))
        for predicate in set(_CONSTRUCTORS) | set(_RESTRICTIONS) | {OWL.onProperty}:
            self.expressions.update(graph.subjects(predicate, None))

    def fail(self, message, node=None):
        suffix = f" (at {node.n3()})" if hasattr(node, "n3") else ""
        raise ProfileError(f"{self.program.profile}: {message}{suffix}")

    def require(self, level, construct, node=None):
        if self.level < level:
            self.fail(f"{construct} requires L{level} or higher", node)

    def fresh(self):
        self.counter += 1
        return Var(f"v{self.counter}")

    def one(self, node, predicate, required=True):
        values = list(self.graph.objects(node, predicate))
        if len(values) != 1 and (required or values):
            self.fail(f"Expected exactly one {predicate.n3()}, found {len(values)}", node)
        return values[0] if values else None

    def rdf_list(self, head):
        values, visited = [], set()
        while head != RDF.nil:
            if not isinstance(head, (BNode, URIRef)) or head in visited:
                self.fail("Malformed or cyclic RDF list", head)
            visited.add(head)
            values.append(self.one(head, RDF.first))
            head = self.one(head, RDF.rest)
        return tuple(values)

    def individual(self, node):
        if not isinstance(node, (URIRef, BNode, Literal)):
            self.fail("Expected an RDF individual or literal", node)
        return node

    def property(self, node, visited=frozenset()):
        if isinstance(node, URIRef):
            if node in {OWL.topObjectProperty, OWL.bottomObjectProperty,
                        OWL.topDataProperty, OWL.bottomDataProperty}:
                self.fail("Built-in top/bottom properties are outside this implementation", node)
            return node, False
        if not isinstance(node, BNode) or node in visited:
            self.fail("Expected a named property or acyclic owl:inverseOf expression", node)
        target = self.one(node, OWL.inverseOf)
        predicate, inverse = self.property(target, visited | {node})
        return predicate, not inverse

    def prop_atom(self, prop, left, right):
        predicate, inverse = prop
        return Atom(predicate, (right, left) if inverse else (left, right))

    def expr(self, node, expand_named=False, stack=frozenset()):
        key = (node, expand_named)
        if key in self.cache:
            return self.cache[key]
        if node == OWL.Thing:
            return _Expr("top")
        if node == OWL.Nothing:
            return _Expr("bottom")
        if (node in _DATATYPES or node in self.datatypes
                or isinstance(node, URIRef) and str(node).startswith(str(XSD))):
            self.fail("Datatype class/range reasoning is unsupported; literal facts are allowed", node)
        if isinstance(node, URIRef) and not expand_named:
            return _Expr("atom", (node,))
        if node in stack:
            self.fail("Cyclic anonymous class expression", node)
        if not isinstance(node, (BNode, URIRef)):
            self.fail("Expected a named class or anonymous class expression", node)
        stack = stack | {node}
        constructors = [(p, k) for p, k in _CONSTRUCTORS.items() if (node, p, None) in self.graph]
        restrictions = [(p, k) for p, k in _RESTRICTIONS.items() if (node, p, None) in self.graph]
        if constructors and (restrictions or (node, OWL.onProperty, None) in self.graph):
            self.fail("Class expression combines a Boolean constructor and a restriction", node)
        if len(constructors) > 1 or len(restrictions) > 1:
            self.fail("Class expression must have exactly one constructor; use intersectionOf", node)
        if constructors:
            predicate, kind = constructors[0]
            obj = self.one(node, predicate)
            if kind == "not":
                result = _Expr(kind, (self.expr(obj, stack=stack),))
            elif kind == "oneof":
                result = _Expr(kind, self.rdf_list(obj))
                for item in result.args:
                    if isinstance(item, Literal):
                        self.fail("Literal enumeration is a datatype restriction, which is unsupported", node)
                    self.individual(item)
            else:
                result = _Expr(kind, tuple(self.expr(x, stack=stack) for x in self.rdf_list(obj)))
        elif restrictions:
            predicate, kind = restrictions[0]
            prop = self.property(self.one(node, OWL.onProperty))
            obj = self.one(node, predicate)
            if kind in {"some", "all"}:
                obj = self.expr(obj, stack=stack)
            elif kind in {"min", "max", "exact"}:
                if (not isinstance(obj, Literal) or isinstance(obj.toPython(), bool)
                        or not isinstance(obj.toPython(), int) or obj.toPython() < 0):
                    self.fail("Cardinality must be a non-negative integer literal", node)
                obj = int(obj)
            else:
                self.individual(obj)
            result = _Expr(kind, (prop, obj))
        else:
            self.fail("Anonymous class has no supported constructor", node)
        result = self.normalize(result)
        self.cache[key] = result
        return result

    def normalize(self, expr):
        """Thesis Table 4.2: simplify before deciding which profile is needed."""
        k, a = expr.kind, expr.args
        if k in {"and", "or"}:
            children = []
            for child in a:
                child = self.normalize(child)
                children.extend(child.args if child.kind == k else (child,))
            annihilator, identity = (("bottom", "top") if k == "and" else ("top", "bottom"))
            if any(c.kind == annihilator for c in children):
                return _Expr(annihilator)
            children = list(dict.fromkeys(c for c in children if c.kind != identity))
            if any(c.kind == "not" and c.args[0] in children for c in children):
                return _Expr(annihilator)
            if not children:
                return _Expr(identity)
            if len(children) == 1:
                return children[0]
            return _Expr(k, tuple(children))
        if k == "not":
            child = self.normalize(a[0])
            ck, ca = child.kind, child.args
            if ck == "not":
                return self.normalize(ca[0])
            if ck in {"top", "bottom"}:
                return _Expr("bottom" if ck == "top" else "top")
            if ck in {"and", "or"}:
                return self.normalize(_Expr("or" if ck == "and" else "and", tuple(
                    _Expr("not", (item,)) for item in ca)))
            if ck in {"some", "all"}:
                return self.normalize(_Expr("all" if ck == "some" else "some", (
                    ca[0], _Expr("not", (ca[1],)))))
            if ck == "min":
                return (_Expr("bottom") if ca[1] == 0 else
                        self.normalize(_Expr("max", (ca[0], ca[1] - 1))))
            if ck == "max":
                return self.normalize(_Expr("min", (ca[0], ca[1] + 1)))
            return _Expr("not", (child,))
        if k in {"some", "all"}:
            child = self.normalize(a[1])
            if k == "some" and child.kind == "bottom":
                return child
            if k == "all" and child.kind == "top":
                return child
            if k == "some" and child.kind == "oneof" and len(child.args) == 1:
                return _Expr("value", (a[0], child.args[0]))
            return _Expr(k, (a[0], child))
        if k == "min" and a[1] == 0:
            return _Expr("top")
        if k == "exact" and a[1] == 0:
            return _Expr("max", a)
        if k == "oneof":
            return _Expr("oneof", tuple(dict.fromkeys(a))) if a else _Expr("bottom")
        return expr

    def body_reference(self, expr, x):
        """Name an antecedent expression using a one-way Horn definition."""
        digest = sha256(repr(expr).encode()).hexdigest()[:24]
        predicate = f"urn:dlp:internal:body:{digest}"
        if expr not in self.body_definitions:
            self.body_definitions.add(expr)
            y = self.fresh()
            for conjunct in self.body(expr, y, factor=False):
                self.emit(Atom(predicate, (y,)), conjunct, "Structural body definition")
        return [(Atom(predicate, (x,)),)]

    def body(self, expr, x, factor=True):
        """Return Horn bodies, factoring subexpressions before distribution.

        One-way definitions suffice on the antecedent side. Naming every Boolean
        or existential subexpression prevents exponential conjunction/union DNF.
        """
        k, a = expr.kind, expr.args
        if factor and k in {"and", "or", "some"}:
            return self.body_reference(expr, x)
        if k == "atom":
            return [(Atom(a[0], (x,)),)]
        if k == "top":
            self.require(1, "owl:Thing / minimum cardinality zero")
            return [(Atom(TOP, (x,)),)]
        if k == "bottom":
            self.require(2, "owl:Nothing")
            return []
        if k == "and":
            if not a:
                return self.body(_Expr("top"), x)
            # Enumerations are disjunctions too: distributing several oneOf
            # lists here would recreate the exponential DNF of thesis p. 133.
            parts = [self.body_reference(child, x) if child.kind == "oneof" else
                     self.body(child, x) for child in a]
            return [tuple(atom for term in terms for atom in term) for terms in product(*parts)]
        if k == "or":
            if not a:
                self.require(2, "empty union / owl:Nothing")
            return [term for child in a for term in self.body(child, x)]
        if k == "value":
            return [(self.prop_atom(a[0], x, a[1]),)]
        if k == "some":
            y = self.fresh()
            return [(self.prop_atom(a[0], x, y),) + term for term in self.body(a[1], y)]
        if k == "oneof":
            self.require(1, "owl:oneOf")
            return [(Atom(TOP, (x,)), Atom(EQ, (x, item))) for item in a]
        if k == "min":
            self.require(1, "minimum cardinality")
            if a[1] == 0:
                return [(Atom(TOP, (x,)),)]
            if a[1] == 1:
                return [(self.prop_atom(a[0], x, self.fresh()),)]
        if k == "not":
            self.fail("Complement on the left of an inclusion is not Horn-expressible")
        self.fail(f"{k} class expression is unsupported on the left of an inclusion")

    def emit(self, head, body=(), label=""):
        body = tuple(dict.fromkeys(body))
        if head is not None and not body:
            def nonground(term):
                return isinstance(term, Var) or isinstance(term, Skolem) and any(
                    nonground(arg) for arg in term.args)
            if not any(nonground(term) for term in head.args):
                self.program.facts.add(head)
                return
        if len(self.program.rules) >= MAX_COMPILED_RULES:
            self.fail(f"Compilation exceeds the {MAX_COMPILED_RULES:,}-rule budget; "
                      "reduce the ontology or cardinality restrictions")
        # Variables are local to each rule. Canonical names keep unchanged
        # axioms stable when unrelated axioms shift the compiler's fresh IDs.
        variables = {}

        def canonical(term):
            if isinstance(term, Var):
                if term not in variables:
                    variables[term] = Var(f"v{len(variables) + 1}")
                return variables[term]
            if isinstance(term, Skolem):
                return Skolem(term.symbol, tuple(canonical(arg) for arg in term.args))
            return term

        def canonical_atom(atom):
            return Atom(atom.predicate, tuple(canonical(term) for term in atom.args))

        self.program.rules.append(Rule(canonical_atom(head) if head else None,
                                       tuple(canonical_atom(atom) for atom in body), label))

    def witness(self, expr, x, index=0):
        digest = sha256(repr(expr).encode()).hexdigest()[:24]
        return Skolem(f"urn:dlp:skolem:{digest}:{index}", (x,))

    def head(self, expr, x, body=(), label=""):
        if isinstance(x, Skolem) and expr.kind not in {"atom", "top"}:
            # Name complex witness fillers so rule bodies need no term unification.
            digest = sha256(repr(expr).encode()).hexdigest()[:24]
            predicate = f"urn:dlp:internal:expression:{digest}"
            self.emit(Atom(predicate, (x,)), body, label)
            if expr not in self.auxiliary_definitions:
                self.auxiliary_definitions.add(expr)
                y = self.fresh()
                self.head(expr, y, (Atom(predicate, (y,)),), label)
            return
        k, a = expr.kind, expr.args
        if k == "atom":
            self.emit(Atom(a[0], (x,)), body, label)
        elif k == "top":
            self.require(1, "owl:Thing / minimum cardinality zero")
            # Retain the active-domain individual even for tautological assertions.
            self.emit(Atom(TOP, (x,)), body, label)
        elif k == "bottom":
            self.require(2, "owl:Nothing")
            self.emit(None, body, label or "An individual belongs to owl:Nothing")
        elif k == "and":
            if not a:
                self.head(_Expr("top"), x, body, label)
            for child in a:
                self.head(child, x, body, label)
        elif k == "value":
            self.emit(self.prop_atom(a[0], x, a[1]), body, label)
        elif k == "all":
            y = self.fresh()
            self.head(a[1], y, body + (self.prop_atom(a[0], x, y),), label)
        elif k == "some":
            if a[1].kind == "bottom":
                self.head(a[1], x, body, label)
                return
            self.require(3, "Existential restriction on the right (owl:someValuesFrom)")
            witness = self.witness(expr, x)
            self.emit(self.prop_atom(a[0], x, witness), body, label)
            self.head(a[1], witness, body, label)
        elif k == "oneof":
            if len(a) == 0:
                self.head(_Expr("bottom"), x, body, label)
                return
            self.require(1, "owl:oneOf")
            if len(a) != 1:
                self.fail("owl:oneOf on the right must contain exactly one individual")
            self.emit(Atom(EQ, (x, a[0])), body, label)
        elif k == "not":
            self.require(2, "Complement / integrity constraints")
            # B -> not C is the constraint B and C -> false; C must be a legal body.
            for negative in self.body(a[0], x):
                self.emit(None, body + negative, label or "Complement class violation")
        elif k in {"min", "max", "exact"}:
            self.cardinality(expr, x, body, label)
        elif k == "or":
            if len(a) == 0:
                self.head(_Expr("bottom"), x, body, label)
            elif len(a) == 1:
                self.head(a[0], x, body, label)
            else:
                negatives = [child.args[0] for child in a if child.kind == "not"]
                positives = [child for child in a if child.kind != "not"]
                if negatives and len(positives) <= 1:
                    self.require(2, "Negation / integrity constraints")
                    for extra in self.body(self.normalize(_Expr("and", tuple(negatives))), x):
                        self.head(positives[0] if positives else _Expr("bottom"), x,
                                  body + extra, label)
                else:
                    self.fail("Union on the right of an inclusion is not Horn-expressible")
        else:
            self.fail(f"Unsupported right-hand class expression: {k}")

    def cardinality(self, expr, x, body, label):
        k, (prop, n) = expr.kind, expr.args
        if k == "exact":
            self.cardinality(_Expr("min", (prop, n)), x, body, label)
            self.cardinality(_Expr("max", (prop, n)), x, body, label)
        elif k == "min":
            self.require(1, "minimum cardinality")
            if n == 0:
                self.head(_Expr("top"), x, body, label)
                return
            self.require(3, "Positive minimum cardinality on the right")
            if n * (n + 1) // 2 + len(self.program.rules) > MAX_COMPILED_RULES:
                self.fail(f"Minimum cardinality {n} exceeds the {MAX_COMPILED_RULES:,}-rule "
                          "compilation budget (pairwise witness inequalities)")
            witnesses = [self.witness(expr, x, i) for i in range(n)]
            for witness in witnesses:
                self.emit(self.prop_atom(prop, x, witness), body, label)
            for left, right in combinations(witnesses, 2):
                self.emit(Atom(NEQ, (left, right)), body, label)
        elif n == 0:
            self.require(2, "Maximum cardinality zero")
            self.emit(None, body + (self.prop_atom(prop, x, self.fresh()),), label)
        elif n == 1:
            self.require(1, "Maximum cardinality one")
            y, z = self.fresh(), self.fresh()
            self.emit(Atom(EQ, (y, z)), body + (
                self.prop_atom(prop, x, y), self.prop_atom(prop, x, z)), label)
        else:
            self.fail("Maximum cardinality above one is not Horn-expressible")

    def inclusion(self, left, right, label):
        x = self.fresh()
        # Validate the head even if the left denotes the empty class.
        bodies = self.body(left, x)
        if not bodies:
            prior_rules, prior_facts = len(self.program.rules), self.program.facts.copy()
            prior_aux = self.auxiliary_definitions.copy(), self.body_definitions.copy()
            self.head(right, x, (Atom(TOP, (x,)),), label)
            del self.program.rules[prior_rules:]
            self.program.facts = prior_facts
            self.auxiliary_definitions, self.body_definitions = prior_aux
        for body in bodies:
            self.head(right, x, body, label)

    def disjoint(self, left, right, label):
        self.require(2, "Disjoint classes")
        x = self.fresh()
        for first, second in product(self.body(left, x), self.body(right, x)):
            self.emit(None, first + second, label)

    def compile(self):
        # Preflight reserved vocabulary: never silently erase unknown OWL axioms.
        for s, p, o in self.graph:
            if p == OWL.imports:
                self.fail("owl:imports must be resolved and import triples removed before compilation", s)
            if str(p).startswith(str(OWL)) and p not in _STRUCTURAL | _ANNOTATIONS | _AXIOMS:
                self.fail(f"Unsupported OWL logical predicate {p.n3()}", s)
            if p == RDF.type and str(o).startswith(str(OWL)) and o not in (
                    _DECLARATIONS | _CHARACTERISTICS | {
                        OWL.NamedIndividual, OWL.AllDifferent, OWL.AllDisjointClasses,
                        OWL.Thing, OWL.Nothing,
                    }):
                self.fail(f"Unsupported OWL type/characteristic {o.n3()}", s)

        # Validate every structural node, including unused malformed definitions.
        for node in sorted(self.expressions, key=str):
            self.expr(node, expand_named=True)

        # A named class with a constructor denotes equivalence to that expression.
        for node in sorted(self.expressions, key=str):
            if isinstance(node, URIRef):
                expr = self.expr(node, expand_named=True)
                atom = self.expr(node)
                self.inclusion(atom, expr, f"Definition of {node}")
                self.inclusion(expr, atom, f"Definition of {node}")

        for s, p, o in sorted(self.graph, key=lambda triple: tuple(map(str, triple))):
            label = f"{s.n3()} {p.n3()} {o.n3()}"
            if p in _STRUCTURAL or p in _ANNOTATIONS or p in self.annotation_properties:
                continue
            if s in self.annotation_properties and p in {
                    RDFS.subPropertyOf, RDFS.domain, RDFS.range}:
                continue
            if p == RDF.type:
                if o in _DECLARATIONS:
                    continue
                if o == OWL.NamedIndividual:
                    self.emit(Atom(TOP, (s,)))
                elif o == OWL.AllDifferent:
                    self.require(2, "owl:AllDifferent", s)
                    list_nodes = list(self.graph.objects(s, OWL.distinctMembers)) + list(
                        self.graph.objects(s, OWL.members))
                    if len(list_nodes) != 1:
                        self.fail("owl:AllDifferent requires exactly one member list", s)
                    members = self.rdf_list(list_nodes[0])
                    for left, right in combinations(members, 2):
                        self.emit(Atom(NEQ, (left, right)))
                elif o == OWL.AllDisjointClasses:
                    self.require(2, "Disjoint classes", s)
                    members = self.rdf_list(self.one(s, OWL.members))
                    for left, right in combinations(members, 2):
                        self.disjoint(self.expr(left), self.expr(right), label)
                elif o in _CHARACTERISTICS:
                    self.characteristic(s, o, label)
                else:
                    self.head(self.expr(o), s, label=label)
            elif p in {RDFS.subClassOf, OWL.equivalentClass}:
                self.inclusion(self.expr(s), self.expr(o), label)
                if p == OWL.equivalentClass:
                    self.inclusion(self.expr(o), self.expr(s), label)
            elif p == OWL.disjointWith:
                self.disjoint(self.expr(s), self.expr(o), label)
            elif p in {RDFS.subPropertyOf, OWL.equivalentProperty, OWL.inverseOf}:
                if p == OWL.inverseOf and isinstance(s, BNode):
                    self.property(s)
                    continue
                left, right = self.property(s), self.property(o)
                x, y = self.fresh(), self.fresh()
                if p == OWL.inverseOf:
                    right = (right[0], not right[1])
                self.emit(self.prop_atom(right, x, y), (self.prop_atom(left, x, y),), label)
                if p != RDFS.subPropertyOf:
                    self.emit(self.prop_atom(left, x, y), (self.prop_atom(right, x, y),), label)
            elif p in {RDFS.domain, RDFS.range}:
                x, y = self.fresh(), self.fresh()
                self.head(self.expr(o), x if p == RDFS.domain else y,
                          (self.prop_atom(self.property(s), x, y),), label)
            elif p == OWL.sameAs:
                self.require(1, "owl:sameAs", s)
                self.emit(Atom(EQ, (s, o)))
            elif p == OWL.differentFrom:
                self.require(2, "owl:differentFrom", s)
                self.emit(Atom(NEQ, (s, o)))
            else:
                if not isinstance(p, URIRef):
                    self.fail("RDF property assertions require an IRI predicate", p)
                self.property(p)
                self.emit(Atom(p, (s, o)))
        self.program.rules = list(dict.fromkeys(self.program.rules))
        return self.program

    def characteristic(self, node, kind, label):
        prop = self.property(node)
        x, y, z = self.fresh(), self.fresh(), self.fresh()
        if kind == OWL.TransitiveProperty:
            self.emit(self.prop_atom(prop, x, z), (
                self.prop_atom(prop, x, y), self.prop_atom(prop, y, z)), label)
        elif kind == OWL.SymmetricProperty:
            self.emit(self.prop_atom(prop, y, x), (self.prop_atom(prop, x, y),), label)
        else:
            self.require(1, "Property functionality", node)
            first, second = ((x, y), (x, z)) if kind == OWL.FunctionalProperty else (
                (y, x), (z, x))
            self.emit(Atom(EQ, (y, z)), (
                self.prop_atom(prop, *first), self.prop_atom(prop, *second)), label)


def compile_graph(graph: Graph, profile: str = "L2") -> Program:
    """Compile an RDFLib graph into the selected thesis DLP profile.

    Unsupported logical axioms and malformed syntax raise :class:`ProfileError`.
    No external documents are fetched. L3 introduces Skolem terms and therefore
    requires resource-bounded evaluation for potentially infinite ontologies.
    """
    try:
        return _Compiler(graph, profile).compile()
    except RecursionError as exc:
        raise ProfileError("Class expression nesting exceeds Python's safe recursion depth; "
                           "introduce named intermediate classes") from exc
