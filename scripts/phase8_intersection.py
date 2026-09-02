#!/usr/bin/env python3
"""Phase 8 step 2 — compile-on-ALL-pins intersection, generalized from scripts/h1_intersection.py
(which hardcoded exactly 2 pins: Goedel + DeepSeek) to an arbitrary list of
statement_validation.json
paths. Cluster-A models that reuse an EXISTING pin (the V1.5 triple, Goedel-Prover-SFT, BFS-Prover —
all on the Goedel pin per results/phase8/ZOO.md) contribute nothing new: their failures are already
captured by that pin's validation file, so passing the same file more than once is a no-op, not a
double-count.

Usage (as a script): prints the intersection size for miniF2F and ProofNet# across every pin
currently in use in this repo (Goedel pin + DeepSeek pin — the only two, as of Phase 8 check-in #1).
"""
import json
import os
from dataclasses import dataclass


@dataclass
class IntersectionResult:
    n_total: int
    excluded_names: set
    intersection_size: int


def _failure_name(f):
    return f["name"] if isinstance(f, dict) else f


def compute_intersection(validation_paths):
    """Intersection (problems that elaborate under EVERY pin) = full set - union(failures).

    Raises FileNotFoundError if any path is missing, ValueError if the validation files disagree on
    n_problems (they should all describe the same canonical benchmark).
    """
    n_total = None
    excluded = set()
    for path in validation_paths:
        if not os.path.exists(path):
            raise FileNotFoundError(f"statement_validation.json not found: {path}")
        with open(path) as f:
            d = json.load(f)
        n = d["n_problems"]
        if n_total is None:
            n_total = n
        elif n != n_total:
            raise ValueError(
                f"{path}: n_problems={n} does not match earlier n_problems={n_total} — "
                "these validation files describe different benchmark sets, not the same one "
                "under different pins."
            )
        excluded |= {_failure_name(f) for f in d.get("failures", [])}
    return IntersectionResult(
        n_total=n_total, excluded_names=excluded, intersection_size=n_total - len(excluded)
    )


PINS_IN_USE = {
    "miniF2F": [
        "results/minif2f/statement_validation.json",
        "results/phase2/deepseek/statement_validation/minif2f_deepseekpin.json",
    ],
    "ProofNet#": [
        "results/proofnet_sharp/statement_validation.json",
        "results/phase2/deepseek/statement_validation/proofnet_deepseekpin.json",
    ],
}


if __name__ == "__main__":
    for bench, paths in PINS_IN_USE.items():
        r = compute_intersection(paths)
        print(
            f"{bench:10s} n_total={r.n_total:4d} excluded={len(r.excluded_names):3d} "
            f"intersection={r.intersection_size:4d}"
        )
