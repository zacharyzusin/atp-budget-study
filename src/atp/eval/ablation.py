"""Expand a Phase 1 sweep config into one-factor-at-a-time ablation cells (Task 1.4).

`phase1_ablation.yaml` carries a `sweep` block — a `baseline` (the reference component setup) and
`axes` (each axis → a list of variant overrides). This module turns that into concrete, validated
`ExperimentConfig` cells the existing eval path (`run_eval`) runs unchanged:

  * the **baseline** cell = base config deep-merged with `sweep.baseline`;
  * for each axis, each variant cell = the baseline cell deep-merged with that variant.

That layering is **OFAT** (one factor at a time): every variant differs from the baseline in *only*
its own axis, so a `pass@B` delta is attributable to that axis. A Slurm array maps array-id → cell;
each cell runs the full problems × seeds grid into its own `results/<run>/<cell>/` dir.

Pure config algebra — no GPU/Lean — so the whole expansion is unit-tested on the login node, and
malformed overrides fail here (re-validation) before any compute is spent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from atp.config import (
    ExperimentConfig,
    _deep_merge,
    config_hash,
    dump_config,
)

BASELINE = "baseline"


@dataclass(frozen=True)
class AblationCell:
    """One ablation run: a name, the axis it varies ("baseline" for the reference), its config."""

    name: str
    axis: str
    config: ExperimentConfig
    override: dict[str, Any]  # the variant override applied to the baseline (for the manifest)


def expand_ablation(config: ExperimentConfig) -> list[AblationCell]:
    """Expand a config's `sweep` block into the baseline + per-axis OFAT cells.

    Raises if the config has no `sweep` block, or if any cell fails schema validation.
    """
    sweep = config.sweep
    if not sweep:
        raise ValueError("config has no `sweep` block to expand (not an ablation config)")

    base = dump_config(config)
    base.pop("sweep", None)  # cells are plain experiment configs, not sweep configs

    baseline_override = sweep.get(BASELINE) or {}
    base_cell = _deep_merge(base, baseline_override)
    base_config = _validate(base_cell, BASELINE)
    cells = [AblationCell(BASELINE, BASELINE, base_config, baseline_override)]

    # Dedup by config-hash: each axis's "control" variant is identical to the baseline, so without
    # this the baseline grid (problems × seeds) would be run several times over. The first cell with
    # a given config wins (the baseline), so an axis only contributes its *distinct* variants.
    names = {BASELINE}
    seen_hashes = {config_hash(base_config)}
    for axis, variants in (sweep.get("axes") or {}).items():
        for i, variant in enumerate(variants):
            cfg = _validate(_deep_merge(base_cell, variant or {}), f"{axis}__{i}")
            h = config_hash(cfg)
            if h in seen_hashes:
                continue  # identical to an already-included cell (usually the baseline)
            seen_hashes.add(h)
            name = f"{axis}__{i}"
            if name in names:
                raise ValueError(f"duplicate ablation cell name {name!r}")
            names.add(name)
            cells.append(AblationCell(name, axis, cfg, variant or {}))
    return cells


def _validate(cell_dict: dict[str, Any], name: str) -> ExperimentConfig:
    try:
        return ExperimentConfig.model_validate(cell_dict)
    except Exception as exc:  # noqa: BLE001 — re-raise with the offending cell name attached
        raise ValueError(f"ablation cell {name!r} is invalid: {exc}") from exc


def validate_cells(cells: list[AblationCell]) -> None:
    """Pre-flight: build each cell's components so semantic errors (e.g. retrieval bm25 without a
    corpus, unknown skeleton schedule) surface on the login node, not 6h into a Slurm sweep."""
    from atp.agents.components import build_components

    for cell in cells:
        # Flag a generation mode with no agent yet (e.g. bfs) before the sweep, not mid-run.
        if cell.config.agent.mode != "whole_proof":
            raise ValueError(
                f"ablation cell {cell.name!r} uses agent.mode={cell.config.agent.mode!r}, which is "
                "not implemented yet (BFS is deferred — needs the REPL stepping layer)"
            )
        try:
            build_components(cell.config)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"ablation cell {cell.name!r} components invalid: {exc}") from exc


def ablation_manifest(cells: list[AblationCell]) -> list[dict[str, Any]]:
    """A serializable name→(axis, override, config_hash) map for analysis to join results back."""
    return [
        {
            "name": cell.name,
            "axis": cell.axis,
            "override": cell.override,
            "config_hash": config_hash(cell.config),
        }
        for cell in cells
    ]
