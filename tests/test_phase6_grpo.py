"""Tests for the GRPO prompt-dataset builder (pure; the trainer/GPU path runs on the probe)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from phase6_grpo import build_prompt_dataset  # noqa: E402

from atp.models.templates import WholeProofTemplate  # noqa: E402


def test_prompt_is_conversational_and_inference_faithful():
    rows = [{"name": "lw_1", "statement": "theorem lw_1 : 1 = 1",
             "opens": [], "imports": ["Mathlib"]}]
    ds = build_prompt_dataset(rows)
    assert len(ds) == 1
    ex = ds[0]
    # conversational prompt = a single user turn
    assert isinstance(ex["prompt"], list)
    assert ex["prompt"][0]["role"] == "user"
    # byte-exact match to what the eval agent renders
    expected = WholeProofTemplate().render(
        __import__("atp.lean.backends", fromlist=["Theorem"]).Theorem(
            name="lw_1", statement="theorem lw_1 : 1 = 1")
    )
    assert ex["prompt"][0]["content"] == expected
    # reward columns forwarded
    assert ex["name"] == "lw_1"
    assert ex["statement"] == "theorem lw_1 : 1 = 1"
    assert ex["opens"] == []
    assert ex["imports"] == ["Mathlib"]


def test_defaults_for_missing_opens_imports():
    rows = [{"name": "t", "statement": "theorem t : True"}]
    ds = build_prompt_dataset(rows)
    assert ds[0]["imports"] == ["Mathlib"]
    assert ds[0]["opens"] == []


def test_content_contains_statement_and_sorry_scaffold():
    rows = [{"name": "t", "statement": "theorem t (n : Nat) : n = n",
             "opens": [], "imports": ["Mathlib"]}]
    content = build_prompt_dataset(rows)[0]["prompt"][0]["content"]
    assert "theorem t (n : Nat) : n = n := by sorry" in content
    assert "```lean4" in content
