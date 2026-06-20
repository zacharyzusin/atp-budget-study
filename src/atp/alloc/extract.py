"""Load the four budget-independent baseline runs into tidy per-cell records (Task 4.1).

Source of truth = the committed per-cell JSONs under `results/<run>/problems/`. Each loads into a
`ProblemResult` carrying `tokens_to_solve` / `solved` — all Task 4.1 needs for the §0 identity, the
cost distribution and the oracle ceiling. (The richer checkpoint features F1/F3 for the *realizable*
policies are extracted separately in `features.py` from `agent_states/`.)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from atp.alloc.policies import solve_cost
from atp.eval.records import ProblemResult

# (run_dir, model, benchmark) for the four budget-independent baselines the §0 identity applies to.
BASELINE_RUNS: list[tuple[str, str, str]] = [
    ("baseline", "goedel", "minif2f"),
    ("proofnet_baseline", "goedel", "proofnet_sharp"),
    ("deepseek_minif2f_baseline", "deepseek", "minif2f"),
    ("deepseek_proofnet_baseline", "deepseek", "proofnet_sharp"),
]


@dataclass(frozen=True)
class RunTable:
    model: str
    benchmark: str
    run_dir: str
    results: list[ProblemResult]

    @property
    def n_cells(self) -> int:
        return len(self.results)

    @property
    def costs(self) -> list[float]:
        """Per-cell solve cost (tokens_to_solve, or +inf if unsolved) — the policy input."""
        return [solve_cost(r) for r in self.results]

    @property
    def n_solved(self) -> int:
        return sum(1 for r in self.results if r.solved)


def load_run(run_dir: str | Path, model: str = "", benchmark: str = "") -> RunTable:
    run_dir = Path(run_dir)
    cells = sorted((run_dir / "problems").glob("*.json"))
    if not cells:
        raise FileNotFoundError(f"no per-cell JSONs under {run_dir}/problems")
    results = [ProblemResult.load(c) for c in cells]
    return RunTable(model=model, benchmark=benchmark, run_dir=str(run_dir), results=results)


def load_baselines(results_root: str | Path) -> list[RunTable]:
    root = Path(results_root)
    return [load_run(root / d, model=m, benchmark=b) for d, m, b in BASELINE_RUNS]
