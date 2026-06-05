"""run_manifest.json — the full reproducibility record for one eval run (rule 4 / §9).

Captures the exact code, config, data, model, Lean env, hardware, and timing so a number can always
be traced back to how it was produced. Embeds the dataset manifest (which problems, from where).
"""

from __future__ import annotations

import os
import platform
import subprocess
from typing import TYPE_CHECKING, Any

from atp.config import config_hash, dump_config

if TYPE_CHECKING:
    from atp.config import ExperimentConfig
    from atp.data.manifest import DatasetManifest

# Keys every manifest must carry (asserted by test_manifest_completeness).
REQUIRED_KEYS = (
    "git_sha",
    "config_hash",
    "config",
    "seeds",
    "budgets",
    "model",
    "lean",
    "dataset",
    "host",
    "started_at",
    "finished_at",
)


def _git_sha(project_root: str) -> str:
    try:
        res = subprocess.run(
            ["git", "-C", project_root, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10, check=True,
        )
        return res.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return "unknown"


def build_run_manifest(
    config: ExperimentConfig,
    dataset_manifest: DatasetManifest,
    *,
    seeds: list[int],
    budgets: list[int],
    started_at: str,
    finished_at: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "git_sha": _git_sha(config.project.root),
        "config_hash": config_hash(config),
        "config": dump_config(config),
        "seeds": seeds,
        "budgets": budgets,
        "model": {
            "name": config.model.name,
            "hf_repo": config.model.hf_repo,
            "revision": config.model.revision,
        },
        "lean": {
            "toolchain": config.lean.toolchain,
            "mathlib_repo": config.lean.mathlib_repo,
            "mathlib_commit": config.lean.mathlib_commit,
        },
        "dataset": dataset_manifest.to_dict(),
        "host": {
            "hostname": platform.node(),
            "platform": platform.platform(),
            "slurm_job_id": os.environ.get("SLURM_JOB_ID", ""),
            "gpu": os.environ.get("ATP_GPU_TYPE", os.environ.get("SLURM_JOB_GPUS", "")),
        },
        "started_at": started_at,
        "finished_at": finished_at,
        **(extra or {}),
    }
