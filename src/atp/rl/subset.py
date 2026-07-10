"""Training/held-out subset selection for the GRPO probe (STAGE_C_PROBE_SPEC.md §1/§2).

GRPO needs problems where the base gets *dense* advantage signal: not 0/K (no gradient) and not K/K
(no headroom). We run the base at K samples over a decontaminated `lean_workbook_clean` slice,
bucket by empirical solve-count, keep the sweet-spot band (base solve-rate in [1/16, 10/16]), and
draw a **disjoint** train set (~256) and held-out gate set (~200) from the SAME band (matched
difficulty). Deterministic given the seed so the split is reproducible + auditable.

Pure over a {name: solve_count} mapping — no Lean/model — so it unit-tests on a login node. The
§0 train/test DISJOINTNESS gate (vs miniF2F + ProofNet#) is enforced upstream at corpus load
(lean_workbook_clean is already decontaminated); this module only guarantees train ∩ heldout = ∅.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class SubsetSplit:
    train: tuple[str, ...]
    heldout: tuple[str, ...]
    band_lo: int
    band_hi: int
    band_size: int  # eligible problems in the band before the train/heldout draw

    @property
    def enough(self) -> bool:
        return len(self.train) > 0 and len(self.heldout) > 0


def band_bounds(k: int, lo_frac: float, hi_frac: float) -> tuple[int, int]:
    """Inclusive solve-count band from fractional bounds. lo rounds UP (exclude 0-solve), hi rounds
    DOWN (exclude a perfect K/K). Clamped to [1, k-1] so the band always excludes no-signal and
    no-headroom problems."""
    lo = max(1, math.ceil(lo_frac * k))
    hi = min(k - 1, math.floor(hi_frac * k))
    return lo, hi


def select_by_solve_rate(
    solve_counts: dict[str, int],
    *,
    k: int,
    lo_frac: float = 1 / 16,
    hi_frac: float = 10 / 16,
    n_train: int = 256,
    n_heldout: int = 200,
    seed: int = 0,
) -> SubsetSplit:
    """Bucket by solve-count, keep the band, shuffle deterministically, split disjointly."""
    lo, hi = band_bounds(k, lo_frac, hi_frac)
    band = sorted(name for name, c in solve_counts.items() if lo <= c <= hi)
    rng = random.Random(seed)
    rng.shuffle(band)
    train = tuple(band[:n_train])
    heldout = tuple(band[n_train:n_train + n_heldout])
    return SubsetSplit(train=train, heldout=heldout, band_lo=lo, band_hi=hi, band_size=len(band))
