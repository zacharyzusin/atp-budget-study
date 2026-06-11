"""atp.agents.components — composable Phase 1 ablation components.

`build_components(config)` assembles the enabled components (per `config.agent.components`) into a
`ComponentPipeline` the agent threads its prompts through. With nothing enabled the pipeline is
empty (all hooks no-op) → the agent is byte-for-byte the Phase 0 baseline.

Components land one axis at a time (Task 1.3). Currently implemented: tactic-skeletons.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from atp.agents.components.base import (
    Component,
    ComponentPipeline,
    PromptContext,
    ReviewVerdict,
)
from atp.agents.components.memory import Memory
from atp.agents.components.retrieval import Retrieval
from atp.agents.components.reviewer import Reviewer
from atp.agents.components.skeletons import TacticSkeletons

if TYPE_CHECKING:
    from atp.config import ExperimentConfig

__all__ = [
    "Component",
    "ComponentPipeline",
    "Memory",
    "PromptContext",
    "ReviewVerdict",
    "Retrieval",
    "Reviewer",
    "TacticSkeletons",
    "build_components",
]


def build_components(config: ExperimentConfig) -> ComponentPipeline:
    """Construct the enabled components from config, in a fixed pipeline order.

    Order is fixed (not config-driven) so a given set of toggles always yields the same pipeline —
    important for reproducibility and for the config-hash to mean one thing. Unknown sub-options
    (e.g. an unrecognised skeleton schedule) raise here, before any GPU/Lean work begins.
    """
    cc = config.agent.components
    components: list[Component] = []

    # Fixed prompt-side order, outer context first: retrieval (library lemmas) → memory (what
    # already failed) → skeletons (a strategy hint). Then the accept-side reviewer (separate
    # `review` hook, runs after Lean rejects a candidate).
    if cc.retrieval.enabled:
        components.append(Retrieval.from_config(cc.retrieval))
    if cc.memory.enabled:
        components.append(Memory.from_config(cc.memory))
    if cc.tactic_skeletons.enabled:
        components.append(TacticSkeletons.from_config(cc.tactic_skeletons))
    if cc.reviewer.enabled:
        components.append(Reviewer.from_config(cc.reviewer))

    return ComponentPipeline(tuple(components))
