"""Prompt templates + completion parsing for the prover models.

Two modes, selected by `config.model.prompt_template`:

  * **whole_proof** (Goedel-Prover-V2-8B): given a Lean 4 theorem statement, the model writes the
    *entire* proof in one shot inside a ```lean4 fenced block. We render the model-card-style
    instruction and extract the fenced Lean back out for the verifier.
  * **tactic** (BFS-Prover): given the statement plus the current proof state and the tactics
    applied so far, the model proposes the *next single tactic*; the search layer (Task 0.4/0.6)
    applies it and recurses.

Pure string handling — no model/Lean import — so it's login-node safe and trivially testable.

NOTE: the exact instruction wording is taken from the published model cards; if a later card
revision changes it, update here and record the change in DECISIONS.md (the served `revision` is
pinned in the config, so prompt drift is a deliberate, logged choice).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from atp.lean.backends import Theorem

if TYPE_CHECKING:
    from atp.config import ExperimentConfig

# A fenced Lean block: ```lean / ```lean4 / ``` ... ```  (language tag optional, case-insensitive).
_FENCE_RE = re.compile(
    r"```(?:lean4?|)\s*\n(?P<body>.*?)```",
    re.DOTALL | re.IGNORECASE,
)


def _theorem_header(theorem: Theorem) -> str:
    """The Lean preamble (imports + opens) that the proof is compiled against."""
    lines = [f"import {imp}" for imp in theorem.imports]
    if theorem.opens:
        lines.append("open " + " ".join(theorem.opens))
    return "\n".join(lines)


def extract_lean_block(text: str) -> str | None:
    """Return the contents of the *last* fenced Lean block, or None if there is no fence.

    The last block is used because models often think aloud in earlier blocks and emit the final
    answer last. Returns None (not "") when no fence is present so callers can fall back.
    """
    matches = list(_FENCE_RE.finditer(text))
    if not matches:
        return None
    return matches[-1].group("body").strip()


@runtime_checkable
class PromptTemplate(Protocol):
    name: str

    def render(self, theorem: Theorem, **kwargs: object) -> str: ...

    def extract_proof(self, theorem: Theorem, completion: str) -> str: ...


@dataclass(frozen=True)
class WholeProofTemplate:
    """Goedel-Prover-V2-8B: emit a complete Lean 4 proof for the given statement."""

    name: str = "whole_proof"

    INSTRUCTION: str = (
        "Complete the following Lean 4 code. Provide the entire file, including the imports and "
        "the theorem statement, with a complete proof (no `sorry`). Put your answer in a single "
        "```lean4 code block."
    )

    def render(self, theorem: Theorem, **kwargs: object) -> str:
        header = _theorem_header(theorem)
        statement = theorem.statement.rstrip()
        # Open the declaration with `:= by` so the model continues into tactic mode.
        scaffold = f"{header}\n\n{statement} := by\n" if header else f"{statement} := by\n"
        return f"{self.INSTRUCTION}\n\n```lean4\n{scaffold}```\n"

    def extract_proof(self, theorem: Theorem, completion: str) -> str:
        """Pull the fenced Lean out of the completion; fall back to the raw text if unfenced."""
        block = extract_lean_block(completion)
        return block if block is not None else completion.strip()


@dataclass(frozen=True)
class TacticTemplate:
    """BFS-Prover: propose the next single tactic from the current proof state."""

    name: str = "tactic"

    INSTRUCTION: str = (
        "You are proving a theorem in Lean 4. Given the current proof state, output the single "
        "next tactic to apply. Output only the tactic, with no commentary and no code fences."
    )

    def render(
        self,
        theorem: Theorem,
        *,
        state: str = "",
        prev_tactics: tuple[str, ...] = (),
        **kwargs: object,
    ) -> str:
        parts = [self.INSTRUCTION, "", f"Theorem: {theorem.statement.rstrip()}"]
        if prev_tactics:
            parts.append("Tactics so far:\n" + "\n".join(f"  {t}" for t in prev_tactics))
        state = state.strip()
        parts.append(f"Current goal state:\n{state}" if state else "Current goal state: (initial)")
        parts.append("Next tactic:")
        return "\n".join(parts)

    def extract_proof(self, theorem: Theorem, completion: str) -> str:
        """A single tactic: strip fences/whitespace and take the first non-empty line."""
        block = extract_lean_block(completion)
        text = block if block is not None else completion
        for line in text.splitlines():
            if line.strip():
                return line.strip()
        return text.strip()


_TEMPLATES: dict[str, PromptTemplate] = {
    "whole_proof": WholeProofTemplate(),
    "tactic": TacticTemplate(),
}


def get_template(name: str) -> PromptTemplate:
    try:
        return _TEMPLATES[name]
    except KeyError:
        raise ValueError(
            f"unknown prompt_template {name!r}; expected one of {sorted(_TEMPLATES)}"
        ) from None


def template_from_config(config: ExperimentConfig) -> PromptTemplate:
    return get_template(config.model.prompt_template)
