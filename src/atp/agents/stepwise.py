"""Phase 7 Track 1 — stepwise generation with verified proof-state feedback.

The Stage B signature (near-zero teacher-forced loss on closings, yet autoregressive failure) is the
exposure-bias fingerprint: whole-proof sampling free-runs on the model's OWN drifted intermediate
states, so late-proof closings fail even though the model assigns them high conditional probability.
This module re-grounds each continuation on the TRUE verified proof prefix instead.

Mode 3 (verified-state re-grounding): generate a whole proof → verify → keep the VERIFIED prefix
(the tactics before the earliest failing step) → re-prompt the model to continue from there →
repeat until closed or budget out. The cheap, in-distribution exposure-bias fix (reuses
`render_continuation`).
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

if TYPE_CHECKING:
    from atp.lean.backends import Theorem
    from atp.lean.verifier import Verifier
    from atp.models.client import VLLMClient
    from atp.models.templates import WholeProofTemplate


def verified_prefix(proof_body: str, failing_line: int) -> str:
    """The verbatim proof-body lines before the earliest failing tactic — the re-grounding prefix.

    `failing_line` is 1-based within the proof body (`FailingStep.line`). Lines before it elaborated
    without error (the earliest error is at the failing tactic), so they are the model's verified
    progress. Formatting/indentation is preserved so the prefix splices back under `:= by`
    byte-exactly. An earliest failure at the first tactic yields the empty prefix (nothing verified
    → fall back to a fresh proposal).
    """
    lines = proof_body.splitlines()
    return "\n".join(lines[: max(failing_line - 1, 0)])


def propose_only_tokens_to_solve(attempts: list[dict]) -> tuple[bool, int | None]:
    """Reconstruct Mode 1 (whole-proof, NO error-feedback) cost from a logged Mode-2 baseline run.

    A committed baseline (refinement.enabled=True by default) interleaves fresh `propose` rounds
    with `refine` attempts conditioned on the immediately-prior failure. A `propose` attempt is a
    FRESH, feedback-free sample (unconditioned on any previous attempt in the cell) — exactly what a
    dedicated no-refinement run would draw. So the Mode-1 pass@B curve is recoverable for free,
    offline, by keeping only `propose`-kind attempts and their cumulative token cost: this is the
    same budget-independence trick Phase 4 used, applied to attempt KIND instead of a budget cap.

    A cell only counts as Mode-1-solved if a `propose` attempt itself closed it — a `refine` solve
    depended on error feedback Mode 1 never receives, so it does not count (conservative: Mode 1's
    reconstructed solve rate is a lower bound on what a real independent no-refinement run might do,
    since a fresh no-refinement run could in principle later re-draw a similarly-good sample that a
    refine attempt merely reached first here — the reconstruction never overcounts Mode 1).
    """
    spent = 0
    for a in attempts:
        if a["kind"] != "propose":
            continue
        spent += int(a["completion_tokens"])
        if a["ok"]:
            return True, spent
    return False, None


def tactic_body_prefix(full_proof: str, failing_line: int) -> str:
    """The verified re-grounding prefix, translated out of the model's FULL completion text.

    `Verifier.verify` computes `FailingStep.line` over the whole completion (`attribute_failure`
    with no offset) — a whole-proof model echoes its OWN restated `theorem ... := by` header before
    the tactics, so that line count includes the header. Re-grounding must continue from just the
    TACTIC BODY (never re-declare the header inside `render_continuation`, which supplies its own),
    so this locates the first `:= by`, counts how many lines precede it, and translates
    `failing_line` into a body-relative offset before delegating to `verified_prefix`. A completion
    with no declaration (already a bare continuation, e.g. a prior re-grounding round) passes
    through unchanged (offset 0).
    """
    marker = ":= by"
    idx = full_proof.find(marker)
    if idx == -1:
        return verified_prefix(full_proof, failing_line)
    header = full_proof[: idx + len(marker)]
    offset = header.count("\n") + 1  # lines the header itself spans (1 even with zero newlines)
    body = full_proof[idx + len(marker):].lstrip("\n")
    return verified_prefix(body, failing_line - offset)


def tactic_body_prefix_candidates(
    full_proof: str, failing_line: int, max_back: int = 15
) -> list[str]:
    """`verified_prefix_candidates`, translated out of the model's FULL completion (see
    `tactic_body_prefix`'s header-offset docstring)."""
    marker = ":= by"
    idx = full_proof.find(marker)
    if idx == -1:
        return verified_prefix_candidates(full_proof, failing_line, max_back)
    header = full_proof[: idx + len(marker)]
    offset = header.count("\n") + 1
    body = full_proof[idx + len(marker):].lstrip("\n")
    return verified_prefix_candidates(body, failing_line - offset, max_back)


def _depth(prefix: str) -> int:
    """Number of non-blank tactic lines in a prefix — the verified frontier's depth."""
    return sum(1 for ln in prefix.splitlines() if ln.strip())


