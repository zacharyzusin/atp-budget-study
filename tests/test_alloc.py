"""Tests for Phase 4 allocation (Tasks 4.1–4.2). All CPU, no GPU/Lean.

The §0 enabling identity is load-bearing for the entire study, so it is tested three ways: against
`ProblemResult.solved_within` (synthetic), against the logged `solved` flag at b=128k (real cells),
and at intermediate budgets. Plus the policy invariants: uniform reproduces logged pass@B exactly,
oracle ≥ uniform always, budgets respect Σb_i ≤ T and b_i ≤ BMAX.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from atp.alloc.extract import load_run
from atp.alloc.policies import (
    BMAX,
    oracle_min_T_to_match,
    oracle_solved,
    solve_cost,
    uniform_solved,
)
from atp.eval.metrics import pass_at_b
from atp.eval.records import ProblemResult

ROOT = Path(__file__).resolve().parents[1]
PROOFNET = ROOT / "results" / "proofnet_baseline"


def _cell(name: str, seed: int, solved: bool, tts: int | None) -> ProblemResult:
    return ProblemResult(
        problem_name=name, seed=seed, budget=BMAX, solved=solved,
        stop_reason="solved" if solved else "budget_exhausted",
        tokens_to_solve=tts, tokens_spent=tts if solved else BMAX, n_attempts=1,
        benchmark="t", split="test",
    )


# ---- §0 identity ---------------------------------------------------------------------------------

def test_solve_cost_matches_solved_within():
    # solve_cost is the §0 identity as a number: (cost <= b) must equal solved_within(b) for all b.
    cells = [_cell("a", 0, True, 500), _cell("b", 0, True, 30_000),
             _cell("c", 0, False, None), _cell("d", 0, True, BMAX)]
    for r in cells:
        cost = solve_cost(r)
        for b in (0, 499, 500, 8000, 30_000, BMAX, BMAX + 1):
            assert (cost <= b) == r.solved_within(b), (r.problem_name, b)


def test_unsolved_cost_is_inf():
    assert solve_cost(_cell("x", 0, False, None)) == math.inf
    # a (hypothetical) solve recorded above the cap is not realizable within BMAX -> inf
    assert solve_cost(_cell("y", 0, True, BMAX + 1)) == math.inf


@pytest.mark.skipif(not PROOFNET.exists(), reason="baseline run not on disk")
def test_solved_identity_on_real_cells():
    # On real logged cells: cost<=128k must equal the logged `solved` flag, and the §0 identity must
    # reproduce solve/no-solve at a couple of intermediate budgets too.
    tbl = load_run(PROOFNET, "goedel", "proofnet_sharp")
    for r in tbl.results:
        assert (solve_cost(r) <= BMAX) == r.solved
        for b in (2000, 8000, 32_000):
            assert r.solved_within(b) == (r.solved and r.tokens_to_solve is not None
                                          and r.tokens_to_solve <= b)


# ---- policy invariants ---------------------------------------------------------------------------

def test_uniform_reproduces_logged_pass_at_b_real():
    # The load-bearing calibration: uniform at T = N*b solves exactly pass@b * N cells.
    if not PROOFNET.exists():
        pytest.skip("baseline run not on disk")
    tbl = load_run(PROOFNET, "goedel", "proofnet_sharp")
    costs = tbl.costs
    n = tbl.n_cells
    for b in (2000, 8000, 32_000, 128_000):
        uni = uniform_solved(costs, n * b)
        # logged pass@b (mean over seeds of solved fraction) * n_cells, both count the same cells
        curve = {p.budget: p for p in pass_at_b(tbl.results, [b])}
        logged = round(curve[b].mean * n)
        assert uni == logged, (b, uni, logged)


def test_uniform_reproduces_pass_at_b_synthetic():
    costs = [100.0, 5000.0, 50_000.0, math.inf]  # 4 cells, one unsolvable
    # at T = 4 * 8000 -> b=8000 -> cells with cost<=8000 = {100, 5000} = 2
    assert uniform_solved(costs, 4 * 8000) == 2
    # at T = 4 * 60000 -> b=60000 -> {100, 5000, 50000} = 3
    assert uniform_solved(costs, 4 * 60_000) == 3


def test_oracle_ge_uniform_everywhere():
    costs = [100.0, 5000.0, 50_000.0, 120_000.0, math.inf, math.inf]
    n = len(costs)
    for mult in (1000, 4000, 8000, 32_000, 128_000):
        T = n * mult
        assert oracle_solved(costs, T) >= uniform_solved(costs, T), mult


def test_oracle_knapsack_cheapest_first():
    costs = [100.0, 5000.0, 50_000.0, math.inf]
    assert oracle_solved(costs, 0) == 0
    assert oracle_solved(costs, 100) == 1
    assert oracle_solved(costs, 5100) == 2          # 100 + 5000
    assert oracle_solved(costs, 55_099) == 2        # can't afford the 50k yet
    assert oracle_solved(costs, 55_100) == 3        # 100 + 5000 + 50000
    assert oracle_solved(costs, 10 ** 12) == 3      # never funds the inf cell


def test_oracle_min_T_to_match():
    costs = [100.0, 5000.0, 50_000.0, math.inf]
    assert oracle_min_T_to_match(costs, 0) == 0.0
    assert oracle_min_T_to_match(costs, 2) == 5100.0
    assert oracle_min_T_to_match(costs, 3) == 55_100.0
    assert oracle_min_T_to_match(costs, 4) == math.inf  # only 3 solvable


def test_oracle_respects_total_budget():
    # The funded set's summed cost never exceeds T (knapsack invariant), for random-ish costs.
    costs = [float(c) for c in (300, 1200, 9000, 9000, 40_000, 90_000, 127_000)]
    for T in (0, 1000, 10_000, 60_000, 200_000, 500_000):
        k = oracle_solved(costs, T)
        spent = sum(sorted(costs)[:k])
        assert spent <= T, (T, k, spent)


def test_bmax_cap_on_uniform():
    # When T/N exceeds BMAX, uniform can't spend the surplus: solves saturate at "cost <= BMAX".
    costs = [1000.0, 100_000.0, math.inf]
    huge = len(costs) * (BMAX * 10)
    assert uniform_solved(costs, huge) == 2  # the inf cell is never solved regardless of T
