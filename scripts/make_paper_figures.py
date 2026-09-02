#!/usr/bin/env python3
"""Generate the paper's figures from data already on disk. CPU-only, no GPU, no new generation.

Figures (written to paper/floor/figs/):
  fig_attempts.pdf  - attempts-per-budget / effective independent samples (the pass@B-vs-pass@N gap)
  fig_passb.pdf     - the pass@B curves, both models x both benchmarks
  fig_stepc.pdf     - Step C manipulation check (diversity) vs outcome (solves)
  fig_frontier.pdf  - the allocation efficiency frontier

Palette: slots 1-3 of the validated categorical palette (blue/orange/aqua). Validated with the
dataviz skill's checker on the all-pairs list in light mode: CVD dE 9.2 (deutan) worst pair,
normal-vision dE 24.0, lightness/chroma/contrast pass -- except aqua at 2.74:1 contrast, which
carries the relief rule, so every aqua series is also direct-labeled.

Usage: python scripts/make_paper_figures.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "paper" / "floor" / "figs"

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#8a8985"
BUDGETS = (2000, 8000, 32000, 128000)
XLAB = ["2k", "8k", "32k", "128k"]


def _style(ax) -> None:
    """Recessive grid and axes; no top/right spines."""
    ax.grid(True, color="#e6e5e1", lw=0.6, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(MUTED)
        ax.spines[s].set_linewidth(0.8)
    ax.tick_params(colors=INK2, labelsize=8, length=3, width=0.8)


def fig_passb() -> None:
    """pass@B, one panel per benchmark.

    The two differ ~5x in absolute scale; a shared y-axis would flatten the OOD curve.
    """
    rep = json.loads((ROOT / "results" / "audit" / "HEARTBEAT_CORRECTED_CURVES.json").read_text())
    panels = [
        (
            "miniF2F (in-distribution)",
            [("Goedel", "baseline"), ("DeepSeek", "deepseek_minif2f_baseline")],
        ),
        (
            "ProofNet# (out-of-distribution)",
            [("Goedel", "proofnet_baseline"), ("DeepSeek", "deepseek_proofnet_baseline")],
        ),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.9))
    for ax, (title, series) in zip(axes, panels, strict=True):
        for color, (label, run) in zip((BLUE, ORANGE), series, strict=True):
            ys = [rep[run]["after"][str(b)][0] * 100 for b in BUDGETS]
            es = [rep[run]["after"][str(b)][1] * 100 for b in BUDGETS]
            ax.errorbar(
                range(len(BUDGETS)), ys, yerr=es, marker="o", ms=4.5, lw=2.0, capsize=2.5,
                color=color, label=label, zorder=3, elinewidth=1.0,
                markeredgecolor="white", markeredgewidth=0.8,
            )
            ax.annotate(  # direct label at the right end; nudged apart where the ends are close
                label, (len(BUDGETS) - 1, ys[-1]), textcoords="offset points",
                xytext=(6, 4 if label == "Goedel" else -8),
                color=color, fontsize=8, fontweight="bold", va="center",
            )
        _style(ax)
        ax.set_title(title, fontsize=9, color=INK, pad=6)
        ax.set_xticks(range(len(BUDGETS)))
        ax.set_xticklabels(XLAB)
        ax.set_xlabel("token budget $B$", fontsize=8.5, color=INK2)
        ax.set_xlim(-0.25, len(BUDGETS) - 0.25 + 0.9)
        ax.set_ylim(0, None)
    axes[0].set_ylabel("pass@$B$ (%)", fontsize=8.5, color=INK2)
    axes[0].legend(frameon=False, fontsize=7.5, labelcolor=INK2, loc="lower right")
    fig.tight_layout()
    fig.savefig(OUT / "fig_passb.pdf", bbox_inches="tight")
    plt.close(fig)
    print("wrote fig_passb.pdf")


def _parse_attempts_table() -> dict[str, dict[int, float]]:
    """Mean propose-attempt count per budget, per cell, from the committed Phase 0 table."""
    txt = (ROOT / "results" / "phase0" / "ATTEMPTS_PER_BUDGET_TABLE.md").read_text()
    out: dict[str, dict[int, float]] = {}
    cur = None
    for line in txt.split("\n"):
        m = re.match(r"^## (\S+)", line)
        if m:
            cur = m.group(1)
            out[cur] = {}
            continue
        m = re.match(r"^\| (\d+) \| \d+ \| ([0-9.]+)/", line)
        if m and cur:
            out[cur][int(m.group(1))] = float(m.group(2))
    return {k: v for k, v in out.items() if v}


def fig_attempts() -> None:
    """The methods finding: how many INDEPENDENT proposals a budget actually buys."""
    data = _parse_attempts_table()
    labels = {
        "goedel_minif2f": ("Goedel x miniF2F", BLUE, "-"),
        "deepseek_minif2f": ("DeepSeek x miniF2F", ORANGE, "-"),
        "goedel_proofnet": ("Goedel x ProofNet#", BLUE, "--"),
        "deepseek_proofnet": ("DeepSeek x ProofNet#", ORANGE, "--"),
    }
    fig, ax = plt.subplots(figsize=(4.6, 3.0))
    for key, (label, color, ls) in labels.items():
        if key not in data:
            print(f"  (skip {key}: not in table)")
            continue
        ys = [data[key].get(b, float("nan")) for b in BUDGETS]
        ax.plot(range(len(BUDGETS)), ys, marker="o", ms=4.5, lw=2.0, ls=ls, color=color,
                label=label, zorder=3, markeredgecolor="white", markeredgewidth=0.8)
    ax.axhline(1.0, color=MUTED, lw=1.0, ls=":", zorder=2)
    ax.annotate("one complete proposal", (0.02, 1.0), xycoords=("axes fraction", "data"),
                textcoords="offset points", xytext=(0, 4), fontsize=7.5, color=INK2)
    _style(ax)
    ax.set_xticks(range(len(BUDGETS)))
    ax.set_xticklabels(XLAB)
    ax.set_xlabel("token budget $B$", fontsize=8.5, color=INK2)
    ax.set_ylabel("mean completed propose attempts", fontsize=8.5, color=INK2)
    ax.legend(frameon=False, fontsize=7.5, labelcolor=INK2, loc="upper left")
    fig.tight_layout()
    fig.savefig(OUT / "fig_attempts.pdf", bbox_inches="tight")
    plt.close(fig)
    print("wrote fig_attempts.pdf")


# Step C, from PROGRESS.md 2026-06-19 / results/phase2 (scripts/stepc_readout.py output).
# ARMS order in stepc_readout.py fixes the cell mapping.
STEPC = [
    ("Goedel\nminiF2F", 44, 1.2),
    ("Goedel\nProofNet#", 42, 0.7),
    ("DeepSeek\nminiF2F", 68, 0.0),
    ("DeepSeek\nProofNet#", 70, 0.0),
]


def fig_stepc() -> None:
    """Manipulation check fired; outcome did not move. The two panels are the whole argument."""
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(6.4, 2.8))
    xs = range(len(STEPC))
    names = [s[0] for s in STEPC]

    a1.bar(xs, [s[1] for s in STEPC], color=BLUE, width=0.6, zorder=3)
    for x, s in zip(xs, STEPC, strict=True):
        a1.annotate(f"+{s[1]}%", (x, s[1]), ha="center", va="bottom",
                    textcoords="offset points", xytext=(0, 2), fontsize=8, color=INK)
    a1.set_ylabel("distinct openings per attempt\n(change vs. baseline)", fontsize=8.5, color=INK2)
    a1.set_title("Manipulation check: fired", fontsize=9, color=INK, pad=6)
    a1.set_ylim(0, 85)

    a2.bar(xs, [s[2] for s in STEPC], color=ORANGE, width=0.6, zorder=3)
    for x, s in zip(xs, STEPC, strict=True):
        a2.annotate(f"{s[2]:.1f}%", (x, s[2]), ha="center", va="bottom",
                    textcoords="offset points", xytext=(0, 2), fontsize=8, color=INK)
    a2.set_ylabel("trapped pass@32k (%)", fontsize=8.5, color=INK2)
    a2.set_title("Outcome: flat", fontsize=9, color=INK, pad=6)
    a2.set_ylim(0, 85)  # same scale as the left panel -- the point is the contrast

    for ax in (a1, a2):
        _style(ax)
        ax.set_xticks(list(xs))
        ax.set_xticklabels(names, fontsize=7.5)
    fig.tight_layout()
    fig.savefig(OUT / "fig_stepc.pdf", bbox_inches="tight")
    plt.close(fig)
    print("wrote fig_stepc.pdf")


def fig_frontier() -> None:
    """Compute saved vs. accuracy target, realizable/oracle, for the cell the paper headlines."""
    rows = json.loads((ROOT / "results" / "phase4" / "frontier.json").read_text())
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.9))
    cells = [("goedel", "proofnet_sharp", "Goedel x ProofNet#"),
             ("deepseek", "proofnet_sharp", "DeepSeek x ProofNet#")]
    for ax, (model, bench, title) in zip(axes, cells, strict=True):
        r = next(x for x in rows if x["model"] == model and x["benchmark"] == bench)
        pts = r["efficiency_at_matched_accuracy"]
        xs = [p["accuracy_target_frac"] * 100 for p in pts]
        for color, key, label in (
            (BLUE, "realizable_saved_frac", "realizable policy"),
            (AQUA, "oracle_saved_frac", "oracle (upper bound)"),
        ):
            ys = [p[key] * 100 for p in pts]
            ax.plot(xs, ys, marker="o", ms=4.5, lw=2.0, color=color, zorder=3, label=label,
                    markeredgecolor="white", markeredgewidth=0.8)
        ax.axhline(0, color=MUTED, lw=1.0, ls=":", zorder=2)
        _style(ax)
        ax.set_title(title, fontsize=9, color=INK, pad=6)
        ax.set_xlabel("accuracy target (% of full-budget solves)", fontsize=8.5, color=INK2)
        # aqua sits below 3:1 on white, so the relief rule applies: legend + value labels
        ax.legend(frameon=False, fontsize=7.5, labelcolor=INK2, loc="center left")
    axes[0].set_ylabel("compute saved (%)", fontsize=8.5, color=INK2)
    fig.tight_layout()
    fig.savefig(OUT / "fig_frontier.pdf", bbox_inches="tight")
    plt.close(fig)
    print("wrote fig_frontier.pdf")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig_attempts()
    fig_passb()
    fig_stepc()
    fig_frontier()
    print(f"figures in {OUT}")


if __name__ == "__main__":
    main()
