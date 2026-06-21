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


# ---- efficiency frontier (Task 4.3-4.4) ----------------------------------------------------------

from atp.alloc.frontier import (  # noqa: E402
    capture_of_oracle,
    cell_outcome,
    min_compute_for_solves,
    oracle_point,
    realizable_point,
    uniform_point,
)

INF = math.inf


def test_cell_outcome_branches():
    # solved before c: spent = cost, solved (keep flag irrelevant)
    assert cell_outcome(500, 2000, kept=False) == (500, True)
    # unsolved at c, kept, solvable within bmax: runs to cost
    assert cell_outcome(50_000, 2000, kept=True) == (50_000, True)
    # unsolved at c, kept, never solvable: runs to bmax, no solve
    assert cell_outcome(INF, 2000, kept=True) == (float(BMAX), False)
    # unsolved at c, abandoned: stops at c, no solve
    assert cell_outcome(50_000, 2000, kept=False) == (2000.0, False)


def test_realizable_tau0_equals_uniform_max():
    # keep everything (tau=0) at checkpoint c == uniform at b=bmax: same compute and solves.
    costs = [500.0, 9000.0, 60_000.0, INF, INF]
    scores = [INF, 0.3, 0.3, 0.3, 0.3]  # cost<=c scored inf; others arbitrary (all kept at tau=0)
    c = 2000
    r_comp, r_solv = realizable_point(costs, scores, c, tau=0.0)
    u_comp, u_solv = uniform_point(costs, BMAX)
    assert (r_comp, r_solv) == (u_comp, u_solv)


def test_realizable_tau_high_abandons_all_unsolved():
    # tau just above every score -> abandon every not-solved-by-c cell at c; only c-solves remain.
    costs = [500.0, 9000.0, 60_000.0, INF]
    scores = [INF, 0.4, 0.4, 0.4]
    c = 2000
    comp, solv = realizable_point(costs, scores, c, tau=0.5)
    assert solv == 1                       # only the 500-cost cell solved by c
    assert comp == 500 + 2000 + 2000 + 2000  # the rest ran to c then stopped


def test_oracle_le_realizable_le_uniform_compute_at_matched_accuracy():
    # at matched max accuracy, oracle compute <= realizable <= uniform.
    costs = [400.0, 3000.0, 9000.0, 40_000.0, INF, INF, INF]
    n_solved = sum(1 for c in costs if c <= BMAX)  # 4
    c = 2000
    # a useful predictor: high score for the (cost>c) winnable cells, low for trapped
    scores = []
    for cost in costs:
        if cost <= c:
            scores.append(INF)
        elif cost <= BMAX:
            scores.append(0.9)   # winnable, predicted keep
        else:
            scores.append(0.1)   # trapped, predicted abandon
    # realizable: keep winnable (>=0.5), abandon trapped -> solves all n_solved cheaply
    r_comp, r_solv = realizable_point(costs, scores, c, tau=0.5)
    assert r_solv == n_solved
    u_comp, _ = uniform_point(costs, BMAX)
    o_comp, o_solv = oracle_point(costs, sum(sorted(x for x in costs if x <= BMAX)))
    assert o_solv == n_solved
    assert o_comp <= r_comp <= u_comp
    # capture is in (0,1]: better than uniform, no better than oracle
    cap = capture_of_oracle(u_comp, r_comp, o_comp)
    assert 0.0 < cap <= 1.0


def test_min_compute_for_solves_and_capture_edges():
    curve = [(0.1, 100.0, 1), (0.2, 250.0, 3), (0.3, 400.0, 3)]
    assert min_compute_for_solves(curve, 3) == 250.0   # cheapest point reaching >=3
    assert min_compute_for_solves(curve, 5) == math.inf
    # full capture (realizable == oracle) -> 1.0; none (== uniform) -> 0.0
    assert capture_of_oracle(1000, 200, 200) == 1.0
    assert capture_of_oracle(1000, 1000, 200) == 0.0
    # no headroom (uniform == oracle) -> nan
    assert math.isnan(capture_of_oracle(1000, 800, 1000))


# ---- successive-halving (the multi-round realizable policy, Task 4.3 extension) ------------------

from atp.alloc.halving import (  # noqa: E402
    RUNGS,
    mrt_curve,
    multiround_threshold,
    sh_curve,
    successive_halving,
)


