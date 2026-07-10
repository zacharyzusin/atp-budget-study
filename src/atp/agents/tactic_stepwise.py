"""Phase 7 Track 1 — Mode 4: true stepwise generation (one tactic per call).

Mode 3 (re-grounding) re-grounds the model on its true verified state but then lets it free-run a
WHOLE continuation from there — which can drift again before it reaches a real closing tactic. That
confound means "Mode 3 engages but doesn't close" cannot distinguish exposure bias (the bottleneck,
just not fixed strongly enough) from a genuine capability ceiling (the model cannot close these
proofs even with help). Mode 4 removes the confound: the model proposes exactly ONE tactic at a
time, conditioned on the TRUE current goal state (via `ReplBackend.elaborate`, never a drifted
self-generated state), and every tactic is validated before being committed. If the model can close
proofs THIS way that Mode 3 couldn't, exposure bias was the bottleneck and single-shot re-grounding
was simply too weak. If it still can't, the capability-floor reading is airtight.
"""

from __future__ import annotations

from collections.abc import Callable
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
from atp.models.templates import candidate_tactic_lines

if TYPE_CHECKING:
    from atp.lean.backends import Theorem
    from atp.lean.verifier import Verifier
    from atp.models.client import VLLMClient
    from atp.models.templates import TacticTemplate


@dataclass(frozen=True)
class StepCheck:
    """The verdict on ONE candidate tactic, from `ReplBackend.elaborate`."""

    ok: bool  # the tactic elaborates cleanly (a legal step, whether or not it closes the goal)
    closed: bool  # AND leaves zero remaining sorries (the whole proof may now be complete)
    state: str = ""  # the next open goal's text (sorries[0]) when ok and not closed


def take_tactic_step(
    propose: Callable[[str], list[str]],
    check: Callable[[str], StepCheck],
    state: str,
    retries: int,
) -> tuple[str | None, StepCheck | None]:
    """Try up to `retries` completions against the TRUE current state; each completion may yield
    SEVERAL candidate tactic lines (a reasoning model's "next tactic" is sometimes a multi-step
    sketch, not one atomic line — see `atp.models.templates.candidate_tactic_lines`), oracle-checked
    in order via `check` until one is accepted. Returns (None, None) if every candidate across every
    retry was rejected — the search is stuck at this goal, not a hallucinated one, because `state`
    never drifts: only an ACCEPTED tactic ever advances it (the caller re-derives `state` from
    `check`'s own verdict)."""
    for _ in range(retries):
        for tactic in propose(state):
            if not tactic:
                continue
            result = check(tactic)
            if result.ok:
                return tactic, result
    return None, None


def expand_node(
    propose: Callable[[str], list[str]],
    check: Callable[[str], StepCheck],
    state: str,
    beam_width: int,
    retries: int,
) -> list[tuple[str, StepCheck]]:
    """Sample up to `retries` completions against the TRUE current state, oracle-check every
    candidate tactic line each yields (a completion can yield several — see `take_tactic_step`),
    and collect up to `beam_width` DISTINCT accepted (tactic, StepCheck) pairs — this node's
    expansion in a best-first-with-backtracking search (unlike `take_tactic_step`, which commits to
    the FIRST acceptable candidate and never revisits this node). `check` is expected to reject a
    candidate that doesn't change the state from `state` (a no-op/stagnation rejection is the
    caller's job, not this function's — see `TacticStepwiseAgent._check`'s stagnation guard), so a
    real Lean-accepted but non-progressing tactic (e.g. `rw [mul_comm]` applied over and over)
    never counts as an expansion — this is what makes a bounded beam safe against infinite loops.
    """
    accepted: list[tuple[str, StepCheck]] = []
    seen: set[str] = set()
    for _ in range(retries):
        for tactic in propose(state):
            if not tactic or tactic in seen:
                continue
            seen.add(tactic)
            result = check(tactic)
            if result.ok:
                accepted.append((tactic, result))
                if len(accepted) >= beam_width:
                    return accepted
    return accepted


