"""Explicit precompiled libraries must never trigger a compiler or a fallback."""
import shutil

import pytest

from dlp_reasoner import native
from dlp_reasoner.engine import Engine
from dlp_reasoner.model import Atom, Program, Rule, Var


@pytest.fixture(scope="module")
def library():
    if not any(shutil.which(name) for name in ("clang++", "g++", "c++")):
        pytest.skip("C++17 compiler unavailable for the precompiled test fixture")
    return native.build_native()


def no_build(*args, **kwargs):
    raise AssertionError("Precompiled native backend invoked the compiler")


def test_precompiled_library_skips_build_and_preserves_reasoning(monkeypatch, library):
    monkeypatch.setenv("DLP_NATIVE_LIBRARY", str(library))
    monkeypatch.setenv("CXX", "/not/an/installed/compiler")
    monkeypatch.setattr(native, "build_native", no_build)
    variable = Var("x")
    program = Program([Rule(Atom("B", (variable,)), (Atom("A", (variable,)),))],
                      {Atom("A", ("a",))})
    engine = Engine(program, backend="native").materialize()
    assert Atom("B", ("a",)) in engine.facts
    with native.NativeContext(object()) as first, native.NativeContext(object()) as second:
        assert first.library_path == library
        assert first.library is second.library


def test_missing_precompiled_library_fails_without_build(monkeypatch, tmp_path):
    path = tmp_path / "missing-library.so"
    monkeypatch.setenv("DLP_NATIVE_LIBRARY", str(path))
    monkeypatch.setattr(native, "build_native", no_build)
    with pytest.raises(native.NativeBackendError, match="Cannot load native backend"):
        native.NativeContext(object())


def test_precompiled_library_abi_is_checked(monkeypatch, library):
    class Function:
        def __call__(self):
            return 999

    class WrongLibrary:
        def __getattr__(self, name):
            return Function()

    # A distinct path avoids the successfully loaded in-process library cache.
    path = library.parent / "wrong-abi.so"
    monkeypatch.setenv("DLP_NATIVE_LIBRARY", str(path))
    monkeypatch.setattr(native, "build_native", no_build)
    monkeypatch.setattr(native.ctypes, "CDLL", lambda unused: WrongLibrary())
    with pytest.raises(native.NativeBackendError, match="ABI mismatch"):
        native.NativeContext(object())
