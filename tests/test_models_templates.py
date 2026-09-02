"""Tests for prompt templates + completion parsing (Task 0.3)."""

from __future__ import annotations

import pytest

from atp.config import BASE_CONFIG, load_config
from atp.lean import Theorem
from atp.models import (
    BFSProverTemplate,
    DeepSeekV15Template,
    GoedelSFTTemplate,
    TacticTemplate,
    WholeProofTemplate,
    candidate_tactic_lines,
    extract_lean_block,
    get_template,
    template_from_config,
)

THM = Theorem(
    name="add_zero",
    statement="theorem add_zero (n : Nat) : n + 0 = n",
    imports=("Mathlib",),
    opens=("Nat",),
)


def test_whole_proof_render_has_instruction_statement_and_fence():
    prompt = WholeProofTemplate().render(THM)
    assert "Lean 4" in prompt
    assert "import Mathlib" in prompt
    assert "open Nat" in prompt
    assert THM.statement in prompt
    assert ":= by" in prompt
    assert "```lean4" in prompt


def test_whole_proof_uses_official_goedel_prompt():
    """Goedel-V2 prompt: the formal block ends in `:= by sorry` and asks for a proof plan."""
    prompt = WholeProofTemplate().render(THM)
    assert prompt.startswith("Complete the following Lean 4 code:")
    assert ":= by sorry" in prompt
    assert "proof plan" in prompt


def test_whole_proof_official_header_adds_aesop_and_max_heartbeats_only():
    """`WholeProofOfficialHeaderTemplate` (2026-07-24, external calibration critique) must differ
    from `WholeProofTemplate` ONLY in the header (import Aesop + set_option maxHeartbeats 0) — same
    instruction, same plan-suffix, same fence, same everything else, so the calibration cell
    isolates
    the header/protocol variable and nothing else."""
    from atp.models import WholeProofOfficialHeaderTemplate

    official = WholeProofOfficialHeaderTemplate().render(THM)
    plain = WholeProofTemplate().render(THM)
    assert "import Aesop" in official
    assert "set_option maxHeartbeats 0" in official
    assert "import Aesop" not in plain
    assert "set_option maxHeartbeats 0" not in plain
    # Strip each one's own header, everything after must match byte-for-byte.
    assert official.split("theorem", 1)[1] == plain.split("theorem", 1)[1]
    assert official.startswith("Complete the following Lean 4 code:")
    assert "proof plan" in official


def test_whole_proof_official_header_registered_under_its_own_prompt_template_name():
    from atp.models import WholeProofOfficialHeaderTemplate

    assert isinstance(get_template("whole_proof_official_header"), WholeProofOfficialHeaderTemplate)


def test_whole_proof_ignores_informal_statement_unaffected_by_the_deepseek_v15_fix():
    """Regression check: the `informal_statement` doc-comment fix (2026-07-06, see
    PROGRESS.md/DECISIONS.md that date) only touches `DeepSeekV15Template`/`GoedelSFTTemplate` —
    `WholeProofTemplate` (Goedel-V2/DeepSeek-V2) must render byte-identically whether or not the
    theorem carries an informal_statement, since it was never part of its own official format."""
    thm_with_informal = Theorem(
        name=THM.name, statement=THM.statement, imports=THM.imports, opens=THM.opens,
        informal_statement="Show that n + 0 = n for every natural number n.",
    )
    assert WholeProofTemplate().render(THM) == WholeProofTemplate().render(thm_with_informal)


