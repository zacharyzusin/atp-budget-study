"""Tests for the leanprover-community/repl backend (Task 0.6 / Phase 0 verification).

Fast tests drive `ReplBackend` through a `ScriptedReplTransport` (no Lean install, no subprocess),
modelling the REPL's JSON protocol exactly. The real-Lean contract lives in `test_lean_verifier.py`
(`lean`+`slow`) and runs against the built env.
"""

from __future__ import annotations

import pytest

from atp.config import BASE_CONFIG, load_config
from atp.lean import (
    LeanEnvNotReady,
    ReplBackend,
    ScriptedReplTransport,
    Theorem,
    Verifier,
    compute_lean_path,
)
from atp.lean.repl import _encode_command

THM = Theorem(name="t", statement="theorem t : True")


def test_encode_command_sends_astral_notation_as_native_utf8():
    # Regression: astral-plane math notation (𝓝 nhds U+1D4DD, 𝓟 principal U+1D4DF) must reach Lean
    # as raw UTF-8, not \uXXXX surrogate escapes — Lean's JSON reader mangles surrogate pairs into
    # "expected token", silently corrupting both such statements and any proof the model emits.
    wire = _encode_command({"cmd": "theorem t : (𝓝 (0:ℝ)).NeBot := by sorry"})
    assert wire.endswith(b"\n\n")
    assert "𝓝".encode() in wire  # raw 4-byte UTF-8 present
    assert b"\\ud835" not in wire and b"\\udcdd" not in wire  # NOT escaped as a surrogate pair
    # round-trips back to the exact codepoint
    import json

    assert json.loads(wire.decode("utf-8"))["cmd"].count("𝓝") == 1


def _backend(responder, **kw):
    cfg = load_config(BASE_CONFIG)
    return ReplBackend(cfg, transport=ScriptedReplTransport(responder), **kw)


def _import_then(proof_response):
    """Responder: first call (`import Mathlib`) -> env 0; later calls -> proof_response."""
    state = {"n": 0}

    def responder(cmd: dict) -> dict:
        state["n"] += 1
        if state["n"] == 1:
            assert cmd["cmd"] == "import Mathlib"
            return {"env": 0}
        return proof_response(cmd) if callable(proof_response) else proof_response

    return responder


# -- accounting: success / failure mapping ---------------------------------------------
def test_accepts_proof_with_no_messages():
    """A REPL response with a new env and no error messages -> accepted."""
    backend = _backend(_import_then({"env": 1, "messages": []}))
    res = backend.verify(THM, "theorem t : True := by trivial")
    assert res.success is True
    assert res.timed_out is False


def test_rejects_proof_with_error_message():
    err = {
        "messages": [
            {"severity": "error", "pos": {"line": 1, "column": 38}, "data": "The rfl tactic failed"}
        ],
        "env": 2,
    }
    backend = _backend(_import_then(err))
    res = backend.verify(THM, "theorem t : (1:Nat) = 2 := by rfl")
    assert res.success is False
    assert "error:" in res.output and "rfl tactic failed" in res.output


def test_verifier_surfaces_compile_error_through_repl_backend():
    """End-to-end through the Verifier: structured REPL error -> compile_error + earliest error."""
    err = {
        "messages": [
            {
                "severity": "error",
                "pos": {"line": 2, "column": 2},
                "data": "unsolved goals\n⊢ True",
            }
        ],
        "env": 2,
    }
    v = Verifier(_backend(_import_then(err)))
    res = v.verify(THM, "theorem t : True := by\n  rfl")
    assert res.ok is False
    assert res.reason == "compile_error"
    assert res.earliest_error is not None and res.earliest_error.line == 2


def test_sorry_field_is_surfaced_as_loophole():
    """REPL reports a proof's `sorries` out-of-band; the Verifier must still reject it."""
    resp = {
        "env": 1,
        "messages": [],
        "sorries": [{"pos": {"line": 1, "column": 20}, "goal": "True"}],
    }
    v = Verifier(_backend(_import_then(resp)))
    # proof text has no literal 'sorry' token, so rejection must come from the sorries field
    res = v.verify(THM, "theorem t : True := by\n  myAdmitTac")
    assert res.ok is False
    assert res.reason == "loophole"
    assert "sorry" in res.loopholes


