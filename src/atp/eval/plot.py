"""pass@B curve plot. matplotlib is imported lazily so `import atp.eval` stays cheap."""

from __future__ import annotations

from pathlib import Path

from atp.eval.metrics import PassAtB


def plot_pass_at_b(
    curve: list[PassAtB], out_path: str | Path, *, title: str | None = None
) -> Path:
    """Save a pass@B curve (mean ± std error bars, log-scale budget axis) to `out_path`."""
    import matplotlib

    matplotlib.use("Agg")  # headless (compute node)
    import matplotlib.pyplot as plt

    xs = [p.budget for p in curve]
    ys = [p.mean for p in curve]
    es = [p.std for p in curve]

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.errorbar(xs, ys, yerr=es, marker="o", capsize=3)
    if len(xs) > 1:
        ax.set_xscale("log")
    ax.set_xlabel("per-problem budget B (generation tokens)")
    ax.set_ylabel("pass@B")
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)
    ax.set_title(title or "pass@B")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return out_path
