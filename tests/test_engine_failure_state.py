"""Failed evaluation must not authorize cached complete answers."""
import pytest

from dlp_reasoner.engine import Engine
from dlp_reasoner.model import Atom, Program, ProfileError, Var


@pytest.mark.parametrize("operation", ["materialize", "update"])
@pytest.mark.parametrize("failure", [RuntimeError, KeyboardInterrupt])
def test_evaluation_failure_marks_state_incomplete(monkeypatch, operation, failure):
    engine = Engine(Program(facts={Atom("p", ("a",))})).materialize()

    def fail(*args, **kwargs):
        raise failure("injected evaluation failure")

    monkeypatch.setattr(engine, "_run", fail)
    with pytest.raises(failure):
        if operation == "materialize":
            engine.materialize()
        else:
            engine.update(add=[Atom("p", ("b",))])
    assert not engine.complete
    assert engine.stats["complete"] is False
    assert engine.stats["failure"] == failure.__name__


def test_invalid_transaction_preserves_old_complete_state():
    engine = Engine(Program(facts={Atom("p", ("a",))})).materialize()
    old_facts, old_revision = set(engine.facts), engine._revision
    with pytest.raises(ProfileError):
        engine.update(add=[Atom("p", (Var("unbound"),))])
    assert engine.complete
    assert engine._revision == old_revision
    assert engine.facts == old_facts
