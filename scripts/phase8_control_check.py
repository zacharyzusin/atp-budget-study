#!/usr/bin/env python3
"""Harness-sanity control (coordinator-mandated 2026-07-09/10): confirm the CURRENT fully-patched
backend still recognizes Goedel-Prover-V2/DeepSeek-Prover-V2-7B's historically-solved proofs as
solved. Targeted and fast, unlike a full re-verify: samples N cells the ORIGINAL run recorded as
`solved=True`, re-verifies ONLY the recorded solving attempt (not every attempt in the cell) against
the current backend, and reports how many still verify. A real, if partial, harness-sanity signal
without re-running the full (slow, many-attempts-per-cell) re-verify pass end to end.
"""
import argparse
import glob
import json
import os
import random


def _load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def sample_solved_cells(run_dir, n, seed=0):
    """[(problem_name, seed, solving_proof)] for N cells the original run recorded as solved,
    reading the recorded tokens_to_solve to find which attempt actually solved it."""
    cell_files = glob.glob(os.path.join(run_dir, "problems", "*.json"))
    solved_names = []
    for f in cell_files:
        d = _load_json(f)
        if d and d.get("solved"):
            base = os.path.basename(f)[: -len(".json")]
            name, _, seed_part = base.rpartition("__seed")
            solved_names.append((name, int(seed_part)))
    rng = random.Random(seed)
    rng.shuffle(solved_names)
    picked = solved_names[:n]

    out = []
    for name, prob_seed in picked:
        state_path = os.path.join(run_dir, "agent_states", f"{name}__seed{prob_seed}.json")
        d = _load_json(state_path)
        if not d:
            continue
        solving_proof = None
        for att in d["attempts"]:
            if att["ok"]:
                solving_proof = att["proof"]
                break
        if solving_proof is not None:
            out.append((name, prob_seed, solving_proof))
    return out, len(solved_names)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("-n", type=int, default=40)
    args = ap.parse_args()

    from atp.config import load_config
    from atp.data import load_dataset
    from atp.lean import ReplBackend, Verifier

    config = load_config(args.config)
    ds = load_dataset(config)
    problems = ds.problems if hasattr(ds, "problems") else ds
    theorem_by_name = {p.name: p.to_theorem() for p in problems}

    backend = ReplBackend(config)
    verifier = Verifier.from_config(config, backend)

    sample, n_solved_total = sample_solved_cells(args.run_dir, args.n)
    print(f"[control] {args.run_dir}: {n_solved_total} cells originally solved; sampling {len(sample)}")

    n_still_ok = 0
    n_checked = 0
    for name, seed, proof in sample:
        theorem = theorem_by_name.get(name)
        if theorem is None:
            continue
        result = verifier.verify(theorem, proof)
        n_checked += 1
        status = "STILL OK" if result.ok else f"NOW FAILS ({result.reason}: {result.feedback[:100]})"
        print(f"  {name}__seed{seed}: {status}")
        if result.ok:
            n_still_ok += 1

    print(f"[control] {n_still_ok}/{n_checked} sampled historically-solved cells still verify as OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
