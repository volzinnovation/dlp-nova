"""Indexed Horn materialization, equality congruence, and DRed maintenance.

The engine deliberately implements positive Horn rules.  ``NEQ`` is an explicit
difference relation (plus known datatype differences), never a unique-name test.
Facts are stored modulo equality; use :meth:`normalize` when looking them up.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
import math
from time import perf_counter
from typing import Iterable

from rdflib import BNode, Literal, URIRef
from rdflib.namespace import RDF, XSD

from .model import Atom, EQ, NEQ, TOP, ProfileError, Program, Rule, Skolem, Var


class _DomainSeed(BNode):
    """A private term type prevents collision with an input blank-node label."""


_SEED = _DomainSeed("dlp-internal-nonempty-domain")
_MISSING = object()
_DECIMAL_DATATYPES = frozenset({
    XSD.decimal, XSD.integer, XSD.nonNegativeInteger, XSD.nonPositiveInteger,
    XSD.positiveInteger, XSD.negativeInteger, XSD.long, XSD.int, XSD.short,
    XSD.byte, XSD.unsignedLong, XSD.unsignedInt, XSD.unsignedShort, XSD.unsignedByte,
})


def _variables(term):
    if isinstance(term, Var):
        return {term}
    if isinstance(term, Skolem):
        return set().union(*(_variables(t) for t in term.args)) if term.args else set()
    return set()


def _constants(term):
    if isinstance(term, Var):
        return set()
    if isinstance(term, Skolem):
        result = set().union(*(_constants(t) for t in term.args)) if term.args else set()
        if not _variables(term):
            result.add(term)
        return result
    return {term}


def _depth(term):
    return 1 + max((_depth(t) for t in term.args), default=0) if isinstance(term, Skolem) else 0


def _literal_key(term):
    """Value identity for an explicit, conservative datatype whitelist.

    Python value types do not identify OWL datatype value spaces: anyURI/string,
    float/double/decimal, and hexBinary/base64Binary must not be conflated.
    Unhandled datatypes remain opaque RDF terms.
    """
    if (not isinstance(term, Literal) or term.value is None
            or term.ill_typed is True):
        return None
    value = term.value
    datatype = term.datatype
    if term.language and datatype in {None, RDF.langString} and isinstance(value, str):
        return "lang", term.language.lower(), value
    if datatype in {None, XSD.string} and isinstance(value, str):
        return "string", value
    if datatype == XSD.boolean and isinstance(value, bool):
        return "boolean", value
    if (datatype in _DECIMAL_DATATYPES and isinstance(value, (int, Decimal))
            and not isinstance(value, bool)):
        if isinstance(value, Decimal) and not value.is_finite():
            return None
        return "number", value
    return None


def _distinct_literals(left, right):
    a, b = _literal_key(left), _literal_key(right)
    return a is not None and b is not None and a != b


class _Index:
    """Hash membership for bound tuples; column indexes for partial searches."""

    def __init__(self, facts=()):
        self.rows = defaultdict(set)
        self.columns = defaultdict(lambda: defaultdict(set))
        for fact in facts:
            self.add(fact)

    def add(self, fact):
        rows = self.rows[fact.predicate]
        if fact.args in rows:
            return
        rows.add(fact.args)
        for position, value in enumerate(fact.args):
            self.columns[fact.predicate, position][value].add(fact.args)

    def lookup(self, predicate, values):
        result = self.rows.get(predicate, ())
        if all(value is not _MISSING for value in values):
            # A bound atom is a membership probe, not a scan of the smallest
            # single-column bucket. This also covers zero-arity predicates.
            return (values,) if values in result else ()
        for position, value in enumerate(values):
            if value is _MISSING:
                continue
            column = self.columns.get((predicate, position))
            bucket = column.get(value, ()) if column is not None else ()
            if len(bucket) < len(result):
                result = bucket
        return result


class Engine:
    """A bounded least-fixed-point evaluator for a :class:`Program`.

    ``semi-naive`` only fires rule variants containing a fact from the last
    delta. ``naive`` independently scans every rule on each round, providing a
    useful correctness oracle.  Resource exhaustion leaves ``complete=False``
    and the partial materialization available for diagnosis.
    """

    def __init__(self, program: Program, strategy="semi-naive", max_rounds=1000,
                 max_facts=1_000_000, max_depth=32):
        if strategy not in {"semi-naive", "naive"}:
            raise ValueError("strategy must be 'semi-naive' or 'naive'")
        if max_rounds < 1 or max_facts < 1 or max_depth < 0:
            raise ValueError("max_rounds/max_facts must be positive; max_depth must be nonnegative")
        self.program = Program(list(program.rules), set(program.facts),
                               program.profile, list(program.warnings))
        self.rules = list(dict.fromkeys(program.rules))
        self.asserted = set(program.facts)
        self.strategy = strategy
        self.max_rounds = max_rounds
        self.max_facts = max_facts
        self.max_depth = max_depth
        self.facts: set[Atom] = set()
        self.terms: set = set()
        self.complete = False
        self.violations: list[str] = []
        self.stats: dict = {}
        self._parent = {}
        self._skolem_lookup = {}
        self._equivalence_cache = None
        self._validate(self.rules, self.asserted)
        self._prepare_rules()
        self._materialized = False

    def _validate(self, rules, facts):
        arities = {EQ: 2, NEQ: 2, TOP: 1}

        def atom_check(atom, ground=False):
            if not isinstance(atom, Atom) or not isinstance(atom.args, tuple):
                raise ProfileError("Atoms must have an immutable tuple of arguments")
            if isinstance(atom.predicate, (Var, Skolem)):
                raise ProfileError("Variable/function predicates are not supported")
            if atom.predicate in arities and arities[atom.predicate] != len(atom.args):
                raise ProfileError(f"Inconsistent arity for predicate {atom.predicate}")
            arities[atom.predicate] = len(atom.args)
            try:
                hash(atom)
            except TypeError as exc:
                raise ProfileError("Rule terms must be hashable") from exc
            if ground and any(_variables(t) for t in atom.args):
                raise ProfileError("Assertions must be ground")

        for fact in facts:
            atom_check(fact, ground=True)
        for rule in rules:
            if not isinstance(rule, Rule):
                raise ProfileError("Expected a Rule")
            bound = set()
            equalities = []
            needed = set()
            for atom in rule.body:
                atom_check(atom)
                variables = set().union(*(_variables(t) for t in atom.args)) if atom.args else set()
                if any(isinstance(t, Skolem) and _variables(t) for t in atom.args):
                    raise ProfileError("Nonground Skolem patterns in rule bodies are unsupported")
                if atom.predicate == EQ:
                    equalities.append(atom)
                elif atom.predicate == NEQ:
                    needed.update(variables)
                else:
                    bound.update(variables)
            changed = True
            while changed:
                changed = False
                for atom in equalities:
                    left, right = (_variables(t) for t in atom.args)
                    if left <= bound and not right <= bound:
                        bound.update(right)
                        changed = True
                    if right <= bound and not left <= bound:
                        bound.update(left)
                        changed = True
            for atom in equalities:
                needed.update(*(_variables(t) for t in atom.args))
            if rule.head is not None:
                atom_check(rule.head)
                needed.update(*(_variables(t) for t in rule.head.args))
            if not needed <= bound:
                names = ", ".join(sorted(v.name for v in needed - bound))
                raise ProfileError(f"Unsafe rule has unbound variables: {names}")

    def _prepare_rules(self):
        self._dependents, self._global_rules = self._rule_dependencies(self.rules)
        self._unary_plans = {}
        for rule in self.rules:
            if not rule.body:
                continue
            first = rule.body[0]
            if len(first.args) != 1 or not isinstance(first.args[0], Var):
                continue
            variable = first.args[0]
            if all(atom.args == (variable,) and atom.predicate not in {EQ, NEQ}
                   for atom in rule.body):
                self._unary_plans[rule] = (
                    variable, tuple(dict.fromkeys(atom.predicate for atom in rule.body)))

    @staticmethod
    def _rule_dependencies(rules):
        dependents = defaultdict(list)
        global_rules = []
        for number, rule in enumerate(rules):
            relational = False
            for position, atom in enumerate(rule.body):
                if atom.predicate != EQ:
                    dependents[atom.predicate].append((number, position))
                    relational = True
            if not relational:
                global_rules.append(number)
        return dependents, global_rules

    def _start_stats(self, operation, method):
        self.stats = {"strategy": self.strategy, "operation": operation,
                      "update_method": method, "rounds": 0, "rule_evaluations": 0,
                      "candidate_rows": 0, "body_matches": 0, "derived_facts": 0,
                      "unary_plan_evaluations": 0, "unary_intersections": 0,
                      "coalesced_delta_variants": 0,
                      "equality_merges": 0, "overdeleted_facts": 0, "rederived_facts": 0}
        self._started = perf_counter()

    def _finish_stats(self):
        self.stats["seconds"] = perf_counter() - self._started
        self.stats["materialized_facts"] = len(self.facts)
        self.stats["asserted_facts"] = len(self.asserted)
        self.stats["terms"] = len(self.terms)
        self.stats["complete"] = self.complete
        self.stats["consistent"] = False if self.violations else (True if self.complete else None)
        self.program.facts = set(self.asserted)
        self.program.rules = list(self.rules)

    def _stop(self, reason):
        self.complete = False
        self.stats.setdefault("limit_reason", reason)

    def _violation(self, message):
        if message not in self._violation_keys:
            self._violation_keys.add(message)
            self.violations.append(message)

    def _find(self, term):
        parent = self._parent
        if term not in parent:
            return term
        root = term
        while parent[root] != root:
            root = parent[root]
        while parent[term] != term:
            next_term = parent[term]
            parent[term] = root
            term = next_term
        return root

    def normalize(self, term):
        """Return the equality representative, also normalizing function arguments."""
        root = self._find(term)
        if isinstance(root, Skolem):
            signature = Skolem(root.symbol, tuple(self.normalize(t) for t in root.args))
            representative = self._skolem_lookup.get(signature, signature)
            representative = self._find(representative)
            if representative != root and not isinstance(representative, Skolem):
                return self.normalize(representative)
            # A lookup may point to a lexically old function term. Its signature
            # is the canonical spelling even when that spelling was never asserted.
            if isinstance(representative, Skolem):
                return Skolem(representative.symbol,
                              tuple(self.normalize(t) for t in representative.args))
            return representative
        return root

    def equivalents(self, term):
        representative = self.normalize(term)
        if not getattr(self, "_ever_merged", False):
            return {representative}
        if self._equivalence_cache is None:
            classes = defaultdict(set)
            for original in self.terms:
                classes[self.normalize(original)].add(original)
            self._equivalence_cache = classes
        return self._equivalence_cache.get(representative, set()) | {representative}

    def _order(self, term):
        # Prefer a named individual over a witness and a shallower function over
        # a deeper one. This also prevents cyclic canonical function spellings.
        category = (0 if isinstance(term, URIRef) else 1 if isinstance(term, Literal)
                    else 3 if isinstance(term, Skolem) else 2)
        return category, _depth(term), type(term).__name__, repr(term)

    def _union(self, left, right):
        a, b = self._find(left), self._find(right)
        if a == b:
            return False
        for first in self._class_literals.get(a, ()):
            for second in self._class_literals.get(b, ()):
                if _distinct_literals(first, second):
                    self._violation(f"Equality identifies distinct datatype values: {first.n3()} and {second.n3()}")
        if self._order(a) > self._order(b):
            a, b = b, a
        self._parent[b] = a
        self._equivalence_cache = None
        self._parent.setdefault(a, a)
        self._class_literals.setdefault(a, set()).update(self._class_literals.pop(b, ()))
        self.stats["equality_merges"] += 1
        self._ever_merged = True
        self._equality_dirty = True
        return True

    def _register(self, term, new_terms):
        if term in self.terms:
            return True
        if isinstance(term, Skolem):
            if _depth(term) > self.max_depth:
                self._stop(f"max_depth={self.max_depth} exceeded by an existential witness")
                return False
            for arg in term.args:
                if not self._register(arg, new_terms):
                    return False
        self.terms.add(term)
        self._equivalence_cache = None
        new_terms.add(term)
        self._parent.setdefault(term, term)
        if isinstance(term, Literal):
            self._class_literals.setdefault(self._find(term), set()).add(term)
            key = _literal_key(term)
            if key is not None:
                previous = self._literal_representatives.setdefault(key, term)
                if previous != term:
                    self._union(term, previous)
        if isinstance(term, Skolem):
            self._skolems.add(term)
            signature = Skolem(term.symbol, tuple(self.normalize(t) for t in term.args))
            previous = self._skolem_lookup.setdefault(signature, term)
            if self._find(previous) != self._find(term):
                self._union(previous, term)
        return True

    def _congruence(self):
        changed = True
        while changed:
            changed = False
            signatures = {}
            for term in self._skolems:
                signature = Skolem(term.symbol, tuple(self.normalize(t) for t in term.args))
                if signature in signatures:
                    changed |= self._union(signatures[signature], term)
                else:
                    signatures[signature] = self._find(term)
            self._skolem_lookup = signatures

    def _canonical(self, atom):
        return Atom(atom.predicate, tuple(self.normalize(t) for t in atom.args))

    def _store(self, fact, delta):
        if fact in self.facts:
            return
        if len(self.facts) >= self.max_facts:
            self._stop(f"max_facts={self.max_facts} exceeded")
            return
        self.facts.add(fact)
        self._index.add(fact)
        delta.add(fact)

    def _reindex(self):
        self._congruence()
        self.facts = {self._canonical(fact) for fact in self.facts}
        self._index = _Index(self.facts)
        self._equality_dirty = False

    def _ingest(self, atoms):
        delta = set()
        for atom in atoms:
            if not self.complete:
                break
            new_terms = set()
            if not all(self._register(t, new_terms) for t in atom.args):
                break
            if atom.predicate == EQ:
                self._union(*atom.args)
            fact = self._canonical(atom)
            self._store(fact, delta)
            if atom.predicate == NEQ:
                self._store(Atom(NEQ, tuple(reversed(fact.args))), delta)
            for term in new_terms:
                self._store(Atom(TOP, (self.normalize(term),)), delta)
        if self._equality_dirty:
            self._reindex()
            # Equality can enable old joins without adding a relational fact.
            delta = set(self.facts)
        self._check_differences()
        return delta

    def _check_differences(self):
        for left, right in self._index.rows.get(NEQ, ()):
            if self.normalize(left) == self.normalize(right):
                self._violation(f"An individual is both equal to and different from itself: {left!r}")

    def _domain_constants(self):
        terms = {_SEED}
        for atom in self.asserted:
            for term in atom.args:
                terms.update(_constants(term))
        for rule in self.rules:
            for atom in (*rule.body, *((rule.head,) if rule.head is not None else ())):
                for term in atom.args:
                    terms.update(_constants(term))
        return terms

    def _bound(self, term, binding):
        if isinstance(term, Var):
            return binding.get(term, _MISSING)
        if isinstance(term, Skolem):
            args = tuple(self._bound(t, binding) for t in term.args)
            if any(t is _MISSING for t in args):
                return _MISSING
            return self.normalize(Skolem(term.symbol, args))
        return self.normalize(term)

    def _solutions(self, rule, delta_index=None, delta_position=None, initial=None):
        self.stats["rule_evaluations"] += 1
        plan = self._unary_plans.get(rule) if self.strategy == "semi-naive" else None
        if plan is not None:
            yield from self._unary_solutions(rule, plan, delta_index, delta_position, initial)
            return

        def visit(remaining, binding):
            if not remaining:
                self.stats["body_matches"] += 1
                yield binding
                return
            chosen = None
            best_size = math.inf
            for position in remaining:
                atom = rule.body[position]
                values = tuple(self._bound(t, binding) for t in atom.args)
                if atom.predicate == EQ:
                    if all(v is _MISSING for v in values):
                        continue
                    size, rows = 1, None
                elif atom.predicate == NEQ:
                    # NEQ is a range-restricted built-in; its variables have to
                    # be bound by relational atoms before checking difference.
                    if any(v is _MISSING for v in values):
                        continue
                    relation = delta_index if position == delta_position else self._index
                    explicit = tuple(values) in relation.rows.get(NEQ, ())
                    known = delta_position != position and _distinct_literals(*values)
                    size, rows = int(explicit or known), None
                else:
                    relation = delta_index if position == delta_position else self._index
                    rows = relation.lookup(atom.predicate, values)
                    size = len(rows)
                if size < best_size:
                    chosen = position, atom, values, rows
                    best_size = size
                    if size == 0:
                        return
            if chosen is None:
                raise ProfileError("Rule evaluation found an unbound equality/difference")
            position, atom, values, rows = chosen
            rest = tuple(p for p in remaining if p != position)
            if atom.predicate == EQ:
                left, right = values
                extended = binding
                if left is _MISSING:
                    extended = {**binding, atom.args[0]: right}
                elif right is _MISSING:
                    extended = {**binding, atom.args[1]: left}
                elif left != right:
                    return
                yield from visit(rest, extended)
            elif atom.predicate == NEQ:
                yield from visit(rest, binding)
            else:
                for row in rows:
                    self.stats["candidate_rows"] += 1
                    extended = binding.copy()
                    matched = True
                    for pattern, actual, expected in zip(atom.args, row, values):
                        if isinstance(pattern, Var):
                            if pattern in extended and extended[pattern] != actual:
                                matched = False
                                break
                            extended[pattern] = actual
                        elif expected != actual:
                            matched = False
                            break
                    if matched:
                        yield from visit(rest, extended)

        yield from visit(tuple(range(len(rule.body))), {} if initial is None else initial)

    def _unary_solutions(self, rule, plan, delta_index, delta_position, initial):
        """Intersect unary relations sharing one variable, without nested joins.

        For an individual delta variant, its relation replaces the full relation.
        The coalesced form (delta index but no position) requires membership in
        at least one participating delta. Set distributivity makes it identical
        to the union of the individual variants, with each binding yielded once.
        Constants, multiple variables, equality and inequality keep the generic
        solver. Plans contain no data, so equality reindexing cannot stale them.
        """
        self.stats["unary_plan_evaluations"] += 1
        variable, predicates = plan
        delta_predicate = (rule.body[delta_position].predicate
                           if delta_position is not None else None)
        rows = [(delta_index if delta_position is not None and predicate == delta_predicate
                 else self._index).rows.get(
                    predicate, ()) for predicate in predicates]
        if any(not relation for relation in rows):
            return
        if delta_index is not None and delta_position is None:
            changed = set()
            for predicate in predicates:
                changed.update(delta_index.rows.get(predicate, ()))
            if not changed:
                return
            rows.append(changed)
        binding = {} if initial is None else initial
        if variable in binding:
            rows.append({(binding[variable],)})
        rows.sort(key=len)
        if len(rows) == 1:
            matches = rows[0]
        else:
            matches = set(rows[0])
            for relation in rows[1:]:
                self.stats["unary_intersections"] += 1
                matches.intersection_update(relation)
                if not matches:
                    return
        for (value,) in matches:
            self.stats["candidate_rows"] += 1
            self.stats["body_matches"] += 1
            yield {**binding, variable: value}

    def _heads(self, rule, delta_index=None, delta_position=None):
        for binding in self._solutions(rule, delta_index, delta_position):
            if rule.head is None:
                label = rule.label or "constraint"
                details = ", ".join(f"{var.name}={value!r}" for var, value in
                                    sorted(binding.items(), key=lambda item: item[0].name))
                self._violation(f"{label} violated" + (f": {details}" if details else ""))
            else:
                yield Atom(rule.head.predicate, tuple(self._bound(t, binding) for t in rule.head.args))

    def _variants(self, delta, include_globals=True):
        predicates = {atom.predicate for atom in delta}
        coalesced = set()
        for predicate in predicates:
            for number, position in self._dependents.get(predicate, ()):
                rule = self.rules[number]
                if self.strategy == "semi-naive" and len(rule.body) > 1 and rule in self._unary_plans:
                    if number in coalesced:
                        self.stats["coalesced_delta_variants"] += 1
                        continue
                    coalesced.add(number)
                    yield number, None
                else:
                    yield number, position
        if include_globals:
            for number in self._global_rules:
                yield number, None

    def _run(self, delta, force=False):
        first = True
        while self.complete and (delta or (first and force)):
            if self.stats["rounds"] >= self.max_rounds:
                self._stop(f"max_rounds={self.max_rounds} exceeded before a fixed point")
                return
            self.stats["rounds"] += 1
            pending = set()
            if self.strategy == "naive":
                variants = ((i, None) for i in range(len(self.rules)))
                delta_index = None
            else:
                variants = self._variants(delta, include_globals=True)
                delta_index = _Index(delta)
            for number, position in variants:
                for head in self._heads(self.rules[number], delta_index, position):
                    if head not in self.facts:
                        pending.add(head)
                    if len(pending) + len(self.facts) > self.max_facts:
                        # Ingest the bounded prefix so all successful partial
                        # derivations remain inspectable after resource failure.
                        break
                if len(pending) + len(self.facts) > self.max_facts:
                    break
            previous = len(self.facts)
            delta = self._ingest(pending)
            self.stats["derived_facts"] += max(0, len(self.facts) - previous)
            if len(pending) + previous > self.max_facts and self.complete:
                self._stop(f"max_facts={self.max_facts} exceeded by a candidate batch")
            first = False

    def materialize(self):
        self._start_stats("materialize", "full")
        self.complete = True
        self.facts = set()
        self.terms = set()
        self.violations = []
        self._violation_keys = set()
        self._parent = {}
        self._skolems = set()
        self._skolem_lookup = {}
        self._equivalence_cache = None
        self._class_literals = {}
        self._literal_representatives = {}
        self._index = _Index()
        self._equality_dirty = False
        self._ever_merged = False
        delta = self._ingest(Atom(TOP, (term,)) for term in self._domain_constants())
        delta.update(self._ingest(self.asserted))
        if self._ever_merged:
            delta = set(self.facts)
        self._run(delta, force=True)
        self._materialized = True
        self._finish_stats()
        return self

    def _can_dred(self, rules=None, facts=None):
        if not self.complete or self._ever_merged:
            return False
        rules = self.rules if rules is None else rules
        facts = self.asserted if facts is None else facts
        literals = {}

        def eligible(atom):
            if atom.predicate == EQ:
                return False
            for term in atom.args:
                if isinstance(term, Skolem):
                    return False
                key = _literal_key(term)
                if key is not None and literals.setdefault(key, term) != term:
                    # Even without an EQ atom, datatype value identity can merge
                    # representatives. Deletion would then require splitting them.
                    return False
            return True

        if not all(eligible(atom) for atom in facts):
            return False
        for rule in rules:
            if not all(eligible(atom) for atom in
                       (*rule.body, *((rule.head,) if rule.head is not None else ()))):
                return False
        return True

    def _derive_once(self, rules):
        """Seed changed rules, bounding candidate storage as in regular evaluation."""
        pending = set()
        for rule in rules:
            for head in self._heads(rule):
                if head not in self.facts:
                    pending.add(head)
                if len(pending) + len(self.facts) > self.max_facts:
                    break
            if len(pending) + len(self.facts) > self.max_facts:
                break
        previous = len(self.facts)
        delta = self._ingest(pending)
        self.stats["derived_facts"] += max(0, len(self.facts) - previous)
        return delta

    def _dred(self, removed, additions, previous_rules):
        """Overdelete under old rules, then rederive exclusively under new rules.

        A lost proof contains either a removed assertion, a removed rule, or a
        constant that has left the active domain. Seed these losses in the old
        closure and follow the OLD dependency graph to remove their consequences.
        Assertions in the new database remain independent support. Every surviving
        fact is therefore valid under the new program. Starting with these facts,
        new assertions, and new domain facts, NEW rules recover alternative proofs
        and propagate insertions. An unsupported recursive cycle has no seed.
        """
        previous_set, next_set = set(previous_rules), set(self.rules)
        removed_rules = previous_set - next_set
        inserted_rules = next_set - previous_set
        old_dependents, _ = self._rule_dependencies(previous_rules)
        protected = {self._canonical(atom) for atom in self.asserted}
        protected.update(Atom(NEQ, tuple(reversed(atom.args))) for atom in list(protected)
                         if atom.predicate == NEQ)
        domain = self._domain_constants()
        protected.update(Atom(TOP, (self.normalize(term),)) for term in domain)
        deleted = {self._canonical(atom) for atom in removed} - protected
        deleted.update(Atom(NEQ, tuple(reversed(atom.args))) for atom in removed
                       if atom.predicate == NEQ and
                       Atom(NEQ, tuple(reversed(atom.args))) not in protected)
        for rule in removed_rules:
            if rule.head is not None:
                deleted.update(self._heads(rule))
        deleted.update(Atom(NEQ, tuple(reversed(atom.args))) for atom in list(deleted)
                       if atom.predicate == NEQ)
        deleted.update(atom for atom in self.facts if atom.predicate == TOP and atom not in protected)
        deleted.intersection_update(self.facts)
        # A rule may be deleted while its head remains explicitly asserted.
        # Such an assertion still supports its descendants independently.
        deleted.difference_update(protected)
        frontier = set(deleted)
        while frontier and self.complete:
            if self.stats["rounds"] >= self.max_rounds:
                self._stop(f"max_rounds={self.max_rounds} exceeded during DRed overdeletion")
                return False
            self.stats["rounds"] += 1
            delta_index = _Index(frontier)
            following = set()
            variants = (variant for predicate in {atom.predicate for atom in frontier}
                        for variant in old_dependents.get(predicate, ()))
            for number, position in variants:
                rule = previous_rules[number]
                if rule.head is None:
                    continue
                for head in self._heads(rule, delta_index, position):
                    if head in self.facts and head not in protected and head not in deleted:
                        following.add(head)
                        if head.predicate == NEQ:
                            reverse = Atom(NEQ, tuple(reversed(head.args)))
                            if reverse not in protected and reverse not in deleted:
                                following.add(reverse)
            deleted.update(following)
            frontier = following
        self.stats["overdeleted_facts"] = len(deleted)
        self.facts.difference_update(deleted)
        self._index = _Index(self.facts)
        self.terms.intersection_update(domain)
        # DRed eligibility guarantees identity representatives. Purge departed
        # terms from all identity caches so a later literal cannot merge with a
        # removed lexical form that is no longer in the active domain.
        self._parent = {term: term for term in self.terms}
        self._class_literals = {term: {term} for term in self.terms if isinstance(term, Literal)}
        self._literal_representatives = {
            _literal_key(term): term for term in self.terms if _literal_key(term) is not None
        }
        self._equivalence_cache = None
        self.violations = []
        self._violation_keys = set()
        # New constants can occur only in a rule, without any inserted assertion.
        delta = self._ingest(Atom(TOP, (term,)) for term in domain - self.terms)
        delta.update(self._ingest(additions))
        # Evaluate all remaining definitions of overdeleted predicates and each
        # inserted rule once. Further derivations are propagated by deltas.
        # No deleted rule participates in this phase, including its rederivations.
        predicates = {atom.predicate for atom in deleted}
        boundary_rules = [rule for rule in self.rules if rule in inserted_rules
                          or (rule.head is not None and rule.head.predicate in predicates)]
        if self.complete:
            delta.update(self._derive_once(boundary_rules))
        self._run(delta)
        self.stats["rederived_facts"] = len(deleted & self.facts)
        self._check_differences()
        if self.complete:
            for rule in self.rules:
                if rule.head is None:
                    list(self._heads(rule))
        return True

    def update(self, add: Iterable[Atom] = (), remove: Iterable[Atom] = (), *,
               add_rules: Iterable[Rule] = (), remove_rules: Iterable[Rule] = ()):
        """Validate and apply one fact/rule transaction; additions win overlap.

        Retractions use DRed only when both programs are equality-free and
        function-free and the previous closure is complete. Otherwise rebuilding
        safely handles equality splitting, witnesses, and incomplete old results.
        """
        additions, removals = set(add), set(remove)
        next_asserted = (self.asserted - removals) | additions
        rule_additions, rule_removals = list(add_rules), set(remove_rules)
        next_rules = list(dict.fromkeys(
            [rule for rule in self.rules if rule not in rule_removals] + rule_additions))
        self._validate(next_rules, next_asserted)
        actual_removed = self.asserted - next_asserted
        actual_added = next_asserted - self.asserted
        previous_rules = self.rules
        previous_set = set(previous_rules)
        deleted = previous_set - set(next_rules)
        inserted = [rule for rule in next_rules if rule not in previous_set]
        rules_changed = bool(deleted or inserted)
        retracting = bool(actual_removed or deleted)
        can_dred = (self._materialized and self._can_dred()
                    and self._can_dred(next_rules, next_asserted)) if retracting else False
        self.asserted = next_asserted
        self.rules = next_rules
        self._prepare_rules()
        if not self._materialized or not self.complete or (retracting and not can_dred):
            self.materialize()
            self.stats["operation"] = "update"
            self.stats["update_method"] = "rematerialize-rules" if rules_changed else "rematerialize"
            return self
        method = ("dred-rules" if rules_changed else "dred") if retracting else (
            "incremental-rules" if rules_changed else "incremental-insert")
        self._start_stats("update", method)
        if retracting:
            if not self._dred(actual_removed, actual_added, previous_rules):
                # An interrupted overdelete may still contain unsupported old
                # facts. Rebuild so even a bounded partial result remains sound.
                self.materialize()
                self.stats["operation"] = "update"
                self.stats["update_method"] = ("rematerialize-rules-after-dred-limit"
                                               if rules_changed else "rematerialize-after-dred-limit")
                return self
        else:
            delta = (self._ingest(Atom(TOP, (term,)) for term in self._domain_constants())
                     if inserted else set())
            delta.update(self._ingest(actual_added))
            if self.complete:
                delta.update(self._derive_once(inserted))
            self._run({self._canonical(atom) for atom in delta})
        self._finish_stats()
        return self

    def update_rules(self, add: Iterable[Rule] = (), remove: Iterable[Rule] = ()):
        """Apply a rule-only transaction through the shared maintenance path."""
        self.update(add_rules=add, remove_rules=remove)
        self.stats["operation"] = "update_rules"
        if self.stats["update_method"] == "incremental-insert":
            self.stats["update_method"] = "incremental-rules"
        elif self.stats["update_method"] == "rematerialize":
            self.stats["update_method"] = "rematerialize-rules"
        return self
