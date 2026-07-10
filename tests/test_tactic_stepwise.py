"""Phase 7 Track 1 — Mode 4: true stepwise generation (one tactic per call).

Pure-core + integration tests (no GPU, no Lean): the model proposes exactly ONE tactic conditioned
on the TRUE current goal state (never a self-generated, possibly-drifted one); every tactic is
validated via `elaborate` before being committed, and the state only ever advances off an ACCEPTED
tactic. This is the strong exposure-bias test Mode 3 (whole-continuation re-grounding) cannot make:
Mode 3 re-grounds the state but then free-runs a WHOLE continuation, which can drift again.
"""

from __future__ import annotations

from atp.agents.state import STOP_BUDGET, STOP_MAX_ROUNDS, STOP_NO_PROGRESS
from atp.agents.tactic_stepwise import (
    BeamTacticStepwiseAgent,
    StepCheck,
    TacticStepwiseAgent,
    expand_node,
    take_tactic_step,
)
from atp.budget import BudgetMeter
from atp.lean import RawVerification, ScriptedBackend, Theorem, Verifier
from atp.models import ScriptedTransport, VLLMClient, completion_response
from atp.models.templates import TacticTemplate

THM = Theorem(name="t", statement="theorem t : True")


def test_take_tactic_step_returns_the_first_accepted_tactic():
    proposals = iter([["bad_tactic"], ["trivial"]])
    checks = {
        "bad_tactic": StepCheck(ok=False, closed=False),
        "trivial": StepCheck(ok=True, closed=True),
    }
    tactic, result = take_tactic_step(
        propose=lambda _s: next(proposals), check=lambda t: checks[t], state="", retries=4
    )
    assert tactic == "trivial"
    assert result.closed


def test_take_tactic_step_tries_every_candidate_from_one_completion_before_a_fresh_retry():
    # A single completion can yield SEVERAL candidate lines (a reasoning model's multi-step sketch);
    # take_tactic_step must try them all before consuming a fresh `propose` retry.
    calls = {"propose": 0}

    def propose(_s):
        calls["propose"] += 1
        return ["bad1", "bad2", "good"]

    def check(t):
        return StepCheck(ok=(t == "good"), closed=True)

    tactic, result = take_tactic_step(propose=propose, check=check, state="", retries=4)
    assert tactic == "good"
    assert result.closed
    assert calls["propose"] == 1  # never needed a second retry — all 3 candidates came from call 1


def test_take_tactic_step_is_stuck_when_every_candidate_is_rejected():
    tactic, result = take_tactic_step(
        propose=lambda _s: ["always_bad"],
        check=lambda _t: StepCheck(ok=False, closed=False),
        state="", retries=3,
    )
    assert tactic is None
    assert result is None


def test_take_tactic_step_never_advances_state_off_a_rejected_candidate():
    # The caller derives the NEXT state only from an accepted StepCheck — take_tactic_step itself
    # must not let a rejected candidate's (nonexistent) state leak in. Verify by checking `propose`
    # is always called with the SAME (never-advanced) state until a tactic is accepted.
    seen_states = []

    def propose(s):
        seen_states.append(s)
        return ["t1"] if len(seen_states) < 3 else ["t2"]

    def check(t):
        return StepCheck(ok=(t == "t2"), closed=True)

    tactic, result = take_tactic_step(propose=propose, check=check, state="GOAL", retries=5)
    assert tactic == "t2"
    assert seen_states == ["GOAL", "GOAL", "GOAL"]


def _client(respond):
    return VLLMClient(
        model="m", transport=ScriptedTransport(respond), meter=BudgetMeter(limit=10_000)
    )


def _verifier_always_ok():
    return Verifier(ScriptedBackend(lambda _t, _p: RawVerification(True, "")))


def test_agent_closes_in_one_step_when_the_first_tactic_solves_it():
    def respond(payload):
        return completion_response("trivial", completion_tokens=payload["max_tokens"])

    def elaborate(_thm, source):
        # Any source ending in the accepted tactic + sorry has zero remaining goals.
        if "trivial" in source:
            return {"errors": 0, "sorries": [], "infra_error": False}
        return {"errors": 0, "sorries": ["True"], "infra_error": False}

    def backend_respond(_thm, proof):
        return RawVerification(success=True, output="")

    agent = TacticStepwiseAgent(
        client=_client(respond), verifier=Verifier(ScriptedBackend(backend_respond)),
        template=TacticTemplate(), elaborate=elaborate, max_steps=5,
    )
    state = agent.prove(THM)
    assert state.solved
    assert "trivial" in state.proof