def test_malformed_response_without_env_is_not_success():
    """A response with neither `env` nor messages is spurious -> must NOT score as verified.

    Regression for the ProofNet# reviewer/memory false-positives (2026-06-14): a wedged/
    cross-talked REPL returning `{}` under co-location was read as 'no errors -> success'.
    """
    backend = _backend(_import_then({}))
    res = backend.verify(THM, "theorem t : True := by trivial")
    assert res.success is False
    assert "REPL_INFRA_ERROR" in res.output


def test_empty_messages_without_env_is_not_success():
    backend = _backend(_import_then({"messages": []}))
    res = backend.verify(THM, "theorem t : True := by trivial")
    assert res.success is False


# -- protocol details ------------------------------------------------------------------
def test_import_is_sent_once_and_proofs_target_base_env():
    transport = ScriptedReplTransport(_import_then({"env": 5, "messages": []}))
    cfg = load_config(BASE_CONFIG)
    backend = ReplBackend(cfg, transport=transport)
    backend.verify(THM, "theorem t : True := by trivial")
    backend.verify(THM, "theorem t : True := by exact trivial")
    # exactly one import, then every proof runs against base env 0
    assert transport.sent[0] == {"cmd": "import Mathlib"}
    assert all(c.get("env") == 0 for c in transport.sent[1:])
    assert len(transport.sent) == 3


def test_build_repl_source_strips_imports_and_keeps_opens():
    backend = _backend(_import_then({"env": 1, "messages": []}))
    thm = Theorem(name="t", statement="theorem t : True", opens=("Nat",))
    proof = "import Mathlib\nimport Aesop\ntheorem t : True := by trivial"
    src = backend._build_repl_source(thm, proof)
    assert "import" not in src  # all import lines stripped (Mathlib already in base env)
    # `set_option maxHeartbeats 0` is now always prepended first (see the dedicated test) — "open"
    # follows it, not the very start of the string.
    assert src.startswith("set_option maxHeartbeats 0\nopen Nat")
    assert "theorem t : True := by trivial" in src


def test_model_opens_not_duplicated():
    backend = _backend(_import_then({"env": 1, "messages": []}))
    thm = Theorem(name="t", statement="theorem t : True", opens=("Nat",))
    src = backend._build_repl_source(thm, "open Finset\ntheorem t : True := by trivial")
    assert src.count("open ") == 1  # model already opened a namespace -> don't prepend ours
    assert src.startswith("set_option maxHeartbeats 0\nopen Finset")


def test_build_repl_source_reconstructs_theorem_header_for_continuation_only_proofs():
    """CRITICAL REGRESSION (found live 2026-07-06, same root cause as `PantographBackend.
    _build_source` — see PROGRESS.md/DECISIONS.md that date — but a SEPARATE class: `ReplBackend` is
    the backend `eval/run.py` actually uses in production ("ReplBackend supersedes PantographBackend
    for the pin" per that module's own docstring), so fixing `_build_source` alone would have been a
    no-op for every real sweep. `_build_repl_source` strips `import` lines and preserves/prepends
    `open`, but — like the other backend — NEVER reconstructed the `theorem ... := by` declaration
    for a bare continuation-only proof (`DeepSeekV15Template`/`GoedelSFTTemplate`'s extracted output).
    Uses the exact real traced example (`Artin__exercise_10_1_13`, DeepSeek-Prover-V1.5-SFT).
    """
    backend = _backend(_import_then({"env": 1, "messages": []}))
    thm = Theorem(
        name="exercise_10_1_13",
        statement=(
            "theorem exercise_10_1_13 {R : Type*} [Ring R] {x : R}\n"
            "  (hx : IsNilpotent x) : IsUnit (1 + x)"
        ),
        opens=("Function", "Fintype", "Subgroup", "Ideal", "Polynomial", "Submodule", "Zsqrtd",
               "BigOperators"),
    )
    continuation_proof = (
        "obtain ⟨n, hn⟩ := hx\n  use 1 - x\n  rw [← sub_eq_zero] at hn\n"
        "  simp [mul_add, mul_comm, mul_left_comm, hn, sub_eq_add_neg]"
    )
    src = backend._build_repl_source(thm, continuation_proof)
    assert "theorem exercise_10_1_13 {R : Type*} [Ring R] {x : R}" in src
    assert "(hx : IsNilpotent x) : IsUnit (1 + x) := by" in src
    assert continuation_proof in src
    assert src.index(":= by") < src.index("obtain ⟨n, hn⟩")


