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


def _deepseek_lean4_header(theorem: Theorem) -> str:
    """The DeepSeek-Prover-V1.5 / Goedel-Prover-SFT family's shared official header convention —
    verified byte-for-byte 2026-07-06 (see PROGRESS.md/DECISIONS.md that date) against
    `quick_start.py` (deepseek-ai/DeepSeek-Prover-V1.5) and `LEAN4_DEFAULT_HEADER` in
    `eval/step1_inference.py` (Goedel-LM/Goedel-Prover): `import Mathlib`, `import Aesop`,
    `set_option maxHeartbeats 0` (disables Lean's elaboration heartbeat limit — without it,
    otherwise-valid proofs using nlinarith/field_simp/simp on nontrivial goals can spuriously fail
    to elaborate in time, indistinguishable from a genuinely wrong proof), then the theorem's own
    `open` clauses (more accurate, per-problem, than the official scripts' hardcoded default open
    list, which is only a fallback for when no per-problem header is supplied).
    """
    lines = [f"import {imp}" for imp in theorem.imports]
    lines.append("import Aesop")
    lines.append("")
    lines.append("set_option maxHeartbeats 0")
    if theorem.opens:
        lines.append("")
        lines.append("open " + " ".join(theorem.opens))
    return "\n".join(lines)


def _informal_doc_comment(theorem: Theorem) -> str:
    """The `/-- <informal statement> -/\\n` doc-comment quick_start.py's own example places directly
    before the theorem (found live 2026-07-06, see PROGRESS.md/DECISIONS.md that date —
    `informal_statement` was silently dropped at the `Problem.to_theorem()` boundary, so this was
    NEVER rendered for any model despite being present for 242/244 miniF2F problems). Empty string
    when the benchmark doesn't provide one (e.g. ProofNet#) — never emit a hollow `/-- -/`.
    """
    if not theorem.informal_statement:
        return ""
    return f"/-- {theorem.informal_statement} -/\n"


_OPEN_FENCE_RE = re.compile(r"```(?:lean4?|)\s*\n", re.IGNORECASE)


def _partial_fence_body(text: str) -> str | None:
    """The tail after the LAST opening fence, even if it never closes (a truncated completion).

    `extract_lean_block` requires a CLOSING fence, so a reasoning model's multi-step sketch that got
    cut off mid-code (a real, common case — see `candidate_tactic_lines`) yields None from it and
    would otherwise fall all the way back to the raw prose. This recovers the (possibly incomplete)
    code that WAS written."""
    matches = list(_OPEN_FENCE_RE.finditer(text))
    if not matches:
        return None
    return text[matches[-1].end():]


def candidate_tactic_lines(completion: str) -> list[str]:
    """Every plausible single-tactic candidate in a completion, most-to-least confident.

    Reasoning models (Goedel-Prover-V2, e.g.) don't reliably answer with a bare tactic even when
    asked for one — sometimes a clean `` `### Next Tactic: \\`<tactic>\\`` `` one-liner, sometimes a
    multi-`have` compound proof SKETCH (often truncated mid-code), sometimes unconverged prose with
    no code at all (found live 2026-07-05, scripts/phase7_format_e_diagnostic.py). No single fixed
    extraction rule turns all three into one right answer — but a multi-step sketch usually contains
    at least one line that IS individually a legal step forward, even if the sketch as a whole isn't
    one atomic tactic. This yields every candidate so the caller can oracle-validate each in turn
    (via `elaborate`) and take the first that's actually accepted, instead of committing to a single
    guess. Ordered: the explicit marker first (highest confidence), then the model's own Lean lines
    (fenced, closed or not), then raw-text lines as a last resort. Markdown headers ('#...') and
    bare comments ('--...') are dropped; duplicates keep only their first (most confident) position.
    """
    candidates: list[str] = []
    marker = TacticTemplate._NEXT_TACTIC_RE.search(completion)
    if marker:
        candidates.append(marker.group(1).strip())

    block = extract_lean_block(completion) or _partial_fence_body(completion) or completion
    for line in block.splitlines():
        s = line.strip()
        if s and not s.startswith("#") and not s.startswith("--") and s not in candidates:
            candidates.append(s)
    return candidates


def extract_lean_block(text: str) -> str | None:
    """Return the contents of the *last* fenced Lean block, or None if there is no fence.

    The last block is used because models often think aloud in earlier blocks and emit the final
    answer last. Returns None (not "") when no fence is present so callers can fall back.
    """
    matches = list(_FENCE_RE.finditer(text))
    if not matches:
        return None
    return matches[-1].group("body").strip()


