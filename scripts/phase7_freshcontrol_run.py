#!/usr/bin/env python3
"""Phase 7 Track 1 — fresh-resample CONTROL (no re-grounding), same trapped set + fresh session.

The offline Mode 1/2 reconstruction (`phase7_offline_modes.py`) reuses each cell's ORIGINAL logged
baseline trajectory, so it is trivially 0/150 on trapped names (that IS the definition of trapped).
Mode 3's real run instead uses a FRESH vLLM session — so a nonzero Mode-3 solve could be genuine
re-grounding signal, OR could just be "a different sampling draw sometimes gets lucky," unrelated to
verified-state feedback. This script runs the EXACT existing `WholeProofAgent` (whole-proof +
error-feedback refinement — the same protocol the original baseline used) on the SAME trapped names,
in a FRESH session, so Mode 3's solve rate can be compared against what fresh re-sampling ALONE
achieves with no state-grounding mechanism at all. Reuses `atp.eval.run.build_solve_fn` verbatim.

Usage (same CLI shape as phase7_stepwise_run.py, minus --max-rounds):
  python scripts/phase7_freshcontrol_run.py --config configs/proofnet_baseline.yaml \
      --trapped scratch/phase2/trapped_proofnet.txt \
      --out results/phase7/goedel_proofnet_freshcontrol --seeds 0 --budget 32000 --n-workers 8
"""

from __future__ import annotations

import argparse
from pathlib import Path

from atp.config import apply_env, load_config
from atp.data import load_dataset
from atp.eval.harness import run_sweep
from atp.eval.run import build_solve_fn, resolve_endpoint_file
from atp.lean.backends import LeanBackend
from atp.lean.repl import ReplBackend
from atp.models.client import OpenAITransport


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--trapped", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seeds", default=None)
    ap.add_argument("--budget", type=int, default=None)
    ap.add_argument("--n-workers", type=int, default=None)
    args = ap.parse_args()

    config = load_config(args.config)
    apply_env(config)
    run_dir = Path(args.out)

    trapped_names = {ln.strip() for ln in Path(args.trapped).read_text().splitlines() if ln.strip()}
    dataset = load_dataset(config, model_revision=config.model.revision)
    dataset.problems = [p for p in dataset.problems if p.name in trapped_names]
    if not dataset.problems:
        raise SystemExit(f"[fresh-control] 0/{len(trapped_names)} trapped names matched")
    print(f"[fresh-control] {len(dataset.problems)}/{len(trapped_names)} trapped names loaded")

    transport = OpenAITransport.from_endpoint_file(
        resolve_endpoint_file(config),
        timeout_s=config.model.request_timeout_s,
        max_retries=config.model.request_max_retries,
    )

    def backend_factory() -> LeanBackend:
        return ReplBackend(config)

    solve_fn = build_solve_fn(config, run_dir, transport, backend_factory)
    seeds = [int(s) for s in args.seeds.split(",")] if args.seeds else None
    try:
        result = run_sweep(
            config, dataset, solve_fn, run_dir=run_dir, seeds=seeds, budget=args.budget,
            n_workers=args.n_workers,
        )
    finally:
        solve_fn.close_backends()  # type: ignore[attr-defined]

    print(f"[fresh-control] {result.n_ran} ran, {result.n_skipped} skipped -> {run_dir}")
    print(f"[fresh-control] metrics: {result.metrics}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