def test_verifier_accepts_genuine_continuation_style_solve_end_to_end():
    """AUDIT REGRESSION (found 2026-07-10, AUDIT_PLAN.md Task A1): a genuinely CORRECT
    continuation-style completion (bare tactic body, no theorem/lemma/example line -- exactly what
    `DeepSeekV15Template`/`GoedelSFTTemplate`/`BFSProverTemplate` extraction produces by design) must
    score `ok=True` when the backend genuinely accepts the reconstructed source.

    Root cause this guards: `Verifier.verify` used to check `_DECL_RE.search(proof)` against the RAW
    extracted completion, not the backend-assembled source. Since continuation-style templates never
    restate the theorem (the backend reconstructs it via `_build_repl_source`), that check was
    structurally always None for this whole template family -- making it IMPOSSIBLE for any
    continuation-style completion to ever score `ok=True`, correct or not. This directly implicates
    Phase 8's reported "0.0%-everywhere" floor for the DeepSeek-V1.5 triple and Leanabell pair (both
    continuation-style) -- reproduced independently against the real Lean REPL in
    `scripts/audit_no_goal_gate_check.py`. Fix: the backend now reports `declares_goal` computed from
    the ASSEMBLED source it actually compiled, and `Verifier.verify` uses that instead of re-deriving
    it from the raw completion.
    """
    # The backend genuinely accepts the RECONSTRUCTED source (env assigned, zero messages) -- this
    # is exactly what a real, correct `trivial` proof produces once `_build_repl_source` prepends
    # `theorem t : True := by`.
    v = Verifier(_backend(_import_then({"env": 1, "messages": []})))
    bare_continuation_proof = "  trivial"  # no theorem/lemma/example line, by construction
    res = v.verify(THM, bare_continuation_proof)
    assert res.ok is True, res.feedback
    assert res.reason == "ok"


def test_build_repl_source_leaves_self_contained_proofs_unaffected():
    """Regression check: a proof that already declares its own theorem/lemma/example must not get a
    SECOND theorem line spliced in (the `_DECL_RE`/theorem-reconstruction fix). Does now ALSO gain a
    `set_option maxHeartbeats 0` prefix (a separate fix, same date) — that one applies uniformly
    regardless of whether the proof is self-contained, since Lean's heartbeat limit can suppress a
    genuinely valid proof either way."""
    backend = _backend(_import_then({"env": 1, "messages": []}))
    thm = Theorem(name="t", statement="theorem t : True", opens=("Nat",))
    proof = "import Mathlib\nimport Aesop\ntheorem t : True := by trivial"
    assert backend._build_repl_source(thm, proof) == (
        "set_option maxHeartbeats 0\nopen Nat\ntheorem t : True := by trivial"
    )


def test_build_repl_source_always_sets_max_heartbeats_zero():
    """CRITICAL REGRESSION (found live 2026-07-06, see PROGRESS.md/DECISIONS.md that date): the
    DeepSeek-Prover-V1.5/Goedel-Prover-SFT family's official header always includes
    `set_option maxHeartbeats 0` — without it, Lean's default elaboration-heartbeat limit can make an
    otherwise-valid nlinarith/field_simp/simp-heavy proof spuriously fail, indistinguishable from a
    genuinely wrong one. Must apply whether or not the proof already declares its own theorem, and
    must not be duplicated if the model's own completion happens to already set it."""
    backend = _backend(_import_then({"env": 1, "messages": []}))
    thm = Theorem(name="t", statement="theorem t : True")
    assert "set_option maxHeartbeats 0" in backend._build_repl_source(thm, "trivial")
    # not duplicated if already present
    already = "set_option maxHeartbeats 400000\ntheorem t : True := by trivial"
    assert backend._build_repl_source(thm, already).count("set_option maxHeartbeats") == 1


def test_timeout_is_graceful_and_marks_timed_out():
    backend = _backend(_import_then({"_timeout": True}))
    res = backend.verify(THM, "theorem t : True := by sorry_loop")
    assert res.success is False
    assert res.timed_out is True
    assert "Timeout" in res.output


