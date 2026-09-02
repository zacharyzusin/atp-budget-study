"""Smoke tests for scripts/make_paper_figures.py.

Plotting code is mostly untestable by assertion, so these pin the parts that can silently go
wrong without anyone noticing in a rendered PDF: the markdown table parser feeding the attempts
figure, and the hard-coded Step C values agreeing with what the paper and PROGRESS.md report.
"""

from __future__ import annotations

from scripts.make_paper_figures import BUDGETS, STEPC, _parse_attempts_table


def test_attempts_table_parses_all_four_cells():
    data = _parse_attempts_table()
    assert set(data) >= {
        "goedel_minif2f",
        "deepseek_minif2f",
        "goedel_proofnet",
        "deepseek_proofnet",
    }


def test_attempts_table_has_every_budget_for_every_cell():
    for cell, per_budget in _parse_attempts_table().items():
        missing = set(BUDGETS) - set(per_budget)
        assert not missing, f"{cell} missing budgets: {missing}"


def test_attempts_are_monotone_in_budget():
    """More budget can only buy more completed attempts -- a parse slip would break this."""
    for cell, per_budget in _parse_attempts_table().items():
        vals = [per_budget[b] for b in BUDGETS]
        assert vals == sorted(vals), f"{cell} non-monotone: {vals}"


def test_2k_buys_less_than_one_full_attempt_everywhere():
    """The paper's claim that the 2k point is attempt-starved -- the reason that figure exists."""
    for cell, per_budget in _parse_attempts_table().items():
        assert per_budget[2000] < 1.0, f"{cell} completes {per_budget[2000]} attempts at 2k"


def test_8k_still_does_not_reach_one_full_attempt():
    """Paper text: "mean propose count 0.68-0.87 across the four baselines" at B=8k.

    Pinned because the paper originally said 0.82-0.87, which silently dropped
    Goedel x ProofNet#'s 0.68 -- caught by this test.
    """
    vals = [pb[8000] for pb in _parse_attempts_table().values()]
    assert all(v < 1.0 for v in vals), vals
    assert 0.68 <= min(vals) and max(vals) <= 0.87, vals


def test_stepc_values_match_the_reported_result():
    # PROGRESS.md 2026-06-19: diversity +44/42/68/70%; trapped pass@32k 1.2/0.7/0/0
    assert [s[1] for s in STEPC] == [44, 42, 68, 70]
    assert [s[2] for s in STEPC] == [1.2, 0.7, 0.0, 0.0]


def test_stepc_cell_order_matches_stepc_readout_arms():
    """The +44/42/68/70 mapping is only correct in scripts/stepc_readout.py's ARMS order."""
    names = [s[0].replace("\n", " ") for s in STEPC]
    assert names == [
        "Goedel miniF2F",
        "Goedel ProofNet#",
        "DeepSeek miniF2F",
        "DeepSeek ProofNet#",
    ]


def test_stepc_manipulation_fired_but_outcome_did_not():
    """The figure's whole argument: every cell's diversity rose, no cell's solve rate did."""
    assert all(s[1] >= 40 for s in STEPC)
    assert all(s[2] <= 1.5 for s in STEPC)
