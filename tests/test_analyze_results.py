"""Tests for scripts/analyze_results.py — Lean/GPU-free, synthetic ProblemResults on disk."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from atp.eval.records import ProblemResult

_SPEC = importlib.util.spec_from_file_location(
    "analyze_results", Path(__file__).resolve().parents[1] / "scripts" / "analyze_results.py"
)
ar = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(ar)


def _cell(name: str, seed: int, tts: int | None, budget: int = 128000) -> ProblemResult:
    """A ProblemResult solved at `tts` tokens (None = unsolved)."""
    return ProblemResult(
        problem_name=name,
        seed=seed,
        budget=budget,
        solved=tts is not None,
        stop_reason="solved" if tts is not None else "budget_exhausted",
        tokens_to_solve=tts,
        tokens_spent=tts if tts is not None else budget,
        n_attempts=1,
    )


def _write(run_dir: Path, cells: list[ProblemResult]) -> Path:
    probs = run_dir / "problems"
    probs.mkdir(parents=True)
    for c in cells:
        c.save(probs / f"{c.problem_name}__seed{c.seed}.json")
    return run_dir


def test_load_dir_reads_all_cells(tmp_path):
    rd = _write(tmp_path / "run", [_cell("a", 0, 1000), _cell("b", 0, None)])
    loaded = ar.load_dir(rd)
    assert len(loaded) == 2
    assert {r.problem_name for r in loaded} == {"a", "b"}


def test_paired_flips_counts_gains_and_losses(tmp_path):
    # base solves {a} ; variant solves {b}  -> 1 gain (b), 1 loss (a), net 0 (noise-like).
    base = _write(tmp_path / "base", [_cell("a", 0, 1000), _cell("b", 0, None)])
    var = _write(tmp_path / "var", [_cell("a", 0, None), _cell("b", 0, 1000)])
    f = ar.paired_flips(ar.load_dir(base), ar.load_dir(var), budget=8000)
    assert f["n_pairs"] == 2
    assert f["gains"] == 1
    assert f["losses"] == 1
    assert f["net"] == 0
    assert f["base_solved"] == 1 and f["variant_solved"] == 1


def test_paired_flips_respects_budget_threshold(tmp_path):
    # variant solves `a` only at 50k; at B=8000 that does NOT count -> no gain.
    base = _write(tmp_path / "base", [_cell("a", 0, None)])
    var = _write(tmp_path / "var", [_cell("a", 0, 50000)])
    assert ar.paired_flips(ar.load_dir(base), ar.load_dir(var), budget=8000)["gains"] == 0
    assert ar.paired_flips(ar.load_dir(base), ar.load_dir(var), budget=128000)["gains"] == 1


def test_paired_flips_only_pairs_present_in_both(tmp_path):
    base = _write(tmp_path / "base", [_cell("a", 0, 1000), _cell("b", 0, 1000)])
    var = _write(tmp_path / "var", [_cell("a", 0, 1000)])  # missing b
    assert ar.paired_flips(ar.load_dir(base), ar.load_dir(var), budget=8000)["n_pairs"] == 1


def test_curve_and_compare_smoke(tmp_path, capsys):
    rd = _write(tmp_path / "run", [_cell("a", 0, 1000), _cell("b", 0, 50000)])
    ar.main(["curve", str(rd), "--budgets", "2000", "128000"])
    out = capsys.readouterr().out
    assert "pass@B" in out and "2000" in out and "128000" in out
    ar.main(["compare", str(rd), str(rd), "--budgets", "2000"])
    assert "Δ(B-A)" in capsys.readouterr().out
