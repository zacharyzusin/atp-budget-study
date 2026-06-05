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
) -> RunResult:
    seeds = list(seeds if seeds is not None else config.eval.seeds)
    budgets = list(config.budget.values)
    budget = budget if budget is not None else max(budgets)
    cfg_hash = config_hash(config)

    run_dir = Path(run_dir)
    problems_dir = run_dir / "problems"
    problems_dir.mkdir(parents=True, exist_ok=True)

    started = _now()
    results: list[ProblemResult] = []
    n_ran = n_skipped = 0

    for seed in seeds:
        for problem in dataset.problems:
            cell = _cell_path(problems_dir, problem.name, seed)
            if resume and cell.exists():
                results.append(ProblemResult.load(cell))
                n_skipped += 1
                continue
            state = solve_fn(problem, seed, budget)
            res = ProblemResult.from_agent_state(
                state,
                seed=seed,
                budget=budget,
                benchmark=problem.benchmark,
                split=problem.split,
                config_hash=cfg_hash,
            )
            res.save(cell)
            results.append(res)
            n_ran += 1

    finished = _now()
    metrics = summarize(results, budgets)
    manifest = build_run_manifest(
        config,
        dataset.manifest,
        seeds=seeds,
        budgets=budgets,
        started_at=started,
        finished_at=finished,
        extra={"n_ran": n_ran, "n_skipped": n_skipped},
    )
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True))
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return RunResult(run_dir, results, metrics, manifest, n_ran, n_skipped)
