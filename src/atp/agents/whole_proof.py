"""Minimal whole-proof agent loop (Task 0.4).

The simplest agent on the whole-proof axis:

    propose a full proof  →  verify (Task 0.2)  →  if it fails, feed the Lean error back and
    *refine*  →  repeat until solved or the token budget is exhausted (Task 0.3).

Everything that touches a GPU or Lean is injected (`VLLMClient` over a transport, `Verifier` over a
`LeanBackend`), so the entire loop is driven deterministically in fast tests with scripted mocks and
needs no real model/Lean. State is checkpointed after every attempt (rule 0.3): a requeued job
reloads and continues — and a problem already solved short-circuits instead of redoing work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from atp.agents.components import ComponentPipeline, PromptContext, build_components
from atp.agents.state import (
    STOP_BUDGET,
    STOP_MAX_ROUNDS,
    STOP_NO_PROGRESS,
    STOP_SOLVED,
    AgentState,
    Attempt,
)
from atp.budget.meter import BudgetExhausted, BudgetMeter
from atp.models.templates import PromptTemplate, template_from_config

if TYPE_CHECKING:
    from atp.config import ExperimentConfig
    from atp.lean.backends import Theorem
    from atp.lean.verifier import Verifier
    from atp.models.client import VLLMClient


@dataclass
class WholeProofAgent:
    """Budget-bounded propose→verify→refine loop for one problem.

    `client` carries the per-problem `BudgetMeter`; when it's exhausted the loop stops cleanly.
    `max_refine` bounds the refinement chain within a round before drawing a fresh proposal;
    `max_rounds` is a safety cap so a generous budget can't spin forever (the budget is the real
    stopping criterion).
    """

    client: VLLMClient
    verifier: Verifier
    template: PromptTemplate
    max_refine: int = 4
    refine_enabled: bool = True
    max_rounds: int = 64
    sample_max_tokens: int = 2048
    # Composable Phase 1 components. The default empty pipeline is a no-op (every hook is the
    # identity) → byte-for-byte the minimal baseline.
    components: ComponentPipeline = field(default_factory=ComponentPipeline)

    @classmethod
    def from_config(
        cls,
        config: ExperimentConfig,
        client: VLLMClient,
        verifier: Verifier,
    ) -> WholeProofAgent:
        if config.agent.mode != "whole_proof":
            # Guard the generation-mode ablation: a 'bfs' cell must NOT silently run as whole-proof.
            raise NotImplementedError(
                f"agent.mode={config.agent.mode!r} has no agent yet; only 'whole_proof' is "
                "implemented (BFS tactic search is deferred — needs the REPL stepping layer)"
            )
        ref = config.agent.refinement
        return cls(
            client=client,
            verifier=verifier,
            template=template_from_config(config),
            max_refine=ref.max_iters,
            refine_enabled=ref.enabled,
            sample_max_tokens=config.model.max_model_len // 2,
            components=build_components(config),
        )

    def prove(self, theorem: Theorem, state_path: str | Path | None = None) -> AgentState:
        """Run the loop for `theorem`, checkpointing to `state_path` after each attempt.

        If `state_path` already holds a finished checkpoint, returns it without any new generation
        (resume = don't redo solved/finished work). Otherwise restores the budget meter from the
        checkpoint and continues.
        """
        state = self._resume(theorem, state_path)
        if state.done:
            return state

        try:
            self._search(theorem, state, state_path)
        except BudgetExhausted:
            self._finish(state, STOP_BUDGET, state_path)
        return state

    def extend(
        self, theorem: Theorem, state_path: str | Path, new_limit: int
    ) -> AgentState:
        """Resume a budget-exhausted checkpoint with a *raised* per-problem limit (Phase 5).

        The reclaim-and-reinvest mechanism: keep the logged trajectory's first `old_limit` tokens
        **verbatim** (we never regenerate them) and sample only `(old_limit, new_limit]`, so the
        result realizes `Solves_reinvest ⊇ Solves_uniform` by construction — an already-solved cell
        short-circuits unchanged; an unsolved cell can only *gain* extension attempts. This
        is why extension must resume, not re-run from scratch: vLLM is not bitwise-deterministic
        across runs, so a fresh run would not reproduce the logged prefix (DECISIONS.md 2026-06-21).

        Requires an existing checkpoint at `state_path`; `new_limit` must exceed the checkpoint's
        limit. A solved or already-`new_limit`-exhausted checkpoint is returned unchanged.
        """
        state = AgentState.load(state_path)
        if state is None:
            raise FileNotFoundError(f"no checkpoint to extend at {state_path}")
        if not state.budget:
            raise ValueError(f"checkpoint at {state_path} has no budget snapshot to extend")

        meter = BudgetMeter.restore(state.budget)
        if new_limit < meter.limit:
            raise ValueError(
                f"extension budget {new_limit} < checkpoint limit {meter.limit}"
            )
        meter.limit = new_limit          # raise the cap; `spent` (the logged prefix) is preserved
        self.client.meter = meter

        if state.solved or meter.exhausted:
            return state                 # kept as-is: a solved cell, or nothing left to spend

        # Re-enter the search from the checkpoint: clear the terminal flags so the loop runs, and
        # continue spending from the carried `spent` toward `new_limit`. New attempts append to the
        # preserved trajectory; the prefix is never touched.
        state.done = False
        state.stop_reason = None
        try:
            self._search(theorem, state, state_path)
        except BudgetExhausted:
            self._finish(state, STOP_BUDGET, state_path)
        return state

    # -- internals ---------------------------------------------------------------------
    def _resume(self, theorem: Theorem, state_path: str | Path | None) -> AgentState:
        existing = AgentState.load(state_path) if state_path is not None else None
        if existing is not None:
            # Resume the budget exactly where the killed job left off (rule 0.3).
            if existing.budget:
                self.client.meter = BudgetMeter.restore(existing.budget)
            return existing
        return AgentState(theorem_name=theorem.name)

    def _search(
        self, theorem: Theorem, state: AgentState, state_path: str | Path | None
    ) -> None:
        for round_index in range(self.max_rounds):
            # Fresh proposal opens a round.
            prompt = self.template.render(theorem)
            prompt = self.components.decorate_prompt(
                prompt,
                PromptContext(
                    theorem=theorem,
                    kind="propose",
                    round_index=round_index,
                    history=tuple(state.attempts),
                ),
            )
            if self._step(theorem, state, prompt, kind="propose", path=state_path) != "failed":
                return

            # Refine off the last error until solved or the round's refine budget is used.
            if self.refine_enabled:
                for _ in range(self.max_refine):
                    last = state.attempts[-1]
                    # Enrich the Lean error with the reviewer's critique (if any) for refinement.
                    feedback = last.feedback
                    if last.review_critique:
                        feedback = f"{feedback}\n\nReviewer critique: {last.review_critique}"
                    prompt = self.template.render_refinement(theorem, last.proof, feedback)
                    prompt = self.components.decorate_prompt(
                        prompt,
                        PromptContext(
                            theorem=theorem,
                            kind="refine",
                            round_index=round_index,
                            history=tuple(state.attempts),
                        ),
                    )
                    status = self._step(theorem, state, prompt, kind="refine", path=state_path)
                    if status != "failed":
                        return
        self._finish(state, STOP_MAX_ROUNDS, state_path)

    def _step(
        self,
        theorem: Theorem,
        state: AgentState,
        prompt: str,
        *,
        kind: str,
        path: str | Path | None,
    ) -> str:
        """One generate+verify+checkpoint.

        Returns "solved" | "no_progress" | "budget" | "failed". `client.generate` may raise
        `BudgetExhausted` (handled by `prove`) — the normal budget-out path before work is wasted.
        """
        completion = self.client.generate(
            prompt, max_tokens=self.sample_max_tokens, label=kind
        )
        proof = self.template.extract_proof(theorem, completion.text)
        result = self.verifier.verify(theorem, proof)

        # Reviewer (Phase 1): consult the critic ONLY on a real proof Lean just rejected, so Lean
        # stays the authoritative gate and a solve is never blocked. The critic spends budget, so it
        # can exhaust mid-step; we still record the (failed) attempt, then stop cleanly.
        review_accept: bool | None = None
        review_critique = ""
        budget_out = False
        if (not result.ok) and completion.completion_tokens > 0:
            try:
                verdict = self.components.review(theorem, proof, result.feedback, self.client)
            except BudgetExhausted:
                budget_out = True
            else:
                if verdict is not None:
                    review_accept = verdict.accept
                    review_critique = verdict.critique

        # Persist the raw verifier output ONLY when the verdict looks like an infra glitch (rejected
        # with no parseable Lean error) — that's the case worth debugging; a normal compile error is
        # already in `feedback`. Keeps state files small.
        raw_dbg = ""
        if (not result.ok) and result.earliest_error is None and result.reason != "loophole":
            raw_dbg = (result.raw_output or "")[:4000]
        state.attempts.append(
            Attempt(
                index=state.n_attempts,
                kind=kind,
                proof=proof,
                ok=result.ok,
                reason=result.reason,
                feedback=result.feedback,
                completion_tokens=completion.completion_tokens,
                raw_output=raw_dbg,
                review_accept=review_accept,
                review_critique=review_critique,
            )
        )
        if self.client.meter is not None:
            state.budget = self.client.meter.snapshot()

        if result.ok:
            state.proof = proof
            self._finish(state, STOP_SOLVED, path)
            return "solved"

        # A zero-token generation means the server can't make progress under the clamp -> stop.
        if completion.completion_tokens == 0:
            self._finish(state, STOP_NO_PROGRESS, path)
            return "no_progress"

        # The reviewer used the last of the budget — record done, like the generate() budget path.
        if budget_out:
            self._finish(state, STOP_BUDGET, path)
            return "budget"

        self._checkpoint(state, path)
        return "failed"

    def _finish(self, state: AgentState, reason: str, path: str | Path | None) -> None:
        state.done = True
        state.stop_reason = reason
        self._checkpoint(state, path)

    @staticmethod
    def _checkpoint(state: AgentState, path: str | Path | None) -> None:
        if path is not None:
            state.save(path)
