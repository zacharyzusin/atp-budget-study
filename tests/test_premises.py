"""Tests for the Mathlib premise-corpus parser (Phase 1 retrieval data-prep).

Pure CPU/string parsing — fast, login-node safe. Drives the lexical extractor on small Lean
snippets; the real corpus build is the script `scripts/build_premise_corpus.py`.
"""

from __future__ import annotations

from atp.data.premises import build_corpus, extract_premises, strip_comments


def test_strip_comments_block_line_and_docstring():
    text = (
        "theorem a : True := trivial  -- inline\n"
        "/-- a docstring mentioning theorem ghost -/\n"
        "/- block /- nested -/ still in -/\n"
        "theorem b : True := trivial\n"
    )
    out = strip_comments(text)
    assert "ghost" not in out  # docstring content removed
    assert "still in" not in out  # nested block fully removed
    assert "theorem a" in out and "theorem b" in out


def test_extract_qualifies_by_namespace_not_section():
    text = (
        "namespace Foo\n"
        "section Helpers\n"
        "theorem bar (n : Nat) : n = n := rfl\n"
        "end Helpers\n"
        "lemma baz : True := trivial\n"
        "end Foo\n"
        "def top : Nat := 0\n"
    )
    got = dict(extract_premises(text))
    assert "Foo.bar" in got  # namespace-qualified
    assert got["Foo.bar"] == "theorem bar (n : Nat) : n = n"  # signature cut at :=
    assert "Foo.baz" in got  # section did not add to the name
    assert "top" in got  # back at top level after `end Foo`


def test_extract_joins_multiline_signature():
    text = (
        "theorem long (a : Nat)\n"
        "    (b : Nat) :\n"
        "    a + b = b + a := by\n"
        "  simp\n"
    )
    got = dict(extract_premises(text))
    assert got["long"] == "theorem long (a : Nat) (b : Nat) : a + b = b + a"


def test_extract_handles_attributes_and_modifiers():
    text = (
        "@[simp] theorem tagged : True := trivial\n"
        "protected noncomputable def secret : Nat := 0\n"
    )
    got = dict(extract_premises(text))
    assert "tagged" in got and "secret" in got


def test_extract_skips_anonymous_instance():
    text = "instance : Inhabited Nat := ⟨0⟩\ninstance named : Inhabited Bool := ⟨true⟩\n"
    names = [n for n, _ in extract_premises(text)]
    assert "named" in names
    assert all(n for n in names)  # no empty names from the anonymous instance


def test_build_corpus_dedups_and_writes_rows(tmp_path):
    (tmp_path / "A.lean").write_text("namespace N\ntheorem dup : True := trivial\nend N\n")
    (tmp_path / "B.lean").write_text(
        "theorem N.dup : True := trivial\ntheorem other : True := trivial\n"
    )
    rows = list(build_corpus(tmp_path))
    names = [r["name"] for r in rows]
    assert names.count("N.dup") == 1  # first occurrence wins, deduped
    assert "other" in names
    assert all(set(r) == {"name", "decl"} for r in rows)


def test_build_corpus_limit_caps_files(tmp_path):
    for i in range(5):
        (tmp_path / f"F{i}.lean").write_text(f"theorem t{i} : True := trivial\n")
    assert len(list(build_corpus(tmp_path, limit=2))) == 2
