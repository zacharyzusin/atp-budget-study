"""Composable agent components — framework (Phase 1, Task 1.1).

Each Phase 1 ablation axis (tactic-skeletons, memory, reviewer, premise retrieval) is an
independent, *composable* component toggled from YAML (`config.agent.components`). A component
participates in the agent loop through optional hooks; **every hook defaults to a no-op**, so an
agent with no components enabled behaves byte-for-byte like the minimal Phase 0 baseline — that
identity is what keeps the Phase 0 `pass@B` curve a valid reference to measure each axis against.

Components are pure Python and login-node testable: none of them touches a GPU or Lean directly
(model/Lean effects stay in the agent loop, which calls these hooks).

Hooks are added only as the component that needs them lands (no speculative interfaces). Defined so
far:
  * `decorate_prompt` — rewrite the proposer/refiner prompt before it is sent to the model
    (tactic-skeletons uses it now; memory/retrieval will reuse it).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atp.agents.state import Attempt
    from atp.lean.backends import Theorem
    from atp.models.client import VLLMClient


@dataclass(frozen=True)
class PromptContext:
    """Everything a component needs to decide how to decorate a prompt.

    `kind` is "propose" (a fresh whole-proof draft) or "refine" (a correction off a Lean error).
    `round_index` counts fresh-proposal rounds from 0, so a component can advance through a fixed
    schedule across successive samples. `history` is the read-only list of attempts already made on
    this problem (empty on the very first call) — the memory component summarises its failures.
    """

    theorem: Theorem
    kind: str
    round_index: int
    history: tuple[Attempt, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ReviewVerdict:
    """A critic's verdict on a candidate proof: accept/reject + a short critique to guide a fix."""

    accept: bool
    critique: str = ""


class Component:
    """Base class for a composable agent component. Every hook defaults to a no-op."""

    name: str = "component"

    def decorate_prompt(self, prompt: str, ctx: PromptContext) -> str:  # noqa: ARG002
        return prompt

    def review(
        self,
        theorem: Theorem,  # noqa: ARG002
        proof: str,  # noqa: ARG002
        feedback: str,  # noqa: ARG002
        client: VLLMClient,  # noqa: ARG002
    ) -> ReviewVerdict | None:
        """Critic hook: judge a candidate proof via `client` (spends budget); None = no opinion."""
        return None


@dataclass(frozen=True)
class ComponentPipeline:
    """An ordered collection of enabled components.

    An empty pipeline is the minimal baseline: every hook is the identity, so the agent's prompts
    (and therefore its behaviour) are unchanged. With components present, each hook is applied in
    pipeline order, threading the result through (so two prompt-decorators compose left-to-right).
    """

    components: tuple[Component, ...] = ()

    def decorate_prompt(self, prompt: str, ctx: PromptContext) -> str:
        for component in self.components:
            prompt = component.decorate_prompt(prompt, ctx)
        return prompt

    def review(
        self, theorem: Theorem, proof: str, feedback: str, client: VLLMClient
    ) -> ReviewVerdict | None:
        """First component with an opinion wins (only the reviewer overrides this hook today)."""
        for component in self.components:
            verdict = component.review(theorem, proof, feedback, client)
            if verdict is not None:
                return verdict
        return None

    def __bool__(self) -> bool:
        return bool(self.components)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.components)