def test_agent_takes_multiple_steps_conditioned_on_the_true_state_each_time():
    # Step 1's goal state is "True"; the model's tactic must reference that EXACT text to be
    # accepted (a stand-in for "the model was given the true state, not a stale/drifted one").
    steps = iter(["intro n", "trivial"])

    def respond(payload):
        return completion_response(next(steps), completion_tokens=payload["max_tokens"])

    def elaborate(_thm, source):
        if "intro n" in source and "trivial" not in source:
            return {"errors": 0, "sorries": ["n : Nat"], "infra_error": False}  # advanced
        if "intro n" in source and "trivial" in source:
            return {"errors": 0, "sorries": [], "infra_error": False}  # closed
        return {"errors": 1, "sorries": [], "infra_error": False}  # anything else rejected

    agent = TacticStepwiseAgent(
        client=_client(respond), verifier=_verifier_always_ok(),
        template=TacticTemplate(), elaborate=elaborate, max_steps=5,
    )
    state = agent.prove(THM)
    assert state.solved
    assert "intro n" in state.proof
    assert "trivial" in state.proof


def test_agent_stops_stuck_when_every_retry_this_step_is_rejected():
    def respond(payload):
        return completion_response("nonsense", completion_tokens=payload["max_tokens"])

    def elaborate(_thm, _source):
        return {"errors": 1, "sorries": [], "infra_error": False}

    agent = TacticStepwiseAgent(
        client=_client(respond), verifier=_verifier_always_ok(),
        template=TacticTemplate(), elaborate=elaborate, max_steps=5, retries_per_step=3,
    )
    state = agent.prove(THM)
    assert not state.solved
    assert state.stop_reason == STOP_NO_PROGRESS


def test_agent_stops_max_rounds_if_it_never_closes_within_the_step_cap():
    calls = {"n": 0}

    def respond(payload):
        calls["n"] += 1
        return completion_response(f"step{calls['n']}", completion_tokens=payload["max_tokens"])

    def elaborate(_thm, _source):
        # every tactic is accepted but never closes the goal (endless progress, no finish)
        return {"errors": 0, "sorries": ["still open"], "infra_error": False}

    agent = TacticStepwiseAgent(
        client=_client(respond), verifier=_verifier_always_ok(),
        template=TacticTemplate(), elaborate=elaborate, max_steps=3,
    )
    state = agent.prove(THM)
    assert not state.solved
    assert state.stop_reason == STOP_MAX_ROUNDS
    assert calls["n"] == 3


def test_agent_respects_budget_and_checkpoints(tmp_path):
    def respond(payload):
        return completion_response("step", completion_tokens=payload["max_tokens"])

    def elaborate(_thm, _source):
        return {"errors": 0, "sorries": ["still open"], "infra_error": False}

    client = VLLMClient(
        model="m", transport=ScriptedTransport(respond), meter=BudgetMeter(limit=100)
    )
    agent = TacticStepwiseAgent(
        client=client, verifier=_verifier_always_ok(),
        template=TacticTemplate(), elaborate=elaborate, max_steps=50, sample_max_tokens=30,
    )
    path = tmp_path / "state.json"
    state = agent.prove(THM, state_path=path)
    assert state.stop_reason == STOP_BUDGET
    assert path.exists()


def test_agent_resume_continues_from_the_checkpointed_prefix(tmp_path):
    call_log = []

    def respond(payload):
        call_log.append(payload["prompt"])
        return completion_response("trivial", completion_tokens=payload["max_tokens"])

    def elaborate(_thm, source):
        if "trivial" in source:
            return {"errors": 0, "sorries": [], "infra_error": False}
        return {"errors": 0, "sorries": ["n : Nat"], "infra_error": False}

    path = tmp_path / "state.json"
    from atp.agents.state import AgentState

    # Hand-craft a checkpoint as if one step ("intro n") already committed.
    partial = AgentState(theorem_name="t", budget={
        "limit": 10_000, "spent": 20, "ledger": [],
        "_tactic_prefix": "  intro n", "_tactic_prev": ["intro n"], "_tactic_step": 1,
    })
    partial.save(path)

    agent = TacticStepwiseAgent(
        client=_client(respond), verifier=_verifier_always_ok(),
        template=TacticTemplate(), elaborate=elaborate, max_steps=5,
    )
    state = agent.prove(THM, state_path=path)
    assert state.solved
    assert "intro n" in state.proof and "trivial" in state.proof
    # The resumed prompt must carry the ALREADY-committed tactic as context.
    assert any("intro n" in p for p in call_log)


# --- BeamTacticStepwiseAgent: best-first-with-backtracking (the fair test for a search-native
# model, e.g. BFS-Prover — a single greedy walk under-tests it; see the class docstring). ----------


def test_expand_node_collects_up_to_beam_width_distinct_accepted_candidates():
    proposals = iter([["bad"], ["t1"], ["t2"], ["t3"]])

    def propose(_s):
        return next(proposals)

    def check(t):
        return StepCheck(ok=(t != "bad"), closed=False, state="next")

    accepted = expand_node(propose=propose, check=check, state="", beam_width=2, retries=4)
    assert [t for t, _ in accepted] == ["t1", "t2"]  # stops at beam_width; "t3" never consumed


def test_expand_node_dedupes_repeated_candidates_across_retries():
    proposals = iter([["t1"], ["t1"], ["t2"]])

    def propose(_s):
        return next(proposals)

    def check(_t):
        return StepCheck(ok=True, closed=False, state="s")

    accepted = expand_node(propose=propose, check=check, state="", beam_width=5, retries=3)
    assert [t for t, _ in accepted] == ["t1", "t2"]


