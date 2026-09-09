"""Adverse benchmark controls have independently checked complete answers."""
import pytest

from benchmarks.external_lookahead import control_program, independent_control
from dlp_reasoner.engine import Engine


@pytest.mark.parametrize("control,count", [("unique", 64), ("nonselective", 4096),
                                          ("skewed", 64), ("empty-cycle", 0)])
def test_adverse_controls_match_independent_nested_join(control, count):
    program, variables, rule = control_program(control)
    expected = independent_control(program, variables, rule)
    assert len(expected) == len(set(expected)) == count
    for enabled in (False, True):
        engine = Engine(program).materialize()
        engine._join_lookahead_enabled = enabled
        before = engine.facts.copy()
        actual = [tuple(binding[v] for v in variables) for binding in engine._solutions(rule)]
        assert len(actual) == len(set(actual)) == count
        assert set(actual) == set(expected)
        assert engine.facts == before
