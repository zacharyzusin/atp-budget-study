"""Tests for the Verifier orchestration (Task 0.2).

Fast tests mock the Lean backend (ScriptedBackend). The real-Lean integration tests are marked
`lean`+`slow` and skip cleanly until `scratch/lean-cache` is built (disk hold).
"""

from __future__ import annotations

import pytest

from atp.config import BASE_CONFIG, load_config
from atp.lean import (
    LeanEnvNotReady,
    PantographBackend,
    RawVerification,
    ReplBackend,
    ScriptedBackend,
    Theorem,
    Verifier,
    always,
)

THM = Theorem(name="t", statement="theorem t : True")

GOOD_PROOF = "theorem t : True := by\n  trivial"
SORRY_PROOF = "theorem t : True := by\n  sorry"
BAD_OUTPUT = "test.lean:2:2: error: unsolved goals\n⊢ True"


def test_accepts_clean_proof():
    v = Verifier(always(success=True, output=""))
    res = v.verify(THM, GOOD_PROOF)
    assert res.ok is True
    assert res.reason == "ok"
    assert res.earliest_error is None
    assert res.loopholes == ()
    assert res.feedback == "Proof verified."


def test_rejects_compile_error_and_surfaces_failing_step():
    v = Verifier(always(success=False, output=BAD_OUTPUT))
    res = v.verify(THM, "theorem t : True := by\n  rfl")
    assert res.ok is False
    assert res.reason == "compile_error"
    assert res.earliest_error is not None
    assert res.earliest_error.line == 2
    assert res.failing_step is not None
    assert "unsolved goals" in res.feedback


def test_rejects_loophole_even_when_backend_accepts():
    """A backend may 'succeed' on a sorry-laden proof; the verifier must still reject it."""
    v = Verifier(always(success=True, output=""))
    res = v.verify(THM, SORRY_PROOF)
    assert res.ok is False
    assert res.reason == "loophole"
    assert "sorry" in res.loopholes
    assert "sorry" in res.feedback


def test_sorry_warning_is_treated_as_loophole():
    v = Verifier(always(success=True, output="test.lean:1:0: warning: declaration uses 'sorry'"))
    # proof text itself doesn't contain the token, but the warning does -> still a loophole
    res = v.verify(THM, "theorem t : True := by\n  myTac")
    assert res.ok is False
    assert res.reason == "loophole"
    assert "sorry" in res.loopholes


def test_timeout_takes_precedence():
    v = Verifier(always(success=False, output="", timed_out=True))
    res = v.verify(THM, GOOD_PROOF)
    assert res.ok is False
    assert res.reason == "timeout"
    assert "timed out" in res.feedback


def test_backend_receives_calls():
    backend = ScriptedBackend(lambda _t, _p: RawVerification(True, ""))
    Verifier(backend).verify(THM, GOOD_PROOF)
    assert backend.calls == [(THM, GOOD_PROOF)]


def test_from_config_uses_config_policy():
    cfg = load_config(BASE_CONFIG)
    v = Verifier.from_config(cfg, always(success=True, output=""))
    assert tuple(cfg.lean.reject_loopholes) == v.reject_loopholes
    assert v.timeout_s == cfg.lean.verify_timeout_s
    # native_decide is in the base reject list -> a "successful" native_decide proof is rejected
    res = v.verify(THM, "theorem t : True := by\n  native_decide")
    assert res.ok is False and res.reason == "loophole"


def test_real_backend_not_ready_raises_clearly():
    """Before the env is built, the real backend fails loudly and clearly (not silently)."""
    cfg = load_config(BASE_CONFIG)
    backend = PantographBackend(cfg)
    with pytest.raises(LeanEnvNotReady):
        backend.verify(THM, GOOD_PROOF)


def test_build_source_adds_imports_when_missing():
    """Source assembly prepends imports/opens for a bare proof, and leaves a full file untouched."""
    cfg = load_config(BASE_CONFIG)
    backend = PantographBackend(cfg)
    thm = Theorem(name="t", statement="theorem t : True", imports=("Mathlib",), opens=("Nat",))
    bare = "theorem t : True := by trivial"
    src = backend._build_source(thm, bare)
    assert src.startswith("import Mathlib")
    assert "open Nat" in src
    assert bare in src
    full = "import Mathlib\n\ntheorem t : True := by trivial"
    assert backend._build_source(thm, full) == full  # already complete -> unchanged


# --------------------------------------------------------------------------------------
# Real-Lean integration CONTRACT (version-agnostic): trivial true/false proofs that must behave
# identically on EITHER stack — the v4.29.0 plumbing env or the Goedel-pinned env. This is the
# contract that lets us swap backends/envs with confidence (DECISIONS.md 2026-06-04).
# Point it at any built lake project via ATP_LEAN_ENV_DIR; skips cleanly when no env is built.
# --------------------------------------------------------------------------------------
def _built_backend():
    """The real verification backend for the Goedel pin: leanprover-community/repl.

    (Supersedes PantographBackend here — PyPantograph has no release matching Lean v4.9.0-rc1;
    see DECISIONS.md 2026-06-05. ReplBackend needs no Python package, only the built `repl` exe.)
    Point it at any built lake env via ATP_LEAN_ENV_DIR; skips cleanly when none is built.
    """
    import os

    cfg = load_config(BASE_CONFIG)
    env_dir = os.environ.get("ATP_LEAN_ENV_DIR")
    backend = ReplBackend(cfg, project_path=env_dir) if env_dir else ReplBackend(cfg)
    if not backend._env_built():
        pytest.skip(
            f"no built Lean env at {backend.project_path} (need mathlib oleans + repl exe at "
            f"{backend._repl_path()})"
        )
    return backend


@pytest.mark.lean
@pytest.mark.slow
def test_contract_accepts_trivial_true():
    v = Verifier(_built_backend())
    thm = Theorem(name="ok", statement="theorem ok : True")
    res = v.verify(thm, "theorem ok : True := by\n  trivial")
    assert res.ok, res.feedback


@pytest.mark.lean
@pytest.mark.slow
def test_contract_rejects_false():
    v = Verifier(_built_backend())
    res = v.verify(
        Theorem(name="bad", statement="theorem bad : (1 : Nat) = 2"),
        "theorem bad : (1 : Nat) = 2 := by\n  rfl",
    )
    assert not res.ok
    assert res.reason == "compile_error"
