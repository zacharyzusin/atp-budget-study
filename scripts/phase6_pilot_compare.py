#!/usr/bin/env python
"""Phase 6 Stage B pilot read-out: base vs A (RFT) vs B (closing-targeted).

Aggregates the six pilot eval arms and prints the base->A->B pass@B table at
each budget for both held-out benchmarks (miniF2F, ProofNet#), then states
whether the B effect matched the pre-registered exposure-bias / saturation
prediction.

Pre-registered prediction (locked before numbers landed):
  If the F2/F3 execution floor is sampling/exposure-bound, Stage B moves
  pass@B LITTLE because SFT optimizes an already-saturated conditional
  probability (closing-token loss ~0.06). Routing:
    (a) B lifts pass@B (>= +3pp, robust)        -> scale the harvest
    (b) B null BUT A-vs-B separates             -> partial signal, scale harvest
    (c) B flatly null (and ~== A)               -> sampling-bound DIAGNOSIS,
                                                   indicated lever is Stage C RL,
                                                   NOT harvest scale-up

Usage: run after all six arms leave the queue.
  python scripts/phase6_pilot_compare.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"

# (arm-label) -> (run-dir-name, config)
ARMS = {
    ("proofnet", "base"): "p6eval_g_pn_base",
    ("proofnet", "A"): "p6eval_g_pn_A",
    ("proofnet", "B"): "p6eval_g_pn_B",
    ("minif2f", "base"): "p6eval_g_mf_base",
    ("minif2f", "A"): "p6eval_g_mf_A",
    ("minif2f", "B"): "p6eval_g_mf_B",
}
BUDGETS = [8000, 32000]


def _load_cells(run_dir: Path) -> list[dict]:
    pdir = run_dir / "problems"
    if not pdir.is_dir():
        return []
    return [json.loads(p.read_text()) for p in sorted(pdir.glob("*.json"))]


def _solved_within(cell: dict, b: int) -> bool:
    tts = cell.get("tokens_to_solve")
    return tts is not None and tts <= b


def _pass_at_b(cells: list[dict], b: int) -> tuple[float, int]:
    """Fraction solved within b (single seed here) and n problems."""
    if not cells:
        return float("nan"), 0
    solved = sum(_solved_within(c, b) for c in cells)
    return solved / len(cells), len(cells)


def main() -> int:
    grid: dict[tuple, dict] = {}
    for (bench, arm), name in ARMS.items():
        cells = _load_cells(RESULTS / name)
        grid[(bench, arm)] = {
            "n": len(cells),
            **{b: _pass_at_b(cells, b) for b in BUDGETS},
        }

    for bench in ("minif2f", "proofnet"):
        print(f"\n=== {bench} (held-out) ===")
        header = f"{'arm':>5} {'n':>5} " + " ".join(f"pass@{b:>6}" for b in BUDGETS)
        print(header)
        for arm in ("base", "A", "B"):
            g = grid[(bench, arm)]
            cells_n = g["n"]
            row = f"{arm:>5} {cells_n:>5} "
            row += " ".join(
                f"{g[b][0]*100:9.1f}%" if cells_n else f"{'--':>10}" for b in BUDGETS
            )
            print(row)
        # deltas vs base
        for b in BUDGETS:
            base = grid[(bench, "base")][b][0]
            a = grid[(bench, "A")][b][0]
            bb = grid[(bench, "B")][b][0]
            if grid[(bench, "base")]["n"] and grid[(bench, "A")]["n"]:
                print(
                    f"  delta@{b}: A-base={(a-base)*100:+.1f}pp  "
                    f"B-base={(bb-base)*100:+.1f}pp  "
                    f"B-A={(bb-a)*100:+.1f}pp"
                    if grid[(bench, "B")]["n"]
                    else f"  delta@{b}: A-base={(a-base)*100:+.1f}pp  (B pending)"
                )
    print(
        "\nRouting key: B>=+3pp robust -> scale harvest | "
        "B~0 but B!=A -> partial, scale | B~0 and B~=A -> sampling-bound, Stage C RL."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
