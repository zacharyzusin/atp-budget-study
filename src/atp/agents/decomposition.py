"""Subgoal-decomposition agent (WS6 item 3 — design note: results/phase_decomp/DESIGN.md).

Step C (Phase 2) established causally that approach discovery is not the bottleneck for trapped
problems; within-approach execution depth is. Every scaffolding/adaptation lever tested elsewhere in
this project targets discovery or post-hoc adaptation, not execution depth directly. This agent does:
decompose the goal into `have` sub-lemmas, prove each independently (shorter, so easier to execute in
one generation), then splice the verified subproofs back into the original goal and re-verify the
whole thing. Read `results/phase_decomp/DESIGN.md` before touching this file — it has the reasoning
behind every non-obvious choice below (why the sketch check bypasses the loophole policy, why subgoal
theorems reuse the parent's own binder list, what's deliberately NOT a soundness risk and why).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from atp.agents.state import (
    STOP_BUDGET,
    STOP_MAX_ROUNDS,
    STOP_SOLVED,
    AgentState,
    Attempt,
)
from atp.agents.whole_proof import WholeProofAgent
from atp.budget.meter import BudgetExhausted
from atp.lean.backends import Theorem

if TYPE_CHECKING:
    from atp.budget.meter import BudgetMeter
    from atp.lean.verifier import Verifier
    from atp.models.client import VLLMClient
    from atp.models.templates import PromptTemplate

# ---------------------------------------------------------------- parsing the model's decomposition
_HAVE_RE = re.compile(
    r"(?im)^\s*HAVE\s+\d+\s*:\s*(?P<name>[A-Za-z_][A-Za-z0-9_']*)\s*:\s*(?P<stmt>.+?)\s*$"
)


@dataclass(frozen=True)
class Decomposition:
    haves: tuple[tuple[str, str], ...]  # (name, lean proposition), one line each
    main: str  # closing tactic block, may reference the have names


def parse_decomposition(text: str) -> Decomposition | None:
    """Extract HAVE lines + a MAIN block from a completion. `None` if the shape isn't parseable.

    One have per line by design (v1 scope, see DESIGN.md) — a have whose proposition needs a
    genuine line break is not supported; the model is prompted to keep each HAVE on one line.
    """
    haves = [(m.group("name"), m.group("stmt")) for m in _HAVE_RE.finditer(text)]
    if not haves:
        return None
    # MAIN: everything after the literal "MAIN:" marker to the end (or a closing fence).
    idx = text.upper().find("MAIN:")
    if idx == -1:
        return None
    main_text = text[idx + len("MAIN:"):]
    main = main_text.strip()
    main = re.sub(r"```\s*$", "", main).strip()
    if not main:
        return None
    return Decomposition(haves=tuple(haves), main=main)


# ---------------------------------------------------------------- signature splitting
def split_signature(statement: str) -> tuple[str, str]:
    """`theorem foo {G} [Group G] (a b : G) : P` -> ("{G} [Group G] (a b : G)", "P").

    Finds the LAST top-level (bracket-depth-0) colon — every colon INSIDE a binder is at depth>=1
    (`(a b : G)`, `{G : Type*}`), so the last depth-0 colon is always the binders/goal separator,
    regardless of how many binders precede it or what's inside them.
    """
    s = re.sub(r"^\s*(?:theorem|lemma|example)\b\s*[A-Za-z_][A-Za-z0-9_'.]*\s*", "", statement.strip())
    depth = 0
    split_at = -1
    for i, ch in enumerate(s):
        if ch in "({[":
            depth += 1
        elif ch in ")}]":
            depth -= 1
        elif ch == ":" and depth == 0:
            split_at = i
    if split_at == -1:
        return "", s.strip()
    return s[:split_at].strip(), s[split_at + 1:].strip()


def subgoal_theorem(parent: Theorem, index: int, name: str, prop: str) -> Theorem:
    """Build a standalone `Theorem` for one `have`, reusing the parent's own binder list so the
    subgoal has access to exactly the same variables/hypotheses it would inside the parent's proof."""
    binders, _ = split_signature(parent.statement)
    sig = f"{binders} : {prop}" if binders else f": {prop}"
    return Theorem(
        name=f"{parent.name}__have{index}",
        statement=f"theorem {parent.name}__have{index} {sig}".strip(),
        imports=parent.imports,
        opens=parent.opens,
    )


# ---------------------------------------------------------------- proof assembly
def build_sketch(theorem: Theorem, decomp: Decomposition) -> str:
    """Full proof text with every have as `:= sorry` — for the structural check only, never scored
    as a solve (see DESIGN.md step 2)."""
    lines = [f"{theorem.statement} := by"]
    for name, stmt in decomp.haves:
        lines.append(f"  have {name} : {stmt} := sorry")
    for line in decomp.main.splitlines():
        lines.append(f"  {line}")
    return "\n".join(lines)


def build_composed_proof(theorem: Theorem, decomp: Decomposition, subproofs: dict[str, str]) -> str:
    """Splice VERIFIED subproofs (no sorry) back into the parent goal for the real, scored check."""
    lines = [f"{theorem.statement} := by"]
    for name, stmt in decomp.haves:
        lines.append(f"  have {name} : {stmt} := by")
        for line in subproofs[name].splitlines():
            lines.append(f"    {line}")
    for line in decomp.main.splitlines():
        lines.append(f"  {line}")
    return "\n".join(lines)