def _flat_scores(n: int, rungs=RUNGS) -> list[list[float]]:
    """A score table that promotes nobody preferentially (all equal) — for the bookend tests."""
    return [[0.5] * n for _ in range(len(rungs) - 1)]


def test_sh_keep_all_equals_uniform_max():
    # keep_frac = 1.0 makes no cut: every cell runs to min(cost, bmax) -> exactly uniform@bmax.
    costs = [500.0, 9000.0, 60_000.0, 127_000.0, INF, INF]
    comp, solv = successive_halving(costs, _flat_scores(len(costs)), keep_frac=1.0)
    u_comp, u_solv = uniform_point(costs, BMAX)
    assert (comp, solv) == (u_comp, u_solv)


def test_sh_compute_never_exceeds_uniform_max():
    costs = [400.0, 3000.0, 9000.0, 40_000.0, 120_000.0, INF, INF, INF]
    u_comp, _ = uniform_point(costs, BMAX)
    for kf in (0.05, 0.2, 0.5, 0.8, 1.0):
        comp, _ = successive_halving(costs, _flat_scores(len(costs)), keep_frac=kf)
        assert comp <= u_comp + 1e-9, kf


def test_sh_monotone_in_keep_frac():
    # lower keep_frac drops more cells earlier -> never spends more compute (monotone non-increase).
    costs = [400.0, 3000.0, 9000.0, 40_000.0, 120_000.0, INF, INF, INF, INF, INF]
    scores = _flat_scores(len(costs))
    comps = [successive_halving(costs, scores, keep_frac=kf)[0]
             for kf in (0.1, 0.3, 0.5, 0.7, 1.0)]
    assert comps == sorted(comps), comps


def test_sh_low_keep_frac_approaches_first_rung_floor():
    # keep_frac -> 0 promotes a single survivor per cut: everyone pays rung[0], ~one cell continues.
    # So compute ≈ rungs[0]*N (the floor), well below the single-checkpoint c*=8k or 16k floor.
    n = 40
    costs = [INF] * n                       # all trapped: nobody solves, pure scheduling cost
    comp, solv = successive_halving(costs, _flat_scores(n), keep_frac=0.001)
    assert solv == 0
    floor = RUNGS[0] * n                     # 2000 * 40 = 80_000
    # the lone survivor walks the remaining rungs to bmax; bound the overage generously
    assert floor <= comp <= floor + BMAX
    # and it is far below the single-checkpoint floor (c*=8000 -> 320_000)
    assert comp < 8000 * n


def test_sh_perfect_predictor_helps_and_beats_uniform():
    # A predictor that ranks winnable (cost<=bmax) above trapped (inf) abandons the trapped first,
    # so vs a flat (uninformative) predictor at the SAME keep_frac it solves at least as many cells
    # for no more compute -> good ranking is what successive-halving converts into savings. (Pure
    # fixed-fraction SH can still cut a late-solving winnable cell when survivors co-compete for one
    # slot, so we do NOT claim it keeps *every* winnable cell — that is what the η sweep is for.)
    costs = [400.0, 3000.0, 9000.0, 40_000.0, INF, INF, INF, INF, INF, INF]
    perfect = [[1.0 if c <= BMAX else 0.0 for c in costs] for _ in range(len(RUNGS) - 1)]
    flat = _flat_scores(len(costs))
    for kf in (0.3, 0.5, 0.8):
        p_comp, p_solv = successive_halving(costs, perfect, keep_frac=kf)
        f_comp, f_solv = successive_halving(costs, flat, keep_frac=kf)
        assert p_solv >= f_solv, kf          # ranking trapped last never loses a solve
        assert p_comp <= f_comp + 1e-9, kf   # and never costs more
    # When winnable cells solve at spread-out rungs (so they don't co-compete for one slot), a
    # perfect predictor retains every winnable cell while cutting the trapped pool -> all solves for
    # a fraction of uniform's compute, the headline mechanism. Costs solve at rungs 0..4 in order.
    costs2 = [1500.0, 3500.0, 7000.0, 15_000.0, 30_000.0] + [INF] * 15
    n_winnable = 5
    perfect2 = [[1.0 if c <= BMAX else 0.0 for c in costs2] for _ in range(len(RUNGS) - 1)]
    p_comp, p_solv = successive_halving(costs2, perfect2, keep_frac=0.5)
    assert p_solv == n_winnable
    u_comp, _ = uniform_point(costs2, BMAX)
    assert p_comp < u_comp                   # same solves as uniform, far less compute
    # never cheaper than the oracle (which pays only the winnable costs, no rung overhead)
    o_comp, o_solv = oracle_point(costs2, sum(c for c in costs2 if c <= BMAX))
    assert o_solv == n_winnable and p_comp >= o_comp


