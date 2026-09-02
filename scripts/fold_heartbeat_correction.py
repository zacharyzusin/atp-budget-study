#!/usr/bin/env python3
"""Fold the 13 maxHeartbeats re-verify flips (audit Check B) into the headline pass@B curves.

Arithmetic only -- no GPU, no new generation, no re-verification. Every flipped cell's correct proof
was already present in the ORIGINAL Phase 0-7 sweep output; the audit only re-scored it under
`set_option maxHeartbeats 0`. See `results/audit/AUDIT_FINDINGS.md` Task B.

Method: recompute pass@B directly from the per-problem records (a cell counts as solved at budget B
iff `tokens_to_solve <= B`), first WITHOUT corrections -- which must reproduce the published
`metrics.json` exactly, or the corrected numbers cannot be trusted -- then WITH the 13 flips applied
at their measured `tokens_to_solve`.

Because the fix strictly widens what counts as solved, no corrected number can move down.

Usage: python scripts/fold_heartbeat_correction.py
Writes results/audit/HEARTBEAT_CORRECTED_CURVES.md and .json.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUDGETS = (2000, 8000, 32000, 128000)

# The 13 flipped cells, with the tokens_to_solve measured by the re-verify.
# Sources: logs/audit-trapped-11473232.out (Goedel x miniF2F), 11479253 (Goedel x ProofNet#),
# 11479255 (DeepSeek x ProofNet#, zero flips), and
# results/deepseek_minif2f_baseline/audit_checkpoint.jsonl (DeepSeek x miniF2F).
FLIPS: dict[str, list[tuple[str, int, int]]] = {
    "baseline": [  # Goedel x miniF2F
        ("algebra_apbon2pownleqapownpbpowon2", 0, 96172),
        ("amc12a_2020_p15", 0, 105491),
        ("amc12a_2020_p15", 2, 6710),
    ],
    "proofnet_baseline": [  # Goedel x ProofNet#
        ("Ireland__Rosen__exercise_12_12", 1, 74523),
        ("Rudin__exercise_4_4b", 2, 10480),
        ("Rudin__exercise_5_5", 2, 40867),
    ],
    "deepseek_minif2f_baseline": [  # DeepSeek x miniF2F
        ("amc12_2001_p21", 0, 9044),
        ("amc12_2001_p21", 1, 42762),
        ("amc12_2001_p21", 2, 46680),
        ("amc12a_2020_p15", 0, 47506),
        ("amc12a_2020_p15", 1, 22512),
        ("imo_1962_p2", 0, 75646),
        ("imo_1962_p2", 2, 68446),
    ],
    "deepseek_proofnet_baseline": [],  # the sole zero-flip core
}

LABELS = {
    "baseline": "miniF2F x Goedel",
    "deepseek_minif2f_baseline": "miniF2F x DeepSeek",
    "proofnet_baseline": "ProofNet# x Goedel",
    "deepseek_proofnet_baseline": "ProofNet# x DeepSeek",
}


def load_cells(run_dir: Path) -> dict[tuple[str, int], float | None]:
    """(problem, seed) -> tokens_to_solve, or None if the cell never solved."""
    cells: dict[tuple[str, int], float | None] = {}
    for f in sorted((run_dir / "problems").glob("*.json")):
        d = json.loads(f.read_text())
        key = (d["problem_name"], int(d["seed"]))
        cells[key] = d.get("tokens_to_solve") if d.get("solved") else None
    return cells


def pass_at_b(cells: dict[tuple[str, int], float | None], seeds: list[int]) -> dict[int, tuple]:
    """Per-budget (mean, std, per-seed rates) over the given seeds."""
    out = {}
    for b in BUDGETS:
        rates = []
        for s in seeds:
            sub = [v for (_, sd), v in cells.items() if sd == s]
            solved = sum(1 for v in sub if v is not None and v <= b)
            rates.append(solved / len(sub))
        # Sample std (n-1), matching the project's convention throughout -- population std would
        # silently shrink every reported +/- by sqrt((n-1)/n) = 0.82 at n=3 and look like a result.
        out[b] = (
            statistics.mean(rates),
            statistics.stdev(rates) if len(rates) > 1 else 0.0,
            rates,
        )
    return out


def main() -> None:
    report = {}
    for run, flips in FLIPS.items():
        d = ROOT / "results" / run
        cells = load_cells(d)
        seeds = sorted({s for _, s in cells})
        # The published headline uses 3 seeds even where more were later collected (WS1.1).
        head_seeds = seeds[:3]

        before = pass_at_b(cells, head_seeds)

        # sanity: does the uncorrected recompute reproduce the committed metrics.json?
        # Reproduce BOTH mean and std -- a mean-only check would have missed the
        # sample-vs-population std discrepancy that this script originally had.
        pub = {
            int(e["budget"]): (e["mean"], e["std"])
            for e in json.loads((d / "metrics.json").read_text())["pass_at_b"]
        }
        published = {b: v[0] for b, v in pub.items()}
        repro = {
            b: (abs(before[b][0] - pub[b][0]) < 5e-4 and abs(before[b][1] - pub[b][1]) < 5e-4)
            for b in BUDGETS
            if b in pub
        }

        corrected = dict(cells)
        applied, skipped = [], []
        for name, seed, toks in flips:
            key = (name, seed)
            if key not in corrected:
                skipped.append((name, seed, "cell not found"))
                continue
            if corrected[key] is not None:
                skipped.append((name, seed, f"already solved at {corrected[key]}"))
                continue
            corrected[key] = toks
            applied.append((name, seed, toks))

        after = pass_at_b(corrected, head_seeds)
        report[run] = {
            "label": LABELS[run],
            "n_problems": len(cells) // len(seeds),
            "seeds_used": head_seeds,
            "reproduces_published": repro,
            "published": published,
            "before": {b: before[b][:2] for b in BUDGETS},
            "after": {b: after[b][:2] for b in BUDGETS},
            "per_seed_after": {b: after[b][2] for b in BUDGETS},
            "flips_applied": applied,
            "flips_skipped": skipped,
        }

    (ROOT / "results" / "audit" / "HEARTBEAT_CORRECTED_CURVES.json").write_text(
        json.dumps(report, indent=2, default=str)
    )

    lines = [
        "# maxHeartbeats correction folded into the headline pass@B curves",
        "",
        "Arithmetic only (audit Check B). Every flipped cell's correct proof was already "
        "present in the original sweep; the audit re-scored it under "
        "`set_option maxHeartbeats 0`. Because the fix strictly widens what counts as solved, "
        "no number here can move down.",
        "",
        "Generated by `scripts/fold_heartbeat_correction.py`.",
        "",
    ]
    for run, r in report.items():
        ok = all(r["reproduces_published"].values())
        lines += [
            f"## {r['label']}  (`results/{run}`)",
            "",
            f"- Seeds used: {r['seeds_used']}; problems: {r['n_problems']}",
            f"- Uncorrected recompute reproduces committed `metrics.json`: "
            f"**{'YES' if ok else 'NO -- ' + str(r['reproduces_published'])}**",
            f"- Flips applied: {len(r['flips_applied'])}"
            + (f"; skipped: {r['flips_skipped']}" if r["flips_skipped"] else ""),
            "",
            "| budget | published | corrected | delta |",
            "|---|---|---|---|",
        ]
        for b in BUDGETS:
            bm, bs = r["before"][b]
            am, asd = r["after"][b]
            lines.append(
                f"| {b // 1000}k | {bm * 100:.1f}% ± {bs * 100:.1f}% "
                f"| **{am * 100:.1f}% ± {asd * 100:.1f}%** "
                f"| {'+' if am >= bm else ''}{(am - bm) * 100:.1f}pp |"
            )
        lines.append("")
    out = ROOT / "results" / "audit" / "HEARTBEAT_CORRECTED_CURVES.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