@dataclass
class TacticStepwiseAgent:
    """Mode 4, wired to the real client/verifier/Lean elaborate — a drop-in `.prove()` counterpart
    to `WholeProofAgent`/`RegroundStepwiseAgent` (same `AgentState` checkpoint format).

    `prefix`/`prev_tactics` (the accumulated proof-so-far) ride in `state.budget`'s extra keys, same
    additive-checkpoint pattern `RegroundStepwiseAgent` uses (`BudgetMeter.restore` ignores extras).
    """

    client: VLLMClient
    verifier: Verifier
    template: TacticTemplate
    # (theorem, full source w/ trailing `sorry`) -> raw ReplBackend.elaborate() dict, i.e.
    # {"errors": int, "sorries": [goal_text, ...], "infra_error": bool}. Pass ReplBackend.elaborate
    # directly (bound method) in real wiring.
    elaborate: Callable[[Theorem, str], dict]
    max_steps: int = 40
    retries_per_step: int = 4
    sample_max_tokens: int = 64

    def prove(self, theorem: Theorem, state_path: str | Path | None = None) -> AgentState:
        state = self._resume(theorem, state_path)
        if state.done:
            return state
        prefix = str(state.budget.get("_tactic_prefix", "")) if state.budget else ""
        prev_tactics: list[str] = (
            list(state.budget.get("_tactic_prev", [])) if state.budget else []
        )
        step = int(state.budget.get("_tactic_step", 0)) if state.budget else 0

        try:
            check0 = self._check(theorem, prefix)
            if check0.closed:
                return self._solve(theorem, state, prefix, prev_tactics, step, state_path)
            goal_state = check0.state

            for _ in range(step, self.max_steps):
                tactic, result = take_tactic_step(
                    propose=lambda s: self._propose(theorem, prev_tactics, s),
                    check=lambda t, p=prefix: self._check(theorem, p, t),
                    state=goal_state,
                    retries=self.retries_per_step,
                )
                if tactic is None:
                    self._finish(state, STOP_NO_PROGRESS, state_path, prefix, prev_tactics, step)
                    return state

                prefix = f"{prefix}\n  {tactic}" if prefix else f"  {tactic}"
                prev_tactics.append(tactic)
                step += 1
                state.attempts.append(
                    Attempt(
                        index=state.n_attempts, kind="tactic", proof=prefix, ok=True,
                        reason="ok", feedback="", completion_tokens=0,
                    )
                )
                self._checkpoint(state, prefix, prev_tactics, step, state_path)

                if result.closed:
                    return self._solve(theorem, state, prefix, prev_tactics, step, state_path)
                goal_state = result.state
        except BudgetExhausted:
            self._finish(state, STOP_BUDGET, state_path, prefix, prev_tactics, step)
            return state

        self._finish(state, STOP_MAX_ROUNDS, state_path, prefix, prev_tactics, step)
        return state

    def _solve(self, theorem, state, prefix, prev_tactics, step, state_path):
        # An empty `prefix` closing (zero tactics needed) is not a real solve — let it fail
        # verification naturally rather than fabricate a tactic that was never proposed/checked.
        full_proof = f"{theorem.statement.rstrip()} := by\n{prefix}".rstrip()
        result = self.verifier.verify(theorem, full_proof)
        state.attempts.append(
            Attempt(
                index=state.n_attempts, kind="tactic_close", proof=full_proof, ok=result.ok,
                reason=result.reason, feedback=result.feedback, completion_tokens=0,
            )
        )
        if result.ok:
            state.proof = full_proof
            self._finish(state, STOP_SOLVED, state_path, prefix, prev_tactics, step)
        else:
            # Lean-clean (no remaining goals) but the soundness gate rejected it (e.g. a hidden
            # `sorry`/`admit`): nothing left to search from, so this cell is done, unsolved.
            self._finish(state, STOP_NO_PROGRESS, state_path, prefix, prev_tactics, step)
        return state

    def _propose(self, theorem: Theorem, prev_tactics: list[str], goal_state: str) -> list[str]:
        prompt = self.template.render(theorem, state=goal_state, prev_tactics=tuple(prev_tactics))
        completion = self.client.generate(prompt, max_tokens=self.sample_max_tokens, label="tactic")
        return candidate_tactic_lines(completion.text)

    def _check(self, theorem: Theorem, prefix: str, tactic: str | None = None) -> StepCheck:
        candidate = f"{prefix}\n  {tactic}" if tactic else prefix
        body = f"{candidate}\n  sorry" if candidate else "  sorry"
        src = f"{theorem.statement.rstrip()} := by\n{body}"
        resp = self.elaborate(theorem, src)
        if resp.get("infra_error") or resp["errors"] != 0:
            return StepCheck(ok=False, closed=False)
        sorries = resp["sorries"]
        if len(sorries) == 0:
            return StepCheck(ok=True, closed=True)
        return StepCheck(ok=True, closed=False, state=sorries[0])

    def _resume(self, theorem: Theorem, state_path: str | Path | None) -> AgentState:
        existing = AgentState.load(state_path) if state_path is not None else None
        if existing is not None:
            if existing.budget:
                self.client.meter = BudgetMeter.restore(existing.budget)
            return existing
        return AgentState(theorem_name=theorem.name)

    def _snapshot(self, prefix: str, prev_tactics: list[str], step: int) -> dict:
        meter = self.client.meter
        base = meter.snapshot() if meter is not None else {}
        return {**base, "_tactic_prefix": prefix, "_tactic_prev": list(prev_tactics),
                "_tactic_step": step}

    def _checkpoint(self, state: AgentState, prefix, prev_tactics, step, path) -> None:
        state.budget = self._snapshot(prefix, prev_tactics, step)
        if path is not None:
            state.save(path)

    def _finish(self, state: AgentState, reason: str, path, prefix, prev_tactics, step) -> None:
        state.done = True
        state.stop_reason = reason
        self._checkpoint(state, prefix, prev_tactics, step, path)


