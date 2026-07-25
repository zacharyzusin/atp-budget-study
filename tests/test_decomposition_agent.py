"""Tests for the subgoal-decomposition agent (WS6 item 3).

Design note: results/phase_decomp/DESIGN.md — read it for why each check below exists. Written
test-first, targeting the specific risks the design note lists (parser correctness, sketch check
gating subgoal spend, budget accounting, round-retry on partial failure) rather than only a
happy-path smoke test.
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

REALISTIC_COMPLETION = """Here is my plan.

HAVE 1: h1 : a * b = a * b
HAVE 2: h2 : True
MAIN:
exact h1
"""


# ---------------------------------------------------------------- parsing
def test_parse_decomposition_completion_realistic():
    d = parse_decomposition(REALISTIC_COMPLETION)
    assert d is not None
    assert d.haves == (("h1", "a * b = a * b"), ("h2", "True"))
    assert d.main == "exact h1"


def test_parse_decomposition_single_have():
    text = "HAVE 1: h : 1 = 1\nMAIN:\nexact h"
    d = parse_decomposition(text)
    assert d is not None
    assert d.haves == (("h", "1 = 1"),)


def test_parse_decomposition_have_with_quantifier():
    text = "HAVE 1: h : ∀ x : Nat, x = x\nMAIN:\nexact fun x => h x"
    d = parse_decomposition(text)
    assert d is not None
    assert d.haves[0] == ("h", "∀ x : Nat, x = x")


def test_parse_decomposition_returns_none_on_missing_main():
    assert parse_decomposition("HAVE 1: h : True") is None


def test_parse_decomposition_returns_none_on_no_haves():
    assert parse_decomposition("MAIN:\ntrivial") is None


def test_parse_decomposition_strips_trailing_fence():
    text = "HAVE 1: h : True\nMAIN:\ntrivial\n```"
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
def test_build_sketch_uses_sorry_for_every_have():
    d = Decomposition(haves=(("h1", "True"), ("h2", "True")), main="exact h1")
    sketch = build_sketch(THM, d)
    assert sketch.count(":= sorry") == 2
    assert "exact h1" in sketch
    assert sketch.startswith(THM.statement)


def test_build_composed_proof_splices_real_subproofs_no_sorry():
    d = Decomposition(haves=(("h1", "True"),), main="exact h1")
    composed = build_composed_proof(THM, d, {"h1": "trivial"})
    assert "sorry" not in composed
    assert "trivial" in composed
    assert "exact h1" in composed


# ---------------------------------------------------------------- agent behavior (scripted)
def _backend_have_aware():
    """Sketch check: accept iff every have is `sorry`-closed and MAIN elaborates (contains 'exact').
    Real (composed) check: accept iff no `sorry` remains and every have's body is `trivial`."""

    def respond(_thm, proof):
        if "sorry" in proof:
            # Sketch pass: structurally fine iff MAIN references something plausible.
            if "exact" in proof:
                return RawVerification(success=True, output="")
            return RawVerification(success=False, output="sketch: MAIN does not close the goal")
        # Composed (real) proof: only accept if every have body is exactly 'trivial'.
        if "bad_tactic" in proof:
            return RawVerification(success=False, output="error: unknown tactic")
        return RawVerification(success=True, output="")

    return ScriptedBackend(respond)


def _subgoal_transport(*, solves: dict[str, bool] | None = None, always_trivial=True):
    """Scripted model for BOTH the decompose call and every subgoal's propose call.

    First call (decompose prompt) returns REALISTIC_COMPLETION-shaped text. Subsequent calls are
    subgoal propose calls (prompt contains the subgoal's own theorem NAME, e.g. `foo__have2` — NOT
    the have's short name `h2`, which never appears verbatim in the rendered subgoal prompt) ->
    return a `trivial` proof (solves) or a bad one (fails), per `solves` (keyed by have name, e.g.
    "h2", internally matched against "__have<i>" using its position in REALISTIC_COMPLETION's order).
    """
    solves = solves or {}
    have_order = [name for name, _ in parse_decomposition(REALISTIC_COMPLETION).haves]

    def respond(payload):
        prompt = payload["prompt"]
        if "Prove the following Lean 4 theorem by decomposing" in prompt:
            text = REALISTIC_COMPLETION
        else:
            # Subgoal propose call: identify which have this is by its theorem name suffix.
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
    bad_completion = "HAVE 1: h1 : True\nMAIN:\ntrivial\n"  # 'trivial' has no 'exact' -> backend rejects

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
