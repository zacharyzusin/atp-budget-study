"""Reclaim-and-reinvest candidate sets (Phase 5, Task 5.1 — offline on existing logs).

The Phase 5 claim is the stronger "more theorems at equal compute": abandon confidently-trapped
unsolved cells *early* (reclaiming `128k - a` tokens each) and spend the reclaim *extending* the
still-progressing unsolved cells past the 128k cap. By the §1 dominance proposition this is weakly
dominant vs uniform at equal total compute — and, crucially, **per-seed sign-safe**: every cell in
the abandon set is unsolved within 128k (never solved in `[0, 128k]`), so cutting it at `a < 128k`
loses nothing vs uniform's first 128k; the only winnable-late cells live in the *extend* set, which
we never abandon. So the seed-2 collapse that sank DeepSeek *allocation* (mis-abandoning a
winnable-late cell) cannot happen here: a mis-routed winnable-late cell still lands in extend and
gets its budget.

This module is pure arithmetic over the logged `CellTrace`s — no GPU. It produces, per (model,
benchmark):
- **extend set** — the unsolved-at-128k cells *not* confidently trapped (route here generously);
- **abandon set** — the confidently-trapped rest, each with the earliest checkpoint `a` at which the
  plateau is already visible (cheapest reclaim) and the reclaimed tokens `128k - a`;
and the iso-compute feasibility arithmetic (how many extensions to budget `E` the reclaim can fund).

Leakage / causality: the abandon decision for a cell uses only its checkpoint-`a` snapshot (attempts
whose cumulative token END is `≤ a`), via `CellTrace.checkpoint_row`. Extend-set membership is the
complement and likewise uses only `≤128k`-observable signal (the whole logged trajectory). Asserted
in `tests/test_reinvest.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

from atp.alloc.features import CHECKPOINTS, CellTrace
from atp.alloc.policies import BMAX


@dataclass(frozen=True)
class ReinvestDecision:
    """How one unsolved-at-128k cell is routed under reclaim-and-reinvest."""
    problem_name: str
    seed: int
    is_extend: bool
    abandon_at: int | None     # checkpoint the plateau was first confidently visible (abandon set)
    reclaim: int               # tokens freed vs uniform = BMAX - abandon_at (0 for extend cells)
    best_depth_128k: int       # deepest verifier step reached by 128k (stratification key)
    n_attempts_128k: int       # attempts made by 128k (stratification / evidence)


def confidently_trapped_at(
    best_depth: int, depth_growth: int, stalled_attempts: int, n_attempts: int,
    *, min_attempts: int, stall_min: int,
) -> bool:
    """Is this cell *confidently* trapped given only its checkpoint-`a` snapshot?

    Conservative by design (route generously into extend): require *all three* of —
    enough evidence (`n_attempts >= min_attempts`), no recent progress (`depth_growth <= 0`, the
    best-so-far in the recent half is no deeper than the early half), and a sustained plateau
    (`stalled_attempts >= stall_min`, that many attempts since the best depth last improved). A cell
    still climbing, or with too few attempts to judge, is *not* abandoned — it goes to extend.
    """
    return (
        n_attempts >= min_attempts
        and depth_growth <= 0
        and stalled_attempts >= stall_min
    )


def classify_cell(
    trace: CellTrace,
    *,
    budget: int = BMAX,
    abandon_checkpoints: tuple[int, ...] = CHECKPOINTS,
    min_attempts: int = 5,
    stall_min: int = 4,
) -> ReinvestDecision | None:
    """Route one cell. Returns None for cells solved within `budget` (kept as-is, never extended).

    For an unsolved cell, scan `abandon_checkpoints` ascending and abandon at the *earliest* one
    where `confidently_trapped_at` already fires (cheapest reclaim). If none fires by the last
    checkpoint the cell is still progressing → extend.
    """
    if trace.solved and trace.tokens_to_solve is not None and trace.tokens_to_solve <= budget:
        return None  # solved within budget — kept, not a Phase-5 candidate

    full = trace.checkpoint_row(budget)
    for a in sorted(abandon_checkpoints):
        row = trace.checkpoint_row(a)
        if row.solved_by_c:
            continue  # solved by this checkpoint — not an abandon candidate (shouldn't happen here)
        if confidently_trapped_at(
            row.best_depth, row.depth_growth, row.stalled_attempts, row.n_attempts,
            min_attempts=min_attempts, stall_min=stall_min,
        ):
            return ReinvestDecision(
                problem_name=trace.problem_name, seed=trace.seed, is_extend=False,
                abandon_at=a, reclaim=budget - a,
                best_depth_128k=full.best_depth, n_attempts_128k=full.n_attempts,
            )
    return ReinvestDecision(
        problem_name=trace.problem_name, seed=trace.seed, is_extend=True,
        abandon_at=None, reclaim=0,
        best_depth_128k=full.best_depth, n_attempts_128k=full.n_attempts,
    )


@dataclass(frozen=True)
class ReinvestSets:
    """The Task 5.1 partition for one (model, benchmark) run, plus iso-compute accounting."""
    model: str
    benchmark: str
    n_cells: int                       # all cells (solved + unsolved)
    n_solved: int                      # kept as-is (cost = tokens_to_solve, unchanged vs uniform)
    extend: list[ReinvestDecision]     # progressing unsolved cells (extension candidates)
    abandon: list[ReinvestDecision]    # confidently-trapped unsolved cells (early-cut for reclaim)
    budget: int = BMAX

    @property
    def n_unsolved(self) -> int:
        return len(self.extend) + len(self.abandon)

    @property
    def total_reclaim(self) -> int:
        """Tokens freed vs uniform by early-abandoning the trapped set (the reinvestment fund)."""
        return sum(d.reclaim for d in self.abandon)

    def max_fundable_extensions(self, extend_budget: int) -> int:
        """Worst-case count of cells extendable to `extend_budget` at *no* net compute vs uniform.

        Each extension costs at most `extend_budget - budget` beyond uniform's 128k (worst case: a
        trapped extend cell that burns the full `E`); a cell that solves early in extension costs
        less. So `floor(reclaim / (E - 128k))` is a conservative floor on how many extensions the
        reclaim funds at iso-compute. Returns the whole extend set if `extend_budget <= budget`.
        """
        per = extend_budget - self.budget
        if per <= 0:
            return len(self.extend)
        return self.total_reclaim // per

    def feasible(self, extend_budget: int, n_to_extend: int) -> bool:
        """Can the reclaim fund extending `n_to_extend` cells to `extend_budget` at iso-compute?"""
        return self.max_fundable_extensions(extend_budget) >= n_to_extend


def partition_run(
    traces: list[CellTrace], model: str, benchmark: str,
    *, budget: int = BMAX, **kw,
) -> ReinvestSets:
    """Split one run's cells into solved (kept) / extend / abandon. The partition is exhaustive and
    disjoint over the unsolved-at-`budget` cells by construction (classify_cell returns exactly one
    of extend/abandon for each, None only for solved)."""
    extend: list[ReinvestDecision] = []
    abandon: list[ReinvestDecision] = []
    n_solved = 0
    for t in traces:
        d = classify_cell(t, budget=budget, **kw)
        if d is None:
            n_solved += 1
        elif d.is_extend:
            extend.append(d)
        else:
            abandon.append(d)
    return ReinvestSets(
        model=model, benchmark=benchmark, n_cells=len(traces), n_solved=n_solved,
        extend=extend, abandon=abandon, budget=budget,
    )


def stratified_pilot(
    extend: list[ReinvestDecision], n: int, *, seed: int = 0,
) -> list[ReinvestDecision]:
    """Pick ~`n` extend cells stratified by depth reached at 128k (sample across the progress range,
    not just the deepest), for the pilot gate (Task 5.2). Deterministic given `seed`."""
    import random

    if n >= len(extend):
        return list(extend)
    by_depth = sorted(extend, key=lambda d: d.best_depth_128k)
    # split the depth-sorted list into n strata, take one (rng-chosen) cell from each
    rng = random.Random(seed)
    picks: list[ReinvestDecision] = []
    step = len(by_depth) / n
    for i in range(n):
        lo, hi = int(i * step), int((i + 1) * step)
        bucket = by_depth[lo:hi] or by_depth[lo:lo + 1]
        picks.append(bucket[rng.randrange(len(bucket))])
    return picks
