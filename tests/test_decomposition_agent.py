"""Tests for the subgoal-decomposition agent (WS6 item 3).

Design note: results/phase_decomp/DESIGN.md — read it for why each check below exists. Written
test-first, targeting the specific risks the design note lists (parser correctness, sketch check
gating subgoal spend, budget accounting, round-retry on partial failure) rather than only a
happy-path smoke test.

REVISED 2026-07-25 after the first real-model smoke test (job 11684686): Goedel-Prover-V2-8B ignored
the original custom `HAVE i:`/`MAIN:` delimited format and instead wrote a normal Lean proof with
genuine `have <name> : <stmt> := by sorry` placeholders — parsing now targets that native shape
directly (see decomposition.py's module-level comment for the full story). These tests reflect the
revised design; the smoke test's actual completion text is used as the "realistic" fixture below.
"""

from __future__ import annotations

from atp.agents.decomposition import (
    Decomposition,
    DecompositionAgent,
    build_composed_proof,
    build_sketch,
    parse_decomposition,
    split_signature,
    subgoal_theorem,
)
from atp.budget import BudgetMeter
from atp.lean import RawVerification, ScriptedBackend, Theorem, Verifier
from atp.models import ScriptedTransport, VLLMClient, completion_response
from atp.models.templates import WholeProofTemplate

THM = Theorem(name="foo", statement="theorem foo {G : Type*} [Group G] (a b : G) : a * b = a * b")

# The actual shape Goedel-Prover-V2-8B produced in the real smoke test (job 11684686,
# aime_1984_p7__seed0), lightly adapted to THM and given a real (non-sorry) closing step.
REALISTIC_COMPLETION = """theorem foo {G : Type*} [Group G] (a b : G) : a * b = a * b := by
  have h1 : a * b = a * b := by sorry
  have h2 : True := by sorry
  exact h1
"""


# ---------------------------------------------------------------- parsing
def test_parse_decomposition_completion_realistic():
    d = parse_decomposition(REALISTIC_COMPLETION)
    assert d is not None
    assert d.haves == (("h1", "a * b = a * b"), ("h2", "True"))
    assert d.main == "exact h1"
    assert d.text == REALISTIC_COMPLETION


def test_parse_decomposition_single_have():
    text = "theorem t : True := by\n  have h : True := by sorry\n  exact h\n"
    d = parse_decomposition(text)
    assert d is not None
    assert d.haves == (("h", "True"),)


def test_parse_decomposition_have_with_quantifier():
    text = "theorem t : True := by\n  have h : ∀ x : Nat, x = x := by sorry\n  trivial\n"
    d = parse_decomposition(text)
    assert d is not None
    assert d.haves[0] == ("h", "∀ x : Nat, x = x")


def test_parse_decomposition_accepts_bare_sorry_form_no_by():
    text = "theorem t : True := by\n  have h : True := sorry\n  trivial\n"
    d = parse_decomposition(text)
    assert d is not None
    assert d.haves == (("h", "True"),)


def test_parse_decomposition_returns_none_on_no_haves():
    assert parse_decomposition("theorem t : True := by\n  trivial\n") is None


def test_parse_decomposition_returns_none_on_bare_sorry_main():
    """The real failure mode found in the smoke test: model gives haves but leaves the actual
    closing step as `sorry` too — must be rejected, not accepted as a trivially-true sketch."""
    text = "theorem t : True := by\n  have h : True := by sorry\n  sorry\n"
    assert parse_decomposition(text) is None


def test_parse_decomposition_returns_none_on_empty_main():
    text = "theorem t : True := by\n  have h : True := by sorry\n"
    assert parse_decomposition(text) is None


def test_parse_decomposition_strips_trailing_fence():
    text = "theorem t : True := by\n  have h : True := by sorry\n  trivial\n```"
    d = parse_decomposition(text)
    assert d is not None
    assert d.main == "trivial"