def test_infra_crash_retries_once_on_fresh_process():
    """A REPL process crash (e.g. the broken-pickle norm_num abort) must NOT score a valid proof as
    failed: verify() restarts and retries once on a fresh env. (Regression 2026-06-06.)"""
    state = {"n": 0}

    def responder(cmd):
        if cmd.get("cmd") == "import Mathlib":
            return {"env": 0}
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("REPL process exited unexpectedly")  # crash once
        return {"env": 1, "messages": []}  # healthy on the retry

    backend = _backend(responder)
    res = backend.verify(THM, "theorem t : True := by trivial")
    assert res.success is True  # the retry saw a valid proof
    assert state["n"] == 2  # crashed once, then retried


def test_persistent_infra_crash_reports_infra_error_not_compile():
    """A crash that outlives the retries reports a distinct REPL_INFRA_ERROR (never mistaken for a
    real compile-error rejection)."""

    def responder(cmd):
        if cmd.get("cmd") == "import Mathlib":
            return {"env": 0}
        raise RuntimeError("REPL process exited unexpectedly")

    backend = _backend(responder)
    res = backend.verify(THM, "theorem t : True := by trivial")
    assert res.success is False
    assert "REPL_INFRA_ERROR" in res.output
    assert res.timed_out is False


# -- env readiness ---------------------------------------------------------------------
def test_real_backend_not_ready_raises_clearly(tmp_path):
    """With no injected transport and no built env, verify fails loudly (not silently)."""
    cfg = load_config(BASE_CONFIG)
    backend = ReplBackend(cfg, project_path=tmp_path)  # empty dir => not built
    assert backend._env_built() is False
    with pytest.raises(LeanEnvNotReady):
        backend.verify(THM, "theorem t : True := by trivial")


def test_repl_path_override(tmp_path, monkeypatch):
    cfg = load_config(BASE_CONFIG)
    backend = ReplBackend(cfg, project_path=tmp_path)
    monkeypatch.setenv("ATP_REPL_BIN", "/custom/repl")
    assert str(backend._repl_path()) == "/custom/repl"


def test_lean_project_env_override_points_at_local_stage(tmp_path, monkeypatch):
    """Sweeps stage the env to node-local SSD and set ATP_LEAN_PROJECT; the backend must honor it
    (explicit project_path still wins)."""
    monkeypatch.setenv("ATP_LEAN_PROJECT", str(tmp_path / "local_stage"))
    cfg = load_config(BASE_CONFIG)
    assert ReplBackend(cfg).project_path == (tmp_path / "local_stage").resolve()
    # an explicit arg overrides the env var
    assert ReplBackend(cfg, project_path=tmp_path).project_path == tmp_path.resolve()


# -- LEAN_PATH layout (the v4.9.0-rc1 build/lib vs build/lib/lean fix) ------------------
def test_compute_lean_path_handles_bare_build_lib_layout(tmp_path):
    """v4.9.0-rc1 puts oleans in .lake/build/lib (no /lean). LEAN_PATH must still find them."""
    proj = tmp_path / "env"
    pkg_lib = proj / ".lake" / "packages" / "mathlib" / ".lake" / "build" / "lib"
    pkg_lib.mkdir(parents=True)
    (pkg_lib / "Mathlib.olean").write_text("")
    lp = compute_lean_path(proj, "leanprover/lean4:v4.9.0-rc1")
    assert str(pkg_lib) in lp


def test_compute_lean_path_includes_packages_with_only_nested_oleans(tmp_path):
    """Regression: importGraph keeps NO top-level olean (only build/lib/ImportGraph/*.olean).

    Dropping it from LEAN_PATH makes `import Mathlib` resolve to an empty env. The probe must be
    recursive so such a package's build/lib is still on LEAN_PATH. (Bug found 2026-06-05.)
    """
    proj = tmp_path / "env"
    ig_lib = proj / ".lake" / "packages" / "importGraph" / ".lake" / "build" / "lib"
    (ig_lib / "ImportGraph").mkdir(parents=True)
    (ig_lib / "ImportGraph" / "Cli.olean").write_text("")  # nested only, no top-level *.olean
    lp = compute_lean_path(proj, "leanprover/lean4:v4.9.0-rc1")
    assert str(ig_lib) in lp


def test_compute_lean_path_prefers_nested_lean_layout(tmp_path):
    """Newer toolchains nest oleans under build/lib/lean; that variant must win when present."""
    proj = tmp_path / "env"
    nested = proj / ".lake" / "packages" / "mathlib" / ".lake" / "build" / "lib" / "lean"
    nested.mkdir(parents=True)
    (nested / "Init.olean").write_text("")
    lp = compute_lean_path(proj, "leanprover/lean4:v4.29.0")
    assert str(nested) in lp


