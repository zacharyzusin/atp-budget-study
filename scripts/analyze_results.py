#!/usr/bin/env python
"""Reusable analysis for a results/<run>/ dir — pass@B curve, run-vs-run comparison, paired flips.

Automates what was done ad-hoc for results/phase1/FINDINGS.md so the ProofNet# baseline writeup and
the ProofNet# Phase 1 recheck use one audited code path. Loads the per-problem JSONs the harness
writes (`results/<run>/problems/<name>__seed<k>.json`) and aggregates across seeds (mean ± std).

Subcommands
-----------
  curve   <run_dir> [--budgets ...]            pass@B table (mean ± seed-std), tokens-to-first-proof
  compare <run_a> <run_b> [--budgets ...]      both curves side by side + per-B Δ (b - a)
  flips   <base_dir> <variant_dir> --budget B  paired gains/losses per (problem,seed) at fixed B

The paired-flip view is the project's noise bar: a mean Δ under ~1 baseline-σ is noise, so we report
*per-problem* gains vs losses (variant solves that the baseline missed, and vice-versa) — when
gains ≈ losses the net Δ is generation churn, not a real lever (DECISIONS 2026-06-11).

CPU-only, no GPU/Lean deps. Works on a partial (in-flight) run dir too — it just analyzes whatever
cells exist (note: a mid-flight sweep is biased toward whichever problems finished first).
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from atp.eval.metrics import pass_at_b, tokens_to_first_proof
from atp.eval.records import ProblemResult

DEFAULT_BUDGETS = [2000, 8000, 32000, 128000]


def load_dir(run_dir: str | Path) -> list[ProblemResult]:
    """Load every per-problem cell JSON under <run_dir>/problems/ (or <run_dir> itself)."""
    run_dir = Path(run_dir)
    probs = run_dir / "problems"
    src = probs if probs.is_dir() else run_dir
    files = sorted(src.glob("*.json"))
    if not files:
        raise SystemExit(f"no cell JSONs found under {src}")
    return [ProblemResult.load(f) for f in files]


def _coverage(results: list[ProblemResult]) -> dict[int, int]:
    """seed -> number of problems present (to flag an incomplete/biased run)."""
    by_seed: dict[int, int] = defaultdict(int)
    for r in results:
        by_seed[r.seed] += 1
    return dict(sorted(by_seed.items()))


def _index(results: list[ProblemResult]) -> dict[tuple[str, int], ProblemResult]:
    return {(r.problem_name, r.seed): r for r in results}


def paired_flips(
    base: list[ProblemResult], variant: list[ProblemResult], budget: int
) -> dict[str, float | int]:
    """Per-(problem,seed) flips at a fixed budget B, over the pairs present in BOTH runs.

    gains = variant solves within B that base did not; losses = base solves that variant lost.
    Net = gains - losses. When gains ≈ losses the net Δ is generation churn, not a real effect.
    """
    bi, vi = _index(base), _index(variant)
    keys = sorted(bi.keys() & vi.keys())
    gains = losses = base_solved = variant_solved = 0
    for k in keys:
        b_ok = bi[k].solved_within(budget)
        v_ok = vi[k].solved_within(budget)
        base_solved += b_ok
        variant_solved += v_ok
        if v_ok and not b_ok:
            gains += 1
        elif b_ok and not v_ok:
            losses += 1
    return {
        "budget": budget,
        "n_pairs": len(keys),
        "base_solved": base_solved,
        "variant_solved": variant_solved,
        "gains": gains,
        "losses": losses,
        "net": gains - losses,
    }


def _fmt_curve(results: list[ProblemResult], budgets: list[int]) -> str:
    rows = ["  budget   pass@B (mean ± std)   n_seeds  n_problems"]
    for p in pass_at_b(results, budgets):
        rows.append(
            f"  {p.budget:>6}   {p.mean * 100:5.1f}% ± {p.std * 100:4.1f}%"
            f"        {p.n_seeds}        {p.n_problems}"
        )
    return "\n".join(rows)


def cmd_curve(args: argparse.Namespace) -> None:
    results = load_dir(args.run_dir)
    cov = _coverage(results)
    print(f"# {args.run_dir}  ({len(results)} cells; problems/seed = {cov})")
    if len(set(cov.values())) > 1 or (cov and min(cov.values()) < args.expect):
        print(f"  ! INCOMPLETE/uneven coverage (expected ~{args.expect}/seed) — preliminary")
    print(_fmt_curve(results, args.budgets))
    ttp = tokens_to_first_proof(results)
    print(f"  tokens_to_first_proof: n_solved={ttp['n_solved']} "
          f"median={ttp['median']:.0f} mean={ttp['mean']:.0f}")


def cmd_compare(args: argparse.Namespace) -> None:
    a, b = load_dir(args.run_a), load_dir(args.run_b)
    ca = {p.budget: p for p in pass_at_b(a, args.budgets)}
    cb = {p.budget: p for p in pass_at_b(b, args.budgets)}
    print(f"# A = {args.run_a}  ({len(a)} cells)")
    print(f"# B = {args.run_b}  ({len(b)} cells)")
    print("  budget     A pass@B        B pass@B        Δ(B-A)")
    for bud in args.budgets:
        pa, pb = ca[bud], cb[bud]
        d = (pb.mean - pa.mean) * 100
        print(f"  {bud:>6}   {pa.mean * 100:5.1f}%±{pa.std * 100:4.1f}%   "
              f"{pb.mean * 100:5.1f}%±{pb.std * 100:4.1f}%   {d:+5.1f}pp")


def cmd_flips(args: argparse.Namespace) -> None:
    base, variant = load_dir(args.base_dir), load_dir(args.variant_dir)
    f = paired_flips(base, variant, args.budget)
    print(f"# base    = {args.base_dir}")
    print(f"# variant = {args.variant_dir}")
    print(f"# paired flips at B={args.budget} over {f['n_pairs']} (problem,seed) pairs in both")
    print(f"  base solved   : {f['base_solved']}")
    print(f"  variant solved: {f['variant_solved']}")
    print(f"  gains (+)     : {f['gains']}   (variant solved, base missed)")
    print(f"  losses (-)    : {f['losses']}   (base solved, variant lost)")
    print(f"  net           : {f['net']:+d}")
    verdict = "NOISE-LIKE (gains≈losses → generation churn)" if abs(f["net"]) <= max(
        2, 0.5 * (f["gains"] + f["losses"])
    ) else "directional (gains/losses imbalanced)"
    print(f"  -> {verdict}")


def cmd_overlay(args: argparse.Namespace) -> None:
    from atp.eval.plot import plot_pass_at_b_overlay

    curves = {}
    for spec in args.runs:
        label, _, run_dir = spec.partition("=")
        if not run_dir:
            label, run_dir = Path(spec).name, spec
        curves[label] = pass_at_b(load_dir(run_dir), args.budgets)
    out = plot_pass_at_b_overlay(curves, args.out, title=args.title)
    print(f"wrote {out}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("curve", help="pass@B curve for one run dir")
    pc.add_argument("run_dir")
    pc.add_argument("--budgets", type=int, nargs="+", default=DEFAULT_BUDGETS)
    pc.add_argument("--expect", type=int, default=0, help="expected problems/seed; flag incomplete")
    pc.set_defaults(func=cmd_curve)

    pm = sub.add_parser("compare", help="two runs side by side")
    pm.add_argument("run_a")
    pm.add_argument("run_b")
    pm.add_argument("--budgets", type=int, nargs="+", default=DEFAULT_BUDGETS)
    pm.set_defaults(func=cmd_compare)

    pf = sub.add_parser("flips", help="paired gains/losses at a fixed budget")
    pf.add_argument("base_dir")
    pf.add_argument("variant_dir")
    pf.add_argument("--budget", type=int, required=True)
    pf.set_defaults(func=cmd_flips)

    po = sub.add_parser("overlay", help="overlay several runs' pass@B curves into one PNG")
    po.add_argument("runs", nargs="+", help="run dirs, optionally label=dir")
    po.add_argument("--out", required=True, help="output PNG path")
    po.add_argument("--budgets", type=int, nargs="+", default=DEFAULT_BUDGETS)
    po.add_argument("--title", default=None)
    po.set_defaults(func=cmd_overlay)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