_ECHOED_OPENING_FENCE_RE = re.compile(r"^```(?:lean4?|Lean4?)?\s*\n?")


def _strip_echoed_opening_fence(text: str) -> str:
    """For prompt-opens-the-fence templates (the opening ```lean4 is in the PROMPT, so the
    completion is only supposed to carry a bare trailing close, if any): some checkpoints
    (Leanabell-Prover-GD-SFT/GD-RL, found live 2026-07-06 — see PROGRESS.md/DECISIONS.md that date)
    re-echo the opening fence marker at the START of their own completion instead of continuing
    straight into the code. Left unstripped, this guarantees a Lean parse error (`unexpected token
    ` ``` `) on every such attempt — not a real proof failure. Strip it if present; a no-op for
    completions that don't echo it (confirmed: DeepSeek-Prover-V1.5/Goedel-Prover-SFT's own traffic
    doesn't exhibit this, so this is a strict generalization, not a behavior change for them).
    """
    return _ECHOED_OPENING_FENCE_RE.sub("", text, count=1)


@runtime_checkable
class PromptTemplate(Protocol):
    name: str

    def render(self, theorem: Theorem, **kwargs: object) -> str: ...

    def render_refinement(self, theorem: Theorem, prev_proof: str, feedback: str) -> str: ...

    def extract_proof(self, theorem: Theorem, completion: str) -> str: ...


@dataclass(frozen=True)
class WholeProofTemplate:
    """Goedel-Prover-V2-8B: emit a complete Lean 4 proof for the given statement."""

    name: str = "whole_proof"

    # Official Goedel-Prover-V2 prompt (model card / Goedel-LM repo): the formal code (imports + the
    # statement ending in `:= by sorry`) in a ```lean4 block, then an explicit proof-plan request so
    # the reasoning model thinks before emitting the final proof. Sent as the user turn through the
    # chat template (config.model.chat_completions). Deviating from this wording silently degrades
    # the prover (inference must match training) — log any change in DECISIONS.md.
    INSTRUCTION: str = "Complete the following Lean 4 code:"
    PLAN_SUFFIX: str = (
        "Before producing the Lean 4 code to formally prove the given theorem, provide a detailed "
        "proof plan outlining the main proof steps and strategies.\nThe plan should highlight key "
        "ideas, intermediate lemmas, and proof structures that will guide the construction of the "
        "final formal proof."
    )

    def _formal_block(self, theorem: Theorem) -> str:
        """imports + opens + the statement ending in `:= by sorry` (what the model completes)."""
        header = _theorem_header(theorem)
        statement = theorem.statement.rstrip()
        return f"{header}\n\n{statement} := by sorry" if header else f"{statement} := by sorry"

    def render(self, theorem: Theorem, **kwargs: object) -> str:
        return (
            f"{self.INSTRUCTION}\n\n```lean4\n{self._formal_block(theorem)}\n```\n\n{self.PLAN_SUFFIX}"
        )

    def _continuation_block(self, theorem: Theorem, proof_prefix: str) -> str:
        """imports + opens + `<statement> := by` followed by the proof-so-far (no `sorry`)."""
        header = _theorem_header(theorem)
        statement = theorem.statement.rstrip()
        body = proof_prefix.strip("\n")
        block = f"{statement} := by\n{body}"
        return f"{header}\n\n{block}" if header else block

    def render_continuation(self, theorem: Theorem, proof_prefix: str) -> str:
        """Stage B (proof-continuation): byte-for-byte the same prompt as `render` — same
        instruction, fence, header and `:= by` scaffolding — except the ```lean4 block ends at the
        (`proof_prefix`) instead of `sorry`. The model is asked to FINISH from a deep in-situ state.
        Inference-faithful: identical wrapper, only the completed-code differs (empty prefix == the
        cold whole-proof prompt with `sorry`)."""
        block = self._continuation_block(theorem, proof_prefix)
        return f"{self.INSTRUCTION}\n\n```lean4\n{block}\n```\n\n{self.PLAN_SUFFIX}"

    REFINE_INSTRUCTION: str = (
        "The following Lean 4 proof attempt failed to compile. Using the Lean error feedback, "
        "write a corrected and complete proof of the original theorem (no `sorry`)."
    )

    def render_refinement(self, theorem: Theorem, prev_proof: str, feedback: str) -> str:
        return (
            f"{self.REFINE_INSTRUCTION}\n\n"
            f"Theorem:\n```lean4\n{self._formal_block(theorem)}\n```\n\n"
            f"Failed attempt:\n```lean4\n{prev_proof.strip()}\n```\n\n"
            f"Lean error feedback:\n{feedback.strip()}\n\n"
            f"{self.PLAN_SUFFIX}"
        )

    def extract_proof(self, theorem: Theorem, completion: str) -> str:
        """Pull the fenced Lean out of the completion; fall back to the raw text if unfenced."""
        block = extract_lean_block(completion)
        return block if block is not None else completion.strip()


