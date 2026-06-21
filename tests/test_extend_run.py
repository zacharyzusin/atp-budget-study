"""Smoke test for the Phase 5 extension runner (Task 5.2). No GPU/Lean/data — fully scripted.

Exercises run_extend's orchestration: seed a fresh run dir from a baseline 128k checkpoint, resume-
extend to a higher budget, write the extended ProblemResult, count per-seed extension solves, and
skip already-finished cells on requeue (rule 0.3). The agent-level extend semantics (prefix
preserved, solve paid past the old cap) are covered in test_agents.py; here we test the wiring.
"""

from __future__ import annotations

import types

import pytest

from atp.agents import WholeProofAgent
from atp.budget import BudgetMeter
from atp.config import BASE_CONFIG, load_config
from atp.data.problems import Problem
from atp.eval.extend_run import load_pilot_cells, run_extend
from atp.eval.records import ProblemResult
from atp.lean import RawVerification, ScriptedBackend, Theorem, Verifier
from atp.models import ScriptedTransport, VLLMClient, completion_response
from atp.models.templates import WholeProofTemplate

GOOD = "```lean4\ntheorem t : True := by\n  trivial\n```"
BAD = "```lean4\ntheorem t : True := by\n  bad_tactic\n```"


def _backend() -> ScriptedBackend:
    def respond(_thm, proof):
        if "trivial" in proof:
            return RawVerification(success=True, output="")
        return RawVerification(success=False, output="test.lean:2:2: error: unknown tactic")
    return ScriptedBackend(respond)


def _transport(*, always_solve: bool) -> ScriptedTransport:
    def respond(payload):
        text = GOOD if always_solve else BAD
        return completion_response(text, completion_tokens=payload["max_tokens"])
    return ScriptedTransport(respond)


def _make_baseline_checkpoint(baseline_dir, name="t", seed=0, limit=25):
    """Run an unsolved cell to budget exhaustion -> a logged checkpoint to extend from."""
    states = baseline_dir / "agent_states"
    states.mkdir(parents=True, exist_ok=True)
    client = VLLMClient(model="m", transport=_transport(always_solve=False),
                        meter=BudgetMeter(limit=limit))
    client.seed = seed
    agent = WholeProofAgent(client=client, verifier=Verifier(_backend()),
                            template=WholeProofTemplate(), max_refine=4, sample_max_tokens=10)
    path = states / f"{name}__seed{seed}.json"
    state = agent.prove(Theorem(name=name, statement="theorem t : True"), state_path=path)
    assert not state.solved
    return path


@pytest.fixture
def patched_dataset(monkeypatch):
    """Make run_extend resolve problem `t` without touching real benchmark files."""
    prob = Problem(name="t", statement="theorem t : True", benchmark="proofnet_sharp", split="test")
    monkeypatch.setattr("atp.eval.extend_run.load_novel_names", lambda cfg: ["t"])
    monkeypatch.setattr("atp.eval.extend_run.load_dataset",
                        lambda cfg, **kw: types.SimpleNamespace(problems=[prob]))
    return prob


def test_run_extend_records_extension_solve(tmp_path, patched_dataset):
    base = tmp_path / "baseline"
    _make_baseline_checkpoint(base, "t", 0, limit=25)
    cfg = load_config(BASE_CONFIG)

    out = run_extend(cfg, tmp_path / "pilot", base, [("t", 0)], new_budget=50,
                     transport=_transport(always_solve=True), backend=_backend())

    assert out["n_extension_solves"] == 1
    assert out["extension_solves_per_seed"] == {0: 1}
    assert out["n_ran"] == 1 and out["n_skipped"] == 0
    # the extended ProblemResult is on disk, solved, and paid for *past* the old 128k-style cap
    r = ProblemResult.load(tmp_path / "pilot" / "problems" / "t__seed0.json")
    assert r.solved and r.tokens_to_solve > 25 and r.tokens_to_solve <= 50
    # the baseline checkpoint was copied (preserved), never mutated in place
    assert (tmp_path / "pilot" / "agent_states" / "t__seed0.json").exists()


