"""Tests for scripts/phase8_smoke_quality.py — the check that would have caught the Leanabell
whole_proof/chat_completions incident (0/2025 solves, fence-leftover + out-of-context tactic errors)
before it burned a full battery's GPU-h. See PROGRESS.md/DECISIONS.md 2026-07-06."""
import json
import os

from scripts.phase8_smoke_quality import check_smoke_quality


def _write_agent_state(run_dir, name, attempts):
    d = os.path.join(run_dir, "agent_states")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"{name}.json"), "w") as f:
        json.dump({"attempts": attempts}, f)


def test_healthy_run_has_no_flags(tmp_path):
    run = str(tmp_path / "run")
    _write_agent_state(run, "a", [
        {"proof": "simp_all\n  norm_num", "feedback": ""},
        {"proof": "linarith", "feedback": "Failed at step 1: unsolved goals"},
    ])
    report = check_smoke_quality(run)
    assert report.n_attempts == 2
    assert report.fence_leftover_count == 0
    assert report.out_of_context_count == 0
    assert report.looks_healthy


def test_flags_fence_leftover(tmp_path):
    run = str(tmp_path / "run")
    _write_agent_state(run, "a", [
        {"proof": "```lean4\n  simp_all only [h]", "feedback": "unexpected token '`'"},
    ] * 5)
    report = check_smoke_quality(run)
    assert report.fence_leftover_count == 5
    assert report.fence_leftover_rate == 1.0
    assert not report.looks_healthy


def test_flags_out_of_context_tactic_errors(tmp_path):
    run = str(tmp_path / "run")
    _write_agent_state(run, "a", [
        {"proof": "simp_all [foo]", "feedback": "unknown namespace 'simp_all'"},
    ] * 5)
    report = check_smoke_quality(run)
    assert report.out_of_context_count == 5
    assert not report.looks_healthy


def test_mixed_run_below_threshold_looks_healthy(tmp_path):
    run = str(tmp_path / "run")
    attempts = [{"proof": "linarith", "feedback": "unsolved goals"}] * 19
    attempts.append({"proof": "```lean4\n  bad", "feedback": "unexpected token"})
    _write_agent_state(run, "a", attempts)
    report = check_smoke_quality(run)
    assert report.fence_leftover_rate == 0.05
    assert report.looks_healthy


def test_empty_run_dir_does_not_crash(tmp_path):
    run = str(tmp_path / "empty_run")
    os.makedirs(run, exist_ok=True)
    report = check_smoke_quality(run)
    assert report.n_attempts == 0
    assert report.looks_healthy