def test_expand_node_returns_fewer_than_beam_width_if_retries_exhaust():
    def propose(_s):
        return ["bad"]

    def check(_t):
        return StepCheck(ok=False, closed=False)

    accepted = expand_node(propose=propose, check=check, state="", beam_width=3, retries=2)
    assert accepted == []


def test_beam_agent_rejects_a_stagnant_tactic_that_elaborates_but_doesnt_change_state():
    # Real bug found live 2026-07-05 (BFS-Prover-V1-7B): `rw [mul_comm]` elaborates cleanly every
    # time but cycles the SAME goal forever — a greedy walk burned its whole step budget
    # re-accepting it. A beam node must treat "no state change" as a rejection, not a valid step.
    def respond(payload):
        return completion_response("loop_tactic", completion_tokens=payload["max_tokens"])

    def elaborate(_thm, _source):
        return {"errors": 0, "sorries": ["GOAL"], "infra_error": False}  # never changes

    agent = BeamTacticStepwiseAgent(
        client=_client(respond), verifier=_verifier_always_ok(),
        template=TacticTemplate(), elaborate=elaborate,
        max_steps=3, beam_width=2, retries_per_step=2,
    )
    state = agent.prove(THM)
    assert not state.solved
    assert state.stop_reason == STOP_NO_PROGRESS


def test_beam_agent_backtracks_from_a_dead_end_to_a_second_beam_candidate():
    def respond(payload):
        prompt = payload["prompt"]
        if "DEAD" in prompt:
            return completion_response("dead_child", completion_tokens=payload["max_tokens"])
        if "GOOD" in prompt:
            return completion_response("close_tactic", completion_tokens=payload["max_tokens"])
        # Root: ONE completion yields TWO candidate lines — the beam's two siblings.
        return completion_response(
            "deadend_tactic\ngood_tactic", completion_tokens=payload["max_tokens"]
        )

    def elaborate(_thm, source):
        if "dead_child" in source:
            return {"errors": 1, "sorries": [], "infra_error": False}
        if "close_tactic" in source:
            return {"errors": 0, "sorries": [], "infra_error": False}
        if "good_tactic" in source:
            return {"errors": 0, "sorries": ["GOOD"], "infra_error": False}
        if "deadend_tactic" in source:
            return {"errors": 0, "sorries": ["DEAD"], "infra_error": False}
        return {"errors": 0, "sorries": ["ROOT"], "infra_error": False}

    agent = BeamTacticStepwiseAgent(
        client=_client(respond), verifier=_verifier_always_ok(),
        template=TacticTemplate(), elaborate=elaborate,
        max_steps=10, beam_width=2, retries_per_step=2,
    )
    state = agent.prove(THM)
    assert state.solved
    assert "good_tactic" in state.proof
    assert "close_tactic" in state.proof
    assert "deadend_tactic" not in state.proof  # the abandoned branch never makes the final proof


def test_beam_agent_respects_budget_and_checkpoints(tmp_path):
    def respond(payload):
        return completion_response("step", completion_tokens=payload["max_tokens"])

    def elaborate(_thm, source):
        # every distinct prefix advances to a genuinely new state — never stagnant, never closes —
        # so the search keeps expanding until the budget runs out.
        return {"errors": 0, "sorries": [f"state-{len(source)}"], "infra_error": False}

    client = VLLMClient(
        model="m", transport=ScriptedTransport(respond), meter=BudgetMeter(limit=100)
    )
    agent = BeamTacticStepwiseAgent(
        client=client, verifier=_verifier_always_ok(), template=TacticTemplate(),
        elaborate=elaborate, max_steps=50, beam_width=1, sample_max_tokens=30,
    )
    path = tmp_path / "state.json"
    state = agent.prove(THM, state_path=path)
    assert state.stop_reason == STOP_BUDGET
    assert path.exists()


def test_beam_agent_resume_continues_the_checkpointed_search_stack(tmp_path):
    def respond(payload):
        return completion_response("close_tactic", completion_tokens=payload["max_tokens"])

    def elaborate(_thm, source):
        if "close_tactic" in source:
            return {"errors": 0, "sorries": [], "infra_error": False}
        return {"errors": 0, "sorries": ["GOOD"], "infra_error": False}

    path = tmp_path / "state.json"
    from atp.agents.state import AgentState

    # Hand-craft a checkpoint as if the root already expanded to one child frame at state "GOOD".
    partial = AgentState(theorem_name="t", budget={
        "limit": 10_000, "spent": 10, "ledger": [],
        "_search_stack": [
            {"prefix": "  good_tactic", "state": "GOOD", "prev_tactics": ["good_tactic"],
             "pending": None},
        ],
        "_search_expansions": 1,
    })
    partial.save(path)

    agent = BeamTacticStepwiseAgent(
        client=_client(respond), verifier=_verifier_always_ok(), template=TacticTemplate(),
        elaborate=elaborate, max_steps=5, beam_width=2,
    )
    state = agent.prove(THM, state_path=path)
    assert state.solved
    assert "good_tactic" in state.proof and "close_tactic" in state.proof
