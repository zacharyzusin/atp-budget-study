# Stage C (GRPO RL) — go / no-go memo

Status: DRAFT for user decision. Written while the 3-seed eval fill runs (does not depend on it;
the seed-0 two-model null below is already locked and the 3-seed bars only tighten it).

## What we have established (Stages A + B)

Closing-targeted SFT (Stage B) and generic RFT (Stage A) were tested against base on **both**
Goedel-Prover-V2-8B and DeepSeek-Prover-V2-7B, 3 seeds, held-out miniF2F + ProofNet#.

- **B (closing-targeted SFT) does NOT lift the execution floor.** Paired B−base @32k sits within
  roughly −2 .. +0.4pp on every (model, benchmark) cell — never the pre-registered ≥+3pp.
- This holds **despite** very low closing-token training loss (Goedel ~0.07, DeepSeek 0.0695):
  the model assigns high *conditional* probability to the correct closings yet still fails to
  *generate* them autoregressively. That gap is the signature of **exposure bias**, not missing
  knowledge.
- **A (generic RFT) actively hurts** (−13..−19pp @32k miniF2F): SFT on self-generated proofs
  narrows the search distribution.

Conclusion locked across two models: **teacher-forced likelihood training cannot move the
F2/F3 execution floor.** Two non-exclusive explanations remain:
  (c1) **exposure-bound** — the policy can represent the closings but its sampling distribution
       doesn't place them on-trajectory; or
  (c2) **capacity-bound** — the model fundamentally can't, and no training helps.

## Why Stage C (GRPO RL) is the sharp test that separates c1 from c2

GRPO optimizes the **actual generation distribution** against a verifier (Lean) reward, not the
conditional likelihood SFT already maxed out. It is the one lever that directly attacks exposure
bias:
- If the floor is **c1 (exposure-bound)**, RL is exactly the tool that should move it where SFT
  could not → a positive result would be the headline of the whole training arc.
- If the floor is **c2 (capacity-bound)**, RL also fails → that *strengthens* the null into a
  clean "this 8B-class prover is at its execution ceiling; neither SFT nor RL moves it," which is
  a publishable, well-isolated claim.

Either outcome is informative. The SFT null is precisely what makes the RL test interesting
rather than redundant.

## Cost (the real reason this is a user decision)

GRPO with Lean-in-the-loop is expensive: per step we sample K proofs per problem and **verify
every one in Lean** (the bottleneck, not the forward pass). A meaningful single-model pilot is
likely **>50 GPU-h** → crosses the CONVENTIONS.md approval line and needs an explicit OK. A full
two-model, multi-seed RL sweep would be multi-day.

## Options

1. **Minimal RL feasibility probe first (RECOMMENDED).** One model (DeepSeek — stronger basis),
   small problem set, short GRPO run, pre-registered success gate (e.g. reward/solve-rate on the
   *training* problems moves up meaningfully within budget). Cheap-falsification-first, matching
   our standing "validate premise before building" rule. If the gate passes → fund the full
   Stage C; if it stalls → c2 confirmed cheaply, close the arc. Est. pilot: ~30–60 GPU-h.
2. **Full Stage C directly.** Skip the probe, run the pre-registered RL sweep on both models.
   Highest information if it works; highest cost if c2 is true. Multi-day, >>50 GPU-h.
3. **Close the training arc at the SFT null (no-go).** Declare "neither generic nor
   closing-targeted SFT lifts the execution floor on two provers" and write up under the
   existing "Budget, Not Scaffolding / training-not-size" framing; list RL as future work.
   Zero additional GPU.

## Recommendation

**Option 1.** The two-model SFT null genuinely motivates a *targeted* RL test (it's the
exposure-bias hypothesis's decisive experiment), but the capacity-bound risk and GPU cost mean
we should gate it on a cheap feasibility probe with a pre-set threshold rather than commit to a
full sweep up front.

## DECISION (2026-06-29, user): Option 1 — gated RL feasibility probe on DeepSeek

Why not Option 2: with a ~even c1/c2 prior, a multi-day two-model sweep is the most expensive
possible way to confirm a negative obtainable in ~40 GPU-h; c2 is *cheaply detectable* (reward
won't move even on training problems). Pay 40h to learn which hypothesis we're in before
committing multi-day compute to a possible dead end. Why not Option 3: probe is positive-EV both
ways — passes → headline; stalls → upgrades "SFT can't" into the cleaner "neither SFT nor RL
moves it; this prover is at its execution ceiling." DeepSeek = probe model (stronger OOD basis,
most exposure-bias headroom).

### Pre-registered SUCCESS GATE (the decisive part — guards against false positives)

The probe must distinguish "RL learning to prove" from "RL learning to reward-hack." A pass
requires ALL THREE; a stall is read via the escape clause:

1. **Held-out verified solve-rate UP** (PRIMARY). Gate on solve-rate on *held-out* problems,
   NOT training reward. Verifier-reward RL is a textbook reward-hacking setup. Training reward up
   is necessary-not-sufficient; if training reward climbs but held-out solve-rate is flat, that
   is overfitting/hacking — a no-go masquerading as a go, NOT c1 confirmed.
2. **Soundness rates do NOT degrade** (first-class output, base vs RL checkpoint). Track
   loophole / malformed / would-be-false-positive rates. Ties to our verifier-soundness
   contribution. If RL "works" only by gaming the verifier, that is a finding (cautionary for the
   field) but emphatically NOT floor-movement.
3. **No diversity collapse / KL blowup.** Generic RFT already hurt by narrowing the policy
   (−13..−19pp). Track generation diversity + KL-to-base during the probe.

**Escape clause (so a stall is read correctly):** if the probe stalls *with* a KL/diversity
pathology, that is "retune (KL coeff / reward shaping) and re-probe," NOT "c2 locked." Capacity-
bound is concluded only when reward fails to move on training problems *without* a tuning
pathology. This is the one way the probe could under-call c1, so it is pre-registered.

Read-out: held-out solve-rate↑ + soundness flat/better + no collapse → **c1, RL moves the
floor**. Reward flat on train, no pathology → **c2, capacity ceiling**. Train reward↑ but
held-out flat / soundness degraded / collapse → **neither (hack or mistune)**, retune-and-reprobe
or no-go.

### Next checkpoint
Bring concrete probe specs — problem subset, K (samples/problem), steps, reward shaping, KL
coefficient, numeric success threshold, GPU-h estimate — for user pressure-test BEFORE spending
the ~40 GPU-h. Sequenced AFTER the 3-seed bars finalize.
