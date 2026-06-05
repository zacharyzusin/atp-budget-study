"""Assemble + run a real eval (Task 0.6): the one-command baseline path.

`run_eval` wires the full stack — dataset → vLLM client → Pantograph verifier → whole-proof agent →
restartable sweep → metrics + manifest + plot — and writes everything under `results/<run>/`.

`transport` and `backend` are injectable so the whole assembly is integration-tested with
`ScriptedTransport` + `ScriptedBackend` (no GPU/Lean). Left as None (the production path), it builds
an `OpenAITransport` from the vLLM endpoint file and a `PantographBackend` on the Goedel-pinned
env — the env whose numbers are the only ones we report (DECISIONS.md guardrail).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from atp.agents.whole_proof import WholeProofAgent
from atp.budget.meter import BudgetMeter
from atp.config import apply_env
from atp.data import load_dataset
from atp.eval.harness import RunResult, SolveFn, run_sweep
from atp.eval.metrics import pass_at_b
from atp.lean.backends import LeanBackend, PantographBackend
from atp.lean.verifier import Verifier
from atp.models.client import OpenAITransport, Transport, VLLMClient

if TYPE_CHECKING:
    from atp.config import ExperimentConfig


def build_solve_fn(
    config: ExperimentConfig,
    run_dir: Path,
    transport: Transport,
    backend: LeanBackend,
) -> SolveFn:
    """A `solve_fn` that runs the whole-proof agent for one (problem, seed) at a given budget."""
    states_dir = run_dir / "agent_states"

    def solve_fn(problem, seed, budget):
        meter = BudgetMeter(limit=budget)
        client = VLLMClient.from_config(config, transport, meter)
        client.seed = seed  # reproducible per-seed sampling
        verifier = Verifier.from_config(config, backend)
        agent = WholeProofAgent.from_config(config, client, verifier)
        state_path = states_dir / f"{problem.name}__seed{seed}.json"
        return agent.prove(problem.to_theorem(), state_path=state_path)

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
        transport = OpenAITransport.from_endpoint_file(config.model.endpoint_file)
    if backend is None:
        backend = PantographBackend(config)

    solve_fn = build_solve_fn(config, run_dir, transport, backend)
    result = run_sweep(config, dataset, solve_fn, run_dir=run_dir, resume=resume)

    # Plot the curve next to the metrics (lazy matplotlib import).
    from atp.eval.plot import plot_pass_at_b

    curve = pass_at_b(result.results, list(config.budget.values))
    title = f"{config.model.name} · {dataset.manifest.split}"
    plot_pass_at_b(curve, run_dir / "pass_at_b.png", title=title)
    return result
