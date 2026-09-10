"""Parser for the separately versioned DLP query language (version 1)."""
from __future__ import annotations

from dataclasses import dataclass
import json
import re

from rdflib import Literal, URIRef, RDF, RDFS, OWL, XSD

from .model import Var
from .query_ir import (
    Aggregate, Bind, Filter, ProviderScan, QueryLanguageError, QueryProgram, QueryRule,
    RelationAtom, SourceLocation,
)


class QueryParseError(QueryLanguageError):
    """Malformed versioned query syntax, with source location."""


@dataclass(frozen=True)
class _Token:
    kind: str
    value: str
    location: SourceLocation


_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*(?::[A-Za-z_][A-Za-z0-9_.:-]*)?")
_NUMBER = re.compile(r"[+-]?(?:[0-9]+\.[0-9]+|\.[0-9]+|[0-9]+)(?:[eE][+-]?[0-9]+)?")
_VARIABLE = re.compile(r"\?[A-Za-z_][A-Za-z0-9_]*")
_ABSOLUTE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")
_PREDEFINED = {"rdf": str(RDF), "rdfs": str(RDFS), "owl": str(OWL), "xsd": str(XSD)}


def _lex(text, source):
    index, line, column = 0, 1, 1
    tokens = []

    def advance(end):
        nonlocal index, line, column
        part = text[index:end]
        line += part.count("\n")
        column = len(part.rsplit("\n", 1)[-1]) + 1 if "\n" in part else column + len(part)
        index = end

    while index < len(text):
        location = SourceLocation(source, line, column)
        char = text[index]
        if char.isspace():
            advance(index + 1)
            continue
        if char == "#" or text.startswith("//", index):
            end = text.find("\n", index)
            advance(len(text) if end < 0 else end)
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                raise QueryParseError("Unterminated block comment", location)
            advance(end + 2)
            continue
        if text.startswith(":-", index) or text.startswith("^^", index):
            kind, value, end = text[index:index + 2], text[index:index + 2], index + 2
        elif char in "(),.@":
            # A leading . followed by a digit belongs to a numeric literal.
            number = _NUMBER.match(text, index) if char == "." else None
            if number:
                kind, value, end = "NUMBER", number.group(), number.end()
            else:
                kind, value, end = char, char, index + 1
        elif char == "<":
            end = text.find(">", index + 1)
            if end < 0:
                raise QueryParseError("Unterminated IRI", location)
            value = text[index + 1:end]
            if (not _ABSOLUTE.match(value) or any(c.isspace() or ord(c) < 32
                    or c in '<>"{}|^`\\' for c in value)):
                raise QueryParseError("Expected an absolute IRI", location)
            kind, end = "IRI", end + 1
        elif char == '"':
            end = index + 1
            escaped = False
            while end < len(text):
                if text[end] == '"' and not escaped:
                    break
                if ord(text[end]) < 32:
                    raise QueryParseError("Use JSON escapes for control characters in strings", location)
                escaped = text[end] == "\\" and not escaped
                end += 1
            if end >= len(text):
                raise QueryParseError("Unterminated string literal", location)
            try:
                value = json.loads(text[index:end + 1])
                # Avoid unpaired-surrogate strings that cannot be encoded as UTF-8.
                value.encode("utf-8")
            except (ValueError, UnicodeError) as exc:
                raise QueryParseError("Invalid string escape or Unicode scalar", location) from exc
            kind, end = "STRING", end + 1
        elif match := _VARIABLE.match(text, index):
            kind, value, end = "VAR", match.group()[1:], match.end()
        elif match := _NUMBER.match(text, index):
            kind, value, end = "NUMBER", match.group(), match.end()
        elif match := _NAME.match(text, index):
            kind, value, end = "NAME", match.group(), match.end()
            # A declaration has a prefix token followed by ':' without a local.
            if end < len(text) and text[end] == ":" and ":" not in value:
                value, end = value + ":", end + 1
        else:
            raise QueryParseError(f"Unexpected character {char!r}", location)
        tokens.append(_Token(kind, value, location))
        advance(end)
    tokens.append(_Token("EOF", "end of input", SourceLocation(source, line, column)))
    return tokens


