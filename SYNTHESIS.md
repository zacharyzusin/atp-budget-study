# Synthesis — Budget-Bounded Agentic Theorem Proving

*Consolidated findings as of 2026-07-10 (Phases 0-8 complete). Source of truth for the numbers:
`PROGRESS.md` (dated lab notebook), `DECISIONS.md`, `results/*/metrics.json`, and each phase's own
result doc (`results/phase1/FINDINGS.md`, `phase2/MECHANISM.md`, `phase3/HAMMER_PROBE.md`,
`phase4/ALLOCATION.md`, `phase6/{FINETUNE.md,STAGE_C_RESULT.md}`, `phase7/STEPWISE.md`,
`phase8/ZOO.md`). This file is the consolidated story; those are the receipts.*

> **⚠ Four corrections logged 2026-07-25, from an external-calibration sprint
> (`CALIBRATION_FINDINGS.md`, `DECISIONS.md` 2026-07-24/25/25b). The original text below is left
> intact; each affected claim is marked inline with a pointer to the "Corrections log" section at
> the bottom of this file, which has the corrected numbers and full derivation. Do not delete the
> original text — the audit trail is a deliberate asset.**

## The question

For a fixed whole-proof theorem prover, how does solve rate scale with the per-problem **token budget**
B, and do **agentic scaffolding** components (premise retrieval, failure memory, an LLM reviewer,
tactic-skeleton hints, budget allocation, forced approach-diversity) buy anything on top of plain
whole-proof sampling at a given budget? And if not — **why** does budget saturate where it does?

- **Models (two, independent):** Goedel-Prover-V2-8B (`Goedel-LM/Goedel-Prover-V2-8B` @ `dfd02e6`, Lean
  v4.9.0-rc1 + mathlib4 `2f65ba7`) and DeepSeek-Prover-V2-7B (`deepseek-ai/DeepSeek-Prover-V2-7B` @
  `a8d9e144`, Lean v4.9.0 + standard mathlib4 `f0957a7`). Lean is the authoritative verifier (REPL backend).
- **Benchmarks:** miniF2F-test (244 audited problems; competition-style, in-distribution) and ProofNet#
  (186 test; undergrad-level, out-of-distribution for these provers).
- **Deliverables:** the pass@B curve per model×benchmark; paired-flip OFAT ablation of each scaffolding
  component (Phase 1); and a mechanism account of the budget→solve relationship culminating in an
  interventional test (Phase 2).
- **Variance:** 3 seeds for every headline number; mean ± seed-std (~1.5–3pp). A single OFAT mean-delta
  under ~1 baseline-σ is treated as noise (the "noise bar," DECISIONS 2026-06-11).

## pass@B — the headline curves (both models)

| budget | miniF2F · Goedel | miniF2F · DeepSeek | ProofNet# · Goedel | ProofNet# · DeepSeek |
|--------|------------------|--------------------|--------------------|----------------------|
| 2k   | 29.6% ± 3.3% | 27.9% ± 2.1% | 4.8% ± 1.4% | 5.4% ± 0.5% |
| 8k   | 60.1% ± 1.9% | 57.9% ± 1.7% | 9.3% ± 1.1% | 13.1% ± 0.8% |
| 32k  | 69.5% ± 0.6% | 67.1% ± 0.9% | 12.0% ± 0.6% | 18.3% ± 1.6% |
| 128k | 74.9% ± 0.9% | 72.0% ± 0.5% | 14.3% ± 0.8% | 22.2% ± 1.7% |

**[CORRECTED — see Corrections log #4: the 2k row is attempt-starved (median ZERO full propose
attempts complete within 2k tokens); treat it as a floor/footnote point, not a comparable curve
point.]**

