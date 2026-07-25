#!/usr/bin/env python3
"""WS6 item 3 — subgoal decomposition real eval run.

Design note: results/phase_decomp/DESIGN.md (read before changing anything here). Same restartable-
sweep machinery every other headline run uses, with `DecompositionAgent` swapping in for
`WholeProofAgent` as the per-cell solver — structurally identical to
`scripts/phase7_stepwise_run.py`'s Mode-3 wiring, only the agent class differs.

Usage (on a GPU node with the vLLM server up + ATP_VLLM_ENDPOINT_FILE set):
  python scripts/phase_decomp_run.py --config configs/proofnet_baseline.yaml \
      --trapped scratch/phase2/trapped_proofnet.txt --out results/phase_decomp/goedel_proofnet \
      --seeds 0 --budget 128000 --max-rounds 8 --max-subgoal-rounds 8
"""

from __future__ import annotations

import argparse
import threading
from pathlib import Path

from atp.agents.decomposition import DecompositionAgent
from atp.budget.meter import BudgetMeter
from atp.config import apply_env, load_config
from atp.data import load_dataset
from atp.eval.harness import run_sweep
from atp.eval.run import resolve_endpoint_file
from atp.lean.backends import LeanBackend
from atp.lean.repl import ReplBackend
from atp.lean.verifier import Verifier
from atp.models.client import OpenAITransport, VLLMClient
from atp.models.templates import WholeProofTemplate


def build_decomp_solve_fn(config, run_dir: Path, transport, max_rounds: int, max_subgoal_rounds: int):
    """Mirrors `phase7_stepwise_run.py::build_stepwise_solve_fn` — same thread-local Lean-backend
    pattern, `DecompositionAgent` as the per-cell solver instead of `RegroundStepwiseAgent`."""
    states_dir = run_dir / "agent_states"
    tls = threading.local()
    created: list[LeanBackend] = []
    created_lock = threading.Lock()

    def _thread_backend() -> LeanBackend:
        b = getattr(tls, "backend", None)
        if b is None:
            b = ReplBackend(config)
            tls.backend = b
            with created_lock:
                created.append(b)
        return b

    def solve_fn(problem, seed, budget):
        meter = BudgetMeter(limit=budget)
        client = VLLMClient.from_config(config, transport, meter)
        client.seed = seed
        verifier = Verifier.from_config(config, _thread_backend())
        agent = DecompositionAgent(
            client=client,
            verifier=verifier,
            template=WholeProofTemplate(),
            max_rounds=max_rounds,
            max_subgoal_rounds=max_subgoal_rounds,
            sample_max_tokens=config.model.sample_max_tokens or (config.model.max_model_len // 2),
        )
        state_path = states_dir / f"{problem.name}__seed{seed}.json"
        return agent.prove(problem.to_theorem(), state_path=state_path)

    def close_backends() -> None:
        with created_lock:
            backends = list(created)
        for b in backends:
            close = getattr(b, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # noqa: BLE001 - best-effort cleanup
                    pass

    solve_fn.close_backends = close_backends  # type: ignore[attr-defined]
    return solve_fn


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--trapped", required=True, help="scratch/phase2/trapped_*.txt")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seeds", default=None, help="comma-separated; default = config.eval.seeds")
    ap.add_argument("--budget", type=int, default=None, help="default = max(config.budget.values)")
    ap.add_argument("--max-rounds", type=int, default=8, help="decomposition attempts cap per cell")
    ap.add_argument("--max-subgoal-rounds", type=int, default=8, help="propose attempts per subgoal")
    ap.add_argument("--n-workers", type=int, default=None)
    args = ap.parse_args()

    config = load_config(args.config)
    apply_env(config)
    run_dir = Path(args.out)

    trapped_names = {ln.strip() for ln in Path(args.trapped).read_text().splitlines() if ln.strip()}
    dataset = load_dataset(config, model_revision=config.model.revision)
    dataset.problems = [p for p in dataset.problems if p.name in trapped_names]
    if not dataset.problems:
        raise SystemExit(
            f"[phase-decomp] 0/{len(trapped_names)} trapped names matched this benchmark's "
            "problem set — wrong --config/--trapped pairing?"
        )
    print(f"[phase-decomp] {len(dataset.problems)}/{len(trapped_names)} trapped names loaded")

    transport = OpenAITransport.from_endpoint_file(
        resolve_endpoint_file(config),
        timeout_s=config.model.request_timeout_s,
        max_retries=config.model.request_max_retries,
    )
    solve_fn = build_decomp_solve_fn(
        config, run_dir, transport, args.max_rounds, args.max_subgoal_rounds
    )

    seeds = [int(s) for s in args.seeds.split(",")] if args.seeds else None
    try:
        result = run_sweep(
            config, dataset, solve_fn, run_dir=run_dir, seeds=seeds, budget=args.budget,
            n_workers=args.n_workers,
        )
    finally:
        solve_fn.close_backends()  # type: ignore[attr-defined]

    print(f"[phase-decomp] {result.n_ran} ran, {result.n_skipped} skipped -> {run_dir}")
    print(f"[phase-decomp] metrics: {result.metrics}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