_DECOMP_PROMPT = """Prove the following Lean 4 theorem by decomposing it into independent sub-lemmas.

{statement}

Respond with a list of `have` sub-lemmas that, once each is proved, let a short tactic block close \
the goal. Use EXACTLY this format (one line per HAVE, plain Lean propositions, no proof terms):

HAVE 1: h1 : <a Lean proposition, in the theorem's own variable/hypothesis context>
HAVE 2: h2 : <a Lean proposition>
MAIN:
<a short tactic block that closes the goal using h1, h2, ...>
"""


@dataclass
class DecompositionAgent:
    """Budget-bounded propose-decomposition -> prove-subgoals -> compose loop for one problem.

    Shares its `client`'s `BudgetMeter` with the per-subgoal `WholeProofAgent`s it spawns, so total
    spend across a decomposition round (sketch generation + every subgoal attempt) is accounted
    against the same per-problem budget as every other agent in this project.
    """

    client: VLLMClient
    verifier: Verifier
    template: PromptTemplate  # used only to extract the fenced-code block from a raw completion
    max_rounds: int = 8
    max_subgoal_rounds: int = 8
    sample_max_tokens: int = 2048

    def prove(self, theorem: Theorem, state_path: str | Path | None = None) -> AgentState:
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
            if existing.budget:
                from atp.budget.meter import BudgetMeter
                self.client.meter = BudgetMeter.restore(existing.budget)
            return existing
        return AgentState(theorem_name=theorem.name)

    def _search(self, theorem: Theorem, state: AgentState, state_path) -> None:
        for round_index in range(self.max_rounds):
            prompt = _DECOMP_PROMPT.format(statement=theorem.statement)
            completion = self.client.generate(
                prompt, max_tokens=self.sample_max_tokens, label="decompose"
            )
            raw_text = self.template.extract_proof(theorem, completion.text)
            decomp = parse_decomposition(raw_text)

            if decomp is None:
                self._record_attempt(state, "decompose", raw_text, ok=False,
                                      reason="unparseable", feedback="Could not parse HAVE/MAIN.",
                                      tokens=completion.completion_tokens)
                self._checkpoint(state, state_path)
                continue

            sketch = build_sketch(theorem, decomp)
            raw = self.verifier.backend.verify(theorem, sketch)
            if not (raw.success and raw.declares_goal and not raw.timed_out):
                self._record_attempt(state, "decompose", sketch, ok=False,
                                      reason="sketch_rejected",
                                      feedback=f"Sketch did not elaborate: {raw.output[:2000]}",
                                      tokens=completion.completion_tokens)
                self._checkpoint(state, state_path)
                continue

            # Record the accepted decomposition proposal itself (charges its generation tokens to
            # the audit trail) before spending anything on subgoal proving.
            self._record_attempt(state, "decompose", sketch, ok=False, reason="sketch_accepted",
                                  feedback="Structural sketch elaborated; proving subgoals.",
                                  tokens=completion.completion_tokens)
            self._checkpoint(state, state_path)

            subproofs = self._prove_subgoals(theorem, decomp, state, state_path)
            if subproofs is None:
                continue  # one subgoal never solved within its cap; try a fresh decomposition

            composed = build_composed_proof(theorem, decomp, subproofs)
            result = self.verifier.verify(theorem, composed)
            self._record_attempt(state, "compose", composed, ok=result.ok,
                                  reason=result.reason, feedback=result.feedback,
                                  tokens=0)  # subgoal tokens already charged individually
            self._checkpoint(state, state_path)
            if result.ok:
                state.proof = composed
                self._finish(state, STOP_SOLVED, state_path)
                return
        self._finish(state, STOP_MAX_ROUNDS, state_path)

    def _prove_subgoals(
        self, parent: Theorem, decomp: Decomposition, state: AgentState, state_path
    ) -> dict[str, str] | None:
        """Prove every have independently (propose-only, no refinement — see DESIGN.md step 3).
        Returns {name: verified proof text} iff ALL subgoals solve; None on the first failure."""
        subproofs: dict[str, str] = {}
        for i, (name, prop) in enumerate(decomp.haves, start=1):
            sub_theorem = subgoal_theorem(parent, i, name, prop)
            sub_agent = WholeProofAgent(
                client=self.client,
                verifier=self.verifier,
                template=self.template,
                refine_enabled=False,
                max_rounds=self.max_subgoal_rounds,
                sample_max_tokens=self.sample_max_tokens,
            )
            sub_state = sub_agent.prove(sub_theorem)
            for a in sub_state.attempts:
                state.attempts.append(a)  # fold subgoal attempts into the parent's audit trail
            if self.client.meter is not None:
                state.budget = self.client.meter.snapshot()
            if not sub_state.solved:
                self._checkpoint(state, state_path)
                return None
            subproofs[name] = sub_state.proof or ""
        return subproofs

    def _record_attempt(self, state: AgentState, kind: str, proof: str, *, ok: bool,
                         reason: str, feedback: str, tokens: int) -> None:
        state.attempts.append(Attempt(
            index=state.n_attempts, kind=kind, proof=proof, ok=ok, reason=reason,
            feedback=feedback, completion_tokens=tokens,
        ))
        if self.client.meter is not None:
            state.budget = self.client.meter.snapshot()

    def _finish(self, state: AgentState, reason: str, path) -> None:
        state.done = True
        state.stop_reason = reason
        self._checkpoint(state, path)

    @staticmethod
    def _checkpoint(state: AgentState, path) -> None:
        if path is not None:
            state.save(path)
