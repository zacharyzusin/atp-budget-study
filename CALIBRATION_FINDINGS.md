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

**Result: 6/55 recovered (10.9%) → falls in the 4–10 band.**

| problem | attempts (of 32) | tokens to solve |
|---|---|---|
| amc12a_2021_p8 | 3 | 131,653 |
| amc12b_2021_p18 | 10 | 317,328 |
| aime_1997_p9 | 19 | 79,986 |
| aime_1988_p8 | 23 | 18,023 |
| algebra_apbon2pownleqapownpbpowon2 | 18 | 114,214 |
| imo_1968_p5_1 | 27 | 428,775 |

**Token-matched comparison (bonus, since completion_tokens was logged per-attempt):**
the original 128k-budget baseline's single most expensive solve anywhere in the whole
run cost less than 4 of these 6 recoveries. Plain resampling reached proofs the
refinement-heavy agent loop structurally could not — not because it had more total
tokens available, but because it wasn't spending them on refinement chains off a bad
first draft. This is directly relevant to the project's founding question about
budget allocation, independent of the calibration purpose.

## Bottom line so far

- The trapped core is legitimate as a population — 89% (49/55) genuinely resist plain
  resampling — but it is not perfectly clean.
- Every claim resting on "trapped ⇒ 0% baseline by construction" (Phase 2 Step C,
  Phase 5, Phase 7) needs an explicit ~11% recovery-rate caveat added before it's
  reused in any writeup.
- The heartbeat-bug framing in SYNTHESIS.md ("scoring-only") is inaccurate for
  miniF2F and needs correcting.
- The "miniF2F saturates" language should be corrected to describe a data-exhaustion
  plateau, not a genuine ceiling.
- The 2k-token budget point should be footnoted as attempt-starved (median 1 attempt).

None of these corrections have been applied to SYNTHESIS.md yet — pending your call
on whether that counts as "documentation" (fine to do now) or falls under the
`paper/floor/` pause (holds until WS2 reopens).

## Open questions (yours to decide)

1. Apply the four corrections above to SYNTHESIS.md now, or hold until WS2 formally
   reopens?
2. Run the same calibration cell on the ProofNet# trapped core (150 problems,
   deferred pending this miniF2F result) — or is this miniF2F result sufficient to
   settle the population-soundness question project-wide?

## Explicitly not done in this sprint

- No new experimental arm (e.g. the decomposition-axis scaffolding gap raised in the
  original critique) — excluded from this sprint's authorization.
- No re-derivation of F2's failure taxonomy against raw Lean error codes.
- No edits to `paper/floor/` (WS2 still paused).
