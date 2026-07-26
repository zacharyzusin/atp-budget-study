#!/usr/bin/env python3
"""WS6 item 1 follow-up: paired bootstrap CI on the retrieval REPLICATION run, at each budget tier.

The original Phase 1 retrieval bootstrap CI (results/EQUIVALENCE_BOUNDS.md) is entirely positive
([+0.82,+6.15]pp @8k) on job 10436909's data. An independently-launched replication run
(results/phase1_retrieval_budget, job 10461442, DECISIONS.md 2026-06-11) landed at +0.7/+0.7/-0.8pp
at 2k/8k/32k -- just outside that CI, and flips sign by 32k. Per the user's 2026-07-26 request: compute
the SAME bootstrap CI machinery on this second run too, and report both side by side, rather than
asserting the disagreement without a number for the second run.

CPU-only, reuses `paired_bootstrap_bound` from equivalence_bounds.py verbatim (same clustered-by-
problem resampling). solved_within(b) is computed from the budget-metered run's own tokens_to_solve
field (identity used project-wide, e.g. scripts/analyze_allocation.py): solved AND tokens_to_solve<=b.

Usage: python scripts/retrieval_replication_ci.py [--n-boot 3000] [--seed 0]
Writes results/RETRIEVAL_REPLICATION_CI.md and .json.
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from equivalence_bounds import paired_bootstrap_bound  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = ROOT / "results" / "phase1_retrieval_budget"
BUDGETS = [2000, 8000, 32000]


def load_solved_at(run_dir: Path, budget: int) -> dict[tuple[str, int], bool]:
    out = {}
    for f in glob.glob(str(run_dir / "problems" / "*.json")):
        d = json.load(open(f))
        tts = d.get("tokens_to_solve")
        solved_at_b = bool(d.get("solved")) and tts is not None and tts <= budget
        out[(d["problem_name"], d["seed"])] = solved_at_b
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-boot", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)

    base_dir = RUN_DIR / "baseline"
    var_dir = RUN_DIR / "retrieval__1"
    if not (base_dir / "problems").exists() or not (var_dir / "problems").exists():
        raise SystemExit(f"missing problems/ under {RUN_DIR}")

    report = []
    for b in BUDGETS:
        base_solved = load_solved_at(base_dir, b)
        var_solved = load_solved_at(var_dir, b)
        res = paired_bootstrap_bound(base_solved, var_solved, args.n_boot, rng)
        res["budget"] = b
        report.append(res)
        print(f"budget={b:6d}  n={res['n_problems']:3d}  point={res['point_delta_pp']:+.2f}pp  "
              f"95% CI [{res['ci95_two_sided_pp'][0]:+.2f}, {res['ci95_two_sided_pp'][1]:+.2f}]pp")

    out_json = ROOT / "results" / "retrieval_replication_ci.json"
    out_json.write_text(json.dumps(report, indent=2))

    lines = [
        "# Retrieval replication run: paired bootstrap CI (WS6 item 1 follow-up)",
        "",
        "Same paired per-problem bootstrap as `EQUIVALENCE_BOUNDS.md`, computed on the INDEPENDENT",
        "replication run (`results/phase1_retrieval_budget`, job 10461442) instead of the original",
        "Phase 1 run (job 10436909). Original-run CI @8k: [+0.82, +6.15]pp (entirely positive).",
        "",
        "| budget | n problems | point (pp) | 95% CI (pp) |",
        "|---|---|---|---|",
    ]
    for r in report:
        lines.append(f"| {r['budget']} | {r['n_problems']} | {r['point_delta_pp']:+.2f} | "
                      f"[{r['ci95_two_sided_pp'][0]:+.2f}, {r['ci95_two_sided_pp'][1]:+.2f}] |")
    lines.append("")
    lines.append("**Reading.** If these CIs do not all contain the original run's [+0.82,+6.15]pp @8k")
    lines.append("point, that is direct, quantified confirmation that within-run bootstrap CIs bound")
    lines.append("only sampling variance conditional on one generation campaign, not run-to-run")
    lines.append("(campaign-level) variance -- the stronger, more general methods lesson (applies to")
    lines.append("any paper reporting a bootstrap CI over a single generation run, not just this one).")
    out_md = ROOT / "results" / "RETRIEVAL_REPLICATION_CI.md"
    out_md.write_text("\n".join(lines) + "\n")
    print(f"\nWrote {out_json} and {out_md}")


if __name__ == "__main__":
    main()
