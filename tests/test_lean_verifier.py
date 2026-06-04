"""Tests for the Verifier orchestration (Task 0.2).

Fast tests mock the Lean backend (ScriptedBackend). The real-Lean integration tests are marked
`lean`+`slow` and skip cleanly until `scratch/lean-cache` is built (disk hold).
"""

from __future__ import annotations

import pytest

from atp.config import BASE_CONFIG, load_config
from atp.lean import (
    LeanDojoBackend,
    LeanEnvNotReady,
    RawVerification,
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
    cfg = load_config(BASE_CONFIG)
    backend = LeanDojoBackend(cfg)
    with pytest.raises(LeanEnvNotReady):
        backend.verify(THM, GOOD_PROOF)


# --------------------------------------------------------------------------------------
# Real-Lean integration (deferred): needs lean-dojo + a built scratch/lean-cache.
# --------------------------------------------------------------------------------------
@pytest.mark.lean
@pytest.mark.slow
def test_verifier_accepts_known_good():
    pytest.importorskip("lean_dojo", reason="real Lean backend deferred (disk hold)")
    pytest.skip("RealLeanBackend.verify lands with the scratch/lean-cache build (deferred).")


@pytest.mark.lean
@pytest.mark.slow
def test_verifier_rejects_known_bad():
    pytest.importorskip("lean_dojo", reason="real Lean backend deferred (disk hold)")
    pytest.skip("RealLeanBackend.verify lands with the scratch/lean-cache build (deferred).")