- **Same shape on both models.** miniF2F is steep early (≈+30pp over 2k→8k) then saturates to a ~72–75%
  ceiling by 128k; ProofNet# is ~3–5× harder at every budget and far flatter — it keeps buying proofs but
  the curve is still climbing at 128k from a low base. The budget-saturation *asymmetry* (in-distribution
  saturates; OOD stays budget-hungry) is not a Goedel artifact — it replicates on an independent prover.
  **[CORRECTED — see Corrections log #1: "saturates to a ceiling" should read "plateaus because the
  agent loop runs out of independent attempts," not a demonstrated capability ceiling.]**
- **A cross-model dichotomy.** Goedel slightly edges DeepSeek in-distribution (−2 to −3pp on miniF2F), but
  **DeepSeek clearly beats Goedel on the harder OOD ProofNet# at every budget, and the gap widens with
  budget** (+8pp at 128k: 22.2 vs 14.3). This is a *training-distribution / recipe* difference, not a
  model-size effect — an 8B-vs-7B gap cannot carry it (the models differ in data, RL recipe, base model,
  and mathlib); isolating the cause needs a controlled model-zoo study (future work).
  - *Not a port artifact (H1).* Both provers attempted the identical canonical statement sets (244 miniF2F,
    186 ProofNet#; 0 disjoint names), and every statement elaborates on **both** Lean pins (Goedel
    v4.9.0-rc1/mathlib `2f65ba7` and DeepSeek v4.9.0/mathlib `f0957a7`: 244/244 and 186/186 each). So the
    compile-on-both-pins intersection is the full set, and pass@B on the intersection is identical to the
    native-port numbers — the gap is real, not a coverage difference.
  - *Mechanism (H4).* The OOD advantage is **deeper within-approach execution, not more approach diversity**:
    every DeepSeek-only ProofNet# win is on an opening Goedel also tried but couldn't close, and on the
    problems both models miss DeepSeek diversifies *less* (3.08 vs 4.07 distinct openings) yet elaborates
    *deeper* (median deepest step 29 vs 24). Search-time scaffolding can't move the execution floor (Phase 1
    null + Step C); the prover's training can. **The real OOD lever is the model, not scaffolding.**

Both baselines are the **no-frills config**: whole_proof + refinement (max_iters 4, alloc_split 0.5),
all Phase 1 components OFF. DeepSeek inherits Goedel's protocol exactly (only model + Lean pin change).

## Phase 1 — Does agentic scaffolding help? No — and on hard problems some of it hurts.

One-factor-at-a-time ablation of each component against the no-frills baseline, judged by **paired flips**
(per (problem, seed): problems the variant solves that the baseline missed vs vice-versa). A real lever
makes *gains dominate losses*; symmetric flips are generation churn.

