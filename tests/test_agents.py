"""Tests for the minimal whole-proof agent loop (Task 0.4).

Fast tests drive the full propose→verify→refine loop with a scripted transport (the "model") and a
scripted Lean backend (the "verifier"), so there's no GPU/Lean dependency. The scripted transport
respects the clamped `max_tokens` the budget meter hands it, exactly like a real vLLM server, so
budget accounting in these tests matches production. The real end-to-end solve is the lean+gpu+slow
test at the bottom (deferred with the Lean build).
"""

from __future__ import annotations

import pytest

from atp.agents import STOP_BUDGET, STOP_SOLVED, AgentState, WholeProofAgent
from atp.budget import BudgetMeter
from atp.lean import RawVerification, ScriptedBackend, Theorem, Verifier
from atp.models import ScriptedTransport, VLLMClient, completion_response
from atp.models.templates import WholeProofTemplate

THM = Theorem(name="t", statement="theorem t : True")

GOOD = "```lean4\ntheorem t : True := by\n  trivial\n```"
BAD = "```lean4\ntheorem t : True := by\n  bad_tactic\n```"


def _backend() -> ScriptedBackend:
    """A scripted Lean: a proof is accepted iff it contains `trivial`."""

    def respond(_thm, proof):
        if "trivial" in proof:
            return RawVerification(success=True, output="")
        return RawVerification(success=False, output="test.lean:2:2: error: unknown tactic")

    return ScriptedBackend(respond)


def _transport(*, solve_on_refine: bool = False, always_solve: bool = False) -> ScriptedTransport:
    """Scripted model. Returns a completion whose token cost respects the clamped max_tokens.

    - always_solve: every call returns a `trivial` proof.
    - solve_on_refine: proposals fail; refinements (prompt has 'error feedback') solve.
    """

    def respond(payload):
        is_refine = "error feedback" in payload["prompt"]
        solved = always_solve or (solve_on_refine and is_refine)
        text = GOOD if solved else BAD
        # A real server generates up to max_tokens; model that so spend == clamp.
        return completion_response(text, completion_tokens=payload["max_tokens"])

    return ScriptedTransport(respond)


def _agent(transport, meter, **kw) -> WholeProofAgent:
    client = VLLMClient(model="m", transport=transport, meter=meter)
    defaults = dict(max_refine=4, sample_max_tokens=10, max_rounds=64)
    defaults.update(kw)
    return WholeProofAgent(
        client=client, verifier=Verifier(_backend()), template=WholeProofTemplate(), **defaults
    )


def test_agent_solves_on_first_attempt():
    transport = _transport(always_solve=True)
    agent = _agent(transport, BudgetMeter(limit=1000))
    state = agent.prove(THM)
    assert state.solved
    assert state.stop_reason == STOP_SOLVED
    assert "trivial" in state.proof
    assert state.n_attempts == 1
    assert state.attempts[0].kind == "propose"


def test_agent_refines_then_solves():
    transport = _transport(solve_on_refine=True)
    agent = _agent(transport, BudgetMeter(limit=1000))
    state = agent.prove(THM)
    assert state.solved
    assert state.n_attempts == 2
    assert state.attempts[0].kind == "propose" and state.attempts[0].ok is False
    assert state.attempts[1].kind == "refine" and state.attempts[1].ok is True
    # the refinement prompt carried the previous proof + Lean error feedback
    assert "error feedback" in transport.calls[1]["prompt"]
    assert "bad_tactic" in transport.calls[1]["prompt"]


def test_agent_respects_budget():
    """Token spend never exceeds B; running out is a clean budget stop, not a crash."""
    limit = 25
    transport = _transport()  # never solves -> loops until budget runs out
    meter = BudgetMeter(limit=limit)
    agent = _agent(transport, meter, sample_max_tokens=10)
    state = agent.prove(THM)
    assert state.stop_reason == STOP_BUDGET
    assert meter.spent == limit  # exactly exhausted, never over
    assert state.budget["spent"] <= limit
    assert meter.exhausted


