"""Tests for the data layer (Task 0.5): loaders, exclusions, contamination, manifest.

Fast + Lean-free: parsing is pure text. A fixture miniF2F dir exercises the loader; a guarded test
checks the real staged benchmark counts (244/244) when present.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atp.config import BASE_CONFIG, load_config
from atp.data import (
    FLAG_CONTAMINATED,
    FLAG_NOVEL,
    apply_exclusions,
    load_dataset,
    load_minif2f,
    load_novel_names,
    load_proofnet,
    mark_contamination,
)
from atp.data.minif2f import DEFAULT_MINIF2F_DIR, parse_minif2f_lean

FIXTURE_LEAN = """import Mathlib

open Real Nat Topology
open scoped BigOperators

theorem t_one (n : Nat) : n + 0 = n := sorry

theorem t_two
  (x : ℝ)
  (h : x > 0) :
  x + 0 = x := sorry

theorem t_bad : (1 : Nat) = 2 := sorry
"""


def _make_minif2f(tmp_path: Path) -> Path:
    root = tmp_path / "miniF2F"
    (root / "formal").mkdir(parents=True)
    (root / "formal" / "valid.lean").write_text(FIXTURE_LEAN)
    idir = root / "informal" / "valid"
    idir.mkdir(parents=True)
    (idir / "t_one.json").write_text('{"problem_name": "t_one", "informal_statement": "n plus 0."}')
    return root


def _cfg(tmp_path, **data_overrides):
    cfg = load_config(BASE_CONFIG)
    updates = {"minif2f_dir": str(_make_minif2f(tmp_path)), **data_overrides}
    return cfg.model_copy(update={"data": cfg.data.model_copy(update=updates)})


# -- parsing ---------------------------------------------------------------------------
def test_parse_strips_proof_and_extracts_names():
    parsed = parse_minif2f_lean(FIXTURE_LEAN)
    names = [n for n, _s, _l in parsed]
    assert names == ["t_one", "t_two", "t_bad"]
    stmt = dict((n, s) for n, s, _ in parsed)
    assert stmt["t_one"] == "theorem t_one (n : Nat) : n + 0 = n"  # := sorry stripped
    assert "sorry" not in stmt["t_two"]
    assert stmt["t_two"].startswith("theorem t_two")


def test_load_minif2f_fixture(tmp_path):
    problems = load_minif2f("valid", _make_minif2f(tmp_path))
    assert [p.name for p in problems] == ["t_one", "t_two", "t_bad"]
    p0 = problems[0]
    assert p0.benchmark == "minif2f" and p0.split == "valid"
    assert p0.imports == ("Mathlib",)
    assert p0.opens == ("Real", "Nat", "Topology", "BigOperators")  # scoped flattened
    assert p0.informal_statement == "n plus 0."
    assert p0.provenance["source_line"] == 6  # 1-based line of `theorem t_one`
    # to_theorem round-trips the fields the verifier needs
    thm = p0.to_theorem()
    assert thm.name == "t_one" and thm.opens == p0.opens
    # CRITICAL REGRESSION (found live 2026-07-06, see PROGRESS.md/DECISIONS.md that date):
    # informal_statement was silently dropped at this boundary — `Theorem` had no field for it, so
    # DeepSeekV15Template/GoedelSFTTemplate could never include the doc-comment their official
    # inference scripts always do, even for the 242/244 miniF2F problems that have one.
    assert thm.informal_statement == p0.informal_statement == "n plus 0."


def test_missing_split_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_minif2f("test", _make_minif2f(tmp_path))  # only valid.lean exists


# -- exclusions ------------------------------------------------------------------------
def test_apply_exclusions_flags_and_reports_unmatched(tmp_path):
    problems = load_minif2f("valid", _make_minif2f(tmp_path))
    flagged, unmatched = apply_exclusions(problems, {"t_bad", "does_not_exist"})
    by_name = {p.name: p for p in flagged}
    assert by_name["t_bad"].is_unprovable
    assert not by_name["t_one"].is_unprovable
    assert unmatched == ["does_not_exist"]  # typo / version-mismatch surfaced


# -- contamination ---------------------------------------------------------------------
def test_mark_contamination_tags_novel_and_rest(tmp_path):
    problems = load_minif2f("valid", _make_minif2f(tmp_path))
    marked = mark_contamination(problems, novel_names={"t_two"})
    by_name = {p.name: p for p in marked}
    assert FLAG_NOVEL in by_name["t_two"].flags
    assert FLAG_CONTAMINATED in by_name["t_one"].flags
    assert FLAG_CONTAMINATED not in by_name["t_two"].flags  # novel ≠ contaminated


# -- load_dataset orchestration --------------------------------------------------------
def test_load_dataset_excludes_and_records_manifest(tmp_path):
    cfg = _cfg(tmp_path, split="valid", exclude_unprovable=True)
    # Point exclusions at a temp file naming t_bad.
    excl = tmp_path / "excl.txt"
    excl.write_text("t_bad\n# comment\n")
    data = cfg.data.model_copy(update={"exclusions_file": str(excl)})
    cfg = cfg.model_copy(update={"data": data})

    ds = load_dataset(cfg, model_revision="rev-abc")
    names = [p.name for p in ds.problems]
    assert "t_bad" not in names  # excluded
    assert ds.manifest.counts["total_loaded"] == 3
    assert ds.manifest.counts["excluded"] == 1
    assert ds.manifest.counts["returned"] == 2
    assert ds.manifest.model_revision == "rev-abc"
    assert ds.manifest.exclusions_applied == ["t_bad"]
    assert ds.manifest.exclusions_unmatched == []


def test_load_dataset_limit_for_smoke(tmp_path):
    cfg = _cfg(tmp_path, split="valid", exclude_unprovable=False, limit=2)
    ds = load_dataset(cfg)
    assert len(ds.problems) == 2
    assert ds.manifest.counts["returned"] == 2


def test_novel_split_requires_names(tmp_path):
    cfg = _cfg(tmp_path, split="valid", use_novel_split=True)
    with pytest.raises(ValueError):
        load_dataset(cfg)  # no novel_names → refuse empty silently


def test_novel_split_filters(tmp_path):
    cfg = _cfg(tmp_path, split="valid", use_novel_split=True, exclude_unprovable=False)
    ds = load_dataset(cfg, novel_names={"t_one"})
    assert [p.name for p in ds.problems] == ["t_one"]
    assert ds.manifest.use_novel_split is True


# -- novel_names_file plumbing (config → CLI/run) --------------------------------------
def _cfg_root(tmp_path, **data_overrides):
    """A config whose project.root is tmp_path, so relative novel_names_file resolves there."""
    cfg = _cfg(tmp_path, **data_overrides)
    proj = cfg.project.model_copy(update={"root": str(tmp_path)})
    return cfg.model_copy(update={"project": proj})


def test_load_novel_names_none_returns_empty(tmp_path):
    assert load_novel_names(_cfg_root(tmp_path)) == []


def test_load_novel_names_newline_skips_blanks_and_comments(tmp_path):
    (tmp_path / "novel.txt").write_text("# held-out set\nt_one\n\n  t_two  \nt_one\n")
    cfg = _cfg_root(tmp_path, novel_names_file="novel.txt")
    assert load_novel_names(cfg) == ["t_one", "t_two"]  # trimmed, comment/blank dropped, de-duped


def test_load_novel_names_json_list(tmp_path):
    (tmp_path / "novel.json").write_text('["t_one", "t_two"]')
    cfg = _cfg_root(tmp_path, novel_names_file="novel.json")
    assert load_novel_names(cfg) == ["t_one", "t_two"]


def test_load_novel_names_resolves_relative_to_project_root(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "n.txt").write_text("t_one\n")
    cfg = _cfg_root(tmp_path, novel_names_file="sub/n.txt")
    assert load_novel_names(cfg) == ["t_one"]


def test_load_novel_names_missing_file_raises(tmp_path):
    cfg = _cfg_root(tmp_path, novel_names_file="nope.txt")
    with pytest.raises(FileNotFoundError, match="novel_names_file"):
        load_novel_names(cfg)


def test_load_novel_names_empty_file_raises(tmp_path):
    (tmp_path / "empty.txt").write_text("# only a comment\n\n")
    cfg = _cfg_root(tmp_path, novel_names_file="empty.txt")
    with pytest.raises(ValueError, match="empty"):
        load_novel_names(cfg)


def test_load_novel_names_bad_json_raises(tmp_path):
    (tmp_path / "bad.json").write_text('{"not": "a list"}')
    cfg = _cfg_root(tmp_path, novel_names_file="bad.json")
    with pytest.raises(ValueError, match="list of strings"):
        load_novel_names(cfg)


def test_novel_names_file_flows_into_load_dataset(tmp_path):
    # The end-to-end config path: a names file restricts the dataset exactly like explicit names do.
    (tmp_path / "novel.txt").write_text("t_one\n")
    cfg = _cfg_root(
        tmp_path, split="valid", use_novel_split=True, exclude_unprovable=False,
        novel_names_file="novel.txt",
    )
    # mirrors run_eval's resolution (explicit names empty → fall back to the config file)
    ds = load_dataset(cfg, novel_names=load_novel_names(cfg))
    assert [p.name for p in ds.problems] == ["t_one"]
    assert ds.manifest.use_novel_split is True


# -- proofnet --------------------------------------------------------------------------
def test_load_proofnet_fixture(tmp_path):
    root = tmp_path / "proofnet"
    root.mkdir()
    (root / "test.jsonl").write_text(
        '{"name": "exercise_1", "statement": "theorem exercise_1 : True", "opens": ["Nat"]}\n'
        "\n"  # blank line tolerated
        '{"name": "exercise_2", "statement": "theorem exercise_2 : 1 = 1"}\n'
    )
    problems = load_proofnet("test", root)
    assert [p.name for p in problems] == ["exercise_1", "exercise_2"]
    assert problems[0].benchmark == "proofnet_sharp"
    assert problems[0].opens == ("Nat",)


def test_proofnet_unstaged_raises():
    with pytest.raises(FileNotFoundError):
        load_proofnet("test", None)


# -- real staged benchmark (guarded) ---------------------------------------------------
def test_real_minif2f_counts_when_staged():
    if not (DEFAULT_MINIF2F_DIR / "formal" / "valid.lean").is_file():
        pytest.skip("real miniF2F not staged at the default sibling path")
    valid = load_minif2f("valid")
    test = load_minif2f("test")
    assert len(valid) == 244
    assert len(test) == 244
    # provenance stamped from the git checkout
    assert valid[0].provenance.get("source_commit")