**miniF2F:** no component cleared the noise bar. Retrieval (BM25, k=8) *looked* like the one mover at
+3.4pp@8k in the first OFAT pass but **did not replicate** (+2.2 / +0.7 / −0.8 pp at 2k/8k/32k; gains ≈
losses at every budget — the BM25 context perturbs sampling, it doesn't inject usable premises). Memory,
reviewer, tactic_skeletons, budget_alloc: all within seed noise. (Detail: `results/phase1/FINDINGS.md`.)

**ProofNet# (paired flips vs ablation baseline):**

| component            | gains | losses | net | verdict             |
|----------------------|-------|--------|-----|---------------------|
| reviewer             |  13   |  10    |  +3 | noise-like          |
| budget_alloc__2      |   9   |  11    |  −2 | noise-like          |
| memory               |   8   |  10    |  −2 | noise-like          |
| tactic_skeletons     |   9   |  12    |  −3 | noise-like          |
| budget_alloc__0      |   6   |  25    | −19 | **directional (hurts)** |
| retrieval            |   6   |  42    | −36 | **directional (hurts)** |

On the harder OOD benchmark the null sharpens: 4/6 still noise-like, but **two are directional and both
*harmful*** — front-loaded allocation (no escalation) and BM25 retrieval (42 baseline solves lost for 6
gained). Bad context poisons the prompt precisely when the model is out of its depth.

**Bottom line:** *no Phase 1 scaffolding component is a net-positive lever* — consistent on the easy
benchmark (all noise), stronger on the hard one (same null plus two components that measurably hurt).

## Phase 2 — Why: the mechanism behind the budget→solve relationship

Phase 1 says *what* (scaffolding is null); Phase 2 explains *why*, mining the on-disk attempt traces
(`scripts/analyze_mechanism.py`, CPU-only) and then testing the explanation interventionally. Every
finding below holds on **both provers × both benchmarks**. (Detail: `results/phase2/MECHANISM.md`.)

- **F1 — diversity collapse.** On problems the model never solves, it tries only ~1.8 *distinct* opening
  tactics across 18–33 attempts — it loops on ~2 approaches regardless of budget.
- **F2 — failure taxonomy (the spend gate).** Unsolved attempts fail at deep reasoning (94–100%
  `reasoning_deep`), essentially never at a missing lemma (~0% `knowledge_hallucinated_lemma`). → premise
  **retrieval cannot help** (nothing to retrieve); this is why ReProver was killed, not just deferred.
- **F3 — capability floor.** Unsolved attempts reach a median deepest step of 26–53 and almost never stall
  at step 1 — the model makes real progress into proofs but cannot *close* them.
- **F4 — no easy subfield.** ProofNet# solve rates are 21–33% across every subfield (Artin…Axler) — there
  is no soft target a smarter router could farm.
- **F5 — late solves are not new approaches (correlational).** When a hard problem is finally solved late
  (after ≥3 attempts), it comes from re-sampling the *same* approach, not a newly explored one (0% new
  opening). This *predicts* that forcing approach-diversity will not help — but F5 is survivor- and
  natural-sampling-conditioned, so it cannot prove causation.

**F6 / Step C — the interventional test.** We built an approach-conditioned `DiversityInjection`
component (lists the distinct openings already tried, asks for a fundamentally different approach) and ran
it on the *trapped cores* — problems unsolved by ALL seeds at 128k baseline — @8k/32k, 3 seeds, on all
four model×benchmark cells. Pre-registered prediction: diversity rises, solves stay flat.

1. **Manipulation check PASSED** (budget-matched @32k): distinct openings per attempt rose **+42–70%**
   (abs ~1.0–1.3 → ~1.7–1.8) with attempt counts matched — the intervention genuinely fired.
2. **Solves NULL:** trapped pass@8k/32k ≈ 0 everywhere (Goedel miniF2F 0.6/1.2%, Goedel ProofNet# 0/0.7%,
   DeepSeek both 0/0%). Exactly **5 genuine verified flips across all four arms (0 on DeepSeek)**, within
   seed-std. → **Approach discovery is not the bottleneck; within-approach execution (the F2/F3 reasoning
   floor) is.** This closes F5's correlational gap with a causal experiment, on two independent provers.
   **[CORRECTED — see Corrections log #3: on Goedel×miniF2F the trapped core recovers 3/55 (possibly
   4/55) at iso-compute and 6/55 at uncapped pass@32; "trapped pass@... ≈ 0 everywhere" needs that
   caveat. Also, restricted to the same 55-problem population, the "1.2%" @32k IS these 2 cells — a
   token-matched plain-resampling control now exists: 1/55 (contamination-flagged), so the honest
   statement is "no clear improvement over resampling at matched budget," not "no improvement over
   zero."]**
3. **Forced diversity mildly *degrades* output:** last-attempt failures shift from `reasoning_deep`
   (38–88%) to majority `formalization_syntax` (62–74%) + `loophole_sorry` (23–36%); soundness-relevant
   rates creep up (loophole ~3×, syntax ~1.5–2×). Pushed for novelty, the model leaves its competent
   manifold — but **every degraded attempt is caught by the verifier (0 false solves)**, so result
   soundness is intact and the scaffolding is counterproductive, not neutral.

## Phase 3 — Hammer/SMT probe: NO-GO

A portfolio of hammer/SMT-style closing tactics tried against the trapped core (problems unsolved by
every seed at 128k). 0/119 newly solved. Rules out "the model just needs a stronger closing-tactic
library" as cheaply as Phase 1 ruled out scaffolding. (`results/phase3/HAMMER_PROBE.md`.)

## Phase 4 — Compute-optimal budget allocation: the one clearly positive lever

Not a model or scaffold change — a policy for *how to spend* a fixed total token budget across a
batch of problems (vs. a flat per-problem allocation). Goedel × ProofNet#: **STRONG and per-seed
robust, +26% ± 7%** (saves ~30% of budget at 90% of full-budget accuracy). DeepSeek × ProofNet#: weak
and fragile by comparison (−13% ± 28%) — this result is one-model-robust, not yet a confirmed general
property. Still the clearest actionable finding in the whole project. (`results/phase4/ALLOCATION.md`.)

## Phase 5 — Reclaim-and-reinvest: a fourth confirmation of the floor

Extending the ALREADY-trapped cells past 128k tokens (more of the SAME budget on the SAME problems):
~0 new solves (Goedel 1, DeepSeek 0). Budget helps when *reallocated across different problems*
(Phase 4); it does not help by simply adding more of it to problems already known to be hard.
**[CORRECTED — see Corrections log #3: same trapped-core recovery-rate caveat as Phase 2 Step C
applies here. The token-matched re-analysis (does the recovered rate change under a comparable
extension of resampling rather than refinement) has not been done yet — flagged as an open residual
in `CALIBRATION_FINDINGS.md`.]**

## Phase 6 — Mechanism-targeted execution fine-tuning

- **Stage A/B** (closing-targeted SFT — maximize conditional likelihood on verified closings): a
  two-model NULL, but a diagnostically useful one — the **exposure-bias signature**: near-zero
  teacher-forced loss on the closing, yet the same model still fails when it has to *generate* its own
  path there autoregressively. Reframes the open question from "does the model know how to close a
  proof" (yes) to "why does it drift away from a closeable state during its own free-running
  generation" (open).
- **Stage C** (`results/phase6/STAGE_C_RESULT.md`): a GRPO RL probe — LoRA r=16, DeepSeek-Prover-V2-7B,
  80 steps, direct outcome-reward against the Lean verifier. Clean **c2 (capacity-ceiling) null**: held-
  out pass@1 went 0.586→0.570 (Δ=−1.6pp), training reward flat for all 80 steps, no reward-hacking or
  diversity collapse (G2/G3 both passed cleanly). RL, at LoRA scale, post-hoc on an existing model,
  does not move the floor.

## Phase 7 — Verified-state re-grounding

Tests the Stage B exposure-bias hypothesis directly and training-independently: force the model to
continue from a VERIFIED intermediate Lean state rather than free-running on its own generation.
Modes 3/4, both models: resolved **NULL**. Re-grounding alone does not unlock the trapped core.
(`results/phase7/STEPWISE.md`.) **[CORRECTED — see Corrections log #3: this ran on miniF2F's trapped
core, which is ~89% sound at iso-compute per the 2026-07-25 calibration cell — the null stands close
to as reported, but "the trapped core" should carry the same recovery-rate caveat as elsewhere. The
ProofNet# trapped core (150 problems, carries this phase's 0/150 headline) has not yet been
calibrated — see `CALIBRATION_FINDINGS.md` open question 1.]**

## Phase 8 — Model zoo: does full-pipeline, lab-scale RL move the floor?

Extends the Phase 2 cross-model replication to a new question: not "do two labs' models differ" but
"does a lab's own full RL training pipeline (not a lightweight post-hoc LoRA probe, but Base→SFT→RL
integrated from the start) move the floor?" — tested via two independent matched lineages:
DeepSeek-Prover-V1.5 (Base→SFT→RL) and Leanabell-Prover (GD-SFT→GD-RL, RL over a continual-trained
Goedel-Prover-SFT base).