@dataclass(frozen=True)
class DeepSeekV15Template:
    """DeepSeek-Prover-V1.5 family's OWN trained format (verified against `quick_start.py` in the
    deepseek-ai/DeepSeek-Prover-V1.5 repo, 2026-07-05 — not assumed): a RAW completion (no chat
    template, no proof-plan preamble) of `"Complete the following Lean 4 code:\\n\\n```lean4\\n"` +
    the formal statement ending in `:= by` (no `sorry`, unlike `WholeProofTemplate` — the model
    continues directly into the tactic block and the fence is closed by the model itself, not the
    prompt). Pre-dates the chat-tuned "Goedel-style" reasoning prompt (`WholeProofTemplate`'s
    PLAN_SUFFIX) — Base/SFT/RL all share this SAME format (confirmed: it is the RL checkpoint's own
    quick-start example, and Base/SFT are the earlier stages of the identical training pipeline, no
    format change documented at any stage). Also used by models fine-tuned from this lineage keeping
    the same prompt convention (e.g. STP, Goedel-Prover-SFT's own variant differs slightly — see
    `GoedelSFTTemplate`).
    """

    name: str = "deepseek_v15"

    INSTRUCTION: str = "Complete the following Lean 4 code:"

    def _code_prefix(self, theorem: Theorem) -> str:
        header = _deepseek_lean4_header(theorem)
        statement = theorem.statement.rstrip()
        block = f"{_informal_doc_comment(theorem)}{statement} := by\n"
        return f"{header}\n\n{block}" if header else block

    def render(self, theorem: Theorem, **kwargs: object) -> str:
        del kwargs
        return f"{self.INSTRUCTION}\n\n```lean4\n{self._code_prefix(theorem)}"

    def render_refinement(self, theorem: Theorem, prev_proof: str, feedback: str) -> str:
        del prev_proof, feedback
        return self.render(theorem)

    def extract_proof(self, theorem: Theorem, completion: str) -> str:
        """The opening ```lean4 fence lives in the PROMPT, not the completion, so
        `extract_lean_block` (which requires a matched opening+closing pair) never applies here.
        The model closes its OWN fence with a bare trailing ``` — strip that if present; if it
        didn't close (truncated), fall back to the raw stripped tail. Also strips a re-echoed
        OPENING fence some checkpoints emit (see `_strip_echoed_opening_fence`) — a no-op for
        completions that don't do this."""
        del theorem
        text = _strip_echoed_opening_fence(completion.strip())
        if text.endswith("```"):
            text = text[: -len("```")].rstrip("\n")
        return text


@dataclass(frozen=True)
class GoedelSFTTemplate:
    """Goedel-Prover-SFT's OWN trained format (verified against `eval/step1_inference.py` in the
    Goedel-LM/Goedel-Prover GitHub repo, 2026-07-05): a RAW completion (no chat template, no
    proof-plan preamble — unlike its successor `WholeProofTemplate`/Goedel-Prover-V2, a reasoning
    model). Instruction differs from `DeepSeekV15Template` (its own base model) by asking for
    explanatory comments preceding each line: `"Complete the following Lean 4 code with explanatory
    comments preceding each line of code:"`. Otherwise identical structure — fenced ```lean4 block,
    statement ending `:= by`, model continues and closes its own fence.
    """

    name: str = "goedel_sft"

    INSTRUCTION: str = (
        "Complete the following Lean 4 code with explanatory comments preceding each line of code:"
    )

    def _code_prefix(self, theorem: Theorem) -> str:
        header = _deepseek_lean4_header(theorem)
        statement = theorem.statement.rstrip()
        block = f"{_informal_doc_comment(theorem)}{statement} := by\n"
        return f"{header}\n\n{block}" if header else block

    def render(self, theorem: Theorem, **kwargs: object) -> str:
        del kwargs
        return f"{self.INSTRUCTION}\n\n```lean4\n{self._code_prefix(theorem)}"

    def render_refinement(self, theorem: Theorem, prev_proof: str, feedback: str) -> str:
        del prev_proof, feedback
        return self.render(theorem)

    def extract_proof(self, theorem: Theorem, completion: str) -> str:
        """Same fence-ownership situation as `DeepSeekV15Template` — the opening fence is in the
        prompt, so strip a bare trailing ``` from the model's own completion rather than requiring
        `extract_lean_block`'s matched pair. Also strips a re-echoed OPENING fence some checkpoints
        emit (see `_strip_echoed_opening_fence`) — a no-op for completions that don't do this."""
        del theorem
        text = _strip_echoed_opening_fence(completion.strip())
        if text.endswith("```"):
            text = text[: -len("```")].rstrip("\n")
        return text


