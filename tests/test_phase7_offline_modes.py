"""Phase 7 Track 1 — offline Modes 1/2 trapped pass@B, free reconstruction from baseline runs.

No GPU/Lean: Mode 2 (whole-proof + error-feedback, already the committed baseline) is the existing
per-cell `ProblemResult`, restricted to the trapped-core problem names; Mode 1 (no-feedback) is
recovered from the same run's `agent_states` via `propose_only_tokens_to_solve`
(tests/test_stepwise.py).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from atp.eval.records import ProblemResult

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "phase7_offline_modes.py"
_spec = importlib.util.spec_from_file_location("phase7_offline_modes", _SCRIPT)
offline = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = offline
_spec.loader.exec_module(offline)
mode1_results = offline.mode1_results
restrict_to_trapped = offline.restrict_to_trapped


def _result(name: str, seed: int, solved: bool, tokens_to_solve: int | None) -> ProblemResult:
    return ProblemResult(
        problem_name=name, seed=seed, budget=128_000, solved=solved, stop_reason="",
        tokens_to_solve=tokens_to_solve, tokens_spent=tokens_to_solve or 128_000, n_attempts=1,
    )


def test_restrict_to_trapped_keeps_only_named_problems():
    results = [_result("A", 0, True, 100), _result("B", 0, False, None)]
    kept = restrict_to_trapped(results, trapped_names={"A"})
    assert [r.problem_name for r in kept] == ["A"]


def test_mode1_results_reconstructs_from_agent_states_attempts():
    # One trapped cell whose Mode-2 (logged) run solved via a refine attempt at token 900, but whose
    # Mode-1 (propose-only) reconstruction never solves (the closing depended on error feedback).
    cell_trace = {
        "problem_name": "A", "seed": 0, "solved": True, "tokens_to_solve": 900,
        "attempts": [
            {"kind": "propose", "completion_tokens": 500, "ok": False},
            {"kind": "refine", "completion_tokens": 400, "ok": True},
        ],
    }
    out = mode1_results([cell_trace])
    assert len(out) == 1
    assert out[0].problem_name == "A"
    assert out[0].seed == 0
    assert out[0].solved is False
    assert out[0].tokens_to_solve is None
