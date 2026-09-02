# Budget-Bounded Agentic Theorem Proving — Full Research Compilation

> ## ⓘ POINT-IN-TIME SNAPSHOT (2026-07-03) — accurate as of its date, but not current
>
> A standalone compilation prepared for external review. It predates Phase 8's withdrawal, the
> independent audit, the 2026-07-25 corrections log, and the WS6 sprint. Everything in it was true
> when written; several framings have since been sharpened or retracted.
>
> **For current state read [`HANDOFF.md`](HANDOFF.md); for the corrections read `SYNTHESIS.md`'s
> "Corrections log".**

---


*Standalone snapshot for external review (advisor + a fresh coding agent). Assumes zero prior
context. Compiled 2026-07-03 from the repo's lab notebooks (`PROGRESS.md`, `DECISIONS.md`) and the
per-phase results docs (`results/*/`, `SYNTHESIS.md`). Every number below traces to a committed
results file; pointers are given per section.*

---

## 0. What this project is, in one paragraph

We study **what actually matters in an LLM + Lean-4 proof agent when the per-problem compute budget
is small and fixed** — the regime an academic lab (tens of GPUs, no datacenter) actually operates in.
We use only open ~7–8B provers. Everything is measured as **`pass@B`**: the fraction of theorems
Lean-verifies within a per-problem budget of `B` generated tokens, reported as a curve over budgets
(2k / 8k / 32k / 128k) with ≥3 seeds (mean ± std). The original bet was: *a learned budget-allocation
controller can beat the best hand-designed agent loop at equal `B`.* Over ~6 phases that bet evolved
into a broader, and now largely **negative**, finding: **at this model scale, raw compute budget and
the prover's own training — not agentic scaffolding, not search, not fine-tuning — are the only things
that move the needle.** One phase produced a modest *positive* result (compute-optimal allocation, but
robust on only one of two models). The current open question is whether reinforcement learning can
move a specific "execution floor" that everything else has failed to move.

---

## 1. The honest executive summary (read this first)

The arc of results, phase by phase:

| Phase | What we tested | Outcome |
|---|---|---|
| 0 | Baseline `pass@B` curves, 2 models × 2 benchmarks | ✅ Clean baselines; found a saturation **asymmetry** (easy benchmark saturates ~72–75%, hard one stays budget-hungry) |
| 1 | Does agentic **scaffolding** help at fixed `B`? (6 components, OFAT) | ❌ **Null** on easy benchmark; on hard benchmark 2 components actively **hurt** |
| 2 | **Why** does budget saturate where it does? (mechanism mining + 1 interventional test) | 🔬 Bottleneck localized: models **collapse onto ~2 approaches** and hit a **deep-execution floor** — they make progress into proofs but cannot *close* them. Forcing diversity raises diversity but not solves. |
| 3 | Can a symbolic **hammer/SMT** close the stuck leaves? | ❌ **NO-GO** — a Lean tactic portfolio closes 0/40 trapped problems |
| 4 | Compute-optimal **budget allocation** (abandon predicted-trapped cells, reinvest) | ✅ **The one positive result** — ~30% compute saved at 90% accuracy on Goedel×ProofNet#, **but one-model-robust only** (fails on DeepSeek per-seed) |
| 5 | **Reclaim-and-reinvest**: give trapped cells far more budget (256k) | ❌ ~0 new solves — confirms the floor isn't "needs more of the same budget" |
| 6 | **Mechanism-targeted fine-tuning**: train the model at exactly the goal-closing bottleneck | ❌ Stage A (generic RFT) **hurts**; Stage B (closing-targeted SFT) is a **two-model, 3-seed null**. ⏳ Stage C (GRPO RL) is the final untested lever — **currently running**. |

