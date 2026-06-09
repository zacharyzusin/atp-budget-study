"""Assemble + run a real eval (Task 0.6): the one-command baseline path.

`run_eval` wires the full stack — dataset → vLLM client → Pantograph verifier → whole-proof agent →
restartable sweep → metrics + manifest + plot — and writes everything under `results/<run>/`.

`transport` and `backend` are injectable so the whole assembly is integration-tested with
`ScriptedTransport` + `ScriptedBackend` (no GPU/Lean). Left as None (the production path), it builds
an `OpenAITransport` from the vLLM endpoint file and a `ReplBackend` on the Goedel-pinned env — the
env whose numbers are the only ones we report (DECISIONS.md guardrail). (ReplBackend supersedes
PantographBackend for the pin: PyPantograph has no v4.9.0-rc1 release — DECISIONS.md 2026-06-05.)
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from atp.agents.whole_proof import WholeProofAgent
from atp.budget.meter import BudgetMeter
from atp.config import apply_env
from atp.data import load_dataset
from atp.eval.harness import RunResult, SolveFn, run_sweep
from atp.eval.metrics import pass_at_b
from atp.lean.backends import LeanBackend
from atp.lean.repl import ReplBackend
from atp.lean.verifier import Verifier
from atp.models.client import OpenAITransport, Transport, VLLMClient

if TYPE_CHECKING:
    from atp.config import ExperimentConfig


def build_solve_fn(
    config: ExperimentConfig,
    run_dir: Path,
    transport: Transport,
    backend_factory: Callable[[], LeanBackend],
) -> SolveFn:
    """A `solve_fn` that runs the whole-proof agent for one (problem, seed) at a given budget.

    The Lean REPL is a single, non-thread-safe stdio subprocess, so under concurrency each worker
    thread must own one. `backend_factory()` builds a backend; we cache it in thread-local storage
    so a thread reuses its backend (amortizing its one-time `import Mathlib`) across the cells it
    runs. The vLLM `transport` is an HTTP client and is shared (thread-safe) so the server batches
    requests. Created backends are tracked for `close_backends()` cleanup at the end of the sweep.
    """
    states_dir = run_dir / "agent_states"
    tls = threading.local()
    created: list[LeanBackend] = []
    created_lock = threading.Lock()

    def _thread_backend() -> LeanBackend:
        b = getattr(tls, "backend", None)
        if b is None:
            b = backend_factory()
            tls.backend = b
            with created_lock:
                created.append(b)
        return b

    def solve_fn(problem, seed, budget):
        meter = BudgetMeter(limit=budget)
        client = VLLMClient.from_config(config, transport, meter)
        client.seed = seed  # reproducible per-seed sampling
        verifier = Verifier.from_config(config, _thread_backend())
        agent = WholeProofAgent.from_config(config, client, verifier)
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


def run_eval(
    config: ExperimentConfig,
    run_dir: str | Path,
    *,
    transport: Transport | None = None,
    backend: LeanBackend | None = None,
    novel_names: Iterable[str] = (),
    resume: bool = True,
) -> RunResult:
    apply_env(config)
    run_dir = Path(run_dir)

    dataset = load_dataset(config, model_revision=config.model.revision, novel_names=novel_names)
    if transport is None:
        transport = OpenAITransport.from_endpoint_file(
            config.model.endpoint_file,
            timeout_s=config.model.request_timeout_s,
            max_retries=config.model.request_max_retries,
        )

    # Production: each worker thread builds its OWN ReplBackend (own Lean subprocess). An injected
    # backend (tests) is shared — fine because tests run n_workers=1.
    def backend_factory() -> LeanBackend:
        return ReplBackend(config) if backend is None else backend

    solve_fn = build_solve_fn(config, run_dir, transport, backend_factory)
    try:
        result = run_sweep(config, dataset, solve_fn, run_dir=run_dir, resume=resume)
    finally:
        solve_fn.close_backends()  # type: ignore[attr-defined]

    # Plot the curve next to the metrics (lazy matplotlib import).
    from atp.eval.plot import plot_pass_at_b

    curve = pass_at_b(result.results, list(config.budget.values))
    title = f"{config.model.name} · {dataset.manifest.split}"
    plot_pass_at_b(curve, run_dir / "pass_at_b.png", title=title)
    return result
