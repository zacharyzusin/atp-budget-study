"""Approach-conditioned diversity injection (Phase 2 Step C).

MECHANISM.md F1 located the saturation of pass@B at the *approach* level: on a hard problem the
model
commits to ~2 distinct opening tactics and resamples variants of them, so extra budget buys
near-duplicates. F5 (the late-solve pre-flight) shows late solves never come from a newly-explored
approach — predicting that *forcing* new approaches will raise diversity but NOT solve rate, because
the bottleneck is within-approach execution (the F2/F3 reasoning floor), not approach discovery.

This component is the decisive *interventional* test of that prediction. On each FRESH proposal it
reads the attempts already made on this problem, lists the distinct opening tactics they used, and
instructs the model to take a fundamentally different approach. Refinement prompts are untouched —
an
approach is chosen at propose time; refinement is execution *within* an approach (and the Lean error
already steers it). The first proposal (empty history) is a no-op.

Targeting the opening/approach level (not raw token-temperature) is deliberate: temperature raises
token entropy but tends to produce noisier versions of the *same* approach, and at high temperature
revives the truncated/malformed generations that the verifier-soundness fix guards against. Pure
Python, login-node testable; no GPU/Lean.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from atp.agents.components.base import Component, PromptContext

if TYPE_CHECKING:
    from atp.agents.state import Attempt
    from atp.config import DiversityCfg

# Leading identifier of the first tactic in a proof body — the same heuristic the analysis
# (scripts/analyze_mechanism.py) uses to define an "approach", kept self-contained so src/ has no
# dependency on scripts/.
_ID = re.compile(r"[A-Za-z_][A-Za-z0-9_'.]*")
_DIVERSITY_PREFIX = "Previously attempted approaches on this problem opened with: "


def _opening_tactic(proof: str) -> str | None:
    if not proof:
        return None
    m = re.search(r":=\s*by\b", proof) or re.search(r":=", proof)
    body = proof[m.end():] if m else proof
    for raw in re.split(r"[\n;]", body):
        s = raw.strip().lstrip("·•-{}⟨ ").strip()
        if not s or s.startswith("--"):
            continue
        tok = _ID.match(s)
        if tok:
            return tok.group(0)
    return None


def _distinct_openings(history: tuple[Attempt, ...]) -> list[str]:
    """Distinct opening tactics tried so far, in first-seen order."""
    seen: list[str] = []
    for a in history:
        t = _opening_tactic(getattr(a, "proof", "") or "")
        if t and t not in seen:
            seen.append(t)
    return seen


@dataclass(frozen=True)
class DiversityInjection(Component):
    """Condition each fresh proposal away from the opening tactics already tried on this problem."""

    max_listed: int = 6
    name: str = "diversity_injection"

    @classmethod
    def from_config(cls, cfg: DiversityCfg) -> DiversityInjection:
        return cls(max_listed=cfg.max_listed)

    def decorate_prompt(self, prompt: str, ctx: PromptContext) -> str:
        # Inject only on fresh proposals; the first one has nothing to diverge from.
        if ctx.kind != "propose":
            return prompt
        tried = _distinct_openings(ctx.history)
        if not tried:
            return prompt
        listed = ", ".join(f"`{t}`" for t in tried[: self.max_listed])
        return (
            f"{prompt}\n\n{_DIVERSITY_PREFIX}{listed}. Do NOT reuse any of these opening tactics or "
            "their overall strategy. Begin with a different opening tactic and pursue a fundamentally "
            "different proof approach."
        )
