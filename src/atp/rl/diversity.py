"""Generation-diversity metrics for the G3 gate (no diversity collapse).

Generic RFT (Stage A) hurt the floor by narrowing the policy (−13..−19pp). The probe watches for the
same failure mode in RL: if reward rises only because the policy collapsed onto a few strings, that
is not floor-movement. We track two cheap, monotone-interpretable statistics over a rollout batch
and compare RL-final to base (G3: retain ≥80% of base). KL-to-base comes free from trl's GRPO logs
(beta>0), so it is not recomputed here.

Pure string functions — no model/Lean — so they unit-test on a login node.
"""

from __future__ import annotations

import math
from collections import Counter


def _tokens(text: str) -> list[str]:
    return text.split()


def distinct_ngram_ratio(texts: list[str], n: int = 3) -> float:
    """distinct-n: unique n-grams / total n-grams across the batch (1.0 = all distinct, →0 = highly
    repetitive). Collapse onto a few templates drives this down. Batches with no n-gram (rollouts
    all shorter than n tokens) return 0.0."""
    total = 0
    seen: set[tuple[str, ...]] = set()
    for text in texts:
        toks = _tokens(text)
        for i in range(len(toks) - n + 1):
            gram = tuple(toks[i:i + n])
            seen.add(gram)
            total += 1
    return len(seen) / total if total else 0.0


def token_entropy(texts: list[str]) -> float:
    """Shannon entropy (nats) of the unigram token distribution over the batch. A policy that
    collapses onto a narrow vocabulary loses entropy. 0.0 for an empty batch."""
    counts: Counter[str] = Counter()
    for text in texts:
        counts.update(_tokens(text))
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return -sum((c / total) * math.log(c / total) for c in counts.values())


def diversity_snapshot(texts: list[str]) -> dict[str, float]:
    """The batch's diversity stats, keyed for trainer logging."""
    return {
        "diversity/distinct_3gram": distinct_ngram_ratio(texts, 3),
        "diversity/token_entropy": token_entropy(texts),
        "diversity/mean_tokens": (
            sum(len(_tokens(t)) for t in texts) / len(texts) if texts else 0.0
        ),
    }


def retention(rl_value: float, base_value: float) -> float:
    """RL-final relative to base for a diversity stat (G3 wants ≥0.80). Base 0 → 1.0 (no collapse
    possible from nothing)."""
    if base_value <= 0:
        return 1.0
    return rl_value / base_value
