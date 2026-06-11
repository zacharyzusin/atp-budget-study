"""Contamination flagging + novel-split support.

miniF2F and ProofNet are public and almost certainly in the training corpora of open provers, so a
headline number on them is contamination-suspect. Two mitigations the eval protocol relies on
(PROJECT_PLAN.md §9): (1) record the base-model revision alongside the data so the comparison is
auditable, and (2) support a **held-out novel split** to lead the strongest claims with.

This module flags items as CONTAMINATED (public + not novel) and tags NOVEL items; it does not pick
the model revision — that's recorded in the dataset manifest at load time.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from atp.data.problems import FLAG_CONTAMINATED, FLAG_NOVEL, Problem

if TYPE_CHECKING:
    from atp.config import ExperimentConfig


def load_novel_names(config: ExperimentConfig) -> list[str]:
    """Read the held-out problem names from `data.novel_names_file` (the missing CLI plumbing).

    Resolves the path relative to `project.root` (absolute paths pass through). Two formats by
    suffix: `.json` → a JSON list of names; anything else → one name per line, blank lines and
    `#` comments ignored. Returns `[]` when no file is configured. Raises if a file IS configured
    but is missing or yields zero names — a silently-empty novel set would defeat the held-out
    comparison (mirrors the `use_novel_split` guard in `load_dataset`).
    """
    rel = config.data.novel_names_file
    if not rel:
        return []
    path = Path(rel)
    if not path.is_absolute():
        path = Path(config.project.root) / path
    if not path.exists():
        raise FileNotFoundError(f"data.novel_names_file not found: {path}")

    text = path.read_text()
    if path.suffix == ".json":
        names = json.loads(text)
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            raise ValueError(f"{path}: JSON novel_names_file must be a list of strings")
        names = [n.strip() for n in names if n.strip()]
    else:
        names = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    if not names:
        raise ValueError(f"data.novel_names_file {path} is empty — no held-out names to keep")
    # De-dup while preserving order (a name listed twice is harmless but tidy to collapse).
    return list(dict.fromkeys(names))


def mark_contamination(
    problems: list[Problem],
    *,
    novel_names: Iterable[str] = (),
    assume_public_contaminated: bool = True,
) -> list[Problem]:
    """Tag NOVEL items and (optionally) flag the rest as plausibly CONTAMINATED.

    `assume_public_contaminated=True` is the conservative default for public benchmarks: every
    non-novel item is treated as potentially in the training corpus, making the novel split the
    clean comparison.
    """
    novel = set(novel_names)
    out: list[Problem] = []
    for p in problems:
        flags: list[str] = []
        if p.name in novel:
            flags.append(FLAG_NOVEL)
        elif assume_public_contaminated:
            flags.append(FLAG_CONTAMINATED)
        out.append(p.with_flags(*flags) if flags else p)
    return out
