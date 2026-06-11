"""Memory component (Phase 1 ablation axis): carry past failures into fresh proposals.

Within one problem's search, each fresh whole-proof proposal is otherwise drawn cold — the model
can't see that earlier rounds already tried (and failed) a given approach, so budget is wasted
re-drawing near-duplicate dead ends. The memory component summarises the most-recent failed attempts
(a short proof sketch + the Lean error) into the fresh-proposal prompt as an explicit "don't repeat
these" block, nudging the next draft toward an unexplored approach.

Like tactic-skeletons it decorates **fresh proposals only** — refinement prompts already carry the
immediate Lean error, and piling older failures on top would dilute that concrete signal. Pure
prompt-side: no GPU/Lean, and deliberately **no cross-problem state** (global solved-lemma memory
across problems is a separate, larger design). Read-only over `ctx.history`.
"""

from __future__ import annotations

from dataclasses import dataclass

from atp.agents.components.base import Component, PromptContext
from atp.config import MemoryCfg

_MEMORY_PREFIX = (
    "Earlier attempts on this theorem already FAILED — do not repeat these approaches; try a "
    "different strategy:"
)

# Per-item proof snippet cap, so a long failed proof can't blow up the next prompt's token cost.
_PROOF_SNIPPET_CHARS = 240


def _summarise(attempt) -> str:  # noqa: ANN001 (Attempt; kept loose to avoid an import cycle)
    proof = " ".join(attempt.proof.split())  # collapse whitespace for a compact one-liner
    if len(proof) > _PROOF_SNIPPET_CHARS:
        proof = proof[:_PROOF_SNIPPET_CHARS] + " …"
    error = " ".join((attempt.feedback or "").split()) or "(no error message)"
    return f"- tried `{proof}` → {error}"


@dataclass(frozen=True)
class Memory(Component):
    """Inject a bounded summary of recent failed attempts into fresh proposals."""

    max_items: int
    name: str = "memory"

    @classmethod
    def from_config(cls, cfg: MemoryCfg) -> Memory:
        return cls(max_items=cfg.max_items)

    def decorate_prompt(self, prompt: str, ctx: PromptContext) -> str:
        if ctx.kind != "propose":
            return prompt
        failures = [a for a in ctx.history if not a.ok]
        if not failures:
            return prompt  # round 0 (no history yet) is a no-op → baseline-identical
        recent = failures[-self.max_items :]
        block = "\n".join(_summarise(a) for a in recent)
        return f"{prompt}\n\n{_MEMORY_PREFIX}\n{block}"