def test_continuation_is_byte_exact_with_render_except_for_the_completed_code():
    """Stage B proof-continuation must share the EXACT wrapper of the cold whole-proof prompt
    (instruction + fence + header + plan suffix); only the in-block code differs — `:= by <prefix>`
    instead of `:= by sorry`. This is the inference-mode-match guard (a drifted wrapper silently
    degrades the prover)."""
    t = WholeProofTemplate()
    cold = t.render(THM)
    cont = t.render_continuation(THM, "  have h : n + 0 = n := by simp")
    # same opening instruction, same import/open header, same plan suffix, same fence language tag
    assert cont.startswith("Complete the following Lean 4 code:")
    assert cont.endswith(t.PLAN_SUFFIX)
    assert "import Mathlib" in cont and "open Nat" in cont and "```lean4" in cont
    assert THM.statement in cont
    # the ONLY difference from cold is the sorry-vs-prefix tail of the code block
    assert ":= by sorry" in cold and ":= by sorry" not in cont
    assert "have h : n + 0 = n := by simp" in cont
    # replacing the prefix back with `sorry` reproduces the cold prompt byte-for-byte
    assert cont.replace("\n  have h : n + 0 = n := by simp\n```", " sorry\n```") == cold


def test_whole_proof_refinement_carries_statement_error_and_no_dangling_fence():
    r = WholeProofTemplate().render_refinement(THM, "theorem ... := by rfl", "error: rfl failed")
    assert "rfl failed" in r
    assert THM.statement in r
    assert r.count("```") % 2 == 0  # all fences closed (chat turn, not a completion prefix)


def test_whole_proof_extracts_fenced_block():
    completion = "Sure!\n```lean4\ntheorem t : True := by\n  trivial\n```\n"
    proof = WholeProofTemplate().extract_proof(THM, completion)
    assert proof == "theorem t : True := by\n  trivial"


def test_extract_uses_last_block():
    """Models often draft in an earlier block; the final block is the answer."""
    completion = "```lean4\nattempt 1\n```\nrethinking...\n```lean4\nfinal proof\n```"
    assert extract_lean_block(completion) == "final proof"


def test_extract_falls_back_to_raw_when_unfenced():
    assert extract_lean_block("no fence here") is None
    proof = WholeProofTemplate().extract_proof(THM, "  theorem t : True := by trivial  ")
    assert proof == "theorem t : True := by trivial"


def test_tactic_render_and_extract():
    t = TacticTemplate()
    prompt = t.render(THM, state="n : Nat ⊢ n + 0 = n", prev_tactics=("intro n",))
    assert "next tactic" in prompt.lower()
    assert "intro n" in prompt
    assert "n + 0 = n" in prompt
    # extraction returns a single tactic, fences/whitespace stripped
    assert t.extract_proof(THM, "```lean\nsimp\n```") == "simp"
    assert t.extract_proof(THM, "  rfl  \n") == "rfl"


def test_tactic_extract_proof_pulls_the_answer_out_of_a_reasoning_completion():
    # Real Goedel-Prover-V2-8B completion (captured live 2026-07-05,
    # scripts/phase7_format_e_diagnostic.py): the model reasons at length even when told to answer
    # with just a tactic, then announces its answer as `### Next Tactic: `<tactic>``. The naive
    # first-non-empty-line parse grabbed the WHOLE markdown line (garbage); it must pull out just
    # the backtick-quoted tactic.
    completion = (
        "### Next Tactic: `simp_all [IsSimpleGroup]`\n\n"
        "#### Explanation:\n1. The theorem states that if `G` is a finite group of order 224 "
        "and `G` is simple, then we derive a contradiction (`false`).\n"
        "2. The hypothesis `hG : card G = 224` gives the order of `G`.\n\n"
        "### Complete Lean 4 Proof\n\n```lean4\ntheorem exercise"
    )
    t = TacticTemplate()
    assert t.extract_proof(THM, completion) == "simp_all [IsSimpleGroup]"


def test_candidate_tactic_lines_puts_the_marker_first():
    # Same fixture as above: the explicit marker is the highest-confidence candidate.
    completion = "### Next Tactic: `simp_all [IsSimpleGroup]`\n\nExplanation:\n1. blah"
    assert candidate_tactic_lines(completion)[0] == "simp_all [IsSimpleGroup]"