def verified_prefix_candidates(proof_body: str, failing_line: int, max_back: int = 15) -> list[str]:
    """`verified_prefix` truncations at the failing line AND at up to `max_back` earlier lines.

    `verified_prefix`'s single fixed cut is frequently a DANGLING boundary in practice: real
    trapped proofs fail mid multi-line tactic combinator (`<;>`, `try { ... }`, a `·` focus block),
    so the line right before the failure is itself inside that combinator, not a clean ancestor
    state (found via live-data inspection 2026-07-04 — 26.8% of candidates on a real trapped run
    ended in a dangling token like `<;>`/`try`/`by`, discarding genuine deep partial credit as a
    side effect of the elaborate gate correctly rejecting the dangling boundary). Backing off
    line-by-line to the nearest earlier point that elaborates cleanly recovers that progress.
    Ordered deepest-first so the caller can stop at the first passing candidate. Blank-line cuts
    are skipped (never a useful boundary); capped at `max_back` non-blank cuts (bounds Lean cost).
    """
    lines = proof_body.splitlines()
    candidates: list[str] = []
    seen_depths: set[int] = set()
    for cut in range(max(failing_line - 1, 0), -1, -1):
        cand = "\n".join(lines[:cut])
        depth = _depth(cand)
        if depth in seen_depths:
            continue
        seen_depths.add(depth)
        candidates.append(cand)
        if len(candidates) > max_back:
            break
    return candidates


def _build_candidate(prefix: str, continuation: str) -> str:
    """Combine the committed prefix with the model's continuation into a proof body to verify.

    If the model re-emitted a whole proof (it repeated the statement / `:= by`) rather than just the
    closing tactics, use it as-is — splicing would duplicate the head. Otherwise append the
    continuation under the verified prefix.
    """
    if "theorem" in continuation or ":= by" in continuation:
        return continuation
    if not prefix:
        return continuation
    return f"{prefix}\n{continuation}"


@dataclass(frozen=True)
class VerifyOutcome:
    """Minimal verify verdict the re-grounding loop needs: did it close, and if not, where."""

    ok: bool
    failing_line: int  # 1-based body line of the earliest failing tactic (0 when solved/unknown)


@dataclass(frozen=True)
class StepwiseResult:
    solved: bool
    proof_body: str
    rounds: int
    prefix_depth: int  # depth of the verified frontier reached (progress signal even when unsolved)


@dataclass
class RegroundProver:
    """Mode 3 — verified-state re-grounding.

    Each round: prompt the model to continue from the current verified prefix, verify the resulting
    body, and — if it fails — advance the verified frontier to the deepest prefix any attempt has
    reached. Re-grounding on the true verified prefix (never the drifted full attempt) is the
    exposure-bias fix. The real wiring injects a budget-metered `generate` (raises when spent);
    `max_rounds` is the pure-core safety cap.
    """

    generate: Callable[[str], tuple[str, str]]   # prompt -> (completion_text, finish_reason)
    verify: Callable[[str], VerifyOutcome]        # proof_body -> outcome
    render_continuation: Callable[[str], str]     # verified_prefix -> continuation prompt
    extract: Callable[[str], str]                 # completion_text -> extracted Lean
    max_rounds: int = 8

    def prove(self) -> StepwiseResult:
        prefix = ""
        best_depth = 0
        for r in range(self.max_rounds):
            text, _finish = self.generate(self.render_continuation(prefix))
            body = _build_candidate(prefix, self.extract(text))
            outcome = self.verify(body)
            if outcome.ok:
                return StepwiseResult(True, body, r + 1, best_depth)
            cand = verified_prefix(body, outcome.failing_line)
            if _depth(cand) > best_depth:
                prefix, best_depth = cand, _depth(cand)
        return StepwiseResult(False, "", self.max_rounds, best_depth)


