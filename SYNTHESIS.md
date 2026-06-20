# Synthesis — Budget-Bounded Agentic Theorem Proving

*Consolidated findings as of 2026-06-18. Source of truth for the numbers: `PROGRESS.md` (dated lab
notebook), `DECISIONS.md`, `results/*/metrics.json`, `results/phase1/FINDINGS.md`, and
`results/phase2/MECHANISM.md`. This file is the one-page story; those are the receipts.*

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

- **Same shape on both models.** miniF2F is steep early (≈+30pp over 2k→8k) then saturates to a ~72–75%
  ceiling by 128k; ProofNet# is ~3–5× harder at every budget and far flatter — it keeps buying proofs but
  the curve is still climbing at 128k from a low base. The budget-saturation *asymmetry* (in-distribution
  saturates; OOD stays budget-hungry) is not a Goedel artifact — it replicates on an independent prover.
- **A cross-model dichotomy.** Goedel slightly edges DeepSeek in-distribution (−2 to −3pp on miniF2F), but
  **DeepSeek clearly beats Goedel on the harder OOD ProofNet# at every budget, and the gap widens with
  budget** (+8pp at 128k: 22.2 vs 14.3). On out-of-distribution math the smaller 7B model both scores
  higher and extracts *more* from extra compute.

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
3. **Forced diversity mildly *degrades* output:** last-attempt failures shift from `reasoning_deep`
   (38–88%) to majority `formalization_syntax` (62–74%) + `loophole_sorry` (23–36%); soundness-relevant
   rates creep up (loophole ~3×, syntax ~1.5–2×). Pushed for novelty, the model leaves its competent
   manifold — but **every degraded attempt is caught by the verifier (0 false solves)**, so result
   soundness is intact and the scaffolding is counterproductive, not neutral.

## The thesis

**Compute budget — not agentic scaffolding — is the lever for whole-proof proving at this scale.** This
holds across two independent provers and two benchmarks, and is supported at three levels: Phase 1
(OFAT-null, with two scaffolding components that *hurt* OOD), Phase 2 mechanism (F1–F4: diversity collapse
onto a deep-reasoning floor with nothing to retrieve), and the F5→F6 interventional test (forcing the one
scaffolding move the mechanism implicates raises diversity but not solves, and degrades quality). The
remaining levers are model capability and raw budget.

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
