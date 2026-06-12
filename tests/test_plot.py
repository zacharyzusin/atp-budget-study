"""Plot smoke tests — skip if matplotlib is absent so the fast suite stays login-node-safe."""

from __future__ import annotations

import pytest

from atp.eval.metrics import PassAtB

pytest.importorskip("matplotlib")

from atp.eval.plot import plot_pass_at_b, plot_pass_at_b_overlay  # noqa: E402


def _curve(scale: float) -> list[PassAtB]:
    return [
        PassAtB(budget=b, mean=scale * f, std=0.02, n_seeds=3, n_problems=10)
        for b, f in [(2000, 0.3), (8000, 0.6), (32000, 0.7)]
    ]


def test_plot_pass_at_b_writes_png(tmp_path):
    out = plot_pass_at_b(_curve(1.0), tmp_path / "c.png", title="t")
    assert out.exists() and out.stat().st_size > 0


def test_plot_overlay_writes_png(tmp_path):
    out = plot_pass_at_b_overlay(
        {"miniF2F": _curve(1.0), "ProofNet#": _curve(0.3)},
        tmp_path / "overlay.png",
        title="pass@B by benchmark",
    )
    assert out.exists() and out.stat().st_size > 0