# ---------------------------------------------------------------- signature splitting
def test_split_signature_simple():
    binders, goal = split_signature("theorem t (n : Nat) : n + 0 = n")
    assert binders == "(n : Nat)"
    assert goal == "n + 0 = n"


def test_split_signature_implicit_and_instance_binders():
    binders, goal = split_signature(
        "theorem foo {G : Type*} [Group G] (a b : G) : a * b = a * b"
    )
    assert binders == "{G : Type*} [Group G] (a b : G)"
    assert goal == "a * b = a * b"


def test_split_signature_no_binders():
    binders, goal = split_signature("theorem t : True")
    assert binders == ""
    assert goal == "True"


def test_subgoal_theorem_reuses_parent_binders():
    thm = subgoal_theorem(THM, 1, "h1", "a * b = a * b")
    assert thm.name == "foo__have1"
    assert "{G : Type*} [Group G] (a b : G)" in thm.statement
    assert thm.statement.rstrip().endswith("a * b = a * b")
    assert thm.imports == THM.imports and thm.opens == THM.opens


# ---------------------------------------------------------------- proof assembly
def test_build_sketch_is_the_models_own_text_verbatim():
    d = parse_decomposition(REALISTIC_COMPLETION)
    sketch = build_sketch(THM, d)
    assert sketch == REALISTIC_COMPLETION
    assert sketch.count(":= by sorry") == 2


def test_build_composed_proof_splices_real_subproofs_no_sorry():
    d = parse_decomposition(REALISTIC_COMPLETION)
    composed = build_composed_proof(THM, d, {"h1": "trivial", "h2": "trivial"})
    assert "sorry" not in composed
    assert composed.count("trivial") == 2
    assert "exact h1" in composed  # the model's own MAIN block, untouched


def test_build_composed_proof_leaves_unrelated_text_untouched():
    """Only the have-sorry occurrences change; everything else (binders, MAIN) is byte-identical."""
    d = parse_decomposition(REALISTIC_COMPLETION)
    composed = build_composed_proof(THM, d, {"h1": "trivial", "h2": "trivial"})
    assert "theorem foo {G : Type*} [Group G] (a b : G) : a * b = a * b := by" in composed
    assert composed.strip().endswith("exact h1")


# ---------------------------------------------------------------- agent behavior (scripted)
def _backend_have_aware():
    """Sketch check: accept iff every have is `sorry`-closed and MAIN elaborates (contains 'exact').
    Real (composed) check: accept iff no `sorry` remains and every have's body is `trivial`."""

    def respond(_thm, proof):
        if "sorry" in proof:
            if "exact" in proof:
                return RawVerification(success=True, output="")
            return RawVerification(success=False, output="sketch: MAIN does not close the goal")
        if "bad_tactic" in proof:
            return RawVerification(success=False, output="error: unknown tactic")
        return RawVerification(success=True, output="")

    return ScriptedBackend(respond)


def _subgoal_transport(*, solves: dict[str, bool] | None = None, always_trivial=True):
    """Scripted model for BOTH the decompose call and every subgoal's propose call.

    First call (decompose prompt) returns REALISTIC_COMPLETION. Subsequent calls are subgoal
    propose calls (prompt contains the subgoal's own theorem NAME, e.g. `foo__have2`) -> return a
    `trivial` proof (solves) or a bad one (fails), per `solves` (keyed by have name).
    """
    solves = solves or {}
    have_order = [name for name, _ in parse_decomposition(REALISTIC_COMPLETION).haves]

    def respond(payload):
        prompt = payload["prompt"]
        if "Write a Lean 4 proof for the following theorem" in prompt:
            text = REALISTIC_COMPLETION
        else:
            name_solves = always_trivial
            for i, have_name in enumerate(have_order, start=1):
                if f"__have{i}" in prompt and have_name in solves:
                    name_solves = solves[have_name]
            body = "trivial" if name_solves else "bad_tactic"
            text = f"```lean4\n{prompt.splitlines()[0]} := by\n  {body}\n```"
        return completion_response(text, completion_tokens=payload["max_tokens"])

    return ScriptedTransport(respond)


