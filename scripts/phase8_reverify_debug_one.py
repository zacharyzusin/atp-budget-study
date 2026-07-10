#!/usr/bin/env python3
"""One-off debug: print the re-verify result + feedback for a single named cell's first attempt.
Confirms the _build_source/_build_repl_source fix actually changed the failure signature (no longer
"unexpected identifier; expected command") rather than silently still failing the same way.
"""
import json
import sys

from atp.config import load_config
from atp.data import load_dataset
from atp.lean import ReplBackend, Verifier

config_path, run_dir, problem_name, seed = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])

cfg = load_config(config_path)
ds = load_dataset(cfg)
problems = ds.problems if hasattr(ds, "problems") else ds
p = [x for x in problems if x.name == problem_name][0]
theorem = p.to_theorem()

d = json.load(open(f"{run_dir}/agent_states/{problem_name}__seed{seed}.json"))
backend = ReplBackend(cfg)
verifier = Verifier.from_config(cfg, backend)

for i, att in enumerate(d["attempts"][:5]):
    proof = att["proof"]
    result = verifier.verify(theorem, proof)
    print(f"--- attempt {i} ---")
    print("proof:", repr(proof[:200]))
    print("ok:", result.ok, "reason:", result.reason)
    print("feedback:", result.feedback)
    print()