This phase surfaced and fixed **four real, independently-confirmed bugs** before its floor table
could be trusted (full evidence trail in `results/phase8/ZOO.md`'s superseded-attempts table and
`PROGRESS.md`/`DECISIONS.md`, 2026-07-05 through 2026-07-10):

1. **Wiring bug**: `WholeProofAgent.from_config` hardcoded `WholeProofTemplate` regardless of
   `config.model.prompt_template`, since the project's first commit. A taint audit confirmed this
   affected **zero** Phase 0-7 results (Goedel-V2/DeepSeek-V2 both natively use `whole_proof`) — fully
   contained to Phase 8.
2. **Missing-theorem-header assembly bug**: the Lean-source assembly never reconstructed the theorem
   declaration for continuation-style completions, so bare tactics landed as top-level commands — a
   guaranteed parse error masquerading as "the model's proof was wrong."
3. **Missing `import Aesop` / `set_option maxHeartbeats 0`**: verified byte-for-byte against the
   models' own official inference scripts; the latter disables Lean's elaboration heartbeat limit,
   without which otherwise-valid proofs can spuriously time out.
4. (Investigated, not scaled) **missing `informal_statement` doc-comment**: real, fixed, smoke-tested
   to 160 cells — modest qualitative improvement, 0 solves, stopped per a pre-committed decision rule.

