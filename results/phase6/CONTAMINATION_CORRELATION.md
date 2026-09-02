# Contamination-correlation check (WS6 item 2, free half) -- NULL

Pre-registered decision rule (committed before running, PLAN_NEXT.md WS6 item 2): NULL if overlap
score does not significantly predict trapped status; SIGNAL if trapped problems are significantly
LESS similar to the Lean-Workbook training corpus than solved ones.

## Result

- 244 miniF2F problems: 55 trapped (0/3 baseline seeds solve),
  189 solved by at least one baseline seed, 0 others.
- TF-IDF formal-statement cosine similarity to nearest Lean-Workbook training example (same metric as
  the Phase 6 Section-0 disjointness gate):
  - trapped: mean 0.8051, median 0.7964
  - solved:  mean 0.7430, median 0.7421
- Mann-Whitney U test (two-sided): U=6097.0, p=0.0494
- Exact (normalized-statement) overlap: 2/55
  (3.6%) of trapped problems vs.
  3/189
  (1.6%) of solved problems have an exact
  normalized-statement match in Lean-Workbook (of 5 total exact
  overlaps across the full eval set).

## Verdict

**NULL relative to the pre-registered SIGNAL direction.** The pre-registered decision rule required
BOTH statistical significance AND the direction "trapped problems are LESS similar to the training
corpus" to escalate. p=0.0494 clears the significance threshold (barely — treat as marginal, not
strong, evidence either way), but the **direction is the opposite of the contamination-boundary
concern**: trapped problems are, if anything, slightly MORE similar to the training corpus (mean
cosine 0.805 vs. 0.743 for solved problems), and have a HIGHER exact-overlap rate (3.6% vs. 1.6%).
Both point away from, not toward, "the floor is where training-set recall ends."

## Interpretation

This check does not just fail to support the recall-boundary reading — it points the wrong way for
that reading to hold. If trapped problems were unsolved because the model had not seen anything like
them during training, we would expect LOWER training-corpus similarity for trapped problems; we
observe the opposite (marginally). A plausible confound: trapped problems may simply be textually
denser/harder competition-style statements that also happen to resemble more Lean-Workbook entries in
surface form (both are drawn from similar competition-math phrasing), without that resemblance
translating into an exploitable memorized proof — consistent with, not contradicted by, F2/F3's
reading of trapped failures as genuine execution-depth failures (the model recognizes the problem
*type* but cannot execute a full closing proof for it). Per WS6's pre-registration, this is a clean
NULL: **the paid mutation-probe follow-up (item 2's paid half) is not triggered.**

## Addendum 2026-07-26 — recovery-level cross-check (user-prompted)

Item 2-free's population-level check (above) compares all 55 trapped vs. all 189 solved miniF2F
problems and finds the WRONG direction for a memorization-boundary account. A complementary, more
targeted question: among the 9 problems that flipped from trapped to solved during this sprint's
calibration cells (Goedel x miniF2F: 6; DeepSeek x miniF2F: 3), do the ones with a real (non-harness-
artifact) explanation show elevated training-corpus overlap specifically?

Cross-referencing per-problem TF-IDF cosine + exact-overlap status (same machinery as above) against
the calibration-cell provenance already logged in DECISIONS.md 2026-07-25k / 2026-07-26b:

| problem | cosine | exact overlap | provenance |
|---|---|---|---|
| amc12a_2021_p8 | 1.000 | **yes** | Goedel genuine (also the known miniF2F/Lean-Workbook overlap case) |
| imo_1968_p5_1 | 1.000 | no | Goedel genuine |
| algebra_apbon2pownleqapownpbpowon2 | 1.000 | no | Goedel header-artifact |
| aime_1997_p9 | 0.906 | no | Goedel header-artifact |
| imo_1962_p2 | 0.789 | no | DeepSeek heartbeat-artifact |
| amc12b_2021_p18 | 0.744 | no | Goedel genuine |
| aime_1988_p8 | 0.636 | no | Goedel genuine |
| mathd_numbertheory_495 | 0.567 | no | DeepSeek genuine |
| amc12_2001_p21 | 0.375 | no | DeepSeek heartbeat-artifact |

Genuine recoveries (n=5) mean cosine 0.789 vs. harness-artifact recoveries (n=4) mean cosine 0.768 —
no separation between the two groups, and both sit close to the trapped-population mean (0.805), which
is exactly what's expected since every recovery is drawn FROM the trapped population (not evidence of
anything beyond item 2-free's own finding).

Exactly 1/9 recoveries (1/5 of the genuine ones) has an exact training-corpus overlap
(`amc12a_2021_p8`). A one-sided binomial test against the trapped-population base exact-overlap rate
(3.6%, 2/55) gives p=0.281 (all 9 recoveries) / p=0.167 (genuine-only, n=5) — **not distinguishable
from the base rate at this sample size.** The single overlap case is also the one that took 3 resample
attempts / 18,023 tokens to close (DECISIONS.md 2026-07-24), which is not the token/attempt signature
of pure lookup recall.

**Verdict: this does not change item 2's NULL.** One exact-overlap recovery out of nine is consistent
with (not elevated above) the population base rate; it is a real, reportable data point for the
`amc12a_2021_p8` contamination caveat that already exists elsewhere in the paper (diversity-injection
discussion), not new evidence that the execution floor is a recall boundary. n=9 is simply too small
for this cross-check to move the verdict either way on its own; item 2-free's population-level
Mann-Whitney (n=55 vs n=189, the far better-powered test) remains the operative result and it points
the wrong direction for the memorization-boundary reading.

## Addendum 2026-07-26 (cont.) — effect size + framing precision (user review)

Rank-biserial correlation from the Mann-Whitney U (U=6097.0, n_trapped=55, n_solved=189):
r = 1 - 2U/(n1*n2) = -0.173 -- a SMALL effect by conventional thresholds (|r|<0.1 negligible, 0.1-0.3
small, 0.3-0.5 medium). Reported alongside p=0.0494 rather than the p-value alone, since a marginal
p-value at n=55 vs 189 is fragile and the sign should not be leaned on harder than the effect size
supports.

**Precise claim, stated for citation:** this check finds NO evidence for the memorization-boundary
account of the execution floor, and WEAK evidence against it (small effect, wrong-direction point
estimate on both the cosine-similarity and exact-overlap measures). It does NOT establish that trapped
problems are meaningfully "more novel" or "less novel" than solved ones in any strong sense -- the
effect is small and the test is underpowered at this n. TF-IDF similarity to Lean-Workbook is also a
proxy for overlap with ONE training corpus (the one used for the contamination check throughout this
project), not a direct measurement of either Goedel-Prover-V2-8B's or DeepSeek-Prover-V2-7B's actual
full pretraining mixture -- a genuine limitation of what this check can speak to, independent of the
sample-size caveat above.
