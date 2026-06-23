"""Tests for the Phase 6 §0 disjointness primitives."""

from __future__ import annotations

from atp.data.disjointness import exact_overlap, normalize_formal_statement


def test_normalize_strips_name_and_whitespace():
    a = "theorem lean_workbook_0 (a b : ℝ) (ha : 0 < a) : a + b = b + a"
    b = "theorem  exercise_1_2   (a b : ℝ)  (ha : 0 < a)  :  a + b = b + a"
    # Same statement, different name + spacing -> identical key.
    assert normalize_formal_statement(a) == normalize_formal_statement(b)


def test_normalize_drops_proof_tail():
    with_proof = "theorem t (n : ℕ) : n = n := by\n  rfl"
    bare = "theorem t (n : ℕ) : n = n"
    assert normalize_formal_statement(with_proof) == normalize_formal_statement(bare)
    sorry_tail = "lemma t (n : ℕ) : n = n := sorry"
    assert normalize_formal_statement(sorry_tail) == normalize_formal_statement(bare)


def test_normalize_keeps_distinct_statements_distinct():
    a = "theorem t (a : ℝ) : a = a"
    b = "theorem t (a : ℝ) : a + 1 = a"
    assert normalize_formal_statement(a) != normalize_formal_statement(b)


def test_lemma_and_example_keywords():
    assert normalize_formal_statement("lemma foo : True") == normalize_formal_statement(
        "example : True"
    )


def test_exact_overlap_finds_renamed_duplicate():
    train = {
        "lean_workbook_5": "theorem lean_workbook_5 (a : ℝ) : a = a",
        "lean_workbook_6": "theorem lean_workbook_6 (a : ℝ) : a + 1 = a + 1",
    }
    evalset = {"minif2f_x": "theorem minif2f_x  (a : ℝ) :  a = a"}
    hits = exact_overlap(train, evalset)
    assert hits == [("lean_workbook_5", "minif2f_x")]


def test_exact_overlap_empty_when_disjoint():
    train = {"lw_1": "theorem lw_1 (a : ℝ) : a = a"}
    evalset = {"ev_1": "theorem ev_1 (b : ℕ) : b + 0 = b"}
    assert exact_overlap(train, evalset) == []
