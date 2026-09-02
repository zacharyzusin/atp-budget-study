#!/usr/bin/env python3
"""H2 — sample unsolved attempts for human validation of the regex failure taxonomy.

The load-bearing claim is "~0% knowledge / 94-100% reasoning_deep" among unsolved attempts — it is
what
KILLS premise retrieval (the failures aren't missing-lemma, so there's nothing to retrieve). That
rests
on _classify() in analyze_mechanism.py (a regex over Lean feedback). This emits a STRATIFIED sample
of
last-attempt failures per run (auto-label + raw feedback + opening tactics) so a human can re-label
and we
can report agreement + the specific reasoning-vs-knowledge confusion rate.

Usage: python scripts/h2_taxonomy_sample.py <run_dir> --n 70 [--seed 0]   -> prints a labeling
worksheet.
"""
import argparse
import glob
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))
from analyze_mechanism import _classify, first_tactic


def last_failures(run_dir):
    """One record per UNSOLVED cell = its last attempt (the giving-up state A2 reports)."""
    recs = []
    for f in sorted(glob.glob(os.path.join(run_dir, "agent_states", "*.json"))):
        try:
            d = json.load(open(f))
        except (json.JSONDecodeError, ValueError):
            continue
        att = d.get("attempts", [])
        if not att or any(a.get("reason") == "ok" for a in att):
            continue  # solved or empty
        last = att[-1]
        recs.append({
            "name": d.get("theorem_name") or os.path.basename(f).split("__seed")[0],
            "auto": _classify(last.get("reason", ""), last.get("feedback", "")),
            "reason": last.get("reason", ""),
            "opening": first_tactic(last.get("proof", "")),
            "feedback": (last.get("feedback") or "").strip(),
        })
    return recs

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--n", type=int, default=70)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    recs = last_failures(a.run_dir)
    from collections import Counter
    dist = Counter(r["auto"] for r in recs)
    rng = random.Random(a.seed)
    # stratified: proportional-ish but guarantee >=5 of any non-empty minority class for scrutiny
    by = {}
    for r in recs:
        by.setdefault(r["auto"], []).append(r)
    sample = []
    for lbl, rs in by.items():
        rng.shuffle(rs)
        take = max(5, round(a.n * len(rs) / len(recs))) if lbl != "reasoning_deep" else None
        sample += rs[:take] if take else rs[: a.n]  # reasoning_deep gets the bulk
    # trim/pad toward n, keep reasoning_deep majority
    rng.shuffle(sample)
    sample = sample[: a.n]
    print(f"### H2 worksheet — {a.run_dir}")
    print(f"### unsolved cells={len(recs)}  auto-label dist={dict(dist)}")
    print(f"### sample n={len(sample)}; for each, HUMAN label in: reasoning|knowledge|syntax|loophole|truncation|other")
    print("=" * 100)
    for i, r in enumerate(sample):
        fb = " ".join(r["feedback"].split())[:500]
        print(f"\n[{i:02d}] auto={r['auto']}  reason={r['reason']}  opening={r['opening']}  ({r['name']})")
        print(f"     feedback: {fb}")

if __name__ == "__main__":
    main()
