"""Parse the thesis's concrete DLP syntax (Appendix A, pp. 233–236).

The syntax is the OWL-style ``Namespace(...) Ontology(...)`` grammar, not
mathematical DL notation. Parsing builds RDF locally; ``compile_graph`` remains
responsible for position-sensitive L0–L3 and datatype-reasoning restrictions.

Two deliberate generalizations reconcile the appendix with Chapter 5: class
descriptions may use every constructor in any position, and cardinalities are
nonnegative integers. Thus the L3 existential/minimum-cardinality consequents
of §5.1.4 can be written; the compiler still rejects non-Horn positions.
Property characteristics may be combined, as they may in RDF/OWL.
Prefixed local names also allow hyphens after the initial letter, so existing
IRIs such as ``bach:johann-sebastian`` can use namespace prefixes unchanged.

Table 5.4 defines ``Class(A partial localdomain(P D))`` as ``exists P.A <= D``:
the class A constrains the *filler*, not the subject. ``localrange(P R)`` means
``A <= forall P.R``. Multiple components of one restriction are a conjunction
of separate OWL restrictions, never several constructors on one RDF node.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
import re

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

from .model import ProfileError


class DLPParseError(ProfileError):
    """A concrete-syntax error with a source name and one-based location."""

    def __init__(self, message: str, *, source: str, line: int, column: int):
        self.source = source
        self.line = line
        self.column = column
        super().__init__(f"{source}:{line}:{column}: {message}")


@dataclass(frozen=True)
class _Token:
    kind: str
    value: str
    line: int
    column: int


_BUILTINS = {"rdf": str(RDF), "rdfs": str(RDFS), "owl": str(OWL), "xsd": str(XSD)}
_RESERVED_NAMESPACES = (str(RDF), str(RDFS), str(OWL), str(XSD))
_ANNOTATIONS = {
    RDFS.label, RDFS.comment, RDFS.seeAlso, RDFS.isDefinedBy,
    OWL.versionInfo, OWL.priorVersion, OWL.backwardCompatibleWith,
    OWL.incompatibleWith, OWL.versionIRI, OWL.deprecated,
    OWL.annotatedSource, OWL.annotatedProperty, OWL.annotatedTarget,
}
_BUILTIN_CLASSES = {OWL.Thing, OWL.Nothing, RDFS.Literal, RDF.langString,
                    RDF.XMLLiteral, RDF.HTML, OWL.real, OWL.rational}
_RESTRICTIONS = {
    "someValuesFrom": OWL.someValuesFrom,
    "allValuesFrom": OWL.allValuesFrom,
    "value": OWL.hasValue,
    "minCardinality": OWL.minCardinality,
    "maxCardinality": OWL.maxCardinality,
    "cardinality": OWL.cardinality,
}
_CHARACTERISTICS = {
    "Symmetric": OWL.SymmetricProperty,
    "Functional": OWL.FunctionalProperty,
    "InverseFunctional": OWL.InverseFunctionalProperty,
    "Transitive": OWL.TransitiveProperty,
}


def _lex(text: str, source: str) -> list[_Token]:
    tokens = []
    index, line, column = 0, 1, 1

    def fail(message, start_line, start_column):
        raise DLPParseError(message, source=source, line=start_line, column=start_column)

    def advance(end):
        nonlocal index, line, column
        segment = text[index:end]
        count = segment.count("\n")
        if count:
            line += count
            column = len(segment.rsplit("\n", 1)[1]) + 1
        else:
            column += len(segment)
        index = end

    while index < len(text):
        char = text[index]
        if char.isspace():
            advance(index + 1)
            continue
        start, start_line, start_column = index, line, column
        if text.startswith("//", index):
            end = text.find("\n", index + 2)
            advance(len(text) if end < 0 else end)
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                fail("Unterminated block comment", start_line, start_column)
            advance(end + 2)
            continue
        if char in "()=@":
            kind, value, end = char, char, index + 1
        elif text.startswith("^^", index):
            kind, value, end = "^^", "^^", index + 2
        elif char == "<":
            end = text.find(">", index + 1)
            if end < 0:
                fail("Unterminated IRI; expected '>'", start_line, start_column)
            kind, value, end = "IRI", text[index + 1:end], end + 1
        elif char == '"':
            end, chars = index + 1, []
            while end < len(text) and text[end] != '"':
                if text[end] == "\\":
                    end += 1
                    if end == len(text):
                        fail("Unterminated string literal", start_line, start_column)
                    if text[end] not in {'"', "\\"}:
                        fail("Only escaped quotes and backslashes are defined by Appendix A",
                             start_line, start_column)
                chars.append(text[end])
                end += 1
            if end == len(text):
                fail("Unterminated string literal", start_line, start_column)
            kind, value, end = "STRING", "".join(chars), end + 1
        else:
            end = index
            while (end < len(text) and not text[end].isspace()
                   and text[end] not in '()=@^<>"'):
                if text.startswith("//", end) or text.startswith("/*", end):
                    break
                end += 1
            if end == index:
                fail(f"Unexpected character {char!r}", start_line, start_column)
            kind, value = "WORD", text[index:end]
        tokens.append(_Token(kind, value, start_line, start_column))
        advance(end)
        assert index > start
    tokens.append(_Token("EOF", "end of input", line, column))
    return tokens


class _Parser:
    def __init__(self, text: str, source: str):
        self.source = source
        self.tokens = _lex(text, source)
        self.index = 0
        self.graph = Graph()
        self.namespaces = _BUILTINS.copy()
        self.explicit_namespaces: dict[str, str] = {}
        self.annotation_properties: dict[URIRef, _Token] = {}
        self.logical_properties: dict[URIRef, _Token] = {}
        self.property_kinds: dict[URIRef, tuple[str, _Token]] = {}
        self.property_values: list[tuple[URIRef, object, _Token]] = []
        self.property_restrictions: list[tuple[URIRef, str, object, _Token]] = []
        self.property_links: list[tuple[URIRef, URIRef, _Token]] = []
        self.object_property_uses: list[tuple[URIRef, _Token]] = []

    @property
    def current(self):
        return self.tokens[self.index]

    def fail(self, message, token=None):
        token = token or self.current
        raise DLPParseError(message, source=self.source, line=token.line, column=token.column)

    def take(self):
        token = self.current
        if token.kind != "EOF":
            self.index += 1
        return token

    def at(self, value):
        kind = value if value in {"(", ")", "=", "@", "^^"} else "WORD"
        return self.current.kind == kind and self.current.value == value

    def expect(self, value):
        if not self.at(value):
            self.fail(f"Expected {value!r}, found {self.current.value!r}")
        return self.take()

    def begin(self, name):
        self.expect(name)
        self.expect("(")

    def iri(self):
        token = self.take()
        if token.kind == "IRI":
            value = token.value
            if (not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", value)
                    or any(c.isspace() or ord(c) < 32 or c in '<>"{}|^`\\' for c in value)):
                self.fail("Expected an absolute IRI", token)
            return URIRef(value)
        if token.kind == "WORD" and ":" in token.value:
            prefix, local = token.value.split(":", 1)
            if (not prefix or not all(c.isalpha() for c in prefix)
                    or not local or not local[0].isalpha()
                    or not all(c.isalpha() or c.isnumeric() or c in "_-" for c in local)):
                self.fail("Invalid QName; use <absolute-IRI> for unsupported names", token)
            if prefix not in self.namespaces:
                self.fail(f"Undeclared namespace prefix {prefix!r}", token)
            return URIRef(self.namespaces[prefix] + local)
        self.fail(f"Expected an IRI or prefixed name, found {token.value!r}", token)

    def starts_iri(self):
        return (self.current.kind == "IRI" or
                self.current.kind == "WORD" and ":" in self.current.value)

    def class_iri(self):
        token, node = self.current, self.iri()
        if (str(node).startswith(_RESERVED_NAMESPACES) and node not in _BUILTIN_CLASSES
                and not str(node).startswith(str(XSD))):
            self.fail(f"Reserved vocabulary <{node}> cannot be used as a class description", token)
        return node

    def property_iri(self):
        token = self.current
        node = self.iri()
        if str(node).startswith(_RESERVED_NAMESPACES):
            self.fail(f"Reserved vocabulary <{node}> cannot be used as a logical property", token)
        self.logical_properties.setdefault(node, token)
        return node

    def annotation_property(self, node, token):
        if node not in _ANNOTATIONS and str(node).startswith(_RESERVED_NAMESPACES):
            self.fail(f"Reserved vocabulary <{node}> cannot be used as an annotation property",
                      token)
        self.annotation_properties.setdefault(node, token)
        if node not in _ANNOTATIONS:
            self.graph.add((node, RDF.type, OWL.AnnotationProperty))

    def literal(self):
        token = self.take()
        if token.kind != "STRING":
            self.fail("Expected a quoted literal", token)
        if self.at("@"):
            self.take()
            language = self.take()
            if language.kind != "WORD" or not re.fullmatch(r"[a-z]+(?:-[a-z0-9]+)*",
                                                          language.value):
                self.fail("Invalid language tag (expected lowercase letters and subtags)", language)
            return Literal(token.value, lang=language.value)
        if self.at("^^"):
            self.take()
            return Literal(token.value, datatype=self.iri(), normalize=False)
        return Literal(token.value)

    def value(self, *, nested=True):
        if self.current.kind == "STRING":
            return self.literal()
        if nested and self.at("Individual"):
            return self.individual()
        return self.iri()

    def rdf_list(self, values):
        head = RDF.nil
        for value in reversed(values):
            cell = BNode()
            self.graph.add((cell, RDF.first, value))
            self.graph.add((cell, RDF.rest, head))
            head = cell
        return head

    def boolean(self, predicate, values):
        node = BNode()
        self.graph.add((node, predicate, self.rdf_list(values)))
        return node

    def conjunction(self, values):
        return values[0] if len(values) == 1 else self.boolean(OWL.intersectionOf, values)

    def restriction_node(self, prop, predicate, value):
        node = BNode()
        self.graph.add((node, RDF.type, OWL.Restriction))
        self.graph.add((node, OWL.onProperty, prop))
        self.graph.add((node, predicate, value))
        return node

    def description(self):
        if self.starts_iri():
            return self.class_iri()
        name = self.current.value
        if name in {"intersectionOf", "unionOf", "oneOf"}:
            self.begin(name)
            values = []
            while not self.at(")"):
                values.append(self.value(nested=False) if name == "oneOf" else self.description())
            self.expect(")")
            predicate = {"intersectionOf": OWL.intersectionOf, "unionOf": OWL.unionOf,
                         "oneOf": OWL.oneOf}[name]
            return self.boolean(predicate, values)
        if name == "complementOf":
            self.begin(name)
            node, value = BNode(), self.description()
            self.expect(")")
            self.graph.add((node, OWL.complementOf, value))
            return node
        if name == "restriction":
            self.begin(name)
            prop = self.property_iri()
            values = []
            while not self.at(")"):
                component = self.current
                name = component.value
                if name not in _RESTRICTIONS:
                    self.fail(f"Unknown restriction component {name!r}")
                self.begin(name)
                if name in {"someValuesFrom", "allValuesFrom"}:
                    value = self.description()
                elif name == "value":
                    value = self.value(nested=False)
                    self.property_values.append((prop, value, component))
                else:
                    number = self.take()
                    if number.kind != "WORD" or not re.fullmatch(r"[0-9]+", number.value):
                        self.fail("Cardinality must be a non-negative integer", number)
                    try:
                        value = Literal(int(number.value), datatype=XSD.nonNegativeInteger)
                    except ValueError:
                        self.fail("Cardinality integer is too large", number)
                self.expect(")")
                values.append(self.restriction_node(prop, _RESTRICTIONS[name], value))
                self.property_restrictions.append((prop, name, value, component))
            if not values:
                self.fail("A restriction requires at least one component")
            self.expect(")")
            return self.conjunction(values)
        self.fail(f"Expected a class description, found {name!r}")

    def annotation(self, subject, name="annotation"):
        self.begin(name)
        token, prop = self.current, self.iri()
        self.annotation_property(prop, token)
        value = self.value()
        self.expect(")")
        self.graph.add((subject, prop, value))

    def annotations(self, subject):
        while self.at("annotation"):
            self.annotation(subject)

    def deprecated(self, subject, declaration):
        self.graph.add((subject, RDF.type, declaration))
        if self.at("Deprecated"):
            self.take()
            deprecated = {OWL.Class: OWL.DeprecatedClass,
                          OWL.ObjectProperty: OWL.DeprecatedProperty,
                          OWL.DatatypeProperty: OWL.DeprecatedProperty}.get(declaration)
            if deprecated is None:
                self.graph.add((subject, OWL.deprecated, Literal(True)))
            else:
                self.graph.add((subject, RDF.type, deprecated))

    def individual(self):
        self.begin("Individual")
        node = self.iri() if self.starts_iri() else BNode()
        self.annotations(node)
        asserted = False
        while self.at("type"):
            self.begin("type")
            self.graph.add((node, RDF.type, self.description()))
            self.expect(")")
            asserted = True
        while self.at("value"):
            token = self.current
            self.begin("value")
            prop = self.property_iri()
            value = self.value()
            self.graph.add((node, prop, value))
            self.property_values.append((prop, value, token))
            self.expect(")")
            asserted = True
        self.expect(")")
        # Preserve domain membership for otherwise empty individual declarations.
        if not asserted:
            self.graph.add((node, RDF.type, OWL.NamedIndividual))
        return node

    def class_axiom(self, name):
        self.begin(name)
        node = self.class_iri()
        self.deprecated(node, OWL.Class)
        if name == "EnumeratedClass":
            self.annotations(node)
            value = self.iri()
            self.expect(")")
            # Separate definitions must conjoin, including repeated declarations.
            # Multiple direct owl:oneOf objects on the named class are malformed.
            self.graph.add((node, OWL.equivalentClass, self.boolean(OWL.oneOf, [value])))
            return
        mode = self.take()
        if mode.kind != "WORD" or mode.value not in {"partial", "complete"}:
            self.fail("Class requires 'partial' or 'complete'", mode)
        self.annotations(node)
        descriptions = []
        while not self.at(")"):
            if self.at("localdomain") or self.at("localrange"):
                if mode.value != "partial":
                    self.fail("Local domain/range convenience forms require a partial Class")
                token = self.current
                name = self.current.value
                self.begin(name)
                prop, target = self.property_iri(), self.description()
                self.object_property_uses.append((prop, token))
                self.expect(")")
                if name == "localdomain":
                    source = self.restriction_node(prop, OWL.someValuesFrom, node)
                    self.graph.add((source, RDFS.subClassOf, target))
                else:
                    target = self.restriction_node(prop, OWL.allValuesFrom, target)
                    self.graph.add((node, RDFS.subClassOf, target))
            else:
                descriptions.append(self.description())
        self.expect(")")
        if mode.value == "partial":
            for description in descriptions:
                self.graph.add((node, RDFS.subClassOf, description))
        else:
            self.graph.add((node, OWL.equivalentClass, self.conjunction(descriptions)))

    def property_axiom(self, name):
        self.begin(name)
        token = self.current
        node = self.property_iri()
        prior = self.property_kinds.get(node)
        if prior and prior[0] != name:
            self.fail(f"Property <{node}> cannot be both ObjectProperty and DatatypeProperty", token)
        self.property_kinds[node] = (name, token)
        declaration = OWL.ObjectProperty if name == "ObjectProperty" else OWL.DatatypeProperty
        self.deprecated(node, declaration)
        self.annotations(node)
        seen = set()
        while not self.at(")"):
            token = self.current
            field = token.value
            if token.kind != "WORD":
                self.fail(f"Expected an {name} component, found {field!r}")
            if field in _CHARACTERISTICS:
                if name == "DatatypeProperty" and field != "Functional":
                    self.fail(f"{field} is only valid for ObjectProperty")
                if field in seen:
                    self.fail(f"Repeated property characteristic {field!r}")
                self.take()
                seen.add(field)
                self.graph.add((node, RDF.type, _CHARACTERISTICS[field]))
            elif field in {"super", "inverseOf", "domain", "range"}:
                if field == "range" and name == "DatatypeProperty":
                    self.fail("Datatype range reasoning is unsupported; literal facts are allowed")
                if field == "inverseOf":
                    if name != "ObjectProperty":
                        self.fail("inverseOf is only valid for ObjectProperty")
                    if field in seen:
                        self.fail("ObjectProperty accepts at most one inverseOf")
                    seen.add(field)
                self.begin(field)
                target = self.property_iri() if field in {"super", "inverseOf"} else self.description()
                self.expect(")")
                predicate = {"super": RDFS.subPropertyOf, "inverseOf": OWL.inverseOf,
                             "domain": RDFS.domain, "range": RDFS.range}[field]
                self.graph.add((node, predicate, target))
                if field in {"super", "inverseOf"}:
                    self.property_links.append((node, target, token))
            else:
                self.fail(f"Unknown {name} component {field!r}")
        self.expect(")")

    def relation_axiom(self, name):
        self.begin(name)
        values = []
        class_names = {"SubClassOf", "EquivalentClasses", "DisjointClasses"}
        property_names = {"SubPropertyOf", "EquivalentProperties"}
        while not self.at(")"):
            if name in class_names:
                values.append(self.description())
            elif name in property_names:
                values.append(self.property_iri())
            else:
                values.append(self.iri())
        # Appendix A explicitly permits one description in EquivalentClasses;
        # that case is a tautology. Other n-ary axioms require two arguments.
        minimum = 1 if name == "EquivalentClasses" else 2
        if len(values) < minimum:
            self.fail(f"{name} requires at least {minimum} argument(s)")
        if name in {"SubClassOf", "SubPropertyOf"} and len(values) != 2:
            self.fail(f"{name} requires exactly two arguments")
        self.expect(")")
        predicate = {
            "SubClassOf": RDFS.subClassOf, "EquivalentClasses": OWL.equivalentClass,
            "DisjointClasses": OWL.disjointWith, "SubPropertyOf": RDFS.subPropertyOf,
            "EquivalentProperties": OWL.equivalentProperty,
            "SameIndividual": OWL.sameAs, "DifferentIndividuals": OWL.differentFrom,
        }[name]
        pairs = (combinations(values, 2) if name in {"DisjointClasses", "DifferentIndividuals"}
                 else ((values[0], value) for value in values[1:]))
        for left, right in pairs:
            self.graph.add((left, predicate, right))
            if name in property_names:
                self.property_links.append((left, right, self.current))

    def declaration(self, name):
        self.begin(name)
        token, node = self.current, self.iri()
        if name == "Datatype":
            self.deprecated(node, RDFS.Datatype)
        else:
            # OntologyProperty is metadata in the old abstract syntax, too.
            self.annotation_property(node, token)
            self.graph.add((node, RDF.type, OWL.AnnotationProperty))
        self.annotations(node)
        self.expect(")")

    def parse(self):
        while self.at("Namespace"):
            self.begin("Namespace")
            prefix = self.take()
            if prefix.kind != "WORD" or not prefix.value or not all(
                    c.isalpha() for c in prefix.value):
                self.fail("Namespace prefix must consist of Unicode letters", prefix)
            self.expect("=")
            if self.current.kind != "IRI":
                self.fail("Namespace requires an <absolute-IRI>")
            iri = str(self.iri())
            if (prefix.value in self.explicit_namespaces
                    and self.explicit_namespaces[prefix.value] != iri):
                self.fail(f"Namespace prefix {prefix.value!r} is already declared", prefix)
            self.explicit_namespaces[prefix.value] = iri
            self.namespaces[prefix.value] = iri
            self.expect(")")
        for prefix, iri in self.namespaces.items():
            self.graph.bind(prefix, iri, replace=True)
        self.begin("Ontology")
        ontology = None
        if self.starts_iri():
            ontology = self.iri()
            self.graph.add((ontology, RDF.type, OWL.Ontology))
        while not self.at(")"):
            name = self.current.value
            if name == "Annotation":
                if ontology is None:
                    ontology = BNode()
                    self.graph.add((ontology, RDF.type, OWL.Ontology))
                self.annotation(ontology, name)
            elif name == "Individual":
                self.individual()
            elif name in {"Class", "EnumeratedClass"}:
                self.class_axiom(name)
            elif name in {"ObjectProperty", "DatatypeProperty"}:
                self.property_axiom(name)
            elif name in {"SubClassOf", "EquivalentClasses", "DisjointClasses", "SubPropertyOf",
                          "EquivalentProperties", "SameIndividual", "DifferentIndividuals"}:
                self.relation_axiom(name)
            elif name in {"Datatype", "AnnotationProperty", "OntologyProperty"}:
                self.declaration(name)
            else:
                self.fail(f"Unknown ontology directive {name!r}")
        self.expect(")")
        if self.current.kind != "EOF":
            self.fail("Unexpected content after Ontology; expected end of input")
        for prop in self.annotation_properties.keys() & self.logical_properties.keys():
            self.fail(f"Property <{prop}> is used both as annotation and logical property",
                      self.logical_properties[prop])
        self.validate_property_kinds()
        return self.graph

    def validate_property_kinds(self):
        """Check explicit property kinds, including declarations after their uses.

        Undeclared property identifiers remain generic RDF predicates. This is
        not a complete OWL DL vocabulary/type checker.
        """
        for prop, value, token in self.property_values:
            kind = self.property_kinds.get(prop)
            if kind and ((kind[0] == "DatatypeProperty") != isinstance(value, Literal)):
                expected = "a literal" if kind[0] == "DatatypeProperty" else "an individual"
                self.fail(f"{kind[0]} <{prop}> requires {expected} value", token)
        for prop, token in self.object_property_uses:
            kind = self.property_kinds.get(prop)
            if kind and kind[0] == "DatatypeProperty":
                self.fail(f"{token.value} requires an object property, found "
                          f"DatatypeProperty <{prop}>", token)
        for left, right, token in self.property_links:
            left_kind, right_kind = self.property_kinds.get(left), self.property_kinds.get(right)
            if left_kind and right_kind and left_kind[0] != right_kind[0]:
                self.fail("Property relations cannot mix ObjectProperty and DatatypeProperty", token)
        for prop, name, value, token in self.property_restrictions:
            kind = self.property_kinds.get(prop)
            if kind and kind[0] == "DatatypeProperty":
                if name in {"someValuesFrom", "allValuesFrom"}:
                    self.fail("Datatype range reasoning is unsupported; literal facts and "
                              "has-value restrictions are allowed", token)
                if name in {"minCardinality", "cardinality"} and int(value) > 0:
                    self.fail("Datatype restrictions cannot create literal witnesses; "
                              "positive datatype minimum cardinality is unsupported", token)


def parse_dlp(text: str, *, source: str = "<string>") -> Graph:
    """Build an RDFLib graph from one concrete DLP ontology without fetching IRIs.

    ``source`` labels diagnostics; it is never opened. Syntax errors raise
    :class:`DLPParseError`. Pass the result to ``compile_graph`` or ``Reasoner``
    to validate the desired profile and materialize consequences.
    """
    if not isinstance(text, str):
        raise TypeError("DLP source text must be a string")
    parser = _Parser(text, source)
    try:
        return parser.parse()
    except RecursionError as exc:
        token = parser.current
        raise DLPParseError("Class/individual nesting exceeds Python's safe recursion depth; "
                            "introduce named intermediate classes", source=source,
                            line=token.line, column=token.column) from exc
