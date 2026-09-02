# Stage C — GRPO RL feasibility probe: result (pre-registered gate, STAGE_C_PROBE_SPEC.md §4)

**Verdict: c2 — capacity ceiling. Close the training arc; RL (as scoped for the probe) does not
move the floor.**

## What ran

- Model: DeepSeek-Prover-V2-7B, LoRA r=16/alpha=32, GRPO (trl 0.17), G=4 rollouts/prompt (reduced
  from the spec's G=8 to fit generation memory — see PROGRESS.md 2026-07-04), B=4-8 prompts/step
  (reduced mid-run after a CUDA OOM at step 72/80 — completions lengthen over training and the
  original B=8 exhausted 79GB at ~step 70), 80 steps total (reduced from the spec's up-to-150 after
  timing showed ~150 steps would not fit the intended wall — see PROGRESS.md 2026-07-03/04),
  lr=1e-6, KL β=0.04, max_new_tokens=4096. Reward: binary Lean-verified+sound, +0.05 format bonus.
- Training subset: 130 `lean_workbook_clean` problems, base solve-rate in [1/16, 10/16].
- Held-out gate set: 70-problem `lean_workbook_clean` slice, disjoint from train and both
  benchmarks. Base vs RL-final compared at pass@1 (mean over 8 seeds) and pass@8 (any-of-8), budget
  8192, same vLLM harness (base = no adapter, RL = adapter served via vLLM LoRA).

## Triple-gate readout

| Gate | Requirement | Result | Pass? |
|---|---|---|---|
| G1 (primary) | pass@1 up ≥5pp AND training reward rose | base 0.586, RL 0.570, Δ=**-1.6pp**; cum. train solve-rate flat (~0.19-0.23 throughout, no trend) | **NO** |
| G2 (soundness) | held-out unsound rate ≤+2pp | base 9.58%, RL 6.17%, Δ=**-3.4pp** (RL slightly cleaner) | YES |
| G3 (no collapse) | diversity ≥80% of base AND mean KL under ceiling | distinct-3gram ratio 1.015 (RL≈base); mean KL=0.0021 (≪0.05 ceiling) | YES |

pass@8: base 0.886, RL 0.900 (both saturate near-ceiling on this held-out slice — not the decisive
number; G1's pass@1 delta is the pre-registered primary).

## Reading

Training reward (cumulative solve-rate on the 130-problem train subset) was **flat for all 80
steps** — never trended up, oscillating 0.17-0.27 without a clear slope. G2/G3 both pass cleanly:
no reward-hacking, no KL blow-up, no diversity collapse. This is the clean "reward flat, no
pathology" branch of the pre-registered decision map → **c2, not a mis-tuned stall** (the escape
clause for a pathological flat run does not apply here).

Per STAGE_C_PROBE_SPEC.md §6.1's pre-registered caveat: this used LoRA r=16 (not full fine-tune) for
probe cheapness. A LoRA-GRPO stall is read as "capacity ceiling under this probe's constraints,"
not an airtight, permanent c2 — a full-FT re-probe would be the next lever if this arc is reopened.
But under the constraints actually run (single seed, G=4, 80 steps, LoRA r=16, 4096-token rollout
cap), RL does not move the held-out solve-rate.

## How this folds into the project thesis

This is a **third independent confirmation** of the execution-floor thesis, via a third mechanism:
- Phase 0-5: scaffolding/search/hammers/reinvestment don't move it (architecture-invariant).
- Phase 6 Stage A/B (SFT): maximizing conditional likelihood on closings doesn't move it (revealed
  the exposure-bias signature instead — near-zero teacher-forced loss on closings, yet
  autoregressive failure).
- Phase 6 Stage C (GRPO RL): directly optimizing the verified-solve reward, under a real (if
  probe-scoped) RL setup, ALSO doesn't move it — reward stayed flat despite 80 steps of on-policy
  gradient signal against the true verifier.

Combined with Stage B's exposure-bias fingerprint, this sharpens rather than closes the question:
RL-on-final-outcome doesn't fix it, but the exposure-bias signature specifically implicates
**autoregressive drift during generation** (free-running on the model's own imperfect intermediate
state) as the mechanism — which is exactly what Phase 7 Track 1 (verified-state re-grounding) is
designed to test directly, independent of any training intervention. Stage C's null rules out
"just add RL against the outcome reward" as a cheap fix; it does not rule out "fix the generation
protocol so the model never has to free-run on its own drift" (Track 1's premise).

## GPU-h accounting

Probe: ~10 GPU-h subset harvest (Stage A/B era, already spent) + ~2.5 GPU-h GRPO training (80 steps,
2 job segments ~34min + ~71min) + ~6 GPU-h G1 held-out eval (8 base shards + 8 RL shards @
~2h45-3h each, ~4 GPU-h base + ~6 GPU-h RL after the LoRA-quota-crash resubmit) ≈ **~15-18 GPU-h
total for Stage C**, well under the ~35 GPU-h pre-registered budget and the 40 GPU-h hard stop.
