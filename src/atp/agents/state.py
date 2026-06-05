"""Persistent agent state for the whole-proof loop (Task 0.4).

The cluster preempts and **requeues from scratch** (rule 0.3), so the agent checkpoints its full
state to disk after every attempt. State captures enough to resume exactly:

  * every attempt made (kind, proof, verdict, tokens) — an auditable trail for analysis;
  * the budget meter snapshot — so a resumed run continues spending from where it stopped;
  * whether/how it finished — so a resumed *solved* problem short-circuits instead of redoing work.

Plain JSON (atomic write) — no heavy deps, human-inspectable in `results/<run>/problems/<id>.json`.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Why the loop stopped — one of these is always set once `done` is True.
STOP_SOLVED = "solved"
STOP_BUDGET = "budget_exhausted"
STOP_MAX_ROUNDS = "max_rounds"
STOP_NO_PROGRESS = "no_progress"  # a generation produced 0 tokens; can't make progress


@dataclass(frozen=True)
class Attempt:
    """One proposer/refiner call + its verifier verdict."""

    index: int
    kind: str  # "propose" | "refine"
    proof: str
    ok: bool
    reason: str  # VerifyResult.reason: ok | compile_error | timeout | loophole
    feedback: str
    completion_tokens: int


@dataclass
class AgentState:
    """The full, resumable state of one problem's proof search."""

    theorem_name: str
    done: bool = False
    stop_reason: str | None = None
    proof: str | None = None  # the verified proof, once solved
    attempts: list[Attempt] = field(default_factory=list)
    budget: dict[str, Any] = field(default_factory=dict)  # BudgetMeter.snapshot()

    @property
    def solved(self) -> bool:
        return self.stop_reason == STOP_SOLVED

    @property
    def n_attempts(self) -> int:
        return len(self.attempts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "theorem_name": self.theorem_name,
            "done": self.done,
            "stop_reason": self.stop_reason,
            "proof": self.proof,
            "attempts": [asdict(a) for a in self.attempts],
            "budget": self.budget,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentState:
        return cls(
            theorem_name=data["theorem_name"],
            done=data.get("done", False),
            stop_reason=data.get("stop_reason"),
            proof=data.get("proof"),
            attempts=[Attempt(**a) for a in data.get("attempts", [])],
            budget=data.get("budget", {}),
        )

    def save(self, path: str | os.PathLike[str]) -> None:
        """Atomically write state to `path` (tmp file + rename) so a preempt mid-write is safe."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True))
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: str | os.PathLike[str]) -> AgentState | None:
        """Load state from `path`, or None if there's no checkpoint yet."""
        path = Path(path)
        if not path.exists():
            return None
        return cls.from_dict(json.loads(path.read_text()))
