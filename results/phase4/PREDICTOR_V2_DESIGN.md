# WS6 item 4: Phase 4 predictor improvement — pre-registration

Written before any code change, per the user's 2026-07-26 guidance ("pre-register the read before you
run it" + "guard the CV... hold out seeds, not just problems"). CPU-only, reuses existing logged attempt
data (`agent_states/*.json`) — no GPU re-run, so richer features are limited to what's derivable from
already-logged `completion_tokens` / `feedback` / `kind` / `proof` per attempt (no logprobs: the harness
does not log them, and re-running to capture them would not be CPU-only or cheap).

## Current baseline (results/phase4/ALLOCATION.md §4)
Problem-grouped 5-fold CV ROC-AUC, ProofNet#, logistic regression beats GBT at every checkpoint:
| c | goedel AUC | deepseek AUC |
|---|---|---|
| 2k | 0.64 | 0.47 |
| 4k | 0.71 | 0.65 |
| 8k | 0.75 | 0.67 |
| 16k | 0.72 | 0.72 |
| 32k | 0.46* | 0.62 |
DeepSeek's realized policy is WEAK/not robust: pooled +10-14% (below the 15% bar), per-seed
+5/+9/**-51%** (a seed-2 collapse) — the predictor misranks on seed 2 specifically.

## Candidate new features (all derivable from existing logs, no re-run)
1. **Error-type histogram** (parse `feedback` prefix): fraction of attempts that are
   syntax/parse-error, elaboration-error ("unsolved goals"), infra-error (REPL_INFRA_ERROR), vs.
   "Failed at step N" — a richer signal than raw depth alone (e.g. an early hard syntax wall vs. a
   late semantic wall may carry different eventual-solve odds).
2. **Depth trajectory shape**, not just early/late split: linear-fit slope of best-depth-so-far vs.
   cumulative tokens, and its residual variance — replaces the current binary `depth_growth` with a
   continuous progress-rate signal.
3. **Token efficiency**: tokens spent per unit of depth gained (`tokens_so_far / max(best_depth,1)`) —
   a cell burning many tokens for little depth is a different failure mode than one making steady
   depth-per-token progress.
4. **propose/refine mix**: fraction of attempts that are `kind=="refine"` vs `"propose"` — a cell stuck
   refining the same failed approach vs. one still generating fresh proposals may carry different odds.
5. **Error diversity**: count of distinct normalized error messages seen (separate from F1's
   opening-tactic diversity) — is the model hitting the same wall repeatedly or different walls.

## Pre-registered decision rule (committed before running)
- **AUC gain < 0.05 at the best checkpoint (either model) OR DeepSeek's per-seed realized saving is
  still inside 1 seed-std of its current spread (roughly [+5,+9,-51]%, i.e. still straddling zero/
  negative on at least one seed)** → the model-dependence caveat in `ALLOCATION.md`/the paper's
  allocation section STANDS AS-IS. No framing change; log the negative/marginal result and stop.
- **AUC ≥ 0.85 at some checkpoint AND DeepSeek's per-seed realized saving clears 1σ (all three seeds
  positive, no seed collapsing toward the current -51%)** → the constructive section's model-dependent
  framing is REVISED: recompute the frontier with the new predictor, update `ALLOCATION.md` and the
  paper's allocation section to drop "one-model-robust."
- Any result strictly between these two bands is reported honestly as "improved but still
  inconclusive," with the numbers, and does NOT trigger a framing change on its own.

## CV guard (the user's specific concern: overfitting via seed non-holdout)
The existing `GroupKFold` already groups by `problem_name` (correct: prevents the same problem's
seeds from splitting across train/test). The NEW guard adds a **seed holdout on top**: seed 2 (the
one showing DeepSeek's -51% collapse) is held out ENTIRELY from feature engineering and model
selection. All feature-set decisions (which of the 5 candidates above to keep) are made using
5-fold GroupKFold CV on seeds 0-1 ONLY. The selected model is then evaluated exactly ONCE on the
held-out seed-2 data, reported alongside the seeds-0-1 CV AUC — not averaged into it. **If the
held-out-seed AUC diverges sharply from the seeds-0-1 CV AUC (e.g. by more than ~0.1), that is
flagged explicitly as a sign of overfitting to the small feature-engineering set, not treated as a
successful improvement**, per the user's explicit instruction not to celebrate a jump without
checking it first.

## Status
Design written 2026-07-26, before any implementation. Next: implement the 5 candidate features in
`src/atp/alloc/features.py` (additive — extend `FEATURE_NAMES`, keep the 8 existing features
unchanged so this is a strict superset, not a replacement), extend `predict.py`'s CV harness with the
seed-holdout evaluation, run, and apply the decision rule above verbatim.

## Result 2026-07-26 — does NOT clear the bar; ALLOCATION.md/paper framing STANDS

Ran `scripts/phase4_predictor_v2.py` (5 new features, seed-holdout guard as designed above).
**Max AUC gain (v2 vs v1, both on the same seeds-{0,1}-only CV protocol) across all model x
checkpoint cells: +0.033** -- under the pre-registered 0.05 bar. Several cells show v2 AUC LOWER than
v1 (e.g. DeepSeek@32k: 0.711 -> 0.604; Goedel@4k: 0.710 -> 0.663), i.e. the richer features add noise
rather than signal at this sample size once evaluated honestly (seeds 0,1 only, not the full 3-seed
pool the original v1 numbers used -- so these v1(s01) numbers are NOT directly comparable to
`ALLOCATION.md`'s original 3-seed v1 AUCs; the comparison that matters is v1 vs v2 within the SAME
restricted protocol, which is what's reported). Held-out-seed-2 AUCs (evaluated once, per the guard)
are mediocre across the board (0.48-0.69), consistent with no genuine, robust gain -- exactly the
outcome the CV guard was designed to catch before it got mistaken for one.

**Applying the pre-registered decision rule verbatim**: "AUC gain < 0.05 at the best checkpoint (either
model)" is satisfied (+0.033 < 0.05) -- this alone triggers the NO-CHANGE branch, independent of the
DeepSeek per-seed condition. **VERDICT: the model-dependence caveat in `ALLOCATION.md` and the paper's
allocation section STANDS AS-IS. No framing change, no frontier recompute.** WS6 item 4 CLOSED,
negative result, logged honestly with the numbers per the pre-registration's own instruction not to
skip reporting a negative just because it wasn't the hoped-for outcome. Full results:
`results/phase4/predictor_v2.json` / `PREDICTOR_V2_RESULT.md`.