@dataclass
class BeamTacticStepwiseAgent:
    """Mode 4, best-first-with-backtracking version — the FAIR test for a tactic-native model built
    for search (e.g. BFS-Prover), not the weaker greedy `TacticStepwiseAgent`.

    Two confounds a single greedy walk has, found live 2026-07-05 on BFS-Prover-V1-7B's first real
    run: (1) a real Lean-accepted but non-progressing tactic (e.g. `rw [mul_comm]`, which cycles
    `a*b`/`b*a` forever) can be re-accepted every step, burning the ENTIRE step budget in a stall
    that looks like "deep progress" but isn't (one cell hit max_steps=64 with the SAME tactic
    accepted all 64 times) — fixed by `_check`'s stagnation guard (reject a candidate whose
    resulting state doesn't change). (2) committing irreversibly to the first accepted candidate
    per step means one bad early choice dead-ends the whole cell with no recovery — the model's own
    designed usage is a BEAM of candidates per state with BACKTRACKING away from dead ends, which
    this class implements as an explicit DFS-with-backtracking over `expand_node` beams.

    The search's live state is an explicit stack of frames (root to current), each holding its own
    UNTRIED beam candidates — checkpointed whole (JSON-safe: tactics/states are strings) so a
    restart resumes the exact same search, not just a linear prefix.
    """

    client: VLLMClient
    verifier: Verifier
    template: TacticTemplate
    elaborate: Callable[[Theorem, str], dict]
    max_steps: int = 40  # node EXPANSIONS (each may push a child or backtrack), not linear depth
    beam_width: int = 3
    retries_per_step: int = 4
    sample_max_tokens: int = 64

    def prove(self, theorem: Theorem, state_path: str | Path | None = None) -> AgentState:
        state = self._resume(theorem, state_path)
        if state.done:
            return state
        stack = self._resume_stack(state)
        if not stack:
            check0 = self._check(theorem, "", "", None)
            if check0.closed:
                return self._solve(theorem, state, "", [], 0, state_path)
            stack = [{"prefix": "", "state": check0.state, "prev_tactics": [], "pending": None}]

        expansions = int(state.budget.get("_search_expansions", 0)) if state.budget else 0
        try:
            while stack and expansions < self.max_steps:
                frame = stack[-1]
                if frame["pending"] is None:
                    accepted = expand_node(
                        propose=lambda s, pt=tuple(frame["prev_tactics"]): self._propose(
                            theorem, list(pt), s
                        ),
                        check=lambda t, p=frame["prefix"], s=frame["state"]: self._check(
                            theorem, p, s, t
                        ),
                        state=frame["state"], beam_width=self.beam_width,
                        retries=self.retries_per_step,
                    )
                    frame["pending"] = [
                        {"tactic": t, "closed": r.closed, "state": r.state} for t, r in accepted
                    ]
                    expansions += 1
                    self._checkpoint_stack(state, stack, expansions, state_path)

                if not frame["pending"]:
                    stack.pop()  # dead end — backtrack to the parent's remaining alternatives
                    self._checkpoint_stack(state, stack, expansions, state_path)
                    continue

                cand = frame["pending"].pop(0)
                tactic = cand["tactic"]
                new_prefix = f"{frame['prefix']}\n  {tactic}" if frame["prefix"] else f"  {tactic}"
                new_prev = [*frame["prev_tactics"], tactic]
                state.attempts.append(
                    Attempt(
                        index=state.n_attempts, kind="tactic", proof=new_prefix, ok=True,
                        reason="ok", feedback="", completion_tokens=0,
                    )
                )
                if cand["closed"]:
                    solved = self._solve(theorem, state, new_prefix, new_prev, expansions, None)
                    if solved.solved:
                        if state_path is not None:
                            solved.save(state_path)
                        return solved
                    # closed-but-unsound (soundness gate rejected it) — a dead branch, but the
                    # PARENT frame still has other pending candidates to try; don't push a child.
                    self._checkpoint_stack(state, stack, expansions, state_path)
                    continue

                stack.append({
                    "prefix": new_prefix, "state": cand["state"], "prev_tactics": new_prev,
                    "pending": None,
                })
                self._checkpoint_stack(state, stack, expansions, state_path)
        except BudgetExhausted:
            self._finish_search(state, STOP_BUDGET, stack, expansions, state_path)
            return state

        reason = STOP_NO_PROGRESS if not stack else STOP_MAX_ROUNDS
        self._finish_search(state, reason, stack, expansions, state_path)
        return state

    def _solve(self, theorem, state, prefix, prev_tactics, expansions, state_path) -> AgentState:
        full_proof = f"{theorem.statement.rstrip()} := by\n{prefix}".rstrip()
        result = self.verifier.verify(theorem, full_proof)
        state.attempts.append(
            Attempt(
                index=state.n_attempts, kind="tactic_close", proof=full_proof, ok=result.ok,
                reason=result.reason, feedback=result.feedback, completion_tokens=0,
            )
        )
        if result.ok:
            state.proof = full_proof
            state.done = True
            state.stop_reason = STOP_SOLVED
            self._checkpoint_stack(state, [], expansions, state_path)
        return state

    def _propose(self, theorem: Theorem, prev_tactics: list[str], goal_state: str) -> list[str]:
        prompt = self.template.render(theorem, state=goal_state, prev_tactics=tuple(prev_tactics))
        completion = self.client.generate(prompt, max_tokens=self.sample_max_tokens, label="tactic")
        return candidate_tactic_lines(completion.text)

    def _check(
        self, theorem: Theorem, prefix: str, current_state: str, tactic: str | None
    ) -> StepCheck:
        candidate = f"{prefix}\n  {tactic}" if tactic else prefix
        body = f"{candidate}\n  sorry" if candidate else "  sorry"
        src = f"{theorem.statement.rstrip()} := by\n{body}"
        resp = self.elaborate(theorem, src)
        if resp.get("infra_error") or resp["errors"] != 0:
            return StepCheck(ok=False, closed=False)
        sorries = resp["sorries"]
        if len(sorries) == 0:
            return StepCheck(ok=True, closed=True)
        new_state = sorries[0]
        if tactic is not None and new_state.strip() == current_state.strip():
            # Elaborates cleanly but changes NOTHING (e.g. `rw [mul_comm]` cycling the same goal) —
            # a real step must make verified progress, or a beam node could accept it forever and
            # burn the whole search on one stalled branch (found live 2026-07-05, BFS-Prover-V1-7B).
            return StepCheck(ok=False, closed=False)
        return StepCheck(ok=True, closed=False, state=new_state)

    def _resume(self, theorem: Theorem, state_path: str | Path | None) -> AgentState:
        existing = AgentState.load(state_path) if state_path is not None else None
        if existing is not None:
            if existing.budget:
                self.client.meter = BudgetMeter.restore(existing.budget)
            return existing
        return AgentState(theorem_name=theorem.name)

    def _resume_stack(self, state: AgentState) -> list[dict]:
        if not state.budget:
            return []
        return [dict(f) for f in state.budget.get("_search_stack", [])]

    def _checkpoint_stack(
        self, state: AgentState, stack: list[dict], expansions: int, path
    ) -> None:
        meter = self.client.meter
        base = meter.snapshot() if meter is not None else {}
        state.budget = {**base, "_search_stack": stack, "_search_expansions": expansions}
        if path is not None:
            state.save(path)

    def _finish_search(self, state, reason, stack, expansions, path) -> None:
        state.done = True
        state.stop_reason = reason
        self._checkpoint_stack(state, stack, expansions, path)