def test_candidate_tactic_lines_recovers_lines_from_an_unclosed_fence():
    # Real Goedel-Prover-V2-8B completion (captured live 2026-07-05): a multi-`have` compound
    # sketch inside a ```lean fence that got cut off before it ever closes. `extract_lean_block`
    # can't help (no closing fence) — the tail after the LAST opening fence must still be mined.
    completion = (
        "### Next Tactic\n\n```lean\n"
        "have h1 : A = A := by\n"
        "  apply Eq.symm\n"
        "  apply Eq.symm\n"
        "  -- a comment, not a tactic\n"
        "  rw [Subgroup.ext_iff]"
    )
    candidates = candidate_tactic_lines(completion)
    assert "have h1 : A = A := by" in candidates
    assert "apply Eq.symm" in candidates
    assert "rw [Subgroup.ext_iff]" in candidates
    # markdown headers and bare comments are never proposed as tactics
    assert "### Next Tactic" not in candidates
    assert "-- a comment, not a tactic" not in candidates
    # `apply Eq.symm` appears twice in the source; only its first (most confident) position is kept
    assert candidates.count("apply Eq.symm") == 1


def test_candidate_tactic_lines_empty_when_the_completion_is_pure_unconverged_prose():
    # Real Goedel-Prover-V2-8B completion (captured live 2026-07-05): pure analysis, no code at all
    # within the sampled budget. No candidate should be fabricated out of prose.
    completion = (
        "### Detailed Proof and Analysis\n\n"
        "First, let's understand the problem:\n\nWe are given..."
    )
    candidates = candidate_tactic_lines(completion)
    assert "Detailed Proof and Analysis" not in candidates  # the '#'-header line is dropped
    # whatever remains is prose sentences, not fabricated Lean — the oracle will reject all of them,
    # which is the correct behavior (stuck, not a hallucinated accept), not this function's job to
    # filter further.


def test_get_template_and_unknown_raises():
    assert get_template("whole_proof").name == "whole_proof"
    assert get_template("tactic").name == "tactic"
    assert get_template("bfs_prover").name == "bfs_prover"
    assert get_template("deepseek_v15").name == "deepseek_v15"
    assert get_template("goedel_sft").name == "goedel_sft"
    with pytest.raises(ValueError):
        get_template("nope")


def test_deepseek_v15_render_matches_quick_start_py():
    # Verified against deepseek-ai/DeepSeek-Prover-V1.5's quick_start.py (2026-07-05): a RAW
    # completion, no proof-plan preamble — "Complete the following Lean 4 code:\n\n```lean4\n" +
    # header + statement ending in `:= by` (no `sorry`; the model continues past this point and
    # closes its own fence).
    prompt = DeepSeekV15Template().render(THM)
    assert prompt.startswith("Complete the following Lean 4 code:\n\n```lean4\n")
    assert "import Mathlib" in prompt
    assert "open Nat" in prompt
    assert prompt.rstrip().endswith(":= by")
    assert "sorry" not in prompt
    assert "proof plan" not in prompt.lower()


def test_deepseek_v15_render_byte_exact_header_against_official_quick_start_py():
    """CRITICAL REGRESSION (found live 2026-07-06 — see PROGRESS.md/DECISIONS.md that date). The
    test above only checked the general SHAPE (instruction, fence, no sorry/plan) — never the
    literal header content — so it missed a real gap: the OFFICIAL quick_start.py (re-fetched from
    github.com/deepseek-ai/DeepSeek-Prover-V1.5, byte-for-byte) uses this exact `code_prefix`:

        import Mathlib
        import Aesop

        set_option maxHeartbeats 0

        open BigOperators Real Nat Topology Rat

        theorem ... := by

    `DeepSeekV15Template` was missing BOTH `import Aesop` and `set_option maxHeartbeats 0` — the
    latter disables Lean's elaboration heartbeat limit; WITHOUT it, otherwise-valid proofs using
    nlinarith/field_simp/simp on nontrivial goals can spuriously fail to elaborate in time, which is
    indistinguishable from a genuine "wrong proof" failure without checking the raw prompt. This is
    exactly the kind of "genuine-looking failure that's actually a format bug" this investigation
    has hit twice already.
    """
    prompt = DeepSeekV15Template().render(THM)
    assert "import Mathlib\nimport Aesop" in prompt
    assert "set_option maxHeartbeats 0" in prompt
    # ordering matters: imports, then the heartbeat option, then opens, then the theorem
    assert prompt.index("import Aesop") < prompt.index("set_option maxHeartbeats 0")
    assert prompt.index("set_option maxHeartbeats 0") < prompt.index("open Nat")
    assert prompt.index("open Nat") < prompt.index("theorem add_zero")