def test_agent_persists_state_each_iteration(tmp_path):
    path = tmp_path / "t.json"
    transport = _transport(solve_on_refine=True)
    agent = _agent(transport, BudgetMeter(limit=1000))
    agent.prove(THM, state_path=path)
    assert path.exists()
    reloaded = AgentState.load(path)
    assert reloaded.solved
    assert reloaded.n_attempts == 2


def test_agent_state_resume_skips_solved_work(tmp_path):
    """A resumed *solved* problem returns immediately with no new generation."""
    path = tmp_path / "t.json"
    agent1 = _agent(_transport(always_solve=True), BudgetMeter(limit=1000))
    agent1.prove(THM, state_path=path)

    # New process: fresh transport (call counter at zero) reading the same checkpoint.
    transport2 = _transport(always_solve=True)
    agent2 = _agent(transport2, BudgetMeter(limit=1000))
    state = agent2.prove(THM, state_path=path)
    assert state.solved
    assert transport2.calls == []  # work was not redone


def test_load_empty_checkpoint_returns_none(tmp_path):
    """A zero-byte/whitespace checkpoint (preempt-killed mid-write) loads as no-state, not a crash.

    Regression: a timeout kill left empty agent_state files; resume then died deterministically on
    `json.loads("")` every requeue, stranding those cells. load() must treat them as "start fresh".
    """
    empty = tmp_path / "empty.json"
    empty.write_text("")
    assert AgentState.load(empty) is None
    blank = tmp_path / "blank.json"
    blank.write_text("   \n")
    assert AgentState.load(blank) is None


def test_load_corrupt_checkpoint_returns_none(tmp_path):
    """A truncated/garbage checkpoint loads as no-state rather than raising."""
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text('{"theorem_name": "t", "attempts": [')  # truncated JSON
    assert AgentState.load(corrupt) is None


def test_agent_resume_continues_unsolved_with_carried_budget(tmp_path):
    """Resuming an unfinished checkpoint restores the spend and continues from there."""
    path = tmp_path / "t.json"
    # Hand-craft a mid-loop checkpoint: one failed attempt, 30 tokens already spent of 100.
    prior = BudgetMeter(limit=100)
    prior.spend(30, label="propose")
    AgentState(
        theorem_name="t",
        done=False,
        attempts=[],
        budget=prior.snapshot(),
    ).save(path)

    # A fresh process picks it up; the model now solves on the first proposal.
    transport = _transport(always_solve=True)
    agent = _agent(transport, BudgetMeter(limit=100), sample_max_tokens=10)
    state = agent.prove(THM, state_path=path)

    assert state.solved
    # Budget continued from 30 (not reset): 30 already spent + 10 for the solving attempt.
    assert agent.client.meter.spent == 40
    assert state.budget["spent"] == 40


# --------------------------------------------------------------------------------------
# Phase 5: reclaim-and-reinvest extension (resume a budget-exhausted checkpoint, raise the cap).
# --------------------------------------------------------------------------------------


def _exhausted_checkpoint(tmp_path, limit=25):
    """Run an unsolved cell to budget exhaustion and return (state_path, logged_state)."""
    path = tmp_path / "t.json"
    agent = _agent(_transport(), BudgetMeter(limit=limit), sample_max_tokens=10)
    state = agent.prove(THM, state_path=path)
    assert state.stop_reason == STOP_BUDGET and not state.solved
    return path, state


def test_extend_preserves_prefix_and_solves_in_extension(tmp_path):
    # an unsolved 25-token checkpoint, then extended to 50 with a model that now solves: the new
    # solve must spend > old limit (it came from the extension), and the logged prefix is intact.
    path, before = _exhausted_checkpoint(tmp_path, limit=25)
    prefix = [(a.kind, a.proof, a.completion_tokens) for a in before.attempts]

    agent = _agent(_transport(always_solve=True), BudgetMeter(limit=25), sample_max_tokens=10)
    after = agent.extend(THM, path, new_limit=50)

    assert after.solved
    assert after.budget["spent"] > 25  # the solve was paid for past the old cap
    assert after.budget["spent"] <= 50  # never overran the new cap
    # Solves_reinvest ⊇ Solves_uniform by construction: every logged attempt is preserved, in order.
    assert [(a.kind, a.proof, a.completion_tokens) for a in after.attempts[: len(prefix)]] == prefix
    assert after.n_attempts > before.n_attempts  # extension only *added* attempts


