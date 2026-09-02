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


def test_rejects_submission_without_theorem_declaration():
    """A truncated/preamble-only submission compiles but proves nothing -> must be rejected.

    Regression for the ProofNet# false-positives (2026-06-14): a generation cut off at the token
    cap emitted only `def is_topology ... :=` (no `theorem`); Lean compiled the bare def with no
    errors and the proof was scored `solved`.

    AUDIT FIX (2026-07-10): `declares_goal=False` here stands in for a backend that genuinely
    found no goal-bearing declaration in what it ACTUALLY COMPILED (post assembly) -- see
    `RawVerification.declares_goal`. This is the verifier's own defense-in-depth, independent of
    which real backend is behind it.
    """
    v = Verifier(always(success=True, output="", declares_goal=False))
    preamble = "def is_topology (X : Type*) (T : Set (Set X)) :=\n  univ ∈ T"
    res = v.verify(THM, preamble)
    assert res.ok is False
    assert res.reason == "no_goal"
    assert "no theorem" in res.feedback


def test_rejects_pure_prose_marked_success():
    """Even if a backend spuriously 'succeeds', free-form prose declares no goal -> rejected."""
    v = Verifier(always(success=True, output="", declares_goal=False))
    res = v.verify(THM, "### Detailed Proof\n\nWe are given a function f ...")
    assert res.ok is False
    assert res.reason == "no_goal"


def test_accepts_lemma_and_example_declarations():
    """`lemma`/`example` are valid goal-bearing declarations (model may rename `theorem`)."""
    v = Verifier(always(success=True, output=""))
    assert v.verify(THM, "lemma t : True := by trivial").ok is True
    assert v.verify(THM, "example : True := by trivial").ok is True


def test_accepts_continuation_style_proof_when_backend_confirms_a_declared_goal():
    """AUDIT REGRESSION (2026-07-10, AUDIT_PLAN.md Task A1): a bare-tactic completion (no
    theorem/lemma/example line -- what continuation-style templates extract by design) must score
    `ok=True` when the backend reports it genuinely compiled a declared goal, even though the RAW
    completion itself has no declaration. See `test_verifier_accepts_genuine_continuation_style_
    solve_end_to_end` in test_lean_repl.py for the real-backend-shaped version of this test.
    """
    v = Verifier(always(success=True, output="", declares_goal=True))
    bare_continuation_proof = "  trivial"
    res = v.verify(THM, bare_continuation_proof)
    assert res.ok is True, res.feedback
    assert res.reason == "ok"


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
    """Source assembly prepends imports/opens for a bare proof, and only inserts the heartbeat
    safety net (not a second theorem line) for an already-complete file (AUDIT_PLAN.md Task A2,
    2026-07-10 — see test_build_source_complete_file_gets_heartbeat_safety_net_only below)."""
    cfg = load_config(BASE_CONFIG)
    backend = PantographBackend(cfg)
    thm = Theorem(name="t", statement="theorem t : True", imports=("Mathlib",), opens=("Nat",))
    bare = "theorem t : True := by trivial"
    src = backend._build_source(thm, bare)
    assert src.startswith("import Mathlib")
    assert "open Nat" in src
    assert bare in src


def test_build_source_reconstructs_theorem_header_for_continuation_only_proofs():
    """CRITICAL REGRESSION (found live 2026-07-06, traced byte-exact from a real p8battery2_*
    ProofNet# cell — see PROGRESS.md/DECISIONS.md that date):
    `DeepSeekV15Template`/`GoedelSFTTemplate`
    ask the model to CONTINUE directly after `:= by` — their extracted "proof" is a bare tactic body
    with no `import` line AND no restated `theorem ...` line (unlike `WholeProofTemplate`, which
    makes
    the model re-emit the whole fenced block, self-contained, hitting the OTHER `_build_source`
    branch). The old code's fallback branch just prepended imports/opens and appended the proof
    VERBATIM — dropping the theorem declaration entirely, so bare tactics ended up at the top level
    of
    the file (a guaranteed Lean parse error, not a real proof failure). This must never regress.

    Uses the EXACT real example traced live: `Artin__exercise_10_1_13`, DeepSeek-Prover-V1.5-SFT.
    """
    cfg = load_config(BASE_CONFIG)
    backend = PantographBackend(cfg)
    thm = Theorem(
        name="exercise_10_1_13",
        statement=(
            "theorem exercise_10_1_13 {R : Type*} [Ring R] {x : R}\n"
            "  (hx : IsNilpotent x) : IsUnit (1 + x)"
        ),
        imports=("Mathlib",),
        opens=("Function", "Fintype", "Subgroup", "Ideal", "Polynomial", "Submodule", "Zsqrtd",
               "BigOperators"),
    )
    # the real extracted proof from the traced cell — bare tactics, no import, no restated theorem
    continuation_proof = (
        "obtain ⟨n, hn⟩ := hx\n  use 1 - x\n  rw [← sub_eq_zero] at hn\n"
        "  simp [mul_add, mul_comm, mul_left_comm, hn, sub_eq_add_neg]"
    )
    src = backend._build_source(thm, continuation_proof)
    assert "import Mathlib" in src
    assert "open Function Fintype Subgroup Ideal Polynomial Submodule Zsqrtd BigOperators" in src
    # the theorem declaration MUST be reconstructed, ending in `:= by`, immediately before the body
    assert "theorem exercise_10_1_13 {R : Type*} [Ring R] {x : R}" in src
    assert "(hx : IsNilpotent x) : IsUnit (1 + x) := by" in src
    assert continuation_proof in src
    # and the body must come AFTER the theorem line, not before it (order matters for Lean parsing)
    assert src.index(":= by") < src.index("obtain ⟨n, hn⟩")


