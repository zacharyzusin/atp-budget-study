"""Tests for prompt templates + completion parsing (Task 0.3)."""

from __future__ import annotations

import pytest

from atp.config import BASE_CONFIG, load_config
from atp.lean import Theorem
from atp.models import (
    TacticTemplate,
    WholeProofTemplate,
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


def test_get_template_and_unknown_raises():
    assert get_template("whole_proof").name == "whole_proof"
    assert get_template("tactic").name == "tactic"
    with pytest.raises(ValueError):
        get_template("nope")


def test_template_from_config():
    cfg = load_config(BASE_CONFIG)
    tmpl = template_from_config(cfg)
    assert tmpl.name == cfg.model.prompt_template  # base.yaml -> whole_proof
