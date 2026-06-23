"""Tests for the Phase 6 harvest aggregation (pure; the Lean/REPL path runs on the pilot)."""

from __future__ import annotations

import sys
from pathlib import Path

from atp.agents.state import STOP_BUDGET, STOP_SOLVED, AgentState

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from phase6_harvest import _depth_interleave, collect_verified_proofs  # noqa: E402

from atp.data.closing_targets import ClosingCandidate  # noqa: E402


def _cand(depth: int, tag: str) -> ClosingCandidate:
    return ClosingCandidate(k=1, n_groups=2, prefix_with_sorry=tag, closing=tag, depth=depth)


def _write_state(d: Path, name: str, *, solved: bool, proof: str | None):
    st = AgentState(
        theorem_name=name,
        done=True,
        stop_reason=STOP_SOLVED if solved else STOP_BUDGET,
        proof=proof,
        budget={"spent": 100, "limit": 16000},
    )
    st.save(d / f"{name}__seed0.json")


def test_collect_verified_proofs_keeps_only_solved_with_proof(tmp_path):
    states = tmp_path / "agent_states"
    states.mkdir()
    _write_state(states, "lean_workbook_1", solved=True, proof="theorem a : True := by trivial")
    _write_state(states, "lean_workbook_2", solved=False, proof=None)          # unsolved -> drop
    _write_state(states, "lean_workbook_3", solved=True, proof=None)           # solved but no proof
    got = collect_verified_proofs(tmp_path)
    assert got == [("lean_workbook_1", "theorem a : True := by trivial")]


def test_collect_verified_proofs_empty_when_no_states(tmp_path):
    (tmp_path / "agent_states").mkdir()
    assert collect_verified_proofs(tmp_path) == []


def test_depth_interleave_alternates_and_front_loads_diversity():
    # closing_truncations emits depth0 first; interleave surfaces a depth1 within max_per_proof=2
    cands = [_cand(0, "a"), _cand(0, "b"), _cand(1, "x"), _cand(1, "y"), _cand(1, "z")]
    out = _depth_interleave(cands)
    assert [c.depth for c in out[:2]] == [1, 0]  # first two cover both depths
    assert {c.closing for c in out} == {"a", "b", "x", "y", "z"}  # nothing dropped


def test_depth_interleave_handles_single_depth():
    only0 = [_cand(0, "a"), _cand(0, "b")]
    assert [c.closing for c in _depth_interleave(only0)] == ["a", "b"]
