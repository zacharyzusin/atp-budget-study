"""Tests for the eval layer (Task 0.6): pass@B metric, manifest completeness, restartable sweep.

All mocked — no GPU/Lean. The sweep is driven by a fake solve_fn returning canned AgentStates.
"""

from __future__ import annotations

import json

import pytest

from atp.agents.state import STOP_BUDGET, STOP_SOLVED, AgentState
from atp.budget import BudgetMeter
from atp.config import BASE_CONFIG, load_config
from atp.data import Dataset
from atp.data.manifest import DatasetManifest
from atp.data.problems import Problem
from atp.eval import (
    REQUIRED_KEYS,
    ProblemResult,
    effective_accuracy,
    pass_at_b,
    run_sweep,
    summarize,
    tokens_to_first_proof,
)


def _result(name, seed, *, solved, tts=None, spent=0, budget=1000):
    return ProblemResult(
        problem_name=name,
        seed=seed,
        budget=budget,
        solved=solved,
        stop_reason=STOP_SOLVED if solved else STOP_BUDGET,
        tokens_to_solve=tts,
        tokens_spent=spent,
        n_attempts=1,
    )


# -- metrics ---------------------------------------------------------------------------
def test_pass_at_b_metric():
    # 2 problems × 2 seeds. p_a solved at 100 tokens; p_b unsolved.
    results = [
        _result("p_a", 0, solved=True, tts=100, spent=100),
        _result("p_b", 0, solved=False, spent=1000),
        _result("p_a", 1, solved=True, tts=400, spent=400),
        _result("p_b", 1, solved=False, spent=1000),
    ]
    curve = {p.budget: p for p in pass_at_b(results, [50, 200, 1000])}
    # B=50: neither seed solved p_a within 50 -> 0/2 both seeds -> mean 0
    assert curve[50].mean == 0.0
    # B=200: seed0 has p_a within 200 (1/2=0.5), seed1 p_a needs 400 (0/2=0.0) -> mean 0.25
    assert curve[200].mean == pytest.approx(0.25)
    assert curve[200].n_seeds == 2 and curve[200].n_problems == 2
    assert curve[200].std == pytest.approx(0.353553, abs=1e-4)  # stdev([0.5, 0.0])
    # B=1000: both seeds solve p_a (0.5 each) -> mean 0.5
    assert curve[1000].mean == pytest.approx(0.5)


def test_solved_within_boundary():
    r = _result("p", 0, solved=True, tts=100)
    assert r.solved_within(100) and not r.solved_within(99)
    assert not _result("p", 0, solved=False).solved_within(10**9)


def test_tokens_to_first_proof():
    results = [
        _result("a", 0, solved=True, tts=100),
        _result("b", 0, solved=True, tts=300),
        _result("c", 0, solved=False),
    ]
    t = tokens_to_first_proof(results)
    assert t["n_solved"] == 2
    assert t["mean"] == pytest.approx(200.0)
    assert t["median"] == pytest.approx(200.0)


def test_effective_accuracy_discounts_false_accepts():
    results = [_result(f"p{i}", 0, solved=True, tts=10) for i in range(4)]
    assert effective_accuracy(results, 1000)["mean"] == pytest.approx(1.0)
    discounted = effective_accuracy(results, 1000, false_accepts_per_seed=1)
    assert discounted["mean"] == pytest.approx(0.75)


# -- sweep harness ---------------------------------------------------------------------
def _dataset(names):
    problems = [
        Problem(name=n, statement=f"theorem {n} : True", benchmark="minif2f", split="valid")
        for n in names
    ]
    manifest = DatasetManifest(benchmark="minif2f", split="valid", counts={"returned": len(names)})
    return Dataset(problems=problems, manifest=manifest)


def _state(name, *, solved, spent):
    s = AgentState(theorem_name=name)
    s.budget = BudgetMeter(limit=1000, spent=spent).snapshot()
    s.done = True
    s.stop_reason = STOP_SOLVED if solved else STOP_BUDGET
    s.attempts = []
    if solved:
        s.proof = "by trivial"
    return s


