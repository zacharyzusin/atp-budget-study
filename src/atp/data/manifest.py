"""Dataset manifest: the audit record of exactly which problems an eval ran on, and from where.

Written into each run's `run_manifest.json` (rule 4 / §9): benchmark + split, counts
(total/included/excluded/novel/contaminated), source repo+commit, the exclusion names applied (and
any that didn't match), the base-model revision, and a timestamp. Reproducibility needs this exact.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class DatasetManifest:
    benchmark: str
    split: str
    counts: dict[str, int] = field(default_factory=dict)
    source: dict[str, str] = field(default_factory=dict)
    exclusions_applied: list[str] = field(default_factory=list)
    exclusions_unmatched: list[str] = field(default_factory=list)
    model_revision: str | None = None
    use_novel_split: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
