#!/usr/bin/env python3
"""Task 4.3 check-in: how early is trapped-ness predictable? (AUC-vs-checkpoint + importances)

For each baseline run and checkpoint c, trains the realizable difficulty predictor on the
leakage-free checkpoint-c features over the *still-running* cells (not solved by c) and reports
problem-grouped cross-validated ROC-AUC for predicting eventual solve, plus GBT feature importances.

The AUC-vs-c curve bounds how much of the 95-98% oracle headroom a during-run policy can capture.
CPU-only. Writes results/phase4/predictor.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from atp.alloc.extract import BASELINE_RUNS
from atp.alloc.features import CHECKPOINTS, CheckpointRow, build_feature_rows
from atp.alloc.predict import cv_auc, gbt_factory, logistic_factory, rows_to_xy

ROOT = Path(__file__).resolve().parents[1]


def gbt_importances(X, y) -> dict[str, float]:
    if len(np.unique(y)) < 2:
        return {}
    m = gbt_factory()
    m.fit(X, y)
    vals = (round(float(v), 4) for v in m.feature_importances_)
    return dict(zip(CheckpointRow.FEATURE_NAMES, vals, strict=True))


def main() -> None:
    report = []
    for run_dir, model, benchmark in BASELINE_RUNS:
        d = ROOT / "results" / run_dir
        if not (d / "problems").exists():
            continue
        rows = build_feature_rows(d, CHECKPOINTS)
        per_c = []
        for c in CHECKPOINTS:
            X, y, groups, _ = rows_to_xy(rows, c)
            n = len(y)
            n_pos = int(y.sum()) if n else 0
            auc_lr, _ = cv_auc(X, y, groups, logistic_factory) if n else (float("nan"), None)
            auc_gbt, _ = cv_auc(X, y, groups, gbt_factory) if n else (float("nan"), None)
            per_c.append({
                "checkpoint": c, "n_running": n, "n_eventual_solve": n_pos,
                "base_rate": (n_pos / n if n else float("nan")),
                "auc_logistic": auc_lr, "auc_gbt": auc_gbt,
                "gbt_importances": gbt_importances(X, y) if n else {},
            })
        report.append({"model": model, "benchmark": benchmark,
                        "run_dir": run_dir, "by_checkpoint": per_c})

    out = ROOT / "results" / "phase4" / "predictor.json"
    out.write_text(json.dumps(report, indent=2))

    for e in report:
        print(f"\n=== {e['model']:9s} × {e['benchmark']:14s} "
              "— predict eventual solve among still-running cells ===")
        hdr = f"  {'c':>7} {'n_run':>6} {'solve%':>7} {'AUC_LR':>7} {'AUC_GBT':>8}   top GBT feats"
        print(hdr)
        for r in e["by_checkpoint"]:
            imp = sorted(r["gbt_importances"].items(), key=lambda kv: -kv[1])[:3]
            top = ", ".join(f"{k}={v:.2f}" for k, v in imp)
            lr = f"{r['auc_logistic']:.3f}" if r["auc_logistic"] == r["auc_logistic"] else "  nan"
            gb = f"{r['auc_gbt']:.3f}" if r["auc_gbt"] == r["auc_gbt"] else "  nan"
            print(f"  {r['checkpoint']:>7} {r['n_running']:>6} {100*r['base_rate']:>6.1f}% "
                  f"{lr:>7} {gb:>8}   {top}")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
