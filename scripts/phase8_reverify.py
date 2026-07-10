#!/usr/bin/env python3
"""Phase 8 — re-verify already-collected p8battery2_* completions against the FIXED
`ReplBackend`/`PantographBackend._build_source` (missing-theorem-header bug, PROGRESS.md/
DECISIONS.md 2026-07-06), with NO new vLLM generation. CPU-only Lean re-verification is much cheaper
than the ~150+ GPU-h the original generation cost.

Usage (per run dir, real Lean env required — run inside a staged-env Slurm job, see
slurm/phase8_reverify.sh):

    python scripts/phase8_reverify.py --config configs/deepseek_v15_sft_proofnet_battery.yaml \\
        --run-dir results/p8battery2_deepseek_v15_sft_proofnet \\
        --out-dir results/p8battery2_verified_deepseek_v15_sft_proofnet [--limit N]

Writes corrected `problems/<name>__seed<N>.json` files (same schema `phase8_floor_table.py` already
reads) reflecting the re-verified `solved`/`tokens_to_solve`, leaving the original run dir untouched.
"""
import argparse
import glob
import json
import os
from dataclasses import dataclass


@dataclass
class ReverifyResult:
    solved: bool
    tokens_to_solve: int | None
    solving_attempt_index: int | None


def reverify_cell(attempts, theorem, verifier) -> ReverifyResult:
    """attempts: list of {"proof": str, "completion_tokens": int}, IN GENERATION ORDER (matches the
    original stop-on-first-success semantics — later attempts are never checked once one solves).
    """
    cumulative = 0
    for i, att in enumerate(attempts):
        cumulative += att["completion_tokens"]
        verdict = verifier.verify(theorem, att["proof"])
        if verdict.ok:
            return ReverifyResult(solved=True, tokens_to_solve=cumulative, solving_attempt_index=i)
    return ReverifyResult(solved=False, tokens_to_solve=None, solving_attempt_index=None)


def _load_attempts(agent_state_path):
    """Returns None (not an exception) for an empty/corrupt checkpoint — a real, previously-seen
    class of issue in this exact repo (`atp.agents.state`'s own "tolerate empty/corrupt checkpoints"
    resume hardening); the re-verify tool must have the same tolerance, not crash the whole batch on
    the first bad file (found live 2026-07-09/10 re-verifying `results/baseline`'s pre-existing
    checkpoints — see PROGRESS.md/DECISIONS.md that date)."""
    try:
        with open(agent_state_path) as f:
            d = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    return d.get("attempts")


def run_reverify(agent_state_files, out_problems_dir, theorem_by_name, verifier):
    """Resumable: skips any cell whose output file already exists (job requeue/timeout tolerance —
    CLAUDE.md rule 3, "sweeps must skip already-completed cells on resume"). Returns
    (n_total, n_flipped_to_solved, n_skipped_done)."""
    os.makedirs(out_problems_dir, exist_ok=True)
    n_flipped_to_solved = 0
    n_total = 0
    n_skipped_done = 0
    for path in agent_state_files:
        base = os.path.basename(path)[: -len(".json")]
        name, _, seed_part = base.rpartition("__seed")
        seed = int(seed_part)
        out_path = os.path.join(out_problems_dir, f"{name}__seed{seed}.json")
        if os.path.exists(out_path):
            n_skipped_done += 1
            continue
        theorem = theorem_by_name.get(name)
        if theorem is None:
            print(f"[reverify] SKIP {base}: problem {name!r} not found in dataset")
            continue
        attempts = _load_attempts(path)
        if attempts is None:
            print(f"[reverify] SKIP {base}: empty/corrupt checkpoint")
            continue
        result = reverify_cell(attempts, theorem, verifier)
        n_total += 1
        if result.solved:
            n_flipped_to_solved += 1
        out = {
            "problem_name": name,
            "seed": seed,
            "solved": result.solved,
            "tokens_to_solve": result.tokens_to_solve,
        }
        with open(out_path, "w") as f:
            json.dump(out, f)
    return n_total, n_flipped_to_solved, n_skipped_done


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--limit", type=int, default=None, help="re-verify only the first N cells (smoke)")
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

    agent_state_files = sorted(glob.glob(os.path.join(args.run_dir, "agent_states", "*.json")))
    if args.limit:
        agent_state_files = agent_state_files[: args.limit]

    out_problems_dir = os.path.join(args.out_dir, "problems")
    n_total, n_flipped_to_solved, n_skipped_done = run_reverify(
        agent_state_files, out_problems_dir, theorem_by_name, verifier
    )
    print(
        f"[reverify] {args.run_dir}: {n_total} cells re-verified ({n_skipped_done} already done, "
        f"skipped), {n_flipped_to_solved} now solved"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
