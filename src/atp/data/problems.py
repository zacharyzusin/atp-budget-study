"""The `Problem` record: one benchmark theorem with everything needed to prove + audit it.

A `Problem` is the data-layer unit; it converts to a `lean.Theorem` (what the agent/verifier
consume) via `to_theorem()`. Beyond the statement we keep **provenance** (which benchmark/commit/
file/line it came from) and **flags** (unprovable / contaminated / novel) so every reported number
is traceable to an exact, audited source (PROJECT_PLAN.md §9).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from atp.lean.backends import Theorem

# Problem flags (membership in `Problem.flags`).
FLAG_UNPROVABLE = "unprovable"  # known-unprovable/ill-posed item (exclusion list)
FLAG_CONTAMINATED = "contaminated"  # plausibly in the model's training corpus
FLAG_NOVEL = "novel"  # held-out novel item (contamination mitigation)


@dataclass(frozen=True)
class Problem:
    name: str
    statement: str  # the declaration head, e.g. "theorem foo (n : Nat) : n + 0 = n" (no ":= proof")
    benchmark: str  # "minif2f" | "proofnet_sharp"
    split: str  # "valid" | "test" | "train" | "novel"
    imports: tuple[str, ...] = ("Mathlib",)
    opens: tuple[str, ...] = ()
    informal_statement: str | None = None
    flags: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def is_unprovable(self) -> bool:
        return FLAG_UNPROVABLE in self.flags

    @property
    def is_novel(self) -> bool:
        return FLAG_NOVEL in self.flags

    @property
    def is_contaminated(self) -> bool:
        return FLAG_CONTAMINATED in self.flags

    def with_flags(self, *flags: str) -> Problem:
        """Return a copy with `flags` added (frozen dataclass → no in-place mutation)."""
        merged = tuple(dict.fromkeys((*self.flags, *flags)))  # dedup, preserve order
        return Problem(
            name=self.name,
            statement=self.statement,
            benchmark=self.benchmark,
            split=self.split,
            imports=self.imports,
            opens=self.opens,
            informal_statement=self.informal_statement,
            flags=merged,
            provenance=self.provenance,
        )

    def to_theorem(self) -> Theorem:
        """The `lean.Theorem` the agent/verifier operate on."""
        return Theorem(
            name=self.name,
            statement=self.statement,
            imports=self.imports,
            opens=self.opens,
            source_file=self.provenance.get("source_file"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
