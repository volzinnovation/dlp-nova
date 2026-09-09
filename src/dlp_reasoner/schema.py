"""Sound positive schema shortcuts over a subset of compiled Horn rules.

Indexed class contexts follow the consequence-classification approach used by
ELK (Kazakov, Krotzsch, Simancik, 2011/2014). As with told-subsumption shortcuts
discussed by MORe (Armas Romero et al., 2012), failure to find a proof here says
nothing about non-entailment: the caller must use its complete semantic probe.

We index only variable-preserving unary Horn rules, binary inclusion/inverse
rules, unconditional domains/ranges, and explicit transitivity. No asserted
individuals, equality, nominals, constraints, or Skolem terms are evaluated here.
Every indexed inference is therefore sound even in a richer surrounding DLP
ontology. This is neither a complete EL classifier nor a module extractor.
"""
from collections import OrderedDict, defaultdict, deque

from rdflib import URIRef

from .model import TOP, Var


class SchemaIndex:
    """Lazily reusable schema proofs; stores no copy of the ABox."""

    def __init__(self, rules):
        self.classes = set()
        self.properties = set()
        self._unary_rules = []
        self._unary_dependents = defaultdict(list)
        self._roles = defaultdict(set)
        self._role_types = defaultdict(set)
        self._transitive = set()
        self._class_cache = OrderedDict()
        self._role_cache = OrderedDict()
        unary_rules = set()
        for rule in rules:
            head, body = rule.head, rule.body
            if head is None:
                continue
            if (len(head.args) == 1 and isinstance(head.args[0], Var) and body
                    and all(atom.args == head.args for atom in body)):
                premises = frozenset(atom.predicate for atom in body)
                unary_rules.add((head.predicate, premises))
                self.classes.update(p for p in premises | {head.predicate}
                                    if isinstance(p, URIRef))
            binary = [atom for atom in body if len(atom.args) == 2]
            if not binary or not all(isinstance(atom.predicate, URIRef) for atom in binary):
                continue
            variables = {term for atom in binary for term in atom.args}
            if not all(isinstance(term, Var) for term in variables):
                continue
            # TOP conditions on already bound endpoints add no restriction.
            if any(atom.predicate != TOP or len(atom.args) != 1 or atom.args[0] not in variables
                   for atom in body if atom not in binary):
                continue
            if len(binary) == 1 and len(set(binary[0].args)) == 2:
                premise = binary[0]
                self.properties.add(premise.predicate)
                if len(head.args) == 1 and head.args[0] in premise.args:
                    position = premise.args.index(head.args[0])
                    self._role_types[premise.predicate, position].add(head.predicate)
                    if isinstance(head.predicate, URIRef):
                        self.classes.add(head.predicate)
                elif isinstance(head.predicate, URIRef) and len(head.args) == 2:
                    if head.args == premise.args:
                        reverse = False
                    elif head.args == tuple(reversed(premise.args)):
                        reverse = True
                    else:
                        continue
                    self.properties.add(head.predicate)
                    self._roles[premise.predicate, False].add((head.predicate, reverse))
                    self._roles[premise.predicate, True].add((head.predicate, not reverse))
            elif (len(binary) == 2 and isinstance(head.predicate, URIRef)
                  and len(head.args) == 2 and len(set(head.args)) == 2
                  and all(atom.predicate == head.predicate for atom in binary)):
                start, end = head.args
                middle = variables - {start, end}
                if len(middle) == 1:
                    via = next(iter(middle))
                    if {atom.args for atom in binary} == {(start, via), (via, end)}:
                        self._transitive.add(head.predicate)
                        self.properties.add(head.predicate)
        for head, premises in unary_rules:
            number = len(self._unary_rules)
            self._unary_rules.append((head, len(premises)))
            for predicate in premises:
                self._unary_dependents[predicate].append(number)

    @staticmethod
    def _remember(cache, key, result):
        # Bound retained query contexts rather than computing an all-pairs table.
        cache[key] = frozenset(result)
        cache.move_to_end(key)
        if len(cache) > 128:
            cache.popitem(last=False)
        return cache[key]

    def _class_closure(self, seeds):
        key = frozenset(seeds)
        if key in self._class_cache:
            self._class_cache.move_to_end(key)
            return self._class_cache[key]
        known = set(key) | {TOP}
        pending = deque(known)
        remaining = {}
        while pending:
            predicate = pending.popleft()
            for number in self._unary_dependents.get(predicate, ()):
                head, count = self._unary_rules[number]
                if head in known:
                    continue
                remaining[number] = remaining.get(number, count) - 1
                if remaining[number] == 0:
                    known.add(head)
                    pending.append(head)
        return self._remember(self._class_cache, key, known)

    def _role_closure(self, seed):
        if seed in self._role_cache:
            self._role_cache.move_to_end(seed)
            return self._role_cache[seed]
        known = {seed}
        pending = [seed]
        while pending:
            for following in self._roles.get(pending.pop(), ()):
                if following not in known:
                    known.add(following)
                    pending.append(following)
        return self._remember(self._role_cache, seed, known)

    def proves_subsumption(self, superclass, subclass):
        if (not isinstance(superclass, URIRef) or not isinstance(subclass, URIRef)
                or superclass not in self.classes or subclass not in self.classes):
            return False
        return superclass in self._class_closure((subclass,))

    def proves_property_inclusion(self, superproperty, subproperty, *, inverse=False):
        if (not isinstance(superproperty, URIRef) or not isinstance(subproperty, URIRef)
                or superproperty not in self.properties or subproperty not in self.properties):
            return False
        return (superproperty, inverse) in self._role_closure((subproperty, False))

    def proves_symmetry(self, predicate):
        return self.proves_property_inclusion(predicate, predicate, inverse=True)

    def proves_transitivity(self, predicate):
        if not isinstance(predicate, URIRef) or predicate not in self.properties:
            return False
        origin = (predicate, False)
        for target in self._role_closure(origin):
            if target[0] in self._transitive and origin in self._role_closure(target):
                return True
        return False

    def proves_domain(self, predicate, concept, *, position=0):
        if (not isinstance(predicate, URIRef) or not isinstance(concept, URIRef)
                or predicate not in self.properties or concept not in self.classes):
            return False
        seeds = set()
        for prop, reverse in self._role_closure((predicate, False)):
            seeds.update(self._role_types.get((prop, position ^ reverse), ()))
        return concept in self._class_closure(seeds)
