# External Calibration Sprint — Findings So Far

**Status:** bounded validation sprint, still in progress. `paper/floor/` (WS2) remains
PAUSED throughout — nothing here has been written into the paper yet.

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

**This result is two different findings, not one, and they answer two different
questions:**

- **Is the trapped core sound at iso-compute (the number that governs Phases 2/5/7's
  "trapped by construction, baseline=0" claims)?** 3/55 clean, 4/55 counting the
  borderline case — **lands in the pre-registered 0–3 "sound" band, not the 4–10 band
  originally reported.** Phases 2/5/7 stand close to as reported; the corrections
  below apply mainly to precision of language, not retraction.
- **Is it trapped in the literature's pass@32 sense (uncapped compute, the number
  that governs any comparison to published pass@N results)?** 6/55 = 10.9%, still the
  4–10 band. This is a real but weaker claim than "trapped" — it's about compute
  budget, not about whether the agent loop's refinement strategy is well-allocated.

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
budget solves **1/55** (`amc12a_2021_p8`, contamination-flagged). This converts the
Step C null from "didn't beat zero" to "didn't clearly beat resampling at matched
budget" — a stronger, more defensible sentence, per the review's suggestion.
Interestingly, diversity injection solved `algebra_apbon2pownleqapownpbpowon2` far
more cheaply (3,893 tokens) than plain resampling ever did for the same problem
(79,986 tokens at uncapped budget) — suggestive, but n=2 vs n=1 single-seed is nowhere
near enough to overturn F5's symptomatic-not-causal verdict. The equivalent
re-analysis for Phase 5 has not been done yet (residual).

## Bottom line so far

- **At iso-compute (the number governing Phases 2/5/7's "trapped by construction"
  claims), the trapped core is sound: 3/55 (possibly 4/55) recover, inside the
  pre-registered 0–3 band.** Phases 2/5/7 stand close to as reported.
- At uncapped pass@32 (the number governing comparison to published pass@N results),
  6/55 (10.9%) recover, and the recovery hazard is flat through N=32 — report as
  "≥11% at N=32, curve not yet flat," not a fixed contamination rate.
- Every claim resting on "trapped ⇒ 0% baseline by construction" (Phase 2 Step C,
  Phase 5, Phase 7) should get both numbers stated: the iso-budget figure (governs the
  claim as originally made) and the pass@32 figure (governs any comparison to
  published work), not a single blended caveat.
- The Step C null is now better stated as "no clear improvement over token-matched
  plain resampling" (2/55 vs 1/55, the 1 being contamination-flagged) rather than "no
  improvement over zero."
- `amc12a_2021_p8`, one of the 6 pass@32 recoveries, is a known miniF2F↔Lean-Workbook
  overlap (Phase 6 §0 gate) — footnote it specifically.
- The heartbeat-bug framing in SYNTHESIS.md ("scoring-only") is inaccurate for
  miniF2F and needs correcting.
- The "miniF2F saturates" language should be corrected to describe a data-exhaustion
  plateau, not a genuine ceiling.
- The 2k-token budget point should be footnoted as attempt-starved (median 1 attempt).

Applied to SYNTHESIS.md as marked, dated corrections (see the corrections log there) —
not silent edits, per the review's guidance on preserving the audit trail. `paper/floor/`
itself is still untouched (WS2 pause holds until you reopen it).

## Resolved this round

1. SYNTHESIS.md corrections — **applied**, as marked/dated corrections with a
   corrections log (documentation, not `paper/floor/`).

## Open questions (yours to decide)

1. **ProofNet# trapped core (150 problems) calibration cell.** Priced at roughly
   3× miniF2F's cost by problem count (job 11682365 ran ~46 GPU-h aggregate across 8
   shards; 150/55 scaling → **~125 GPU-h estimate**, well over the 50 GPU-h ask-first
   line, same treatment as WS1.1). Worth running because Goedel×ProofNet# carries both
   the project's one clean positive result (+26%±7%, Phase 4) and Phase 7's headline
   null (0/150) — if plain resampling recovers a nontrivial fraction, that null needs
   the same two-number treatment this miniF2F result got. Full 150 or skip — a
   stratified subsample only estimates the rate, not the per-problem comparison
   against Phase 7 that's the actual reason to run it. Your call on the spend.
2. **`alloc_split=0.0` cell at B=128k (Goedel×miniF2F, 3 seeds)** — the minimal test
   of "plain resampling beats the refinement loop at the budget where refinement
   dominates spend," framed as extending an existing ablation (`budget_alloc__0`) to
   the untested budget tier rather than a new arm. Cheap (existing config/code, no new
   machinery) but it's compute spent on a new question, not validation of a committed
   result — outside this sprint's original authorization. Flagging rather than
   running it.

## Residuals (logged, not blocking)

- DeepSeek's trapped cores remain uncalibrated on both benchmarks (only Goedel×miniF2F
  has a resampling control now).
- F2's failure taxonomy re-derivation against raw Lean error codes is still undone.
- Phase 5's token-matched re-analysis (same shape as the Step C one above) not yet
  done.
- No edits to `paper/floor/` (WS2 still paused).
