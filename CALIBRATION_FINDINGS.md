# External Calibration Sprint — Findings So Far

**Status: CLOSED (2026-07-25g).** Every item from the original critique and every
follow-on the sprint surfaced is resolved, run, declined-with-reasoning, or logged as
an explicit scope limit — see "Resolved this round" below. `paper/floor/` (WS2) was
never touched during the sprint; reopening it is now a recommendation awaiting your
confirmation, not something still blocked on more calibration work.

## Why this sprint happened

An external reviewer critiqued the project's committed results, focused mainly on
Phase 8's headline "0.0%-everywhere" number and the trapped-core population used
throughout Phases 2/5/7. The critique argued three things: (1) Goedel's own baseline
looked ~10pp low vs. published numbers, suggesting a harness/prompt mismatch; (2) the
project's "pass@budget" metric (tokens spent, including refinement) is not the same
thing as the literature's "pass@N" (independent fresh samples), so trapped-core claims
built on pass@budget=0 don't straightforwardly transfer; (3) several downstream
verdicts (Stage C's RL "capacity ceiling", the scaffolding-doesn't-help claim) may be
under-tested rather than genuinely negative.

The plan agreed with the user: cheap CPU-only checks first, escalate to one real GPU
calibration cell only if those checks found something load-bearing, and do not open
any new experimental arm or touch the paper along the way.

## Tier 0 — CPU-only checks (no GPU spent)

| Check | Finding | Doc |
|---|---|---|
| Lean/mathlib version pin | Already verified correct against Goedel-Prover-V2's own `.gitmodules` in an earlier session — not a live issue | (resolved from existing evidence, DECISIONS.md 2026-07-21) |
| pass@N recount | **The big one.** Goedel×miniF2F's 128k-token budget maps to a median of only **1** independent propose attempt (max 14), because the refinement loop (up to 4 iterations/attempt) consumes most of the budget. "Trapped" in this project's sense is not the same claim as "trapped under pass@32" in the literature's sense. | `results/phase0/PASS_AT_N_RECOUNT.md` |
| Truncation / heartbeat audit | Only 4.89% of Goedel miniF2F PROPOSE attempts hit the token cap — truncation is not a material confound. The heartbeat bug (`set_option maxHeartbeats 0` missing) is **not** scoring-only for miniF2F as SYNTHESIS.md currently claims — it affects 17.8% of refine steps. | `results/phase0/TRUNCATION_AND_TIMEOUT_AUDIT.md` |
| Stage A format diff | Logged for the record; no action needed yet | `results/phase6/STAGE_A_FORMAT_DIFF.md` |
| F1 attempt-count reconciliation | Resolved an apparent contradiction between two prior counts: different population (unsolved-only vs. all cells) and different convention (total propose+refine vs. propose-only) — both were correct for what they measured | `results/phase2/F1_ATTEMPT_COUNT_RECONCILIATION.md` |
| Attempts-per-budget table | Full breakdown backing the pass@N recount | `results/phase0/ATTEMPTS_PER_BUDGET_TABLE.md` |

