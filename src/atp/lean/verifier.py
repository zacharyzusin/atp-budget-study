"""Verifier: backend verdict + loophole/timeout policy -> a structured, sound `VerifyResult`.

This is the deterministic decision layer the agent loop relies on. Given any `LeanBackend`, it:
  * parses the raw compiler output,
  * applies the soundness policy (reject `sorry`/`admit`/`native_decide` even if Lean "accepts"),
  * surfaces the earliest failing tactic + message for refinement feedback and Phase-2 reward.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from atp.lean.backends import LeanBackend, Theorem
from atp.lean.errors import (
    LOOPHOLE_DEFAULT,
    FailingStep,
    LeanMessage,
    ParsedLeanOutput,
    attribute_failure,
    find_loopholes,
    parse_lean_output,
)

if TYPE_CHECKING:
    from atp.config import ExperimentConfig

# A whole proof MUST declare the goal it proves. A submission with no `theorem`/`lemma`/`example`
# (e.g. a generation truncated at the token cap that emitted only a preamble `def`/`#eval`/prose)
# can still *compile* — Lean has nothing to fail on — and would otherwise be scored "verified".
# Requiring a declaration is a necessary soundness gate (validated: 528/528 real solves declare
# one; it removes the truncation false-positives that dominated the ProofNet# runs, 2026-06-14).
_DECL_RE = re.compile(r"(?m)^\s*(?:theorem|lemma|example)\b")


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    reason: str  # "ok" | "compile_error" | "timeout" | "loophole"
    raw_output: str
    parsed: ParsedLeanOutput
    earliest_error: LeanMessage | None
    failing_step: FailingStep | None
    loopholes: tuple[str, ...]
    timed_out: bool
    elapsed_s: float

    @property
    def feedback(self) -> str:
        """Compact human-readable feedback for the proposer's refinement step (Task 0.4)."""
        if self.ok:
            return "Proof verified."
        if self.reason == "timeout":
            return f"Verification timed out after {self.elapsed_s:.1f}s."
        if self.reason == "no_goal":
            return (
                "Proof rejected: no theorem/lemma/example declaration found "
                "(output may be truncated or incomplete)."
            )
        if self.reason == "loophole":
            return f"Proof rejected: uses disallowed tactic(s) {', '.join(self.loopholes)}."
        if self.failing_step is not None:
            fs = self.failing_step
            return f"Failed at step {fs.step_index} (`{fs.tactic}`): {fs.message}"
        if self.earliest_error is not None:
            e = self.earliest_error
            return f"Error at {e.line}:{e.col}: {e.text}"
        return "Proof rejected (no parseable error)."


class Verifier:
    def __init__(
        self,
        backend: LeanBackend,
        reject_loopholes: tuple[str, ...] = LOOPHOLE_DEFAULT,
        timeout_s: int = 120,
    ) -> None:
        self.backend = backend
        self.reject_loopholes = tuple(reject_loopholes)
        self.timeout_s = timeout_s

    @classmethod
    def from_config(cls, config: ExperimentConfig, backend: LeanBackend) -> Verifier:
        return cls(
            backend,
            reject_loopholes=tuple(config.lean.reject_loopholes),
            timeout_s=config.lean.verify_timeout_s,
        )

    def verify(self, theorem: Theorem, proof: str) -> VerifyResult:
        raw = self.backend.verify(theorem, proof)
        parsed = parse_lean_output(raw.output)
        loopholes = tuple(find_loopholes(proof, self.reject_loopholes))
        # `sorry` can pass compilation as a mere warning — treat it as a loophole too.
        rejects_sorry = "sorry" in self.reject_loopholes
        if parsed.uses_sorry_warning and rejects_sorry and "sorry" not in loopholes:
            loopholes = (*loopholes, "sorry")

        if raw.timed_out:
            reason = "timeout"
        elif (not raw.success) or parsed.has_error:
            reason = "compile_error"
        elif not _DECL_RE.search(proof):
            # Compiled cleanly but proves nothing: the submission never declares the goal.
            reason = "no_goal"
        elif loopholes:
            reason = "loophole"
        else:
            reason = "ok"

        earliest = parsed.earliest_error
        step = attribute_failure(proof, parsed) if earliest is not None else None
        return VerifyResult(
            ok=(reason == "ok"),
            reason=reason,
            raw_output=raw.output,
            parsed=parsed,
            earliest_error=earliest,
            failing_step=step,
            loopholes=loopholes,
            timed_out=raw.timed_out,
            elapsed_s=raw.elapsed_s,
        )
