"""Phase 7 Track 1 — stepwise generation with verified proof-state feedback.

Pure-core tests (no GPU, no Lean): the re-grounding logic that keeps the VERIFIED prefix of a failed
attempt and asks the model to continue from the true state, rather than free-running on its own
drifted proof (the exposure-bias fix predicted by the Stage B teacher-forced-loss signature).
"""

from __future__ import annotations

import pytest

from atp.agents.state import STOP_BUDGET, STOP_MAX_ROUNDS, STOP_SOLVED
from atp.agents.stepwise import (
    RegroundProver,
    RegroundStepwiseAgent,
    VerifyOutcome,
    propose_only_tokens_to_solve,
    tactic_body_prefix,
    tactic_body_prefix_candidates,
    verified_prefix,
    verified_prefix_candidates,
)
from atp.budget import BudgetMeter
from atp.budget.meter import BudgetExhausted
from atp.lean import RawVerification, ScriptedBackend, Theorem, Verifier
from atp.models import ScriptedTransport, VLLMClient, completion_response
from atp.models.templates import WholeProofTemplate, extract_lean_block

THM = Theorem(name="t", statement="theorem t : True")


def test_verified_prefix_keeps_lines_before_failing_tactic():
    body = "intro n\nrw [foo]\nnlinarith\nring"
    # Lean blamed the tactic on body line 3 (`nlinarith`) → the verified prefix is the two tactics
    # before it, verbatim.
    assert verified_prefix(body, failing_line=3) == "intro n\nrw [foo]"


def test_verified_prefix_empty_when_first_tactic_fails():
    # Nothing is verified if the very first tactic is the earliest failure.
    assert verified_prefix("simp\nring", failing_line=1) == ""


def test_tactic_body_prefix_strips_the_restated_header():
    # A real whole-proof completion echoes the theorem's OWN header before `:= by` — the failing
    # line (from `FailingStep.line`, counted over the FULL completion) must be translated into an
    # offset within the tactic body, or re-grounding would double-declare the header next round.
    full = "theorem t : True := by\n  intro n\n  WRONG"
    # Lean blamed line 3 (`WRONG`) in the full completion.
    assert tactic_body_prefix(full, failing_line=3) == "  intro n"


def test_tactic_body_prefix_handles_multiline_header():
    full = "theorem t\n  (n : Nat) : True := by\n  intro n\n  WRONG"
    # `:= by` is on line 2; body line 1 (`intro n`) is full-text line 3; failure at line 4.
    assert tactic_body_prefix(full, failing_line=4) == "  intro n"


def test_tactic_body_prefix_empty_when_no_declaration_present():
    # A bare continuation (no restated header) is already just the tactic body.
    assert tactic_body_prefix("intro n\nWRONG", failing_line=2) == "intro n"


def test_verified_prefix_preserves_indentation():
    # Indentation must survive so the prefix splices back under `:= by` byte-exactly.
    body = "  intro n\n  have h : n = n := rfl\n  bad_tactic"
    assert verified_prefix(body, failing_line=3) == "  intro n\n  have h : n = n := rfl"


def test_verified_prefix_candidates_ordered_deepest_first():
    body = "a\nb\nc\nd\nWRONG"
    cands = verified_prefix_candidates(body, failing_line=5)
    assert cands[0] == "a\nb\nc\nd"
    assert cands[-1] == ""
    # strictly decreasing depth (no duplicate-depth entries — blank cuts collapse to one candidate)
    depths = [len(c.splitlines()) for c in cands]
    assert depths == sorted(depths, reverse=True)


def test_verified_prefix_candidates_lets_caller_back_off_past_a_dangling_cut():
    # The naive single cut (right before the failure) lands mid `<;>` — dangling. The next
    # candidate back (excluding the combinator line entirely) is the real usable boundary.
    body = "have h1 : True := trivial\n<;>\nWRONG"
    cands = verified_prefix_candidates(body, failing_line=3)
    assert cands[0] == "have h1 : True := trivial\n<;>"  # naive cut: dangling
    assert cands[1] == "have h1 : True := trivial"  # backed-off: clean


def test_verified_prefix_candidates_respects_max_back_cap():
    body = "\n".join(f"line{i}" for i in range(50)) + "\nWRONG"
    cands = verified_prefix_candidates(body, failing_line=51, max_back=3)
    assert len(cands) <= 4  # deepest + up to max_back backed-off


def test_tactic_body_prefix_candidates_translates_header_offset():
    full = "theorem t : True := by\n  have h1 : True := trivial\n  <;>\n  WRONG"
    cands = tactic_body_prefix_candidates(full, failing_line=4)
    assert cands[0] == "  have h1 : True := trivial\n  <;>"
    assert cands[1] == "  have h1 : True := trivial"


