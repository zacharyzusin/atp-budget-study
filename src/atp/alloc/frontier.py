"""Efficiency frontier: solve-rate vs compute for uniform / oracle / realizable (Task 4.3-4.4).

All three policies are scored on the same per-cell solve costs (§0 identity), so the curves are
directly comparable on one axis pair (total tokens spent, cells solved):

- **uniform(b)** — every cell capped at per-cell budget `b`: spends `min(cost, b)`, solves iff
  `cost ≤ b`. Sweeping `b` traces the naive curve.
- **oracle(T)** — knapsack: fund cheapest costs until `T` exhausted. The unrealizable lower bound on
  compute for any solve count.
- **realizable(c, τ)** — run every cell to the decision checkpoint `c`; for cells still unsolved at
  `c`, keep funding (to 128k) only those with predicted solve-probability `≥ τ`, abandon the rest
  at `c`. Sweeping `τ` traces the realizable curve: low `τ` (keep all) → the uniform max point; high
  `τ` (abandon aggressively) → cheap but only the early solves. The predicted probabilities are
  **OOF** (out-of-fold), so the curve carries no train/test leakage.

The headline is **capture of oracle**: at matched accuracy, what fraction of the oracle's compute
saving over uniform the realizable policy recovers. The oracle−realizable *accuracy* gap at matched
compute is the tuning gate (large ⇒ prediction-limited; small ⇒ saturation, no AUC would help).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

BMAX = 128_000


def cell_outcome(cost: float, c: int, kept: bool, bmax: float = BMAX) -> tuple[float, bool]:
    """(compute spent, solved) for one cell under the realizable policy at checkpoint `c`.

    Every cell runs to at least `min(cost, c)`. Solved by `c` ⇒ done (spent = cost). Otherwise: if
    kept, run to `min(cost, bmax)` (solved iff `cost ≤ bmax`); if abandoned, stop at `c` (no solve).
    """
    if cost <= c:
        return cost, True
    if kept:
        return (cost, True) if cost <= bmax else (float(bmax), False)
    return float(c), False


def realizable_point(costs: Sequence[float], scores: Sequence[float], c: int, tau: float,
                     bmax: float = BMAX) -> tuple[float, int]:
    """Total (compute, solves) at abandonment threshold `tau`. A cell is kept iff its score ≥ tau;
    cells solved by `c` are scored `+inf` so they are always 'kept' (their outcome ignores it)."""
    comp = 0.0
    solv = 0
    for cost, p in zip(costs, scores, strict=True):
        spent, ok = cell_outcome(cost, c, p >= tau, bmax)
        comp += spent
        solv += ok
    return comp, solv


def realizable_curve(costs: Sequence[float], scores: Sequence[float], c: int,
                     bmax: float = BMAX) -> list[tuple[float, float, int]]:
    """(tau, compute, solves) over a sweep of thresholds = every distinct finite score plus the
    endpoints. Sorted by increasing compute is not guaranteed; callers can sort as needed."""
    finite = {p for p in scores if math.isfinite(p)}
    taus = sorted(finite | {0.0, 1.0 + 1e-9, -1e-9})
    return [(tau, *realizable_point(costs, scores, c, tau, bmax)) for tau in taus]


def uniform_point(costs: Sequence[float], b: float, bmax: float = BMAX) -> tuple[float, int]:
    b = min(b, bmax)
    comp = sum(min(cost, b) for cost in costs)  # unsolved (cost=inf) spends the full cap b
    solv = sum(1 for cost in costs if cost <= b)
    return comp, solv


def uniform_curve(costs: Sequence[float], budgets: Sequence[float],
                  bmax: float = BMAX) -> list[tuple[float, float, int]]:
    return [(b, *uniform_point(costs, b, bmax)) for b in budgets]


def oracle_point(costs: Sequence[float], T: float, bmax: float = BMAX) -> tuple[float, int]:
    finite = sorted(c for c in costs if c <= bmax)
    spent = 0.0
    k = 0
    for c in finite:
        if spent + c <= T:
            spent += c
            k += 1
        else:
            break
    return spent, k


def oracle_curve(costs: Sequence[float], totals: Sequence[float],
                 bmax: float = BMAX) -> list[tuple[float, float, int]]:
    return [(T, *oracle_point(costs, T, bmax)) for T in totals]


def min_compute_for_solves(curve: list[tuple[float, float, int]], target: int) -> float:
    """Least compute among curve points achieving ≥ `target` solves (+inf if none do).

    `curve` is a list of (param, compute, solves). Used to read off, at matched accuracy, the
    compute each policy needs — the basis for the efficiency 'capture of oracle' number.
    """
    best = math.inf
    for _, comp, solv in curve:
        if solv >= target and comp < best:
            best = comp
    return best


def capture_of_oracle(uniform_comp: float, realizable_comp: float, oracle_comp: float) -> float:
    """Fraction of the oracle's compute saving (over uniform) the realizable policy recovers, at
    matched accuracy: (uniform − realizable) / (uniform − oracle). 1.0 = matches oracle, 0.0 = no
    better than uniform. nan if there is no headroom (uniform == oracle)."""
    denom = uniform_comp - oracle_comp
    if denom <= 0:
        return float("nan")
    return (uniform_comp - realizable_comp) / denom