@dataclass
class RegroundStepwiseAgent:
    """Mode 3, wired to the real client/verifier/budget-meter — a drop-in `.prove()` counterpart to
    `WholeProofAgent` (same `AgentState` checkpoint format), so it plugs into the existing
    restartable-sweep + pass@B machinery unchanged.

    The verified-frontier (`prefix`, its `depth`) is the one piece of extra state Mode 3 needs
    beyond what `AgentState`/`BudgetMeter` already carry. Rather than widening the shared
    `Attempt`/`AgentState` schema (every other phase's tooling reads it), it rides along as two
    extra keys inside the already-freeform `state.budget` dict (`BudgetMeter.restore` reads only
    `limit`/`spent`/`ledger` and ignores the rest, so this is a safe, additive checkpoint format).
    """

    client: VLLMClient
    verifier: Verifier
    template: WholeProofTemplate
    # (theorem, candidate_prefix) -> True iff `<statement> := by\n<prefix>\n  sorry` elaborates
    # cleanly to EXACTLY ONE open goal (the Phase 6 harvest's own deep_state validation,
    # `ReplBackend.elaborate`: errors==0 and len(sorries)==1). A candidate prefix that merely
    # "elaborated without error so far" can still be a DANGLING boundary — e.g. mid a `have h :=
    # by` block with no sub-proof written — which is not a safe re-grounding point: re-prompting
    # from there gives the model a nonsensical "finish this" state and it degenerates into prose
    # (found via the real-data smoke run, not a hypothetical — see DECISIONS.md 2026-07-03). A
    # rejected candidate leaves the frontier at its last VALIDATED value instead of advancing.
    elaborate: Callable[[Theorem, str], bool]
    max_rounds: int = 64
    sample_max_tokens: int = 4096

    def prove(self, theorem: Theorem, state_path: str | Path | None = None) -> AgentState:
        state = self._resume(theorem, state_path)
        if state.done:
            return state
        prefix = str(state.budget.get("_stepwise_prefix", "")) if state.budget else ""
        best_depth = int(state.budget.get("_stepwise_depth", 0)) if state.budget else 0

        try:
            for _ in range(self.max_rounds):
                prompt = (
                    self.template.render(theorem)
                    if prefix == ""
                    else self.template.render_continuation(theorem, prefix)
                )
                completion = self.client.generate(
                    prompt, max_tokens=self.sample_max_tokens, label="reground"
                )
                continuation = self.template.extract_proof(theorem, completion.text)
                candidate = self._candidate(theorem, prefix, continuation)
                result = self.verifier.verify(theorem, candidate)
                state.attempts.append(
                    Attempt(
                        index=state.n_attempts,
                        kind="reground",
                        proof=candidate,
                        ok=result.ok,
                        reason=result.reason,
                        feedback=result.feedback,
                        completion_tokens=completion.completion_tokens,
                    )
                )
                if result.ok:
                    state.proof = candidate
                    self._finish(state, STOP_SOLVED, state_path, prefix, best_depth)
                    return state
                if completion.completion_tokens == 0:
                    self._finish(state, STOP_NO_PROGRESS, state_path, prefix, best_depth)
                    return state
                failing_line = result.failing_step.line if result.failing_step else 1
                for cand_prefix in tactic_body_prefix_candidates(candidate, failing_line):
                    if _depth(cand_prefix) <= best_depth:
                        break  # deepest-first: nothing shallower can beat best_depth either
                    if self.elaborate(theorem, cand_prefix):
                        prefix, best_depth = cand_prefix, _depth(cand_prefix)
                        break
                self._checkpoint(state, prefix, best_depth, state_path)
        except BudgetExhausted:
            self._finish(state, STOP_BUDGET, state_path, prefix, best_depth)
            return state

        self._finish(state, STOP_MAX_ROUNDS, state_path, prefix, best_depth)
        return state

    @staticmethod
    def _candidate(theorem: Theorem, prefix: str, continuation: str) -> str:
        """Build the full proof text to verify from the model's extracted completion.

        The common case: a whole-proof model asked to "complete" a prompt ending mid-proof echoes
        the ENTIRE code block back (header + old prefix + its new tactics) — the same behavior the
        Format-I guard validated (Stage B probe: 99%+ parseable completions). Detected by the
        presence of a declaration/`:= by`, `continuation` is then already the full candidate.
        Fallback (rare degeneration: the model emits only bare new tactics) reconstructs a
        compilable candidate by splicing under the verified prefix, using the theorem's own
        statement — matching `phase6_continuation_probe.build_proof_from_prefix`.
        """
        if "theorem" in continuation or "lemma" in continuation or ":= by" in continuation:
            return continuation
        if not prefix:
            return continuation
        return f"{theorem.statement.rstrip()} := by\n{prefix}\n{continuation}".strip("\n")

    def _resume(self, theorem: Theorem, state_path: str | Path | None) -> AgentState:
        existing = AgentState.load(state_path) if state_path is not None else None
        if existing is not None:
            if existing.budget:
                self.client.meter = BudgetMeter.restore(existing.budget)
            return existing
        return AgentState(theorem_name=theorem.name)

    def _snapshot(self, prefix: str, depth: int) -> dict:
        meter = self.client.meter
        base = meter.snapshot() if meter is not None else {}
        return {**base, "_stepwise_prefix": prefix, "_stepwise_depth": depth}

    def _checkpoint(
        self, state: AgentState, prefix: str, depth: int, path: str | Path | None
    ) -> None:
        state.budget = self._snapshot(prefix, depth)
        if path is not None:
            state.save(path)

    def _finish(
        self,
        state: AgentState,
        reason: str,
        path: str | Path | None,
        prefix: str,
        depth: int,
    ) -> None:
        state.done = True
        state.stop_reason = reason
        self._checkpoint(state, prefix, depth, path)
