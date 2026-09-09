"""Bounded positive support certificates for one deletion transaction.

The oracle reasons only with current assertions, current domain membership, and
current variable-preserving unary Horn rules. It never accepts an old derived
fact as a proof premise. Thus an unsupported recursive cycle cannot certify
itself, even when a transaction changes facts and rules simultaneously.

This is a specialized proof filter inspired by DRed/B/F support checking and
modular materialisation; it is not an implementation of DRedc or B/Fc. Sharing
closure computations between equal subject type signatures avoids storing a
derivation counter for every materialized fact. A negative answer means that
no certificate was found, so the caller must retain its general DRed path.
"""
from collections import defaultdict, deque

from .model import TOP, Skolem, Var


class UnarySupport:
    """Search for sound current proofs; inputs must stay fixed during use.

    ``rules`` and ``asserted`` must describe the candidate transaction state,
    not the old state. ``domain`` contains precisely its current domain terms.
    The caller must ensure equality-free, function-free deletion eligibility.
    This helper does not materialize its conclusions or change engine state.

    Context and rule-visit caps bound additional proof search. Running out of
    budget only loses opportunities to avoid overdeletion. Completed positive
    inferences remain valid, including those in a partially explored context.
    """

    def __init__(self, rules, asserted, domain, *, max_contexts=128,
                 max_rule_visits=100_000):
        if max_contexts < 0 or max_rule_visits < 0:
            raise ValueError("Support proof budgets must be nonnegative")
        self._asserted = asserted
        self._domain = domain
        self._max_contexts = max_contexts
        self._max_rule_visits = max_rule_visits
        self._seed_index = None
        self._cache = {}
        self._rules = []
        self._dependents = defaultdict(list)
        self._heads = set()
        seen = set()
        for rule in rules:
            head = rule.head
            if (head is None or len(head.args) != 1
                    or not isinstance(head.args[0], Var) or not rule.body
                    or any(atom.args != head.args for atom in rule.body)):
                continue
            premises = frozenset(atom.predicate for atom in rule.body)
            key = head.predicate, premises
            if key in seen:
                continue
            seen.add(key)
            number = len(self._rules)
            self._rules.append((head.predicate, len(premises)))
            self._heads.add(head.predicate)
            for predicate in premises:
                self._dependents[predicate].append(number)
        self.stats = {
            "queries": 0, "certified": 0, "contexts": 0, "cache_hits": 0,
            "rule_visits": 0, "budget_misses": 0, "indexed_subjects": 0,
        }

    def proves(self, atom):
        """Return true only if a finite current unary proof has been found."""
        self.stats["queries"] += 1
        if (len(atom.args) != 1 or atom.predicate not in self._heads
                or isinstance(atom.args[0], (Var, Skolem))):
            return False
        if self._max_contexts == 0:
            self.stats["budget_misses"] += 1
            return False
        if self._seed_index is None:
            self._seed_index = defaultdict(set)
            for fact in self._asserted:
                if len(fact.args) == 1:
                    self._seed_index[fact.args[0]].add(fact.predicate)
            self.stats["indexed_subjects"] = len(self._seed_index)
        term = atom.args[0]
        seeds = set(self._seed_index.get(term, ()))
        if term in self._domain:
            seeds.add(TOP)
        key = frozenset(seeds)
        known = self._cache.get(key)
        if known is not None:
            self.stats["cache_hits"] += 1
        elif (len(self._cache) >= self._max_contexts
              or self.stats["rule_visits"] >= self._max_rule_visits):
            self.stats["budget_misses"] += 1
            return False
        else:
            known = set(key)
            pending = deque(known)
            remaining = {}
            exhausted = False
            while pending and not exhausted:
                predicate = pending.popleft()
                for number in self._dependents.get(predicate, ()):
                    if self.stats["rule_visits"] >= self._max_rule_visits:
                        exhausted = True
                        self.stats["budget_misses"] += 1
                        break
                    self.stats["rule_visits"] += 1
                    head, count = self._rules[number]
                    if head in known:
                        continue
                    remaining[number] = remaining.get(number, count) - 1
                    if remaining[number] == 0:
                        known.add(head)
                        pending.append(head)
            known = self._cache[key] = frozenset(known)
            self.stats["contexts"] += 1
        result = atom.predicate in known
        self.stats["certified"] += result
        return result
