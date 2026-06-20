#!/usr/bin/env python3
"""Task 4.3-4.4: the efficiency frontier + capture-of-oracle, all four baselines (CPU-only).

For each (model, benchmark):
  1. costs = per-cell solve cost (§0 identity, tokens_to_solve or +inf).
  2. decision checkpoint c* = the checkpoint with the best grouped-CV AUC (from the predictor); get
     leakage-free OOF predicted solve-probabilities for the still-running cells there.
  3. build the uniform / oracle / realizable(c*, τ-sweep) curves on one (compute, solves) axis pair.
  4. headline numbers vs the §5 thresholds:
       - EFFICIENCY: at matched max accuracy (all solvable solved), compute saved by realizable vs
         uniform, and capture-of-oracle = (uniform-realizable)/(uniform-oracle).
       - ACCURACY: at a few matched total-compute points, realizable vs uniform extra solves (Δpp),
         and the oracle-realizable accuracy gap (the tuning gate).
  5. write results/phase4/frontier.json and a frontier PNG per run.

Honest framing: realizable uses only during-run signals + OOF predictions (no peeking ahead).
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
    capture_of_oracle,
    min_compute_for_solves,
    oracle_curve,
    realizable_curve,
    uniform_curve,
    uniform_point,
)
from atp.alloc.policies import solve_cost
from atp.alloc.predict import cv_auc, logistic_factory, rows_to_xy

ROOT = Path(__file__).resolve().parents[1]


def best_checkpoint_scores(run_dir: Path):
    """Pick c* = argmax CV-AUC; return (c*, auc, per-cell OOF prob dict keyed by (name, seed))."""
    rows = build_feature_rows(run_dir, CHECKPOINTS)
    best = (-1.0, None, {})
    for c in CHECKPOINTS:
        sel = [r for r in rows if r.checkpoint == c and not r.solved_by_c]
        X, y, groups, _ = rows_to_xy(rows, c)
        if len(y) == 0:
            continue
        auc, oof = cv_auc(X, y, groups, logistic_factory)
        if math.isnan(auc):
            continue
        if auc > best[0]:
            scores = {(r.problem_name, r.seed): float(p) for r, p in zip(sel, oof, strict=True)}
            best = (auc, c, scores)
    return best[1], best[0], best[2]


def make_scores(results, c, oof_scores):
    """Per-cell score aligned to `results` order: cost<=c -> +inf (always kept, irrelevant); else
    the cell's OOF prob (fallback to the median score for any cost>c cell the predictor missed)."""
    med = float(np.median(list(oof_scores.values()))) if oof_scores else 0.0
    out = []
    for r in results:
        cost = solve_cost(r)
        if cost <= c:
            out.append(math.inf)
        else:
            out.append(oof_scores.get((r.problem_name, r.seed), med))
    return out