class _Parser:
    def __init__(self, text, source):
        self.tokens = _lex(text, source)
        self.index = 0
        self.namespaces = dict(_PREDEFINED)
        self.declared = set()

    @property
    def current(self):
        return self.tokens[self.index]

    def fail(self, message, token=None):
        raise QueryParseError(message, (token or self.current).location)

    def take(self):
        result = self.current
        if result.kind != "EOF":
            self.index += 1
        return result

    def at(self, value):
        return self.current.value == value and self.current.kind in {"NAME", value}

    def expect(self, value):
        if not self.at(value):
            self.fail(f"Expected {value!r}, found {self.current.value!r}")
        return self.take()

    def variable(self):
        if self.current.kind != "VAR":
            self.fail("Expected a variable")
        return Var(self.take().value)

    def name(self, *, unqualified=False):
        token = self.take()
        if token.kind == "IRI":
            return URIRef(token.value)
        if token.kind != "NAME":
            self.fail("Expected a relation/operation IRI", token)
        if ":" in token.value:
            prefix, local = token.value.split(":", 1)
            if not local:
                self.fail("Expected a nonempty prefixed local name", token)
            if prefix not in self.namespaces:
                self.fail(f"Undeclared prefix {prefix!r}", token)
            return URIRef(self.namespaces[prefix] + local)
        if unqualified:
            return URIRef("urn:dlp:query:" + token.value)
        self.fail("Operations and IRI constants require a prefix or <absolute-IRI>", token)

    def term(self):
        token = self.current
        if token.kind == "VAR":
            return self.variable()
        if token.kind == "NUMBER":
            value = self.take().value
            datatype = XSD.double if "e" in value.lower() else XSD.decimal if "." in value else XSD.integer
            return Literal(value, datatype=datatype, normalize=False)
        if token.kind == "STRING":
            value = self.take().value
            datatype, language = None, None
            if self.at("^^"):
                self.take()
                datatype = self.name()
            elif self.at("@"):
                self.take()
                tag = self.take()
                if tag.kind != "NAME" or not re.fullmatch(r"[A-Za-z]+(?:-[A-Za-z0-9]+)*", tag.value):
                    self.fail("Invalid language tag", tag)
                language = tag.value
            return Literal(value, datatype=datatype, lang=language, normalize=False)
        if token.kind == "NAME" and token.value in {"true", "false"}:
            return Literal(self.take().value, datatype=XSD.boolean, normalize=False)
        return self.name()

    def args(self):
        self.expect("(")
        args = []
        if not self.at(")"):
            args.append(self.term())
            while self.at(","):
                self.take()
                args.append(self.term())
        self.expect(")")
        return tuple(args)

    def atom(self):
        location = self.current.location
        return RelationAtom(self.name(unqualified=True), self.args(), location=location)

    def outputs(self):
        if self.at("("):
            self.take()
            outputs = [self.variable()]
            while self.at(","):
                self.take()
                outputs.append(self.variable())
            self.expect(")")
            return tuple(outputs)
        return (self.variable(),)

    def body_node(self):
        token = self.current
        if self.at("MIN"):
            self.take()
            value = self.variable()
            self.expect("GROUP_BY")
            if self.at("("):
                self.take()
                groups = []
                if not self.at(")"):
                    groups.append(self.variable())
                    while self.at(","):
                        self.take()
                        groups.append(self.variable())
                self.expect(")")
            else:
                groups = [self.variable()]
                while self.at(","):
                    self.take()
                    groups.append(self.variable())
            self.expect("FROM")
            relation = self.atom()
            self.expect("AS")
            return Aggregate(relation, tuple(groups), value, self.variable(), location=token.location)
        if self.at("filter") or self.at("bind") or self.at("scan"):
            keyword = self.take().value
            operation = self.name()
            args = self.args()
            if keyword == "filter":
                return Filter(operation, args, location=token.location)
            self.expect("as")
            if keyword == "bind":
                return Bind(operation, args, self.term(), location=token.location)
            return ProviderScan(operation, args, self.outputs(), location=token.location)
        return self.atom()

    def rule(self):
        location = self.current.location
        if self.at("query"):
            self.take()
        head = self.atom()
        given = ()
        if self.at("given"):
            self.take()
            self.expect("(")
            params = []
            if not self.at(")"):
                params.append(self.variable())
                while self.at(","):
                    self.take()
                    params.append(self.variable())
            self.expect(")")
            if len(set(params)) != len(params):
                self.fail("given parameters must be distinct")
            given = tuple(params)
        self.expect(":-")
        body = [self.body_node()]
        while self.at(","):
            self.take()
            body.append(self.body_node())
        self.expect(".")
        return QueryRule(head, tuple(body), str(head.predicate), given, location=location)

    def parse(self):
        self.expect("version")
        version = self.take()
        if version.kind != "NUMBER" or version.value != "1":
            self.fail("Only query language version 1 is supported", version)
        if self.at("."):
            self.take()
        while self.at("prefix"):
            self.take()
            token = self.take()
            if token.kind != "NAME" or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*:", token.value):
                self.fail("Expected prefix name ending in ':'", token)
            prefix = token.value[:-1]
            if prefix in self.declared:
                self.fail(f"Duplicate prefix {prefix!r}", token)
            if self.current.kind != "IRI":
                self.fail("Prefix namespace must be an absolute <IRI>")
            namespace = self.take().value
            if prefix in _PREDEFINED and namespace != _PREDEFINED[prefix]:
                self.fail(f"Cannot redefine predefined prefix {prefix!r}", token)
            self.namespaces[prefix] = namespace
            self.declared.add(prefix)
            if self.at("."):
                self.take()
        rules = []
        while self.current.kind != "EOF":
            rules.append(self.rule())
        return QueryProgram(tuple(rules), self.namespaces, version=1)


def parse_query_program(text: str, *, source: str = "<string>") -> QueryProgram:
    """Parse explicitly versioned query syntax without invoking any provider."""
    return _Parser(text, source).parse()
