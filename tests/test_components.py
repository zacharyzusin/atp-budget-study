"""Tests for the composable component framework + tactic-skeletons (Phase 1, Tasks 1.1/1.3).

Pure-Python, login-node fast: no GPU/Lean. Covers the framework contract (empty pipeline is a
no-op; components compose in order), the tactic-skeletons component (propose-only, schedule
cycling, bad-schedule validation), and the `build_components` wiring off the real config.
"""

from __future__ import annotations

import json

import pytest

from atp.agents import WholeProofAgent
from atp.agents.components import (
    Component,
    ComponentPipeline,
    Memory,
    PromptContext,
    Retrieval,
    Reviewer,
    ReviewVerdict,
    TacticSkeletons,
    build_components,
)
from atp.agents.components.memory import _MEMORY_PREFIX
from atp.agents.components.retrieval import _RETRIEVAL_PREFIX, load_premises
from atp.agents.components.reviewer import _parse_verdict
from atp.agents.components.skeletons import _HINT_PREFIX, available_schedules
from atp.agents.state import Attempt
from atp.budget import BudgetMeter
from atp.config import BASE_CONFIG, ExperimentConfig, load_config
from atp.lean.backends import Theorem
from atp.models import ScriptedTransport, VLLMClient, completion_response
from atp.models.templates import WholeProofTemplate

THM = Theorem(name="t", statement="theorem t : True")


def _ctx(
    kind: str = "propose", round_index: int = 0, history: tuple[Attempt, ...] = ()
) -> PromptContext:
    return PromptContext(theorem=THM, kind=kind, round_index=round_index, history=history)


def _fail(index: int, proof: str, feedback: str) -> Attempt:
    return Attempt(
        index=index, kind="propose", proof=proof, ok=False, reason="compile_error",
        feedback=feedback, completion_tokens=1,
    )


def _config(**components: dict) -> ExperimentConfig:
    """BASE_CONFIG with `agent.components.<name>` sub-dicts overridden."""
    data = load_config(BASE_CONFIG).model_dump(mode="json")
    data["agent"]["components"].update(components)
    return ExperimentConfig.model_validate(data)


def _skeletons(schedule: str = "default") -> TacticSkeletons:
    cfg = _config(tactic_skeletons={"enabled": True, "schedule": schedule})
    return TacticSkeletons.from_config(cfg.agent.components.tactic_skeletons)


# -- framework ----------------------------------------------------------------------------
def test_empty_pipeline_is_noop():
    pipe = ComponentPipeline()
    assert not pipe
    assert pipe.names == ()
    assert pipe.decorate_prompt("PROMPT", _ctx()) == "PROMPT"


def test_pipeline_composes_in_order():
    class Tag(Component):
        def __init__(self, tag: str) -> None:
            self.name = tag

        def decorate_prompt(self, prompt: str, ctx: PromptContext) -> str:
            return f"{prompt}+{self.name}"

    pipe = ComponentPipeline((Tag("a"), Tag("b")))
    assert pipe.names == ("a", "b")
    # Left-to-right threading: a then b.
    assert pipe.decorate_prompt("P", _ctx()) == "P+a+b"


def test_base_component_hook_is_identity():
    assert Component().decorate_prompt("X", _ctx()) == "X"


# -- tactic-skeletons component -----------------------------------------------------------
def test_skeletons_decorates_propose_only():
    skel = _skeletons()
    out = skel.decorate_prompt("PROMPT", _ctx(kind="propose"))
    assert out.startswith("PROMPT\n\n")
    assert _HINT_PREFIX in out
    # Refinement prompts are left untouched (keep the Lean-error signal clean).
    assert skel.decorate_prompt("PROMPT", _ctx(kind="refine")) == "PROMPT"


def test_skeletons_cycles_schedule_by_round():
    skel = _skeletons()
    n = len(skel.schedule)
    assert n > 1
    first = skel.decorate_prompt("P", _ctx(round_index=0))
    second = skel.decorate_prompt("P", _ctx(round_index=1))
    wrapped = skel.decorate_prompt("P", _ctx(round_index=n))
    assert first != second  # consecutive rounds get different hints
    assert first == wrapped  # schedule wraps modulo its length


def test_skeletons_unknown_schedule_raises():
    cfg = _config(tactic_skeletons={"enabled": True, "schedule": "does_not_exist"})
    with pytest.raises(ValueError, match="unknown tactic_skeletons schedule"):
        build_components(cfg)


