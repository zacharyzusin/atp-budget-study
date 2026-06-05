"""Per-problem eval record — the unit the harness writes and the metrics consume.

One `ProblemResult` per (problem, seed) cell. We run each cell once at the run's max budget and
record *when* (cumulative tokens) the proof was found, so the whole `pass@B` curve for every smaller
`B` is derivable from a single run (no re-running per budget point). Serialized as
`results/<run>/problems/<name>__seed<k>.json` — both the resume signal and the audit trail.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from atp.agents.state import AgentState


@dataclass(frozen=True)
class ProblemResult:
    problem_name: str
    seed: int
    budget: int  # the run's max per-problem budget B this cell was given
    solved: bool
    stop_reason: str
    tokens_to_solve: int | None  # cumulative tokens at the solving attempt (None if unsolved)
    tokens_spent: int  # total generated tokens spent in this cell
    n_attempts: int
    benchmark: str = ""
    split: str = ""
    config_hash: str = ""

    @classmethod
    def from_agent_state(
        cls,
        state: AgentState,
        *,
        seed: int,
        budget: int,
        benchmark: str = "",
        split: str = "",
        config_hash: str = "",
    ) -> ProblemResult:
        spent = int(state.budget.get("spent", 0)) if state.budget else 0
        return cls(
            problem_name=state.theorem_name,
            seed=seed,
            budget=budget,
            solved=state.solved,
            stop_reason=state.stop_reason or "",
            tokens_to_solve=spent if state.solved else None,
            tokens_spent=spent,
            n_attempts=state.n_attempts,
            benchmark=benchmark,
            split=split,
            config_hash=config_hash,
        )

    def solved_within(self, b: int) -> bool:
        """True iff this cell found a verified proof using ≤ `b` generated tokens."""
        return self.solved and self.tokens_to_solve is not None and self.tokens_to_solve <= b

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ProblemResult:
        return cls(**d)

    def save(self, path: str | os.PathLike[str]) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True))
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: str | os.PathLike[str]) -> ProblemResult:
        return cls.from_dict(json.loads(Path(path).read_text()))