def _extract(text: str) -> str:
    block = extract_lean_block(text)
    return block if block is not None else text.strip()


def test_regrounding_closes_after_committing_verified_prefix():
    # Round 1 (empty prefix): a full whole-proof attempt fails at the 3rd tactic → its first two
    # tactics are the verified prefix. Round 2, re-grounded on that prefix, the model supplies the
    # correct closing → solved. This is the exposure-bias fix: commit what's verified, continue.
    scripted = iter(
        [
            "```lean4\nintro n\nrw [foo]\nWRONG\n```",  # round 1: fails at line 3
            "```lean4\nnlinarith\n```",                 # round 2: continuation closes
        ]
    )

    def generate(prompt: str) -> tuple[str, str]:
        return next(scripted), "stop"

    def verify(body: str) -> VerifyOutcome:
        if body.strip() == "intro n\nrw [foo]\nnlinarith":
            return VerifyOutcome(ok=True, failing_line=0)
        return VerifyOutcome(ok=False, failing_line=3)  # the `WRONG` tactic on line 3

    prover = RegroundProver(
        generate=generate,
        verify=verify,
        render_continuation=lambda prefix: f"CONT<{prefix}>",
        extract=_extract,
        max_rounds=8,
    )
    result = prover.prove()

    assert result.solved
    assert result.proof_body.strip() == "intro n\nrw [foo]\nnlinarith"


def _attempt(kind: str, tokens: int, ok: bool) -> dict:
    return {"kind": kind, "completion_tokens": tokens, "ok": ok}


def test_propose_only_reconstructs_mode1_solve_and_cost():
    # A logged baseline round: propose(fail) -> refine(fail) -> refine(fail) -> propose(SOLVE).
    # Mode 1 (no error-feedback) never sees the refine attempts; its cumulative cost counts only
    # the propose-kind tokens, and it solves at the propose that succeeded.
    attempts = [
        _attempt("propose", 500, False),
        _attempt("refine", 300, False),
        _attempt("refine", 300, False),
        _attempt("propose", 700, True),
    ]
    solved, tokens_to_solve = propose_only_tokens_to_solve(attempts)
    assert solved is True
    assert tokens_to_solve == 500 + 700  # refine tokens never counted toward Mode-1 cost


def test_propose_only_unsolved_when_only_refine_attempts_close():
    # If ONLY a refine attempt ever solved (never a fresh propose), Mode 1 counts it unsolved —
    # that closing depended on error feedback, which Mode 1 by definition never had.
    attempts = [
        _attempt("propose", 400, False),
        _attempt("refine", 200, True),
    ]
    solved, tokens_to_solve = propose_only_tokens_to_solve(attempts)
    assert solved is False
    assert tokens_to_solve is None


def test_propose_only_no_propose_attempts_is_unsolved():
    assert propose_only_tokens_to_solve([]) == (False, None)


def test_regrounding_reprompt_carries_verified_prefix_not_drift():
    # The whole point: round 2's prompt is grounded on the VERIFIED prefix, never the drifted one.
    prompts: list[str] = []
    scripted = iter(["```lean4\na\nb\nWRONG\n```", "```lean4\nclose\n```"])

    def generate(prompt: str) -> tuple[str, str]:
        prompts.append(prompt)
        return next(scripted), "stop"

    def verify(body: str) -> VerifyOutcome:
        return VerifyOutcome(ok=(body.strip() == "a\nb\nclose"), failing_line=3)

    RegroundProver(
        generate=generate,
        verify=verify,
        render_continuation=lambda prefix: f"CONT<{prefix}>",
        extract=_extract,
    ).prove()

    assert prompts[1] == "CONT<a\nb>"      # grounded on the verified prefix
    assert "WRONG" not in prompts[1]       # never the drifted failure


def test_regrounding_propagates_budget_exhaustion_uncaught():
    # Real wiring's `generate` is metered (VLLMClient.generate raises BudgetExhausted when the
    # per-problem budget runs out mid-loop, exactly like WholeProofAgent). The pure core must NOT
    # swallow it — matching WholeProofAgent's pattern lets one caller finish/checkpoint state for
    # every mode uniformly (budget parity: the same stop signal, not a mode-specific shortcut).
    def generate(prompt: str) -> tuple[str, str]:
        raise BudgetExhausted(spent=8000, limit=8000, requested=512)

    def verify(body: str) -> VerifyOutcome:
        raise AssertionError("verify must not be called once generate is out of budget")

    prover = RegroundProver(
        generate=generate,
        verify=verify,
        render_continuation=lambda prefix: prefix,
        extract=lambda t: t,
    )
    with pytest.raises(BudgetExhausted):
        prover.prove()