def test_available_schedules_includes_default():
    assert "default" in available_schedules()


# -- build_components wiring ---------------------------------------------------------------
def test_build_components_empty_by_default():
    pipe = build_components(load_config(BASE_CONFIG))
    assert not pipe  # baseline: nothing enabled
    assert pipe.names == ()


def test_build_components_enables_skeletons():
    pipe = build_components(_config(tactic_skeletons={"enabled": True, "schedule": "default"}))
    assert pipe.names == ("tactic_skeletons",)
    assert isinstance(pipe.components[0], TacticSkeletons)


# -- memory component ----------------------------------------------------------------------
def _memory(max_items: int = 3) -> Memory:
    cfg = _config(memory={"enabled": True, "max_items": max_items})
    return Memory.from_config(cfg.agent.components.memory)


def test_memory_noop_without_failures():
    mem = _memory()
    # Round 0 (empty history) and a history of only-solved attempts both decorate nothing.
    assert mem.decorate_prompt("P", _ctx(history=())) == "P"
    solved = Attempt(index=0, kind="propose", proof="ok", ok=True, reason="ok", feedback="",
                     completion_tokens=1)
    assert mem.decorate_prompt("P", _ctx(history=(solved,))) == "P"


def test_memory_summarises_recent_failures_propose_only():
    hist = (_fail(0, "by simp", "simp made no progress"),
            _fail(1, "by ring", "ring failed: not a ring"))
    out = _memory().decorate_prompt("PROMPT", _ctx(kind="propose", history=hist))
    assert _MEMORY_PREFIX in out
    assert "by simp" in out and "ring failed" in out
    # Refinement keeps the immediate Lean error clean — memory stays out of it.
    refined = _memory().decorate_prompt("PROMPT", _ctx(kind="refine", history=hist))
    assert _MEMORY_PREFIX not in refined


def test_memory_caps_to_max_items_most_recent():
    hist = tuple(_fail(i, f"proof{i}", f"err{i}") for i in range(5))
    out = _memory(max_items=2).decorate_prompt("P", _ctx(history=hist))
    # Only the two most recent failures appear; older ones are dropped.
    assert "proof4" in out and "proof3" in out
    assert "proof0" not in out and "proof2" not in out


def test_build_components_order_is_memory_then_skeletons():
    pipe = build_components(
        _config(memory={"enabled": True}, tactic_skeletons={"enabled": True})
    )
    assert pipe.names == ("memory", "tactic_skeletons")


# -- reviewer component --------------------------------------------------------------------
@pytest.mark.parametrize(
    ("text", "accept"),
    [
        ("ACCEPT — looks complete", True),
        ("REJECT: uses sorry", False),
        ("accept, the proof is fine", True),
        ("This is wrong. REJECT.", False),
        ("REJECT first but mentions accept later", False),  # first explicit token wins
        ("no verdict at all", False),  # ambiguous → conservative reject
    ],
)
def test_parse_verdict(text, accept):
    assert _parse_verdict(text).accept is accept


def _reviewer_client(verdict_text: str, *, limit: int = 1000):
    """A VLLMClient whose scripted model always returns `verdict_text` (one critic call)."""
    seen: list[str] = []

    def respond(payload):
        seen.append(payload["prompt"])
        return completion_response(verdict_text, completion_tokens=payload["max_tokens"])

    client = VLLMClient(
        model="m", transport=ScriptedTransport(respond), meter=BudgetMeter(limit=limit)
    )
    return client, seen


def test_reviewer_calls_model_and_parses_verdict():
    reviewer = Reviewer.from_config(_config(reviewer={"enabled": True}).agent.components.reviewer)
    client, seen = _reviewer_client("ACCEPT — fine")
    verdict = reviewer.review(THM, "by simp", "simp failed", client)
    assert isinstance(verdict, ReviewVerdict) and verdict.accept is True
    assert "Candidate proof" in seen[0] and "by simp" in seen[0]  # critic saw the candidate
    assert client.meter.spent > 0  # the critic call cost budget


def test_reviewer_respects_max_tokens():
    reviewer = Reviewer.from_config(
        _config(reviewer={"enabled": True, "max_tokens": 7}).agent.components.reviewer
    )
    client, _ = _reviewer_client("REJECT")
    reviewer.review(THM, "by ring", "ring failed", client)
    assert client.meter.spent == 7  # scripted model spends exactly the clamp