**Consequence:** the pass@N recount escalated the sprint. It wasn't just a calibration
question anymore — it meant the trapped-core population (used as the "baseline=0 by
construction" foundation of Phases 2, 5, and 7) had never actually been tested under
plain independent resampling. The GPU cell was redesigned around answering that
question directly, per the user's instruction ("check #1 found something bigger than a
calibration problem").

## Tier 1 — GPU calibration cell (job 11682365, completed 2026-07-25)

**Design:** Goedel-Prover-V2-8B on its own 55-problem miniF2F trapped core (unsolved
by every seed at 128k tokens), official protocol — Aesop header, `maxHeartbeats 0`,
temp 0.7 — 32 independent samples per problem, no refinement, no budget meter
(`max_rounds=32` is the real stopping condition). Config:
`configs/calibration_trapped32_goedel_minif2f.yaml`.

**Pre-registered read (recovery count out of 55):**
- 0–3 → trapped core sound, Phases 2/5/7 stand as reported.
- 4–10 → contamination real but bounded, claims need a stated recovery-rate caveat.
- \>10 → trapped core needs regenerating at proper sample counts; every downstream
  "trapped by construction" claim goes with it.

**Result: 6/55 recovered (10.9%) under uncapped pass@32.**

> **Correction (2026-07-25b):** the table below was originally published with
> `tokens_to_solve` mis-paired against problem names (a zip bug, not a harness bug —
> the attempt counts were always correct). External review caught it by noticing
> `amc12a_2021_p8`'s implied 44k tokens/attempt exceeded the cell's per-attempt cap.
> Re-verified directly against `agent_states/*.json`. Corrected table below; see
> DECISIONS.md 2026-07-25b for the full derivation.

| problem | attempts (of 32) | tokens to solve | vs. 128k baseline budget |
|---|---|---|---|
| amc12a_2021_p8 | 3 | 18,023 | within (14%) — **Lean-Workbook overlap, see caveat below** |
| algebra_apbon2pownleqapownpbpowon2 | 18 | 79,986 | within (63%) |
| amc12b_2021_p18 | 10 | 114,214 | within (89%) |
| aime_1997_p9 | 19 | 131,653 | borderline, 1.03× over |
| aime_1988_p8 | 23 | 317,328 | 2.5× over |
| imo_1968_p5_1 | 27 | 428,775 | 3.4× over |

**This result is two different findings, not one, and composition matters more than
a band label — reporting the count alone (even "3/55") obscures that one of the three
is a known training-set overlap:**

- **Iso-compute (governs Phases 2/5/7's "trapped by construction, baseline=0"
  claims): 3/55 within the original 128k budget, of which only 2/55 are clean —
  `amc12a_2021_p8` is a known miniF2F↔Lean-Workbook overlap (see below).** 3/55 sits
  exactly on the pre-registered 0–3/4–10 boundary, and the borderline case
  (`aime_1997_p9`, 1.03× over) tips it over — so this is not cleanly "band one."
  Report the composition (2 clean / 1 contaminated / 1 borderline), not a band.
- **Uncapped pass@32 (governs comparison to published pass@N results): 6/55 =
  10.9%.** A real but weaker claim than "trapped" — about compute availability, not
  about whether the agent loop's refinement strategy is well-allocated.

**Token-matched comparison, corrected:** only 3 of the 6 recoveries (`aime_1997_p9`,
`aime_1988_p8`, `imo_1968_p5_1`) needed more tokens than the original 128k baseline
had available; the other 3 solved within budget. So the genuinely interesting finding
— fresh independent samples beating the refinement-heavy loop at *equal* compute — is
supported by 3 cases, not 6. That's a narrower, more defensible claim: within-problem
sampling allocation is a live lever at the budgets where the agent loop's refinement
chains dominate the spend (128k, median 1 propose attempt — see the pass@N recount),
not a blanket "more tokens always would have won."

**Caution on the 10.9%:** the solved-at-attempt indices (3, 10, 18, 19, 23, 27 — two
per third of the 32-sample range) are flat, not decreasing. A flat hazard means the
recovery curve hasn't started flattening by N=32, so treat "≥11% at N=32, curve not
yet flat" as the honest caveat, not a fixed "11% contamination rate."

**Contamination flag:** `amc12a_2021_p8` — the cheapest and earliest of the 6
recoveries — is one of the 10 exact miniF2F↔Lean-Workbook overlaps already found by
the Phase 6 §0 disjointness gate (plausible AoPS-sourced train/eval leakage). Checked
the other 5 against the same overlap list: none match. Only this one recovery is
contamination-flagged, but it's also the cell driving the "1/55 solves within a
32k-token budget" control point below, so that control is itself compromised.

**Free re-analysis — Step C token-matched control (done):** Phase 2 Step C's own
diversity-injection arm, restricted to this same 55-problem population at
budget=32000, solved **2/55** (`amc12b_2021_p18` at 19,743 tokens;
`algebra_apbon2pownleqapownpbpowon2` at 3,893 tokens — this is the "1–2 cell blip"
already logged as noise on 2026-06-18e). Plain resampling at the same ≤32k cumulative
budget solves **1/55**, and that single win is `amc12a_2021_p8` — **the contaminated
one.** So the honest reading is: **resampling recovered ZERO clean problems at 32k.**
Both 2/55 and 1/55 are noise-level counts; the re-analysis's value is that "no clear
improvement over resampling at matched budget" is now a defensible sentence to put in
place of "no improvement over zero" — not that either arm discriminated a real effect.
Diversity injection's cheap solve of `algebra_apbon2pownleqapownpbpowon2` (3,893
tokens vs. plain resampling's 79,986-token solve of the same problem at uncapped
budget) remains a suggestive n=1 data point, no more. The equivalent re-analysis for
Phase 5 has not been done yet (residual).

