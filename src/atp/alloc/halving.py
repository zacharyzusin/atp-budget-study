"""Successive-halving: the multi-round realizable policy that lowers the single-checkpoint floor.

The single-checkpoint realizable policy (`frontier.py`) forces *every* cell to run to one decision
checkpoint `c*` before anyone can be abandoned, so its compute can never drop below `c*·N` — the
"compute floor" that blocks the cheap regime and pushes the loose-target / miniF2F numbers negative.

Successive-halving removes that floor by deciding in **rounds**. Everyone runs a cheap first rung;
after each non-final rung we keep only the top `keep_frac` of the still-unsolved cells (ranked by
the out-of-fold predicted solve-probability *at that rung's checkpoint*) and abandon the rest. A
weak cell is therefore cut after 2k tokens instead of after `c*`, so the floor falls from `c*·N`
toward `rungs[0]·N`.

Accounting mirrors `frontier.cell_outcome`, per cell:
  - solved while active at rung `r` (cost ≤ r)        → spent = cost,          solved.
  - abandoned at the cut after rung `r`               → spent = r,             unsolved.
  - survives every cut, reaches final rung `bmax`     → spent = min(cost,bmax), solved iff ≤ bmax.

So a cell always spends `min(cost, rung_it_stopped_at)` and solves iff `cost ≤ rung_it_stopped_at`.
Scored on the same (compute, solves) axis as uniform/oracle/realizable, so the curves overlay.

Bookends (asserted in `test_alloc`): `keep_frac = 1.0` makes no cut → exactly `uniform@bmax`;
`keep_frac → 0` keeps one survivor per cut → ≈ the `rungs[0]·N` floor; compute is monotone
non-increasing in `keep_frac` and never exceeds `uniform@bmax`.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from atp.alloc.frontier import BMAX

# Default rung schedule: the five feature checkpoints plus the 128k cap. The cut after rung k ranks
# cells by their OOF score at checkpoint `rungs[k]`, so `scores_by_rung` is aligned to `rungs[:-1]`.
RUNGS: tuple[int, ...] = (2000, 4000, 8000, 16000, 32000, BMAX)


def successive_halving(costs: Sequence[float], scores_by_rung: Sequence[Sequence[float]],
                       rungs: Sequence[int] = RUNGS, keep_frac: float = 0.5,
                       bmax: float = BMAX) -> tuple[float, int]:
    """One successive-halving run → (total compute spent, cells solved).

    `costs[i]` is cell i's §0 solve cost (`tokens_to_solve` or +inf). `scores_by_rung[k][i]` is the
    OOF predicted P(solve) for cell i at checkpoint `rungs[k]`, used only for the cut *after* rung k
    (so `scores_by_rung` need only be `len(rungs) - 1` long; the final rung has no cut). Cells
    solved or abandoned before a cut are ignored by it. `keep_frac` ∈ (0,1] is promoted-fraction η,
    applied at every cut; at least one cell is always promoted.
    """
    n = len(costs)
    spent = [0.0] * n
    solved = [False] * n
    active = list(range(n))
    last = len(rungs) - 1

    for k, rung in enumerate(rungs):
        r = min(float(rung), bmax)
        still: list[int] = []
        for i in active:
            cost = costs[i]
            if cost <= r:
                spent[i] = cost          # solved while active at this rung
                solved[i] = True
            else:
                spent[i] = r             # ran to this rung's boundary (kept cells overwritten next)
                still.append(i)
        active = still
        if k < last and active:
            scores = scores_by_rung[k]
            ranked = sorted(active, key=lambda i: scores[i], reverse=True)
            n_keep = max(1, math.ceil(keep_frac * len(active)))
            active = ranked[:n_keep]     # promoted; the rest stay abandoned at spent = r

    return float(sum(spent)), int(sum(solved))


def sh_curve(costs: Sequence[float], scores_by_rung: Sequence[Sequence[float]],
             rungs: Sequence[int] = RUNGS, bmax: float = BMAX,
             keep_fracs: Sequence[float] | None = None) -> list[tuple[float, float, int]]:
    """(keep_frac, compute, solves) over a sweep of promoted-fractions η — the realizable SH curve.

    Low η (aggressive cutting) → cheap but only early solves; η = 1.0 → the `uniform@bmax` point.
    Not sorted by compute; callers sort as needed (mirrors `frontier.realizable_curve`).
    """
    if keep_fracs is None:
        keep_fracs = [round(0.05 * i, 2) for i in range(1, 21)]  # 0.05 .. 1.00
    return [(kf, *successive_halving(costs, scores_by_rung, rungs, kf, bmax)) for kf in keep_fracs]


def multiround_threshold(costs: Sequence[float], scores_by_rung: Sequence[Sequence[float]],
                         rungs: Sequence[int] = RUNGS, tau: float = 0.5,
                         bmax: float = BMAX) -> tuple[float, int]:
    """Multi-round THRESHOLD policy → (total compute, solves). Same rung ladder and per-cell
    accounting as `successive_halving`, but at each non-final rung it keeps every still-unsolved
    cell whose OOF score `>= tau` (a quality *set*) and abandons the rest, not a top-fraction slice.

    Because the kept set is quality-defined, this can abandon an early-revealing trapped cell at
    rung 0 instead of waiting for a single checkpoint `c*` (lowering the floor) *without* shedding
    the rare late-solving winnable cells that fixed-fraction halving cuts. It is the natural
    multi-round generalization of the single-checkpoint threshold policy in `realizable_point`.
    """
    n = len(costs)
    spent = [0.0] * n
    solved = [False] * n
    active = list(range(n))
    last = len(rungs) - 1

    for k, rung in enumerate(rungs):
        r = min(float(rung), bmax)
        still: list[int] = []
        for i in active:
            cost = costs[i]
            if cost <= r:
                spent[i] = cost
                solved[i] = True
            else:
                spent[i] = r
                still.append(i)
        active = still
        if k < last and active:
            scores = scores_by_rung[k]
            active = [i for i in active if scores[i] >= tau]  # keep quality set, abandon below τ

    return float(sum(spent)), int(sum(solved))


def mrt_curve(costs: Sequence[float], scores_by_rung: Sequence[Sequence[float]],
              rungs: Sequence[int] = RUNGS, bmax: float = BMAX,
              taus: Sequence[float] | None = None) -> list[tuple[float, float, int]]:
    """(tau, compute, solves) over a sweep of quality thresholds — the multi-round-threshold curve.
    τ = 0 keeps everyone → `uniform@bmax`; τ above every score abandons all unsolved at rung 0 → the
    `rungs[0]·N` floor point. Not sorted by compute (mirrors `frontier.realizable_curve`)."""
    if taus is None:
        taus = [round(0.02 * i, 2) for i in range(0, 51)]  # 0.00 .. 1.00
    return [(t, *multiround_threshold(costs, scores_by_rung, rungs, t, bmax)) for t in taus]
