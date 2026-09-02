"""Phase 8 step 4 — matched-pair floor table for the DeepSeek-Prover-V1.5 Base/SFT/RL triple.

Only a fair, apples-to-apples read: for a given (benchmark, seed), the three stages have generally
completed DIFFERENT subsets of cells so far (an in-flight sweep, not a finished one). Comparing raw
pass@B percentages over each stage's own (different-sized) completed set would bias the read if the
still-unrun problems aren't a random sample. So we restrict every stage, per seed, to the
INTERSECTION
of problem names that ALL THREE stages have already completed for that seed — the same discipline
`scripts/h1_intersection.py` already uses for cross-pin fairness, applied here across training
stages
on a partially-completed sweep instead.
"""

import json
import os

from scripts.phase8_floor_table import (
    completed_names_by_seed,
    pass_at_b_on_common_subset,
    seed_balance_report,
)


def _write_cell(run_dir, name, seed, solved, tokens_to_solve, budget=32000):
    d = os.path.join(run_dir, "problems")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"{name}__seed{seed}.json"), "w") as f:
        json.dump(
            {
                "problem_name": name,
                "seed": seed,
                "solved": solved,
                "tokens_to_solve": tokens_to_solve,
                "budget": budget,
            },
            f,
        )


def test_completed_names_by_seed(tmp_path):
    run = str(tmp_path / "run")
    _write_cell(run, "a", 0, True, 2000)
    _write_cell(run, "b", 0, False, None)
    _write_cell(run, "a", 1, False, None)
    names = completed_names_by_seed(run)
    assert names == {0: {"a", "b"}, 1: {"a"}}


def test_pass_at_b_on_common_subset_restricts_to_intersection(tmp_path):
    base = str(tmp_path / "base")
    rl = str(tmp_path / "rl")
    # base has 3 problems done for seed 0; rl only has 2 of them (an in-flight sweep) — the
    # comparison must restrict to the 2 in common, not silently use base's extra problem.
    _write_cell(base, "a", 0, True, 2000)
    _write_cell(base, "b", 0, True, 8000)
    _write_cell(base, "c", 0, False, None)
    _write_cell(rl, "a", 0, True, 2000)
    _write_cell(rl, "b", 0, False, None)

    result = pass_at_b_on_common_subset({"base": base, "rl": rl}, budgets=[2000, 8000, 32000])
    assert result.common_names_by_seed[0] == {"a", "b"}
    # base: pass@2000 = 1/2 (only "a" solved by 2000); pass@8000 = 2/2 ("b" solved by 8000 too)
    assert result.pass_at_b["base"][2000][0] == (100.0 * 1 / 2)
    assert result.pass_at_b["base"][8000][0] == (100.0 * 2 / 2)
    # rl: pass@2000 = 1/2, pass@8000 = 1/2 (b never solved)
    assert result.pass_at_b["rl"][2000][0] == (100.0 * 1 / 2)
    assert result.pass_at_b["rl"][8000][0] == (100.0 * 1 / 2)


def test_pass_at_b_reports_per_seed_not_just_pooled(tmp_path):
    base = str(tmp_path / "base")
    rl = str(tmp_path / "rl")
    for seed in (0, 1):
        _write_cell(base, "a", seed, True, 2000)
        _write_cell(rl, "a", seed, True, 2000)
    result = pass_at_b_on_common_subset({"base": base, "rl": rl}, budgets=[2000])
    assert set(result.common_names_by_seed.keys()) == {0, 1}
    assert result.per_seed_pass_at_b["base"][2000] == {0: 100.0, 1: 100.0}


def test_seed_balance_report_flags_missing_seeds(tmp_path):
    run = str(tmp_path / "run")
    _write_cell(run, "a", 0, True, 2000)
    _write_cell(run, "b", 0, True, 2000)
    # no seed 1 or 2 at all — the exact "all of seed 0, none of the rest" bad case
    report = seed_balance_report(run, expected_seeds=[0, 1, 2], expected_total_per_seed=10)
    assert report.counts == {0: 2, 1: 0, 2: 0}
    assert report.is_badly_imbalanced is True


def test_seed_balance_report_passes_when_all_seeds_present_with_reasonable_spread(tmp_path):
    run = str(tmp_path / "run")
    for seed, n in [(0, 8), (1, 5), (2, 4)]:
        for i in range(n):
            _write_cell(run, f"p{i}", seed, False, None)
    report = seed_balance_report(run, expected_seeds=[0, 1, 2], expected_total_per_seed=10)
    assert report.counts == {0: 8, 1: 5, 2: 4}
    assert report.is_badly_imbalanced is False


def test_real_repo_seed_balance_report_runs_cleanly_on_live_run_dirs():
    """Not a frozen-state assertion (the sweep is live and its cell counts change between runs of
    this test) — just confirms `seed_balance_report` runs against the real run dirs without error
    and
    returns a well-formed report. The actual imbalance READING (which stage/benchmark passes or
    fails
    the balance check right now) belongs in PROGRESS.md/ZOO.md as a dated finding, not as a test
    assertion that would go stale the moment the sweep advances another cell."""
    for run_dir, target in [
        ("results/p8battery_deepseek_v15_rl_minif2f", 244),
        ("results/p8battery_deepseek_v15_rl_proofnet", 186),
    ]:
        if not os.path.isdir(os.path.join(run_dir, "problems")):
            return
        report = seed_balance_report(
            run_dir, expected_seeds=[0, 1, 2], expected_total_per_seed=target
        )
        assert set(report.counts.keys()) == {0, 1, 2}
        assert isinstance(report.is_badly_imbalanced, bool)