def test_compute_lean_path_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("ATP_LEAN_PATH", "/staged/local/path")
    assert compute_lean_path(tmp_path, "x") == "/staged/local/path"


# -- Mathlib base env load: ALWAYS a fresh import, NEVER the pickle ---------------------
def _real_path_backend(tmp_path, responder):
    """A backend with a scripted transport but the real-FS (non-injected) load path enabled."""
    cfg = load_config(BASE_CONFIG)
    t = ScriptedReplTransport(responder)
    b = ReplBackend(cfg, project_path=tmp_path, transport=t)
    b._injected = False  # exercise the production load path
    return b, t


def test_always_imports_never_pickles(tmp_path):
    """Regression (2026-06-06): the REPL pickle yields an env that CRASHES on `norm_num` (cannot
    evaluate the `@[init]` normNumExt) — it made the smoke score every real proof 0. The backend
    must always `import Mathlib` fresh and never emit `unpickleEnvFrom`/`pickleTo`, even if a stale
    `mathlib_env.pkl` is sitting next to the project."""
    (tmp_path / "mathlib_env.pkl").write_text("")  # a stale pickle must be ignored

    def responder(cmd):
        if cmd.get("cmd") == "import Mathlib":
            return {"env": 0}
        return {"env": 1, "messages": []}

    b, t = _real_path_backend(tmp_path, responder)
    b.verify(THM, "theorem t : True := by trivial")
    assert t.sent[0] == {"cmd": "import Mathlib"}  # first command is a fresh import
    assert all("unpickleEnvFrom" not in c for c in t.sent)
    assert all("pickleTo" not in c for c in t.sent)
    assert all(c.get("env") == 0 for c in t.sent if "cmd" in c and c["cmd"] != "import Mathlib")


def test_elaborate_returns_single_sorry_goal():
    # Phase 6 closing-targets: a `<prefix> … sorry` source elaborates with a sorry warning (not an
    # error) and the intermediate goal in `sorries[].goal`.
    resp = {
        "env": 1,
        "sorries": [{"goal": "a b : ℝ\n⊢ b = a", "proofState": 3,
                     "pos": {"line": 2, "column": 2}}],
        "messages": [{"severity": "warning", "data": "declaration uses 'sorry'",
                      "pos": {"line": 1, "column": 0}}],
    }
    b = _backend(_import_then(resp))
    out = b.elaborate(THM, "theorem t : True := by\n  sorry")
    assert out["errors"] == 0 and not out["infra_error"]
    assert out["sorries"] == ["a b : ℝ\n⊢ b = a"]


def test_elaborate_counts_error_severity():
    resp = {"messages": [{"severity": "error", "data": "unsolved goals",
                          "pos": {"line": 2, "column": 2}}]}
    b = _backend(_import_then(resp))
    out = b.elaborate(THM, "theorem t : True := by\n  foo\n  sorry")
    assert out["errors"] == 1 and out["sorries"] == []


def test_old_header_reverify_backend_omits_max_heartbeats_override():
    # scripts/header_confound_reverify.py (DECISIONS.md 2026-07-25h) simulates the pre-2026-07-06
    # verifier by NOT injecting `set_option maxHeartbeats 0` -- this locks that the subclass it
    # builds actually omits it (the whole point of the diagnostic), while still stripping imports
    # and reconstructing the theorem header exactly like the real (current) backend does.
    import importlib.util
    import pathlib

    script_path = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "header_confound_reverify.py"
    spec = importlib.util.spec_from_file_location("header_confound_reverify", script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    cfg = load_config(BASE_CONFIG)
    old_backend = mod.build_old_header_backend(cfg, ReplBackend)
    src = old_backend._build_repl_source(THM, "trivial")
    assert "set_option maxHeartbeats" not in src
    assert "theorem t : True := by" in src
    assert "trivial" in src

    # Sanity: the CURRENT (real) backend still always injects it -- the two backends must diverge
    # on this exact axis, or the diagnostic proves nothing.
    current_backend = ReplBackend(cfg, transport=ScriptedReplTransport(lambda cmd: {}))
    assert "set_option maxHeartbeats 0" in current_backend._build_repl_source(THM, "trivial")
