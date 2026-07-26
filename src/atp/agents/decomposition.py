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
#
# REVISED 2026-07-25 after the first smoke test (job 11684686): the original design asked for a
# custom `HAVE i: name : stmt` / `MAIN:` delimited format, on the theory that it would be easy to
# parse. In practice Goedel-Prover-V2-8B (heavily trained on ONE specific whole-proof output shape)
# ignored that format entirely and instead did something better: it wrote a normal Lean proof with
# genuine `have <name> : <stmt> := by sorry` placeholders for the parts it couldn't close, e.g.
#   theorem aime_1984_p7 ... := by
#     have h2 : f 999 = 998 := by sorry
#     have h3 : f 84 = 997 := by sorry
#     sorry
# This is directly usable and needs no artificial delimiter format — parse real Lean `have ... :=
# sorry` syntax instead. The one thing the model did NOT do unprompted is give a real closing tactic
# (it left a bare `sorry` where MAIN should be) — the prompt is revised accordingly to ask for it
# explicitly, and the parser rejects a still-bare-sorry MAIN rather than accept it (a MAIN of `sorry`
# would make the sketch check vacuous — it accepts ANY goal — so this must be caught before spending
# any subgoal-proving budget, not left to the final Verifier's loophole policy to catch after the
# fact).
_HAVE_SORRY_RE = re.compile(
    r"have\s+(?P<name>[A-Za-z_][A-Za-z0-9_'.]*)\s*:\s*(?P<stmt>.+?)\s*:=\s*(?:by\s+)?sorry\b"
)
_BARE_SORRY = re.compile(r"^\s*sorry\s*$")


@dataclass(frozen=True)
class Decomposition:
    text: str  # the model's own completion text, sorries intact (IS the sketch, verbatim)
    haves: tuple[tuple[str, str], ...]  # (name, lean proposition), in order of first appearance
    main: str  # the tactic text after the LAST have-sorry, to the end of `text`


def parse_decomposition(text: str) -> Decomposition | None:
    """Extract real Lean `have <name> : <stmt> := (by )?sorry` placeholders directly from a normal
    proof completion. `None` if there are no haves, or the closing block after the last have is
    empty or itself a bare `sorry`/`admit` (nothing real to compose against, see module docstring).
    """
    matches = list(_HAVE_SORRY_RE.finditer(text))
    if not matches:
        return None
    haves = [(m.group("name"), m.group("stmt")) for m in matches]
    main = text[matches[-1].end():].strip()
    main = re.sub(r"```\s*$", "", main).strip()
    if not main or _BARE_SORRY.match(main) or main.lower() in {"admit", "sorry"}:
        return None
    return Decomposition(text=text, haves=tuple(haves), main=main)


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
#
# REVISED 2026-07-25: `decomp.text` is now the model's OWN completion (a full `theorem ... := by`
# proof with real Lean `have ... := sorry` placeholders already in it, extracted verbatim by
# `template.extract_proof` before `parse_decomposition` ever runs) — it does not need to be
# reconstructed line-by-line from parts; the sketch check just verifies it as-is, and composition is
# a targeted substitution of each `have ... := sorry` occurrence, leaving the model's own MAIN block
# (and everything else) untouched.
def build_sketch(theorem: Theorem, decomp: Decomposition) -> str:
    """The model's own completion, sorries intact — for the structural check only (DESIGN.md step 2),
    never scored as a solve."""
    return decomp.text


def build_composed_proof(theorem: Theorem, decomp: Decomposition, subproofs: dict[str, str]) -> str:
    """Splice VERIFIED subproofs (no sorry) into the model's own completion for the real, scored
    check — a targeted substitution of each `have <name> : <stmt> := (by )?sorry` occurrence,
    everything else (including the model's own MAIN block) left byte-identical."""
    text = decomp.text
    for name, stmt in decomp.haves:
        pat = re.compile(
            rf"have\s+{re.escape(name)}\s*:\s*{re.escape(stmt)}\s*:=\s*(?:by\s+)?sorry\b"
        )
        body = "\n".join(f"    {line}" for line in subproofs[name].splitlines())
        replacement = f"have {name} : {stmt} := by\n{body}"
        text, n = pat.subn(replacement, text, count=1)
        assert n == 1, f"expected exactly one occurrence of have {name} to replace, found {n}"
    return text


_DECOMP_PROMPT = """Write a Lean 4 proof for the following theorem.

{statement}

Break the proof into genuine intermediate steps: for EACH fact you need but cannot prove immediately, \
state it as its own `have <name> : <proposition> := by sorry` and continue past it. You must use MORE \
THAN ONE such `have` unless the goal is genuinely a single step — do not collapse the whole goal into \
one `have` that just restates it. After stating every `have` you need, write the REAL closing \
tactic(s) that finish the goal using those haves — never leave the final step as `sorry`.

Example of the expected shape (illustrative only, not the actual problem):
```lean4
theorem example_thm (a b c : ℕ) (h : a + b = c) : a + b + 0 = c := by
  have step1 : a + b + 0 = a + b := by sorry
  have step2 : a + b = c := by sorry
  rw [step1, step2]
```
Note `step1` and `step2` each isolate one genuinely separate fact, and the closing `rw [step1, step2]` \
is short because the `have`s did the hard work — it is NOT `sorry`.

Respond with the complete Lean 4 proof only, in a single ```lean4 code block.
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
