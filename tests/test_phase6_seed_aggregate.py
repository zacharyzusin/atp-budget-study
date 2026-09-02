"""Tests for the Phase 6 3-seed aggregator's paired-delta logic (intersection pairing)."""
import importlib.util
import json
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "phase6_seed_aggregate",
    Path(__file__).resolve().parents[1] / "scripts" / "phase6_seed_aggregate.py",
)
agg = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(agg)


def _write(run_dir: Path, cells: dict[str, int | None]):
    """cells: problem_name -> tokens_to_solve (None = unsolved)."""
    pdir = run_dir / "problems"
    pdir.mkdir(parents=True, exist_ok=True)
    for name, tts in cells.items():
        (pdir / f"{name}.json").write_text(
            json.dumps({"problem_name": name, "tokens_to_solve": tts, "solved": tts is not None})
        )


@pytest.fixture
def results(tmp_path, monkeypatch):
    monkeypatch.setattr(agg, "RESULTS", tmp_path)
    return tmp_path


def test_paired_delta_basic(results):
    # seed 0: base solves p1 only; B solves p1,p2 -> B-base = +0.5 at b=10000
    _write(results / "p6eval_d_pn_base", {"p1": 5000, "p2": None})
    _write(results / "p6eval_d_pn_B", {"p1": 5000, "p2": 9000})
    _write(results / "p6eval_d_pn_A", {"p1": 5000, "p2": None})
    d = agg._paired_deltas("d", "pn", 10000)
    assert d["B"] == [pytest.approx(0.5)]
    assert d["A"] == [pytest.approx(0.0)]


def test_pairs_over_intersection_when_arm_partial(results):
    # base has 2 problems; B (partial) has only p1 -> delta computed over {p1} only, not penalized
    # for the p2 it hasn't run yet.
    _write(results / "p6eval_d_mf_base", {"p1": 5000, "p2": None})
    _write(results / "p6eval_d_mf_B", {"p1": 5000})  # p2 not yet run
    d = agg._paired_deltas("d", "mf", 10000)
    # intersection {p1}: both solve -> delta 0 (NOT -0.5 from comparing 1/1 vs 1/2)
    assert d["B"] == [pytest.approx(0.0)]


def test_budget_threshold_respected(results):
    # p1 solved at 20000 tokens: counts at b=32000, not at b=8000
    _write(results / "p6eval_g_pn_base", {"p1": None})
    _write(results / "p6eval_g_pn_B", {"p1": 20000})
    assert agg._paired_deltas("g", "pn", 8000)["B"] == [pytest.approx(0.0)]
    assert agg._paired_deltas("g", "pn", 32000)["B"] == [pytest.approx(1.0)]


def test_multiseed_collects_per_seed(results):
    for _s, suffix in [(0, ""), (1, "_s1"), (2, "_s2")]:
        _write(results / f"p6eval_d_pn_base{suffix}", {"p1": 5000})
        _write(results / f"p6eval_d_pn_B{suffix}", {"p1": 5000})
    d = agg._paired_deltas("d", "pn", 8000)
    assert len(d["B"]) == 3  # one paired delta per seed
