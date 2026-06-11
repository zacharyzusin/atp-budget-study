"""Tactic-skeleton structural prior (Phase 1 ablation axis: inference-time structural priors).

A cheap, *fixed* (non-learned) inference-time prior: on each fresh whole-proof proposal, append a
one-line hint naming a common Lean tactic skeleton to bias the draft, cycling through a schedule
across successive samples so the budget explores a spread of standard structures/closers instead of
re-drawing near-duplicate proofs. Refinement prompts are left untouched — the Lean error already
steers those, and layering a generic skeleton hint on top would only dilute that concrete signal.

The plan flags the published claim that such skeletons give *large relative gains at equal
samples*; Phase 1 measures whether that holds for Goedel-Prover-V2-8B on our fixed-budget axis
(verify/refute).

Schedules are hard-coded here (no learning, no data dependency) so any change is an explicit,
logged edit — the schedule name is recorded in the run manifest via the config.
"""

from __future__ import annotations

from dataclasses import dataclass

from atp.agents.components.base import Component, PromptContext
from atp.config import SkeletonsCfg

# Each entry is a one-line structural hint appended to a *fresh* proposal prompt. Ordered roughly by
# how often each pattern closes competition-style (miniF2F/ProofNet) goals; the agent cycles through
# them across successive samples (round_index % len). Wording is deliberately suggestive, not
# prescriptive — it nudges the prover toward a structure without overriding its own plan.
_DEFAULT_SCHEDULE: tuple[str, ...] = (
    "Try to close the goal directly with one strong tactic after introducing hypotheses: "
    "`nlinarith`, `norm_num`, `linarith`, or `polyrith`.",
    "Simplify first (`simp`, `simp_all`, or `norm_num [...]`), then finish with "
    "`nlinarith`/`linarith`.",
    "If the goal is arithmetic over ℕ/ℤ, try `omega`; if it is a pure ring identity, try `ring` "
    "or `ring_nf`.",
    "Break the goal apart with `constructor`/`rcases`/`obtain`, then discharge each resulting goal "
    "separately.",
    "For divisibility or modular goals, try `decide`, `omega`, or rewriting with "
    "`Nat.dvd_iff_mod_eq_zero` before `norm_num`.",
    "For goals with division use `field_simp` then `ring`; for positivity goals use `positivity`.",
    "Try induction on the key variable (`induction`/`Nat.rec`), then close each case with "
    "`simp`/`omega`.",
    "Combine steps: `intro ...`, `simp_all`, then `nlinarith [sq_nonneg _, mul_self_nonneg _]` "
    "with helpful auxiliary square terms.",
)

# Registry of named schedules. `build_components` rejects an unknown name (config-validation).
_SCHEDULES: dict[str, tuple[str, ...]] = {
    "default": _DEFAULT_SCHEDULE,
}

_HINT_PREFIX = "Hint (one promising proof strategy to try): "


def available_schedules() -> tuple[str, ...]:
    return tuple(sorted(_SCHEDULES))


@dataclass(frozen=True)
class TacticSkeletons(Component):
    """Cycle a fixed schedule of tactic-skeleton hints into fresh proposal prompts."""

    schedule: tuple[str, ...]
    name: str = "tactic_skeletons"

    @classmethod
    def from_config(cls, cfg: SkeletonsCfg) -> TacticSkeletons:
        try:
            schedule = _SCHEDULES[cfg.schedule]
        except KeyError:
            raise ValueError(
                f"unknown tactic_skeletons schedule {cfg.schedule!r}; "
                f"expected one of {list(available_schedules())}"
            ) from None
        return cls(schedule=schedule)

    def decorate_prompt(self, prompt: str, ctx: PromptContext) -> str:
        # Skeletons bias *fresh* drafts only; refinements keep the concrete Lean-error signal clean.
        if ctx.kind != "propose":
            return prompt
        hint = self.schedule[ctx.round_index % len(self.schedule)]
        return f"{prompt}\n\n{_HINT_PREFIX}{hint}"
