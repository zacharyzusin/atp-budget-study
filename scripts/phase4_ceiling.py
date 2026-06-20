#!/usr/bin/env python3
"""Task 4.1 check-in: tokens_to_solve distribution + oracle headroom ceiling, all four baselines.

CPU-only, offline. For each (model, benchmark) baseline run it reports:
  - the solve-cost distribution among solved cells (where the reclaimable budget lives),
  - uniform pass@b on the grid (sanity vs logged metrics),
  - EFFICIENCY ceiling: oracle's min total budget to match uniform's max-budget solve rate -> %
    compute the oracle could save at equal accuracy,
  - ACCURACY ceiling: at each fixed total budget T=N*b, oracle solves vs uniform solves (extra
    solves and Δpp) -> the upside the oracle could buy at equal compute.

The oracle is the unrealizable upper bound; this only tells us whether there is headroom worth
chasing with the realizable policies (Tasks 4.2-4.3). Writes results/phase4/ceiling.json.
"""

from __future__ import annotations

import json
import statistics as st
from pathlib import Path

from atp.alloc.extract import load_baselines
from atp.alloc.policies import BMAX, oracle_min_T_to_match, oracle_solved, uniform_solved

GRID = [2000, 8000, 32000, 128000]
ROOT = Path(__file__).resolve().parents[1]


def _pct(xs: list[float], q: float) -> float:
    if not xs:
        return float("nan")
    xs = sorted(xs)
    i = min(len(xs) - 1, int(q * len(xs)))
    return xs[i]


def main() -> None:
    tables = load_baselines(ROOT / "results")
    report = []
    for tbl in tables:
        costs = tbl.costs
        n = tbl.n_cells
        finite = sorted(c for c in costs if c <= BMAX)
        n_solved = len(finite)

        T_max = n * BMAX  # uniform's total compute at the max per-cell budget (b=128k)
        # EFFICIENCY: oracle funds the cheapest cells; to match uniform's max-budget solve count
        # (= all n_solved solvable cells) it needs only the sum of their costs.
        T_match = oracle_min_T_to_match(costs, n_solved)
        eff_saved = 1.0 - T_match / T_max if T_max else 0.0

        # ACCURACY: at each fixed total budget T = n*b, compare oracle vs uniform solve counts.
        acc = []
        for b in GRID:
            T = n * b
            uni = uniform_solved(costs, T)
            ora = oracle_solved(costs, T)
            acc.append({
                "budget_per_cell": b, "total_T": T,
                "uniform_solved": uni, "oracle_solved": ora,
                "uniform_pass": uni / n, "oracle_pass": ora / n,
                "extra_solves": ora - uni, "delta_pp": 100.0 * (ora - uni) / n,
            })

        entry = {
            "model": tbl.model, "benchmark": tbl.benchmark, "run_dir": tbl.run_dir,
            "n_cells": n, "n_solved": n_solved, "solve_rate": n_solved / n,
            "cost_distribution": {
                "min": finite[0] if finite else None,
                "p25": _pct(finite, 0.25), "median": st.median(finite) if finite else None,
                "p75": _pct(finite, 0.75), "p90": _pct(finite, 0.90),
                "max": finite[-1] if finite else None,
                "mean": st.fmean(finite) if finite else None,
                "sum_finite": sum(finite),
            },
            "efficiency_ceiling": {
                "uniform_T_at_128k": T_max, "oracle_T_to_match": T_match,
                "compute_saved_frac": eff_saved,
            },
            "accuracy_ceiling": acc,
        }
        report.append(entry)

    out = ROOT / "results" / "phase4" / "ceiling.json"
    out.write_text(json.dumps(report, indent=2))

    # ---- human-readable summary ----
    for e in report:
        d = e["cost_distribution"]
        print(f"\n=== {e['model']:9s} × {e['benchmark']:14s}  "
              f"({e['n_cells']} cells, solved {e['n_solved']} = {100*e['solve_rate']:.1f}%) ===")
        if e["n_solved"]:
            print(f"  solve-cost tokens: min {d['min']:.0f}  p25 {d['p25']:.0f}  "
                  f"med {d['median']:.0f}  p75 {d['p75']:.0f}  p90 {d['p90']:.0f}  "
                  f"max {d['max']:.0f}")
        ec = e["efficiency_ceiling"]
        print(f"  EFFICIENCY ceiling: oracle matches uniform@128k using "
              f"{ec['oracle_T_to_match']/1e6:.2f}M vs {ec['uniform_T_at_128k']/1e6:.1f}M tokens "
              f"-> {100*ec['compute_saved_frac']:.1f}% compute saved")
        print("  ACCURACY ceiling (oracle vs uniform at equal total compute):")
        for a in e["accuracy_ceiling"]:
            print(f"    T=N×{a['budget_per_cell']:>6}: uniform {100*a['uniform_pass']:5.1f}%  "
                  f"oracle {100*a['oracle_pass']:5.1f}%  (+{a['extra_solves']} solves, "
                  f"{a['delta_pp']:+.1f}pp)")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
