"""Restartable eval sweep over a problem set (Task 0.6).

Runs each (problem, seed) cell once at the run's max budget; the per-cell record carries
`tokens_to_solve`, so `pass@B` for every smaller B comes from the same run. **Restartable** (rule
0.3 / rule 3): a completed cell's JSON is the resume signal — on requeue the sweep loads it and
skips the work, so a preempted sweep never redoes solved cells.

The actual proving is injected as `solve_fn(problem, seed, budget) -> AgentState`, so the harness is
fully exercised with mocks (no GPU/Lean). The real `solve_fn` (vLLM client + Pantograph verifier +
WholeProofAgent) is assembled by the eval entry point once the GPU + Goedel-pin env are up.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from atp.config import config_hash
from atp.eval.manifest import build_run_manifest
from atp.eval.metrics import summarize
from atp.eval.records import ProblemResult

if TYPE_CHECKING:
    from atp.agents.state import AgentState
    from atp.config import ExperimentConfig
    from atp.data import Dataset, Problem

SolveFn = Callable[["Problem", int, int], "AgentState"]


@dataclass
class RunResult:
    run_dir: Path
    results: list[ProblemResult]
    metrics: dict
    manifest: dict
    n_ran: int
    n_skipped: int


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _cell_path(problems_dir: Path, name: str, seed: int) -> Path:
    safe = name.replace("/", "_").replace(" ", "_")
    return problems_dir / f"{safe}__seed{seed}.json"


def run_sweep(
    config: ExperimentConfig,
    dataset: Dataset,
    solve_fn: SolveFn,
    *,
    run_dir: str | Path,
    seeds: list[int] | None = None,
    budget: int | None = None,
    resume: bool = True,
    n_workers: int | None = None,
) -> RunResult:
    seeds = list(seeds if seeds is not None else config.eval.seeds)
    budgets = list(config.budget.values)
    budget = budget if budget is not None else max(budgets)
    cfg_hash = config_hash(config)
    n_workers = config.eval.n_workers if n_workers is None else n_workers

    run_dir = Path(run_dir)
    problems_dir = run_dir / "problems"
    problems_dir.mkdir(parents=True, exist_ok=True)

    started = _now()

    # Resume first (cheap, serial): load finished cells, queue the rest. Preserve cell order so the
    # metrics/results are deterministic regardless of n_workers.
    done: list[ProblemResult] = []
    pending: list[tuple[int, Problem, Path]] = []
    for seed in seeds:
        for problem in dataset.problems:
            cell = _cell_path(problems_dir, problem.name, seed)
            if resume and cell.exists():
                done.append(ProblemResult.load(cell))
            else:
                pending.append((seed, problem, cell))
    n_skipped = len(done)

    def _run_cell(args: tuple[int, Problem, Path]) -> ProblemResult | None:
        # CONTAINMENT (rule 3): one cell's failure must never abort the sweep. A transient vLLM
        # timeout once propagated through ThreadPoolExecutor.map and killed baseline 10272937 at
        # 165 cells with no metrics written. On any exception we log it and return None (the cell
        # file is NOT written), so the cell is just retried on the next resume instead of crashing.
        seed, problem, cell = args
        try:
            state = solve_fn(problem, seed, budget)
            res = ProblemResult.from_agent_state(
                state,
                seed=seed,
                budget=budget,
                benchmark=problem.benchmark,
                split=problem.split,
                config_hash=cfg_hash,
            )
            res.save(cell)  # each cell writes a distinct file -> safe from worker threads
            return res
        except Exception as exc:  # noqa: BLE001 - deliberate per-cell containment
            import traceback

            print(
                f"[sweep] CELL FAILED (will retry on resume) {problem.name} seed={seed}: "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )
            traceback.print_exc()
            return None

    if n_workers and n_workers > 1 and len(pending) > 1:
        # solve_fn is I/O-bound on the vLLM HTTP call (GPU batches concurrent requests), and each
        # worker thread uses its OWN Lean REPL (see build_solve_fn), so cells run safely in parallel
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            ran = [r for r in pool.map(_run_cell, pending) if r is not None]
    else:
        ran = [r for a in pending if (r := _run_cell(a)) is not None]

    results = done + ran
    n_ran = len(ran)
    n_failed = len(pending) - n_ran

    finished = _now()
    metrics = summarize(results, budgets)
    manifest = build_run_manifest(
        config,
        dataset.manifest,
        seeds=seeds,
        budgets=budgets,
        started_at=started,
        finished_at=finished,
        extra={"n_ran": n_ran, "n_skipped": n_skipped, "n_failed": n_failed},
    )
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True))
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return RunResult(run_dir, results, metrics, manifest, n_ran, n_skipped)
