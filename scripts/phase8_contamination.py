#!/usr/bin/env python3
"""Phase 8 — contamination-noted subset for the matched-pair floor table.

This is NOT a full contamination audit (we have no access to any of these labs' actual training
corpora) — it is the concrete, mechanical checking that IS available to us from the benchmark data
itself, plus one well-documented, field-specific risk:

1. **miniF2F valid/test name-collision check** — the mechanical thing we can actually verify: does
   the vendored miniF2F copy leak any problem name between its `valid` and `test` splits (a real bug
   pattern in this exact research area — RL/expert-iteration stages in this whole prover lineage
   train on miniF2F-*valid*, so a valid/test leak would be a genuine contamination vector). No
   per-problem overlap flag beyond this is possible without the labs' private training manifests.

2. **ProofNet# textbook-exercise flag** — ProofNet# is composed almost entirely (180/186) of named
   textbook exercises (Dummit&Foote, Munkres, Rudin, Herstein, Artin, Axler, Ireland&Rosen,
   Shakarchi, Pugh — verified via the `NAME__exercise_...` prefix convention) plus 6 Putnam
   competition problems. Textbook exercise banks are the field's standard synthetic-training-data
   source pool (DeepSeek-Prover-V1.5/Goedel-Prover/Leanabell-Prover all describe synthesizing SFT/RL
   training data from exactly this kind of source), so textbook-named problems carry a real,
   plausible train-overlap risk for ALL of these labs' models specifically (not just a generic
   web-pretraining risk). The 6 Putnam problems are the best available LOWER-risk subset (not the
   field's standard textbook-synthesis source pool) — still not zero-risk (Putnam solutions are
   public online, and inherited web-pretraining contamination applies equally to Base too, so it
   isn't RL-differential) but the closest thing to a "flagged-clean" slice this repo can produce
   without the labs' private data.

Both checks are logged plainly as what they are: real but partial evidence, not a full audit.
"""
import re
from dataclasses import dataclass

_TEXTBOOK_PREFIXES = frozenset({
    "Dummit", "Munkres", "Rudin", "Herstein", "Artin", "Axler", "Ireland", "Shakarchi", "Pugh",
})


def proofnet_problem_source(name):
    """The `NAME__exercise_...` prefix convention -> ('textbook', <book>) or ('competition', <src>)."""
    prefix = name.split("__")[0]
    if prefix in _TEXTBOOK_PREFIXES:
        return ("textbook", prefix)
    return ("competition", prefix)


def proofnet_low_risk_subset(names):
    """The Putnam (competition) slice — NOT the field's standard textbook-synthesis source pool.
    Still not zero-risk (see module docstring) — the best available lower-risk subset, not a
    guarantee of no contamination.
    """
    return {n for n in names if proofnet_problem_source(n)[0] == "competition"}


@dataclass
class MiniF2FSplitLeakReport:
    test_names: set
    valid_names: set
    overlap: set

    @property
    def is_clean(self):
        return len(self.overlap) == 0


def minif2f_split_leak_check(test_problems, valid_problems):
    """Exact-name overlap between the vendored miniF2F test/valid splits. RL/expert-iteration stages
    in this lineage are documented as training on miniF2F-*valid* — a valid/test name collision would
    be a direct, concrete leak into what's reported as the "test" floor.
    """
    test_names = {p.name for p in test_problems}
    valid_names = {p.name for p in valid_problems}
    return MiniF2FSplitLeakReport(
        test_names=test_names, valid_names=valid_names, overlap=test_names & valid_names
    )
