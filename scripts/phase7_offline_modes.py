#!/usr/bin/env python3
"""Phase 7 Track 1 — offline Modes 1/2 trapped pass@B (zero GPU/Lean).

Mode 2 (whole-proof + error-feedback refinement) IS the committed baseline (every config has
refinement.enabled=true) — its pass@B on the trapped core is just the existing per-cell
`ProblemResult`s restricted to trapped problem names. Mode 1 (no-feedback whole-proof) is recovered
FOR FREE from the same run's `agent_states`: a `propose`-kind attempt is a fresh, feedback-free
sample (unconditioned on any prior attempt in the cell), so keeping only propose-kind attempts and
their cumulative cost reconstructs what a dedicated no-refinement run would have measured — the same
budget-independence trick Phase 4 used, applied to attempt KIND instead of a budget cap
(atp.agents.stepwise.propose_only_tokens_to_solve; see DECISIONS.md 2026-07-03).

Only Mode 3 (verified-state re-grounding) needs new inference — this script produces Modes 1+2 so
the trapped-first eval (Task 7.1.5) only has to spend GPU on Mode 3.

Usage:
  python scripts/phase7_offline_modes.py --run-dir results/proofnet_baseline \
      --trapped scratch/phase2/trapped_proofnet.txt --budgets 2000,8000,32000 \
      --out results/phase7/offline_goedel_proofnet.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from atp.agents.stepwise import propose_only_tokens_to_solve
from atp.alloc.features import load_cell_traces
from atp.eval.metrics import PassAtB, pass_at_b
from atp.eval.records import ProblemResult


def restrict_to_trapped(
    results: list[ProblemResult], trapped_names: set[str]
) -> list[ProblemResult]:
    """Keep only cells whose problem is in the trapped core (the cleanest fork signal)."""
    return [r for r in results if r.problem_name in trapped_names]


def mode1_results(cell_traces: list[dict]) -> list[ProblemResult]:
    """Reconstruct each trapped cell's Mode-1 (no-feedback) `ProblemResult` from its attempts."""
    out: list[ProblemResult] = []
    for cell in cell_traces:
        solved, tokens_to_solve = propose_only_tokens_to_solve(cell["attempts"])
        out.append(
            ProblemResult(
                problem_name=cell["problem_name"],
                seed=cell["seed"],
                budget=128_000,
                solved=solved,
                stop_reason="",
                tokens_to_solve=tokens_to_solve,
                tokens_spent=tokens_to_solve if tokens_to_solve is not None else 128_000,
                n_attempts=len(cell["attempts"]),
            )
        )
    return out


def _curve_to_dict(curve: list[PassAtB]) -> list[dict]:
    return [
        {"budget": p.budget, "mean": p.mean, "std": p.std, "n_seeds": p.n_seeds,
         "n_problems": p.n_problems}
        for p in curve
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True, help="results/<baseline_run>")
    ap.add_argument("--trapped", required=True, help="scratch/phase2/trapped_*.txt")
    ap.add_argument("--budgets", default="2000,8000,32000")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    trapped_names = {ln.strip() for ln in Path(args.trapped).read_text().splitlines() if ln.strip()}
    budgets = [int(b) for b in args.budgets.split(",")]

    problems_dir = Path(args.run_dir) / "problems"
    mode2_all = [ProblemResult.load(p) for p in sorted(problems_dir.glob("*.json"))]
    mode2 = restrict_to_trapped(mode2_all, trapped_names)

    traces = [
        {"problem_name": t.problem_name, "seed": t.seed, "attempts": t.attempts}
        for t in load_cell_traces(args.run_dir)
        if t.problem_name in trapped_names
    ]
    mode1 = mode1_results(traces)

    out = {
        "run_dir": args.run_dir,
        "trapped": args.trapped,
        "n_trapped_names": len(trapped_names),
        "n_cells_mode1": len(mode1),
        "n_cells_mode2": len(mode2),
        "mode1_pass_at_b": _curve_to_dict(pass_at_b(mode1, budgets)),
        "mode2_pass_at_b": _curve_to_dict(pass_at_b(mode2, budgets)),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2))
    print(f"[phase7-offline] {args.run_dir}: {len(trapped_names)} trapped names, "
          f"mode1 cells={len(mode1)} mode2 cells={len(mode2)} -> {args.out}")
    for b1, b2 in zip(out["mode1_pass_at_b"], out["mode2_pass_at_b"], strict=True):
        print(f"  B={b1['budget']:>6} mode1={b1['mean']:.3%}±{b1['std']:.3%} "
              f"mode2={b2['mean']:.3%}±{b2['std']:.3%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