**Free gate #1 — the `alloc_split=0.0` arm is settled without GPU spend, on the right
grounds.** Initial framing (refinement closes 20.7% of solves, compared to the OFAT
noise bar) was a category error — that's an attribution share, not a counterfactual,
and the noise bar measures between-arm deltas, not within-run attribution. Retracted.
**The load-bearing reason is Phase 1's own `budget_alloc__0` result**: a wash at ≤32k,
directionally harmful on ProofNet# — an actual counterfactual, and it points the same
direction. 20.7% (`results/phase0/ATTEMPTS_PER_BUDGET_TABLE.md`) stands as a
descriptive fact with this caveat attached. Cross-check (reported, not independently
verified in this repo): Goedel-V2's own self-correction mode nets ~+2pp at pass@32 —
the right order of magnitude for refinement's true counterfactual value, consistent
with 20.7% overstating it. **Not running this arm.**

**Free gate #2 — corrected.** The original comparison (ProofNet# @128k propose
mean 4.71 vs. miniF2F 1.94) used the OVERALL population, not the trapped-core
population specifically — an apples-to-oranges error. Recomputed directly from
`agent_states/*.json`, restricted to each benchmark's actual trapped-core problem
list, summed propose attempts across all 3 baseline seeds per problem:

| | n | mean | median | min | max |
|---|---|---|---|---|---|
| miniF2F trapped | 55 | 11.89 | 11 | 5 | 35 |
| ProofNet# trapped | 150 | 14.71 | 13 | 6 | 47 |

These are close, not a 4× gap. **Corrected leverage**: the miniF2F calibration cell's
real leverage was 32/11.89 ≈ **2.7×** existing coverage, not the ~10× a "union of ~3"
framing implied. Matching that leverage for ProofNet# needs **N≈40 samples**
(32/11.89 × 14.71), pricing at **≈157 GPU-h** (150×40, scaled from job 11682365's
observed rate) — not the ≈125 GPU-h (N=32) or ≈250 GPU-h (N=64) estimates floated
earlier, both built on the same uncorrected baseline.

**No-go, confirmed.** ≈157 GPU-h (≈3.1× the ask-first line) to put a caveat on one of
eight converging nulls, in a one-paper world where Phase 7 isn't the headline — the EV
isn't there. **Design-advice reversal, logged for the record**: last round's "breadth
over depth" (150×16/150×12) was right when coverage looked like ~1 attempt/problem
(the overall-population average, wrongly applied here). Now that the trapped
population specifically already has broad shallow coverage (~13 attempts), depth is
what would add information, not breadth — if this is ever revisited, ~40 problems ×
32 samples (~33 GPU-h), not 150 × 12–16.

