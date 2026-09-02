"""Tests for scripts/fold_heartbeat_correction.py (audit Check B arithmetic fold-in).

The script's real safety property is that it recomputes pass@B from raw per-problem records the same
way the harness did -- so these tests pin the recompute semantics (solved iff
`tokens_to_solve <= B`), the sample-vs-population std convention, and the flip-application rules.
"""

from __future__ import annotations

import json

from scripts.fold_heartbeat_correction import BUDGETS, FLIPS, load_cells, pass_at_b


def _write_cells(tmp_path, rows):
    d = tmp_path / "run"
    (d / "problems").mkdir(parents=True)
    for name, seed, solved, tts in rows:
        (d / "problems" / f"{name}__seed{seed}.json").write_text(
            json.dumps(
                {
                    "problem_name": name,
                    "seed": seed,
                    "solved": solved,
                    "tokens_to_solve": tts,
                }
            )
        )
    return d


def test_load_cells_maps_unsolved_to_none(tmp_path):
    d = _write_cells(tmp_path, [("p1", 0, True, 500), ("p2", 0, False, None)])
    cells = load_cells(d)
    assert cells[("p1", 0)] == 500
    assert cells[("p2", 0)] is None


def test_load_cells_ignores_tokens_when_not_solved(tmp_path):
    # a cell can carry a stale tokens_to_solve while solved=False; it must not count as solved
    d = _write_cells(tmp_path, [("p1", 0, False, 500)])
    assert load_cells(d)[("p1", 0)] is None


def test_pass_at_b_counts_solved_within_budget_only(tmp_path):
    d = _write_cells(
        tmp_path,
        [("a", 0, True, 1000), ("b", 0, True, 9000), ("c", 0, False, None), ("d", 0, True, 40000)],
    )
    out = pass_at_b(load_cells(d), [0])
    assert out[2000][0] == 0.25  # only `a`
    assert out[8000][0] == 0.25  # `b` needs 9000
    assert out[32000][0] == 0.50  # a + b
    assert out[128000][0] == 0.75  # a + b + d; `c` never solves


def test_pass_at_b_boundary_is_inclusive(tmp_path):
    d = _write_cells(tmp_path, [("a", 0, True, 8000)])
    assert pass_at_b(load_cells(d), [0])[8000][0] == 1.0


def test_pass_at_b_uses_sample_std_not_population(tmp_path):
    # seeds solve 1/1, 0/1, 0/1 -> rates 1,0,0. sample std = 0.5774, population std = 0.4714.
    rows = [("a", 0, True, 100), ("a", 1, False, None), ("a", 2, False, None)]
    d = _write_cells(tmp_path, rows)
    std = pass_at_b(load_cells(d), [0, 1, 2])[2000][1]
    assert abs(std - 0.5773502691896258) < 1e-9


def test_flip_table_matches_the_audits_reported_totals():
    # AUDIT_FINDINGS.md Task B: 13 cells across 4 cores; DeepSeek x ProofNet# is the sole
    # zero-flip core.
    assert sum(len(v) for v in FLIPS.values()) == 13
    assert len(FLIPS["baseline"]) == 3
    assert len(FLIPS["proofnet_baseline"]) == 3
    assert len(FLIPS["deepseek_minif2f_baseline"]) == 7
    assert FLIPS["deepseek_proofnet_baseline"] == []


def test_flip_tokens_are_plausible_and_within_the_128k_budget():
    for run, flips in FLIPS.items():
        for name, seed, toks in flips:
            assert 0 < toks <= 128000, f"{run}/{name} seed{seed}: {toks} outside the 128k budget"
            assert isinstance(seed, int) and 0 <= seed <= 2


def test_a_flip_only_moves_budgets_at_or_above_its_token_cost(tmp_path):
    """Point of using tokens_to_solve: a 40k flip must not touch the 2k/8k/32k rows."""
    d = _write_cells(tmp_path, [("a", 0, False, None), ("b", 0, True, 1000)])
    cells = load_cells(d)
    before = pass_at_b(cells, [0])
    cells[("a", 0)] = 40000  # the flip
    after = pass_at_b(cells, [0])
    for b in (2000, 8000, 32000):
        assert after[b][0] == before[b][0]
    assert after[128000][0] > before[128000][0]


def test_corrections_never_lower_a_rate(tmp_path):
    """The heartbeat fix strictly widens what counts as solved, so no budget may move down."""
    d = _write_cells(tmp_path, [("a", 0, False, None), ("b", 0, True, 5000), ("c", 0, False, None)])
    cells = load_cells(d)
    before = pass_at_b(cells, [0])
    cells[("a", 0)] = 3000
    cells[("c", 0)] = 90000
    after = pass_at_b(cells, [0])
    for b in BUDGETS:
        assert after[b][0] >= before[b][0]
