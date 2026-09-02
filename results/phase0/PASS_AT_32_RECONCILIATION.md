# pass@32-ish reconciliation against published/third-party numbers (WS6 item 6a, 2026-07-25)

**Free, arithmetic-only, closes the calibration question on the record per the user's explicit
request.**

Goedel-Prover-V2-8B × miniF2F, union coverage:

- Baseline (3 original seeds, 128k-token budget each): **189/244 solved** (77.46%) — any of the 3
  seeds solving counts, computed directly from `results/baseline/problems/*.json`.
- Plus the 6 calibration-cell recoveries at N=32 fresh samples on the 55-problem trapped core (see
  `scripts/header_confound_reverify.py`'s `RECOVERED` list; these are disjoint from the 189 by
  construction — the trapped core is exactly the population no baseline seed solved):
  **189 + 6 = 195/244 = 79.92% ≈ 80%.**

This sits between the model authors' reported 84.6% and GAR's third-party reproduction of ~78%
(reported figure, not independently re-verified by this project — cited from the WS6 pre-registration
discussion, not re-checked against GAR's own paper this pass).

**Caveat, stated explicitly (do not drop when citing this number):** this is a **union across the 3
original seeds plus 32 additional fresh calibration samples on the previously-unsolved subset**, not a
single clean pass@32 run over all 244 problems. It is a reasonable proxy for "how much does this model
solve given roughly pass@32-scale sampling," and it lands in a believable range relative to both the
authors' number and a third-party reproduction — which is the calibration question this number is
meant to close (is our harness producing wildly-off numbers relative to what's published) — but it
should not be reported as a clean pass@32 headline in its own right.

**Verdict:** the calibration question is closed on the record. Our harness's numbers land in a
believable band relative to both ends of the published-vs-reproduced range; no further calibration
work needed on this axis.
