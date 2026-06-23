"""Tests for the Phase 6 continuation probe core (Lean-free, GPU-free: generate/verify injected)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "phase6_continuation_probe.py"
_spec = importlib.util.spec_from_file_location("phase6_continuation_probe", _SCRIPT)
probe = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = probe  # dataclass decorator needs the module registered during exec
_spec.loader.exec_module(probe)

PROOF = """theorem lw (a b : ℝ) (h : a = b) : b = a := by
  have h1 : a - b = 0 := by
    rw [h]
    ring
  linarith [h1]"""


class _Thm:
    def __init__(self, name, statement):
        self.name = name
        self.statement = statement


def test_recompute_cont_prefers_stored_fields():
    row = {"cont_prefix": "  intro x", "cont_target": "  exact x", "proof": "ignored"}
    assert probe.recompute_cont(row) == ("  intro x", "  exact x")


def test_recompute_cont_rederives_from_proof_by_matching_candidate():
    # a top-level cut keeping the substantive `linarith [h1]`
    row = {"proof": PROOF, "depth": 0, "k": 1, "n_groups": 2, "closing": "linarith [h1]"}
    cp, ct = probe.recompute_cont(row)
    assert cp + "\n" + ct == "\n".join(PROOF.split("\n")[1:])  # body reconstructs
    assert "linarith [h1]" in ct


def test_recompute_cont_returns_none_when_no_unique_match():
    row = {"proof": PROOF, "depth": 0, "k": 99, "n_groups": 2, "closing": "nope"}
    assert probe.recompute_cont(row) is None


def test_classify_hard_when_sample_conclusively_fails():
    # finished naturally (not truncated) and didn't close => a conclusive failure => HARD
    samples = [probe.SampleOutcome(parseable=True, whole_closed=False, spliced_closed=False,
                                   finished=True)]
    out = probe.classify_samples(samples)
    assert out["is_hard"] is True and out["indeterminate"] is False and out["n_parseable"] == 1


def test_classify_indeterminate_when_only_truncated_failures():
    # the base ran out of budget re-emitting a long proof (finish=length) => NOT hard, indeterminate
    samples = [probe.SampleOutcome(parseable=False, whole_closed=False, spliced_closed=False,
                                   finished=False)]
    out = probe.classify_samples(samples)
    assert out["is_hard"] is False and out["indeterminate"] is True


def test_classify_not_hard_when_any_sample_closes_either_way():
    samples = [
        probe.SampleOutcome(parseable=True, whole_closed=False, spliced_closed=False,
                            finished=True),
        probe.SampleOutcome(parseable=True, whole_closed=False, spliced_closed=True),  # splice ok
    ]
    out = probe.classify_samples(samples)
    assert out["is_hard"] is False and out["indeterminate"] is False


def _deps(*, closes: bool, parseable: bool = True, via_splice: bool = False, finish: str = "stop"):
    # injected callables emulate the model + verifier
    def verify(thm, proof):
        if via_splice:
            # only the SPLICED proof verifies: it has the prefix ("intro x") + bare output ("foo")
            return closes and ("intro x" in proof and "foo" in proof)
        return closes
    return probe.ProbeDeps(
        render_continuation=lambda thm, prefix: f"PROMPT::{prefix}",
        extract_proof=lambda thm, text: text,
        generate=lambda prompt, seed: (
            ("foo" if via_splice else "theorem t := by exact h"), finish),
        verify=verify,
        has_fence=lambda t: parseable,
        build_proof_from_prefix=lambda thm, cp, cont: f"{thm.statement} := by\n{cp}\n{cont}",
    )


def test_probe_pairs_marks_hard_when_base_fails():
    rows = [{"name": "t", "cont_prefix": "  intro x", "cont_target": "  exact x", "depth": 1}]
    thms = {"t": _Thm("t", "theorem t : P")}
    recs = probe.probe_pairs(rows, thms, _deps(closes=False), samples=1)
    assert recs[0]["is_hard"] is True and recs[0]["skipped"] is False


def test_probe_pairs_marks_indeterminate_when_truncated():
    rows = [{"name": "t", "cont_prefix": "  intro x", "cont_target": "  exact x"}]
    thms = {"t": _Thm("t", "theorem t : P")}
    recs = probe.probe_pairs(rows, thms, _deps(closes=False, finish="length"), samples=1)
    assert recs[0]["is_hard"] is False and recs[0]["indeterminate"] is True


def test_probe_pairs_marks_closable_when_base_closes_whole():
    rows = [{"name": "t", "cont_prefix": "  intro x", "cont_target": "  exact x"}]
    thms = {"t": _Thm("t", "theorem t : P")}
    recs = probe.probe_pairs(rows, thms, _deps(closes=True), samples=1)
    assert recs[0]["is_hard"] is False


def test_probe_pairs_splice_path_counts_as_closed():
    # base emits bare tactics "foo"; only the spliced (prefix+cont) proof verifies
    rows = [{"name": "t", "cont_prefix": "  intro x", "cont_target": "  exact x"}]
    thms = {"t": _Thm("t", "theorem t : P")}
    recs = probe.probe_pairs(rows, thms, _deps(closes=True, via_splice=True), samples=1)
    assert recs[0]["is_hard"] is False and recs[0]["n_spliced_closed"] == 1


def test_probe_pairs_skips_unknown_theorem_or_missing_cont():
    rows = [{"name": "missing", "cont_prefix": "x", "cont_target": "y"}]
    recs = probe.probe_pairs(rows, {}, _deps(closes=True), samples=1)
    assert recs[0]["skipped"] is True and recs[0]["reason"] == "no_theorem"


def test_summarize_counts_hard_indeterminate_and_parseable():
    records = [
        {"skipped": False, "is_hard": True, "indeterminate": False, "n_samples": 2,
         "n_parseable": 2, "n_finished": 2},
        {"skipped": False, "is_hard": False, "indeterminate": True, "n_samples": 2,
         "n_parseable": 1, "n_finished": 0},
        {"skipped": False, "is_hard": False, "indeterminate": False, "n_samples": 2,
         "n_parseable": 2, "n_finished": 2},
        {"skipped": True, "reason": "no_theorem"},
    ]
    s = probe.summarize(records)
    assert s["n_probed"] == 3 and s["n_hard"] == 1 and s["n_indeterminate"] == 1
    assert s["n_base_closes"] == 1 and s["n_skipped"] == 1
