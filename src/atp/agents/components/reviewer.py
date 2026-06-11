"""Reviewer / critic component (Phase 1 ablation axis).

Semantics (pinned 2026-06-10; see DECISIONS.md):

  * The reviewer is an LLM critic consulted **only on a candidate proof that Lean has just
    REJECTED** — Lean stays the free, authoritative gate, so a real solve is never blocked, delayed,
    or thrown away by the critic, and the reviewer's token cost is only paid on failures (where the
    agent is about to refine anyway).
  * It returns ACCEPT/REJECT + a short critique. Because it is run only on Lean-failed proofs, every
    ACCEPT here is by definition a **false accept** — that is exactly the plan's "how often does the
    critic wave a bad proof through" diagnostic. The agent records the verdict; the eval layer
    aggregates `reviewer_false_accept_rate = accepts / reviewed` over those failed attempts.
  * The critique is fed into the next refinement prompt (its behavioural value): a second opinion on
    *why* the proof is wrong, on top of the raw Lean error.

So the ablation answer is honest on both axes: does the critic's critique improve `pass@B` enough to
pay for its token cost, and how reliable would the critic be as a standalone acceptance gate.

Pure component: the model call is made through the injected `VLLMClient` (budget-metered), so fast
tests drive it with a scripted transport — no GPU.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from atp.agents.components.base import Component, ReviewVerdict
from atp.config import ReviewerCfg

if TYPE_CHECKING:
    from atp.lean.backends import Theorem
    from atp.models.client import VLLMClient

_CRITIC_INSTRUCTION = (
    "You are a strict Lean 4 proof reviewer. Given a theorem and a candidate proof, decide whether "
    "the proof is correct and complete (compiles, no `sorry`/`admit`, actually proves the goal). "
    "Respond on the first line with exactly ACCEPT or REJECT, then one or two sentences explaining "
    "the key flaw (if any) to guide a fix."
)


def _parse_verdict(text: str) -> ReviewVerdict:
    """ACCEPT only on an explicit accept token; anything ambiguous is a (conservative) REJECT."""
    stripped = text.strip()
    upper = stripped.upper()
    # Decide on the first explicit token seen, so "REJECT: it ... accept ..." isn't misread.
    accept = False
    for token in ("ACCEPT", "REJECT"):
        idx = upper.find(token)
        if idx != -1:
            accept = token == "ACCEPT" and (
                "REJECT" not in upper or upper.find("REJECT") > idx
            )
            break
    return ReviewVerdict(accept=accept, critique=stripped)


@dataclass(frozen=True)
class Reviewer(Component):
    """LLM critic consulted on Lean-rejected candidates; scores false-accepts, guides refinement."""

    max_tokens: int
    name: str = "reviewer"

    @classmethod
    def from_config(cls, cfg: ReviewerCfg) -> Reviewer:
        return cls(max_tokens=cfg.max_tokens)

    def _prompt(self, theorem: Theorem, proof: str, feedback: str) -> str:
        return (
            f"{_CRITIC_INSTRUCTION}\n\n"
            f"Theorem:\n```lean4\n{theorem.statement.rstrip()}\n```\n\n"
            f"Candidate proof:\n```lean4\n{proof.strip()}\n```\n\n"
            f"Lean reported:\n{feedback.strip()}\n\nVerdict:"
        )

    def review(
        self, theorem: Theorem, proof: str, feedback: str, client: VLLMClient
    ) -> ReviewVerdict | None:
        completion = client.generate(
            self._prompt(theorem, proof, feedback), max_tokens=self.max_tokens, label="review"
        )
        return _parse_verdict(completion.text)
