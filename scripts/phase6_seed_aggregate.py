#!/usr/bin/env python
"""Phase 6 3-seed read-out: per-seed pass@B + mean±std, PER MODEL, with PAIRED B-base deltas.

Aggregates the 3-seed eval matrix (seeds 0,1,2 x {base,A,B} x {miniF2F,ProofNet#}) into the
publishable null table. Seed-0 run dirs have the bare name (p6eval_<m>_<short>_<arm>); seeds 1,2
carry the _s<seed> suffix. Reports, per (model, benchmark, budget):
  - pass@B mean±std across seeds for base/A/B
  - PAIRED delta B-base and A-base computed per seed then averaged (mean±std) -- the headline null
    statistic (pairing removes the per-seed sampling-luck shared by all arms at that seed).

Pre-registered null (locked at seed-0, two-model): B-base ~ 0 (flat-to-slightly-negative, never
>=+3pp) with low closing-token loss => execution floor is sampling/exposure-bound, not liftable by
closing-targeted SFT. A (generic RFT) actively hurts. This script turns that into per-seed bars.

Usage:
  python scripts/phase6_seed_aggregate.py            # both models
  python scripts/phase6_seed_aggregate.py --model d  # one model
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"

_BENCH_SHORT = {"minif2f": "mf", "proofnet": "pn"}
BUDGETS = [8000, 32000]
SEEDS = [0, 1, 2]
ARMS = ("base", "A", "B")


def _run_dir(model: str, short: str, arm: str, seed: int) -> Path:
    name = f"p6eval_{model}_{short}_{arm}"
    if seed != 0:
        name += f"_s{seed}"
    return RESULTS / name


def _load_cells(run_dir: Path) -> dict[str, dict]:
    pdir = run_dir / "problems"
    if not pdir.is_dir():
        return {}
    out = {}
    for p in sorted(pdir.glob("*.json")):
        c = json.loads(p.read_text())
        out[c.get("problem_name", p.stem)] = c
    return out


def _solved_within(cell: dict, b: int) -> bool:
    tts = cell.get("tokens_to_solve")
    return tts is not None and tts <= b


def _pass(cells: dict, b: int) -> float | None:
    if not cells:
        return None
    return sum(_solved_within(c, b) for c in cells.values()) / len(cells)


def _ms(xs: list[float]) -> str:
    if not xs:
        return "    --   "
    if len(xs) == 1:
        return f"{xs[0]*100:5.1f}%   "
    return f"{statistics.mean(xs)*100:5.1f}±{statistics.stdev(xs)*100:.1f}"


def _paired_deltas(model, short, b) -> dict[str, list[float]]:
    """Per-seed paired (arm - base) at budget b, computed over the INTERSECTION of problems present
    in BOTH that arm and base at that seed (so a partially-complete arm is never compared against a
    different problem subset). At full completion the intersection == the full set."""
    out = {"A": [], "B": []}
    for seed in SEEDS:
        base = _load_cells(_run_dir(model, short, "base", seed))
        if not base:
            continue
        for arm in ("A", "B"):
            cells = _load_cells(_run_dir(model, short, arm, seed))
            if not cells:
                continue
            common = base.keys() & cells.keys()
            if not common:
                continue
            pb = sum(_solved_within(base[k], b) for k in common) / len(common)
            pa = sum(_solved_within(cells[k], b) for k in common) / len(common)
            out[arm].append(pa - pb)
    return out


def _report_model(model: str) -> None:
    mname = "goedel" if model == "g" else "deepseek"
    print(f"\n##### model={mname} #####")
    for bench, short in _BENCH_SHORT.items():
        print(f"\n=== {bench} (held-out) ===")
        # availability line
        avail = {
            arm: [s for s in SEEDS if _load_cells(_run_dir(model, short, arm, s))]
            for arm in ARMS
        }
        ncells = {
            arm: {s: len(_load_cells(_run_dir(model, short, arm, s))) for s in avail[arm]}
            for arm in ARMS
        }
        print("  seeds present: " + " | ".join(f"{arm}={avail[arm]}{ncells[arm]}" for arm in ARMS))
        print(f"  {'arm':>5} " + " ".join(f"pass@{b}".rjust(13) for b in BUDGETS))
        for arm in ARMS:
            row = f"  {arm:>5} "
            for b in BUDGETS:
                xs = [v for s in avail[arm] if (v := _pass(_load_cells(_run_dir(model, short, arm, s)), b)) is not None]
                row += f"  {_ms(xs):>11}"
            print(row)
        for b in BUDGETS:
            d = _paired_deltas(model, short, b)
            seg = []
            for arm in ("A", "B"):
                xs = d[arm]
                if xs:
                    m = statistics.mean(xs) * 100
                    s = statistics.stdev(xs) * 100 if len(xs) > 1 else 0.0
                    seg.append(f"{arm}-base={m:+.1f}±{s:.1f}pp (n={len(xs)})")
                else:
                    seg.append(f"{arm}-base=--")
            print(f"    paired@{b}: " + "  ".join(seg))
    print(
        "\nNull check (pre-registered): B-base mean ~0, never >=+3pp robust => sampling/exposure-bound "
        "floor; A-base negative => generic RFT hurts."
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["g", "d"], help="omit for both")
    args = ap.parse_args()
    for m in ([args.model] if args.model else ["g", "d"]):
        _report_model(m)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
