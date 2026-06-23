"""Lean Workbook (Phase 6 training corpus) loader.

Reads the **decontaminated** corpus written by `scripts/phase6_decontaminate.py`
(`scratch/phase6/lean_workbook_clean.json`): a JSON list of objects with `formal_statement`
(`theorem <name> <binders> : <goal> := by sorry`), `natural_language_statement`, `tags`, and the
`_lw_id` stamped at decontamination time. Disjoint from miniF2F / ProofNet#-test by construction
(§0, see results/phase6/DISJOINTNESS.md) — NEVER load the raw corpus for training.

`Problem.statement` is the declaration head with the `:= by sorry` proof tail stripped (the prover
appends its own proof), mirroring the miniF2F/ProofNet loaders.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from atp.data.problems import Problem

_PROOF_TAIL = re.compile(r"\s*:=\s*(?:by\s+)?sorry\s*$", re.DOTALL)


def strip_proof_tail(formal_statement: str) -> str:
    """Drop a trailing `:= by sorry` / `:= sorry`, returning the bare declaration head."""
    return _PROOF_TAIL.sub("", formal_statement.strip()).rstrip()


def load_lean_workbook(clean_path: str | Path) -> list[Problem]:
    """Load the decontaminated Lean Workbook clean corpus as `Problem`s (benchmark='lean_workbook').

    Raises FileNotFoundError if the clean corpus is missing — the §0 decontamination must run first
    (the raw corpus is contaminated and must not be used for training).
    """
    path = Path(clean_path)
    if not path.is_file():
        raise FileNotFoundError(
            f"clean Lean Workbook not found: {path} — run scripts/phase6_decontaminate.py first "
            "(loading the raw, contaminated corpus for training is forbidden, see §0)."
        )
    rows = json.loads(path.read_text())
    problems: list[Problem] = []
    for i, d in enumerate(rows):
        name = d.get("_lw_id") or f"lean_workbook_{i}"
        problems.append(
            Problem(
                name=name,
                statement=strip_proof_tail(d["formal_statement"]),
                benchmark="lean_workbook",
                split="train",
                imports=("Mathlib",),
                opens=(),
                informal_statement=d.get("natural_language_statement"),
                provenance={
                    "benchmark": "lean_workbook",
                    "corpus": "lean_workbook_clean",
                    "tags": d.get("tags", []),
                    "source_file": str(path),
                    "source_index": i,
                },
            )
        )
    return problems
