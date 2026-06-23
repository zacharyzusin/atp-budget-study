"""Tests for the Phase 6 Lean Workbook (training corpus) loader."""

from __future__ import annotations

import json

import pytest

from atp.data.lean_workbook import load_lean_workbook, strip_proof_tail


def test_strip_proof_tail_variants():
    head = "theorem lean_workbook_0 (a : ℝ) : a = a"
    assert strip_proof_tail(head + " := by sorry") == head
    assert strip_proof_tail(head + "  :=  by sorry") == head
    assert strip_proof_tail(head + " := sorry") == head
    # nothing to strip -> unchanged
    assert strip_proof_tail(head) == head


def test_load_lean_workbook(tmp_path):
    rows = [
        {"_lw_id": "lean_workbook_5",
         "formal_statement": "theorem lean_workbook_5 (a : ℝ) : a = a := by sorry",
         "natural_language_statement": "trivially a = a", "tags": ["algebra"]},
        {"_lw_id": "lean_workbook_9",
         "formal_statement": "theorem lean_workbook_9 : 1 + 1 = 2 := sorry",
         "natural_language_statement": "one plus one", "tags": []},
    ]
    p = tmp_path / "clean.json"
    p.write_text(json.dumps(rows))
    probs = load_lean_workbook(p)
    assert [x.name for x in probs] == ["lean_workbook_5", "lean_workbook_9"]
    assert probs[0].statement == "theorem lean_workbook_5 (a : ℝ) : a = a"
    assert "sorry" not in probs[0].statement and "sorry" not in probs[1].statement
    assert all(x.benchmark == "lean_workbook" and x.split == "train" for x in probs)
    assert probs[0].informal_statement == "trivially a = a"
    assert probs[0].provenance["corpus"] == "lean_workbook_clean"


def test_load_lean_workbook_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_lean_workbook(tmp_path / "does_not_exist.json")
