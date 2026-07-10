"""Tests for the GRPO subset-selection IO shell (solve_counts over K-seed agent_states)."""

from __future__ import annotations

import sys
from pathlib import Path

from atp.agents.state import STOP_BUDGET, STOP_SOLVED, AgentState

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from phase6_select_subset import solve_counts  # noqa: E402


def _write(states: Path, name: str, seed: int, solved: bool):
    st = AgentState(
        theorem_name=name,
        done=True,
        stop_reason=STOP_SOLVED if solved else STOP_BUDGET,
    )
    st.save(states / f"{name}__seed{seed}.json")


def test_solve_counts_over_seeds(tmp_path):
    states = tmp_path / "agent_states"
    states.mkdir()
    # p_a solved on 2 of 3 seeds; p_b solved on 0 of 2; p_c solved on 1 of 1
    _write(states, "p_a", 0, True)
    _write(states, "p_a", 1, True)
    _write(states, "p_a", 2, False)
    _write(states, "p_b", 0, False)
    _write(states, "p_b", 1, False)
    _write(states, "p_c", 0, True)

    counts, seen = solve_counts(tmp_path)
    assert counts == {"p_a": 2, "p_b": 0, "p_c": 1}
    assert seen == {"p_a": 3, "p_b": 2, "p_c": 1}


def test_solve_counts_ignores_empty_checkpoints(tmp_path):
    states = tmp_path / "agent_states"
    states.mkdir()
    _write(states, "p_a", 0, True)
    (states / "p_a__seed1.json").write_text("")  # truncated kill -> load() returns None
    counts, seen = solve_counts(tmp_path)
    assert counts == {"p_a": 1}
    assert seen == {"p_a": 1}


def test_min_samples_filters_low_coverage(tmp_path):
    """A low-coverage all-solve problem must be droppable so the absolute-count band stays exact."""
    states = tmp_path / "agent_states"
    states.mkdir()
    # p_full: 16 seeds, 3 solves (in-band at k=16). p_partial: 2 seeds, 2 solves (would be c=2,
    # spuriously in [1,6] though it is really all-solve) -> must be dropped by min_samples>=8.
    for s in range(16):
        _write(states, "p_full", s, s < 3)
    _write(states, "p_partial", 0, True)
    _write(states, "p_partial", 1, True)
    counts, seen = solve_counts(tmp_path)
    kept = {n: c for n, c in counts.items() if seen.get(n, 0) >= 8}
    assert kept == {"p_full": 3}
