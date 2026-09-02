#!/usr/bin/env python3
"""Phase 2 Step C readout: budget-matched manipulation check + solve flips + failure texture +
soundness
guard, for all 4 diversity arms vs their baselines. CPU-only, reads results/*/agent_states/*.json.

Manipulation check is BUDGET-MATCHED: both baseline and diversity attempts are truncated to
cumulative
completion_tokens <= 32000 before counting distinct opening tactics, so the comparison is not
confounded
by the baseline running to 128k (far more attempts => more distinct tactics for free).
"""

import glob
import json
import os
import statistics as st
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from analyze_mechanism import _classify, first_tactic  # reuse the validated helpers

BUDGET = 32000


def load_trunc(run_dir, names=None, budget=BUDGET):
    """Yield per-cell dicts with attempts truncated to cumulative completion_tokens <= budget."""
    cells = []
    for f in sorted(glob.glob(os.path.join(run_dir, "agent_states", "*.json"))):
        try:
            d = json.load(open(f))
        except (json.JSONDecodeError, ValueError):
            continue
        name = d.get("theorem_name") or os.path.basename(f).split("__seed")[0]
        if names is not None and name not in names:
            continue
        kept, cum = [], 0
        for a in d.get("attempts", []):
            if cum >= budget:  # no budget left to START this attempt
                break
            kept.append(a)
            cum += a.get("completion_tokens", 0)
        cells.append(
            {
                "name": name,
                "file": os.path.basename(f),
                "attempts": kept,
                "solved": any(a.get("reason") == "ok" for a in kept),
            }
        )
    return cells


def manip(cells):
    """A1 on unsolved cells: distinct opening tactics, attempts, and distinct/attempt ratio."""
    dist, att = [], []
    for c in cells:
        if c["solved"]:
            continue
        fts = [first_tactic(a.get("proof", "")) for a in c["attempts"]]
        fts = [t for t in fts if t]
        if not c["attempts"]:
            continue
        dist.append(len(set(fts)))
        att.append(len(c["attempts"]))
    if not dist:
        return None
    return {
        "n": len(dist),
        "distinct": round(st.mean(dist), 3),
        "attempts": round(st.mean(att), 2),
        "distinct_per_attempt": round(st.mean(dist) / st.mean(att), 3),
    }


def texture(cells):
    """Failure-category fractions over the LAST attempt
    of each unsolved cell (the giving-up state)."""
    from collections import Counter

    c = Counter()
    for cell in cells:
        if cell["solved"] or not cell["attempts"]:
            continue
        last = cell["attempts"][-1]
        c[_classify(last.get("reason", ""), last.get("feedback", ""))] += 1
    tot = sum(c.values()) or 1
    return {k: round(100 * v / tot, 1) for k, v in c.most_common()}, tot


def soundness(cells):
    """Fraction of ALL attempts that are loophole_sorry / truncation / formalization_syntax (the
    verifier-soundness-relevant failure modes). Diversity must NOT inflate these vs baseline."""
    from collections import Counter

    c = Counter()
    n = 0
    for cell in cells:
        for a in cell["attempts"]:
            c[_classify(a.get("reason", ""), a.get("feedback", ""))] += 1
            n += 1
    n = n or 1
    return {
        k: round(100 * c.get(k, 0) / n, 2)
        for k in ("loophole_sorry", "truncation", "formalization_syntax")
    }


ARMS = [
    (
        "Goedel  miniF2F",
        "results/baseline",
        "results/diversity_minif2f",
        "scratch/phase2/trapped_minif2f.txt",
    ),
    (
        "Goedel  ProofNet#",
        "results/proofnet_baseline",
        "results/diversity_proofnet",
        "scratch/phase2/trapped_proofnet.txt",
    ),
    (
        "DeepSeek miniF2F",
        "results/deepseek_minif2f_baseline",
        "results/diversity_minif2f_deepseek",
        "scratch/phase2/trapped_minif2f_deepseek.txt",
    ),
    (
        "DeepSeek ProofNet#",
        "results/deepseek_proofnet_baseline",
        "results/diversity_proofnet_deepseek",
        "scratch/phase2/trapped_proofnet_deepseek.txt",
    ),
]

for label, base_dir, div_dir, trap_file in ARMS:
    trapped = set(line.strip() for line in open(trap_file) if line.strip())
    base = load_trunc(base_dir, names=trapped)  # baseline truncated to 32k, restricted to trapped
    div = load_trunc(div_dir)  # diversity run already only-trapped, truncate to 32k
    mb, md = manip(base), manip(div)
    flips = sorted(set(c["file"] for c in div if c["solved"]))
    tb, ntb = texture(base)
    tdx, ntd = texture(div)
    print(f"\n===== {label}  (trapped={len(trapped)}) =====")
    print("  MANIP-CHECK @32k (budget-matched, unsolved cells):")
    print(
        f"    baseline : distinct_first_tac={mb['distinct']}  attempts={mb['attempts']}  "
        f"distinct/attempt={mb['distinct_per_attempt']}  (n={mb['n']})"
    )
    print(
        f"    diversity: distinct_first_tac={md['distinct']}  attempts={md['attempts']}  "
        f"distinct/attempt={md['distinct_per_attempt']}  (n={md['n']})"
    )
    print(
        f"  SOLVE FLIPS @32k (baseline=0 on trapped by construction): {len(flips)} cells solved by diversity"  # noqa: E501
    )
    for fl in flips:
        print(f"      + {fl}")
    print(f"  A2 TEXTURE (last-attempt failure %): baseline={tb}")
    print(f"                                       diversity={tdx}")
    print(f"  SOUNDNESS (all-attempt %, must not creep up): baseline={soundness(base)}")
    print(f"                                                diversity={soundness(div)}")