**Free substitute — Phase 7 already has its own resampling control; no new work
needed.** Checking `results/phase7/STEPWISE.md` found Phase 7's Mode 3 track already
ran a "matched fresh-resample control (same names, fresh session, zero re-grounding)"
on the full 150-problem population, specifically to rule out whether Mode 3's one raw
solve was caused by re-grounding or a cold-start artifact. **That control got 0/150.**
This is a real, already-existing, designed control — stronger evidence than anything
a new inferred coverage argument could add. Phase 7's null does NOT need a Step
C-style "beat resampling, not zero" caveat — it already tested resampling directly and
found nothing. It DOES need the Check B correction below.

**Free substitute — fold Check B's flips into Phase 7's denominator.** All 3
Goedel×ProofNet# heartbeat-reverify flips (`Ireland__Rosen__exercise_12_12`,
`Rudin__exercise_4_4b`, `Rudin__exercise_5_5` — `results/audit/AUDIT_FINDINGS.md` Task
B) are confirmed members of the 150-problem trapped list. **Phase 7's population is
147, not 150** — 3 were already known-recoverable via an unrelated scoring fix before
Phase 7 ran.

**Coverage stated explicitly for the eventual writeup**: miniF2F trapped ≈ 11 median
independent proposals (3 seeds combined) before the calibration cell found 2 clean / 1
contaminated recoveries at N=32 (2.7× leverage). ProofNet# trapped ≈ 13 median
independent proposals, plus a dedicated single-sample fresh-resample control — both
came back at/near zero. miniF2F's ≥11% at N=32 should be read as a weak upper bound on
what deeper resampling might find on ProofNet#, given the similar (not 4×-different)
starting coverage and the modest (2.7×) leverage that produced it — not a confident
estimate, and not something worth spending ≈157 GPU-h to pin down more precisely.

**Free re-analysis — Phase 5, corrected scope.** Checking further found Phase 5's
"Goedel 1, DeepSeek 0" result was a **10-cell-per-model pilot subsample of the
ProofNet# trapped core** (not miniF2F, not the full 150 — problem names in the pilot
log, e.g. `Herstein_3_2_21`, `Rudin_3_2a`, are ProofNet#-style; SYNTHESIS.md's original
one-line summary doesn't say this). Those 10 problems already carried ~13 independent
propose attempts with zero solves before the pilot found 1 (Goedel, via extending an
existing trajectory past 128k — a different lever than fresh resampling, so it isn't
in tension with "0 clean resampling recoveries" elsewhere). No calibration cell
touched this population.

## Bottom line so far

- **At iso-compute (the number governing Phases 2/5/7's "trapped by construction"
  claims), report composition, not a band: 3/55 within budget, only 2/55 clean of
  known contamination, 1/55 borderline.** This sits on, not cleanly inside, the
  pre-registered 0–3 boundary. Phases 2/5/7 stand close to as reported but the
  precise number to cite is "2 clean," not "3" or "band one."
- At uncapped pass@32 (the number governing comparison to published pass@N results),
  6/55 (10.9%) recover, and the recovery hazard is flat through N=32 — report as
  "≥11% at N=32, curve not yet flat," not a fixed contamination rate.
- Every claim resting on "trapped ⇒ 0% baseline by construction" (Phase 2 Step C,
  Phase 5, Phase 7) should get both numbers stated: the iso-budget figure (governs the
  claim as originally made) and the pass@32 figure (governs any comparison to
  published work), not a single blended caveat.
- The Step C null is now better stated as "no clear improvement over token-matched
  plain resampling" — and specifically, resampling's only matched-budget win is itself
  contamination-flagged, so **resampling recovered zero clean problems** at 32k.
- `amc12a_2021_p8` is a known miniF2F↔Lean-Workbook overlap (Phase 6 §0 gate);
  footnote it wherever any of these recovery numbers are cited.
- **The `alloc_split=0.0` GPU cell is not worth running** — free gate #1 above shows
  refinement closes 20.7% of Goedel×miniF2F's solves, 7.8–15.5× the noise bar, and
  Phase 1 already found the same lever directionally harmful on ProofNet#. Settled
  without GPU spend.
