#!/usr/bin/env python3
"""WS6 item 1: equivalence-testing reframe -- upper confidence bounds instead of "within noise."

"Within 1 seed-std at n=3" is an absence of evidence, not evidence of absence, and understates the
statistical power actually available: each Phase 1 ablation has 186-244 paired problem-level
observations (x3 seeds), not 3. This script reports, for each baseline-vs-variant comparison, a
paired per-problem bootstrap 95% CI on the mean solve-rate delta (same clustered-by-problem
bootstrap
as `scripts/phase4_bootstrap_ci.py` -- a problem's seeds resample together, since they are not
independent draws of "how hard this problem is"). The one-sided 97.5th percentile of the bootstrap
distribution is reported as the equivalence bound: "this component's true effect is below +Xpp with
~97.5% one-sided confidence." A bound that is tight and near zero is a citable equivalence result; a
bound that is wide (e.g. several points either side) means the comparison never had the power to
detect a real effect at that seed count -- worth knowing before a reviewer notices.

CPU-only. Covers: all Phase 1 scaffolding components on both benchmarks (baseline vs each variant,
paired by (problem_name, seed), "solved" field at the run's own fixed budget), plus Step C
(diversity
injection vs its own token-matched resampling control) if that data is present in the same paired
per-cell shape.

Usage: python scripts/equivalence_bounds.py [--n-boot 3000] [--seed 0]
Writes results/equivalence_bounds.json and .md.
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]

# (run_root, baseline_subdir, {label: variant_subdir}, benchmark_label)
PHASE1_COMPARISONS = [
    (
        "phase1_ablation",
        "baseline",
        {
            "retrieval": "retrieval__1",
            "memory": "memory__1",
            "reviewer": "reviewer__1",
            "tactic_skeletons": "tactic_skeletons__1",
            "budget_alloc__0": "budget_alloc__0",
            "budget_alloc__2": "budget_alloc__2",
        },
        "minif2f",
    ),
    (
        "phase1_proofnet",
        "baseline",
        {
            "retrieval": "retrieval__1",
            "memory": "memory__1",
            "reviewer": "reviewer__1",
            "tactic_skeletons": "tactic_skeletons__1",
            "budget_alloc__0": "budget_alloc__0",
            "budget_alloc__2": "budget_alloc__2",
        },
        "proofnet_sharp",
    ),
]


def load_solved(run_dir: Path) -> dict[tuple[str, int], bool]:
    out = {}
    for f in glob.glob(str(run_dir / "problems" / "*.json")):
        d = json.load(open(f))
        out[(d["problem_name"], d["seed"])] = bool(d.get("solved"))
    return out


def load_solved_merged(run_dirs: list[Path]) -> dict[tuple[str, int], bool]:
    """Merge per-seed run dirs (e.g. p6eval_g_mf_base + _s1 + _s2, each internally seed-homogeneous)
    into one paired-cell dict keyed by (problem_name, seed) -- same shape load_solved returns for a
    single multi-seed run dir."""
    out: dict[tuple[str, int], bool] = {}
    for d in run_dirs:
        out.update(load_solved(d))
    return out


# Phase 6 Stage B (closing-targeted SFT) / Stage A (generic RFT) pilot: base vs A vs B, both models
# (g=Goedel, d=DeepSeek), both held-out benchmarks (mf=miniF2F, pn=ProofNet#), 3 seeds each stored
# as
# 3 separate single-seed run dirs (results/p6eval_{g,d}_{mf,pn}_{base,A,B}[_s1|_s2]).
STAGE_B_COMPARISONS = [
    (model, bench, arm) for model in ("g", "d") for bench in ("mf", "pn") for arm in ("A", "B")
]


def _p6_dirs(model: str, bench: str, arm: str) -> list[Path]:
    base = f"p6eval_{model}_{bench}_{arm}"
    return [
        ROOT / "results" / base,
        ROOT / "results" / f"{base}_s1",
        ROOT / "results" / f"{base}_s2",
    ]


def paired_bootstrap_bound(
    baseline: dict, variant: dict, n_boot: int, rng: np.random.Generator
) -> dict | None:
    """Cluster-by-problem bootstrap on the paired
    per-cell delta (variant_solved - baseline_solved)."""
    keys = sorted(set(baseline) & set(variant))
    if not keys:
        return None
    by_problem: dict[str, list[tuple[str, int]]] = {}
    for name, seed in keys:
        by_problem.setdefault(name, []).append((name, seed))
    names = sorted(by_problem)
    n = len(names)

    def mean_delta(cell_keys) -> float:
        deltas = [int(variant[k]) - int(baseline[k]) for k in cell_keys]
        return float(np.mean(deltas)) if deltas else 0.0

    point = mean_delta(keys)
    boot = []
    for _ in range(n_boot):
        picked = rng.choice(names, size=n, replace=True)
        cell_keys = [k for name in picked for k in by_problem[name]]
        boot.append(mean_delta(cell_keys))

    lo, hi = float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))
    ub_one_sided = float(
        np.percentile(boot, 97.5)
    )  # one-sided 97.5th pct == upper end of 95% two-sided
    lb_one_sided = float(np.percentile(boot, 2.5))
    return {
        "n_problems": n,
        "n_cells": len(keys),
        "point_delta_pp": 100 * point,
        "ci95_two_sided_pp": [100 * lo, 100 * hi],
        "upper_bound_97_5_pp": 100 * ub_one_sided,
        "lower_bound_2_5_pp": 100 * lb_one_sided,
        "n_boot": n_boot,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-boot", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)

    report = []
    for run_root, base_sub, variants, bench in PHASE1_COMPARISONS:
        base_dir = ROOT / "results" / run_root / base_sub
        if not (base_dir / "problems").exists():
            print(f"SKIP {run_root}: no baseline problems/")
            continue
        base_solved = load_solved(base_dir)
        for label, sub in variants.items():
            var_dir = ROOT / "results" / run_root / sub
            if not (var_dir / "problems").exists():
                print(f"SKIP {run_root}/{sub}: missing")
                continue
            var_solved = load_solved(var_dir)
            res = paired_bootstrap_bound(base_solved, var_solved, args.n_boot, rng)
            if res is None:
                continue
            res.update({"benchmark": bench, "component": label, "group": "phase1"})
            report.append(res)
            print(
                f"{bench:14s} {label:20s} n={res['n_problems']:3d}  "
                f"point={res['point_delta_pp']:+.2f}pp  "
                f"95% CI [{res['ci95_two_sided_pp'][0]:+.2f}, {res['ci95_two_sided_pp'][1]:+.2f}]pp"
            )

    stage_b_report = []
    for model, bench, arm in STAGE_B_COMPARISONS:
        base_dirs = _p6_dirs(model, bench, "base")
        var_dirs = _p6_dirs(model, bench, arm)
        if not all((d / "problems").exists() for d in base_dirs + var_dirs):
            print(f"SKIP stageB {model}/{bench}/{arm}: missing a seed dir")
            continue
        base_solved = load_solved_merged(base_dirs)
        var_solved = load_solved_merged(var_dirs)
        res = paired_bootstrap_bound(base_solved, var_solved, args.n_boot, rng)
        if res is None:
            continue
        model_label = "Goedel" if model == "g" else "DeepSeek"
        bench_label = "miniF2F" if bench == "mf" else "ProofNet#"
        arm_label = "A (generic RFT)" if arm == "A" else "B (closing-targeted SFT)"
        res.update(
            {"model": model_label, "benchmark": bench_label, "arm": arm_label, "group": "stage_b"}
        )
        stage_b_report.append(res)
        print(
            f"stageB {model_label:9s} {bench_label:10s} {arm_label:25s} n={res['n_problems']:3d}  "
            f"point={res['point_delta_pp']:+.2f}pp  "
            f"95% CI [{res['ci95_two_sided_pp'][0]:+.2f}, {res['ci95_two_sided_pp'][1]:+.2f}]pp"
        )

    out_json = ROOT / "results" / "equivalence_bounds.json"
    out_json.write_text(json.dumps(report + stage_b_report, indent=2))

    lines = [
        "# Equivalence bounds for Phase 1 scaffolding components (WS6 item 1)",
        "",
        "Paired per-problem bootstrap (clustered by problem, all seeds of a problem resampled",
        "together), 95% CI on the mean solve-rate delta (variant - baseline), in percentage",
        "points. Upper/lower bound columns are the one-sided 97.5th/2.5th percentiles (same",
        'numbers as the two-sided CI ends, labeled for the equivalence-testing framing: "this',
        "component's true effect is below +Xpp with ~97.5% one-sided confidence\").",
        "",
        "| benchmark | component | n problems | point (pp) | 95% CI (pp) | upper bound (pp) |",
        "|---|---|---|---|---|---|",
    ]
    for r in report:
        lines.append(
            f"| {r['benchmark']} | {r['component']} | {r['n_problems']} | "
            f"{r['point_delta_pp']:+.2f} | "
            f"[{r['ci95_two_sided_pp'][0]:+.2f}, {r['ci95_two_sided_pp'][1]:+.2f}] | "
            f"{r['upper_bound_97_5_pp']:+.2f} |"
        )
    lines += [
        "",
        "## Phase 6 Stage A/B (SFT exposure-bias pilot), both models, both benchmarks, 3 seeds",
        "",
        "Same paired per-problem bootstrap, base vs. each arm (A = generic RFT, "
        "B = closing-targeted SFT), merged across 3 single-seed run dirs per arm "
        "(`p6eval_{g,d}_{mf,pn}_{base,A,B}[_s1|_s2]`).",
        "",
        "| model | benchmark | arm | n problems | point (pp) | 95% CI (pp) | upper bound (pp) |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in stage_b_report:
        lines.append(
            f"| {r['model']} | {r['benchmark']} | {r['arm']} | {r['n_problems']} | "
            f"{r['point_delta_pp']:+.2f} | "
            f"[{r['ci95_two_sided_pp'][0]:+.2f}, {r['ci95_two_sided_pp'][1]:+.2f}] | "
            f"{r['upper_bound_97_5_pp']:+.2f} |"
        )
    out_md = ROOT / "results" / "EQUIVALENCE_BOUNDS.md"
    out_md.write_text("\n".join(lines) + "\n")
    print(f"\nwrote {out_json}\nwrote {out_md}")


if __name__ == "__main__":
    main()
