"""Eval metrics — the honest, budget-aware numbers (PROJECT_PLAN.md §9).

All operate on a flat list of `ProblemResult` (one per problem×seed) and aggregate **across seeds**
as mean ± std (rule 7: ≥3 seeds for headline numbers). The headline is `pass@B`: the fraction of
problems with a verified proof found within a per-problem budget `B`, as a curve over several `B`.

Because each cell records `tokens_to_solve`, the whole curve comes from one run per (problem, seed).
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass

from atp.eval.records import ProblemResult


@dataclass(frozen=True)
class PassAtB:
    budget: int
    mean: float  # mean over seeds of (fraction of problems solved within budget)
    std: float  # sample std over seeds (0.0 if <2 seeds)
    n_seeds: int
    n_problems: int


def _by_seed(results: list[ProblemResult]) -> dict[int, list[ProblemResult]]:
    out: dict[int, list[ProblemResult]] = defaultdict(list)
    for r in results:
        out[r.seed].append(r)
    return out


def _std(xs: list[float]) -> float:
    return statistics.stdev(xs) if len(xs) >= 2 else 0.0


def pass_at_b(results: list[ProblemResult], budgets: list[int]) -> list[PassAtB]:
    """`pass@B` curve: for each B, mean±std over seeds of the solved-within-B fraction."""
    by_seed = _by_seed(results)
    n_problems = max((len(rs) for rs in by_seed.values()), default=0)
    curve: list[PassAtB] = []
    for b in budgets:
        per_seed_frac = [
            sum(r.solved_within(b) for r in rs) / len(rs) for rs in by_seed.values() if rs
        ]
        mean = statistics.fmean(per_seed_frac) if per_seed_frac else 0.0
        curve.append(
            PassAtB(
                budget=b,
                mean=mean,
                std=_std(per_seed_frac),
                n_seeds=len(per_seed_frac),
                n_problems=n_problems,
            )
        )
    return curve


def tokens_to_first_proof(results: list[ProblemResult]) -> dict[str, float | int]:
    """Mean/median cumulative tokens to the verified proof, over solved cells only."""
    toks = [r.tokens_to_solve for r in results if r.solved and r.tokens_to_solve is not None]
    if not toks:
        return {"n_solved": 0, "mean": 0.0, "median": 0.0}
    return {
        "n_solved": len(toks),
        "mean": statistics.fmean(toks),
        "median": statistics.median(toks),
    }


def effective_accuracy(
    results: list[ProblemResult], budget: int, *, false_accepts_per_seed: int = 0
) -> dict[str, float]:
    """Solved-within-`budget` fraction, discounting unsound (reviewer-flagged) false accepts.

    With a sound verifier and no reviewer, `false_accepts_per_seed=0` → this equals `pass@budget`.
    Kept separate so the reviewer ablation (Phase 1) can subtract false accepts honestly.
    """
    by_seed = _by_seed(results)
    per_seed = []
    for rs in by_seed.values():
        if not rs:
            continue
        solved = sum(r.solved_within(budget) for r in rs)
        per_seed.append(max(0, solved - false_accepts_per_seed) / len(rs))
    return {
        "budget": float(budget),
        "mean": statistics.fmean(per_seed) if per_seed else 0.0,
        "std": _std(per_seed),
    }


def summarize(
    results: list[ProblemResult], budgets: list[int]
) -> dict[str, object]:
    """All Phase-0 metrics in one dict (ready to dump to results/<run>/metrics.json)."""
    curve = pass_at_b(results, budgets)
    max_b = max(budgets) if budgets else 0
    return {
        "n_cells": len(results),
        "pass_at_b": [vars(p) for p in curve],
        "tokens_to_first_proof": tokens_to_first_proof(results),
        "effective_accuracy": effective_accuracy(results, max_b),
    }
