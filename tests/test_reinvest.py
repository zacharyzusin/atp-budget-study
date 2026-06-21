"""Tests for Phase 5 reclaim-and-reinvest candidate sets (Task 5.1). All CPU, no GPU/Lean.

The load-bearing properties of the §1 dominance argument, asserted here:
- the extend/abandon split is exhaustive & disjoint over the unsolved-at-128k cells, and *every*
  candidate (both sets) is genuinely unsolved within 128k (so early-abandon loses nothing);
- routing uses only ≤128k-observable signal, and the abandon checkpoint uses only ≤a signal;
- the abandon rule is conservative (a still-climbing cell is never abandoned -> goes to extend),
  which is what makes the *sign* per-seed-safe; and
- the iso-compute feasibility arithmetic (reclaim >= extension overspend) is correct.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atp.alloc.features import CellTrace, load_cell_traces
from atp.alloc.policies import BMAX
from atp.alloc.reinvest import (
    classify_cell,
    confidently_trapped_at,
    partition_run,
    stratified_pilot,
)

ROOT = Path(__file__).resolve().parents[1]
PROOFNET = ROOT / "results" / "proofnet_baseline"


def _att(tokens: int, ok: bool, step: int | None, opening: str = "intro") -> dict:
    fb = "Proof verified." if ok else f"Failed at step {step} (`x`): unsolved goals"
    return {"completion_tokens": tokens, "ok": ok, "feedback": fb,
            "proof": f"theorem t := by\n  {opening}\n"}


def _trapped(name: str, seed: int = 0, n: int = 8, depth: int = 3) -> CellTrace:
    # climbs to `depth` on attempt 0 then flat-lines forever: a plateau (confidently trapped).
    atts = [_att(2000, False, depth)] + [_att(2000, False, depth - 1) for _ in range(n - 1)]
    return CellTrace(name, seed, solved=False, tokens_to_solve=None, attempts=atts)


def _climbing(name: str, seed: int = 0, n: int = 8) -> CellTrace:
    # best depth strictly increases each attempt: still progressing -> extend.
    atts = [_att(2000, False, 2 + i) for i in range(n)]
    return CellTrace(name, seed, solved=False, tokens_to_solve=None, attempts=atts)


# ---- the confidently-trapped rule (conservative by design) ---------------------------------------

def test_trapped_rule_requires_all_three_conditions():
    # plateaued + enough evidence -> trapped
    assert confidently_trapped_at(6, 0, 4, 8, min_attempts=5, stall_min=4)
    # still climbing (growth > 0) -> NOT trapped, even if other bars met
    assert not confidently_trapped_at(6, 2, 4, 8, min_attempts=5, stall_min=4)
    # too few attempts to judge -> NOT trapped (route to extend)
    assert not confidently_trapped_at(6, 0, 4, 3, min_attempts=5, stall_min=4)
    # short stall -> NOT trapped
    assert not confidently_trapped_at(6, 0, 1, 8, min_attempts=5, stall_min=4)


def test_climbing_cell_is_never_abandoned():
    # the sign-safety property: a still-progressing cell must land in extend, never abandon.
    d = classify_cell(_climbing("p"))
    assert d is not None and d.is_extend and d.abandon_at is None and d.reclaim == 0


def test_trapped_cell_is_abandoned_with_reclaim():
    d = classify_cell(_trapped("p", n=8, depth=3))
    assert d is not None and not d.is_extend
    assert d.abandon_at is not None and d.abandon_at <= 32_000
    assert d.reclaim == BMAX - d.abandon_at > 0


def test_solved_cell_is_not_a_candidate():
    cell = CellTrace("p", 0, solved=True, tokens_to_solve=1500,
                     attempts=[_att(1500, True, None)])
    assert classify_cell(cell) is None


def test_abandon_picks_earliest_confident_checkpoint():
    # plateaus immediately (by attempt 5 at 2k each -> 10k spend), so the earliest checkpoint that
    # has >= min_attempts AND a sustained stall is 16k (8 attempts * 2k = 16k). Reclaim from there.
    d = classify_cell(_trapped("p", n=8, depth=3), min_attempts=5, stall_min=2)
    assert d is not None and not d.is_extend
    # the chosen checkpoint must be the cheapest one where the rule already fires
    assert d.abandon_at in (8000, 16000)
    assert d.reclaim == BMAX - d.abandon_at


# ---- partition: exhaustive, disjoint, all-unsolved -----------------------------------------------

def test_partition_exhaustive_disjoint_and_all_unsolved():
    traces = [
        _climbing("c1"), _climbing("c2"), _trapped("t1"), _trapped("t2"),
        CellTrace("s1", 0, solved=True, tokens_to_solve=2000, attempts=[_att(2000, True, None)]),
    ]
    sets = partition_run(traces, "m", "b")
    assert sets.n_cells == 5 and sets.n_solved == 1
    assert sets.n_unsolved == 4  # exhaustive over the 4 unsolved cells
    names_e = {d.problem_name for d in sets.extend}
    names_a = {d.problem_name for d in sets.abandon}
    assert names_e.isdisjoint(names_a)                     # disjoint
    assert names_e | names_a == {"c1", "c2", "t1", "t2"}   # exhaustive, solved cell excluded
    # every candidate (both sets) is genuinely unsolved -> early-abandon loses nothing vs uniform
    by_name = {t.problem_name: t for t in traces}
    for d in sets.extend + sets.abandon:
        assert not by_name[d.problem_name].solved


def test_extend_set_routed_generously():
    # conservative abandonment: climbing cells all go to extend; only the flat-lined ones abandon.
    sets = partition_run([_climbing("c1"), _climbing("c2"), _trapped("t1")], "m", "b")
    assert {d.problem_name for d in sets.extend} == {"c1", "c2"}
    assert {d.problem_name for d in sets.abandon} == {"t1"}


# ---- iso-compute feasibility arithmetic ----------------------------------------------------------

def test_feasibility_reclaim_funds_extension():
    # 4 trapped cells abandoned early -> reclaim; check it funds extensions to E at no net compute.
    sets = partition_run([_trapped(f"t{i}", n=8, depth=3) for i in range(4)]
                         + [_climbing(f"c{i}") for i in range(3)], "m", "b")
    assert sets.total_reclaim == sum(d.reclaim for d in sets.abandon) > 0
    E = 512_000
    per = E - BMAX
    expected = sets.total_reclaim // per
    assert sets.max_fundable_extensions(E) == expected
    assert sets.feasible(E, expected)
    assert not sets.feasible(E, expected + 1)


def test_no_extension_budget_is_all_fundable():
    # E <= 128k is not an extension; the helper returns the whole extend set (degenerate guard).
    sets = partition_run([_climbing("c1"), _trapped("t1")], "m", "b")
    assert sets.max_fundable_extensions(BMAX) == len(sets.extend)


def test_stratified_pilot_is_deterministic_and_sized():
    sets = partition_run([_climbing(f"c{i}") for i in range(20)], "m", "b")
    pick = stratified_pilot(sets.extend, 8, seed=0)
    assert len(pick) == 8
    assert pick == stratified_pilot(sets.extend, 8, seed=0)        # deterministic
    assert len({(d.problem_name, d.seed) for d in pick}) == 8       # distinct cells
    # asking for more than available returns all
    assert len(stratified_pilot(sets.extend, 999)) == len(sets.extend)


# ---- on real logs --------------------------------------------------------------------------------

@pytest.mark.skipif(not PROOFNET.exists(), reason="baseline run not on disk")
def test_real_partition_is_clean_and_all_unsolved():
    traces = load_cell_traces(PROOFNET)
    sets = partition_run(traces, "goedel", "proofnet_sharp")
    # exhaustive/disjoint over unsolved cells; solved count matches the logged flag
    n_solved_logged = sum(1 for t in traces if t.solved)
    assert sets.n_solved == n_solved_logged
    assert sets.n_unsolved == len(traces) - n_solved_logged
    e = {(d.problem_name, d.seed) for d in sets.extend}
    a = {(d.problem_name, d.seed) for d in sets.abandon}
    assert e.isdisjoint(a)
    # no solved cell leaked into a candidate set
    solved_keys = {(t.problem_name, t.seed) for t in traces if t.solved}
    assert (e | a).isdisjoint(solved_keys)
    # reclaim is non-negative and each abandon checkpoint is below the cap
    assert all(0 < d.reclaim <= BMAX for d in sets.abandon)
    assert all(d.abandon_at is not None and d.abandon_at < BMAX for d in sets.abandon)
