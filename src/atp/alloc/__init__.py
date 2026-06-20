"""Phase 4 — compute-optimal budget allocation.

Turns the negative result (scaffolding null; real hammer 0/119 trapped) into a positive one: a
per-problem budget-allocation policy that proves the same theorems for less compute (and ideally
more theorems for the same compute) than uniform budgeting. The whole study is **offline
arithmetic** over the baseline runs' logged `tokens_to_solve`, using the identity in `solve_cost`:

    solved(problem, seed, b)  ==  (tokens_to_solve(problem, seed) <= b)   for b <= 128k

This holds **only** for the budget-independent baseline runs (one cell at the 128k max, the action
sequence a prefix). Never apply it to a budget-proportional variant — `test_alloc` asserts this.
"""

from atp.alloc.policies import (
    BMAX,
    oracle_min_T_to_match,
    oracle_solved,
    solve_cost,
    uniform_solved,
)

__all__ = [
    "BMAX",
    "solve_cost",
    "uniform_solved",
    "oracle_solved",
    "oracle_min_T_to_match",
]
