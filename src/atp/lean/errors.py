"""Pure-Python parsing of Lean 4 compiler output. No Lean/LeanDojo dependency.

Two signals matter downstream:
  * pass/fail + the human-readable error (refinement feedback, Task 0.4), and
  * the *earliest failing tactic* + message (dense reward shaping, Phase 2 / Task 0.2 spec).

Lean emits diagnostics as headers `path:line:col: <severity>: <message>` followed by zero or more
continuation lines (goals, hints) until the next header. We group those, then expose the errors
ordered by source position so the *earliest* failure is unambiguous.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Loopholes that make a "proof" unsound for our protocol (PROJECT_PLAN.md §9).
LOOPHOLE_DEFAULT: tuple[str, ...] = ("sorry", "admit", "native_decide")

# `Foo/Bar.lean:12:4: error: unsolved goals`  (path may be <stdin>; col may be 0)
_HEADER_RE = re.compile(
    r"^(?P<path>.*?):(?P<line>\d+):(?P<col>\d+):\s*"
    r"(?P<sev>error|warning|info)\b:?[ \t]?(?P<msg>.*)$"
)


@dataclass(frozen=True)
class LeanMessage:
    """One diagnostic from the Lean compiler."""

    severity: str  # "error" | "warning" | "info"
    line: int
    col: int
    text: str
    path: str | None = None

    @property
    def is_error(self) -> bool:
        return self.severity == "error"

    @property
    def position(self) -> tuple[int, int]:
        return (self.line, self.col)


@dataclass(frozen=True)
class FailingStep:
    """The tactic blamed for the earliest failure (best-effort source-position attribution)."""

    step_index: int  # 0-based index among non-blank tactic lines of the proof body
    tactic: str
    line: int  # 1-based line of that tactic within the proof body
    message: str


@dataclass(frozen=True)
class ParsedLeanOutput:
    messages: tuple[LeanMessage, ...]
    raw: str = ""

    @property
    def errors(self) -> tuple[LeanMessage, ...]:
        return tuple(m for m in self.messages if m.severity == "error")

    @property
    def warnings(self) -> tuple[LeanMessage, ...]:
        return tuple(m for m in self.messages if m.severity == "warning")

    @property
    def has_error(self) -> bool:
        return any(m.severity == "error" for m in self.messages)

    @property
    def earliest_error(self) -> LeanMessage | None:
        """The error with the smallest (line, col) — i.e. where compilation first breaks."""
        errs = self.errors
        return min(errs, key=lambda m: m.position) if errs else None

    @property
    def uses_sorry_warning(self) -> bool:
        """Lean reports `declaration uses 'sorry'` as a warning, not an error — catch it."""
        return any("sorry" in m.text for m in self.warnings)


def parse_lean_output(raw: str) -> ParsedLeanOutput:
    """Parse raw Lean stderr/stdout into structured messages (continuation lines folded in)."""
    messages: list[LeanMessage] = []
    cur: dict | None = None
    cont: list[str] = []

    def _flush() -> None:
        nonlocal cur, cont
        if cur is not None:
            head = cur["msg"]
            body = "\n".join([head, *cont]).strip() if cont else head.strip()
            messages.append(
                LeanMessage(cur["sev"], cur["line"], cur["col"], body, cur["path"] or None)
            )
        cur = None
        cont = []

    for ln in raw.splitlines():
        m = _HEADER_RE.match(ln)
        if m:
            _flush()
            cur = {
                "path": m.group("path"),
                "line": int(m.group("line")),
                "col": int(m.group("col")),
                "sev": m.group("sev"),
                "msg": m.group("msg"),
            }
        elif cur is not None:
            cont.append(ln)
        # lines before the first header are preamble noise — ignore.
    _flush()
    return ParsedLeanOutput(tuple(messages), raw)


def find_loopholes(proof_text: str, tokens: tuple[str, ...] = LOOPHOLE_DEFAULT) -> list[str]:
    """Return loophole tokens that appear as whole words in the proof (order = `tokens`).

    Word-boundary matching so identifiers like `admitCard` or `sorryAx`-free names don't trip it;
    conservative on purpose (soundness > recall) — a stray `sorry` token fails the proof.
    """
    found: list[str] = []
    for tok in tokens:
        if re.search(rf"(?<!\w){re.escape(tok)}(?!\w)", proof_text):
            found.append(tok)
    return found


def _tactic_lines(proof_body: str) -> list[tuple[int, str]]:
    """Non-blank lines of the proof body as (1-based line number, stripped text)."""
    return [(i, s.strip()) for i, s in enumerate(proof_body.splitlines(), start=1) if s.strip()]


def attribute_failure(
    proof_body: str, parsed: ParsedLeanOutput, body_line_offset: int = 0
) -> FailingStep | None:
    """Map the earliest error back to the tactic most likely responsible.

    Picks the last tactic line at or before the error's (offset-adjusted) line. `body_line_offset`
    is how many lines precede `proof_body` in the compiled source (e.g. imports + signature), so
    callers can pass absolute Lean line numbers.
    """
    err = parsed.earliest_error
    if err is None:
        return None
    tactics = _tactic_lines(proof_body)
    if not tactics:
        return None
    rel_line = err.line - body_line_offset
    chosen_idx, (chosen_line, chosen_text) = 0, tactics[0]
    for idx, (lno, txt) in enumerate(tactics):
        if lno <= rel_line:
            chosen_idx, chosen_line, chosen_text = idx, lno, txt
        else:
            break
    return FailingStep(chosen_idx, chosen_text, chosen_line, err.text)
