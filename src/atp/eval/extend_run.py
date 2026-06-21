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
import threading
from collections.abc import Callable
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
    backend_factory: Callable[[], LeanBackend] | None = None,
    n_workers: int | None = None,
) -> dict:
    """Extend `cells` (problem_name, seed) from `baseline_dir`'s 128k checkpoints to `new_budget`.

    Writes extended agent states under `run_dir/agent_states/` and `ProblemResult`s under
    `run_dir/problems/`. Returns a summary dict (counts + per-seed extension solves).

    Cells run concurrently over `n_workers` threads (default `config.eval.n_workers`): each extends
    up to `new_budget` tokens, so sequential single-stream throughput (~40 tok/s) would blow the
    walltime; with workers, vLLM batches the streams and the GPU stays busy while a cell verifies in
    Lean. Each worker owns its OWN Lean REPL (thread-local, not thread-safe to share), mirroring
    `eval.run.build_solve_fn`. An *injected* `backend` (tests) forces sequential — it is shared. A
    per-cell failure is contained (logged, counted) so a requeue retries just that cell (rule 0.3).
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

    # A shared (injected) backend is not REPL-thread-safe -> force sequential; otherwise each worker
    # thread builds + caches its OWN backend (amortizing its one-time `import Mathlib`), via
    # `backend_factory` (default: a fresh ReplBackend on the configured Lean env).
    workers = 1 if backend is not None else (n_workers or config.eval.n_workers)
    if backend_factory is None:
        def backend_factory() -> LeanBackend:
            from atp.lean.repl import ReplBackend
            return ReplBackend(config)
    tls = threading.local()
    created: list[LeanBackend] = []
    created_lock = threading.Lock()

    def thread_backend() -> LeanBackend:
        if backend is not None:
            return backend
        b = getattr(tls, "backend", None)
        if b is None:
            b = backend_factory()
            tls.backend = b
            with created_lock:
                created.append(b)
        return b

    chash = config_hash(config)
    skipped_lock = threading.Lock()
    counters = {"skipped": 0}

    def extend_one(cell: tuple[str, int]) -> dict | None:
        """Extend a single cell; returns {seed, solved} on success, None on skip/failure."""
        name, seed = cell
        result_path = problems_dir / f"{name}__seed{seed}.json"
        if _cell_finished(result_path, new_budget):
            with skipped_lock:
                counters["skipped"] += 1
            return None
        if name not in by_name:
            raise KeyError(f"pilot cell {name!r} absent from {config.data.benchmark} split")
        try:
            dst_state = states_dir / f"{name}__seed{seed}.json"
            if not dst_state.exists():  # first touch: seed the logged 128k prefix (never re-copy)
                src = src_states / f"{name}__seed{seed}.json"
                if not src.exists():
                    raise FileNotFoundError(f"no baseline checkpoint to extend at {src}")
                shutil.copy2(src, dst_state)

            meter = BudgetMeter(limit=new_budget)
            client = VLLMClient.from_config(config, transport, meter)
            client.seed = seed
            verifier = Verifier.from_config(config, thread_backend())
            agent = WholeProofAgent.from_config(config, client, verifier)

            state = agent.extend(by_name[name].to_theorem(), dst_state, new_budget)
            result = ProblemResult.from_agent_state(
                state, seed=seed, budget=new_budget,
                benchmark=config.data.benchmark, split=config.data.split, config_hash=chash,
            )
            result.save(result_path)
            return {"seed": seed, "solved": state.solved}
        except (FileNotFoundError, KeyError):
            raise  # a setup error (missing checkpoint / bad name) is fatal, not a per-cell retry
        except Exception as exc:  # noqa: BLE001 - contain a per-cell crash so a requeue retries it
            import traceback
            print(f"[pilot] CELL FAILED (will retry on resume) {name} seed={seed}: "
                  f"{type(exc).__name__}: {exc}", flush=True)
            traceback.print_exc()
            return None

    try:
        if workers and workers > 1 and len(cells) > 1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=workers) as pool:
                outs = [o for o in pool.map(extend_one, cells) if o is not None]
        else:
            outs = [o for c in cells if (o := extend_one(c)) is not None]
    finally:
        for b in created:
            close = getattr(b, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # noqa: BLE001 - best-effort cleanup
                    pass

    ext_solves_per_seed: dict[int, int] = {}
    for o in outs:
        if o["solved"]:
            ext_solves_per_seed[o["seed"]] = ext_solves_per_seed.get(o["seed"], 0) + 1
    return {
        "run_dir": str(run_dir), "baseline_dir": str(baseline_dir),
        "new_budget": new_budget, "n_cells": len(cells), "n_workers": workers,
        "n_ran": len(outs), "n_skipped": counters["skipped"],
        "n_extension_solves": sum(1 for o in outs if o["solved"]),
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