def main() -> None:
    have_mpl = True
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        have_mpl = False

    report = []
    for run_dir, model, benchmark in BASELINE_RUNS:
        d = ROOT / "results" / run_dir
        if not (d / "problems").exists():
            continue
        tbl = load_run(d, model, benchmark)
        costs = [solve_cost(r) for r in tbl.results]
        n = len(costs)
        n_solved = sum(1 for c in costs if c <= BMAX)

        cstar, auc, oof = best_checkpoint_scores(d)
        scores = make_scores(tbl.results, cstar, oof)

        # curves
        budgets = sorted(set(list(range(1000, BMAX + 1, 1000)) + [c for c in CHECKPOINTS]))
        uni = uniform_curve(costs, budgets)
        # oracle swept over total budgets up to uniform's max compute
        u_max_comp, _ = uniform_point(costs, BMAX)
        Ts = sorted(set(int(u_max_comp * f) for f in np.linspace(0.005, 1.0, 80)))
        ora = oracle_curve(costs, Ts)
        rea = realizable_curve(costs, scores, cstar)

        # EFFICIENCY at matched accuracy. The matched-MAX (100%) target is ~0-capturable by
        # construction: to solve every winnable cell you must keep the hardest ones, which are
        # indistinguishable from trapped (cost ≈ 128k) -> keep all -> no saving. The positive result
        # lives at fractional targets (give up the hardest few), so we report a sweep.
        eff = []
        for tf in (0.80, 0.90, 0.95, 1.00):
            target = math.floor(tf * n_solved)
            u_comp = min_compute_for_solves(uni, target)
            o_comp = min_compute_for_solves(ora, target)
            r_comp = min_compute_for_solves(rea, target)
            eff.append({
                "accuracy_target_frac": tf, "target_solves": target,
                "uniform_compute": u_comp, "realizable_compute": r_comp, "oracle_compute": o_comp,
                "realizable_saved_frac": (1.0 - r_comp / u_comp) if u_comp else float("nan"),
                "oracle_saved_frac": (1.0 - o_comp / u_comp) if u_comp else float("nan"),
                "capture_of_oracle": capture_of_oracle(u_comp, r_comp, o_comp),
            })

        # ACCURACY at matched compute: pick a few total-compute targets (fractions of u_max_comp)
        acc = []
        for frac in (0.05, 0.10, 0.25, 0.50):
            T = frac * u_max_comp
            u_s = max((s for _, comp, s in uni if comp <= T), default=0)
            o_s = max((s for _, comp, s in ora if comp <= T), default=0)
            r_s = max((s for _, comp, s in rea if comp <= T), default=0)
            acc.append({
                "compute_frac": frac, "total_compute": T,
                "uniform_solved": u_s, "realizable_solved": r_s, "oracle_solved": o_s,
                "realizable_minus_uniform_pp": 100.0 * (r_s - u_s) / n,
                "oracle_minus_realizable_pp": 100.0 * (o_s - r_s) / n,  # the tuning gate
            })

        report.append({
            "model": model, "benchmark": benchmark, "n_cells": n, "n_solved": n_solved,
            "decision_checkpoint": cstar, "auc_at_cstar": auc,
            "efficiency_at_matched_accuracy": eff,
            "accuracy_at_matched_compute": acc,
        })

        if have_mpl:
            fig, ax = plt.subplots(figsize=(6, 4))
            for curve, lab, style in [(uni, "uniform", "o-"), (rea, "realizable", "s-"),
                                      (ora, "oracle", "-")]:
                pts = sorted(((comp, s) for _, comp, s in curve))
                xs = [p[0] / 1e6 for p in pts]
                ys = [100.0 * p[1] / n for p in pts]
                ax.plot(xs, ys, style, ms=3, lw=1.4, label=lab)
            ax.set_xlabel("total compute (M tokens)")
            ax.set_ylabel("solve rate (%)")
            ax.set_title(f"{model} × {benchmark}  (c*={cstar}, AUC={auc:.2f})")
            ax.legend()
            ax.grid(alpha=0.3)
            fig.tight_layout()
            fig.savefig(ROOT / "results" / "phase4" / f"frontier_{model}_{benchmark}.png", dpi=130)
            plt.close(fig)

    out = ROOT / "results" / "phase4" / "frontier.json"
    out.write_text(json.dumps(report, indent=2))

    for e in report:
        print(f"\n=== {e['model']:9s} × {e['benchmark']:14s}  "
              f"(c*={e['decision_checkpoint']}, AUC={e['auc_at_cstar']:.2f}, "
              f"solved {e['n_solved']}/{e['n_cells']}) ===")
        print("  EFFICIENCY (compute to reach X% of solvable, realizable vs uniform vs oracle):")
        for ef in e["efficiency_at_matched_accuracy"]:
            sv = ef["realizable_saved_frac"]
            tgt = int(100 * ef["accuracy_target_frac"])
            u_m = ef["uniform_compute"] / 1e6
            r_m = ef["realizable_compute"] / 1e6
            o_m = ef["oracle_compute"] / 1e6
            print(f"    {tgt:>3}% ({ef['target_solves']:>3}): "
                  f"uni {u_m:>5.1f}M  rea {r_m:>5.1f}M  ora {o_m:>5.2f}M "
                  f"-> saved {100*sv:+5.0f}% capture {100*ef['capture_of_oracle']:+5.0f}%")
        print("  ACCURACY @ matched compute:  frac   uni   rea   ora   (rea-uni / ora-rea pp)")
        for a in e["accuracy_at_matched_compute"]:
            print(f"      {a['compute_frac']:>5.2f}  {a['uniform_solved']:>4d} "
                  f"{a['realizable_solved']:>4d} {a['oracle_solved']:>4d}   "
                  f"({a['realizable_minus_uniform_pp']:+.1f} /"
                  f" {a['oracle_minus_realizable_pp']:+.1f})")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
