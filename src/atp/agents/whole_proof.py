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

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from atp.agents.state import (
    STOP_BUDGET,
    STOP_MAX_ROUNDS,
    STOP_NO_PROGRESS,
    STOP_SOLVED,
    AgentState,
    Attempt,
)
from atp.budget.meter import BudgetExhausted, BudgetMeter
from atp.models.templates import WholeProofTemplate

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
    template: WholeProofTemplate
    max_refine: int = 4
    refine_enabled: bool = True
    max_rounds: int = 64
    sample_max_tokens: int = 2048

    @classmethod
    def from_config(
        cls,
        config: ExperimentConfig,
        client: VLLMClient,
        verifier: Verifier,
    ) -> WholeProofAgent:
        ref = config.agent.refinement
        return cls(
            client=client,
            verifier=verifier,
            template=WholeProofTemplate(),
            max_refine=ref.max_iters,
            refine_enabled=ref.enabled,
            sample_max_tokens=config.model.max_model_len // 2,
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
        for _ in range(self.max_rounds):
            # Fresh proposal opens a round.
            prompt = self.template.render(theorem)
            if self._step(theorem, state, prompt, kind="propose", path=state_path) != "failed":
                return

            # Refine off the last error until solved or the round's refine budget is used.
            if self.refine_enabled:
                for _ in range(self.max_refine):
                    last = state.attempts[-1]
                    prompt = self.template.render_refinement(theorem, last.proof, last.feedback)
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

        Returns "solved" | "no_progress" | "failed". `client.generate` may raise `BudgetExhausted`
        (handled by `prove`), which is the normal budget-out path before any work is wasted.
        """
        completion = self.client.generate(
            prompt, max_tokens=self.sample_max_tokens, label=kind
        )
        proof = self.template.extract_proof(theorem, completion.text)
        result = self.verifier.verify(theorem, proof)

        state.attempts.append(
            Attempt(
                index=state.n_attempts,
                kind=kind,
                proof=proof,
                ok=result.ok,
                reason=result.reason,
                feedback=result.feedback,
                completion_tokens=completion.completion_tokens,
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