def test_build_source_whole_proof_branch_is_unaffected_by_the_fix():
    """Regression check: `WholeProofTemplate`'s own models (Goedel-Prover-V2, DeepSeek-Prover-V2-7B)
    re-emit a complete file (their extraction naturally includes `import ...`) — that branch must
    not
    get a theorem line spliced in a second time (the header-reconstruction fix is a no-op here).
    """
    cfg = load_config(BASE_CONFIG)
    backend = PantographBackend(cfg)
    thm = Theorem(name="t", statement="theorem t : True", imports=("Mathlib",), opens=("Nat",))
    full = "import Mathlib\n\ntheorem t : True := by trivial"
    src = backend._build_source(thm, full)
    assert src.count("theorem t : True") == 1  # not duplicated
    assert "import Mathlib" in src


def test_build_source_complete_file_gets_heartbeat_safety_net_only():
    """AUDIT FIX (2026-07-10, AUDIT_PLAN.md Task A2): the complete-file branch previously returned
    `proof` completely untouched, diverging from `ReplBackend._build_repl_source` (which applies
    `set_option maxHeartbeats 0` unconditionally, regardless of shape) — parity gap, benign in
    practice since `PantographBackend` is never used by a real run (`eval/run.py` wires
    `ReplBackend`
    exclusively), but fixed for consistency. Must insert the option, not restate the declaration.
    """
    cfg = load_config(BASE_CONFIG)
    backend = PantographBackend(cfg)
    thm = Theorem(name="t", statement="theorem t : True", imports=("Mathlib",), opens=("Nat",))
    full = "import Mathlib\n\ntheorem t : True := by trivial"
    src = backend._build_source(thm, full)
    assert "set_option maxHeartbeats 0" in src
    assert src.count("theorem t : True") == 1
    assert src.count("import Mathlib") == 1
    # inserted right after the import block, not duplicated on a second call
    already = "import Mathlib\nset_option maxHeartbeats 400000\n\ntheorem t : True := by trivial"
    assert backend._build_source(thm, already).count("set_option maxHeartbeats") == 1


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


@pytest.mark.lean
@pytest.mark.slow
def test_contract_accepts_genuine_continuation_style_solve():
    """AUDIT REGRESSION (2026-07-10, AUDIT_PLAN.md Task A1/G): permanent REAL-Lean lock-in for the
    no_goal false-rejection bug. Every other test of this exact scenario
    (`test_lean_repl.py::test_verifier_accepts_genuine_continuation_style_solve_end_to_end`,
    `test_accepts_continuation_style_proof_when_backend_confirms_a_declared_goal` above) runs
    against `ScriptedReplTransport`/`always()`, which only proves the WIRING is correct — this test
    is the one that proves the real Lean REPL genuinely accepts the reconstructed source the way the
    fix assumes, closing the exact coverage gap this bug exploited (a newly-exercised code path —
    continuation-style, bare-tactic completions — that only fast/mocked tests had ever touched,
    per SYNTHESIS.md Lesson 8).
    """
    v = Verifier(_built_backend())
    thm = Theorem(name="triv_continuation", statement="theorem triv_continuation : True")
    # No theorem/lemma/example line -- exactly what DeepSeekV15Template/GoedelSFTTemplate/
    # BFSProverTemplate extraction produces by design (the backend reconstructs the header).
    res = v.verify(thm, "  trivial")
    assert res.ok, res.feedback
    assert res.reason == "ok"