def test_run_extend_skips_finished_cells_on_requeue(tmp_path, patched_dataset):
    base = tmp_path / "baseline"
    _make_baseline_checkpoint(base, "t", 0, limit=25)
    cfg = load_config(BASE_CONFIG)
    args = dict(transport=_transport(always_solve=True), backend=_backend())

    first = run_extend(cfg, tmp_path / "pilot", base, [("t", 0)], new_budget=50, **args)
    assert first["n_ran"] == 1
    # second pass: the solved cell is already finished -> skipped, no re-extension
    second = run_extend(cfg, tmp_path / "pilot", base, [("t", 0)], new_budget=50, **args)
    assert second["n_ran"] == 0 and second["n_skipped"] == 1


def test_run_extend_missing_baseline_checkpoint_raises(tmp_path, patched_dataset):
    base = tmp_path / "baseline"
    (base / "agent_states").mkdir(parents=True)  # empty: no checkpoint for ("t", 0)
    cfg = load_config(BASE_CONFIG)
    with pytest.raises(FileNotFoundError):
        run_extend(cfg, tmp_path / "pilot", base, [("t", 0)], new_budget=50,
                   transport=_transport(always_solve=True), backend=_backend())


def test_run_extend_stays_unsolved_when_tail_dead(tmp_path, patched_dataset):
    base = tmp_path / "baseline"
    _make_baseline_checkpoint(base, "t", 0, limit=25)
    cfg = load_config(BASE_CONFIG)
    out = run_extend(cfg, tmp_path / "pilot", base, [("t", 0)], new_budget=50,
                     transport=_transport(always_solve=False), backend=_backend())
    assert out["n_extension_solves"] == 0 and out["extension_solves_per_seed"] == {}
    r = ProblemResult.load(tmp_path / "pilot" / "problems" / "t__seed0.json")
    assert not r.solved and r.tokens_spent == 50


def test_run_extend_concurrent_processes_all_cells(tmp_path, patched_dataset, monkeypatch):
    # exercise the real ThreadPoolExecutor path: 4 cells, n_workers=3, per-thread scripted backend.
    # all must be processed and the per-seed solve tally correct regardless of execution order.
    base = tmp_path / "baseline"
    monkeypatch.setattr("atp.eval.extend_run.load_dataset", lambda cfg, **kw: types.SimpleNamespace(
        problems=[Problem(name=n, statement="theorem t : True", benchmark="proofnet_sharp",
                          split="test") for n in ("t", "u", "v", "w")]))
    monkeypatch.setattr("atp.eval.extend_run.load_novel_names", lambda cfg: ["t", "u", "v", "w"])
    for n in ("t", "u", "v", "w"):
        _make_baseline_checkpoint(base, n, 0, limit=25)
    cfg = load_config(BASE_CONFIG)

    out = run_extend(cfg, tmp_path / "pilot", base, [("t", 0), ("u", 0), ("v", 0), ("w", 0)],
                     new_budget=50, transport=_transport(always_solve=True),
                     backend_factory=_backend, n_workers=3)
    assert out["n_workers"] == 3
    assert out["n_ran"] == 4 and out["n_extension_solves"] == 4
    assert out["extension_solves_per_seed"] == {0: 4}
    for n in ("t", "u", "v", "w"):
        assert (tmp_path / "pilot" / "problems" / f"{n}__seed0.json").exists()


def test_load_pilot_cells_reads_candidates(tmp_path):
    import json
    cand = tmp_path / "candidates.json"
    cand.write_text(json.dumps([
        {"model": "goedel", "benchmark": "proofnet_sharp",
         "pilot_cells": [{"problem_name": "A", "seed": 0}, {"problem_name": "B", "seed": 0}]},
    ]))
    cells = load_pilot_cells(cand, "goedel", "proofnet_sharp")
    assert cells == [("A", 0), ("B", 0)]
    with pytest.raises(KeyError):
        load_pilot_cells(cand, "deepseek", "proofnet_sharp")
