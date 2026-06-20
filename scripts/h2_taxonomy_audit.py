#!/usr/bin/env python3
"""H2 — corrected attempt-level failure taxonomy + the load-bearing knowledge rate.

Two corrections to the original A2 (analyze_mechanism.taxonomy, which labels each CELL by its most-
ADVANCED attempt, so reasoning_deep masks everything else and yields the misleading "94-100% reasoning /
~0% knowledge"):
  (1) report at the ATTEMPT level (every failed attempt counts once), and
  (2) split out REPL-infra crashes (Lean process exited / malformed-no-env response) which _classify
      otherwise buries in reasoning_shallow.
Headline: the KNOWLEDGE/missing-identifier rate — the retrieval-relevant class — is NOT ~0% on OOD.
"""
import glob, json, os, re, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(__file__))
from analyze_mechanism import _classify

INFRA = re.compile(r"REPL_INFRA_ERROR|exited with code|malformed response \(no 'env'")
MD = re.compile(r"unexpected token '#'|expected command")  # model emitted markdown/prose, not Lean

RUNS = [
    ("Goedel  miniF2F",   "results/baseline"),
    ("Goedel  ProofNet#", "results/proofnet_baseline"),
    ("DeepSeek miniF2F",  "results/deepseek_minif2f_baseline"),
    ("DeepSeek ProofNet#","results/deepseek_proofnet_baseline"),
]

def audit(run):
    c = Counter(); tot = 0
    for f in glob.glob(os.path.join(run, "agent_states", "*.json")):
        try: d = json.load(open(f))
        except (json.JSONDecodeError, ValueError): continue
        att = d.get("attempts", [])
        if not att or any(a.get("reason") == "ok" for a in att):
            continue
        for a in att:
            fb = a.get("feedback", "") or ""; rn = a.get("reason", "")
            lab = _classify(rn, fb)
            if lab == "ok":
                continue
            tot += 1
            if INFRA.search(fb):
                c["infra_repl_crash"] += 1            # corrected: pull out of reasoning_shallow
            elif lab == "formalization_syntax" and MD.search(fb):
                c["markdown_nonlean"] += 1            # corrected: model wrote prose, not Lean
            else:
                c[lab] += 1
    return c, tot

print("CORRECTED attempt-level failure taxonomy (infra crashes + markdown split out):\n")
for label, run in RUNS:
    c, tot = audit(run)
    tot = tot or 1
    row = {k: f"{100*v/tot:.1f}%" for k, v in c.most_common()}
    print(f"{label}  (n_failed_attempts={tot})")
    print(f"   {row}")
    print(f"   >> KNOWLEDGE/missing-identifier = {100*c['knowledge_hallucinated_lemma']/tot:.1f}%  "
          f"(the retrieval-relevant class; original A2 cell-level reported ~0%)\n")
