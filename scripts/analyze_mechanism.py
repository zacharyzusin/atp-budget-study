#!/usr/bin/env python3
"""Phase 2 mechanism analysis — explain the budget→solve asymmetry from data on disk.

CPU-only, no GPU/Lean deps. Mines `results/<run>/agent_states/<problem>__seed<k>.json` (the full
per-attempt corpus: every attempt's generated `proof`, Lean `feedback`, `reason`, `kind`, tokens).

Four analyses (PHASE2_PLAN.md):
  A1 diversity  — distinct first-tactics / distinct skeletons across a cell's attempts vs solve
  outcome.
                  Flat pass@B = resampling the same wrong idea; tests if diversity collapses OOD.
  A2 taxonomy   — classify unsolved cells' failures: formalization / knowledge(hallucinated lemma) /
                  reasoning / near-miss / loophole / truncation. THIS GATES downstream GPU spend.
  A3 tokens     — tokens-to-solve CDF + unsolved fraction: long "almost" tail vs hard floor.
  A4 stratify   — solve rate by subfield (ProofNet# name prefix).

Usage:
  analyze_mechanism.py <run_dir> [<run_dir> ...] [--label name=dir ...] [--out results/phase2]
Each run_dir needs an agent_states/ subdir. Labels default to the dir basename.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import statistics as st
from collections import Counter, defaultdict

# ---------------------------------------------------------------- proof parsing
# Leading-identifier of a Lean tactic line. We only need a stable, comparable token, not a real
# parser.
_TAC_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_'.]*")

def _body(proof: str) -> str:
    """Text after the first `:= by` (or `:=`), i.e. the tactic block."""
    if not proof:
        return ""
    m = re.search(r":=\s*by\b", proof)
    if m:
        return proof[m.end():]
    m = re.search(r":=", proof)
    return proof[m.end():] if m else proof

def _tactic_tokens(proof: str) -> list[str]:
    """Sequence of leading tactic identifiers in the proof body (skeleton)."""
    out = []
    for raw in re.split(r"[\n;]", _body(proof)):
        s = raw.strip()
        if not s or s.startswith("--"):
            continue
        # strip focusing dots / brackets so `· simp` and `simp` compare equal
        s = s.lstrip("·•-{}⟨ ").strip()
        m = _TAC_RE.match(s)
        if m:
            out.append(m.group(0))
    return out

def first_tactic(proof: str) -> str | None:
    toks = _tactic_tokens(proof)
    return toks[0] if toks else None

def skeleton(proof: str, depth: int = 4) -> str:
    """First `depth` tactic tokens joined — a coarse structural signature of the approach."""
    return ">".join(_tactic_tokens(proof)[:depth])

# ---------------------------------------------------------------- failure taxonomy
_STEP_RE = re.compile(r"Failed at step\s+(\d+)")

def _classify(reason: str, feedback: str) -> str:
    fb = (feedback or "").lower()
    if reason == "loophole":
        return "loophole_sorry"
    if reason == "no_goal":
        return "truncation"
    if reason == "ok":
        return "ok"
    # everything else is a compile_error; sub-classify by the Lean message
    if ("unknown identifier" in fb or "unknown constant" in fb
            or "unknown namespace" in fb or "unknown" in fb and "ambiguous" in fb):
        return "knowledge_hallucinated_lemma"
    if ("unexpected token" in fb or "expected" in fb or "unterminated" in fb
            or "syntax" in fb):
        return "formalization_syntax"
    # reasoning failure (unsolved goals / type mismatch / failed tactic). Split by how far the proof
    # elaborated before failing — DEEP = failed after >=4 steps of a long proof (NOT a claim of
    # "one step from done"); SHALLOW = stalled near the start.
    m = _STEP_RE.search(feedback or "")
    if m and int(m.group(1)) >= 4:
        return "reasoning_deep"
    return "reasoning_shallow"

def deepest_step(attempts: list[dict]) -> int:
    best = 0
    for a in attempts:
        m = _STEP_RE.search(a.get("feedback") or "")
        if m:
            best = max(best, int(m.group(1)))
    return best

# ---------------------------------------------------------------- per-cell load
def load_cells(run_dir: str) -> list[dict]:
    cells, skipped = [], 0
    for f in sorted(glob.glob(os.path.join(run_dir, "agent_states", "*.json"))):
        try:
            d = json.load(open(f))
        except (json.JSONDecodeError, ValueError):
            skipped += 1
            continue
        attempts = d.get("attempts", [])
        name = d.get("theorem_name") or os.path.basename(f).split("__seed")[0]
        cells.append({
            "name": name,
            "subfield": name.split("__")[0] if "__" in name else name.split("_")[0],
            "solved": any(a.get("reason") == "ok" for a in attempts),
            "attempts": attempts,
            "stop_reason": d.get("stop_reason"),
        })
    if skipped:
        print(f"  [load] {run_dir}: skipped {skipped} corrupt/empty agent_state file(s)")
    return cells

# ---------------------------------------------------------------- A1 diversity
def diversity(cells: list[dict]) -> dict:
    def ratios(group):
        fts, sks, nat, ftc, skc = [], [], [], [], []
        for c in group:
            ats = c["attempts"]
            if not ats:
                continue
            ft = {first_tactic(a.get("proof", "")) for a in ats} - {None}
            sk = {skeleton(a.get("proof", "")) for a in ats} - {""}
            fts.append(len(ft) / len(ats))
            ftc.append(len(ft))
            sks.append(len(sk) / len(ats))
            skc.append(len(sk))
            nat.append(len(ats))

        def agg(xs):
            return round(st.mean(xs), 3) if xs else None
        return {"n_cells": len(group), "mean_attempts": agg(nat),
                # ratios are mechanically depressed by attempt count; the ABSOLUTE distinct counts
                # (mean_distinct_*) are the confound-free collapse metric.
                "first_tactic_diversity": agg(fts), "skeleton_diversity": agg(sks),
                "mean_distinct_first_tactics": agg(ftc), "mean_distinct_skeletons": agg(skc)}
    return {"solved": ratios([c for c in cells if c["solved"]]),
            "unsolved": ratios([c for c in cells if not c["solved"]])}

# ---------------------------------------------------------------- A2 taxonomy (unsolved only)
def taxonomy(cells: list[dict]) -> dict:
    unsolved = [c for c in cells if not c["solved"]]
    # per-cell label = the most "advanced" failure it reached (priority order)
    prio = ["reasoning_deep", "reasoning_shallow", "knowledge_hallucinated_lemma",
            "formalization_syntax", "loophole_sorry", "truncation"]
    cell_label = Counter()
    attempt_label = Counter()
    for c in unsolved:
        labels = set()
        for a in c["attempts"]:
            lab = _classify(a.get("reason"), a.get("feedback", ""))
            if lab != "ok":
                attempt_label[lab] += 1
                labels.add(lab)
        chosen = next((p for p in prio if p in labels), "none")
        cell_label[chosen] += 1
    n = len(unsolved) or 1
    return {"n_unsolved_cells": len(unsolved),
            "cell_pct": {k: round(100 * v / n, 1) for k, v in cell_label.most_common()},
            "attempt_counts": dict(attempt_label.most_common())}

# ---------------------------------------------------------------- A3 / A4
def tokens_dist(cells: list[dict]) -> dict:
    """Deepest reached step among unsolved cells — proxy for 'almost solving' vs hard floor."""
    steps = [deepest_step(c["attempts"]) for c in cells if not c["solved"]]
    if not steps:
        return {"n": 0}
    steps.sort()
    def pct(p):
        return steps[min(len(steps) - 1, int(p * len(steps)))]
    return {"n_unsolved": len(steps), "deepest_step_median": pct(0.5),
            "deepest_step_p90": pct(0.9), "frac_never_past_step1": round(
                sum(1 for s in steps if s <= 1) / len(steps), 3)}

def late_solve_approach(cells: list[dict]) -> dict:
    """Pre-flight for Step C (causal vs symptomatic): when a problem is solved LATE (after several
    attempts), did the win come from an opening tactic the model had NOT already tried (exploration
    unlocked it = F1-causal), or from re-trying its dominant approach (= diversity is symptomatic)?
    Compares early (w=1-2) vs late (w>=3) solves; w = index of the first verifying attempt. The
    first-shot (w=0) bucket is reported but trivial (empty prior → 'new' by construction)."""
    rows = []
    for c in cells:
        ats = c["attempts"]
        w = next((i for i, a in enumerate(ats) if a.get("reason") == "ok"), None)
        if w is None:
            continue
        opens = [first_tactic(a.get("proof", "")) for a in ats]
        t_win = opens[w]
        if t_win is None:
            continue
        prior = [o for o in opens[:w] if o is not None]
        t_first = next((o for o in opens if o is not None), None)
        rows.append({"w": w,
                     "new": t_win not in prior,                       # win uses an untried opening
                     "switched": t_first is not None and t_win != t_first})

    def bucket(lo, hi):
        sel = [r for r in rows if lo <= r["w"] <= hi]
        n = len(sel) or 1
        return {"n": len(sel),
                "pct_new_approach": round(100 * sum(r["new"] for r in sel) / n, 1),
                "pct_switched_from_first": round(100 * sum(r["switched"] for r in sel) / n, 1)}
    return {"first_shot_w0": bucket(0, 0), "early_w1_2": bucket(1, 2),
            "late_w3plus": bucket(3, 10**9)}


def trapped_problems(cells: list[dict]) -> list[str]:
    """Problem names unsolved by EVERY seed at the run's ceiling — the fully-stuck core that is the
    population for Step C (a problem any seed already solves is not 'trapped'). Sorted, de-duped."""
    by_problem: dict[str, list[bool]] = defaultdict(list)
    for c in cells:
        by_problem[c["name"]].append(c["solved"])
    return sorted(name for name, solves in by_problem.items() if not any(solves))


def stratify(cells: list[dict]) -> dict:
    by = defaultdict(lambda: [0, 0])
    for c in cells:
        by[c["subfield"]][0] += int(c["solved"])
        by[c["subfield"]][1] += 1
    return {k: {"solve_rate": round(s / n, 3), "n": n}
            for k, (s, n) in sorted(by.items(), key=lambda kv: -kv[1][0] / kv[1][1])}

# ---------------------------------------------------------------- driver
def analyze(run_dir: str) -> dict:
    cells = load_cells(run_dir)
    return {"run": run_dir, "n_cells": len(cells),
            "solve_rate": round(sum(c["solved"] for c in cells) / (len(cells) or 1), 3),
            "A1_diversity": diversity(cells), "A2_taxonomy": taxonomy(cells),
            "A3_tokens": tokens_dist(cells), "A4_stratify": stratify(cells),
            "A5_late_solve_approach": late_solve_approach(cells)}

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+", help="run dirs (optionally label=dir)")
    ap.add_argument("--out", default="results/phase2", help="output dir for mechanism.json")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    results = {}
    for r in args.runs:
        label, _, d = r.partition("=")
        if not d:
            label, d = os.path.basename(r.rstrip("/")), r
        results[label] = analyze(d)
    outp = os.path.join(args.out, "mechanism.json")
    json.dump(results, open(outp, "w"), indent=2)
    # human-readable summary
    for label, res in results.items():
        print(f"\n===== {label}  (solve_rate={res['solve_rate']}, n={res['n_cells']}) =====")
        d = res["A1_diversity"]
        for grp in ("solved", "unsolved"):
            g = d[grp]
            print(f"  A1 {grp:8s}: distinct first-tacs {g['mean_distinct_first_tactics']} "
                  f"skeletons {g['mean_distinct_skeletons']} over {g['mean_attempts']} attempts "
                  f"(ratios {g['first_tactic_diversity']}/{g['skeleton_diversity']})")
        t = res["A2_taxonomy"]
        print(f"  A2 taxonomy (% of {t['n_unsolved_cells']} unsolved cells): {t['cell_pct']}")
        print(f"  A3 unsolved depth: {res['A3_tokens']}")
        top = list(res["A4_stratify"].items())[:5]
        print("  A4 top subfields: " + ", ".join(f"{k}={v['solve_rate']}(n{v['n']})" for k, v in top))
        a5 = res["A5_late_solve_approach"]
        print("  A5 late-solve approach (causal pre-flight):")
        for b in ("early_w1_2", "late_w3plus"):
            print(f"       {b:12s} n={a5[b]['n']:<4} new-approach {a5[b]['pct_new_approach']}%  "
                  f"switched-from-first {a5[b]['pct_switched_from_first']}%")
    print(f"\nwrote {outp}")

if __name__ == "__main__":
    main()
