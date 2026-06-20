# Phase 2 / Step A — Mechanism (CPU-only, data already on disk)

Source: `scripts/analyze_mechanism.py` over `results/baseline/agent_states` (miniF2F, 704/732 cells; 28
empty states excluded) and `results/proofnet_baseline/agent_states` (ProofNet#, 558/558). Raw numbers in
`results/phase2/mechanism.json`. No GPU/Lean. This step exists to explain the central asymmetry — budget
converts to solves on miniF2F (29.6→74.9% over 64×) but barely on ProofNet# (4.8→14.3%) — and thereby
explain the Phase 1 scaffolding null.

## Finding 1 — pass@B saturates because sample diversity collapses at the *approach* level

Per unsolved cell, across ~19–24 attempts the model commits to only **~2 distinct opening tactics**:

| group (benchmark)   | mean attempts | distinct first-tactics | distinct skeletons |
|---------------------|---------------|------------------------|--------------------|
| miniF2F  unsolved   | 18.9          | **1.94**               | 6.1                |
| ProofNet# unsolved  | 23.6          | **2.28**               | 9.0                |
| miniF2F  solved     |  2.1          | 1.01                   | 1.4                |
| ProofNet# solved    |  6.3          | 1.04                   | 3.0                |

(Absolute distinct counts, not ratios — ratios are mechanically depressed by attempt count, so we report
counts.) Two reads:
- **The model explores ~2 high-level approaches and then resamples variants of them.** Skeletons vary
  more than first-tactics (6–9 vs ~2), i.e. it reshuffles *downstream* tactics inside ~2 fixed frames
  rather than reconsidering the approach. Once neither frame closes the goal, extra budget buys
  near-duplicate proofs → **the flat tail of pass@B on *both* curves.**
- **This is a property of hard/unsolved problems, not of OOD-ness per se** — unsolved cells collapse
  identically on both benchmarks (~2 first-tactics). The benchmark asymmetry is just the *fraction* of
  problems trapped in this regime: miniF2F 25% unsolved vs ProofNet# 86%. ProofNet#'s curve is flat
  because nearly all its problems fall into the collapse regime almost immediately.

## Finding 2 — the bottleneck is REASONING, not knowledge or formalization  *(the decision gate)*

Failure-mode taxonomy over unsolved cells (per-cell most-advanced failure reached):

| bucket                          | miniF2F | ProofNet# | what it means              |
|---------------------------------|---------|-----------|----------------------------|
| reasoning (deep + shallow)      | 98.9%   | 95.2%     | elaborates, can't close goals |
| formalization / syntax          |  1.1%   |  3.8%     | can't write valid Lean     |
| knowledge / hallucinated lemma  |  0.0%   |  **1.0%** | cites a non-existent premise |

**The dominant failure is not finding/closing the proof, not missing premises and not writing Lean.**
This gates every downstream option, with data instead of a hunch:
- **Retrieval is doomed by construction** — premise-availability is <1% of the problem. This is *why*
  naive BM25 was null/harmful in Phase 1: it injected plausible-but-irrelevant premises into problems
  whose bottleneck was reasoning, distracting generation (matches the −36 flip count on ProofNet#).
  A fancier retriever (ReProver) is unmotivated. **Killed.**
- **BFS / proof-state search is doomed** — the failure is closing goals while exploring only ~2
  approaches (Finding 1); stepping with the same weak per-step policy adds no new approach. **Held.**
- **Diversity injection is the one motivated positive lever** — it directly targets Finding 1. → Phase 2
  Step C is justified (temperature/nucleus scheduling across the budget, or prompting for explicitly
  distinct approaches). Contingent only on it actually moving pass@B.

## Finding 3 — depth-of-failure: a capability floor, not an "almost-solving" tail

Deepest step reached before the first error (proxy for how far the proof gets):

| benchmark | median deepest step | p90 | frac never past step 1 |
|-----------|---------------------|-----|------------------------|
| miniF2F   | 64                  | 137 | 1.1%                   |
| ProofNet# | 23                  | 65  | 10.0%                  |

miniF2F unsolved fail *deep* in long elaborated proofs (it tries hard, writes a lot, can't close).
ProofNet# stalls earlier (median step 23) and has 10× more genuine can't-starts (10% never past step 1),
but 90% still get going. Neither is a near-miss tail one nudge from solving — it is a **capability floor**:
the model produces substantial proofs it cannot complete. (Caveat: "deepest step" is first-error depth,
not a proof of near-correctness.)

## Finding 4 — no easy subfield on ProofNet#

Solve rate by subfield (name prefix): ProofNet# best are Dummit 0.26 / Rudin 0.22 / Artin 0.21, worst
Axler 0.12 / Ireland 0.13 — a hard core *across* topics, not one bad area. miniF2F is concentrated in
easy competition buckets (amc12 0.94, mathd 0.94), with algebra/numbertheory lower. Confirms the flat
ProofNet# curve is a uniformly hard set, not a mix of easy+impossible.

## Finding 5 — pre-flight: the collapse is SYMPTOMATIC, not causal (predicts Step C nulls)

Step C exists to discriminate two stories consistent with F1: *causal* (the model could solve more if it
stopped re-trying ~2 approaches → forcing exploration unlocks solves) vs *symptomatic* (it collapses to
~2 approaches because it has no better one → more approaches buy more distinct flailing). Cheap
existing-data test: when a problem is solved **late** (first verifying attempt at index w≥3), did the win
use an opening tactic the model had **not** already tried before the win (exploration unlocked it), or one
it had already been using (better execution of a known approach)?

| benchmark | early solves (w=1–2) | late solves (w≥3) | new-approach @ late | switched-from-first @ late |
|-----------|----------------------|-------------------|---------------------|----------------------------|
| miniF2F   | n=45                 | n=64              | **0.0%**            | 1.6%                       |
| ProofNet# | n=11                 | n=31              | **0.0%**            | 0.0%                       |

**Late solves essentially never come from a newly-explored approach.** Combined with F1 (only ~2 distinct
openings total), the model wins late by getting the *execution* of an already-chosen approach right, not
by discovering a new one. This is direct evidence that approach-diversity is **symptomatic of the
capability floor** (F2/F3), not the lever — and it **predicts Step C (diversity injection) will null**.
That reframes C from "the lever that works" to **the decisive confirmation**: if injecting approach
diversity raises the diversity metric but not solve rate, it confirms the strongest form of the thesis
(even the intervention targeting the mechanism fails because the mechanism is a symptom). Caveats: this is
correlational and only observes the model's *natural* sampling — it cannot prove that *forcing* a broader
approach set can't help (that is exactly what C tests); "approach" = opening-tactic heuristic.

## Verdict → updates to PHASE2_PLAN.md

1. **Mechanism established:** budget saturates because the model collapses to ~2 proof approaches per
   hard problem; the unsolved residue is a reasoning/capability floor, not premise- or syntax-limited.
   This *explains* the scaffolding null — retrieval/memory/reviewer/skeletons don't touch approach
   diversity or goal-closing, so they could not have helped.
2. **Gate (A2) result:** retrieval & ReProver **killed**; BFS **held**; third benchmark unmotivated.
3. **Next GPU spend:** **Step C (diversity injection)** — but F5 reframes it as the *causal-vs-symptomatic
   discriminator* and predicts a NULL (collapse looks symptomatic). Run it scoped & cheap (trapped cells
   only, 8k/32k) and measure BOTH solve-rate AND whether approach-diversity actually moved (the 2×2: a
   null is only meaningful if diversity provably rose). Prefer approach-conditioning over raw temperature
   (temperature risks reviving the truncation/false-solve pathology — run on the fixed verifier and watch
   the syntax-failure rate). **Step B (DeepSeek-Prover-V2-7B replication)** runs in parallel (independent
   of C) to show mechanism + flat-OOD + scaffolding-null generalize beyond Goedel-V2-8B; defer only B's
   diversity-injection arm until C resolves.
4. **Caveats:** heuristic tactic parsing (leading-identifier, not a Lean AST); solved-vs-unsolved
   diversity is confounded by attempt count (solved stop early) — the robust claim is the absolute ~2
   first-tactics over ~20 attempts in unsolved cells and the unsolved-vs-unsolved match across benchmarks;
   28 empty miniF2F states excluded.

================================================================================
F6 / STEP C — INTERVENTIONAL TEST OF F5 (diversity injection), both provers × both benchmarks
================================================================================
Ran approach-conditioned DiversityInjection on the trapped cores (problems unsolved by ALL seeds @128k
baseline) @8k/32k, 3 seeds: Goedel miniF2F (55), Goedel ProofNet# (150), DeepSeek miniF2F (61),
DeepSeek ProofNet# (140). Jobs 10726054/55/56/57. Pre-registered prediction (DECISIONS 2026-06-17/18):
diversity rises, solves stay flat, forced-new approaches still fail. VERDICT: CONFIRMED on all 4 arms.

1. MANIPULATION CHECK PASSED (budget-matched @32k — both baseline and diversity truncated to cumulative
   completion_tokens<=32k, so NOT confounded by baseline's 128k attempt count). Diversity demonstrably
   raised opening-tactic exploration in every arm (distinct-first-tactics / attempt; attempt counts
   matched within ~2%):
     Goedel  miniF2F   0.243 -> 0.349 (+44%)   abs distinct 1.17->1.71
     Goedel  ProofNet# 0.206 -> 0.292 (+42%)   abs distinct 1.29->1.77
     DeepSeek miniF2F  0.175 -> 0.294 (+68%)   abs distinct 1.02->1.73
     DeepSeek ProofNet#0.126 -> 0.214 (+70%)   abs distinct 1.07->1.80
   => the intervention fired; the null below is INTERPRETABLE.

2. SOLVES: NULL. pass@8k/32k on trapped (baseline=0 BY CONSTRUCTION): Goedel miniF2F 0.6/1.2%, Goedel
   ProofNet# 0.0/0.7%, DeepSeek miniF2F 0/0%, DeepSeek ProofNet# 0/0%. Exactly 5 genuine verified flips
   (reason==ok) across all 4 arms — 2 Goedel miniF2F (algebra_apbon2..., amc12b_2021_p18), 3 Goedel
   ProofNet# (Munkres 18_8a, Rudin 4_4b x2 seeds), ZERO DeepSeek. All within seed-std of zero. Forcing
   +40-70% more approach diversity bought ~nothing. => APPROACH DISCOVERY IS NOT THE BOTTLENECK; the
   binding constraint is within-approach EXECUTION (the F2/F3 deep-reasoning floor). This closes F5's
   correlational/survivor-conditioned gap with an interventional experiment, on TWO independent provers.

3. SECONDARY FINDING — diversity injection DEGRADES output quality (does not merely fail to help).
   Last-attempt failure texture shifts massively from reasoning to malformed/cheating:
     baseline reasoning_deep  38-88%  ->  diversity reasoning_deep <=3%
     diversity last-attempt now majority formalization_syntax (62-74%) + loophole_sorry (23-36%).
   Soundness-relevant rates creep UP in every arm (all-attempt %): loophole_sorry ~tripled
   (1-3% -> 4-10%), formalization_syntax up ~1.5-2x (8-22% -> 16-32%). Pushed for novelty, the model
   leaves its competent manifold and emits more syntactically broken and sorry/loophole proofs.
   CRUCIAL: every one of these is CAUGHT by the (fixed) verifier — none counts as a solve (solves stayed
   ~0) — so RESULT soundness is intact. This both (a) reinforces the verifier-soundness contribution and
   (b) shows forced-diversity scaffolding is mildly COUNTERPRODUCTIVE, not neutral.

BOTTOM LINE (Phase 2): across 2 models × 2 benchmarks, compute budget — not agentic scaffolding — is the
lever for whole-proof proving at this scale. Retrieval/review/budget-realloc were OFAT-null (Phase 1);
the mechanism is diversity-collapse onto a deep-reasoning floor (F1-F4) with late-solves never from new
approaches (F5); and the decisive interventional test (F6/Step C) shows forcing approach-diversity raises
diversity but not solves and degrades proof quality. The remaining lever is model capability + budget.
