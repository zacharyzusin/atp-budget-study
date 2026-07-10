#!/usr/bin/env python3
"""One-off sanity scan: re-verify EVERY attempt (not just until first solve) for N cells and report
the full distribution of `reason` values, to catch a silent bug in the main reverify pass (e.g. a
false negative from _DECL_RE, or an exception being swallowed) rather than trusting a 0% count blind.
"""
import glob
import json
import sys
from collections import Counter

from atp.config import load_config
from atp.data import load_dataset
from atp.lean import ReplBackend, Verifier

config_path, run_dir, n_cells = sys.argv[1], sys.argv[2], int(sys.argv[3])

cfg = load_config(config_path)
ds = load_dataset(cfg)
problems = ds.problems if hasattr(ds, "problems") else ds
theorem_by_name = {p.name: p.to_theorem() for p in problems}

backend = ReplBackend(cfg)
verifier = Verifier.from_config(cfg, backend)

files = sorted(glob.glob(f"{run_dir}/agent_states/*.json"))[:n_cells]
reasons = Counter()
any_ok = []
sample_feedback = []
n_attempts_checked = 0
for path in files:
    base = path.split("/")[-1][: -len(".json")]
    name, _, seed_part = base.rpartition("__seed")
    theorem = theorem_by_name.get(name)
    if theorem is None:
        continue
    d = json.load(open(path))
    for att in d["attempts"]:
        result = verifier.verify(theorem, att["proof"])
        reasons[result.reason] += 1
        n_attempts_checked += 1
        if result.ok:
            any_ok.append((base, att["index"]))
        elif len(sample_feedback) < 10:
            sample_feedback.append((base, att["index"], result.feedback, att["proof"][:150]))

print("cells scanned:", len(files))
print("attempts checked:", n_attempts_checked)
print("reason distribution:", dict(reasons))
print("any_ok:", any_ok[:20])

print()
print("=== sample feedback (first 10 non-ok) ===")
for base, idx, feedback, proof_head in sample_feedback:
    print(f"--- {base} attempt {idx} ---")
    print("feedback:", feedback)
    print("proof head:", repr(proof_head))
    print()
