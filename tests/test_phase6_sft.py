"""Tests for the Phase 6 SFT data builder core (no model/GPU: template is a tiny stub)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "phase6_build_sft.py"
_spec = importlib.util.spec_from_file_location("phase6_build_sft", _SCRIPT)
build = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = build
_spec.loader.exec_module(build)


class _Thm:
    def __init__(self, name):
        self.name = name


class _Template:
    def render(self, thm):
        return f"COLD::{thm.name}"

    def render_continuation(self, thm, prefix):
        return f"CONT::{thm.name}::{prefix}"


def test_make_example_A_uses_cold_prompt_and_fenced_proof():
    e = build.make_example("A", _Template(), _Thm("t1"), "theorem t1 := by simp", None)
    assert e["kind"] == "A" and e["name"] == "t1"
    assert e["messages"][0] == {"role": "user", "content": "COLD::t1"}
    assert e["messages"][1]["role"] == "assistant"
    assert e["messages"][1]["content"] == "```lean4\ntheorem t1 := by simp\n```"


def test_make_example_B_uses_continuation_prompt_with_prefix():
    e = build.make_example("B", _Template(), _Thm("t2"), "theorem t2 := by\n  a\n  b", "  a", "  b")
    assert e["messages"][0]["content"] == "CONT::t2::  a"
    # assistant turn is the SAME fenced full proof shape as A (single variable = the prompt)
    assert e["messages"][1]["content"].startswith("```lean4\ntheorem t2")
    # B records supervise_after = the closing block (verbatim, with indent), so training masks loss
    # to the closing only
    assert e["supervise_after"] == "  b"


def test_make_example_A_has_no_supervise_after():
    e = build.make_example("A", _Template(), _Thm("t1"), "theorem t1 := by simp", None)
    assert "supervise_after" not in e


def test_make_example_B_requires_prefix():
    with pytest.raises(ValueError):
        build.make_example("B", _Template(), _Thm("t"), "p", None)


def _shard_file(tmp_path, shard, recs):
    p = tmp_path / f"probe_hard.s{shard}.json"
    p.write_text(json.dumps({"records": recs}))
    return p


def test_hard_rows_from_shards_replays_stride_and_filters_hard(tmp_path):
    # 4 rows, 2 shards: shard0 -> rows[0],[2]; shard1 -> rows[1],[3]
    rows = [{"name": f"r{i}", "k": i, "n_groups": 9} for i in range(4)]
    _shard_file(tmp_path, 0, [{"name": "r0", "is_hard": True, "k": 0, "n_groups": 9},
                              {"name": "r2", "is_hard": False, "k": 2, "n_groups": 9}])
    _shard_file(tmp_path, 1, [{"name": "r1", "is_hard": False, "k": 1, "n_groups": 9},
                              {"name": "r3", "is_hard": True, "k": 3, "n_groups": 9}])
    hard = build.hard_rows_from_shards(rows, str(tmp_path / "probe_hard.s*.json"), 2)
    assert {r["name"] for r in hard} == {"r0", "r3"}


def test_hard_rows_from_shards_detects_name_stride_mismatch(tmp_path):
    rows = [{"name": "r0"}, {"name": "r1"}]
    _shard_file(tmp_path, 0, [{"name": "WRONG", "is_hard": True}])
    with pytest.raises(ValueError, match="stride mismatch"):
        build.hard_rows_from_shards(rows, str(tmp_path / "probe_hard.s*.json"), 2)