After all three structural bugs were fixed, a **harness-sanity control** (re-verifying Goedel-V2/
DeepSeek-V2's historically-solved proofs under the current patched backend: 37/37 and 40/40 still
verify) confirmed the scoring pipeline itself is sound. The result, harness-validated:

**0.0 ± 0.0 pass@B — every stage (Base/SFT/RL, GD-SFT/GD-RL), both benchmarks, every budget up to
32000, for BOTH matched lineages.** The originally-reported "clean Base<SFT<RL" pattern was entirely a
wiring-bug artifact and does not survive correction.

## The thesis

**Compute budget allocation — not agentic scaffolding, not search strategy, not more of the same
budget, not SFT-style closing-likelihood training, not lightweight post-hoc RL, and not full-pipeline
lab-scale RL either — is the one lever that has moved anything in this whole project.** Across eight
phases and four independent proving lineages (Goedel-Prover-V2, DeepSeek-Prover-V2, DeepSeek-Prover-
V1.5, Leanabell-Prover), the execution floor holds:

- Phase 1: agentic scaffolding (memory/reviewer/retrieval/skeletons) — OFAT-null, two components
  actively hurt OOD.
- Phase 2 mechanism (F1-F4) + F6 intervention: diversity collapse onto a deep-reasoning floor with
  nothing to retrieve; forcing diversity raises it but not solves, and degrades quality.
- Phase 3: hammer/SMT closing-tactic strategies — NO-GO.
- Phase 5: more of the same budget on already-trapped problems — ~0 new solves.
- Phase 6 Stage B: SFT-style closing-likelihood maximization — null, reveals exposure bias instead.
- Phase 6 Stage C: lightweight, post-hoc, outcome-reward RL — clean capacity-ceiling null.
- Phase 7: verified-state re-grounding — null.
- **Phase 8, corrected and harness-validated: full-pipeline, lab-scale RL, two independent training
  lineages — also null.**

The one lever that DID move something, robustly for at least one model (Phase 4): *how* a fixed
compute budget is allocated across a batch of DIFFERENT problems. That remains this project's
clearest actionable finding, and the open question — Phase 4's result is one-model-robust, not yet
confirmed on DeepSeek or in the Phase 8 zoo — is the natural next validation if this project
continues.

**What this synthesis does not decide**: whether the accumulated null (an execution floor that eight
phases, four training lineages, and every tried intervention except budget-allocation policy fail to
move) is written up as a definitive-negative paper finding or kept as an internal record. That framing
call, like the discovery-vs-null headline itself, is explicitly the user's/coordinator's to make.