# -- RegroundStepwiseAgent: real VLLMClient/Verifier/BudgetMeter, scripted transport/backend -------
# Mirrors tests/test_agents.py's fixtures so Mode 3 is exercised through the SAME real
# client/verifier/budget-meter path the eval harness uses (only the network + Lean process are
# scripted).


def _backend_closes_on(marker: str) -> ScriptedBackend:
    """A scripted Lean: closes iff the body contains `marker`; otherwise fails at line 2."""

    def respond(_thm, proof):
        if marker in proof:
            return RawVerification(success=True, output="")
        # Body line 1 is `intro n`; blame line 2 so line 1 becomes the verified prefix.
        return RawVerification(
            success=False, output="test.lean:3:2: error: unsolved goals"
        )

    return ScriptedBackend(respond)


def test_stepwise_agent_rejects_a_dangling_prefix_and_does_not_advance():
    # Real-data finding (smoke 11110019, Artin__exercise_10_4_7a): a naive line-slice can land mid
    # a `have h : ... := by` block with no sub-proof written yet — it elaborates without an ERROR
    # up to that line (nothing's wrong YET), but appending `sorry` does NOT close to a single
    # clean goal (Lean expects the `have`'s own tactic block, not a bare continuation).
    # Re-grounding on such a dangling boundary makes the model see a nonsensical "finish this"
    # prompt and it degenerates into prose. The agent must validate each candidate prefix
    # (elaborate + sorry) before committing to it; a rejected prefix must NOT replace the (safe,
    # still-empty) one.
    def respond(payload):
        # Always the same dangling completion: elaborates line-by-line with no ERROR at "have ... :=
        # by" itself, but the failure is reported one line later (a nested unsolved-goals error).
        return completion_response(
            "```lean4\ntheorem t : True := by\n  have h1 : True := by\n  WRONG\n```",
            completion_tokens=payload["max_tokens"],
        )

    def backend_respond(_thm, proof):
        if "WRONG" in proof:
            return RawVerification(success=False, output="test.lean:4:2: error: unsolved goals")
        return RawVerification(success=True, output="")

    client = VLLMClient(
        model="m", transport=ScriptedTransport(respond), meter=BudgetMeter(limit=10_000)
    )
    verifier = Verifier(ScriptedBackend(backend_respond))
    # The dangling prefix ("  have h1 : True := by") never validates as a clean single-goal state.
    agent = RegroundStepwiseAgent(
        client=client, verifier=verifier, template=WholeProofTemplate(), sample_max_tokens=10,
        max_rounds=3, elaborate=lambda _thm, _prefix: False,
    )

    state = agent.prove(THM)

    assert not state.solved
    assert state.stop_reason == STOP_MAX_ROUNDS
    # The frontier never advanced past the safe start ("") — every round re-grounds identically.
    assert state.budget["_stepwise_prefix"] == ""
    assert state.budget["_stepwise_depth"] == 0


def test_stepwise_agent_backs_off_past_a_dangling_cut_to_a_clean_ancestor():
    # Real-data finding (2026-07-04, Rudin__exercise_5_1 @ 32k): the naive single cut frequently
    # lands mid a multi-line combinator (`<;>`, `try { ... }`) — dangling — even though a SHORTER,
    # still-substantial prefix one line back is a perfectly clean re-grounding point. The agent must
    # back off to it rather than discarding all that verified progress as "never advances."
    def respond(payload):
        return completion_response(
            "```lean4\ntheorem t : True := by\n  have h1 : True := trivial\n  <;>\n  WRONG\n```",
            completion_tokens=payload["max_tokens"],
        )

    def backend_respond(_thm, proof):
        if "WRONG" in proof:
            return RawVerification(success=False, output="test.lean:5:2: error: unsolved goals")
        return RawVerification(success=True, output="")

    client = VLLMClient(
        model="m", transport=ScriptedTransport(respond), meter=BudgetMeter(limit=10_000)
    )
    verifier = Verifier(ScriptedBackend(backend_respond))
    # Only the backed-off (non-dangling) prefix validates; the naive `<;>`-ending cut does not.
    agent = RegroundStepwiseAgent(
        client=client, verifier=verifier, template=WholeProofTemplate(), sample_max_tokens=10,
        max_rounds=1, elaborate=lambda _thm, prefix: prefix.strip() == "have h1 : True := trivial",
    )

    state = agent.prove(THM)

    assert state.budget["_stepwise_prefix"].strip() == "have h1 : True := trivial"
    assert state.budget["_stepwise_depth"] == 1


