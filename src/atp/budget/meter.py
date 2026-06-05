"""Budget meter: the token ledger that makes "fixed-budget proving" exact and enforceable.

The central experimental knob of this project is a per-problem **generation-token budget** `B`.
Every model call spends generated tokens against the current problem's ledger; the agent loop
(Task 0.4) must stop the instant the budget is exhausted, and a requeued job must resume with the
spend it had already incurred (rule 0.3). So this module is:

  * **exact** — tokens are summed from the server's `usage.completion_tokens`, never estimated;
  * **enforcing** — `request()` clamps the next call to what's left and raises `BudgetExhausted`
    cleanly when nothing remains (no crash, the agent saves partial state and moves on);
  * **restartable** — `snapshot()`/`restore()` round-trip the ledger to/from disk.

Pure Python, no heavy deps, so it imports on a login node and unit-tests without a server.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from atp.config import ExperimentConfig


class BudgetExhausted(RuntimeError):
    """Raised when a call is requested but the per-problem token budget is spent.

    Carries the numbers so the agent can log a clean stop reason and persist partial state
    rather than crashing.
    """

    def __init__(self, spent: int, limit: int, requested: int | None = None) -> None:
        self.spent = spent
        self.limit = limit
        self.requested = requested
        msg = f"budget exhausted: {spent}/{limit} tokens spent"
        if requested is not None:
            msg += f"; requested {requested} more"
        super().__init__(msg)


@dataclass(frozen=True)
class LedgerEntry:
    """One charged call: how many tokens, what it was for, and the running total after it."""

    label: str
    tokens: int
    cumulative: int


@dataclass
class BudgetMeter:
    """Tracks generated tokens spent against a per-problem limit `B`.

    Usage pattern (paired with the model client):
        allowed = meter.request(want_max_tokens)   # clamp to remaining; raises if nothing left
        completion = client.generate(prompt, max_tokens=allowed)
        meter.spend(completion.completion_tokens, label="propose")
    """

    limit: int
    spent: int = 0
    ledger: list[LedgerEntry] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.limit < 0:
            raise ValueError(f"budget limit must be non-negative, got {self.limit}")
        if self.spent < 0:
            raise ValueError(f"spent must be non-negative, got {self.spent}")

    # -- views -------------------------------------------------------------------------
    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.spent)

    @property
    def exhausted(self) -> bool:
        return self.remaining == 0

    # -- enforcement -------------------------------------------------------------------
    def request(self, tokens: int) -> int:
        """Tokens the next call may generate: ``min(tokens, remaining)``.

        Raises `BudgetExhausted` if the budget is already spent, so the caller never issues a
        zero-length (pointless) generation and gets a clean stop signal instead.
        """
        if tokens < 0:
            raise ValueError(f"requested tokens must be non-negative, got {tokens}")
        if self.exhausted:
            raise BudgetExhausted(self.spent, self.limit, requested=tokens)
        return min(tokens, self.remaining)

    def can_afford(self, tokens: int) -> bool:
        return tokens <= self.remaining

    def check(self) -> None:
        """Raise if the budget is exhausted (cheap guard at the top of an agent iteration)."""
        if self.exhausted:
            raise BudgetExhausted(self.spent, self.limit)

    def spend(self, tokens: int, label: str = "") -> int:
        """Charge `tokens` to the ledger and return the new remaining count.

        Records actual generated tokens (the work has already happened), so accounting stays
        exact even if a server returns slightly more than requested. Use `request()` beforehand
        to keep generations inside the budget.
        """
        if tokens < 0:
            raise ValueError(f"spent tokens must be non-negative, got {tokens}")
        self.spent += tokens
        self.ledger.append(LedgerEntry(label=label, tokens=tokens, cumulative=self.spent))
        return self.remaining

    # -- restartability (rule 0.3) -----------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        """Serializable state for checkpointing a requeue-able job."""
        return {
            "limit": self.limit,
            "spent": self.spent,
            "ledger": [asdict(e) for e in self.ledger],
        }

    @classmethod
    def restore(cls, state: dict[str, Any]) -> BudgetMeter:
        """Rebuild a meter from `snapshot()` output, preserving spend and ledger."""
        meter = cls(limit=state["limit"], spent=state["spent"])
        meter.ledger = [LedgerEntry(**e) for e in state.get("ledger", [])]
        return meter

    @classmethod
    def from_config(cls, config: ExperimentConfig, value: int | None = None) -> BudgetMeter:
        """Build a meter for one budget point.

        `config.budget.values` is the *curve* of budgets pass@B is reported over; a single run
        fixes one. Defaults to the largest configured value when `value` is omitted.
        """
        values = config.budget.values
        if not values:
            raise ValueError("config.budget.values is empty; nothing to meter")
        if value is None:
            value = max(values)
        elif value not in values:
            raise ValueError(f"budget {value} not in configured values {values}")
        return cls(limit=value)