## Verifier soundness — why these numbers are trustworthy

A 2026-06-14 audit found two verifier holes that produced false-positive solves on hard problems: (1) a
truncated generation could emit a bare `def` preamble that Lean compiles with no goal → scored solved; (2)
a wedged/cross-talked REPL could return an empty no-error response → scored success. Both fixed (commit
`aa659f5`): a solve now requires a declared theorem/lemma/example **and** a REPL response carrying an
`env`. Blast radius: miniF2F Phase 0 had **0** false positives (headline miniF2F numbers stand); miniF2F
Phase 1 had 6/3124 (0.2%); **only ProofNet# was materially corrupted** (constant full-budget truncation),
which is why the ProofNet# baseline and ablations were fully re-run on the fixed verifier. The Step C
soundness creep (above) is the same story from the other side: a scaffolding intervention that *increases*
malformed/loophole attempts is fully absorbed by the fixed verifier — none of the 5 reported flips is a
false accept. Trustworthy numbers depend on the verifier, and we audit it as a first-class artifact.

## What we are NOT building, and why

- **BFS / proof-state search:** deferred. Prior was search < Pass@1, and the flat ProofNet# curve + the
  F3 reasoning floor say more *search* won't fix a problem of proof *execution*, not proof *finding*.
- **ReProver / neural retrieval:** killed, not deferred — F2 shows ~0% knowledge failures, so there is no
  premise to retrieve; BM25 already churned (Phase 1) and hurt OOD.
- **Diversity-injection as a product feature:** the F6 test shows it raises diversity but not solves and
  mildly degrades quality. It served its purpose as the decisive experiment; it is not a lever to ship.

## Methodology lessons worth carrying forward

1. **Paired flips beat mean-deltas** at n=3 seeds; the flip table exposed retrieval as churn.
2. **A second, harder, OOD benchmark earns its cost** — corroborated the miniF2F null and surfaced
   harmful components the easy benchmark masked.
3. **A second model earns its cost** — turned "a Goedel result" into a mechanism that generalizes, and
   surfaced the in-dist/OOD dichotomy.
4. **Distinguish manipulation check from outcome.** A null is only interpretable once you've shown the
   intervention fired; the budget-matched A1 check (not raw distinct counts, which are attempt-confounded)
   is what makes the Step C null meaningful.
5. **Audit the verifier before trusting "good" results** — the impossible-looking ProofNet# Phase 1 rates
   were the tell.
6. **Infra:** sharded co-located sweeps on packed A6000 nodes need per-shard isolation — node-local Lean
   env staging to `/dev/shm`, per-shard vLLM port + endpoint file, stagger vLLM starts (NVML herd), and
   exclude bad nodes (ins082/ins087). Resume the *full* array range, never a sparse subset (num-shards is
   derived from the task count). See `slurm/sweep_array.sh` and PROGRESS.md 2026-06-16/18.
7. **A near-zero result across a new dimension deserves the SAME base-rate check as a "too good"
   result.** Phase 8's 0.0%-everywhere floor looked like a real finding (a clean, consistent
   Base<SFT<RL pattern) right up until it was compared against the models' own published numbers and
   an actual byte-level prompt diff — the same discipline that would catch an implausibly HIGH number
   should be applied symmetrically to an implausibly LOW or implausibly PERFECT one. "Individual
   failures look like genuine math failures" is not sufficient evidence when the base rate (a
   published ~50-60% pass rate) says something is structurally wrong; a harness-sanity control against
   an unaffected reference model is cheap and should be run BEFORE trusting a dramatic null, not just
   before trusting a dramatic positive.
8. **A newly-introduced model config exercises code paths existing tests never covered.** All three
   structural Phase 8 bugs were latent in code that had been shipping (and presumably had been passing
   review / a fast test suite) for weeks — they only surfaced when a genuinely different template
   (`prompt_template != whole_proof`) was exercised for the first time at real scale. Existing
   regression tests locked in the OLD (buggy) behavior's shape without ever exercising the branch the
   new model actually needed; add the new case FIRST as a failing test against real data, not a
   synthetic example that happens to avoid the bug.

