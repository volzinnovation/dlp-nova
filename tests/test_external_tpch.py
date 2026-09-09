"""Offline checks for TPC-H-derived row-identity-preserving join components."""
import random

import pytest

from benchmarks.external_tpch import COMPONENTS, digest, make_program
from dlp_reasoner.engine import Engine


def independent_join(component, relations):
    """Nested relational join without Engine or its indexes/plans."""
    bindings = [{}]
    for table, columns in component["body"]:
        next_bindings = []
        for binding in bindings:
            for row in relations[table]:
                current = dict(binding)
                for column, value in zip(columns, row):
                    if column in current and current[column] != value:
                        break
                    current[column] = value
                else:
                    next_bindings.append(current)
        bindings = next_bindings
    return [tuple(binding[name] for name in component["answer"]) for binding in bindings]


@pytest.mark.parametrize("number", [3, 5, 9])
def test_component_bindings_match_independent_join(number):
    randomizer = random.Random(number)
    component = COMPONENTS[number]
    for trial in range(30):
        relations = {table: sorted({tuple(randomizer.randrange(4) for _ in columns)
                                   for _ in range(8)}) for table, columns in component["body"]}
        program, variables, rule = make_program(number, relations)
        engine = Engine(program).materialize()
        actual = [tuple(binding[var] for var in variables) for binding in engine._solutions(rule)]
        expected = independent_join(component, relations)
        assert sorted(actual) == sorted(expected), (number, trial)
        assert len(program.facts) == sum(map(len, relations.values()))


def test_lineitem_primary_key_preserves_two_bag_rows():
    relations = {"customer": [(3,)], "orders": [(8, 3)], "lineitem": [(8, 1), (8, 2)]}
    program, variables, rule = make_program(3, relations)
    engine = Engine(program).materialize()
    result = {tuple(binding[var] for var in variables) for binding in engine._solutions(rule)}
    assert result == {(3, 8, 8, 1), (3, 8, 8, 2)}
    assert digest(result) != digest({(3, 8, 8, 1)})


def test_each_projected_relation_includes_its_primary_key():
    primary_keys = {"customer": ["c_custkey"], "orders": ["o_orderkey"],
                    "lineitem": ["l_orderkey", "l_linenumber"], "supplier": ["s_suppkey"],
                    "nation": ["n_nationkey"], "region": ["r_regionkey"],
                    "part": ["p_partkey"], "partsupp": ["ps_partkey", "ps_suppkey"]}
    for component in COMPONENTS.values():
        for table, sql in component["relations"].items():
            columns = sql.partition(" FROM ")[0].removeprefix("SELECT ").split(",")
            assert set(primary_keys[table]) <= set(columns)
        assert set(component["relations"]) == {table for table, _ in component["body"]}
