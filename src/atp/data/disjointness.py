"""Train/test disjointness checking for Phase 6 fine-tuning (the §0 non-negotiable gate).

A fine-tuning result is worthless if the training corpus overlaps the eval benchmarks. This module
provides the load-bearing primitive: `normalize_formal_statement`, which strips a Lean theorem down
to a name- and whitespace-invariant key so the SAME problem stated under a different declaration
name or formatting hashes identically. Exact-overlap on these keys is the hard disjointness signal;
the fuzzy/near-duplicate pass (TF-IDF cosine over formal + informal text) lives in
`scripts/phase6_disjointness.py` and feeds a manual spot-check.

Disjointness must hold against BOTH eval sets (miniF2F-test, ProofNet#). See PHASE6 plan §0.
"""

from __future__ import annotations

import re

# Leading declaration keyword + the (optional, `example` has none) declared name, e.g.
# "theorem lean_workbook_0", "lemma foo'", "example".
_DECL_HEAD = re.compile(
    r"^\s*(?:theorem|lemma|example|def)\b\s*(?:[A-Za-z_][A-Za-z0-9_'.]*)?\s*", re.UNICODE
)
# A trailing proof body, if a full proof slipped into the statement string.
_PROOF_TAIL = re.compile(r"\s*:=\s*by\b.*$", re.DOTALL)
_SORRY_TAIL = re.compile(r"\s*:=\s*(?:sorry|by\s+sorry)\s*$", re.DOTALL)


def normalize_formal_statement(stmt: str) -> str:
    """Reduce a Lean statement to a name- and whitespace-invariant key.

    Strips the leading `theorem/lemma/example/def <name>`, any `:= by …`/`:= sorry` proof tail, and
    collapses all runs of whitespace to single spaces. Two statements that differ ONLY in the
    declaration name or formatting map to the same key (so an eval problem re-named in the corpus is
    caught by exact-key overlap). Does NOT alpha-rename binders — that is the fuzzy pass's job.
    """
    s = stmt.strip()
    s = _DECL_HEAD.sub("", s, count=1)
    s = _SORRY_TAIL.sub("", s)
    s = _PROOF_TAIL.sub("", s)
    s = s.rstrip(" \t\n:=")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def exact_overlap(
    train: dict[str, str], evalset: dict[str, str]
) -> list[tuple[str, str]]:
    """Return (train_name, eval_name) pairs whose normalized statements are byte-identical.

    `train`/`evalset` map problem name -> raw formal statement. The hard disjointness signal: any
    returned pair is a confirmed contamination (same statement up to name/whitespace).
    """
    by_key: dict[str, str] = {}
    for name, stmt in evalset.items():
        by_key[normalize_formal_statement(stmt)] = name
    hits: list[tuple[str, str]] = []
    for name, stmt in train.items():
        ev = by_key.get(normalize_formal_statement(stmt))
        if ev is not None:
            hits.append((name, ev))
    return hits
