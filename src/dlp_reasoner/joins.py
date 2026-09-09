"""Experimental positional plans for positive relational joins.

This is an interpreter specialization, not an implementation of RPT+ or a
worst-case-optimal join algorithm. Exact bucket selection remains dynamic;
variable classification is compiled once and intermediate bindings use slots.
"""
from itertools import islice

from .model import EQ, NEQ, Var


class _Lookahead:
    """Invocation-local ordering estimates; never a filter or answer cache."""

    MIN_FANOUT = 32
    SIZE_FACTOR = 4
    SAMPLE_ROWS = 4
    PROBE_BUDGET = 1024

    def __init__(self, atoms, missing, stats):
        self.atoms, self.missing, self.stats = atoms, missing, stats
        self.probes = 0
        self.hints = {}
        self.exhausted = False
        for key in ("calls", "eligible_choices", "decisions", "reorders", "cache_hits",
                    "probe_lookups", "sample_rows", "budget_exhaustions", "hint_entries"):
            stats.setdefault("lookahead_" + key, 0)
        stats["lookahead_calls"] += 1

    def _score(self, candidate, remaining, binding):
        position, slots, values, rows = candidate
        total, samples = 0, 0
        for row in islice(rows, self.SAMPLE_ROWS):
            samples += 1
            self.stats["lookahead_sample_rows"] += 1
            extended = binding.copy()
            for slot, actual, expected in zip(slots, row, values):
                if slot >= 0:
                    bound = extended[slot]
                    if bound is not self.missing and bound != actual:
                        break
                    extended[slot] = actual
                elif actual != expected:
                    break
            else:
                next_size = float("inf")
                for following in remaining:
                    if following == position:
                        continue
                    if self.probes >= self.PROBE_BUDGET:
                        self._exhaust()
                        return None
                    predicate, next_slots, constants, relation = self.atoms[following]
                    next_values = tuple(extended[slot] if slot >= 0 else constant
                                        for slot, constant in zip(next_slots, constants))
                    self.probes += 1
                    self.stats["lookahead_probe_lookups"] += 1
                    next_size = min(next_size, len(relation.lookup(predicate, next_values)))
                    if next_size == 0:
                        break
                total += next_size
        # Invalid sample rows contribute zero next-step volume, but neither
        # invalid nor unrepresentative samples can eliminate any actual rows.
        return len(rows) * (1 + total / samples)

    def _exhaust(self):
        if not self.exhausted:
            self.stats["lookahead_budget_exhaustions"] += 1
            self.exhausted = True

    def choose(self, first, second, remaining, binding):
        # Invalid sampled rows can consume no lookups. Bound their decisions
        # and retained hints too, rather than relying on the lookup budget alone.
        if self.exhausted or self.probes >= self.PROBE_BUDGET or len(self.hints) >= self.PROBE_BUDGET:
            self._exhaust()
            return first
        if (second is None or len(first[3]) < self.MIN_FANOUT
                or len(second[3]) > self.SIZE_FACTOR * len(first[3])):
            return first
        self.stats["lookahead_eligible_choices"] += 1
        # These coarse keys intentionally reuse only traversal hints. Binding
        # values may differ and estimates may be wrong; enumeration stays exact.
        key = (remaining, tuple(i for i, value in enumerate(binding)
                                if value is not self.missing),
               first[0], second[0], len(first[3]).bit_length(), len(second[3]).bit_length())
        if key in self.hints:
            self.stats["lookahead_cache_hits"] += 1
            chosen = first if self.hints[key] == first[0] else second
        else:
            first_score = self._score(first, remaining, binding)
            if first_score is None:
                return first
            second_score = self._score(second, remaining, binding)
            if second_score is None:
                return first
            chosen = second if second_score < first_score else first
            self.hints[key] = chosen[0]
            self.stats["lookahead_hint_entries"] += 1
            self.stats["lookahead_decisions"] += 1
        self.stats["lookahead_reorders"] += chosen[0] != first[0]
        return chosen


class RelationalPlan:
    __slots__ = ("variables", "atoms")

    def __init__(self, rule):
        variables = {}
        atoms = []
        for atom in rule.body:
            terms = []
            for term in atom.args:
                if isinstance(term, Var):
                    terms.append((variables.setdefault(term, len(variables)), None))
                else:
                    terms.append((-1, term))
            atoms.append((atom.predicate, tuple(terms)))
        self.variables = tuple(variables)
        self.atoms = tuple(atoms)

    @classmethod
    def create(cls, rule):
        if not rule.body or any(atom.predicate in {EQ, NEQ} for atom in rule.body):
            return None
        return cls(rule)

    def solutions(self, engine, missing, delta_index=None, delta_position=None, initial=None,
                  *, lookahead=False):
        """Yield the same complete bindings as the generic positive evaluator."""
        initial = {} if initial is None else initial
        variables = self.variables
        # Constants can change representatives after equality ingestion, so only
        # their positions are cached. Resolve values anew on every invocation.
        atoms = tuple((predicate, tuple(slot for slot, _ in terms),
                       tuple(engine.normalize(term) if slot < 0 else missing
                             for slot, term in terms),
                       delta_index if position == delta_position else engine._index)
                      for position, (predicate, terms) in enumerate(self.atoms))
        stats = engine.stats
        planner = _Lookahead(atoms, missing, stats) if lookahead and len(atoms) > 1 else None

        def visit(remaining, binding):
            if not remaining:
                stats["body_matches"] += 1
                yield {**initial, **dict(zip(variables, binding))}
                return
            chosen = None
            second = None
            size = float("inf")
            for position in remaining:
                predicate, slots, constants, relation = atoms[position]
                values = tuple(binding[slot] if slot >= 0 else constant
                               for slot, constant in zip(slots, constants))
                rows = relation.lookup(predicate, values)
                count = len(rows)
                if count == 0:
                    return
                if count < size:
                    if planner is not None:
                        second = chosen
                    chosen = position, slots, values, rows
                    size = count
                elif planner is not None and (second is None or count < len(second[3])):
                    second = position, slots, values, rows
            if planner is not None:
                chosen = planner.choose(chosen, second, remaining, binding)
            position, slots, values, rows = chosen
            rest = tuple(p for p in remaining if p != position)
            for row in rows:
                stats["candidate_rows"] += 1
                extended = binding.copy()
                for slot, actual, expected in zip(slots, row, values):
                    if slot >= 0:
                        bound = extended[slot]
                        if bound is not missing and bound != actual:
                            break
                        extended[slot] = actual
                    elif actual != expected:
                        break
                else:
                    yield from visit(rest, extended)

        try:
            yield from visit(tuple(range(len(atoms))),
                             [initial.get(variable, missing) for variable in variables])
        finally:
            # Release captured indexes/hints promptly, including early close.
            visit = None