def test_extend_solved_checkpoint_is_unchanged(tmp_path):
    # a cell solved within the old budget short-circuits: no new generation, identical state.
    path = tmp_path / "t.json"
    _agent(_transport(always_solve=True), BudgetMeter(limit=1000)).prove(THM, state_path=path)
    solved_before = AgentState.load(path)

    transport = _transport(always_solve=True)
    after = _agent(transport, BudgetMeter(limit=1000)).extend(THM, path, new_limit=500_000)
    assert after.solved and transport.calls == []  # work not redone
    assert after.n_attempts == solved_before.n_attempts


def test_extend_rejects_lower_budget(tmp_path):
    path, _ = _exhausted_checkpoint(tmp_path, limit=25)
    agent = _agent(_transport(), BudgetMeter(limit=25))
    with pytest.raises(ValueError, match="< checkpoint limit"):
        agent.extend(THM, path, new_limit=10)


def test_extend_missing_checkpoint_raises(tmp_path):
    agent = _agent(_transport(), BudgetMeter(limit=25))
    with pytest.raises(FileNotFoundError):
        agent.extend(THM, tmp_path / "nope.json", new_limit=50)


def test_extend_stays_unsolved_when_tail_is_dead(tmp_path):
    # the saturation case: extending a still-failing cell just spends the extra budget and stops
    # cleanly at the new cap (a per-cell "no extension solve" — the honest null of the pilot gate).
    path, _ = _exhausted_checkpoint(tmp_path, limit=25)
    agent = _agent(_transport(), BudgetMeter(limit=25), sample_max_tokens=10)
    after = agent.extend(THM, path, new_limit=50)
    assert not after.solved
    assert after.stop_reason == STOP_BUDGET
    assert after.budget["spent"] == 50  # the reclaimed budget was fully spent, no solve


def test_from_config_wires_refinement_policy():
    from atp.config import BASE_CONFIG, load_config

    cfg = load_config(BASE_CONFIG)
    client = VLLMClient(model="m", transport=_transport(), meter=BudgetMeter(limit=10))
    agent = WholeProofAgent.from_config(cfg, client, Verifier(_backend()))
    assert agent.max_refine == cfg.agent.refinement.max_iters
    assert agent.refine_enabled == cfg.agent.refinement.enabled
    assert agent.sample_max_tokens == cfg.model.max_model_len // 2
    assert agent.max_rounds == cfg.agent.max_rounds


def test_from_config_wires_max_rounds_override():
    """`agent.max_rounds` (added for pass@N calibration cells that need an exact sample count
    independent of the token budget) must actually reach the agent, not just validate."""
    from atp.config import BASE_CONFIG, load_config

    cfg = load_config(BASE_CONFIG)
    assert cfg.agent.max_rounds == 64  # the documented default, unchanged for every existing config
    cfg2 = cfg.model_copy(update={"agent": cfg.agent.model_copy(update={"max_rounds": 32})})
    client = VLLMClient(model="m", transport=_transport(), meter=BudgetMeter(limit=10))
    agent = WholeProofAgent.from_config(cfg2, client, Verifier(_backend()))
    assert agent.max_rounds == 32


def test_from_config_sample_max_tokens_override():
    """`model.sample_max_tokens` (added for calibration cells that want more of the model's native
    context spent on generation than the default max_model_len//2 refinement-loop heuristic)."""
    from atp.config import BASE_CONFIG, load_config

    cfg = load_config(BASE_CONFIG)
    assert (
        cfg.model.sample_max_tokens is None
    )  # unset by default — every existing config unaffected
    client = VLLMClient(model="m", transport=_transport(), meter=BudgetMeter(limit=10))
    agent_default = WholeProofAgent.from_config(cfg, client, Verifier(_backend()))
    assert agent_default.sample_max_tokens == cfg.model.max_model_len // 2

    cfg2 = cfg.model_copy(
        update={"model": cfg.model.model_copy(update={"sample_max_tokens": 30000})}
    )
    agent_override = WholeProofAgent.from_config(cfg2, client, Verifier(_backend()))
    assert agent_override.sample_max_tokens == 30000


