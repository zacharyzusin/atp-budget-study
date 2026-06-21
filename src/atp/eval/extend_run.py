"""Resume-extend a set of budget-exhausted cells to a higher budget (Phase 5 reclaim-and-reinvest).

`run_extend` is the GPU entry point for the extension runs: it takes specific (problem, seed) cells
that were *unsolved at 128k* in a baseline run, copies each one's logged 128k checkpoint into a
fresh run dir, and calls `WholeProofAgent.extend` to continue the search up to `new_budget`. The
logged 128k prefix is preserved verbatim (we never regenerate it); only `(128k, new_budget]` is
sampled. So a newly solved cell is, by construction, an *extension solve* (`tokens_to_solve > 128k`)
and the run realizes `Solves_reinvest ⊇ Solves_uniform`. See DECISIONS.md 2026-06-21 for why this
resumes, not re-runs.

Restartable (rule 0.3): a cell whose extended `ProblemResult` is already on disk and is finished
(solved, or spent == new_budget) is skipped on requeue; a partially-extended checkpoint resumes from
where it stopped (the copied state is updated in place, never re-copied over).

Stack assembly mirrors `run_eval` (injectable `transport`/`backend` for the no-GPU smoke test). The
pilot is small, so cells run sequentially over one Lean backend (amortizing its `import Mathlib`).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from atp.agents.whole_proof import WholeProofAgent
from atp.budget.meter import BudgetMeter
from atp.config import apply_env, config_hash
from atp.data import load_dataset
from atp.data.contamination import load_novel_names
from atp.eval.records import ProblemResult
from atp.lean.verifier import Verifier
from atp.models.client import OpenAITransport, VLLMClient

if TYPE_CHECKING:
    from atp.config import ExperimentConfig
    from atp.lean.backends import LeanBackend
    from atp.models.client import Transport


def _cell_finished(result_path: Path, new_budget: int) -> bool:
    """Has this cell already been extended to completion (solved, or the full new budget spent)?"""
    if not result_path.exists():
        return False
    r = ProblemResult.load(result_path)
    return r is not None and (r.solved or r.tokens_spent >= new_budget)


def run_extend(
    config: ExperimentConfig,
    run_dir: str | Path,
    baseline_dir: str | Path,
    cells: list[tuple[str, int]],
    new_budget: int,
    *,
    transport: Transport | None = None,
    backend: LeanBackend | None = None,
) -> dict:
    """Extend `cells` (problem_name, seed) from `baseline_dir`'s 128k checkpoints to `new_budget`.

    Writes extended agent states under `run_dir/agent_states/` and `ProblemResult`s under
    `run_dir/problems/`. Returns a summary dict (counts + per-seed extension solves).
    """
    apply_env(config)
    run_dir, baseline_dir = Path(run_dir), Path(baseline_dir)
    states_dir = run_dir / "agent_states"
    problems_dir = run_dir / "problems"
    states_dir.mkdir(parents=True, exist_ok=True)
    problems_dir.mkdir(parents=True, exist_ok=True)
    src_states = baseline_dir / "agent_states"

    names = load_novel_names(config)
    dataset = load_dataset(config, model_revision=config.model.revision, novel_names=names)
    by_name = {p.name: p for p in dataset.problems}

    if transport is None:
        # Honor a per-job endpoint file (ATP_VLLM_ENDPOINT_FILE) so two concurrent pilots serving
        # DIFFERENT provers never cross-read each other's endpoint (the shared-file collision).
        from atp.eval.run import resolve_endpoint_file
        transport = OpenAITransport.from_endpoint_file(
            resolve_endpoint_file(config),
            timeout_s=config.model.request_timeout_s,
            max_retries=config.model.request_max_retries,
        )

    def backend_factory() -> LeanBackend:
        if backend is not None:
            return backend
        from atp.lean.repl import ReplBackend
        return ReplBackend(config)

    chash = config_hash(config)
    lean_backend = backend_factory()
    ran, skipped, solves, ext_solves_per_seed = 0, 0, 0, {}
    try:
        for name, seed in cells:
            result_path = problems_dir / f"{name}__seed{seed}.json"
            if _cell_finished(result_path, new_budget):
                skipped += 1
                continue
            if name not in by_name:
                raise KeyError(f"pilot cell {name!r} absent from {config.data.benchmark} split")

            dst_state = states_dir / f"{name}__seed{seed}.json"
            if not dst_state.exists():  # first touch: seed the logged 128k prefix (never re-copy)
                src = src_states / f"{name}__seed{seed}.json"
                if not src.exists():
                    raise FileNotFoundError(f"no baseline checkpoint to extend at {src}")
                shutil.copy2(src, dst_state)

            meter = BudgetMeter(limit=new_budget)
            client = VLLMClient.from_config(config, transport, meter)
            client.seed = seed
            verifier = Verifier.from_config(config, lean_backend)
            agent = WholeProofAgent.from_config(config, client, verifier)

            theorem = by_name[name].to_theorem()
            state = agent.extend(theorem, dst_state, new_budget)
            result = ProblemResult.from_agent_state(
                state, seed=seed, budget=new_budget,
                benchmark=config.data.benchmark, split=config.data.split, config_hash=chash,
            )
            result.save(result_path)
            ran += 1
            if state.solved:  # every cell was unsolved at 128k -> any solve is an extension solve
                solves += 1
                ext_solves_per_seed[seed] = ext_solves_per_seed.get(seed, 0) + 1
    finally:
        close = getattr(lean_backend, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # noqa: BLE001 - best-effort cleanup
                pass

    return {
        "run_dir": str(run_dir), "baseline_dir": str(baseline_dir),
        "new_budget": new_budget, "n_cells": len(cells),
        "n_ran": ran, "n_skipped": skipped, "n_extension_solves": solves,
        "extension_solves_per_seed": dict(sorted(ext_solves_per_seed.items())),
    }


def load_pilot_cells(
    candidates_json: str | Path, model: str, benchmark: str,
) -> list[tuple[str, int]]:
    """Read the stratified pilot cells (problem_name, seed) for one run from candidates.json."""
    import json

    data = json.loads(Path(candidates_json).read_text())
    for e in data:
        if e["model"] == model and e["benchmark"] == benchmark:
            return [(c["problem_name"], c["seed"]) for c in e["pilot_cells"]]
    raise KeyError(f"no candidates entry for {model} x {benchmark} in {candidates_json}")
