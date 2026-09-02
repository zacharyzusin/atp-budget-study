#!/usr/bin/env python3
"""WS6 item 4: does the richer (v2) feature set improve the difficulty predictor?

Pre-registration: results/phase4/PREDICTOR_V2_DESIGN.md (read before touching this). CPU-only,
reuses
already-logged attempt data (no GPU re-run).

Protocol (the CV guard from the pre-registration): seed 2 -- the one showing DeepSeek's per-seed
saving collapse (-51%, ALLOCATION.md) -- is held out ENTIRELY from feature-set/model selection. All
CV AUC numbers below are computed on seeds {0,1} ONLY (v1 vs v2, same protocol, apples-to-apples).
The selected feature set (v2, since it's a superset) is then evaluated exactly ONCE on the held-out
seed 2, reported separately, never averaged into the seeds-0-1 CV number.

Usage: python scripts/phase4_predictor_v2.py
Writes results/phase4/predictor_v2.json and results/phase4/PREDICTOR_V2_RESULT.md.
"""

from __future__ import annotations

import json
from pathlib import Path

from atp.alloc.extract import BASELINE_RUNS
from atp.alloc.features import CHECKPOINTS, CheckpointRow, build_feature_rows
from atp.alloc.predict import (
    cv_auc,
    holdout_seed_eval,
    logistic_factory,
    rows_to_xy_by_seed,
)

ROOT = Path(__file__).resolve().parents[1]
TRAIN_SEEDS = {0, 1}
HOLDOUT_SEED = 2
PROOFNET_RUNS = [(d, m, b) for d, m, b in BASELINE_RUNS if b == "proofnet_sharp"]


def main() -> None:
    report = []
    for run_dir, model, benchmark in PROOFNET_RUNS:
        d = ROOT / "results" / run_dir
        if not (d / "problems").exists():
            print(f"SKIP {run_dir}: no problems/")
            continue
        rows = build_feature_rows(d, CHECKPOINTS)
        per_c = []
        for c in CHECKPOINTS:
            row = {"checkpoint": c}
            for tag, names in (
                ("v1", CheckpointRow.FEATURE_NAMES),
                ("v2", CheckpointRow.FEATURE_NAMES_V2),
            ):
                X, y, groups, _ = rows_to_xy_by_seed(rows, c, TRAIN_SEEDS, names)
                n = len(y)
                auc, _ = cv_auc(X, y, groups, logistic_factory) if n else (float("nan"), None)
                row[f"auc_{tag}_seeds01"] = auc
                row[f"n_seeds01_{tag}"] = n
            # held-out-seed check: fit v2 on seeds 0,1 (already CV'd above), evaluate ONCE on seed 2
            auc_ho = holdout_seed_eval(
                rows, c, HOLDOUT_SEED, TRAIN_SEEDS, logistic_factory, CheckpointRow.FEATURE_NAMES_V2
            )
            row["auc_v2_heldout_seed2"] = auc_ho
            per_c.append(row)
        report.append(
            {"model": model, "benchmark": benchmark, "run_dir": run_dir, "by_checkpoint": per_c}
        )

    out_json = ROOT / "results" / "phase4" / "predictor_v2.json"
    out_json.write_text(json.dumps(report, indent=2))

    lines = [
        "# WS6 item 4: v2 predictor result (seed-holdout guarded)",
        "",
        "Pre-registration: `results/phase4/PREDICTOR_V2_DESIGN.md`. All CV AUCs computed on "
        "seeds {0,1} only; seed 2 evaluated exactly once, held out from feature/model selection.",
        "",
        "| model | c | AUC v1 (s01) | AUC v2 (s01) | gain | AUC v2 (heldout s2) |",
        "|---|---|---|---|---|---|",
    ]
    print(
        f"\n{'model':9s} {'c':>7} {'AUC_v1(s01)':>12} {'AUC_v2(s01)':>12} {'gain':>7} "
        f"{'AUC_v2(s2 heldout)':>20}"
    )
    max_gain = float("-inf")
    for e in report:
        for r in e["by_checkpoint"]:
            v1, v2, ho = r["auc_v1_seeds01"], r["auc_v2_seeds01"], r["auc_v2_heldout_seed2"]
            gain = (v2 - v1) if (v1 == v1 and v2 == v2) else float("nan")
            if gain == gain:
                max_gain = max(max_gain, gain)

            def fmt(x):
                return f"{x:.3f}" if x == x else "  nan"

            print(
                f"{e['model']:9s} {r['checkpoint']:>7} {fmt(v1):>12} {fmt(v2):>12} "
                f"{fmt(gain):>7} {fmt(ho):>20}"
            )
            lines.append(
                f"| {e['model']} | {r['checkpoint']} | {fmt(v1)} | {fmt(v2)} | {fmt(gain)} | "
                f"{fmt(ho)} |"
            )

    lines += [
        "",
        f"**Max AUC gain (v2 vs v1, seeds 0,1 CV) across all cells: {max_gain:+.3f}**",
        "",
    ]
    out_md = ROOT / "results" / "phase4" / "PREDICTOR_V2_RESULT.md"
    out_md.write_text("\n".join(lines) + "\n")
    print(f"\nmax gain = {max_gain:+.3f}")
    print(f"wrote {out_json}\nwrote {out_md}")


if __name__ == "__main__":
    main()