## Independent audit, 2026-07-10/16

A full independent audit (`AUDIT_PLAN.md`, ledger in `results/audit/AUDIT_FINDINGS.md`) re-verified this
project's own pipeline end-to-end before any further experiments were queued. **Headline: the execution
floor thesis holds.** One P0 verifier bug was found and fixed (Task A1: the `no_goal` soundness gate
checked the model's raw extracted completion instead of the backend's assembled/compiled source, making
it structurally impossible for any *continuation-style* completion — DeepSeek-V1.5/Leanabell GD-SFT/GD-RL,
Phase 8 only — to ever score solved, regardless of correctness; fixed, permanent real-Lean regression test
added). This **does not affect any Phase 0-7 `whole_proof` (Goedel-V2/DeepSeek-V2) headline number** — the
gate is a no-op for that template family, confirmed both by code (harness-sanity control, 37/37 & 40/40)
and by this audit's own re-derivation of the ProofNet# pass@B curve, oracle ceiling, and Phase 1 flip
table from raw cells, all of which matched the committed numbers exactly (Tasks F1-F2). It DOES implicate
Phase 8's own "0.0%-everywhere corrected floor" headline, which remains open pending a GPU regeneration +
reverify under the fix (not yet actioned — a user decision, since it requires new GPU spend).

**Task B — the highest-value check — is now closed and is MATERIAL, not a no-op.** Does
`set_option maxHeartbeats 0` (added 2026-07-06, absent from every Phase 0-7 sweep) retroactively change any
Phase 0-7 headline result? A full offline CPU re-verify (no GPU, no new generation) of every recorded failed
attempt on the trapped core — problems that never solved at ANY budget — across all 4 (model × benchmark)
cores found **13 of 1212 re-verified cells (1.1%) flip from failed to solved**, covering 8 distinct
(problem, model) pairs out of 406 trapped-problem instances (2.0%): Goedel×miniF2F 3/159, Goedel×ProofNet#
3/450, DeepSeek×ProofNet# 0/420 (unaffected), DeepSeek×miniF2F 7/183. Per this task's own pre-registered
decision rule (any flip on any model is material), this is a real, if modest, correction: Lean's OLD
internal heartbeat limit was rejecting a small number of genuinely-correct proofs before they could finish
compiling, and the Phase 0-7 execution floor was inflated by that amount. **This is a scoring correction,
not a new capability finding** — every flipped cell's proof was already present in the ORIGINAL Phase 0-7
generation; nothing new was generated, and the fix can only ever widen (never narrow) what counts as
solved, so no reported number was an *over*-count.
**[CORRECTED — see Corrections log #2: "scoring correction" undersells the miniF2F effect. The
2026-07-24 truncation/heartbeat audit found the missing `maxHeartbeats 0` setting affected 17.8-17.75%
of REFINE steps on miniF2F (both models), i.e. it distorted the trajectory the refinement loop saw at
the time, not just the final scoring of a handful of terminal cells. The final-flip count (13/1212)
still stands as the *scoring* correction; the *trajectory-distortion* rate is a separate, larger number
that hasn't been folded into any headline yet.]** The corrected floor numbers (folding these 13 cells'
`tokens_to_solve` back into the affected curves) have not yet been recomputed — an arithmetic-only
follow-up, not a new experiment, and not expected to change the thesis at this magnitude. Task B's Step 4
(broadening the reverify to a sample of *all* near-frontier failures, not just the trapped core, to check
for a similar effect on the mid-curve) was not performed — flagged as a residual open item, not blocking.

With Tasks A0-A2, B, C-G all terminal, this audit is closed and `PLAN_NEXT.md`'s WS1 (the Phase 4
validation critical path, which reuses this exact harness) is unblocked, carrying the small pending
floor-number correction above as a known, quantified, non-blocking caveat.