def test_from_config_resolves_the_configured_prompt_template():
    """CRITICAL REGRESSION (found live 2026-07-06 — see PROGRESS.md/DECISIONS.md that date):
    `WholeProofAgent.from_config` used to hardcode `template=WholeProofTemplate()`, ignoring
    `config.model.prompt_template` entirely — `template_from_config` existed but was dead code,
    never
    called here. Every model whose config specifies a DIFFERENT template (DeepSeekV15Template,
    GoedelSFTTemplate, ...) was silently run under WholeProofTemplate's chat/proof-plan prompt
    instead
    of its own validated format. This must never regress: the agent's resolved template has to match
    what the config actually asks for, for a genuinely non-default case.
    """
    from atp.config import load_config
    from atp.models.templates import DeepSeekV15Template, GoedelSFTTemplate, WholeProofTemplate

    cfg = load_config("configs/deepseek_v15_base_minif2f.yaml")
    assert cfg.model.prompt_template == "deepseek_v15"  # sanity: this config IS non-default
    client = VLLMClient(model="m", transport=_transport(), meter=BudgetMeter(limit=10))
    agent = WholeProofAgent.from_config(cfg, client, Verifier(_backend()))
    assert isinstance(agent.template, DeepSeekV15Template)
    assert not isinstance(agent.template, WholeProofTemplate)

    cfg2 = load_config("configs/goedel_sft_minif2f.yaml")
    assert cfg2.model.prompt_template == "goedel_sft"
    agent2 = WholeProofAgent.from_config(cfg2, client, Verifier(_backend()))
    assert isinstance(agent2.template, GoedelSFTTemplate)


def test_from_config_regression_goedel_v2_and_deepseek_v2_still_resolve_whole_proof_template():
    """Regression check for the fix above: Goedel-Prover-V2 (base.yaml) and DeepSeek-Prover-V2-7B
    (deepseek_minif2f_baseline.yaml / deepseek_proofnet_baseline.yaml) are the two models whose
    OFFICIAL prompt format IS textually WholeProofTemplate's (by design, documented in their own
    config comments) — they were unaffected by the wiring bug (they happened to want the hardcoded
    template anyway) and MUST STILL resolve to WholeProofTemplate after the fix, not silently break.
    This is load-bearing for Phases 1-7, which used these two models as the headline comparison —
    if either ever specified a non-default prompt_template upstream of Phase 8, this test surfaces
    it
    now rather than leaving it undiscovered.
    """
    from atp.config import BASE_CONFIG, load_config
    from atp.models.templates import WholeProofTemplate

    client = VLLMClient(model="m", transport=_transport(), meter=BudgetMeter(limit=10))

    goedel_v2_cfg = load_config(BASE_CONFIG)
    assert goedel_v2_cfg.model.prompt_template == "whole_proof"
    goedel_v2_agent = WholeProofAgent.from_config(goedel_v2_cfg, client, Verifier(_backend()))
    assert isinstance(goedel_v2_agent.template, WholeProofTemplate)

    for path in [
        "configs/deepseek_minif2f_baseline.yaml",
        "configs/deepseek_proofnet_baseline.yaml",
    ]:
        deepseek_v2_cfg = load_config(path)
        assert deepseek_v2_cfg.model.prompt_template == "whole_proof", (
            f"{path}: expected whole_proof (this model's own documented official format) — if this "
            "ever changes, the fix above would silently change DeepSeek-V2's actual prompt too"
        )
        deepseek_v2_agent = WholeProofAgent.from_config(
            deepseek_v2_cfg, client, Verifier(_backend())
        )
        assert isinstance(deepseek_v2_agent.template, WholeProofTemplate)


# --------------------------------------------------------------------------------------
# Real end-to-end solve (deferred): needs a running vLLM server + built Lean cache.
# --------------------------------------------------------------------------------------
@pytest.mark.lean
@pytest.mark.gpu
@pytest.mark.slow
def test_agent_solves_trivial():
    pytest.importorskip("lean_dojo", reason="real Lean backend deferred (compute-node hold)")
    pytest.skip("end-to-end solve lands with the vLLM server + lean-cache build (deferred).")