def test_prompt_only_components_have_no_review_opinion():
    # Memory/skeletons must return None for the review hook (so the pipeline finds no reviewer).
    client, _ = _reviewer_client("ACCEPT")
    assert Memory(max_items=3).review(THM, "p", "f", client) is None
    assert _skeletons().review(THM, "p", "f", client) is None
    assert client.meter.spent == 0  # they never call the model


def test_build_components_enables_reviewer():
    pipe = build_components(_config(reviewer={"enabled": True}))
    assert pipe.names == ("reviewer",)
    assert isinstance(pipe.components[0], Reviewer)


def test_agent_reviewer_records_false_accept_and_feeds_critique():
    """End-to-end: every proof fails Lean; the critic always ACCEPTs (→ false accepts) and its
    critique reaches the refinement prompt; ProblemResult/metrics count the false accepts."""
    from atp.eval.metrics import reviewer_false_accept_rate
    from atp.eval.records import ProblemResult
    from atp.lean import RawVerification, ScriptedBackend, Verifier

    seen: list[str] = []

    def respond(payload):
        prompt = payload["prompt"]
        seen.append(prompt)
        if "proof reviewer" in prompt:  # the critic call
            return completion_response("ACCEPT looks good", completion_tokens=payload["max_tokens"])
        return completion_response("```lean4\nbad\n```", completion_tokens=payload["max_tokens"])

    backend = ScriptedBackend(lambda _t, _p: RawVerification(success=False, output="err"))
    client = VLLMClient(
        model="m", transport=ScriptedTransport(respond), meter=BudgetMeter(limit=200)
    )
    agent = WholeProofAgent(
        client=client,
        verifier=Verifier(backend),
        template=WholeProofTemplate(),
        max_refine=2,
        sample_max_tokens=10,
        components=build_components(_config(reviewer={"enabled": True, "max_tokens": 5})),
    )
    state = agent.prove(THM)

    # Every failed attempt was reviewed and (wrongly) accepted → all false accepts.
    reviewed = [a for a in state.attempts if a.review_accept is not None]
    assert reviewed and all(a.review_accept for a in reviewed)
    # The critique is threaded into refinement prompts.
    refinements = [p for p in seen if "Reviewer critique:" in p]
    assert refinements and all("ACCEPT looks good" in p for p in refinements)

    pr = ProblemResult.from_agent_state(state, seed=0, budget=200)
    assert pr.n_reviewed == len(reviewed)
    assert pr.n_review_false_accept == len(reviewed)
    far = reviewer_false_accept_rate([pr])
    assert far is not None and far["rate"] == 1.0


def test_reviewer_false_accept_rate_none_without_reviewer():
    from atp.eval.metrics import reviewer_false_accept_rate
    from atp.eval.records import ProblemResult

    pr = ProblemResult(
        problem_name="t", seed=0, budget=100, solved=False, stop_reason="budget_exhausted",
        tokens_to_solve=None, tokens_spent=100, n_attempts=2,
    )
    assert reviewer_false_accept_rate([pr]) is None  # reviewer never ran → metric omitted


# -- retrieval component -------------------------------------------------------------------
_CORPUS = [
    {"name": "Nat.add_comm", "decl": "theorem Nat.add_comm (n m : Nat) : n + m = m + n"},
    {"name": "Nat.mul_comm", "decl": "theorem Nat.mul_comm (n m : Nat) : n * m = m * n"},
    {"name": "List.length_append", "decl": "theorem List.length_append : (l1 ++ l2).length = ..."},
]


def _corpus_file(tmp_path, rows=_CORPUS) -> str:
    p = tmp_path / "premises.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return str(p)


def _retrieval(tmp_path, **over) -> Retrieval:
    opts = {"enabled": True, "backend": "bm25", "corpus": _corpus_file(tmp_path)}
    opts.update(over)
    return Retrieval.from_config(_config(retrieval=opts).agent.components.retrieval)


def test_load_premises_parses_and_skips_blanks(tmp_path):
    p = tmp_path / "c.jsonl"
    p.write_text('{"name": "A", "decl": "d"}\n\n{"name": "B"}\n')
    prem = load_premises(p)
    assert [x.name for x in prem] == ["A", "B"]
    assert prem[1].decl == ""  # missing decl defaults to empty


