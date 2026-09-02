#!/usr/bin/env python3
"""H3 — soundness-creep across ALL scaffolding components (generalizes Step C's C-3).

For every Phase 1 component (+ Step C diversity) vs the no-frills baseline, measure the rate at
which the
model emits attempts in the two UNSOUND modes the verifier audit fixed:
  - loophole  (reason='loophole'): proof carries sorry/admit-style holes
  - truncation (reason='no_goal'): bare-def / no-goal output a NAIVE verifier would accept as
    "compiles"
"unsound surface" = loophole + truncation = the would-be-false-positive rate a naive (un-hardened)
pipeline would be exposed to. Claim under test: scaffolding systematically inflates this surface.
All rates are per-FAILED-attempt (ok attempts excluded) so the comparison is about output quality.
"""
import glob
import json
import os
from collections import Counter

BENCHES = {
    "miniF2F":   "results/phase1_ablation",
    "ProofNet#": "results/phase1_proofnet",
}
COMPONENTS = ["baseline", "retrieval__1", "memory__1", "reviewer__1",
              "tactic_skeletons__1", "budget_alloc__0", "budget_alloc__2"]
# Step C diversity arms (different run dirs; their baselines are the full-budget baselines)
STEPC = {
    "miniF2F":   ("results/diversity_minif2f",          "results/baseline"),
    "ProofNet#": ("results/diversity_proofnet",         "results/proofnet_baseline"),
}

def rates(run):
    c = Counter()
    n = 0
    for f in glob.glob(os.path.join(run, "agent_states", "*.json")):
        try:
            d = json.load(open(f))
        except (json.JSONDecodeError, ValueError):
            continue
        for a in d.get("attempts", []):
            r = a.get("reason")
            if r == "ok":
                continue
            n += 1
            if r == "loophole":
                c["loophole"] += 1
            elif r == "no_goal":
                c["truncation"] += 1
    n = n or 1
    loop = 100 * c["loophole"] / n
    trunc = 100 * c["truncation"] / n
    return loop, trunc, loop + trunc, n

for bench, root in BENCHES.items():
    print(f"\n===== {bench} — unsound surface per component (per failed attempt) =====")
    print(f"  {'component':22s} {'loophole%':>9s} {'trunc%':>7s} {'UNSOUND%':>9s}  {'Δ vs base':>9s}  (n)")
    base = rates(os.path.join(root, "baseline"))
    base_surf = base[2]
    for comp in COMPONENTS:
        p = os.path.join(root, comp)
        if not os.path.isdir(p):
            continue
        loop, trunc, surf, n = rates(p)
        d = surf - base_surf
        flag = "  <== inflates" if d > 0.5 else ""
        print(f"  {comp:22s} {loop:9.2f} {trunc:7.2f} {surf:9.2f}  {d:+9.2f}  ({n}){flag}")
    # Step C diversity (full-budget baseline as reference)
    div_run, div_base = STEPC[bench]
    if os.path.isdir(div_run):
        bl = rates(div_base)
        dv = rates(div_run)
        print(f"  {'diversity (Step C)':22s} {dv[0]:9.2f} {dv[1]:7.2f} {dv[2]:9.2f}  {dv[2]-bl[2]:+9.2f}  ({dv[3]})"
              f"   [vs its own baseline {bl[2]:.2f}%]")