@dataclass(frozen=True)
class BFSProverTemplate:
    """ByteDance-Seed/BFS-Prover-V1-7B's OWN trained format (verified against its model card
    2026-07-05, not assumed): a raw completion, no chat template, no instruction text at all — the
    model expects exactly `"{state}:::"` and continues directly with the tactic
    (card example: `"h : x = y + 2 ⊢ x - 1 = y + 1:::"` -> `"simp [h]"`). This is a genuinely
    tactic-native model (unlike Goedel-Prover-V2, which always reasons at length even when asked
    for a bare tactic — see `TacticTemplate`'s docstring and DECISIONS.md 2026-07-05), so Mode 4
    (`atp.agents.tactic_stepwise`) is in-distribution for it rather than a forced format.
    """

    name: str = "bfs_prover"

    def render(
        self,
        theorem: Theorem,
        *,
        state: str = "",
        prev_tactics: tuple[str, ...] = (),
        **kwargs: object,
    ) -> str:
        # No room in this model's trained format for the theorem statement or tactic history —
        # it's pure state -> next-tactic, matching LeanDojo-style single-step generation exactly.
        del theorem, prev_tactics, kwargs
        return f"{state.strip()}:::"

    def render_refinement(self, theorem: Theorem, prev_proof: str, feedback: str) -> str:
        return self.render(theorem, state=feedback)

    def extract_proof(self, theorem: Theorem, completion: str) -> str:
        """The tactic is the raw completion itself (no fences/markdown to strip — this model
        wasn't trained to produce them); take the first non-empty line as a defensive trim."""
        del theorem
        for line in completion.splitlines():
            if line.strip():
                return line.strip()
        return completion.strip()


@dataclass(frozen=True)
class TacticTemplate:
    """A generic instruction-following "give me the next tactic" prompt for CHAT models.

    NOT BFS-Prover's own trained format (that's `BFSProverTemplate`, verified against its model
    card) — this is a speculative format for models that follow natural-language instructions
    reasonably (e.g. as an ablation prompt on a whole-proof reasoning model). Reasoning models often
    ignore the "just the tactic" instruction and answer with a CoT explanation instead — see
    `atp.models.templates.candidate_tactic_lines` for the resulting extraction that copes with that.
    """

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

    def render_refinement(self, theorem: Theorem, prev_proof: str, feedback: str) -> str:
        # Tactic mode re-asks for the next tactic, carrying the failed tactic + error as context.
        return self.render(theorem, state=feedback, prev_tactics=(prev_proof,))

    _NEXT_TACTIC_RE = re.compile(r"next\s+tactic\s*:?\s*`([^`]+)`", re.IGNORECASE)

    def extract_proof(self, theorem: Theorem, completion: str) -> str:
        """A single tactic.

        Reasoning-style models (e.g. Goedel-Prover-V2, which always emits a CoT explanation even
        when instructed to answer with just a tactic — found live 2026-07-05, see
        scripts/phase7_format_e_diagnostic.py) announce their answer as
        `### Next Tactic: \\`<tactic>\\`` — matched FIRST, since the generic fenced-block/first-line
        fallback would otherwise grab prose, or a LATER unrelated restated-proof block the same
        completion goes on to produce. Falls back to the original bare/fenced parsing for terser
        models that answer with just the tactic.
        """
        marker = self._NEXT_TACTIC_RE.search(completion)
        if marker:
            return marker.group(1).strip()
        block = extract_lean_block(completion)
        text = block if block is not None else completion
        for line in text.splitlines():
            if line.strip():
                return line.strip()
        return text.strip()


_TEMPLATES: dict[str, PromptTemplate] = {
    "whole_proof": WholeProofTemplate(),
    "tactic": TacticTemplate(),
    "bfs_prover": BFSProverTemplate(),
    "deepseek_v15": DeepSeekV15Template(),
    "goedel_sft": GoedelSFTTemplate(),
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