def test_deepseek_v15_render_includes_informal_statement_doc_comment_when_present():
    """CRITICAL REGRESSION (found live 2026-07-06, see PROGRESS.md/DECISIONS.md that date):
    quick_start.py's own example wraps the informal problem statement as a `/-- ... -/` doc-comment
    directly before the theorem — `informal_statement` was silently dropped at the
    `Problem.to_theorem()` boundary (fixed in `tests/test_data.py`'s regression), so this was NEVER
    rendered for any model, even for the 242/244 miniF2F problems that have one. Median completion
    length for DeepSeek-Prover-V1.5-SFT was ~33 tokens on this exact (informal-statement-less)
    prompt — far too short for a real multi-step proof — a real behavioral signature, not just an
    error pattern, that this fix targets.
    """
    thm = Theorem(
        name="add_zero",
        statement="theorem add_zero (n : Nat) : n + 0 = n",
        imports=("Mathlib",),
        opens=("Nat",),
        informal_statement="Show that n + 0 = n for every natural number n.",
    )
    prompt = DeepSeekV15Template().render(thm)
    assert "/-- Show that n + 0 = n for every natural number n. -/" in prompt
    # doc-comment sits directly before the theorem, after the header/opens
    assert prompt.index("open Nat") < prompt.index("/--")
    assert prompt.index("/--") < prompt.index("theorem add_zero")
    assert prompt.index("-/") < prompt.index("theorem add_zero")


def test_deepseek_v15_render_omits_doc_comment_when_no_informal_statement():
    # THM (module-level fixture) has no informal_statement — must not render an empty `/-- -/`.
    prompt = DeepSeekV15Template().render(THM)
    assert "/--" not in prompt


def test_deepseek_v15_extract_proof_uses_closed_or_unclosed_fence():
    # The opening ```lean4 fence is part of the PROMPT (render), not the completion — so the
    # completion only ever carries a bare CLOSING fence (if the model emitted one at all).
    t = DeepSeekV15Template()
    completion = "  simp_all\n  nlinarith\n```"
    assert t.extract_proof(THM, completion) == "simp_all\n  nlinarith"
    # truncated (no closing fence): falls back to the raw stripped tail
    assert t.extract_proof(THM, "  simp_all") == "simp_all"


def test_deepseek_v15_extract_proof_strips_a_reechoed_opening_fence():
    # Found live 2026-07-06 (Leanabell-Prover-GD-SFT/GD-RL, which reuses this exact template): some
    # checkpoints re-echo the opening ```lean4 marker at the start of their OWN completion instead
    # of
    # continuing straight into code, even though the prompt already opened the fence. Left
    # unstripped
    # this guaranteed a Lean parse error on every such attempt. Must be a no-op for completions that
    # don't do this (the two cases above stay unchanged).
    t = DeepSeekV15Template()
    assert t.extract_proof(THM, "```lean4\n  simp_all\n  nlinarith") == "simp_all\n  nlinarith"
    assert t.extract_proof(THM, "```lean4\n  simp_all\n```") == "simp_all"


def test_goedel_sft_render_asks_for_explanatory_comments():
    # Verified against Goedel-LM/Goedel-Prover's eval/step1_inference.py (2026-07-05): same raw,
    # no-plan-preamble structure as DeepSeekV15Template, but a distinct instruction wording.
    prompt = GoedelSFTTemplate().render(THM)
    assert prompt.startswith(
        "Complete the following Lean 4 code with explanatory comments preceding each line of code:"
    )
    assert "```lean4" in prompt
    assert prompt.rstrip().endswith(":= by")
    assert "proof plan" not in prompt.lower()


