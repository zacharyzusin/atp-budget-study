#!/usr/bin/env python3
"""Per-seed consistency of the realizable saving (sample-generalization from logged data, CPU-only).

The headline saving is computed by pooling all logged seeds. A reviewer asking "would this work on a
fresh sample?" is answered without any new GPU run: the baseline logged **3 independent seeds**
(0,1,2), each an independent temperature-1.0 draw of the same problems. We recompute the headline
operating point (compute saved vs uniform to retain 90% of that seed's solvable cells) **within each
seed separately**, using the same global decision checkpoint c* and the same OOF predictor.

If the saving holds across all three independent draws, that is sample-generalization evidence (on
top of the predictor's out-of-fold problem-grouped CV, which already shows problem-generalization),
and — because the predictor is trained and applied on the same temperature-1.0 process — there is no
distribution shift between simulated and prospective deployment. Writes perseed.json.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from atp.alloc.extract import BASELINE_RUNS, load_run
from atp.alloc.features import CHECKPOINTS, build_feature_rows
from atp.alloc.frontier import (
    BMAX,
    min_compute_for_solves,
    oracle_curve,
    realizable_curve,
    uniform_curve,
    uniform_point,
)
from atp.alloc.policies import solve_cost
from atp.alloc.predict import cv_auc, logistic_factory, rows_to_xy

ROOT = Path(__file__).resolve().parents[1]


def best_checkpoint_oof(run_dir: Path):
    """c* = argmax grouped-CV AUC; return (c*, auc, OOF dict keyed (name, seed)). As in frontier."""
    rows = build_feature_rows(run_dir, CHECKPOINTS)
    best = (-1.0, None, {})
    for c in CHECKPOINTS:
        sel = [r for r in rows if r.checkpoint == c and not r.solved_by_c]
        X, y, groups, _ = rows_to_xy(rows, c)
        if len(y) == 0:
            continue
        auc, oof = cv_auc(X, y, groups, logistic_factory)
        if math.isnan(auc) or auc <= best[0]:
            continue
        scores = {(r.problem_name, r.seed): float(p) for r, p in zip(sel, oof, strict=True)}
        best = (auc, c, scores)
    return best[1], best[0], best[2]


def saved_at_target(costs, scores, cstar, frac=0.90):
    """Compute saved (vs uniform) to retain `frac` of solvable cells, for one seed's subset."""
    n_solved = sum(1 for c in costs if c <= BMAX)
    if n_solved == 0:
        return None
    target = math.floor(frac * n_solved)
    budgets = sorted(set(list(range(1000, BMAX + 1, 1000)) + list(CHECKPOINTS)))
    uni = uniform_curve(costs, budgets)
    u_max, _ = uniform_point(costs, BMAX)
    Ts = sorted(set(int(u_max * f) for f in np.linspace(0.005, 1.0, 80)))
    ora = oracle_curve(costs, Ts)
    rea = realizable_curve(costs, scores, cstar)
    u_comp = min_compute_for_solves(uni, target)
    r_comp = min_compute_for_solves(rea, target)
    o_comp = min_compute_for_solves(ora, target)
    if not (u_comp and math.isfinite(u_comp)):
        return None
    return {
        "n_solved": n_solved, "target": target,
        "realizable_saved_frac": 1.0 - r_comp / u_comp,
        "oracle_saved_frac": 1.0 - o_comp / u_comp,
    }


def main() -> None:
    report = []
    for run_dir, model, benchmark in BASELINE_RUNS:
        d = ROOT / "results" / run_dir
        if not (d / "problems").exists():
            continue
        tbl = load_run(d, model, benchmark)
        cstar, auc, oof = best_checkpoint_oof(d)
        med = float(np.median(list(oof.values()))) if oof else 0.0
        seeds = sorted({r.seed for r in tbl.results})

        per_seed = []
        for s in seeds:
            rs = [r for r in tbl.results if r.seed == s]
            costs = [solve_cost(r) for r in rs]
            scores = [math.inf if solve_cost(r) <= cstar
                      else oof.get((r.problem_name, r.seed), med) for r in rs]
            out = saved_at_target(costs, scores, cstar, frac=0.90)
            if out is not None:
                out["seed"] = s
                per_seed.append(out)

        saved = [p["realizable_saved_frac"] for p in per_seed]
        entry = {
            "model": model, "benchmark": benchmark, "decision_checkpoint": cstar, "auc": auc,
            "per_seed": per_seed,
            "mean_saved_frac": float(np.mean(saved)) if saved else float("nan"),
            "std_saved_frac": float(np.std(saved)) if saved else float("nan"),
        }
        report.append(entry)

    out = ROOT / "results" / "phase4" / "perseed.json"
    out.write_text(json.dumps(report, indent=2))

    for e in report:
        ss = "  ".join(
            f"s{p['seed']}={100*p['realizable_saved_frac']:+.0f}%" for p in e["per_seed"])
        print(f"{e['model']:9s} × {e['benchmark']:14s} (c*={e['decision_checkpoint']}): "
              f"saved@90% per seed [{ss}]  -> mean {100*e['mean_saved_frac']:+.0f}% "
              f"± {100*e['std_saved_frac']:.0f}%")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
