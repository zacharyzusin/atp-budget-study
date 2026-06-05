"""atp.data — benchmark loaders + audited splits (Task 0.5).

`load_dataset(config)` is the one entry point the eval harness calls: it loads the configured
benchmark/split, flags known-unprovable items (and optionally drops them), tags contamination /
restricts to the novel split, applies the smoke `limit`, and returns the problems plus a
`DatasetManifest` for `run_manifest.json`. Pure-Python + login-node safe.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from atp.data.contamination import mark_contamination
from atp.data.exclusions import apply_exclusions, load_exclusions
from atp.data.manifest import DatasetManifest
from atp.data.minif2f import load_minif2f
from atp.data.problems import (
    FLAG_CONTAMINATED,
    FLAG_NOVEL,
    FLAG_UNPROVABLE,
    Problem,
)
from atp.data.proofnet import load_proofnet

if TYPE_CHECKING:
    from atp.config import ExperimentConfig

__all__ = [
    "Problem",
    "Dataset",
    "DatasetManifest",
    "load_dataset",
    "load_minif2f",
    "load_proofnet",
    "load_exclusions",
    "apply_exclusions",
    "mark_contamination",
    "FLAG_UNPROVABLE",
    "FLAG_NOVEL",
    "FLAG_CONTAMINATED",
]


@dataclass
class Dataset:
    problems: list[Problem]
    manifest: DatasetManifest


def _load_raw(config: ExperimentConfig, split: str) -> list[Problem]:
    bench = config.data.benchmark
    if bench == "minif2f":
        return load_minif2f(split, getattr(config.data, "minif2f_dir", None))
    if bench == "proofnet_sharp":
        return load_proofnet(split, getattr(config.data, "proofnet_dir", None))
    raise ValueError(f"unknown benchmark {bench!r}")


def load_dataset(
    config: ExperimentConfig,
    *,
    model_revision: str | None = None,
    novel_names: Iterable[str] = (),
) -> Dataset:
    """Load + audit the configured dataset.

    Pipeline: load split → flag exclusions (drop if `data.exclude_unprovable`) → tag contamination /
    novel → restrict to novel if `data.use_novel_split` → apply `data.limit` (smoke). Counts and
    provenance land in the manifest.
    """
    d = config.data
    novel = set(novel_names)
    if d.use_novel_split and not novel:
        raise ValueError(
            "data.use_novel_split=True but no novel_names provided — refusing to return an empty "
            "novel set silently."
        )

    # The novel split is a tagged subset of the underlying split, so always load a concrete split.
    base_split = d.split if d.split != "novel" else "valid"
    problems = _load_raw(config, base_split)
    total = len(problems)

    exclusions = load_exclusions(getattr(d, "exclusions_file", None))
    problems, unmatched = apply_exclusions(problems, exclusions)
    problems = mark_contamination(problems, novel_names=novel)

    n_unprovable = sum(1 for p in problems if p.is_unprovable)
    if d.exclude_unprovable:
        problems = [p for p in problems if not p.is_unprovable]

    if d.use_novel_split:
        problems = [p for p in problems if p.is_novel]

    if d.limit is not None:
        problems = problems[: d.limit]

    source: dict[str, str] = {}
    if problems:
        prov = problems[0].provenance
        source = {
            k: str(prov[k])
            for k in ("source_repo", "source_commit", "source_file")
            if k in prov
        }

    manifest = DatasetManifest(
        benchmark=d.benchmark,
        split=("novel" if d.use_novel_split else base_split),
        counts={
            "total_loaded": total,
            "unprovable_flagged": n_unprovable,
            "excluded": (n_unprovable if d.exclude_unprovable else 0),
            "novel": sum(1 for p in problems if p.is_novel),
            "contaminated": sum(1 for p in problems if p.is_contaminated),
            "returned": len(problems),
        },
        source=source,
        exclusions_applied=sorted(exclusions),
        exclusions_unmatched=unmatched,
        model_revision=model_revision,
        use_novel_split=d.use_novel_split,
    )
    return Dataset(problems=problems, manifest=manifest)
