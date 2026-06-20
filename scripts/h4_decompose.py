#!/usr/bin/env python3
"""H4 — decompose the OOD cross-model dichotomy (DeepSeek > Goedel on ProofNet#) through the F1/F3 lens.

Question: does DeepSeek's OOD advantage come from (a) LESS diversity collapse (explores more viable
approaches) or (b) DEEPER within-approach execution (closes goals Goedel stalls on with the same approach)?

Two views:
 1. WIN ATTRIBUTION (causal): for each problem DeepSeek solves but Goedel does not, look at DeepSeek's
    winning opening tactic + skeleton. Did Goedel ever TRY that same approach on that problem?
       - Goedel tried it (same opening) and still failed  -> DeepSeek won by deeper EXECUTION (b)
       - Goedel never tried that opening                  -> DeepSeek won by a different APPROACH (a)
 2. MATCHED-DIFFICULTY aggregate: on the SHARED-FAIL set (problems BOTH models fail on all seeds; removes
    survivorship), compare distinct openings/attempt (F1) and deepest-step-reached (F3) across models.
"""
import glob, json, os, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(__file__))
from analyze_mechanism import first_tactic, skeleton, deepest_step
import statistics as st

def load(run):
    """problem -> {'solved_by_seed': {seed: bool}, 'attempts_all': [...], 'solve_openings': set,
                   'all_openings': set, 'cells': [(seed, attempts, solved)]}"""
    P = defaultdict(lambda: {"solve_openings": set(), "all_openings": set(), "deepest": [],
                             "solved": False, "cells": 0, "solved_cells": 0})
    for f in sorted(glob.glob(os.path.join(run, "agent_states", "*.json"))):
        try: d = json.load(open(f))
        except (json.JSONDecodeError, ValueError): continue
        name = d.get("theorem_name") or os.path.basename(f).split("__seed")[0]
        att = d.get("attempts", [])
        e = P[name]; e["cells"] += 1
        solved_here = False
        for a in att:
            op = first_tactic(a.get("proof", ""))
            if op: e["all_openings"].add(op)
            if a.get("reason") == "ok":
                solved_here = True; e["solved"] = True
                if op: e["solve_openings"].add(op)
        if solved_here: e["solved_cells"] += 1
        if not solved_here and att:
            e["deepest"].append(deepest_step(att))
    return P

G = load("results/proofnet_baseline")
D = load("results/deepseek_proofnet_baseline")
names = set(G) & set(D)

# ---- View 1: win attribution on DeepSeek-only wins ----
ds_only = sorted(n for n in names if D[n]["solved"] and not G[n]["solved"])
exec_win = approach_win = 0; rows = []
for n in ds_only:
    ds_ops = D[n]["solve_openings"]
    goedel_tried = G[n]["all_openings"]
    overlap = ds_ops & goedel_tried
    if overlap:
        exec_win += 1; verdict = "EXECUTION (Goedel tried same opening, failed)"
    else:
        approach_win += 1; verdict = "APPROACH (Goedel never tried this opening)"
    rows.append((n, sorted(ds_ops)[:3], verdict))

print("===== H4 ProofNet# OOD dichotomy decomposition =====")
print(f"problems: shared={len(names)}  Goedel-solves={sum(G[n]['solved'] for n in names)}  "
      f"DeepSeek-solves={sum(D[n]['solved'] for n in names)}  DeepSeek-only-wins={len(ds_only)}\n")
print(f"WIN ATTRIBUTION over the {len(ds_only)} DeepSeek-only wins:")
print(f"  EXECUTION (Goedel tried DeepSeek's winning opening but failed): {exec_win}  "
      f"({100*exec_win/max(1,len(ds_only)):.0f}%)")
print(f"  APPROACH  (Goedel never tried DeepSeek's winning opening):      {approach_win}  "
      f"({100*approach_win/max(1,len(ds_only)):.0f}%)")
print("  (sample:)")
for n, ops, v in rows[:12]:
    print(f"    {n:40s} ds_open={ops} -> {v}")

# ---- View 2: matched-difficulty aggregate on shared-fail set ----
shared_fail = [n for n in names if not G[n]["solved"] and not D[n]["solved"]]
def agg(P, nameset):
    opens = [len(P[n]["all_openings"]) for n in nameset]
    deep = [st.mean(P[n]["deepest"]) for n in nameset if P[n]["deepest"]]
    return st.mean(opens), st.median(deep)
go, gd = agg(G, shared_fail); do, dd = agg(D, shared_fail)
print(f"\nMATCHED-DIFFICULTY (shared-fail set, n={len(shared_fail)} problems both models miss):")
print(f"  F1 distinct openings/problem:  Goedel {go:.2f}   DeepSeek {do:.2f}")
print(f"  F3 median deepest-step reached: Goedel {gd:.1f}   DeepSeek {dd:.1f}")
