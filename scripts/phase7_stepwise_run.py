#!/usr/bin/env python3
"""Phase 7 Track 1 — Mode 3 (verified-state re-grounding) real eval run.

Restricted to the TRAPPED core (trapped-first, per the plan): the same restartable-sweep machinery
`atp.eval.run` uses for the committed baselines, with `RegroundStepwiseAgent` (Mode 3) swapping in
for `WholeProofAgent` as the per-cell solver. Output composes directly with the existing
`pass_at_b`/`ProblemResult` tooling (same `results/<run>/{problems,agent_states}/` layout), so Mode
3's trapped pass@B is computed the same way as the offline Mode 1/2 reconstruction
(`phase7_offline_modes.py`).

Usage (on a GPU node with the vLLM server up + ATP_VLLM_ENDPOINT_FILE set, mirrors `atp sweep`):
  python scripts/phase7_stepwise_run.py --config configs/proofnet_baseline.yaml \
      --trapped scratch/phase2/trapped_proofnet.txt --out results/phase7/goedel_proofnet_mode3 \
      --seeds 0,1,2 --budget 32000 --max-rounds 8
"""

from __future__ import annotations

import argparse
import threading
from pathlib import Path

from atp.agents.stepwise import RegroundStepwiseAgent
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


def build_stepwise_solve_fn(config, run_dir: Path, transport, max_rounds: int):
    """Mirrors `atp.eval.run.build_solve_fn` — same thread-local Lean-backend pattern — but wires
    `RegroundStepwiseAgent` (Mode 3) instead of `WholeProofAgent` as the per-cell solver."""
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

    def elaborate(theorem, prefix: str) -> bool:
        """A candidate re-grounding prefix is safe iff `<statement> := by\\n<prefix>\\n  sorry`
        elaborates to EXACTLY ONE clean goal — the same deep_state validation the Phase 6 harvest
        used (`ReplBackend.elaborate`), applied online instead of offline. Rejects dangling
        boundaries (e.g. mid a `have h := by` block with no sub-proof) that "elaborated without
        error so far" but aren't a syntactically well-formed stopping point (DECISIONS.md
        2026-07-03 — found live, not hypothesized)."""
        src = f"{theorem.statement.rstrip()} := by\n{prefix}\n  sorry"
        resp = _thread_backend().elaborate(theorem, src)
        return (not resp["infra_error"]) and resp["errors"] == 0 and len(resp["sorries"]) == 1

    def solve_fn(problem, seed, budget):
        meter = BudgetMeter(limit=budget)
        client = VLLMClient.from_config(config, transport, meter)
        client.seed = seed
        verifier = Verifier.from_config(config, _thread_backend())
        agent = RegroundStepwiseAgent(
            client=client,
            verifier=verifier,
            template=WholeProofTemplate(),
            elaborate=elaborate,
            max_rounds=max_rounds,
            sample_max_tokens=config.model.max_model_len // 2,
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
    ap.add_argument("--max-rounds", type=int, default=8, help="re-grounding rounds cap per cell")
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
            f"[phase7-stepwise] 0/{len(trapped_names)} trapped names matched this benchmark's "
            "problem set — wrong --config/--trapped pairing?"
        )
    print(f"[phase7-stepwise] {len(dataset.problems)}/{len(trapped_names)} trapped names loaded")

    transport = OpenAITransport.from_endpoint_file(
        resolve_endpoint_file(config),
        timeout_s=config.model.request_timeout_s,
        max_retries=config.model.request_max_retries,
    )
    solve_fn = build_stepwise_solve_fn(config, run_dir, transport, args.max_rounds)

    seeds = [int(s) for s in args.seeds.split(",")] if args.seeds else None
    try:
        result = run_sweep(
            config, dataset, solve_fn, run_dir=run_dir, seeds=seeds, budget=args.budget,
            n_workers=args.n_workers,
        )
    finally:
        solve_fn.close_backends()  # type: ignore[attr-defined]

    print(f"[phase7-stepwise] {result.n_ran} ran, {result.n_skipped} skipped -> {run_dir}")
    print(f"[phase7-stepwise] metrics: {result.metrics}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
