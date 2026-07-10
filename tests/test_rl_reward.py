"""Reward-scoring core tests (pure; no Lean/GPU). The batch path is exercised with a fake backend
that returns scripted verdicts, so the reward -> verifier wiring is covered without a REPL."""

from __future__ import annotations

import pytest

from atp.lean.backends import RawVerification, Theorem
from atp.rl import reward as R


def test_score_verified_is_one_regardless_of_fence():
    assert R.score("ok", has_fence=True, format_bonus=0.05) == 1.0
    assert R.score("ok", has_fence=False, format_bonus=0.05) == 1.0


def test_score_failed_gets_format_bonus_only_with_fence():
    assert R.score("compile_error", has_fence=True, format_bonus=0.05) == 0.05
    assert R.score("compile_error", has_fence=False, format_bonus=0.05) == 0.0
    # A loophole (sorry/admit) is NOT verified -> never full reward, only the format bonus.
    assert R.score("loophole", has_fence=True, format_bonus=0.05) == 0.05


def test_normalize_completion_handles_text_and_chat():
    assert R.normalize_completion("hello") == "hello"
    assert R.normalize_completion(
        [{"role": "assistant", "content": "abc"}]
    ) == "abc"
    assert R.normalize_completion([{"role": "assistant", "content": "a"},
                                   {"role": "assistant", "content": "b"}]) == "ab"


def test_tally_solve_and_unsound_rates():
    t = R.SoundnessTally()
    for r in ["ok", "ok", "compile_error", "loophole", "no_goal"]:
        t.add(r)
    assert t.total == 5
    assert t.solve_rate == pytest.approx(2 / 5)
    # unsound surface = loophole + no_goal = 2/5
    assert t.unsound_rate == pytest.approx(2 / 5)
    snap = t.snapshot()
    assert snap["reward/solve_rate"] == pytest.approx(0.4)
    assert snap["reward/frac_ok"] == pytest.approx(0.4)
    assert snap["reward/unsound_rate"] == pytest.approx(0.4)


def test_tally_empty_is_zero_not_crash():
    t = R.SoundnessTally()
    assert t.solve_rate == 0.0
    assert t.unsound_rate == 0.0


def test_coerce_seq():
    assert R._coerce_seq(None, ("Mathlib",)) == ("Mathlib",)
    assert R._coerce_seq(["A", "B"], ()) == ("A", "B")
    assert R._coerce_seq("Nat", ()) == ("Nat",)
    assert R._coerce_seq("", ("d",)) == ("d",)


class _FakeBackend:
    """Returns a scripted RawVerification keyed by the proof text. A `sorry` in the proof compiles
    (success) but is caught as a loophole by the verifier's own `find_loopholes` — no need to fake
    the warning parse."""

    def verify(self, theorem: Theorem, proof: str) -> RawVerification:
        if "sorry" in proof:
            return RawVerification(output="", success=True, timed_out=False, elapsed_s=0.1)
        if "GOOD" in proof:
            return RawVerification(output="", success=True, timed_out=False, elapsed_s=0.1)
        return RawVerification(
            output="error: unknown identifier", success=False, timed_out=False, elapsed_s=0.1
        )

    def close(self) -> None:  # pragma: no cover - trivial
        pass


def _config():
    from atp.config import load_config

    return load_config("configs/deepseek_smoke.yaml")


def test_batch_reward_verified_vs_failed_vs_sorry():
    cfg = _config()
    rw = R.LeanReward(cfg, _FakeBackend, n_workers=2, format_bonus=0.05)
    try:
        completions = [
            "```lean4\ntheorem t : True := by GOOD\n```",       # verified -> 1.0
            "```lean4\ntheorem t : True := by sorry\n```",       # sorry loophole -> 0.05 (fence)
            "no fence here, just prose",                          # failed, no fence -> 0.0
        ]
        cols = {
            "name": ["t1", "t2", "t3"],
            "statement": ["theorem t : True"] * 3,
            "opens": [None, None, None],
            "imports": [None, None, None],
        }
        rewards = rw(prompts=None, completions=completions, **cols)
        assert rewards[0] == 1.0
        assert rewards[1] == pytest.approx(0.05)
        assert rewards[2] == 0.0
        # tally reflects one solve out of three, one unsound (sorry->loophole)
        assert rw.tally.total == 3
        assert rw.tally.counts["ok"] == 1
        assert rw.tally.counts["loophole"] == 1
    finally:
        rw.close()


def test_drain_metrics_aggregates_then_clears():
    cfg = _config()
    rw = R.LeanReward(cfg, _FakeBackend, n_workers=2)
    try:
        cols = {"name": ["t"], "statement": ["theorem t : True"], "opens": [None],
                "imports": [None]}
        rw(completions=["```lean4\ntheorem t : True := by GOOD\n```"], **cols)  # solve
        rw(completions=["```lean4\ntheorem t : True := by oops\n```"], **cols)  # fail
        m = rw.drain_metrics()
        assert m["reward/cum_solve_rate"] == pytest.approx(0.5)
        assert "diversity/distinct_3gram" in m
        # draining clears the per-batch buffer
        assert rw.drain_metrics() == {}
    finally:
        rw.close()


def test_reward_name_attribute_for_trl_logging():
    cfg = _config()
    rw = R.LeanReward(cfg, _FakeBackend)
    try:
        assert rw.__name__ == "lean_verified"
    finally:
        rw.close()