def _agent(transport, backend, meter, **kw) -> DecompositionAgent:
    client = VLLMClient(model="m", transport=transport, meter=meter)
    defaults = dict(sample_max_tokens=10, max_rounds=4, max_subgoal_rounds=4)
    defaults.update(kw)
    return DecompositionAgent(
        client=client, verifier=Verifier(backend), template=WholeProofTemplate(), **defaults
    )


def test_sketch_check_accepts_and_all_subgoals_solve_composes_final_proof():
    transport = _subgoal_transport(always_trivial=True)
    agent = _agent(transport, _backend_have_aware(), BudgetMeter(limit=100000))
    state = agent.prove(THM)
    assert state.solved
    assert "sorry" not in state.proof
    assert "trivial" in state.proof
    kinds = [a.kind for a in state.attempts]
    assert "decompose" in kinds and "compose" in kinds
    assert any(k == "propose" for k in kinds)  # subgoal attempts folded into the audit trail


def test_sketch_rejected_makes_zero_subgoal_calls():
    """A MAIN that doesn't reference any have -> sketch structurally rejected -> no subgoal spend."""
    bad_completion = (
        "theorem foo {G : Type*} [Group G] (a b : G) : a * b = a * b := by\n"
        "  have h1 : True := by sorry\n  trivial\n"  # 'trivial' has no 'exact' -> backend rejects
    )

    def respond(payload):
        return completion_response(bad_completion, completion_tokens=payload["max_tokens"])

    transport = ScriptedTransport(respond)
    agent = _agent(transport, _backend_have_aware(), BudgetMeter(limit=100000), max_rounds=2)
    state = agent.prove(THM)
    assert not state.solved
    # every recorded attempt is a "decompose" kind (no "propose"/"refine" subgoal calls were made)
    assert all(a.kind == "decompose" for a in state.attempts)
    assert transport.calls  # the decompose call itself did happen
    # exactly one call per round (no subgoal calls appended)
    assert len(transport.calls) == 2


def test_unparseable_completion_makes_zero_subgoal_calls():
    """A bare-sorry MAIN (the exact failure mode the real smoke test hit) -> unparseable -> no
    sketch check, no subgoal spend, just a cheap rejected 'decompose' attempt per round."""
    bare_sorry_completion = (
        "theorem foo {G : Type*} [Group G] (a b : G) : a * b = a * b := by\n"
        "  have h1 : True := by sorry\n  sorry\n"
    )

    def respond(payload):
        return completion_response(bare_sorry_completion, completion_tokens=payload["max_tokens"])

    transport = ScriptedTransport(respond)
    agent = _agent(transport, _backend_have_aware(), BudgetMeter(limit=100000), max_rounds=2)
    state = agent.prove(THM)
    assert not state.solved
    assert all(a.kind == "decompose" and a.reason == "unparseable" for a in state.attempts)
    assert len(transport.calls) == 2  # one decompose call per round, nothing else


def test_one_subgoal_unsolved_tries_a_fresh_decomposition_next_round():
    # h1 always solves; h2 never solves (always bad_tactic) for max_subgoal_rounds, exhausting it.
    transport = _subgoal_transport(solves={"h1": True, "h2": False})
    agent = _agent(transport, _backend_have_aware(), BudgetMeter(limit=1_000_000), max_rounds=2,
                    max_subgoal_rounds=2)
    state = agent.prove(THM)
    assert not state.solved
    # two decomposition rounds attempted (max_rounds=2), each with subgoal attempts appended
    n_decompose = sum(1 for a in state.attempts if a.kind == "decompose")
    assert n_decompose >= 2


def test_budget_shared_across_decompose_and_subgoal_calls():
    transport = _subgoal_transport(always_trivial=True)
    meter = BudgetMeter(limit=100000)
    agent = _agent(transport, _backend_have_aware(), meter)
    agent.prove(THM)
    total_reported = sum(c["max_tokens"] for c in transport.calls)
    assert meter.spent == total_reported
    assert meter.spent > 0
