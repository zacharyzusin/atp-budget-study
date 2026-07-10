"""Phase 8 — re-verify already-collected completions against a FIXED backend, no new generation.

Core logic (`reverify_cell`) is pure and testable with a scripted verifier: given the attempts
already recorded for a cell (in order) and a theorem, re-run verification on each `proof` text in
turn and report the first newly-solved attempt (or none). This is what lets the `_build_source`/
`_build_repl_source` fix (PROGRESS.md/DECISIONS.md 2026-07-06) be applied to the ~150+ GPU-h of
already-collected p8battery2_* completions WITHOUT any new vLLM generation.
"""
import json
import os
from dataclasses import dataclass

from scripts.phase8_reverify import reverify_cell, run_reverify


@dataclass
class _FakeVerifyResult:
    ok: bool


class _FakeVerifier:
    """ok_for: set of proof strings that verify as solved under the (fixed) backend."""

    def __init__(self, ok_for):
        self.ok_for = ok_for
        self.calls = []

    def verify(self, theorem, proof):
        self.calls.append(proof)
        return _FakeVerifyResult(ok=proof in self.ok_for)


def test_reverify_cell_finds_first_newly_solved_attempt():
    attempts = [
        {"proof": "bad_1", "completion_tokens": 100},
        {"proof": "actually_fine", "completion_tokens": 250},
        {"proof": "bad_2", "completion_tokens": 50},
    ]
    verifier = _FakeVerifier(ok_for={"actually_fine"})
    result = reverify_cell(attempts, theorem=None, verifier=verifier)
    assert result.solved is True
    assert result.tokens_to_solve == 100 + 250  # cumulative up to AND including the solving attempt
    assert result.solving_attempt_index == 1


def test_reverify_cell_reports_unsolved_when_nothing_verifies():
    attempts = [
        {"proof": "bad_1", "completion_tokens": 100},
        {"proof": "bad_2", "completion_tokens": 50},
    ]
    verifier = _FakeVerifier(ok_for=set())
    result = reverify_cell(attempts, theorem=None, verifier=verifier)
    assert result.solved is False
    assert result.tokens_to_solve is None
    assert result.solving_attempt_index is None


def test_reverify_cell_stops_at_first_solve_does_not_check_later_attempts():
    attempts = [
        {"proof": "good_early", "completion_tokens": 10},
        {"proof": "good_late", "completion_tokens": 20},
    ]
    verifier = _FakeVerifier(ok_for={"good_early", "good_late"})
    result = reverify_cell(attempts, theorem=None, verifier=verifier)
    assert result.solved is True
    assert result.solving_attempt_index == 0
    assert result.tokens_to_solve == 10
    assert verifier.calls == ["good_early"]  # never even checked "good_late"


def test_reverify_cell_empty_attempts_is_unsolved():
    result = reverify_cell([], theorem=None, verifier=_FakeVerifier(ok_for=set()))
    assert result.solved is False
    assert result.tokens_to_solve is None


def _write_agent_state(states_dir, name, seed, attempts):
    os.makedirs(states_dir, exist_ok=True)
    with open(os.path.join(states_dir, f"{name}__seed{seed}.json"), "w") as f:
        json.dump({"attempts": attempts}, f)


def test_run_reverify_resumes_by_skipping_already_written_cells(tmp_path):
    """CLAUDE.md rule 3: sweeps must skip already-completed cells on resume — this job hit a 3-hour
    Slurm TIMEOUT mid-pass for 3 of the 10 configs (2026-07-06); resubmitting must not silently redo
    (and re-spend CPU time on) cells the first attempt already finished."""
    states_dir = str(tmp_path / "agent_states")
    out_dir = str(tmp_path / "problems")
    _write_agent_state(states_dir, "a", 0, [{"proof": "good", "completion_tokens": 5}])
    _write_agent_state(states_dir, "b", 0, [{"proof": "bad", "completion_tokens": 5}])
    theorem_by_name = {"a": "THM_A", "b": "THM_B"}  # fake theorem objects (verifier is scripted)
    verifier = _FakeVerifier(ok_for={"good"})

    import glob
    files = sorted(glob.glob(os.path.join(states_dir, "*.json")))
    n_total, n_solved, n_skipped = run_reverify(files, out_dir, theorem_by_name, verifier)
    assert n_total == 2 and n_solved == 1 and n_skipped == 0
    assert verifier.calls == ["good", "bad"]

    # simulate a resubmit after a timeout: same inputs, a FRESH verifier (would re-count calls if
    # not skipped) — everything must be skipped, no re-verification work done
    verifier2 = _FakeVerifier(ok_for={"good"})
    n_total2, n_solved2, n_skipped2 = run_reverify(files, out_dir, theorem_by_name, verifier2)
    assert n_total2 == 0 and n_skipped2 == 2
    assert verifier2.calls == []  # resumed run touched Lean zero times


def test_run_reverify_skips_empty_or_corrupt_checkpoints_instead_of_crashing(tmp_path):
    """CRITICAL REGRESSION (found live 2026-07-09/10 — see PROGRESS.md/DECISIONS.md that date): the
    harness-sanity control check on `results/baseline` (732 pre-existing agent_state files, some from
    much earlier phases) crashed the WHOLE re-verify pass on the first empty/corrupt checkpoint file
    (`json.JSONDecodeError`), losing all already-computed progress in that process and blocking the
    coordinator's blocking harness-sanity gate. The production eval loop already tolerates this
    (`atp.agents.state`, "Resume robustness: tolerate empty/corrupt checkpoints" — a real, previously-
    fixed class of issue in this exact repo); the re-verify tool must have the same tolerance: skip
    and count the bad file, keep going, never crash the batch.
    """
    states_dir = str(tmp_path / "agent_states")
    out_dir = str(tmp_path / "problems")
    os.makedirs(states_dir, exist_ok=True)
    _write_agent_state(states_dir, "a", 0, [{"proof": "good", "completion_tokens": 5}])
    # a corrupt/empty checkpoint, same failure mode observed live
    with open(os.path.join(states_dir, "b__seed0.json"), "w") as f:
        f.write("")
    _write_agent_state(states_dir, "c", 0, [{"proof": "bad", "completion_tokens": 5}])

    theorem_by_name = {"a": "THM_A", "b": "THM_B", "c": "THM_C"}
    verifier = _FakeVerifier(ok_for={"good"})

    import glob
    files = sorted(glob.glob(os.path.join(states_dir, "*.json")))
    n_total, n_solved, n_skipped = run_reverify(files, out_dir, theorem_by_name, verifier)
    # "a" and "c" must still be processed; "b" (corrupt) must be skipped, not crash the batch
    assert n_total == 2 and n_solved == 1
    assert verifier.calls == ["good", "bad"]
