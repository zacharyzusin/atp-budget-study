#!/usr/bin/env python3
"""Paired per-problem bootstrap CI for the realizable-policy saving (replaces the 1-seed-std gate).

WS2 writing pass (2026-07-25): with only 3-8 seeds, a seed-std computed over 3 points is itself
barely estimated -- +26% +/- 7% on 3 draws (+25/+18/+34) tells you almost nothing about the true
sampling distribution's shape or tails. This script instead treats each PROBLEM (not each seed) as
the resampling unit: a bootstrap replicate resamples problem names with replacement (same total
count), pools that resampled problem set's cells across ALL its logged seeds (a paired/clustered
bootstrap -- a problem's seeds move together, since they are not independent draws of "how hard this
problem is"), keeps the already-fixed decision checkpoint c* and OOF predictor scores fixed (only
the
population of problems varies), and recomputes the realizable-saved-fraction statistic from scratch
on each replicate. 186-244 problems per benchmark gives a far better-populated resampling
distribution
than 3 seed points ever could.

CPU-only, no GPU, reuses the exact `saved_at_target` computation from `phase4_perseed.py` so the
point estimate matches that script exactly; only the CI construction differs.

Usage: python scripts/phase4_bootstrap_ci.py [--n-boot 2000] [--seed 0]
Writes results/phase4/bootstrap_ci.json.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from phase4_perseed import best_checkpoint_oof, saved_at_target

from atp.alloc.extract import BASELINE_RUNS, load_run
from atp.alloc.policies import solve_cost

ROOT = Path(__file__).resolve().parents[1]


def bootstrap_ci(tbl, cstar, oof, med, n_boot: int, rng: np.random.Generator, frac: float = 0.90):
    """Resample problem names (paired across seeds) with replacement; return point estimate + CI."""
    by_problem: dict[str, list] = {}
    for r in tbl.results:
        by_problem.setdefault(r.problem_name, []).append(r)
    names = sorted(by_problem)
    n = len(names)

    def saved_frac_for(cells) -> float | None:
        costs = [solve_cost(r) for r in cells]
        scores = [
            math.inf if solve_cost(r) <= cstar else oof.get((r.problem_name, r.seed), med)
            for r in cells
        ]
        out = saved_at_target(costs, scores, cstar, frac=frac)
        return out["realizable_saved_frac"] if out is not None else None

    point = saved_frac_for(tbl.results)

    boot_vals = []
    for _ in range(n_boot):
        picked = rng.choice(names, size=n, replace=True)
        cells = [r for name in picked for r in by_problem[name]]
        v = saved_frac_for(cells)
        if v is not None:
            boot_vals.append(v)

    if not boot_vals:
        return point, None, None, 0
    lo, hi = float(np.percentile(boot_vals, 2.5)), float(np.percentile(boot_vals, 97.5))
    return point, lo, hi, len(boot_vals)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-boot", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    report = []
    for run_dir, model, benchmark in BASELINE_RUNS:
        d = ROOT / "results" / run_dir
        if not (d / "problems").exists():
            continue
        tbl = load_run(d, model, benchmark)
        cstar, auc, oof = best_checkpoint_oof(d)
        med = float(np.median(list(oof.values()))) if oof else 0.0

        point, lo, hi, n_ok = bootstrap_ci(tbl, cstar, oof, med, args.n_boot, rng)
        entry = {
            "model": model,
            "benchmark": benchmark,
            "decision_checkpoint": cstar,
            "n_problems": len({r.problem_name for r in tbl.results}),
            "point_saved_frac": point,
            "ci95_lo": lo,
            "ci95_hi": hi,
            "n_boot_valid": n_ok,
            "n_boot_requested": args.n_boot,
        }
        report.append(entry)
        ci_str = f"[{100 * lo:+.1f}%, {100 * hi:+.1f}%]" if lo is not None else "n/a"
        pt_str = f"{100 * point:+.1f}%" if point is not None else "n/a"
        print(
            f"{model:9s} x {benchmark:14s} (c*={cstar}): saved@90% = {pt_str}  "
            f"95% CI {ci_str}  (n={entry['n_problems']} problems, {n_ok}/{args.n_boot} valid boots)"
        )

    out = ROOT / "results" / "phase4" / "bootstrap_ci.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