def test_stepwise_agent_regrounds_across_rounds_then_solves():
    # Round 1 (fresh whole-proof prompt): the model proposes a full proof (header echoed, as a real
    # whole-proof model does) whose first tactic elaborates but whose second doesn't ("WRONG") ->
    # verified prefix = "intro n" (line 2 of the full text, header on line 1). Round 2 (continuation
    # prompt grounded on that prefix): the model echoes the WHOLE completed text again — header +
    # the carried prefix + its new closing tactic (the Format-I guard behavior).
    calls: list[dict] = []

    def respond(payload):
        calls.append(payload)
        is_cont = "intro n" in payload["prompt"]  # render_continuation embeds the verified prefix
        text = (
            "```lean4\ntheorem t : True := by\n  intro n\n  close_it\n```"
            if is_cont
            else "```lean4\ntheorem t : True := by\n  intro n\n  WRONG\n```"
        )
        return completion_response(text, completion_tokens=payload["max_tokens"])

    transport = ScriptedTransport(respond)
    client = VLLMClient(model="m", transport=transport, meter=BudgetMeter(limit=10_000))
    verifier = Verifier(_backend_closes_on("close_it"))
    agent = RegroundStepwiseAgent(
        client=client, verifier=verifier, template=WholeProofTemplate(), sample_max_tokens=10,
        elaborate=lambda _t, _p: True,
    )

    state = agent.prove(THM)

    assert state.solved
    assert state.stop_reason == STOP_SOLVED
    assert "close_it" in state.proof
    assert state.n_attempts == 2
    # Round 2's prompt is grounded on the verified prefix "intro n", never the drifted "WRONG".
    assert "intro n" in calls[1]["prompt"]
    assert "WRONG" not in calls[1]["prompt"]


def test_stepwise_agent_respects_budget_and_checkpoints(tmp_path):
    """Token spend never exceeds B; running out is a clean, checkpointed budget stop."""

    def respond(payload):
        # Never closes -> the agent keeps re-grounding/looping until the budget runs out.
        return completion_response(
            "```lean4\nintro n\nWRONG\n```", completion_tokens=payload["max_tokens"]
        )

    limit = 25
    transport = ScriptedTransport(respond)
    client = VLLMClient(model="m", transport=transport, meter=BudgetMeter(limit=limit))
    verifier = Verifier(_backend_closes_on("__never__"))
    agent = RegroundStepwiseAgent(
        client=client, verifier=verifier, template=WholeProofTemplate(), sample_max_tokens=10,
        elaborate=lambda _t, _p: True,
    )
    state_path = tmp_path / "cell.json"

    state = agent.prove(THM, state_path=state_path)

    assert not state.solved
    assert state.stop_reason == STOP_BUDGET
    assert state.budget["spent"] <= limit
    assert state_path.exists()  # checkpointed, so a requeue can resume


def test_stepwise_agent_resume_continues_from_the_checkpointed_frontier(tmp_path):
    """A resumed cell continues re-grounding from the checkpointed prefix, not from scratch."""
    path = tmp_path / "t.json"
    # Hand-craft a mid-loop checkpoint (rule 3: a requeue kills the process between rounds): one
    # failed attempt already reached the verified prefix "intro n" (depth 1), 30/100 tokens spent.
    prior = BudgetMeter(limit=100)
    prior.spend(30, label="reground")
    from atp.agents.state import AgentState, Attempt

    AgentState(
        theorem_name="t",
        done=False,
        attempts=[
            Attempt(index=0, kind="reground", proof="intro n\nWRONG", ok=False,
                    reason="compile_error", feedback="Failed at step 1: unsolved goals",
                    completion_tokens=30)
        ],
        budget={**prior.snapshot(), "_stepwise_prefix": "intro n", "_stepwise_depth": 1},
    ).save(path)

    calls: list[dict] = []

    def respond(payload):
        calls.append(payload)
        return completion_response("```lean4\nintro n\nclose_it\n```",
                                    completion_tokens=payload["max_tokens"])

    client = VLLMClient(
        model="m", transport=ScriptedTransport(respond), meter=BudgetMeter(limit=100)
    )
    verifier = Verifier(_backend_closes_on("close_it"))
    agent = RegroundStepwiseAgent(
        client=client, verifier=verifier, template=WholeProofTemplate(), sample_max_tokens=10,
        elaborate=lambda _t, _p: True,
    )

    state = agent.prove(THM, state_path=path)

    # The very next generation call is grounded on the CARRIED frontier, not a fresh cold start.
    assert "intro n" in calls[0]["prompt"]
    assert state.solved
    assert state.n_attempts == 2  # the carried attempt + the one new round
    assert agent.client.meter.spent == 30 + 10  # spend continued from 30, not reset
