# Stage C — GRPO RL feasibility probe: concrete spec (for pressure-test BEFORE any GPU)

Decided upstream (STAGE_C_DECISION.md): gated GRPO RL probe on DeepSeek-Prover-V2-7B, ~40 GPU-h
hard cap, to separate c1 (exposure-bound → RL moves floor) from c2 (capacity-bound) from
"neither (hack/mistune)". This doc fills in the numbers. Nothing runs until you sign off.

## 0. Pre-probe smoke (validate premise first, ~1 GPU-h) — GATE on all three
- (a) **Reward signal exists:** chosen train subset has base solve-rate in the sweet spot
  (below). If base solves ~0 even on "easy" Workbook at the rollout budget, GRPO has no gradient
  → fix the subset/budget before spending, don't misread as c2.
- (b) **Reward function correct:** known-good proof → reward 1; `sorry`/`admit` proof → 0
  (soundness gate fires); malformed/non-parseable → 0; a `native_decide`/axiom-cheat → 0.
- (c) **Trainer smoke:** 2–3 GRPO steps, reward + KL logged finite, checkpoint resumes.
Only launch the full probe if (a)+(b)+(c) pass.

## 1. Training problem subset
- Source: `lean_workbook_clean` (140,012, decontaminated vs BOTH eval sets — §0 DISJOINTNESS.md).
- Selection: run DeepSeek **base** at budget 8192, K=16 samples, over a ~2000-problem random
  slice; bucket by empirical solve-rate; **keep problems with base solve-rate in [1/16, 10/16]
  (≈6–63%)** — the sweet spot where GRPO gets dense advantage signal (excludes 0 = no signal and
  16/16 = no headroom). Target **~256 training problems**.
- Cost: ~2000×16×8192-tok gen + Lean verify ≈ **~10 GPU-h** (reuses harvest infra).

## 2. Held-out gate set (SEPARATE from train AND from miniF2F/ProofNet#)
- ~200-problem `lean_workbook_clean` slice, disjoint from the 256 train problems and both eval
  sets, similar difficulty band. Measure base vs RL-final **pass@1 and pass@8 @ budget 8192**.
- Rationale: the probe question is "can RL move verified solve-rate on UNSEEN problems at all?"
  A Workbook held-out slice answers that cheaply and cleanly. The **OOD benchmark floor-move
  (miniF2F/ProofNet#) is the FULL-run gate, not the probe gate** — keeps the real benchmark's
  validity unspent and avoids overfitting the probe to it. (Open decision — see §6.)

## 3. GRPO config
- LoRA r=16, alpha=32 (matches Stage A/B arms — single-variable-ish).
- G=8 rollouts/prompt; B=16 prompts/step; up to **~150 steps** (early-stop on gate signal or
  reward plateau).
- lr=1e-6; **KL β=0.04** initial (prevents the RFT-style collapse that made A hurt −13..−20pp;
  raise if KL blows up); rollout temp=1.0, top-p=0.95; **max_new_tokens=4096** (cost control).
- **Reward = binary:** +1 iff Lean-verified AND passes the soundness gate (reject
  sorry/admit/loophole/unproven-axiom/`native_decide`-abuse), else 0; +0.05 format bonus for a
  parseable ```lean4 block (avoids degenerate non-parseable rollouts stalling learning).
  **No progress/depth shaping in the probe** — keeps the reward-hacking surface minimal; add
  dense shaping only in the full run if binary reward proves too sparse.

## 4. Success gates (pre-registered, numeric) — a PASS needs ALL THREE
- **G1 PRIMARY — held-out solve-rate up:** RL-final held-out pass@1 ≥ base **+5pp absolute**
  (clears ≥2× the SFT-study per-seed std ~1.5pp) AND training-reward curve rose. Reward-up but
  held-out-flat = overfit/hack, NOT c1.
- **G2 soundness not degraded:** held-out loophole/malformed/false-positive rate rises **≤ +2pp**
  vs base (base-vs-RL, same set). RL "working" by gaming the verifier is a finding, not floor-move.
- **G3 no collapse:** sampled-proof diversity (distinct-trigram ratio / token entropy) retains
  **≥80%** of base AND mean KL-to-base stays under a pre-set ceiling (reward not bought by KL blow-up).

### Decision map
- All three PASS → **c1**: RL moves the floor → fund full Stage C (two models, 3 seeds, OOD
  benchmarks, +progress shaping if needed).
- Reward rose but G1 fails, or G2 fails → **hack/overfit → NO-GO** (not c1).
- Reward FLAT on train, no pathology → **c2 capacity ceiling → close the training arc.**
- Reward flat WITH a KL/diversity pathology → **retune (β/lr/reward) + re-probe** (escape clause;
  a mis-tuned stall is NOT c2).

## 5. GPU-h budget
- subset harvest ~10 + GRPO ~20–25 + base/RL held-out eval ~3 ≈ **~35 GPU-h; HARD STOP at 40**
  (abort + report per CLAUDE.md rule 8). Lean verification is CPU (Phase-0 concurrency infra), not
  counted in GPU-h but is the throughput bottleneck to watch.

## 6. Open decisions — RESOLVED (user, 2026-07-01: "yes do what you recommend")
1. **LoRA vs full-FT for the probe → LoRA r=16.** Cheap, single-variable-clean vs the SFT arms.
   Pre-registered caveat retained: a LoRA-GRPO stall is read as "retune/consider full-FT before
   concluding c2" (escape clause), NOT an immediate airtight c2. If the probe stalls *cleanly*
   (no KL/diversity pathology) we note the LoRA-rank caveat when reporting c2.
2. **Held-out gate → Workbook slice** for the probe (cheap, clean feasibility read; keeps the OOD
   benchmark validity unspent). OOD benchmarks are the FULL-run gate only.
3. **Rollout cap → max_new_tokens=4096.** Accepted probe limitation; targets the F2/F3
   short-closing regime. Full run would revisit the horizon.
4. **Reward → binary** (+soundness gate, +0.05 format bonus), NO progress shaping in the probe —
   minimizes the hacking surface G2 must police. Add shaping only if the §0 smoke shows binary
   reward is too sparse to produce any gradient on the subset.

## 7. Infra to build (all testable before GPU)
- GRPO trainer via trl 0.17 GRPOTrainer + custom Lean-verify reward server (reuse eval verifier +
  soundness gate + Phase-0 concurrency). Subset-selection harvest (mostly have it). Diversity/KL/
  soundness logging. Test-first per project rule.
