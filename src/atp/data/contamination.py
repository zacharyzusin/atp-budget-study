"""Contamination flagging + novel-split support.

miniF2F and ProofNet are public and almost certainly in the training corpora of open provers, so a
headline number on them is contamination-suspect. Two mitigations the eval protocol relies on
(PROJECT_PLAN.md §9): (1) record the base-model revision alongside the data so the comparison is
auditable, and (2) support a **held-out novel split** to lead the strongest claims with.

This module flags items as CONTAMINATED (public + not novel) and tags NOVEL items; it does not pick
the model revision — that's recorded in the dataset manifest at load time.
"""

from __future__ import annotations

from collections.abc import Iterable

from atp.data.problems import FLAG_CONTAMINATED, FLAG_NOVEL, Problem


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