def test_goedel_sft_render_byte_exact_header_against_official_step1_inference_py():
    """CRITICAL REGRESSION (found live 2026-07-06 — same class of gap as DeepSeekV15Template, see
    PROGRESS.md/DECISIONS.md that date). Re-fetched github.com/Goedel-LM/Goedel-Prover's
    `eval/step1_inference.py` byte-for-byte: its own
    `LEAN4_DEFAULT_HEADER = "import Mathlib\\nimport Aesop\\n\\nset_option maxHeartbeats 0\\n\\n
    open BigOperators Real Nat Topology Rat\\n\\n"` — Leanabell-Prover-GD-SFT/GD-RL (which reuse
    this
    exact template) and Goedel-Prover-SFT itself were both missing `import Aesop` and
    `set_option maxHeartbeats 0`.
    """
    prompt = GoedelSFTTemplate().render(THM)
    assert "import Mathlib\nimport Aesop" in prompt
    assert "set_option maxHeartbeats 0" in prompt
    assert prompt.index("import Aesop") < prompt.index("set_option maxHeartbeats 0")
    assert prompt.index("set_option maxHeartbeats 0") < prompt.index("open Nat")
    assert prompt.index("open Nat") < prompt.index("theorem add_zero")


def test_goedel_sft_render_includes_informal_statement_doc_comment_when_present():
    # Same fix, same rationale as DeepSeekV15Template's version — see that test's docstring.
    thm = Theorem(
        name="add_zero",
        statement="theorem add_zero (n : Nat) : n + 0 = n",
        imports=("Mathlib",),
        opens=("Nat",),
        informal_statement="Show that n + 0 = n for every natural number n.",
    )
    prompt = GoedelSFTTemplate().render(thm)
    assert "/-- Show that n + 0 = n for every natural number n. -/" in prompt
    assert prompt.index("open Nat") < prompt.index("/--") < prompt.index("theorem add_zero")


def test_goedel_sft_extract_proof():
    t = GoedelSFTTemplate()
    assert t.extract_proof(THM, "  -- comment\n  simp\n```") == "-- comment\n  simp"


def test_goedel_sft_extract_proof_strips_a_reechoed_opening_fence():
    # Same fix as DeepSeekV15Template — see that test's docstring. GoedelSFTTemplate is the template
    # Leanabell-Prover-GD-SFT/GD-RL actually use.
    t = GoedelSFTTemplate()
    assert t.extract_proof(THM, "```lean4\n-- comment\n  simp") == "-- comment\n  simp"
    assert t.extract_proof(THM, "```lean4\n-- comment\n  simp\n```") == "-- comment\n  simp"


def test_bfs_prover_render_matches_the_models_own_card_format():
    # Verified against ByteDance-Seed/BFS-Prover-V1-7B's model card 2026-07-05: the model expects
    # EXACTLY "{state}:::" — no instruction text, no theorem restatement, no chat template. Card's
    # own worked example: "h : x = y + 2 ⊢ x - 1 = y + 1:::" -> "simp [h]".
    t = BFSProverTemplate()
    prompt = t.render(THM, state="h : x = y + 2\n⊢ x - 1 = y + 1")
    assert prompt == "h : x = y + 2\n⊢ x - 1 = y + 1:::"


def test_bfs_prover_extract_proof_is_the_raw_completion_unmodified():
    t = BFSProverTemplate()
    assert t.extract_proof(THM, "simp [h]") == "simp [h]"
    assert t.extract_proof(THM, "  ring  \n") == "ring"


def test_bfs_prover_render_ignores_prev_tactics_and_theorem_per_its_trained_format():
    # Unlike TacticTemplate, BFS-Prover's card format has no room for tactic history or the
    # restated theorem — passing them must not change the rendered prompt.
    t = BFSProverTemplate()
    bare = t.render(THM, state="⊢ True")
    with_history = t.render(THM, state="⊢ True", prev_tactics=("intro n", "simp"))
    assert bare == with_history == "⊢ True:::"


def test_template_from_config():
    cfg = load_config(BASE_CONFIG)
    tmpl = template_from_config(cfg)
    assert tmpl.name == cfg.model.prompt_template  # base.yaml -> whole_proof
