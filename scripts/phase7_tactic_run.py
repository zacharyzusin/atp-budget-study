#!/usr/bin/env python3
"""Phase 7 Track 1 — Mode 4 (true stepwise, one tactic per call) real eval run.

The strong exposure-bias disambiguator: Mode 3 re-grounds the state but then free-runs a WHOLE
continuation (which can drift again before it reaches a real closing tactic), so "Mode 3 engages
but doesn't close" cannot distinguish "exposure bias isn't the bottleneck" from "single-shot
re-grounding is too weak." Mode 4 removes the confound — one tactic per call, conditioned on the
TRUE current goal state via `ReplBackend.elaborate`, every tactic validated before commit. Same
restartable-sweep machinery as Mode 3 (`atp.eval.harness.run_sweep`), same `results/<run>/
{problems,agent_states}/` output layout.

Usage (on a GPU node with the vLLM server up + ATP_VLLM_ENDPOINT_FILE set):
  python scripts/phase7_tactic_run.py --config configs/proofnet_baseline.yaml \
      --trapped scratch/phase7/mode3_engaged_names.txt --out results/phase7/goedel_proofnet_mode4 \
      --seeds 0 --budget 32000 --max-steps 40
"""

from __future__ import annotations

import argparse
import threading
from pathlib import Path

from atp.agents.tactic_stepwise import BeamTacticStepwiseAgent
from atp.budget.meter import BudgetMeter
from atp.config import apply_env, load_config
from atp.data import load_dataset
from atp.eval.harness import run_sweep
from atp.eval.run import resolve_endpoint_file
from atp.lean.backends import LeanBackend
from atp.lean.repl import ReplBackend
from atp.lean.verifier import Verifier
from atp.models.client import OpenAITransport, VLLMClient
from atp.models.templates import template_from_config


def build_tactic_solve_fn(
    config, run_dir: Path, transport, max_steps: int, retries_per_step: int,
    beam_width: int = 3, sample_max_tokens: int = 768,
):
    """Mirrors `phase7_stepwise_run.build_stepwise_solve_fn`'s thread-local Lean-backend pattern,
    wiring `BeamTacticStepwiseAgent` (Mode 4, best-first-with-backtracking) instead. Uses
    `config.model.prompt_template` via `template_from_config` — NOT a hardcoded template (a real
    bug found 2026-07-05: this function hardcoded `TacticTemplate()` regardless of config, so a
    BFS-Prover run never actually used `BFSProverTemplate`'s native format)."""
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

    def elaborate(theorem, source: str) -> dict:
        return _thread_backend().elaborate(theorem, source)

    def solve_fn(problem, seed, budget):
        meter = BudgetMeter(limit=budget)
        client = VLLMClient.from_config(config, transport, meter)
        client.seed = seed
        verifier = Verifier.from_config(config, _thread_backend())
        agent = BeamTacticStepwiseAgent(
            client=client,
            verifier=verifier,
            template=template_from_config(config),
            elaborate=elaborate,
            max_steps=max_steps,
            beam_width=beam_width,
            retries_per_step=retries_per_step,
            sample_max_tokens=sample_max_tokens,
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
    ap.add_argument("--trapped", required=True, help="a name-per-line file (any subset)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seeds", default=None, help="comma-separated; default = config.eval.seeds")
    ap.add_argument("--budget", type=int, default=None, help="default = max(config.budget.values)")
    ap.add_argument("--max-steps", type=int, default=40, help="node expansions cap per cell")
    ap.add_argument("--beam-width", type=int, default=3, help="candidates kept per node")
    ap.add_argument("--retries-per-step", type=int, default=4)
    ap.add_argument(
        "--sample-max-tokens", type=int, default=768,
        help="reasoning models need CoT room before they answer — see DECISIONS.md 2026-07-05",
    )
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
            f"[phase7-tactic] 0/{len(trapped_names)} trapped names matched this benchmark's "
            "problem set — wrong --config/--trapped pairing?"
        )
    print(f"[phase7-tactic] {len(dataset.problems)}/{len(trapped_names)} trapped names loaded")

    transport = OpenAITransport.from_endpoint_file(
        resolve_endpoint_file(config),
        timeout_s=config.model.request_timeout_s,
        max_retries=config.model.request_max_retries,
    )
    solve_fn = build_tactic_solve_fn(
        config, run_dir, transport, args.max_steps, args.retries_per_step,
        beam_width=args.beam_width, sample_max_tokens=args.sample_max_tokens,
    )

    seeds = [int(s) for s in args.seeds.split(",")] if args.seeds else None
    try:
        result = run_sweep(
            config, dataset, solve_fn, run_dir=run_dir, seeds=seeds, budget=args.budget,
            n_workers=args.n_workers,
        )
    finally:
        solve_fn.close_backends()  # type: ignore[attr-defined]

    print(f"[phase7-tactic] {result.n_ran} ran, {result.n_skipped} skipped -> {run_dir}")
    print(f"[phase7-tactic] metrics: {result.metrics}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
