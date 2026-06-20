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


# ---- checkpoint features (Task 4.1 / 4.3): causality + no leakage --------------------------------

from atp.alloc.features import (  # noqa: E402
    CellTrace,
    CheckpointRow,
    attempt_depth,
    build_feature_rows,
    opening_tactic,
)


def test_attempt_depth_parses_failed_at_step():
    assert attempt_depth(False, "Failed at step 5 (`foo`): unsolved goals") == 5
    assert attempt_depth(False, "Failed at step 0 (`x`): REPL_INFRA_ERROR ...") == 0
    assert attempt_depth(False, "some unparseable noise") == 0  # infra/unknown -> 0
    assert attempt_depth(True, "Proof verified.") == 10_000     # reached the end


def test_opening_tactic_after_by():
    assert opening_tactic("theorem t : p := by\n  intro h\n  exact h") == "intro"
    assert opening_tactic("theorem t := by\n  -- comment\n  simp") == "simp"  # skips comments
    assert opening_tactic("") == ""


def _att(tokens: int, ok: bool, step: int | None, opening: str = "intro") -> dict:
    fb = "Proof verified." if ok else f"Failed at step {step} (`x`): unsolved goals"
    return {"completion_tokens": tokens, "ok": ok, "feedback": fb,
            "proof": f"theorem t := by\n  {opening}\n"}


def test_checkpoint_only_sees_attempts_finished_by_c():
    # 3 attempts of 1000 tokens each (cum ends 1000/2000/3000). At c=2000 only the first two are
    # observable; the third (depth 9) must NOT influence any feature -> causality.
    cell = CellTrace("p", 0, solved=False, tokens_to_solve=None, attempts=[
        _att(1000, False, 3), _att(1000, False, 5), _att(1000, False, 9),
    ])
    r = cell.checkpoint_row(2000)
    assert r.n_attempts == 2
    assert r.tokens_so_far == 2000
    assert r.best_depth == 5          # the depth-9 attempt (cum 3000 > 2000) is invisible
    assert r.last_depth == 5
    # at a later checkpoint the third attempt becomes visible
    assert cell.checkpoint_row(3000).best_depth == 9


def test_partial_attempt_at_boundary_excluded():
    # an attempt whose END exceeds c is not yet observed (we only see *completed* attempts).
    cell = CellTrace("p", 0, solved=False, tokens_to_solve=None,
                     attempts=[_att(1500, False, 4), _att(1500, False, 12)])
    r = cell.checkpoint_row(2000)  # second attempt ends at 3000 > 2000
    assert r.n_attempts == 1 and r.best_depth == 4


def test_stalled_and_growth_signals():
    # best depth climbs 2->6 at attempt 1, then never improves: a genuine plateau (stuck).
    cell = CellTrace("p", 0, solved=False, tokens_to_solve=None, attempts=[
        _att(1000, False, 2), _att(1000, False, 6), _att(1000, False, 4), _att(1000, False, 5),
    ])
    r = cell.checkpoint_row(4000)
    assert r.best_depth == 6
    assert r.stalled_attempts == 2     # best (6) last hit at idx 1; two attempts since -> stuck
    # depth_growth: early half best = max(2,6)=6, recent half best = max(4,5)=5 -> -1 (declining)
    assert r.depth_growth == -1
    assert r.distinct_openings == 1
    assert r.compiled_past_step1 == 1

    # contrast: a cell still climbing has positive growth and zero stall
    climbing = CellTrace("q", 0, solved=False, tokens_to_solve=None, attempts=[
        _att(1000, False, 2), _att(1000, False, 3), _att(1000, False, 5), _att(1000, False, 9),
    ])
    rc = climbing.checkpoint_row(4000)
    assert rc.stalled_attempts == 0 and rc.depth_growth > 0


