#!/usr/bin/env python3
"""Phase 5 Task 5.1: build reclaim-and-reinvest candidate sets offline (no GPU).

For each baseline run, partition the unsolved-at-128k cells into extend (still progressing) vs
abandon (confidently trapped), compute the iso-compute reclaim/feasibility arithmetic, and emit the
stratified pilot list (~8-12 extend cells/model) for the Task 5.2 gate. Reports per-seed
extend/abandon counts — the per-seed split is the empirical question for whether DeepSeek's reinvest
margin survives where its allocation margin didn't (it is sign-safe by construction; the margin is
what the pilot/full run measures). Writes results/phase5/candidates.json.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from atp.alloc.extract import BASELINE_RUNS
from atp.alloc.features import load_cell_traces
from atp.alloc.reinvest import partition_run, stratified_pilot

ROOT = Path(__file__).resolve().parents[1]
PILOT_N = 10               # extend cells per model to probe in the gate (Task 5.2)
PILOT_E = 512_000          # extension budget for the pilot
FULL_E_LEVELS = (256_000, 512_000, 1_000_000)


def _decision_dict(d) -> dict:
    return {
        "problem_name": d.problem_name, "seed": d.seed, "is_extend": d.is_extend,
        "abandon_at": d.abandon_at, "reclaim": d.reclaim,
        "best_depth_128k": d.best_depth_128k, "n_attempts_128k": d.n_attempts_128k,
    }


def _per_seed(decisions) -> dict[int, int]:
    return dict(sorted(Counter(d.seed for d in decisions).items()))


def main() -> None:
    report = []
    for run_dir, model, benchmark in BASELINE_RUNS:
        d = ROOT / "results" / run_dir
        if not (d / "problems").exists():
            continue
        traces = load_cell_traces(d)
        sets = partition_run(traces, model, benchmark)
        # pilot: stratified sample of the extend set across the 128k depth range (only ProofNet#
        # really matters — miniF2F is the saturated contrast with a tiny extend set).
        pilot = stratified_pilot(sets.extend, PILOT_N, seed=0)
        feas = {str(E): sets.max_fundable_extensions(E) for E in FULL_E_LEVELS}
        report.append({
            "model": model, "benchmark": benchmark, "run_dir": run_dir,
            "n_cells": sets.n_cells, "n_solved": sets.n_solved, "n_unsolved": sets.n_unsolved,
            "n_extend": len(sets.extend), "n_abandon": len(sets.abandon),
            "extend_per_seed": _per_seed(sets.extend),
            "abandon_per_seed": _per_seed(sets.abandon),
            "total_reclaim": sets.total_reclaim,
            "max_fundable_extensions": feas,
            "pilot_E": PILOT_E, "pilot_n": len(pilot),
            "pilot_feasible_at_E": sets.feasible(PILOT_E, len(pilot)),
            "pilot_cells": [_decision_dict(p) for p in pilot],
            "extend": [_decision_dict(x) for x in sets.extend],
            "abandon": [_decision_dict(x) for x in sets.abandon],
        })

    out = ROOT / "results" / "phase5" / "candidates.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))

    for e in report:
        print(f"\n=== {e['model']:9s} × {e['benchmark']:14s} ===")
        print(f"  cells={e['n_cells']}  solved={e['n_solved']}  unsolved={e['n_unsolved']}  "
              f"-> extend={e['n_extend']}  abandon={e['n_abandon']}")
        print(f"  extend/seed  = {e['extend_per_seed']}")
        print(f"  abandon/seed = {e['abandon_per_seed']}")
        print(f"  reclaim = {e['total_reclaim']:,} tok   "
              f"max extensions fundable @E: {e['max_fundable_extensions']}")
        print(f"  PILOT: extend {e['pilot_n']} cells to {e['pilot_E']:,} "
              f"(feasible@iso-compute={e['pilot_feasible_at_E']})")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
