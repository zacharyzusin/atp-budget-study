"""Allocation policies as pure arithmetic over per-cell solve costs (Task 4.2, the ceiling pair).

A *cell* is one (problem, seed). Its **solve cost** is the tokens it needed to find a verified
proof, or +inf if it never solved within the 128k baseline budget. A *policy* maps a list of cells'
costs and a total budget `T` to per-cell budgets `{b_i}` with `Σ b_i ≤ T` and `b_i ≤ BMAX`; its
*score* is the number of cells solved, i.e. `Σ [cost_i ≤ b_i]`.

This file holds the two non-learned policies that bracket the result:
- `uniform_solved` — the naive baseline (`b_i = T/N`); at `T = N·b` reproduces the logged `pass@b`.
- `oracle_solved` — the unrealizable upper bound (knapsack on known costs); the headroom ceiling.

The realizable policies (successive-halving, learned predictor) live in `realizable.py`, scored the
same way, so they sit between these two by construction (`oracle ≥ realizable ≥ uniform` in solves
at fixed `T`, modulo the realizable policy's prediction error).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

from atp.eval.records import ProblemResult

# The baseline's max per-problem budget. `tokens_to_solve` is always ≤ this for solved cells, so a
# funded cell's budget never needs to exceed BMAX — the `b_i ≤ BMAX` cap binds only on `uniform`
# when `T/N > BMAX` (then the surplus is wasted, which is exactly uniform's naivety).
BMAX = 128_000


def solve_cost(r: ProblemResult) -> float:
    """The §0 identity as a cost: tokens to a verified proof, or +inf if never solved within BMAX.

    `solved(cell, b) == (solve_cost(cell) <= b)`. Mirrors `ProblemResult.solved_within` exactly (it
    is tested against it), but returns a number so policies can sort/knapsack over costs.
    """
    if r.solved and r.tokens_to_solve is not None and r.tokens_to_solve <= BMAX:
        return float(r.tokens_to_solve)
    return math.inf


def uniform_solved(costs: Sequence[float], total_budget: float, *, n: int | None = None,
                   bmax: float = BMAX) -> int:
    """Naive policy: split `T` evenly over all `n` cells (default `len(costs)`); count solves.

    Each cell gets `b = min(T/n, bmax)`; surplus above `bmax·n` is wasted (uniform can't move it).
    At `T = n·b` every cell gets exactly `b`, so the solve count equals `Σ [cost ≤ b]` — the logged
    `pass@b` numerator (`test_uniform_reproduces_pass_at_b`).
    """
    n = len(costs) if n is None else n
    if n <= 0:
        return 0
    b = min(total_budget / n, bmax)
    return sum(1 for c in costs if c <= b)


def oracle_solved(costs: Iterable[float], total_budget: float, *, bmax: float = BMAX) -> int:
    """Unrealizable upper bound: fund the cheapest-to-solve cells first (greedy knapsack on costs).

    Returns the largest `k` such that the `k` smallest finite costs sum to `≤ T`. Each funded cell
    gets exactly its cost (`≤ bmax`), so the `b_i ≤ bmax` cap is automatically satisfied. This is
    the headroom ceiling: it reclaims both the budget uniform wastes on trapped cells (cost = inf,
    never funded) and the over-funding of easy ones.
    """
    finite = sorted(c for c in costs if c <= bmax)
    spent = 0.0
    k = 0
    for c in finite:
        if spent + c <= total_budget:
            spent += c
            k += 1
        else:
            break
    return k


def oracle_min_T_to_match(costs: Iterable[float], target_solved: int, *,
                          bmax: float = BMAX) -> float:
    """Minimum total budget the oracle needs to solve `target_solved` cells = sum of that many
    smallest finite costs. `inf` if fewer than `target_solved` cells are solvable at all.

    This is the efficiency headline's denominator: `compute_saved = 1 - T'/T` where `T'` is this and
    `T` is uniform's budget at the matched solve count.
    """
    finite = sorted(c for c in costs if c <= bmax)
    if target_solved <= 0:
        return 0.0
    if target_solved > len(finite):
        return math.inf
    return float(sum(finite[:target_solved]))