**The uncomfortable meta-pattern the user wants advice on:** five of six phases landed negative or
one-model. The project has, almost by accident, become a **rigorous negative-results paper** ("Budget,
Not Scaffolding: what doesn't help small theorem-proving agents, and why") plus one modest positive
(allocation). Every "make the number go up" lever we've pulled — scaffolding, search, hammers, budget
reinvestment, supervised fine-tuning — has confirmed the same **execution floor**. The last untested
lever is on-policy RL (Stage C), running now. The strategic question is whether that's worth waiting
for, and what the strongest publishable story actually is.

---

## 2. Setup and infrastructure (the same for every phase)

**Models (two independent open provers — a second model is used throughout so findings are not
one-model artifacts):**
- **Goedel-Prover-V2-8B** (`Goedel-LM/Goedel-Prover-V2-8B` @ `dfd02e6`), on **Lean v4.9.0-rc1** with a
  **custom mathlib4 fork** (`xinhjBrant/mathlib4` @ `2f65ba7`) matched to its training-time API.
- **DeepSeek-Prover-V2-7B** (`deepseek-ai/DeepSeek-Prover-V2-7B` @ `a8d9e144`), on **Lean v4.9.0** with
  **standard mathlib4** (`f0957a7`).
- Both run in **whole-proof mode**: statement in → full Lean proof out in one generation, then verify.

**Benchmarks:**
- **miniF2F-test** — 244 audited competition-style problems (known-unprovable items excluded).
  **In-distribution** for these provers.
- **ProofNet#** — 186 undergraduate-level problems. **Out-of-distribution (OOD)** for these provers,
  and ~3–5× harder at every budget. This is where most of the interesting signal lives.

**The metric — `pass@B`:** budget `B` = total LLM-generated tokens per problem, summed over all model
calls (proposals + refinements). Hardware-independent (unlike wall-clock). Reported as a curve over
{2k, 8k, 32k, 128k}, ≥3 seeds, mean ± std. Per-seed std is ~1.5–3pp, so **a single mean delta under
~3pp is treated as noise** — a bar we apply everywhere.

**Verifier soundness (treated as a first-class artifact).** Lean is the sole authority. A 2026-06-14
audit found two false-positive holes (a truncated `def` preamble that compiles with no goal; a wedged
REPL returning empty-no-error). Both fixed (commit `aa659f5`): a solve now requires a declared
theorem/lemma/example **and** a REPL response carrying a real environment. Only ProofNet# was
materially affected pre-fix and was fully re-run. Proofs with `sorry`/`admit`/`native_decide` loopholes
are rejected. Throughout, we report the reviewer/critic **false-accept rate** as a metric.

**Cluster / engineering.** Columbia Insomnia (Slurm), tens of GPUs (L40S/A6000 for inference/eval,
H100 for training/RL). A persistent **vLLM** server hosts the prover; the agent meters every token; a
persistent **Lean-4 REPL** with Mathlib preloaded verifies each proof warm (~0.2s). Hard-won details
baked into the harness: unset the inherited SSH proxy in every job; stage Mathlib's ~4.7k oleans to
node-local SSD (`/dev/shm`) to dodge a shared-GPFS storm; drive the REPL over a PTY; **never** pickle
the REPL env (it silently corrupts verdicts on `@[init]` tactic extensions); gate every GPU sweep on a
probe that accepts a `norm_num` proof and rejects a false one, so a broken env fails fast. Everything
is config-driven (versioned YAML + `run_manifest.json`), test-first, and restartable (jobs checkpoint
and resume; the cluster preempts and requeues from scratch).

---

## 3. Phase 0 — Baselines and the saturation asymmetry

*Source: `SYNTHESIS.md`, `results/*/metrics.json`.*

The headline `pass@B` curves (the foundation everything else is measured against):

| budget | miniF2F · Goedel | miniF2F · DeepSeek | ProofNet# · Goedel | ProofNet# · DeepSeek |
|--------|------------------|--------------------|--------------------|----------------------|
| 2k   | 29.6% ± 3.3% | 27.9% ± 2.1% | 4.8% ± 1.4% | 5.4% ± 0.5% |
| 8k   | 60.1% ± 1.9% | 57.9% ± 1.7% | 9.3% ± 1.1% | 13.1% ± 0.8% |
| 32k  | 69.5% ± 0.6% | 67.1% ± 0.9% | 12.0% ± 0.6% | 18.3% ± 1.6% |
| 128k | 74.9% ± 0.9% | 72.0% ± 0.5% | 14.3% ± 0.8% | 22.2% ± 1.7% |

Two structural facts that drive the whole project:

1. **Saturation asymmetry.** miniF2F rises steeply early (+30pp over 2k→8k) then **saturates to a
   ~72–75% ceiling**; ProofNet# is far flatter and **still climbing at 128k from a low base**. In-
   distribution saturates; OOD stays budget-hungry. Replicates on both models → not an artifact.
2. **A cross-model dichotomy.** Goedel slightly wins in-distribution (miniF2F), but **DeepSeek clearly
   beats Goedel on the hard OOD benchmark, and the gap widens with budget** (+8pp at 128k: 22.2 vs
   14.3). This is a **training-distribution/recipe difference, not a size effect** (8B vs 7B can't
   carry it). This "the model's training is the real OOD lever" observation recurs as the deepest
   finding of the project.

---

## 4. Phase 1 — Does agentic scaffolding help? No, and some of it hurts.

*Source: `results/phase1/FINDINGS.md`, `SYNTHESIS.md`.*

We ablated six composable scaffolding components **one-factor-at-a-time** against a no-frills baseline
(whole-proof + refinement, everything else off), judged by **paired flips** (per (problem, seed):
problems the variant solves that the baseline missed, vs vice-versa). A real lever makes gains
*dominate* losses; symmetric flips are just generation churn.

Components: (1) **budget allocation** (fresh samples vs iterative refinement split), (2) cross-attempt
**memory**, (3) an LLM **reviewer/critic**, (4) **premise retrieval** (BM25, k=8), (5) inference-time
**tactic-skeleton** hints, (6) forced **approach-diversity** (added in Phase 2).

**miniF2F:** no component cleared the noise bar. Retrieval *looked* like a mover at +3.4pp@8k in the
first pass but **did not replicate** (+2.2 / +0.7 / −0.8 pp at 2k/8k/32k in a second campaign) — the
+3.4 vs +0.7 gap is pure run-to-run variance (separate vLLM processes aren't bitwise reproducible).

**ProofNet# (paired flips vs baseline):**

| component | gains | losses | net | verdict |
|---|---|---|---|---|
| reviewer | 13 | 10 | +3 | noise-like |
| budget_alloc (all-refine) | 9 | 11 | −2 | noise-like |
| memory | 8 | 10 | −2 | noise-like |
| tactic_skeletons | 9 | 12 | −3 | noise-like |
| budget_alloc (all-fresh, no escalation) | 6 | 25 | **−19** | **hurts** |
| retrieval (BM25) | 6 | 42 | **−36** | **hurts** |

On the harder benchmark the null sharpens: 4/6 noise-like, and **two are directionally harmful** —
front-loaded allocation and BM25 retrieval (42 baseline solves lost for 6 gained). Bad context poisons
the prompt precisely when the model is out of its depth.

**Takeaway:** *no scaffolding component is a net-positive lever.* This killed the original "clever
agent loop" thesis and forced the question: **why?**

---

## 5. Phase 2 — The mechanism: a diversity collapse onto a deep-execution floor

*Source: `results/phase2/MECHANISM.md`, `SYNTHESIS.md`. CPU-only mining of attempt traces + one
interventional GPU test. Every finding holds on both models × both benchmarks.*

- **F1 — diversity collapse.** On problems it never solves, a model tries only **~1.8 distinct opening
  tactics across 18–33 attempts** — it loops on ~2 approaches regardless of budget.
- **F2 — failure taxonomy (the spend gate).** Unsolved attempts fail at **deep reasoning (94–100%
  `reasoning_deep`)**, essentially never at a missing lemma (~0% `knowledge_hallucinated_lemma`). →
  There is nothing to retrieve; this is *why* premise retrieval (BM25 and neural ReProver) can't help.
- **F3 — capability floor.** Unsolved attempts reach a **median deepest step of 26–53** and almost
  never stall at step 1 — the model makes **real progress into proofs but cannot close them.**
- **F4 — no easy subfield.** ProofNet# solve rates are 21–33% across every subfield — no soft target a
  smarter router could farm.
- **F5 — late solves are re-samples, not new approaches** (correlational): when a hard problem is
  finally solved late, it's the *same* approach re-sampled (0% new opening).

**F6 / Step C — the interventional test that closes F5's correlational gap.** We built an
approach-conditioned **DiversityInjection** component (lists the openings already tried, asks for a
fundamentally different one) and ran it on the **trapped cores** (problems unsolved by ALL seeds at
128k), 3 seeds, all four model×benchmark cells. Pre-registered prediction: diversity rises, solves
stay flat.
1. **Manipulation check PASSED** — distinct openings rose **+42–70%** (budget-matched) → the
   intervention genuinely fired.
2. **Solves NULL** — trapped pass ≈ 0 everywhere; **5 genuine verified flips across all four arms
   (0 on DeepSeek)**, within seed noise. → **Approach discovery is not the bottleneck; within-approach
   execution is.**
3. **Forcing diversity mildly degrades quality** — failures shift from `reasoning_deep` to
   `formalization_syntax` + `loophole_sorry`; soundness-relevant rates creep up ~1.5–3× — but **every
   degraded attempt is caught by the verifier (0 false solves).**

**This is the intellectual core of the project:** the budget→solve relationship saturates because the
model collapses onto a couple of approaches and hits a **deep-execution floor** — it can't *close*
proofs it has correctly started, and no search-time move fixes a problem of proof *execution*.

---

## 6. Phase 3 — Can a symbolic hammer close the stuck leaves? No.

*Source: `results/phase3/HAMMER_PROBE.md`.*

If the floor is leaf-closing, the natural lever is "hand the model's stuck leaf to a symbolic closer."
We ran a Lean tactic **portfolio** (`omega | nlinarith | norm_num | simp_all | decide | aesop`) on the
Goedel ProofNet# trapped core:

| Arm | what | result |
|---|---|---|
| Positive control | portfolio on 4 trivial synthetic goals | **4/4 PASS** (probe fires) |
| Arm 0 | portfolio on the original trapped statement | **0 / 30** |
| Arm A-lite | portfolio swapped in for the model's failing tactic | **0 / 40** |

**NO-GO** (pre-registered threshold: <2pp closure). Honest caveat: a *real* superposition prover
(`duper`) or SMT (cvc5/Lean-SMT) reasons beyond the portfolio and was **not** tested (it needs a
v4.9.0 port + proper proof-state extraction, ~1–2 days). But given the converging negatives, the EV of
building it is low. Folded into the negative thesis as: *"even handing the model's deepest stuck leaf to
standard Lean automation closes 0/40 — the OOD floor is not a thin automation gap."* Phase 3 also
hardened the negative thesis with CPU-only checks (statement-set intersection, human-validated failure
taxonomy, soundness-creep audit) and reframed the writeup toward **"Budget, Not Scaffolding"** (a
training-not-size story).

---

## 7. Phase 4 — Compute-optimal budget allocation (THE positive result)

*Source: `results/phase4/ALLOCATION.md`. All offline arithmetic over the committed 128k baseline runs,
via the identity `solved(cell,b) == tokens_to_solve(cell) ≤ b`; realizability is by construction
(early-stopping of budget-independent runs), so no GPU re-run was needed.*

The idea: on ProofNet#, ~80% of cells never solve, and uniform budgeting pours full budget into a
provably-trapped core. A **realizable** during-run policy uses a logistic predictor (trained only on
info observable by a decision checkpoint `c*`: elapsed tokens, #attempts, deepest step reached,
plateau signals; out-of-fold) to **abandon predicted-trapped cells and reallocate to survivors.**

| model × benchmark | save @90% acc | per-seed @90% | verdict |
|---|---|---|---|
| **Goedel × ProofNet#** | **+30%** | **+26% ± 7%** (+25/+18/+34) | **STRONG, robust** |
| DeepSeek × ProofNet# | +10% | −13% ± 28% (+5/+9/**−51**) | WEAK / fragile |
| Goedel × miniF2F | −16% | — | negative (contrast) |
| DeepSeek × miniF2F | −16% | — | negative (contrast) |

**Reading:** "retain 90% of solves for ~30% less compute." Robust across all 3 seeds on Goedel
ProofNet#, but the **DeepSeek result collapses on seed 2 (−51%)** → the positive contribution is
**one-model-robust, not two-model.** miniF2F is the contrast (nothing to reclaim at 75% solve rate).

Two honest caveats: (1) the win is at a **fractional-accuracy** operating point — to solve *every*
winnable cell you must keep the hardest ones, whose cost is indistinguishable from trapped cells, so at
100% accuracy the policy saves ~0; (2) predictability is only **moderate (AUC ~0.65–0.75, peaking
mid-run)**. The unrealizable oracle ceiling is ~98% saved; the realizable policy captures ~1/3 of it.
Two multi-round policy variants (successive-halving, multi-round thresholding) were pre-registered and
**both falsified** — single-checkpoint wins. This is the strongest *positive* thing the project has.

---

## 8. Phase 5 — Reclaim-and-reinvest: does more budget on trapped cells help? No.

*Source: `results/phase5_pilot_*/pilot_summary.json`.*

If Phase 4 reclaims compute from trapped cells, does **reinvesting** it (extending the hardest cells far
past 128k, to **256k**) buy new solves? Pilot on the ProofNet# trapped core:
- Goedel: 1 cell ran to 256k → **0 extension solves**.
- DeepSeek: 2 cells ran to 256k → **0 extension solves**.

Doubling budget on trapped cells yields essentially nothing — a **fourth independent confirmation of the
execution floor** (after Phase 1 null, Phase 2 mechanism, Phase 3 hammer NO-GO). The floor is not "needs
more of the same sampling budget." This closed the reinvest idea and motivated Phase 6 (training).

---

## 9. Phase 6 — Mechanism-targeted fine-tuning (the current phase)

*Source: `results/phase6/{FINETUNE.md, STAGE_C_DECISION.md, STAGE_C_PROBE_SPEC.md, DISJOINTNESS.md}`.*

**Thesis under test:** training is the one lever the project's own data hasn't ruled out (the
DeepSeek>Goedel OOD gap is a *training-distribution* effect — Phase 0/2). So: **can training targeted
at the mechanistically-identified bottleneck (within-approach goal-closing) lift `pass@B` where
scaffolding, search, and budget could not?** Both outcomes were pre-registered as publishable (positive
= a method contribution; null = "the floor is capacity-bound at this scale, resists targeted FT").

**§0 disjointness gate (non-negotiable).** Training data harvested only from **Lean-Workbook**
(140,214 problems), decontaminated against both eval sets (dropped exact + high-cosine near-dups → 202
removed, 140,012 clean). Every checkpoint manifest records the corpus + disjointness proof. Serving is
byte-exact (vLLM serves the LoRA adapter on the base tokenizer/template) and empirically guarded.

**Stage A — generic RFT (rejection-sampling fine-tuning; control).** Train on the model's own verified
whole proofs. Result: **actively HURTS** — −12..−20pp @32k miniF2F. Self-training on already-solved
proofs narrows the sampling distribution.

**Stage B — closing-targeted SFT (the novel method).** Take verified proofs, truncate at a deep point,
and train `(deep_proof_state → remaining closing tactics)` with the loss **masked to the closing
tokens only** — "here's the proof so far, learn to close it," in the byte-exact inference format. Only
targets closings the base model **fails** to produce on its own (so it teaches new capability, not echo).
**Result: two-model, 3-seed NULL.** Paired B−base @32k:

| model | miniF2F | ProofNet# |
|---|---|---|
| Goedel | −2.0 ± 1.1 pp | −2.0 ± 1.2 pp |
| DeepSeek | −0.3 ± 1.3 pp | −0.9 ± 0.3 pp |

All flat-to-slightly-negative, **never within reach of the pre-registered ≥+3pp**, tight bars across 3
seeds. **The critical diagnostic:** this null holds *despite* very low closing-token training loss
(~0.07) — **the model assigns high conditional probability to the correct closings yet fails to generate
them autoregressively.** That gap is the textbook signature of **exposure bias**, not missing knowledge.

**This leaves exactly two live hypotheses for the execution floor:**
- **(c1) exposure-bound** — the policy *can* represent the closings but its sampling distribution
  doesn't put them on-trajectory. If so, **on-policy RL against the verifier is exactly the tool that
  should move it** where teacher-forced SFT could not.
- **(c2) capacity-bound** — the 8B-class model fundamentally can't, and no training helps. If so, RL
  also fails → a clean "this prover is at its execution ceiling."

**Stage C — gated GRPO RL feasibility probe (RUNNING NOW).** GRPO optimizes the *actual generation
distribution* against a binary Lean-verified reward (+ soundness gate; +0.05 format bonus; no dense
shaping, to minimize reward-hacking surface). One model (DeepSeek — stronger OOD basis). Pre-registered
**triple success gate** (a PASS needs ALL three, to distinguish "learning to prove" from "learning to
reward-hack"):
1. **G1 (primary): held-out verified solve-rate ↑** by ≥ +5pp (NOT training reward — verifier-reward RL
   is a textbook reward-hacking setup; train-reward-up-but-held-out-flat = overfit, not c1).
2. **G2: soundness does not degrade** (loophole/malformed/false-positive rate rises ≤ +2pp).
3. **G3: no diversity collapse / KL blowup** (retain ≥80% of base diversity; KL under a ceiling).

Decision map: all three pass → **c1, RL moves the floor** (headline of the whole training arc); reward
flat on train with no pathology → **c2, capacity ceiling** (clean negative); reward-up but G1/G2/G3
fail → **hack/mistune** → retune-and-reprobe. Cost-gated at ~40 GPU-h (an explicit user-approved
feasibility probe, single-seed by design, *before* any multi-day sweep).

**Live status (2026-07-03):** the probe is a LoRA r=16 GRPO run on DeepSeek over a 130-train/70-heldout
subset of Lean-Workbook (base solve-rate band [1,10]/16 — the "dense advantage" sweet spot, disjoint
from train and both eval sets). Pipeline smoke-tested (reward fires on real verified solves; KL/
soundness/diversity instruments wired). The run itself is **queued on the cluster, waiting on H100
availability, and has not yet completed a training step** — so **there is no Stage C result yet.** The
probe was re-sized from a nominal 150 steps to ~80 steps to fit the pre-registered ~20–25 GPU-h GRPO
budget. When it runs: measure per-step timing, watch the three gate signals, then run the base-vs-RL
held-out eval and compute the triple-gate verdict.

---

## 10. What is running right now, and what is planned after

### 10.1 Currently running (as of 2026-07-03)

**The only live experiment is the Stage C GRPO RL feasibility probe (Phase 6).** Nothing else is
executing; all Phases 0–5 and Phase 6 Stages A/B are complete and their results are committed.

Concrete state of the live probe:
- **Job `11108694`**, partition `short`, on the Columbia Insomnia cluster. **Status: `PENDING`
  (queued, waiting on an H100) — it has not yet completed a single training step.** Estimated start
  ~18:43 on 2026-07-03; H100s are scarce (all 6 allocated). A background monitor is watching for it to
  start / produce its first steps.
- **What it does:** on-policy GRPO RL on **DeepSeek-Prover-V2-7B** (LoRA r=16), reward = **binary
  Lean-verified + soundness gate** (+0.05 format bonus, no dense shaping). Trains on a **130-problem**
  subset of Lean-Workbook whose base solve-rate is in the "dense-advantage" band [1,10]/16, with a
  **disjoint 70-problem held-out** set (disjoint from train AND both eval benchmarks).
- **Key hyperparameters:** `num_generations=4`, `prompts_per_step=8` (→ 32 verified rollouts/step),
  `lr=1e-6`, KL `beta=0.04`, `max_completion_length=4096`, `save_steps=10`, `seed=0`, `max_steps=80`.
  Single-seed **by design** (this is a gated feasibility probe, not a headline number). Re-sized from a
  nominal 150 steps to ~80 to fit the pre-registered ~20–25 GPU-h budget (the Lean-in-the-loop
  verification of every rollout is the bottleneck, not the forward pass).
- **What happens the moment it finishes:** run the **base-vs-RL held-out eval** on the 70 held-out
  problems (`configs/phase6_grpo_heldout_deepseek.yaml`, budget 8192, seeds 0–7, refinement on),
  compute the **pre-registered triple-gate verdict** (G1 held-out solve-rate ↑ ≥ +5pp / G2 soundness
  not degraded / G3 no diversity-collapse-or-KL-blowup), and write `results/phase6/STAGE_C_RESULT.md`.

### 10.2 Planned next, conditioned on the Stage C verdict

The probe is explicitly a **branch point**, pre-registered before spending GPU:

- **If the triple gate PASSES → c1 (exposure-bound), RL moves the floor.** This becomes the headline of
  the entire training arc. Planned follow-up = **fund the full Stage C**: both models (Goedel +
  DeepSeek), 3 seeds, the real OOD benchmarks (miniF2F + ProofNet#), and — only if binary reward proves
  too sparse — add dense progress/depth reward shaping. This is a multi-day, >50 GPU-h sweep and would
  be re-approved before launch.
- **If it stalls cleanly (reward flat on train, no KL/diversity pathology) → c2 (capacity-bound).**
  Planned follow-up = **close the training arc** and write the sharpened negative: "neither generic nor
  closing-targeted SFT, nor on-policy RL, moves the execution floor — this 7–8B-class prover is at its
  execution ceiling." A pre-registered caveat applies: because the probe is LoRA (not full fine-tuning),
  a *clean* stall is reported as c2 **with** a LoRA-rank caveat (a stricter test would retune / try
  full-FT before calling c2 airtight).
- **If training reward climbs but the held-out gate fails (G1 flat / G2 soundness degrades / G3
  collapse) → hack-or-mistune, NOT c2.** Planned follow-up = **retune** (KL coefficient, lr, reward
  shaping) and **re-probe** once — the escape clause that prevents a mis-tuned run from being misread as
  a capacity ceiling.

### 10.3 Other pending / optional items (not currently scheduled)

- **Stage D — teacher distillation** (Phase 6 plan): harvest closing segments from a stronger prover
  (DeepSeek-V2-671B / a frontier API) on problems the 8B can't solve, as an upper-bound "how far can it
  be pushed." Was gated on Stage B showing lift; since B is null, it is **deprioritized / future work**.
- **Phase 4 Task 4.4 — live confirming run** of the compute-optimal allocation policy: the "+30% saved"
  is *simulated* (offline, by construction) and was never converted into a *measured* live run. This is
  the single cheapest step that would harden the one positive result, and it remains **not executed**.
- **Deferred-by-design (may reopen if the story needs it):** best-first tactic / proof-state **search**
  (a different generation mode than whole-proof); a **`duper`/SMT hammer** ported to the v4.9.0 pin with
  proper proof-state extraction (the decisive version of the Phase 3 probe); a **model-zoo study** of
  which training-recipe differences create the DeepSeek>Goedel OOD advantage.

---

## 11. The overall thesis (what we believe the results mean)

**At ~7–8B scale, for whole-proof theorem proving under a fixed budget:**
1. **Compute budget is a real lever** — but it *saturates* in-distribution (~75%) and, on OOD problems,
   buys proofs slowly against a hard floor.
2. **Agentic scaffolding is not a lever** — retrieval, memory, reviewer, tactic hints, allocation
   splits, forced diversity: all null at fixed budget, two of them harmful on hard problems.
3. **The bottleneck is within-approach execution / goal-closing** — models collapse onto ~2 approaches
   and make deep progress they cannot finish. Localized four ways (mechanism mining, an interventional
   diversity test, a hammer probe, and budget reinvestment — all confirm it).
4. **Search-time interventions cannot move an execution floor** — because it's a problem of proof
   *execution*, not proof *finding* or *retrieval*.
5. **The model's training is the real OOD lever** (DeepSeek > Goedel is a training-recipe effect) — but
   our own attempts to exploit that via SFT (Stages A/B) are **null**, consistent with an exposure-bias
   floor that supervised likelihood training can't move.
6. **The one thing that transfers to compute efficiency** is mechanism-informed **budget allocation**
   (Phase 4) — abandon predicted-trapped cells, reinvest — but robust on one model only.

**Two clean, defensible contributions exist today, with zero further compute:**
- A **rigorous, two-model, mechanism-backed negative result**: *what doesn't help small proof agents,
  and why* ("Budget, Not Scaffolding").
- A **modest positive**: mechanism-informed compute-optimal allocation (one-model-robust).

The **Stage C RL probe is the swing** that could either (a) turn the training arc positive (c1: RL
moves the floor — a real headline), or (b) sharpen the negative into "neither SFT nor RL moves it; this
prover is at its execution ceiling."

---

## 12. Where we're stuck — the strategic questions to ask

The user's concern is that **research doesn't feel like it's moving forward**: many phases, one modest
positive, and a series of well-executed nulls. That's the honest read. The questions worth putting to
an advisor / a fresh agent:

1. **Is the negative-thesis paper the right deliverable now?** We have a tight, two-model, mechanism-
   backed story ("Budget, Not Scaffolding") that's arguably TMLR/workshop-publishable *today*. Is it
   stronger to write that up now, or does it need the Stage C RL result to feel complete?
2. **How much does Stage C actually change the story?** If RL passes the triple gate (c1), it's a real
   headline. If it stalls (c2), it *strengthens* the negative but adds compute+time. Given ~even prior
   and H100 scarcity, is the ~40 GPU-h probe worth waiting on, or should we lock the writeup and treat
   RL as future work?
3. **Have we mis-scoped by fixing the model class?** The deepest finding is that **the model's training,
   not scale or scaffolding, is the OOD lever** (DeepSeek > Goedel). We deliberately excluded a
   model-zoo / larger-model study as out of scope. Is the *most* interesting paper actually a controlled
   study of *which training-recipe differences* create the OOD execution advantage — i.e., pivot toward
   the one thing that demonstrably moves the floor?
4. **Is "execution floor" the right framing, or an artifact of whole-proof mode?** We never built
   best-first tactic/proof-state search (deferred: prior was search < pass@1). Could a genuinely
   different *generation mode* (stepwise, with proof-state feedback) move the floor that whole-proof
   sampling can't? Or is that ruled out by F2/F3?
5. **Is the Phase 4 positive worth hardening into its own contribution?** It's one-model-robust and
   simulated-not-live (the "live confirming run," Task 4.4, was never executed). Would a live confirming
   run + a second robust model make it a standalone paper, independent of the negative thesis?
6. **What would actually change our minds about c1 vs c2** short of the full RL sweep — is the
   single-seed gated probe informative enough to bet the writeup on?

---

## 13. Rough compute + reproducibility notes

- All experiments are config-driven (`configs/*.yaml`) with `run_manifest.json` provenance (git SHA,
  model revision, mathlib commit, Lean version, seeds, GPU type). Lab notebooks: `PROGRESS.md`
  (append-only, ~2200 lines), `DECISIONS.md` (~1000 lines). Per-phase results in `results/phase{1..6}/`.
- Compute has been dominated by: the 128k baseline sweeps (2 models × 2 benchmarks × 3 seeds), the
  Phase 2 trapped-core interventional runs, the Phase 6 harvest + SFT eval matrix (2 models × 3 seeds ×
  2 benchmarks × 3 arms × 2 budgets), and now the Stage C GRPO probe. Order of magnitude: several
  hundred GPU-hours cumulatively; the Phase 6 subset-generation alone overran to ~130 GPU-h.
- Key reproducibility landmines (all handled, documented in `DECISIONS.md`): Mathlib custom-fork oleans
  built from source and staged node-local; never pickle the Lean env; verifier soundness audited as a
  first-class artifact; per-seed std ~1.5–3pp sets a ~3pp noise bar on all deltas.

*End of compilation. For the live, dated narrative see `PROGRESS.md`; for design rationale see
`DECISIONS.md`; for the one-page story with all receipts see `SYNTHESIS.md`.*
