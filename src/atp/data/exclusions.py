"""Known-unprovable exclusion list for miniF2F.

Mechanism only — the names live in a data file (`minif2f_exclusions.txt`, or a config override) so
the audited set can be updated without code changes. `apply_exclusions` flags matches as
UNPROVABLE and returns the names that matched *nothing* loaded, so typos or a benchmark-version
mismatch surface loudly instead of silently excluding zero problems.
"""

from __future__ import annotations

from pathlib import Path

from atp.data.problems import FLAG_UNPROVABLE, Problem

DEFAULT_EXCLUSIONS_FILE = Path(__file__).parent / "minif2f_exclusions.txt"


def load_exclusions(path: str | Path | None = None) -> set[str]:
    """Read problem names from the exclusion file (one per line, `#` comments). Empty if absent."""
    p = Path(path) if path else DEFAULT_EXCLUSIONS_FILE
    if not p.is_file():
        return set()
    names: set[str] = set()
    for line in p.read_text().splitlines():
        s = line.split("#", 1)[0].strip()
        if s:
            names.add(s)
    return names


def apply_exclusions(
    problems: list[Problem], exclusions: set[str]
) -> tuple[list[Problem], list[str]]:
    """Flag problems named in `exclusions` as UNPROVABLE (does not drop them — the caller decides).

    Returns (flagged_problems, unmatched_exclusion_names). Unmatched names almost always mean a typo
    or that the staged benchmark differs from the one the list was written against.
    """
    present = {p.name for p in problems}
    flagged = [p.with_flags(FLAG_UNPROVABLE) if p.name in exclusions else p for p in problems]
    unmatched = sorted(exclusions - present)
    return flagged, unmatched
