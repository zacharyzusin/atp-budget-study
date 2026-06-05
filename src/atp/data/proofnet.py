"""ProofNet# (corrected ProofNet) loader.

Reads a JSONL bank (`<split>.jsonl`, one object per line: name, statement, optional imports/opens/
informal). Not staged on this cluster yet — `load_proofnet` raises FileNotFoundError until
`config.data.proofnet_dir` points at the data; the format/loader are unit-tested via a fixture so
wiring it later is a config change.
"""

from __future__ import annotations

import json
from pathlib import Path

from atp.data.problems import Problem


def load_proofnet(split: str, proofnet_dir: str | Path | None = None) -> list[Problem]:
    if proofnet_dir is None:
        raise FileNotFoundError(
            "ProofNet# not staged; set config.data.proofnet_dir to a dir with <split>.jsonl files."
        )
    root = Path(proofnet_dir)
    jf = root / f"{split}.jsonl"
    if not jf.is_file():
        raise FileNotFoundError(f"ProofNet# split not found: {jf}")

    problems: list[Problem] = []
    for line_no, line in enumerate(jf.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        d = json.loads(line)
        problems.append(
            Problem(
                name=d["name"],
                statement=d["statement"],
                benchmark="proofnet_sharp",
                split=split,
                imports=tuple(d.get("imports", ["Mathlib"])),
                opens=tuple(d.get("opens", ())),
                informal_statement=d.get("informal_statement"),
                provenance={
                    "benchmark": "proofnet_sharp",
                    "split": split,
                    "source_file": str(jf),
                    "source_line": line_no,
                },
            )
        )
    return problems