def test_run_sweep_writes_cells_metrics_and_manifest(tmp_path):
    cfg = load_config(BASE_CONFIG)
    ds = _dataset(["p_a", "p_b"])

    def solve_fn(problem, seed, budget):
        # p_a solves at 500 tokens; p_b never solves.
        is_a = problem.name == "p_a"
        return _state(problem.name, solved=is_a, spent=500 if is_a else budget)

    run_dir = tmp_path / "run"
    res = run_sweep(cfg, ds, solve_fn, run_dir=run_dir, seeds=[0, 1])
    # 2 problems × 2 seeds = 4 cells written
    assert res.n_ran == 4 and res.n_skipped == 0
    assert len(list((run_dir / "problems").glob("*.json"))) == 4
    assert (run_dir / "metrics.json").exists()
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    for k in REQUIRED_KEYS:
        assert k in manifest, f"manifest missing {k}"
    assert manifest["seeds"] == [0, 1]
    assert manifest["lean"]["mathlib_commit"]  # Goedel-pin provenance recorded


def test_manifest_completeness(tmp_path):
    cfg = load_config(BASE_CONFIG)
    ds = _dataset(["only"])
    solve = lambda p, s, b: _state(p.name, solved=True, spent=10)  # noqa: E731
    res = run_sweep(cfg, ds, solve, run_dir=tmp_path / "r", seeds=[0])
    assert set(REQUIRED_KEYS).issubset(res.manifest.keys())
    assert res.manifest["config_hash"]
    assert res.manifest["dataset"]["benchmark"] == "minif2f"


def test_run_sweep_is_restartable(tmp_path):
    cfg = load_config(BASE_CONFIG)
    ds = _dataset(["p_a", "p_b"])
    run_dir = tmp_path / "run"
    solve = lambda p, s, b: _state(p.name, solved=True, spent=10)  # noqa: E731
    run_sweep(cfg, ds, solve, run_dir=run_dir, seeds=[0])

    def exploding_solve(problem, seed, budget):
        raise AssertionError("solve_fn must not be called for already-completed cells")

    res2 = run_sweep(cfg, ds, exploding_solve, run_dir=run_dir, seeds=[0], resume=True)
    assert res2.n_ran == 0 and res2.n_skipped == 2  # all cells resumed, nothing recomputed


def test_summarize_shape():
    results = [_result("a", 0, solved=True, tts=100), _result("b", 0, solved=False)]
    s = summarize(results, [50, 200])
    assert s["n_cells"] == 2
    assert [p["budget"] for p in s["pass_at_b"]] == [50, 200]
    assert "tokens_to_first_proof" in s and "effective_accuracy" in s


# -- full real assembly, mocked transport + backend (integration) ----------------------
def test_run_eval_end_to_end_mocked(tmp_path):
    """Exercise the production wiring (client→agent→verifier→sweep→metrics→manifest→plot)
    end to end with a scripted vLLM transport + scripted Lean backend — no GPU/Lean."""
    from atp.lean import RawVerification, ScriptedBackend
    from atp.models import ScriptedTransport, completion_response

    # tiny miniF2F fixture
    root = tmp_path / "miniF2F"
    (root / "formal").mkdir(parents=True)
    (root / "formal" / "valid.lean").write_text(
        "import Mathlib\n\nopen Nat\n\n"
        "theorem t_a : True := sorry\n\ntheorem t_b : True := sorry\n"
    )
    cfg = load_config(BASE_CONFIG)
    data = cfg.data.model_copy(
        update={"minif2f_dir": str(root), "split": "valid", "exclude_unprovable": False}
    )
    cfg = cfg.model_copy(update={"data": data})

    # Model always emits a `trivial` proof (cheap: 50 tokens); backend accepts proofs with `trivial`
    transport = ScriptedTransport(
        lambda payload: completion_response("```lean4\ntheorem t : True := by\n  trivial\n```", 50)
    )
    backend = ScriptedBackend(
        lambda _t, proof: RawVerification(success="trivial" in proof, output="")
    )

    from atp.eval.run import run_eval

    result = run_eval(cfg, tmp_path / "run", transport=transport, backend=backend)
    # 2 problems × 3 seeds (base config) = 6 cells; all solve cheaply → pass@B == 1 for every B
    assert result.n_ran == 6
    curve = {p["budget"]: p for p in result.metrics["pass_at_b"]}
    for b in cfg.budget.values:
        assert curve[b]["mean"] == pytest.approx(1.0)
    assert (result.run_dir / "run_manifest.json").exists()
    assert (result.run_dir / "pass_at_b.png").exists()  # plot rendered
    assert result.manifest["model"]["name"] == cfg.model.name
