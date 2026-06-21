#!/usr/bin/env python3
"""Phase 5 Task 5.2 PILOT GATE: extend a stratified sample of the extend set to E and count solves.

The go/no-go before any full spend: resume-extend ~10 still-progressing ProofNet# cells per model
from their logged 128k checkpoints to E=512k (1 GPU job/model), early-stopping on solve. If >=2-3
solve the tail is live -> proceed to the full run; if 0 solve the tail is saturated -> stop and
report the honest null. Reports the per-seed split too (the empirical question post-Phase-4).

Thin wrapper over the tested `run_extend` / `load_pilot_cells` (src/atp/eval/extend_run.py). Needs a
live vLLM endpoint (serving the config's model) + the built Lean env — same preconditions as sweep.

Usage:
  python scripts/phase5_pilot.py --config configs/proofnet_baseline.yaml \
      --baseline results/proofnet_baseline --model goedel --benchmark proofnet_sharp \
      --new-budget 512000 --name phase5_pilot_goedel_proofnet
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from atp.config import config_hash, load_config
from atp.eval.extend_run import load_pilot_cells, run_extend

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="model+benchmark+lean config (baseline config)")
    ap.add_argument("--baseline", required=True, help="run dir whose 128k checkpoints to extend")
    ap.add_argument("--candidates", default="results/phase5/candidates.json")
    ap.add_argument("--model", required=True)
    ap.add_argument("--benchmark", required=True)
    ap.add_argument("--new-budget", type=int, default=512_000)
    ap.add_argument("--n-workers", type=int, default=8,
                    help="concurrent cells (vLLM batches the streams; each owns a Lean REPL)")
    ap.add_argument("--name", required=True, help="run dir under results/")
    args = ap.parse_args()

    cfg = load_config(args.config)
    cells = load_pilot_cells(args.candidates, args.model, args.benchmark)
    run_dir = Path(cfg.project.root) / cfg.project.results_dir / args.name
    print(f"[pilot] {args.model} x {args.benchmark}: extending {len(cells)} cells "
          f"{args.baseline} -> E={args.new_budget:,} (n_workers={args.n_workers}, "
          f"config_hash={config_hash(cfg)})")

    summary = run_extend(cfg, run_dir, args.baseline, cells, args.new_budget,
                         n_workers=args.n_workers)
    summary["model"] = args.model
    summary["benchmark"] = args.benchmark
    (run_dir / "pilot_summary.json").write_text(json.dumps(summary, indent=2))

    print(f"[pilot] ran={summary['n_ran']} skipped={summary['n_skipped']}  "
          f"EXTENSION SOLVES={summary['n_extension_solves']}/{summary['n_cells']}")
    print(f"[pilot] extension solves per seed: {summary['extension_solves_per_seed']}")
    print(f"[pilot] wrote {run_dir}/pilot_summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