## Corrections log (added 2026-07-25, does not modify the text above)

An external calibration sprint (triggered by an outside review of the committed results) found four
issues in how the numbers above are framed. None require retracting a headline result; all require
more precise language before reuse in a writeup. Full derivation in `CALIBRATION_FINDINGS.md` and
`DECISIONS.md` (2026-07-21 through 2026-07-25b).

1. **"miniF2F saturates to a ~72–75% ceiling"** is imprecise. The pass@N recount
   (`results/phase0/PASS_AT_N_RECOUNT.md`) found that at 128k tokens the refinement loop consumes most
   of the budget: median 1 independent propose attempt per cell (max 14). The plateau is *at least
   partly* an artifact of the harness running out of independent attempts, not solely a demonstrated
   capability ceiling of the model. Correct reading: "plateaus because the refinement-heavy agent loop
   exhausts its independent-attempt budget before exhausting tokens," pending further work to isolate
   how much of the plateau is genuine model ceiling vs. this artifact.

2. **"This is a scoring correction, not a new capability finding"** (the `maxHeartbeats` fix,
   Task B above) undersells the miniF2F effect specifically. The trajectory-distortion rate — REFINE
   steps immediately preceded by a spurious Lean heartbeat-timeout — is 17.80% (Goedel×miniF2F,
   550/3090) and 17.75% (DeepSeek×miniF2F, 718/4046); ProofNet# is far less affected (3.35% and 1.64%).
   The 13/1212 final-flip count is still the right number for "how many cells changed verdict," but
   "scoring correction" implies the bug only touched final scoring — it also fed distorted feedback
   into ~1 in 6 refinement steps on miniF2F, which could have steered trajectories away from solutions
   that a correctly-scored refine step might have found. Not yet quantified; flagged, not corrected.
   (`results/phase0/TRUNCATION_AND_TIMEOUT_AUDIT.md`.)

3. **Trapped-core claims (Phase 2 Step C, Phase 5, Phase 7 — "trapped ⇒ 0% baseline by construction")**
   need a stated recovery-rate caveat, with two separate numbers, not one:
   - **Iso-compute (governs the claims as originally made):** on Goedel×miniF2F's 55-problem trapped
     core, plain resampling at the *original 128k-token budget* recovers 3/55 (possibly 4/55 counting
     one borderline case) — inside the pre-registered "sound" band. The claims stand close to as
     reported.
   - **Uncapped pass@32 (governs comparison to published pass@N results):** the same population
     recovers 6/55 (10.9%) under 32 independent samples with no budget cap. This is a different,
     weaker claim about compute availability, not about whether the 128k-budget agent loop was
     well-allocated. The recovery hazard is flat through N=32 (solved-at-attempt: 3, 10, 18, 19, 23,
     27) — report as "≥11% at N=32, curve not yet flat," not a fixed rate.
   - One of the 6 pass@32 recoveries (`amc12a_2021_p8`) is a known exact miniF2F↔Lean-Workbook overlap
     (`results/phase6/DISJOINTNESS.md`) — footnote it as possible train/eval leakage when citing this
     number.
   - The Step C null specifically is better stated as "no clear improvement over token-matched plain
     resampling" (2/55 vs. a 1/55 resampling control, the 1 being the contamination-flagged case above)
     rather than "no improvement over zero."
   - Only Goedel×miniF2F has been calibrated this way. DeepSeek's trapped cores (both benchmarks) and
     Goedel×ProofNet# (which carries Phase 7's 0/150 headline) remain uncalibrated — open items, see
     `CALIBRATION_FINDINGS.md`.

4. **The 2k-token budget point** on every headline curve is attempt-starved: median ZERO full propose
   attempts complete within a 2k-token cap (`results/phase0/ATTEMPTS_PER_BUDGET_TABLE.md`). Footnote it
   as such rather than treating it as a comparable point on the same curve as 8k/32k/128k.
