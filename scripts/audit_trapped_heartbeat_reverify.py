"""AUDIT_PLAN.md Task B — does `set_option maxHeartbeats 0` (added 2026-07-06, absent for every
Phase 0-7 sweep) retroactively change any Phase 0-7 headline result? Re-verifies a sample of the
TRAPPED-CORE problems' recorded failed attempts (whole_proof, Goedel-V2/DeepSeek-V2 -- the models
every Phase 0-7 headline number is built on) against the CURRENT, fully-patched `ReplBackend`, with
NO new GPU generation. Reuses `scripts/phase8_reverify.py`'s `reverify_cell`/`_load_attempts`.

Usage (real Lean env required):
    ATP_LEAN_PROJECT=/local/$USER/atp-lean-env python scripts/audit_trapped_heartbeat_reverify.py \
        --config configs/proofnet_baseline.yaml --run-dir results/proofnet_baseline \
        --trapped-file scratch/phase2/trapped_proofnet.txt --limit-problems 15
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from phase8_reverify import _load_attempts, reverify_cell  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--trapped-file", required=True)
    ap.add_argument("--limit-problems", type=int, default=None)
    ap.add_argument("--checkpoint", default=None,
                     help="JSONL file to append results to; on startup, (name,seed) pairs "
                          "already present are skipped. Defaults to <run-dir>/audit_checkpoint.jsonl")
    args = ap.parse_args()

    from atp.config import load_config
    from atp.data import load_dataset
    from atp.lean import ReplBackend, Verifier

    trapped_names = [ln.strip() for ln in open(args.trapped_file) if ln.strip()]
    if args.limit_problems:
        trapped_names = trapped_names[: args.limit_problems]
    trapped_set = set(trapped_names)
    print(f"[audit] {len(trapped_names)} trapped problems selected from {args.trapped_file}")

    checkpoint_path = args.checkpoint or os.path.join(args.run_dir, "audit_checkpoint.jsonl")
    done = {}
    if os.path.exists(checkpoint_path):
        with open(checkpoint_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                done[(rec["name"], rec["seed"])] = rec
        print(f"[audit] resuming from checkpoint: {len(done)} cells already done "
              f"({checkpoint_path})")

    config = load_config(args.config)
    ds = load_dataset(config)
    problems = ds.problems if hasattr(ds, "problems") else ds
    theorem_by_name = {p.name: p.to_theorem() for p in problems}

    backend = ReplBackend(config)
    verifier = Verifier.from_config(config, backend)

    agent_states_dir = os.path.join(args.run_dir, "agent_states")
    n_checked = sum(1 for (n, _) in done if n in trapped_set)
    n_flipped = sum(1 for rec in done.values() if rec["name"] in trapped_set and rec["solved"])
    flipped_names = [f"{rec['name']}__seed{rec['seed']}" for rec in done.values()
                      if rec["name"] in trapped_set and rec["solved"]]
    ckpt_f = open(checkpoint_path, "a")
    for name in trapped_names:
        theorem = theorem_by_name.get(name)
        if theorem is None:
            print(f"[audit] SKIP {name}: not found in dataset")
            continue
        for seed in (0, 1, 2):
            if (name, seed) in done:
                continue
            path = os.path.join(agent_states_dir, f"{name}__seed{seed}.json")
            if not os.path.exists(path):
                continue
            attempts = _load_attempts(path)
            if not attempts:
                continue
            result = reverify_cell(attempts, theorem, verifier)
            n_checked += 1
            ckpt_f.write(json.dumps({
                "name": name, "seed": seed, "solved": bool(result.solved),
                "tokens_to_solve": result.tokens_to_solve,
            }) + "\n")
            ckpt_f.flush()
            if result.solved:
                n_flipped += 1
                flipped_names.append(f"{name}__seed{seed}")
                print(f"[audit] FLIPPED TO SOLVED: {name} seed={seed} "
                      f"tokens_to_solve={result.tokens_to_solve}", flush=True)
            if n_checked % 5 == 0:
                print(f"[audit] progress: {n_checked} cells checked, {n_flipped} flipped so far",
                      flush=True)
    ckpt_f.close()

    print(f"\n[audit] FINAL: {n_checked} cells re-verified across {len(trapped_set)} trapped "
          f"problems, {n_flipped} flipped to solved.")
    if flipped_names:
        print("[audit] flipped cells:", flipped_names)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