- **The ProofNet# calibration cell's expected payoff is smaller than miniF2F's** —
  free gate #2 shows ProofNet# already gets ~4× more independent samples at the
  median (4 vs. 1) than miniF2F did before recovering 10.9%. Treat miniF2F's number as
  an upper bound, not a like-for-like estimate, when deciding whether to spend on it.
- The heartbeat-bug framing in SYNTHESIS.md ("scoring-only") is inaccurate for
  miniF2F and needs correcting.
- The "miniF2F saturates" language should be corrected to describe a data-exhaustion
  plateau, not a genuine ceiling.
- The 2k-token budget point should be footnoted as attempt-starved (median 1 attempt).

Applied to SYNTHESIS.md as marked, dated corrections (see the corrections log there) —
not silent edits, per the review's guidance on preserving the audit trail. `paper/floor/`
itself is still untouched (WS2 pause holds until you reopen it).

## Resolved this round

1. **SYNTHESIS.md corrections — applied**, as marked/dated corrections with a
   corrections log (documentation, not `paper/floor/`). Now 6 corrections total.
2. **`alloc_split=0.0` cell — not run.** Original reasoning (20.7% vs. the OFAT noise
   bar) was a category error, retracted. Load-bearing reason: Phase 1's own
   `budget_alloc__0` result (a real counterfactual — wash at ≤32k, harmful on
   ProofNet#). 20.7% kept as a descriptive fact with that caveat. Cross-checked
   (user-reported, not independently verified here) against Goedel-V2's own
   self-correction mode (~+2pp at pass@32) as the right order of magnitude.
3. **ProofNet# trapped core calibration cell — NO-GO.** Gate #2's original "4× gap"
   was computed over the wrong (overall, not trapped-restricted) population — corrected
   to miniF2F trapped ≈11 vs. ProofNet# trapped ≈13 median independent proposals, a
   small gap, not 4×. Real leverage of the miniF2F cell was 2.7×, not ~10×; matching it
   for ProofNet# needs ~40 samples/problem (~157 GPU-h, not ~125 or ~250) — ~3× the
   ask-first line for one of eight converging nulls in a one-paper world. Not running
   it. Design-advice reversal logged: breadth-over-depth was right when coverage
   looked like ~1/problem; now that the trapped population has ~13, depth (not
   breadth) is what would add information if ever revisited.
4. **Phase 7's null — already had a resampling control, corrected denominator.**
   `results/phase7/STEPWISE.md` already ran a matched fresh-resample control (0/150) —
   no new work needed; it does not need a Step C-style caveat. Denominator corrected to
   147 (3 of the 150 are pre-known recoverable via Check B's heartbeat fix, unrelated
   to re-grounding).
5. **Phase 5's scope corrected.** "Goedel 1, DeepSeek 0" was a 10-cell-per-model
   ProofNet# pilot subsample, not miniF2F, not the full 150 — logged and reflected in
   SYNTHESIS.md; the 1 solve is a different lever (extension) than resampling.
6. **F2's failure taxonomy re-derived against raw Lean error text.** Classifier code is
   clean (reproduces the exact reported numbers). Real finding: F2's cell-level label
   is the single dominant *terminal* failure, which buries earlier premise errors the
   model recovered from. Measured across the full attempt history: miniF2F 8.0%
   (consistent with the 0.0% terminal figure), **ProofNet# 51.9%** (vs. the reported
   1.0% terminal figure) — a real, ProofNet#-specific correction to the taxonomy-based
   case for "retrieval is doomed by construction." Does not reverse the actual
   retrieval kill decision, which rests on Phase 1's direct BM25 ablation (−36 net
   flips), independent evidence this correction doesn't touch.

## Residuals (logged as known scope limits, not to-dos)

- DeepSeek's trapped cores remain uncalibrated on both benchmarks — the miniF2F result
  suggests the effect is small, and DeepSeek's own baselines already match published
  numbers.
- No edits to `paper/floor/` — sprint is closed; **recommending WS2 reopen** (per
  DECISIONS.md 2026-07-25g), awaiting your confirmation.