def test_sh_curve_endpoints_and_shape():
    costs = [500.0, 9000.0, 60_000.0, INF, INF]
    curve = sh_curve(costs, _flat_scores(len(costs)))
    kfs = [kf for kf, _, _ in curve]
    assert kfs[0] > 0 and kfs[-1] == 1.0
    # the keep-all endpoint equals uniform@bmax
    _, comp_last, solv_last = curve[-1]
    u_comp, u_solv = uniform_point(costs, BMAX)
    assert (comp_last, solv_last) == (u_comp, u_solv)
    # compute increases (weakly) with keep_frac along the swept curve
    comps = [comp for _, comp, _ in curve]
    assert comps == sorted(comps)


# ---- multi-round THRESHOLD (keep score>=τ each rung; quality-set variant of halving) -------------

def test_mrt_tau0_equals_uniform_max():
    # τ = 0 keeps every cell at every cut -> no abandonment -> exactly uniform@bmax.
    costs = [500.0, 9000.0, 60_000.0, 127_000.0, INF, INF]
    comp, solv = multiround_threshold(costs, _flat_scores(len(costs)), tau=0.0)
    assert (comp, solv) == uniform_point(costs, BMAX)


def test_mrt_high_tau_abandons_all_unsolved_at_first_rung():
    # τ above every score -> every cell unsolved by rung0 is cut there; only rung0-solves remain.
    costs = [1500.0, 9000.0, 60_000.0, INF]   # only the 1500 cell solves within rungs[0]=2000
    comp, solv = multiround_threshold(costs, _flat_scores(len(costs)), tau=0.9)
    assert solv == 1
    assert comp == 1500 + 2000 + 2000 + 2000   # the rest ran to rung0 then stopped

def test_mrt_monotone_and_bounded_by_uniform():
    costs = [400.0, 3000.0, 9000.0, 40_000.0, 120_000.0, INF, INF, INF]
    # scores spread so different τ cut different amounts
    scores = [[0.2, 0.4, 0.6, 0.8, 0.3, 0.1, 0.5, 0.7] for _ in range(len(RUNGS) - 1)]
    u_comp, _ = uniform_point(costs, BMAX)
    comps = [multiround_threshold(costs, scores, tau=t)[0] for t in (0.0, 0.25, 0.5, 0.75, 1.01)]
    assert comps == sorted(comps, reverse=True)   # higher τ -> more cut -> less compute
    for c in comps:
        assert c <= u_comp + 1e-9


def test_mrt_keeps_all_winnable_where_sh_sheds_one():
    # The defining contrast: on the exact costs where fixed-fraction SH shed a late winnable cell,
    # the quality-SET threshold keeps EVERY winnable (cost<=bmax) and cuts only trapped -> all win.
    costs = [400.0, 3000.0, 9000.0, 40_000.0, INF, INF, INF, INF, INF, INF]
    n_winnable = sum(1 for c in costs if c <= BMAX)
    perfect = [[1.0 if c <= BMAX else 0.0 for c in costs] for _ in range(len(RUNGS) - 1)]
    m_comp, m_solv = multiround_threshold(costs, perfect, tau=0.5)
    assert m_solv == n_winnable                 # SH only managed n_winnable-1 here (SH test note)
    # and it solves them for less than uniform, no cheaper than oracle
    u_comp, _ = uniform_point(costs, BMAX)
    o_comp, o_solv = oracle_point(costs, sum(c for c in costs if c <= BMAX))
    assert o_comp <= m_comp < u_comp and o_solv == n_winnable


def test_mrt_curve_endpoints():
    costs = [500.0, 9000.0, 60_000.0, INF, INF]
    curve = mrt_curve(costs, _flat_scores(len(costs)))
    taus = [t for t, _, _ in curve]
    assert taus[0] == 0.0 and taus[-1] == 1.0
    # τ=0 endpoint == uniform@bmax; compute is non-increasing as τ rises
    _, comp0, solv0 = curve[0]
    assert (comp0, solv0) == uniform_point(costs, BMAX)
    comps = [comp for _, comp, _ in curve]
    assert comps == sorted(comps, reverse=True)
