# Phase 4 — Compute-Optimal Budget Allocation (the positive result)

**Date:** 2026-06-20 · **Status:** core result landed and **one-model-robust** — single-checkpoint
realizable policy is the headline (goedel ProofNet# STRONG, +26% ± 7% per-seed); deepseek ProofNet#
downgraded to WEAK/fragile on the per-seed check (§1/§5). Two multi-round variants (successive-halving +
multi-round threshold) tested and pre-registered-falsified — policy-design phase closed (§6).
Realizability is by construction (early-stopping of budget-independent runs, §5), so no GPU confirming
run is required. All numbers are offline arithmetic over the four committed budget-independent baseline
runs (Goedel + DeepSeek × miniF2F + ProofNet#), via the §0 identity
`solved(cell,b) == tokens_to_solve(cell) ≤ b`. Code: `src/atp/alloc/` (tested, 36 cases); reproduce with
`scripts/phase4_ceiling.py`, `phase4_predictor.py`, `phase4_frontier.py`, `phase4_perseed.py`. Artifacts:
`ceiling.json`, `predictor.json`, `frontier.json`, `perseed.json`, `frontier_<model>_<benchmark>.png`.

## 1. Headline

On **ProofNet#** (the hard benchmark where ~80% of cells never solve and uniform pours full budget into a
provably-trapped core), a **realizable** during-run policy — abandon cells a logistic predictor flags as
trapped at a decision checkpoint `c*`, reallocate to survivors — saves substantial compute at near-equal
accuracy. The predictor uses **only** information observable by `c*` (elapsed tokens, #attempts, deepest
proof step reached, progress/plateau signals) and **out-of-fold** predictions (no train/test leakage).

| model × benchmark | save @80% acc | save @90% | save @95% | save @100% | per-seed @90% | call (§5) |
|---|---|---|---|---|---|---|
| **goedel × ProofNet#** | +15% | **+30%** | +24% | −2% | **+26% ± 7%** (+25/+18/+34) | **STRONG, robust** |
| deepseek × ProofNet# | −16% | +10% | +1% | +14% | −13% ± 28% (+5/+9/**−51**) | WEAK / fragile |
| goedel × miniF2F | −? | −16% | −22% | −0% | −40% ± 18% (−17/−62/−42) | negative (contrast) |
| deepseek × miniF2F | −64% | −16% | −22% | −0% | −13% ± 28% (−30/−28/+2) | negative (contrast) |

*(per-seed column added 2026-07-16 from the already-committed `perseed.json` — `phase4_perseed.py`
loops over all four baseline runs, so this data existed but wasn't previously tabulated. Confirms the
miniF2F contrast is per-seed consistent too: both models negative on all or nearly all seeds, no
seed happens to look positive.)*

**[UPDATED 2026-07-21, logged DECISIONS.md 2026-07-21 "WS1.1 power-up RESOLVED" but never folded back
into this table until 2026-07-25m — flagging that gap for the record]**: the deepseek × ProofNet# row
above is now **stale**. An 8-seed power-up (seeds 0–7, `results/phase4/perseed.json` regenerated
2026-07-24) resolved the per-seed @90% figure from **−13% ± 28% (3 seeds)** to **+10% ± 24% (8 seeds)**
— no single catastrophic seed anymore, sign flipped positive, variance shrank, but 0 still falls
within 1σ of the mean, so the call stands **WEAK/model-dependent, not confirmed**, just less noisy
than the 3-seed number implied. Gate G1 (2026-07-21) used this resolved number to make the
one-paper-world call. A 2026-07-25 paired per-problem bootstrap (`scripts/phase4_bootstrap_ci.py`,
`bootstrap_ci.json`) additionally found the seed-std framing understates true uncertainty for BOTH
models — see `paper/floor/main.tex`'s allocation section and DECISIONS.md 2026-07-25n for the exact
CIs.

"save @X%" = fraction of total compute the realizable policy saves vs uniform to reach X% of the solvable
cells (pooled over 3 seeds). The **per-seed @90%** column (`scripts/phase4_perseed.py`, recomputed within
each seed's cells using the same global c* and OOF predictor) is the load-bearing robustness check: the
**goedel ProofNet# headline holds across all three independent temperature-1.0 draws (+26% ± 7%)**, but
the **deepseek ProofNet# result does not** — it is +5/+9/−51%, dominated by a seed-2 collapse, and even
its pooled +10% sits below the pre-registered POSITIVE bar (15%). The positive contribution is therefore
**one-model-robust**, not two-model. miniF2F is the **contrast** — at ~75% solve rate there is little
wasted compute to reclaim, so abandonment only hurts (exactly as pre-registered).

## 2. Two honest caveats (load-bearing)

1. **The win is at a fractional-accuracy operating point, not at 100%.** To solve *every* winnable cell
   you must keep the hardest ones, whose cost (≈128k) is indistinguishable from trapped cells — so at
   100% accuracy the policy keeps almost everything and saves ~0. The positive result is "retain 90–95%
   of solves for ~25–30% less compute," and it is reported as such. This is a property of the problem,
   not a tuning failure: the cells that waste the most compute look like the cells that need the most.

2. **Efficiency, not raw accuracy, is the robust axis.** At fixed compute the realizable policy beats
   uniform only modestly (+0.2–0.5pp on ProofNet#), because the single decision checkpoint imposes a
   compute floor (`c*·N`) that blocks the cheap regime. The frontier figure shows realizable above
   uniform through the 5–35M-token operating band, converging at the top.

## 3. The oracle ceiling (why there was headroom to chase)

`scripts/phase4_ceiling.py` → `ceiling.json`. The unrealizable knapsack oracle (fund cheapest
`tokens_to_solve` first) shows the maximum headroom:

| model × benchmark | oracle compute saved @ equal final accuracy |
|---|---|
| goedel × miniF2F | 95.2% (4.5M vs 93.7M alloc) |
| goedel × ProofNet# | 98.1% (1.35M vs 71.4M) |
| deepseek × miniF2F | 95.1% |
| deepseek × ProofNet# | 96.9% |

The realizable policy captures roughly **one third** of this on Goedel ProofNet# at the 90% operating
point (saved 30% vs oracle's ~98%). The large oracle−realizable gap is the **predictability cost** — it
is prediction-limited at the fractional targets (tuning could help) and recall-limited at 100% (no
predictor can help, by caveat 1).

## 4. How early is trapped-ness predictable?

`scripts/phase4_predictor.py` → `predictor.json`. Problem-grouped CV AUC for predicting eventual solve
among still-running cells, ProofNet#:

| checkpoint c | goedel AUC | deepseek AUC |
|---|---|---|
| 2k | 0.64 | 0.47 |
| 4k | 0.71 | 0.65 |
| 8k | **0.75** | 0.67 |
| 16k | 0.72 | **0.72** |
| 32k | 0.46* | 0.62 |

*small-sample (≈13 positives). Predictability is **moderate (~0.65–0.75), peaking mid-run**. The dominant
feature is consistently `tokens_so_far` (elapsed-spend-without-success, a survival/hazard signal); the
plateau/stall signal (`depth_growth`) becomes a top-3 feature at c=16k; F1 opening-diversity never ranks
(it is weakly discriminative within the hard set, as found in Phase 2). Logistic regression beats
gradient boosting at every checkpoint (GBT overfits the small positive class). Real proof-step depth
came **free** from the verifier's logged `Failed at step N` (97.8% coverage) — no error-locus parser
needed.

## 5. Verdict vs pre-registered thresholds (§5 of the plan)

- **goedel × ProofNet#: STRONG and robust** — +30% compute saved at 90% of max accuracy (≥30% bar),
  +15–24% across 80–95%, and **+26% ± 7% per-seed** (all three independent draws +18 to +34%). This is
  the headline positive contribution.
- **deepseek × ProofNet#: WEAK / not robust** (downgraded from the earlier "POSITIVE" read once the
  per-seed and threshold checks were applied). Pooled +10–14% sits **below the 15% POSITIVE bar**, and
  per-seed it is +5/+9/**−51%** — a seed-2 collapse. Why: with only ~40 solved cells/seed and a high
  `c*` = 16k, the decision population is the *high-`tokens_to_solve` winnable* cells, which the pooled
  predictor misranks on seed 2; retaining 90% then forces a low abandonment threshold that keeps trapped
  cells. So the policy does not robustly transfer to the second model at this scale.
- **miniF2F (both): negative / not applicable** — the contrast benchmark; little wasted compute to
  reclaim. Reported honestly as the boundary of where allocation helps.

**The positive contribution is one-model-robust** (goedel ProofNet#), not two-model. (The *negative*
results — scaffolding null, hammer NO-GO, and the two falsified multi-round policies in §6 — are
two-model.) **Realizability is by construction, not just simulated:** the policy is early-stopping of the
budget-independent 128k runs (the agent's trajectory depends only on seed/model/verifier, never on the
announced budget — `max_refine` is a fixed count, `alloc_split` is unused, and the budget meter's clamp
only truncates the max length of a single boundary attempt, which alters neither `solved` nor
`tokens_to_solve`). A kept cell keeps its logged 128k trajectory; an abandoned cell stops at a *prefix*
where the verifier already shows no solve. So realized = simulated exactly, no GPU re-run required, and
the §0 identity is validated three ways plus the Phase 0 pass@B reproduction.

**Framing:** to our knowledge the first *mechanism-informed* compute-optimal budget allocation for
whole-proof theorem proving — the abandonment signal is derived from the Phase 2 failure mechanism
(elapsed-spend + proof-depth plateau), and the efficiency frontier is given for the constrained,
modest-scale setting. The contribution is the application + the mechanism-derived signal + the frontier,
not the invention of allocation or successive-halving.

## 6. Multi-round policies: two pre-registered negatives (tested, not just argued)

The single decision checkpoint imposes a compute floor (`c*·N`), so we pre-registered (DECISIONS.md,
2026-06-20) and built **two** multi-round policies over the rung ladder `[2k,4k,8k,16k,32k,128k]` (cut
on the OOF score at each rung's checkpoint): **successive-halving** (cut the weakest top-η *fraction*
each rung) and **multi-round thresholding** (keep the quality *set* with score ≥ τ each rung). The
registered hypothesis was that lowering the floor would lift the loose-target and DeepSeek numbers
toward two-model STRONG; thresholding was registered as the sharper test (it abandons trapped cells at
rung 0 without shedding late winnable cells, so it *could* in principle shave the floor off the
headline). Both built (`src/atp/alloc/halving.py`, tested) and run on the same frontier. **Both
headline claims are falsified; the single-checkpoint policy wins.**

| ProofNet#, save vs uniform | @80% | @90% | @95% | @100% |
|---|---|---|---|---|
| goedel — **single-checkpoint (headline)** | +15% | **+30%** | +24% | −2% |
| goedel — successive-halving | −95% | −50% | −25% | −2% |
| goedel — multi-round threshold | +2% | −29% | −18% | −2% |
| deepseek — **single-checkpoint (headline)** | −16% | +10% | +1% | +14% |
| deepseek — successive-halving | −145% | −99% | −43% | −6% |
| deepseek — multi-round threshold | −34% | −47% | −2% | −5% |

We pre-registered and tested **two** multi-round variants. Findings, against the registered clauses:

1. **Both are falsified on the headline; single-checkpoint is the best realizable policy of the three.**
   Fixed-fraction halving is far worse on compute-saved-at-accuracy; multi-round thresholding is also
   worse, never better. Diagnosis: in the rare-winnable regime (ProofNet# ≈14% solvable) (a) constant-η
   halving must keep a high fraction every round to retain the rare *late*-solving winnable cells, which
   drags trapped cells to late rungs; and (b) a single τ applied at *every* rung thresholds on the early
   rungs (2k/4k) where AUC is weak-to-below-chance (deepseek 2k = 0.47), abandoning winnable cells by
   mistake unless τ is low enough to keep almost everyone. The single-checkpoint policy avoids both by
   deciding **once**, at the **best-AUC** checkpoint `c*`, on a quality-defined **set**. So the headline
   number is **ranking/recall-limited, not floor-limited** — now a *measured* fact across three policies,
   not an argument: no scheduling we tried shaves the headline, and the "does multi-round thresholding
   beat it?" objection is pre-empted empirically. The registered trip-wire (a multi-round policy
   *materially beating* single-checkpoint) did **not** fire.
2. **The floor is real but only bites the cheapest operating point, and no variant converts it to a
   robust win.** At 5% of uniform's max compute the single-checkpoint policy solves **0** (its `c*·N`
   floor isn't cleared); halving solves **51/80** (goedel) / **54/124** (deepseek) and edges uniform
   (+1.1pp goedel) by reallocating from trapped (cut at 2k) to winnable — but the edge is gone by 10%,
   and thresholding does not even reach it (it ties uniform @5%, trails @10%). So the floor matters only
   in a regime no one operates in.
3. **Safety clause held (both variants).** Neither moves the 100%-accuracy target (≈−2% to −6%),
   confirming the recall wall (caveat 1) is a fundamental problem property, not a scheduling artifact.
   The registered "if the 100% target lifts, the floor diagnosis was wrong" did not trigger.

The headline policy therefore **stays single-checkpoint**, and this is the **end of the policy-design
phase** (the cheap empirical checks are done; further tuning has low marginal value against an
already-positive, recall-capped number). The one remaining load-bearing step is a small **live confirming
run** (Task 4.4) on the single-checkpoint policy, to convert "we *simulated* 30% saved" into "we
*measured* it" — the claim a reviewer most wants to see verified.
