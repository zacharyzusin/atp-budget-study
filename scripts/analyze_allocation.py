#!/usr/bin/env python3
"""Phase 4 mechanism analysis (WS1.2, PLAN_NEXT.md) — why does budget allocation help when it helps?

CPU-only, no GPU/Lean deps. Reuses the same four budget-independent baseline runs and the same
`solved(cell,b) == tokens_to_solve(cell) <= b` identity as `src/atp/alloc/` (ALLOCATION.md §0) — no
new data, no re-simulation of the policy, just a different cut of the already-committed cells.

Hypothesis (PLAN_NEXT.md WS1.2): the realizable policy's gain comes from harvesting "cheap marginal"
cells — pass@B curve slope heterogeneity across (problem, seed) cells lets a knapsack-style policy
correctly abandon truly-trapped cells past the decision checkpoint c* while still funding the late
solves ("late bloomers") that occur past c*. If Goedel x ProofNet# has a richer late-bloomer
population / more cost dispersion than DeepSeek x ProofNet#, that is a mechanistic account of
ALLOCATION.md's STRONG-vs-WEAK asymmetry.

Two analyses:
  M1 problem-level mixed-outcome heterogeneity — classify each PROBLEM (pooled over its 3 seeds) as
     trapped (0/3 solved) / partial (1-2/3, i.e. seed-dependent) / robust (3/3). The partial bucket
     is
     the direct signature of "solved cheaply on some seeds, not others" — the textbook case a
     pooled-cell knapsack can exploit that a per-problem policy cannot.
  M2 post-c* population decomposition — using each run's own already-fit c* (peak-AUC checkpoint,
     read from predictor.json, no refitting), split cells still running at c* into late bloomers
     (eventually solve, cost in (c*, B_max]) vs correctly-abandonable (never solve). Late-bloomer
     token cost dispersion (CV) is the direct "how much is there to harvest" measure.

Usage: analyze_allocation.py [--results-root results] [--out results/phase4]
Writes ALLOCATION_MECHANISM.json; prints a human-readable summary; the .md writeup is separate
(ALLOCATION_MECHANISM.md, written by hand from this script's output, per repo convention).
"""
from __future__ import annotations

import argparse
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

from atp.alloc.extract import BASELINE_RUNS, load_run
from atp.alloc.policies import solve_cost

ROOT = Path(__file__).resolve().parents[1]


def cv(xs: list[float]) -> float | None:
    """Coefficient of variation (std/mean) — scale-free dispersion, comparable across models."""
    if len(xs) < 2:
        return None
    mean = st.mean(xs)
    if mean == 0:
        return None
    return round(st.pstdev(xs) / mean, 3)


def iqr_over_median(xs: list[float]) -> float | None:
    if len(xs) < 4:
        return None
    xs = sorted(xs)
    n = len(xs)
    q1 = xs[n // 4]
    q3 = xs[(3 * n) // 4]
    med = xs[n // 2]
    if med == 0:
        return None
    return round((q3 - q1) / med, 3)


def m1_problem_heterogeneity(table) -> dict:
    by_problem: dict[str, list[bool]] = defaultdict(list)
    for r in table.results:
        by_problem[r.problem_name].append(r.solved)
    n_seeds_expected = max((len(v) for v in by_problem.values()), default=0)
    trapped = partial = robust = 0
    for _, solves in by_problem.items():
        n_solved = sum(solves)
        if n_solved == 0:
            trapped += 1
        elif n_solved == len(solves):
            robust += 1
        else:
            partial += 1
    n = len(by_problem) or 1
    return {
        "n_problems": len(by_problem),
        "seeds_per_problem": n_seeds_expected,
        "trapped_pct": round(100 * trapped / n, 1),
        "partial_pct": round(100 * partial / n, 1),
        "robust_pct": round(100 * robust / n, 1),
        "trapped": trapped, "partial": partial, "robust": robust,
    }


def m2_post_cstar_decomposition(table, cstar: int) -> dict:
    _bmax = max((solve_cost(r) for r in table.results if r.solved), default=0)
    still_running = [r for r in table.results if solve_cost(r) > cstar]
    late_bloomers = [r for r in still_running if r.solved]
    correctly_abandonable = [r for r in still_running if not r.solved]
    costs = [float(r.tokens_to_solve) for r in late_bloomers if r.tokens_to_solve is not None]
    n_pool = len(still_running) or 1
    return {
        "cstar": cstar,
        "n_still_running_at_cstar": len(still_running),
        "n_late_bloomers": len(late_bloomers),
        "n_correctly_abandonable": len(correctly_abandonable),
        "late_bloomer_pct_of_post_cstar_pool": round(100 * len(late_bloomers) / n_pool, 1),
        "late_bloomer_cost_cv": cv(costs),
        "late_bloomer_cost_iqr_over_median": iqr_over_median(costs),
        "late_bloomer_cost_median": round(st.median(costs), 0) if costs else None,
        # tokens actually harvested: what uniform would have burned on the abandonable cells past
        # c*, all of which is saved because they never solve regardless of extra budget.
        "tokens_wasted_by_uniform_on_dead_cells": sum(
            (r.budget or 0) - cstar for r in correctly_abandonable if (r.budget or 0) > cstar
        ),
    }


def load_predictor_cstars(results_root: Path) -> dict[tuple[str, str], int]:
    """Peak-logistic-AUC checkpoint per (model, benchmark), read from the already-fit predictor.json
    (no refitting — same c* the realizable policy in ALLOCATION.md actually used)."""
    p = json.load(open(results_root / "phase4" / "predictor.json"))
    out = {}
    for entry in p:
        best_c, best_auc = None, -1.0
        for row in entry["by_checkpoint"]:
            if row["auc_logistic"] > best_auc:
                best_auc, best_c = row["auc_logistic"], row["checkpoint"]
        out[(entry["model"], entry["benchmark"])] = best_c
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results-root", default="results")
    ap.add_argument("--out", default="results/phase4")
    args = ap.parse_args()
    results_root = ROOT / args.results_root
    out_dir = ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    cstars = load_predictor_cstars(results_root)
    results = {}
    for run_dir, model, benchmark in BASELINE_RUNS:
        table = load_run(results_root / run_dir, model=model, benchmark=benchmark)
        cstar = cstars[(model, benchmark)]
        label = f"{model}_{benchmark}"
        results[label] = {
            "run_dir": run_dir, "model": model, "benchmark": benchmark,
            "n_cells": table.n_cells, "n_solved": table.n_solved,
            "M1_problem_heterogeneity": m1_problem_heterogeneity(table),
            "M2_post_cstar_decomposition": m2_post_cstar_decomposition(table, cstar),
        }

    outp = out_dir / "ALLOCATION_MECHANISM.json"
    json.dump(results, open(outp, "w"), indent=2)

    print(f"{'model x benchmark':<24}{'partial%':>9}{'trapped%':>9}{'robust%':>9}   |  "
          f"{'c*':>6}{'n_post_c*':>11}{'late-bloom%':>13}{'cost_CV':>9}")
    for label, r in results.items():
        m1, m2 = r["M1_problem_heterogeneity"], r["M2_post_cstar_decomposition"]
        print(f"{label:<24}{m1['partial_pct']:>8}%{m1['trapped_pct']:>8}%{m1['robust_pct']:>8}%   |  "
              f"{m2['cstar']:>6}{m2['n_still_running_at_cstar']:>11}"
              f"{m2['late_bloomer_pct_of_post_cstar_pool']:>12}%{str(m2['late_bloomer_cost_cv']):>9}")
    print(f"\nwrote {outp}")


if __name__ == "__main__":
    main()