def test_features_never_include_label():
    # no-leakage: tokens_to_solve / eventual_solve / solved_by_c are NOT in the feature vector.
    cell = CellTrace("p", 0, solved=True, tokens_to_solve=1500, attempts=[_att(1000, True, None)])
    r = cell.checkpoint_row(2000)
    feats = r.features()
    for banned in ("tokens_to_solve", "eventual_solve", "solved_by_c", "checkpoint"):
        assert banned not in feats
    assert set(feats) == set(CheckpointRow.FEATURE_NAMES)


@pytest.mark.skipif(not PROOFNET.exists(), reason="baseline run not on disk")
def test_real_rows_build_and_respect_causality():
    rows = build_feature_rows(PROOFNET, checkpoints=(2000, 8000))
    assert rows, "no rows built"
    # every checkpoint row's observed tokens must not exceed its checkpoint (causality on real data)
    for r in rows:
        assert r.tokens_so_far <= r.checkpoint
        assert r.checkpoint in (2000, 8000)
    # one row per (cell, checkpoint)
    assert len(rows) == len({(r.problem_name, r.seed, r.checkpoint) for r in rows})


# ---- predictor: leakage-free X/y + grouped CV (Task 4.3) -----------------------------------------

from atp.alloc.predict import cv_auc, gbt_factory, logistic_factory, rows_to_xy  # noqa: E402


def _row(name, seed, c, *, solved_by_c, eventual, best_depth=3, stalled=0, growth=1):
    return CheckpointRow(
        problem_name=name, seed=seed, checkpoint=c,
        tokens_so_far=c, n_attempts=4, best_depth=best_depth, last_depth=best_depth,
        depth_growth=growth, stalled_attempts=stalled, distinct_openings=2,
        compiled_past_step1=int(best_depth >= 2),
        solved_by_c=solved_by_c, eventual_solve=eventual,
        tokens_to_solve=(c - 1 if eventual else None),
    )


def test_rows_to_xy_excludes_already_solved_and_other_checkpoints():
    rows = [
        _row("a", 0, 2000, solved_by_c=False, eventual=True),
        _row("b", 0, 2000, solved_by_c=True, eventual=True),    # already solved -> excluded
        _row("c", 0, 8000, solved_by_c=False, eventual=False),  # wrong checkpoint -> excluded
    ]
    X, y, groups, names = rows_to_xy(rows, 2000)
    assert X.shape == (1, len(CheckpointRow.FEATURE_NAMES))
    assert list(y) == [1]
    assert list(groups) == ["a"]
    assert names == list(CheckpointRow.FEATURE_NAMES)


def test_grouped_cv_has_no_problem_in_both_splits():
    # two seeds per problem; GroupKFold must never split a problem across train/test.
    from sklearn.model_selection import GroupKFold
    rows = []
    for p in range(10):
        for s in (0, 1):
            rows.append(_row(f"p{p}", s, 2000, solved_by_c=False, eventual=(p % 2 == 0)))
    X, y, groups, _ = rows_to_xy(rows, 2000)
    for tr, te in GroupKFold(n_splits=5).split(X, y, groups):
        assert not (set(groups[tr]) & set(groups[te]))


def test_cv_auc_separable_is_high_degenerate_is_nan():
    # perfectly separable by best_depth -> AUC ~1; single-class -> nan.
    rows = []
    for p in range(20):
        ev = p % 2 == 0
        rows.append(_row(f"p{p}", 0, 2000, solved_by_c=False, eventual=ev,
                         best_depth=(20 if ev else 1), growth=(5 if ev else -5)))
    X, y, groups, _ = rows_to_xy(rows, 2000)
    auc, _ = cv_auc(X, y, groups, logistic_factory, n_splits=5)
    assert auc > 0.9
    # all same label -> nan
    flat = [_row(f"q{p}", 0, 2000, solved_by_c=False, eventual=False) for p in range(10)]
    Xf, yf, gf, _ = rows_to_xy(flat, 2000)
    a2, _ = cv_auc(Xf, yf, gf, gbt_factory, n_splits=5)
    assert a2 != a2  # nan