def test_load_premises_empty_raises(tmp_path):
    p = tmp_path / "empty.jsonl"
    p.write_text("\n  \n")
    with pytest.raises(ValueError, match="empty"):
        load_premises(p)


def test_retrieval_ranks_relevant_premise_first(tmp_path):
    ret = _retrieval(tmp_path, k=1)
    thm = Theorem(name="g", statement="theorem g (a b : Nat) : a + b = b + a")
    out = ret.decorate_prompt("PROMPT", PromptContext(theorem=thm, kind="propose", round_index=0))
    assert _RETRIEVAL_PREFIX in out
    assert "Nat.add_comm" in out  # the additive-commutativity goal retrieves add_comm, not mul_comm
    assert "Nat.mul_comm" not in out


def test_retrieval_propose_only(tmp_path):
    ret = _retrieval(tmp_path)
    thm = Theorem(name="g", statement="theorem g (a b : Nat) : a + b = b + a")
    refine_ctx = PromptContext(theorem=thm, kind="refine", round_index=0)
    assert ret.decorate_prompt("PROMPT", refine_ctx) == "PROMPT"


def test_retrieval_reprover_backend_deferred(tmp_path):
    with pytest.raises(NotImplementedError, match="reprover"):
        _retrieval(tmp_path, backend="reprover")


def test_retrieval_bm25_requires_corpus():
    cfg = _config(retrieval={"enabled": True, "backend": "bm25", "corpus": None})
    with pytest.raises(ValueError, match="requires `corpus`"):
        build_components(cfg)


def test_build_components_enables_retrieval_first(tmp_path):
    pipe = build_components(
        _config(
            retrieval={"enabled": True, "backend": "bm25", "corpus": _corpus_file(tmp_path)},
            memory={"enabled": True},
        )
    )
    assert pipe.names == ("retrieval", "memory")  # retrieval leads the prompt-side order


# -- agent integration: the prompt the model actually receives ----------------------------
def _captured_agent(components: ComponentPipeline):
    """A WholeProofAgent whose scripted transport records every prompt it is sent.

    The proof always fails (`bad`), so the loop runs a fresh proposal then refinements — letting us
    inspect both prompt kinds — until the small budget stops it.
    """
    from atp.budget import BudgetMeter
    from atp.lean import RawVerification, ScriptedBackend, Verifier
    from atp.models import ScriptedTransport, VLLMClient, completion_response
    from atp.models.templates import WholeProofTemplate

    seen: list[str] = []

    def respond(payload):
        seen.append(payload["prompt"])
        return completion_response("```lean4\nbad\n```", completion_tokens=payload["max_tokens"])

    backend = ScriptedBackend(lambda _t, _p: RawVerification(success=False, output="err"))
    client = VLLMClient(
        model="m", transport=ScriptedTransport(respond), meter=BudgetMeter(limit=40)
    )
    agent = WholeProofAgent(
        client=client,
        verifier=Verifier(backend),
        template=WholeProofTemplate(),
        max_refine=2,
        sample_max_tokens=10,
        components=components,
    )
    return agent, seen


def test_agent_baseline_prompts_carry_no_hint():
    agent, seen = _captured_agent(ComponentPipeline())
    agent.prove(THM)
    assert seen  # the loop made at least one model call
    assert all(_HINT_PREFIX not in p for p in seen)  # byte-identical baseline: no decoration


def test_agent_skeletons_decorate_only_fresh_proposals():
    agent, seen = _captured_agent(
        build_components(_config(tactic_skeletons={"enabled": True}))
    )
    agent.prove(THM)
    # The opening prompt of each round is a fresh proposal → it carries a hint. Refinement prompts
    # (they include the Lean error feedback block) must NOT.
    proposals = [p for p in seen if "error feedback" not in p.lower()]
    refinements = [p for p in seen if "error feedback" in p.lower()]
    assert proposals and all(_HINT_PREFIX in p for p in proposals)
    assert all(_HINT_PREFIX not in p for p in refinements)


def test_agent_memory_recalls_prior_round_failures():
    agent, seen = _captured_agent(build_components(_config(memory={"enabled": True})))
    agent.prove(THM)
    proposals = [p for p in seen if "error feedback" not in p.lower()]
    assert len(proposals) >= 2  # the small budget funds more than one fresh round
    # First fresh proposal has no history → no memory block; a later one recalls prior failures.
    assert _MEMORY_PREFIX not in proposals[0]
    assert any(_MEMORY_PREFIX in p for p in proposals[1:])
