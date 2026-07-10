#!/usr/bin/env python3
"""Phase 8 step 4 — matched-pair floor table for the DeepSeek-Prover-V1.5 Base/SFT/RL triple.

The sweep is still in flight (an ongoing cluster sweep, not a finished one), so different stages have
completed different subsets of cells so far. Two things this module does, both in the same spirit as
`scripts/h1_intersection.py`'s cross-pin fairness discipline:

1. `seed_balance_report` — before trusting ANY comparison, check that each seed actually has
   substantial, comparable coverage (not "seed 0 100%, seeds 1/2 untouched", which would silently
   bias a floor read toward whatever seed 0 happens to look like).
2. `pass_at_b_on_common_subset` — restrict every stage's pass@B, per seed, to the INTERSECTION of
   problem names all stages have already completed for that seed, so the comparison is apples-to-
   apples on already-computed cells rather than mixing in each stage's own arbitrary in-progress
   subset.
"""
import glob
import json
import os
import statistics as st
from dataclasses import dataclass, field


def completed_names_by_seed(run_dir):
    """seed -> set of problem names with a written cell (attempted, whether solved or not)."""
    out = {}
    for f in glob.glob(os.path.join(run_dir, "problems", "*.json")):
        with open(f) as fh:
            d = json.load(fh)
        out.setdefault(d["seed"], set()).add(d["problem_name"])
    return out


@dataclass
class SeedBalanceReport:
    counts: dict
    is_badly_imbalanced: bool


def seed_balance_report(run_dir, expected_seeds, expected_total_per_seed, min_fraction=0.10):
    """Flag the "all of one seed, none of the rest" failure mode: any expected seed with fewer than
    `min_fraction` of its target cells present (default 10%) counts as effectively missing.
    Badly imbalanced = at least one seed present at a normal level AND at least one seed missing.
    """
    by_seed = completed_names_by_seed(run_dir)
    counts = {s: len(by_seed.get(s, set())) for s in expected_seeds}
    threshold = expected_total_per_seed * min_fraction
    present = [s for s, n in counts.items() if n >= threshold]
    missing = [s for s, n in counts.items() if n < threshold]
    is_badly_imbalanced = len(present) > 0 and len(missing) > 0
    return SeedBalanceReport(counts=counts, is_badly_imbalanced=is_badly_imbalanced)


def _load_cells(run_dir):
    cells = []
    for f in glob.glob(os.path.join(run_dir, "problems", "*.json")):
        with open(f) as fh:
            d = json.load(fh)
        cells.append((d["problem_name"], d["seed"], bool(d["solved"]), d.get("tokens_to_solve")))
    return cells


@dataclass
class FloorTableResult:
    common_names_by_seed: dict
    pass_at_b: dict = field(default_factory=dict)  # stage -> budget -> (mean, std, n_seeds)
    per_seed_pass_at_b: dict = field(default_factory=dict)  # stage -> budget -> {seed: pct}


def pass_at_b_on_common_subset(stage_run_dirs, budgets):
    """stage_run_dirs: {stage_label: run_dir}. Restricts each seed's comparison across ALL stages to
    the intersection of problem names every stage has already completed for that seed.
    """
    by_stage_seed_names = {
        stage: completed_names_by_seed(run_dir) for stage, run_dir in stage_run_dirs.items()
    }
    all_seeds = set()
    for seed_map in by_stage_seed_names.values():
        all_seeds |= set(seed_map.keys())

    common_names_by_seed = {}
    for seed in sorted(all_seeds):
        name_sets = [
            seed_map.get(seed, set()) for seed_map in by_stage_seed_names.values()
        ]
        common_names_by_seed[seed] = set.intersection(*name_sets) if name_sets else set()

    cells_by_stage = {stage: _load_cells(run_dir) for stage, run_dir in stage_run_dirs.items()}

    pass_at_b = {}
    per_seed_pass_at_b = {}
    for stage, cells in cells_by_stage.items():
        pass_at_b[stage] = {}
        per_seed_pass_at_b[stage] = {}
        cell_lookup = {(name, seed): (solved, tts) for name, seed, solved, tts in cells}
        for b in budgets:
            per_seed_pct = {}
            for seed, names in common_names_by_seed.items():
                if not names:
                    continue
                n_solved = sum(
                    1
                    for name in names
                    if cell_lookup.get((name, seed), (False, None))[0]
                    and cell_lookup[(name, seed)][1] is not None
                    and cell_lookup[(name, seed)][1] <= b
                )
                per_seed_pct[seed] = round(100.0 * n_solved / len(names), 1)
            per_seed_pass_at_b[stage][b] = per_seed_pct
            vals = list(per_seed_pct.values())
            mean = round(st.fmean(vals), 1) if vals else 0.0
            std = round(st.stdev(vals), 1) if len(vals) >= 2 else 0.0
            pass_at_b[stage][b] = (mean, std, len(vals))

    return FloorTableResult(
        common_names_by_seed=common_names_by_seed,
        pass_at_b=pass_at_b,
        per_seed_pass_at_b=per_seed_pass_at_b,
    )
