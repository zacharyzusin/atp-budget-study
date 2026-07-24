# Project Summary — Budget-Bounded Agentic Theorem Proving

*Written 2026-07-21, expanded to full experimental detail on request. Source of truth remains
`SYNTHESIS.md` (consolidated narrative), `PROGRESS.md` (dated lab notebook, ~3900 lines),
`DECISIONS.md` (design choices + pre-registrations, ~1800 lines), and each phase's own result doc
under `results/*/` (the "receipts" this file draws its numbers from: `results/phase1/FINDINGS.md`,
`phase2/MECHANISM.md`, `phase3/HAMMER_PROBE.md`, `phase4/ALLOCATION.md` +
`ALLOCATION_MECHANISM.md`, `phase6/{DISJOINTNESS,FINETUNE,STAGE_C_DECISION,STAGE_C_PROBE_SPEC,
STAGE_C_RESULT}.md`, `phase7/STEPWISE.md`, `phase8/ZOO.md`, `audit/AUDIT_FINDINGS.md`). This file
exists so a reader can see exactly what was run, on what data, with what config, and what the exact
numeric result was, for every phase, without reconstructing that from the raw notebooks.*

---

## 1. The question we set out to answer

For a fixed whole-proof Lean theorem prover (an LLM that writes a complete proof attempt, gets it
checked by Lean, and retries within a token budget):

1. **Does agentic scaffolding help?** — does adding retrieval of relevant lemmas, memory of past
   failed attempts, an LLM "reviewer" step, tactic-skeleton hints, or smarter *within-problem*
   budget allocation buy more solves at a fixed token budget, on top of just sampling more
   whole-proof attempts?
2. **If not, why not** — what is actually limiting the model, and is there any lever (search
   strategy, more compute, fine-tuning, RL) that moves it?
3. **(Emerged mid-project, became the main positive result)** Does *how you divide a fixed total
   compute budget across a batch of different problems* matter, independent of any change to the
   model or its scaffolding?

## 2. Setup

- **Two independent provers:**
  - Goedel-Prover-V2-8B (`Goedel-LM/Goedel-Prover-V2-8B` @ `dfd02e6`, Lean v4.9.0-rc1 + mathlib4
    `2f65ba7`).
  - DeepSeek-Prover-V2-7B (`deepseek-ai/DeepSeek-Prover-V2-7B` @ `a8d9e144`, Lean v4.9.0 + standard
    mathlib4 `f0957a7`).
  - Lean itself (official REPL backend) is the authoritative verifier.
- **Two benchmarks:** miniF2F-test (244 audited problems, in-distribution/competition-style) and
  ProofNet# (186 test problems, undergrad-level, out-of-distribution, ~3-5x harder).
- **Variance discipline:** ≥3 seeds for every headline number (8 for the final DeepSeek allocation
  cell), mean ± seed-std. A delta under ~1 baseline seed-std is treated as noise ("the noise bar,"
  set 2026-06-11, applied throughout).
- **Verifier soundness audited twice** (2026-06-14 and 2026-07-10/16) — see §9. This matters more
  than it might sound: essentially every claim in this project is "the model could/couldn't solve
  X," and that claim is only as good as the thing deciding "solved."

## 3. Phase 0 — Baselines (the pass@budget curves)

The whole-proof baseline sweep for both models × both benchmarks, no scaffolding, `alloc_split=0.5`,
`max_iters=4` refinement. 3 seeds each, full 244/186 problem sets, budgets [2k, 8k, 32k, 128k].

| budget | miniF2F · Goedel | miniF2F · DeepSeek | ProofNet# · Goedel | ProofNet# · DeepSeek |
|--------|------------------|--------------------|--------------------|----------------------|
| 2k   | 29.6% ± 3.3% | 27.9% ± 2.1% | 4.8% ± 1.4% | 5.4% ± 0.5% |
| 8k   | 60.1% ± 1.9% | 57.9% ± 1.7% | 9.3% ± 1.1% | 13.1% ± 0.8% |
| 32k  | 69.5% ± 0.6% | 67.1% ± 0.9% | 12.0% ± 0.6% | 18.3% ± 1.6% |
| 128k | 74.9% ± 0.9% | 72.0% ± 0.5% | 14.3% ± 0.8% | 22.2% ± 1.7% |

**Reading:** miniF2F saturates (~72-75% ceiling by 128k, most of the gain by 8k); ProofNet# never
saturates in this range and is still climbing at 128k, at much lower absolute rates. This asymmetry
replicates independently on both models — it's a task property, not a model artifact.

**Cross-model dichotomy, checked for artifacts:**
- Goedel edges DeepSeek in-distribution (−2 to −3pp on miniF2F) but DeepSeek clearly and
  increasingly beats Goedel out-of-distribution (+8pp at 128k on ProofNet#: 22.2 vs 14.3%, gap
  widens with budget).
- **H1 (not a port artifact):** both provers attempt the identical canonical statement sets (244
  miniF2F, 186 ProofNet#, zero disjoint names) and every statement elaborates on *both* Lean pins
  (244/244 and 186/186 each) — the compile-on-both-pins intersection is the full set, so the gap is
  real, not a coverage difference.
- **H4 (mechanism):** the OOD advantage is deeper within-approach execution, not more approach
  diversity — every DeepSeek-only ProofNet# win is on an opening Goedel also tried but couldn't
  close, and on shared misses DeepSeek diversifies *less* (3.08 vs 4.07 distinct openings) yet
  elaborates *deeper* (median deepest step 29 vs 24). Conclusion: the real OOD lever is the model's
  own training, not scaffolding or search.

## 4. Phase 1 — Agentic scaffolding OFAT ablation: null (job 10436909, then 10461442/10481853)

**First pass** (job `10436909`, `slurm/ablation.sh configs/phase1_ablation.yaml`, 7 cells, 3 seeds,
Goedel-V2, miniF2F, B=8000, n_workers=8, all cells 732/732 complete):

| cell | component / setting | pass@8000 | Δ vs baseline | median tokens-to-proof |
|---|---|---|---|---|
| baseline | all off, alloc_split 0.5 | 60.1 ± 3.3% | (ref) | 1953 |
| budget_alloc__0 | alloc_split 0.0 (all fresh samples) | 60.7 ± 1.8% | +0.5 pp | 1968 |
| budget_alloc__2 | alloc_split 1.0 (all refinement) | 60.5 ± 0.9% | +0.4 pp | 1965 |
| memory__1 | within-problem failure memory | 60.5 ± 3.1% | +0.4 pp | 1916 |
| reviewer__1 | LLM critic (non-authoritative) | 60.4 ± 2.3% | +0.3 pp | 1922 |
| retrieval__1 | BM25 premise selection (k=8) | **63.5 ± 1.9%** | **+3.4 pp** | 1935 |
| tactic_skeletons__1 | strategy-hint schedule | 61.1 ± 2.3% | +1.0 pp | 1990 |

Baseline seed-std is 3.3pp, so retrieval's +3.4pp was the only delta that cleared noise; everything
else (budget_alloc, memory, reviewer, tactic_skeletons) sat well inside it. A **reviewer safety
check** (the critic is consulted only on Lean-rejected candidates, so any ACCEPT it emits is by
definition a false accept) found it accepted **17 of 249 (6.8%)** already-failed candidates —
confirms an LLM critic is not a trustworthy verifier and Lean must stay authoritative (which it
does — the reviewer never gates a solve, only adds critique text to refinement).

**Retrieval promoted, then failed to replicate** (job `10461442`, resumed `10481853`, cross-budget
[2k, 8k, 32k], 3 seeds, full 244 problems, both cells 732/732):

| B | baseline | retrieval | Δ (pp) |
|---|---|---|---|
| 2000 | 0.3033 ± 0.0309 | 0.3251 ± 0.0237 | +2.2 |
| 8000 | 0.5943 ± 0.0148 | 0.6011 ± 0.0144 | +0.7 |
| 32000| 0.7008 ± 0.0071 | 0.6926 ± 0.0082 | −0.8 |

At 8k this run gives **+0.7pp, not the +3.4pp** the first campaign reported — run-to-run variance
(vLLM sampling is not bitwise-reproducible across separate processes), and retrieval's lift shrinks
with budget and goes negative by 32k. A **paired-flip analysis** (which specific problems changed,
per seed) makes the mechanism explicit:

| B | gained (retrieval solved, baseline didn't) | lost | net |
|---|---|---|---|
| 2000 | +47 | −31 | +16 |
| 8000 | +46 | −41 | +5 |
| 32000| +20 | −26 | −6 |

Gains ≈ losses at every budget — a real premise signal would make gains *dominate*; this symmetric
churn means the BM25 context perturbs stochastic sampling rather than injecting usable premises.
**Revised conclusion: retrieval is not a robust lever; the Phase 1 +3.4pp was itself within the
noise band and simply did not replicate.**

**ProofNet# ablation** (harder benchmark, paired flips vs the ablation baseline):

| component | gains | losses | net | verdict |
|---|---|---|---|---|
| reviewer | 13 | 10 | +3 | noise-like |
| budget_alloc__2 | 9 | 11 | −2 | noise-like |
| memory | 8 | 10 | −2 | noise-like |
| tactic_skeletons | 9 | 12 | −3 | noise-like |
| budget_alloc__0 | 6 | 25 | **−19** | **directional (hurts)** |
| retrieval | 6 | 42 | **−36** | **directional (hurts)** |

Four of six are noise-like on this benchmark too, but two are now directionally *harmful*:
front-loaded allocation (no escalation) and BM25 retrieval (42 baseline solves lost for only 6
gained). **Bottom line: no Phase 1 scaffolding component is a net-positive lever anywhere; on the
harder benchmark two are measurably harmful.**

## 5. Phase 2 — Mechanism: why doesn't scaffolding help? (CPU-only trace mining + causal test)

Source: `scripts/analyze_mechanism.py` over on-disk attempt traces (miniF2F 704/732 cells with
states, ProofNet# 558/558). No GPU.

**F1 — diversity collapse.** On unsolved cells, across 18.9-23.6 attempts the model commits to only
~1.94-2.28 *distinct* opening tactics (vs ~1.0-1.04 on solved cells, which stop almost immediately).
It reshuffles downstream tactic variants inside ~2 fixed approach-frames rather than reconsidering
the approach — this is the mechanical source of the flat pass@B tail on both curves, and it's a
property of *unsolved* problems, not of OOD-ness per se (unsolved cells collapse identically on
both benchmarks; the benchmark asymmetry is just the *fraction* trapped in this regime: miniF2F 25%
unsolved vs ProofNet# 86%).

**F2 — failure taxonomy (the decision gate).** Failure-mode breakdown over unsolved cells:

| bucket | miniF2F | ProofNet# |
|---|---|---|
| reasoning (deep+shallow) | 98.9% | 95.2% |
| formalization/syntax | 1.1% | 3.8% |
| knowledge/hallucinated lemma | 0.0% | 1.0% |

The dominant failure is deep reasoning, essentially never a missing premise. This is *why* retrieval
was doomed by construction (nothing to retrieve) — directly explains Phase 1's null on that
component — and why BFS/proof-state search is also doomed (the failure is closing goals while
exploring only ~2 approaches; stepping with the same weak per-step policy adds nothing).

**F3 — capability floor, not a near-miss tail.** Deepest step reached before first error: miniF2F
median 64 (p90 137, only 1.1% never past step 1); ProofNet# median 23 (p90 65, 10.0% never past step
1). Neither benchmark shows a "one nudge from solving" tail — the model produces substantial partial
proofs it cannot complete.

**F4 — no easy subfield.** ProofNet# solve rates run 21-33% uniformly across every subject area
(Dummit 0.26 best, Axler 0.12 worst) — a hard core across topics, not a mix of easy+impossible.

**F5 — late solves are not new approaches (correlational).** When a hard problem solves late (first
verifying attempt at index ≥3), it comes from re-sampling the *same* approach 0.0% of the time from a
newly-explored one, on both benchmarks (miniF2F n=64 late solves, ProofNet# n=31). This *predicts*
that forcing approach-diversity won't help, but is only correlational (natural sampling).

**F6 / Step C — the interventional test (jobs 10726054/55/56/57).** Built an approach-conditioned
`DiversityInjection` component (lists distinct openings already tried, asks for a fundamentally
different approach) and ran it on the trapped cores (unsolved by ALL seeds at 128k baseline) at
8k/32k, 3 seeds, all four model×benchmark cells (Goedel miniF2F n=55, Goedel ProofNet# n=150,
DeepSeek miniF2F n=61, DeepSeek ProofNet# n=140). Pre-registered prediction: diversity rises, solves
stay flat.

1. **Manipulation check PASSED** (budget-matched @32k, so not confounded by attempt-count):
   distinct-openings-per-attempt rose in every arm — Goedel miniF2F 0.243→0.349 (+44%), Goedel
   ProofNet# 0.206→0.292 (+42%), DeepSeek miniF2F 0.175→0.294 (+68%), DeepSeek ProofNet#
   0.126→0.214 (+70%). The intervention genuinely fired.
2. **Solves: NULL.** pass@8k/32k on trapped cells (baseline = 0 by construction): Goedel miniF2F
   0.6%/1.2%, Goedel ProofNet# 0.0%/0.7%, DeepSeek both 0%/0%. Exactly **5 genuine verified flips**
   across all four arms (2 Goedel miniF2F, 3 Goedel ProofNet#, **zero on DeepSeek**), all within
   seed-std. **Approach discovery is not the bottleneck; within-approach execution is** — proven
   causally (not just correlationally) on two independent provers.
3. **Diversity injection mildly degrades output.** Last-attempt failure mode shifts from
   `reasoning_deep` (38-88% at baseline) to majority `formalization_syntax` (62-74%) +
   `loophole_sorry` (23-36%). Soundness-relevant rates creep up (loophole ~3x, syntax ~1.5-2x) but
   **every degraded attempt is caught by the verifier** (0 false solves) — sound but counterproductive.

## 6. Phase 3 — Hammer/SMT leaf-closing probe: NO-GO (2026-06-20, CPU-only)

Motivation: if the OOD floor is within-approach execution/leaf-closing (H4), the natural next test
is handing the model's stuck leaf to a symbolic closer.

| Arm | what | result |
|---|---|---|
| Positive control | portfolio on 4 synthetic trivial goals | 4/4 PASS (probe fires correctly) |
| Arm 0 | portfolio on the **original** trapped statement | **0/30** |
| Arm A-lite | portfolio swapped in for the model's failing tactic, in-context | **0/40** |

Portfolio = `omega | nlinarith | norm_num | simp_all | decide | aesop` (on-pin tactics; `grind`,
`duper`, Lean-SMT/LeanHammer are not on the v4.9.0 pin, so a real superposition prover was never
tested — an explicitly honest caveat). Pre-registered NO-GO threshold was <~2pp closure across arms;
met (0pp on both cheap arms). **Recommendation: NO-GO on porting `duper`** — the converging
negatives (Arm0=0, Arm-A-lite=0, H4 execution-floor, Step C forced-diversity null) make the EV of a
1-2 day infra investment low, though a real hammer was never decisively ruled out.

## 7. Phase 4 — Compute-optimal budget allocation (the positive result)

Not a model or scaffolding change — a policy for *how to spend* a fixed total token budget across a
batch of problems (abandon cells a predictor flags as trapped at a decision checkpoint c*,
reallocate to survivors), vs. flat per-problem allocation. All numbers are **offline arithmetic**
over the four already-committed budget-independent Phase 0 baseline runs — no new GPU spend, because
realizability is by construction (the agent's trajectory never depends on the announced budget, so a
kept cell's logged 128k trajectory IS the realized run, and an abandoned cell's prefix already shows
no solve). Code: `src/atp/alloc/` (36 tests); scripts `phase4_ceiling.py`, `phase4_predictor.py`,
`phase4_frontier.py`, `phase4_perseed.py`.

**Headline table** ("save@X%" = fraction of total compute saved vs. uniform to reach X% of solvable
cells, pooled over seeds):

| model × benchmark | save@80% | save@90% | save@95% | save@100% | per-seed@90% (original 3-seed) | call |
|---|---|---|---|---|---|---|
| goedel × ProofNet# | +15% | **+30%** | +24% | −2% | **+26% ± 7%** (+25/+18/+34) | **STRONG, robust** |
| deepseek × ProofNet# | −16% | +10% | +1% | +14% | −13% ± 28% (+5/+9/−51) | WEAK/fragile |
| goedel × miniF2F | — | −16% | −22% | −0% | −40% ± 18% (−17/−62/−42) | negative (contrast) |
| deepseek × miniF2F | −64% | −16% | −22% | −0% | −13% ± 28% (−30/−28/+2) | negative (contrast) |

**Two load-bearing caveats:** (1) the win is at a fractional-accuracy operating point (90-95%), not
100% — the hardest solvable cells cost as much as trapped ones, so at 100% accuracy the policy
retains almost everything and saves ~0; a property of the problem, not a tuning failure. (2)
Efficiency, not raw accuracy, is the robust axis — at fixed compute the realizable policy beats
uniform only modestly (+0.2-0.5pp on ProofNet#) because a single decision checkpoint imposes a
compute floor.

**Oracle ceiling** (`phase4_ceiling.py`, the unrealizable knapsack-optimal reallocation, for scale):
Goedel×miniF2F 95.2% compute saved at equal final accuracy, Goedel×ProofNet# 98.1%, DeepSeek×miniF2F
95.1%, DeepSeek×ProofNet# 96.9%. The realizable policy captures roughly **one third** of this
headroom on the Goedel ProofNet# headline (30% saved vs. oracle's 98%) — the gap is a
"predictability cost," not slack left on the table by a bad policy.

**Predictability of "trapped-ness"** (`phase4_predictor.py`, problem-grouped CV AUC, logistic
regression beats gradient boosting): peaks mid-run for Goedel (0.75 @ 8k) and slightly later for
DeepSeek (0.72 @ 16k). The dominant feature at every checkpoint is `tokens_so_far` (elapsed spend
without success — a hazard signal); depth-plateau becomes top-3 only at 16k; opening-diversity never
ranks highly.

**Two multi-round policy variants, pre-registered and falsified (§6):** because the single
checkpoint imposes a compute floor, we built and tested **successive-halving** (cut the weakest
top-η fraction each rung of [2k,4k,8k,16k,32k,128k]) and **multi-round thresholding** (keep the
quality-set ≥τ each rung), hypothesizing a lower floor would lift the loose/negative numbers toward
two-model STRONG.

| ProofNet#, save vs uniform | @80% | @90% | @95% | @100% |
|---|---|---|---|---|
| goedel — single-checkpoint (headline) | +15% | **+30%** | +24% | −2% |
| goedel — successive-halving | −95% | −50% | −25% | −2% |
| goedel — multi-round threshold | +2% | −29% | −18% | −2% |
| deepseek — single-checkpoint (headline) | −16% | +10% | +1% | +14% |
| deepseek — successive-halving | −145% | −99% | −43% | −6% |
| deepseek — multi-round threshold | −34% | −47% | −2% | −5% |

**Both falsified — single-checkpoint remains the best of the three.** Diagnosis: in the
rare-winnable regime, constant-η halving must keep a high fraction each round to retain rare late
solvers (dragging trapped cells to late rungs), and a single τ applied to early rungs (where AUC can
be below chance — DeepSeek 2k AUC=0.47) abandons winnable cells by mistake. **The headline number is
ranking/recall-limited, not floor-limited** — a measured fact across three tested policies, not an
argument. The one place the compute floor genuinely bit (5% of uniform's max compute) is a regime no
one operates in (single-checkpoint solves 0 there; halving edges uniform by +1.1pp but the edge is
gone by 10%). This closed the policy-design phase.

**WS1.2 mechanism follow-up** (`scripts/analyze_allocation.py`, exploratory, no decision rule
pre-registered — 2026-07-16): asked *why* Goedel's effect is clean and DeepSeek's is noisy.
- **M1 (problem-level heterogeneity):** classify each problem as trapped (0/3 seeds solve), partial
  (1-2/3 — pure seed-luck), or robust (3/3). Goedel×ProofNet# partial rate 9.7% vs DeepSeek×ProofNet#
  4.8% — Goedel has ~2x the exploitable seed-luck heterogeneity. But DeepSeek×ProofNet# has 2x the
  robust rate (19.9% vs 9.7%) — when it solves, it solves on every seed.
- **M2 (post-c* population):** DeepSeek×ProofNet# actually has *more* late-bloomer cells in absolute
  terms (36 vs Goedel's 28) and a higher rate (7.7% vs 5.5%) — "less to harvest" is NOT the
  explanation for DeepSeek's fragility. What differs is dispersion: Goedel's late-bloomer costs are
  far more spread out (cost CV 0.83 vs DeepSeek's 0.61).
- **Reading:** a thin-population sampling account, not a pure heterogeneity account — DeepSeek's 36
  late bloomers split ~12/seed, thin enough that a single seed's predictor misranking can swing that
  seed's realized saving by tens of points (exactly the seed-2 collapse to −51% observed). This
  directly motivated spending GPU time on more DeepSeek seeds (WS1.1, §8 below) rather than treating
  the 3-seed result as final.

## 8. WS1.1 — The DeepSeek seed power-up (2026-07-16 through 2026-07-21) and Gate G1

**Pre-registration (2026-07-16, before any new GPU spend):** extend DeepSeek×ProofNet# from 3→8
seeds (config `configs/deepseek_proofnet_power8.yaml`, seeds 3-7, inheriting the baseline's model/
Lean pins unchanged, merged into the same run dir so all 8 seeds aggregate together). Budget
estimate ~90-95 GPU-h (linear scaling off the original 3-seed run's ~55 GPU-h, `sacct -j 10676442`
+ resubmits `10676443`/`10687933`) — over the 50 GPU-h ask-first line, explicitly flagged and
approved per the project's GPU-hour soft-limit norm. **Decision rule, pre-registered verbatim:** if
the 8-seed DeepSeek mean is within 1σ of zero → "one-model-robust, model-dependent," full stop; if
positive and >1σ → claim two-model generality; if negative and >1σ → the divergence becomes the
paper's headline mechanism question.

**Execution (pure infra, ~5 days):** submitted on `burst` (job 11587682 → 11599656), which stalled
for days under genuine cluster-wide GPU+RAM saturation (confirmed via real allocation counts and
free-RAM checks, not just node "MIXED" state — investigated in depth after a user challenge).
Switched to the `short` partition (12h cap) after discovering the sweep script's `--resume` flag
makes a `short`-partition TIMEOUT non-destructive — job 11616556, then chained through repeated
12h-TIMEOUT/resume cycles (11617103 fixing an NVML-GPU-init-contention FAILED batch on node ins089,
then 11628973, 11641972, 11650652) as each 12h wall-clock cap was hit before the ~16-20h/shard
total work finished. All 8 shard-indices reached COMPLETED on 2026-07-21.

**Result:** deepseek × proofnet_sharp per-seed saved@90% (c*=16000): s0=+4%, s1=+3%, s2=+16%,
s3=+54%, s4=−17%, s5=−28%, s6=+29%, s7=+19% → **mean +10% ± 24%** (up from the noise-dominated
3-seed −13% ± 28%; variance did shrink as predicted, sign flipped positive as predicted, but the
effect did not clear the 1σ bar). Goedel×ProofNet# unchanged at 3 seeds, mean +26% ± 7%. Applying
the pre-registered rule: 0 falls within 1σ of the +10% mean (range −14% to +34%) → **"one-model-
robust, model-dependent," full stop** — not a confirmed generalization, and (unlike the 3-seed
read) also not a confirmed negative, just genuinely inconclusive on DeepSeek even at n=8.
`ALLOCATION_MECHANISM.json` was also refreshed at 8 seeds: deepseek_proofnet_sharp trapped%=72.6%,
robust%=17.7%, n_post_c*=1256.

**Gate G1 (pre-registered in PLAN_NEXT.md as the user's call, not this session's):**
- Two-paper world (if allocation generalized or an online policy captured ≥~50% of oracle gain):
  WS3 becomes a standalone paper, WS2 stays the mechanism/null paper.
- One-paper world (if allocation stayed one-model-robust): fold Phase 4 into WS2 as an honestly
  scoped constructive section.
- **Resolved 2026-07-21: user chose one-paper world.** Logged in `DECISIONS.md`. WS3 (a standalone
  online-allocation-policy paper) is not being pursued; Phase 4 folds into the single paper as a
  model-dependent constructive counterpoint to the otherwise-uniform null.

## 9. Phase 5 — Reclaim-and-reinvest: a 4th confirmation of the floor (2026-06-21)

Question: does giving *already-trapped* cells more of the *same* budget (extending past the logged
128k) recover solves, at iso-compute vs. spending that budget on different problems (Phase 4)?
Mechanism: resume from the verbatim logged 128k prefix and sample only the tail (128k, E] — NOT
re-run from scratch, since vLLM sampling isn't bitwise-deterministic and a fresh run would break the
dominance semantics.

**Candidate sets (offline, no GPU):** ProofNet# unsolved-at-128k: Goedel 478 → 391 extend/87 abandon
(conservative rule: n_attempts≥5 ∧ depth_growth≤0 ∧ stalled≥4); DeepSeek 434 → 326 extend/108
abandon. miniF2F is a saturated contrast (tiny reclaim, expected ~0 gain).

**Pilot at E=512k** (jobs 10782471/72, then 10782674/75 after fixing 3 infra bugs — a shared-config
endpoint-file cross-read between concurrent model servers, HF offline-mode network calls, and a
disk-quota crash from torch-inductor cache writes to `$HOME`): both pilots hit their 4:55h walltime
cap (checkpoint-restartable, no work lost). Result on ~10 stratified extend-set cells/model:
- **Goedel: 1/9 solved** (Herstein_3_2_21, seed0, closed at tokens_to_solve=171928 — only ~44k past
  the 128k cap). Per-seed {0:1, 1:0, 2:0}.
- **DeepSeek: 0/8 solved.**
- A scan of the 16 budget-exhausted cells' attempt traces (43-190 attempts each, deepest steps
  5-144) shows genuine churn, not "still climbing" — the F2/F3 execution floor reasserting itself,
  not a budget-starved tail.

**Design correction and clean re-pilot at E=256k** (the lone solve landed at 172k, so a lower cap
catches near-cap solves while funding ~3x more extensions at the same total reclaim: Goedel
22→68 extensions, DeepSeek 28→84): offline re-tally resolved 17/20 cells for free; 3 timeout-cut
cells needed a small GPU resubmit (10784792/93, after a first attempt no-opped on a budget-limit
guard and was fixed by patching 3 checkpoint files' recorded limit). **Final clean tally: Goedel
1/10 (Herstein_3_2_21 seed0, same solve), DeepSeek 0/10.**

**Verdict: weak-dominance confirmed (by construction, Δsolves≥0) but the margin is WEAK and
ONE-MODEL** — projected full-run lift ~+1pp on Goedel (below the pre-registered 2pp positive bar),
~0 on DeepSeek. **Phase 5 closed without a full run** (low EV given the pilot numbers) — the 4th
independent confirmation of the execution floor, after Phase 1's OFAT null, Phase 2/3's mechanism,
and Phase 3's hammer NO-GO.

## 10. Phase 6 — Mechanism-targeted execution fine-tuning

**§0 gate — train/test disjointness (2026-06-21, non-negotiable before any training).** Candidate
corpus: `internlm/Lean-Workbook`, 140,214 autoformalized problems. Three overlap signals checked
against the union of both eval sets: exact normalized-statement match, formal-statement TF-IDF
cosine, informal-statement TF-IDF cosine. **The gate did its job:** found 10 exact miniF2F overlaps
(AoPS-sourced competition problems duplicated verbatim in Workbook — `imo_1983_p6`,
`amc12a_2021_p25`, `amc12a_2021_p8`, `amc12b_2020_p2`, one problem appearing twice), 0 exact
ProofNet# overlaps. Chose an evidence-based drop rule (`exact ∪ formal-cosine≥0.95 ∪ informal-
cosine≥0.85`) after reading the boundary band — the 0.85-0.98 formal-cosine band turned out to be
thematic similarity (shared notation/binders on genuinely distinct problems), not duplication, so
keeping it preserves training utility; the informal-cosine tail is the clean duplicate signal.
**Result: 202/140,214 (0.14%) dropped → 140,012-problem clean corpus**, used for every Phase 6
training run.

**Stage A/B — supervised fine-tuning (2026-06-30, full 3-seed matrix, LoRA r=16).** Two arms vs.
base: A = generic RFT (rejection fine-tuning on the model's own successful self-generated proofs); B
= closing-targeted SFT (loss masked to only the closing tokens after a deep, previously-unclosed
state). Both models, both benchmarks, budgets {8000, 32000}.

| model | benchmark | arm | pass@8000 | pass@32000 | paired vs base @32k |
|---|---|---|---|---|---|
| goedel | miniF2F | base | 61.5±1.6 | 70.4±0.6 | — |
| goedel | miniF2F | A (generic RFT) | 49.2±3.3 | 50.7±3.9 | **−19.7±4.4pp** |
| goedel | miniF2F | B (closing SFT) | 59.2±0.9 | 68.3±1.7 | −2.0±1.1pp |
| goedel | proofnet | base | 12.2±0.8 | 14.2±0.6 | — |
| goedel | proofnet | A | 8.6±0.0 | 9.3±0.6 | −4.8±1.1pp |
| goedel | proofnet | B | 10.2±1.1 | 12.2±0.6 | −2.0±1.2pp |
| deepseek | miniF2F | base | 57.4±0.8 | 65.4±0.5 | — |
| deepseek | miniF2F | A | 49.3±1.3 | 52.9±0.8 | −12.6±1.3pp |
| deepseek | miniF2F | B | 54.2±0.9 | 65.2±1.4 | −0.3±1.3pp |
| deepseek | proofnet | base | 11.5±0.6 | 17.6±1.2 | — |
| deepseek | proofnet | A | 13.4±1.4 | 15.1±1.6 | −2.5±2.0pp |
| deepseek | proofnet | B | 11.8±2.3 | 16.7±1.4 | −0.9±0.3pp |

**Headline: Stage B (closing-targeted SFT) does NOT lift the floor** — flat-to-slightly-negative
everywhere, never within reach of the pre-registered ≥+3pp bar, tight bars across all 3 seeds on
both models. **Crucially this holds despite near-zero closing-token training loss (~0.07 both
models)** — the model assigns high *conditional* probability to the correct closing yet fails to
*generate* it autoregressively. Textbook **exposure bias**, not missing knowledge. **Stage A
(generic RFT) actively hurts** (−12 to −20pp @32k miniF2F) — SFT on self-generated proofs narrows
the search distribution. Two live hypotheses remained afterward: c1 (exposure-bound — RL against
the true generation distribution should fix it) vs c2 (capacity-bound — nothing will).

**Stage C decision (2026-06-29) — a gated RL feasibility probe, not a full sweep.** A full two-model
GRPO sweep was estimated at multi-day, >>50 GPU-h; chose instead a single-model (DeepSeek — stronger
OOD basis), pre-registered, numeric-gated ~40 GPU-h probe. Three gates, ALL required for a pass:
G1 (primary) — held-out solve-rate up ≥5pp AND training reward rose (reward-up-but-held-out-flat =
overfit, not c1); G2 — soundness/loophole rate does not rise >+2pp; G3 — no diversity collapse /
KL blowup. An escape clause: a stall *with* a KL/diversity pathology reads as "retune and re-probe,"
not c2 — capacity-bound is only concluded from a *clean* flat stall.

**Stage C spec and result (2026-07-04/05, job spanning ~15-18 GPU-h of the 35 GPU-h/40 GPU-h hard
stop):** DeepSeek-Prover-V2-7B, LoRA r=16/alpha=32, GRPO (trl 0.17), G=4 rollouts/prompt (reduced
from spec's G=8 for generation memory), B=4-8 prompts/step (reduced mid-run after a CUDA OOM at
step 72/80 as completions lengthened), 80 steps (reduced from up-to-150 after timing estimates),
lr=1e-6, KL β=0.04, max_new_tokens=4096, binary Lean-verified+sound reward +0.05 format bonus.
Training subset: 130 `lean_workbook_clean` problems, base solve-rate in [1/16, 10/16] (the
dense-signal sweet spot). Held-out gate: 70-problem disjoint slice.

| Gate | Requirement | Result | Pass? |
|---|---|---|---|
| G1 (primary) | pass@1 up ≥5pp AND reward rose | base 0.586, RL 0.570, **Δ=−1.6pp**; train solve-rate flat (0.17-0.27 oscillation, no trend) all 80 steps | **NO** |
| G2 (soundness) | unsound rate ≤+2pp | base 9.58%, RL 6.17%, Δ=−3.4pp (RL cleaner) | YES |
| G3 (no collapse) | diversity ≥80% base, KL under ceiling | distinct-3gram ratio 1.015; mean KL=0.0021 (≪0.05 ceiling) | YES |

**Verdict: c2 — capacity ceiling.** Training reward flat for all 80 steps with no pathology (G2/G3
clean) is precisely the pre-registered "clean flat stall" branch, not a mis-tuned run needing
retuning. RL, at LoRA-probe scale, post-hoc on an existing model, does not move the floor. Per the
pre-registered caveat (LoRA r=16, not full-FT), this is read as "capacity ceiling under the probe's
constraints," not an airtight permanent close — full-FT RL remains the reopening lever if revisited.
This is the **third independent confirmation** of the execution-floor thesis (after
scaffolding/search Phases 0-5, and SFT Stage A/B's exposure-bias-but-no-floor-move), via a third
mechanism (RL against the true verifier reward).

## 11. Phase 7 — Verified-state re-grounding: NULL, in its strongest form (single seed, feasibility arc)

Tests the Stage B exposure-bias hypothesis directly and training-independently: force the model to
continue from a *verified* correct intermediate Lean state rather than free-running on its own
(possibly already-drifted) generation. All runs on the 150 ProofNet# problems Goedel-Prover-V2-8B
could not solve at ANY budget up to 128k in the committed 3-seed baseline (trapped by construction).

- **Modes 1/2** (whole-proof, no feedback / error-string refinement): reconstructed for free from
  the baseline's own logged attempts — 0/150 by construction.
- **Mode 3** (verified-state re-grounding, whole-continuation): after fixing a boundary-finder bug
  that discarded real partial credit (a naive single-cut landed mid tactic-combinator 27% of the
  time), the frontier genuinely advances in 19/150 cells (one reaching a 90-tactic-line verified
  prefix). **0/19 of those engaged cells convert to a close.** A matched fresh-resample control
  (same names, fresh session, zero re-grounding) also got 0/150.
- **Mode 4 on Goedel-Prover-V2-8B** (true step-by-step, one tactic per call): Goedel is a whole-proof
  reasoning model that doesn't reliably decompose into atomic tactic turns (its "next tactic" answer
  is unpredictably a one-liner, a multi-`have` compound, or unconverged prose). After a time-boxed,
  oracle-validated multi-candidate extraction fix, 6/19 cells reached genuine accepted steps (one 10
  deep) — a fair, if partial, test. **0/19 closed.**
- **Mode 4 on BFS-Prover-V1-7B** (a genuinely tactic-native disambiguator model, pulled forward from
  Track 2, run on the full 150-cell trapped set). First attempt found three confounds — a real
  Lean-accepted but non-progressing tactic could be re-accepted every step (one cell: the same
  tactic accepted 64/64 times, looking like depth but being a stall); a single irreversible path
  under-tests a model designed for best-first search with backtracking; and a script bug hardcoded
  the wrong prompt template. All three fixed in one pass (stagnation rejection +
  `BeamTacticStepwiseAgent`, a real DFS-with-backtracking over a small beam, plus correct template
  wiring), then re-run once, final. **Engagement: 77/150 cells (51%) reach real oracle-validated
  progress**, several with genuinely varied multi-tactic exploration (up to 18 distinct tactics on
  one problem). A residual short-cycle artifact affects 4/150 cells (quantified, not eliminated, per
  a pre-registered one-more-run stopping rule). **0/150 closed.**

**Reading:** every weaker/confounded version of this experiment was upgraded before being trusted,
and at every step the fix *increased* engagement (Mode 3: 1→19 cells; Goedel Mode 4: 0→6; BFS-Prover
Mode 4: 0→33→77) — confirming each earlier "null" had been partly an artifact of an under-tested
mechanism. The final, fully-corrected numbers on both models still converge to **zero closes**, even
giving the model its own true verified state at every step with real search and backtracking. This
closes the "did you test it properly?" objection on both axes available (single-shot re-grounding
and step-by-step search; a whole-proof model and a tactic-native one). **Secondary finding:**
Goedel-Prover-V2-8B does not cleanly decompose into single-tactic turns even when explicitly asked —
a real architecture-level property, not a prompting failure. **Scope caveats, stated honestly:**
only ProofNet# tested (not miniF2F or DeepSeek's own trapped set); single seed throughout (a
feasibility arc, not the 3-seed headline protocol — should get seeds before anchoring a paper claim);
the 4/150 short-cycle artifact is quantified but not eliminated.

## 12. Phase 8 — Model zoo: does full-pipeline, lab-scale RL move the floor?

Extends Phase 2's cross-model replication to a stronger question: not "do two labs' released models
differ" but "does a lab's own full Base→SFT→RL training pipeline (not a lightweight post-hoc LoRA
probe) move the floor?" Tested via two independent matched lineages: DeepSeek-Prover-V1.5
(Base→SFT→RL) and Leanabell-Prover (GD-SFT→GD-RL, continual-trained from a Goedel-Prover-SFT base,
per its own paper, arXiv:2504.06122).

**This phase's numbers were wrong THREE times before they were trusted — each catch is its own
finding about how easy it is to fool yourself with a near-zero or too-clean result:**

1. **First check-in #2 table (looked like a clean, exciting result: Base<SFT<RL at every budget/
   seed, delta-floor Base→SFT +5.2pp, SFT→RL +3.7pp on ProofNet#).** Root cause found 2026-07-06:
   `WholeProofAgent.from_config` hardcoded `WholeProofTemplate` regardless of
   `config.model.prompt_template` — dead code (`template_from_config`) had existed since the
   project's first commit but was never called. Every model in this battery whose config asked for
   a prompt_template other than `whole_proof` was silently served the wrong prompt. Confirmed
   directly (not inferred) by pulling the actual "Received request" text vLLM logged for the
   original V1.5 battery job (11117638) — it was unambiguously `WholeProofTemplate`'s chat/
   proof-plan prompt, not `DeepSeekV15Template`'s intended raw-continuation format. **Confirmed to
   have zero effect on Goedel-V2/DeepSeek-V2 (Phases 0-7)** — their own official format IS textually
   `WholeProofTemplate`'s, so the bug was a no-op for them.
2. **Second attempt, after fixing the wiring bug, still invalid.** A second, independent bug:
   `PantographBackend._build_source`/`ReplBackend._build_repl_source` never reconstructed the
   `theorem ... := by` declaration for continuation-style completions (these templates ask the
   model to continue directly after `:= by`, never restating the theorem) — bare tactics landed as
   top-level commands, a guaranteed Lean parse error dressed up as "the model's proof was wrong."
   Found by hand-tracing individual completions byte-for-byte. **A third bug found the same day:**
   both templates were also missing `import Aesop` + `set_option maxHeartbeats 0` (the latter
   disables Lean's elaboration heartbeat limit; without it, otherwise-valid nlinarith/field_simp/
   simp-heavy proofs can spuriously time out) — verified byte-for-byte against each model's own
   official inference script. **A fourth candidate bug was investigated but not adopted at scale:**
   a missing `informal_statement` doc-comment; fixed in code and smoke-tested to 160 cells (modest
   qualitative improvement, still 0/160 solved) but not pursued further per a pre-committed decision
   rule.
3. **Corrected battery (`p8battery2_verified2_*`, 2026-07-07), all three real bugs fixed, 5,586
   re-verified cells, seed-balance-checked on all 10 configs:**

| | ProofNet# floor (pass@32000) | miniF2F floor (pass@32000) |
|---|---|---|
| V1.5 Base | 0.0 ± 0.0 | 0.0 ± 0.0 |
| V1.5 SFT | 0.0 ± 0.0 | 0.0 ± 0.0 |
| V1.5 RL | 0.0 ± 0.0 | 0.0 ± 0.0 |
| Leanabell GD-SFT | 0.0 ± 0.0 | 0.0 ± 0.0 |
| Leanabell GD-RL | 0.0 ± 0.0 | 0.0 ± 0.0 |

**Every cell, both lineages, both benchmarks, every budget: exactly zero solves.** The original
"clean Base<SFT<RL" pattern had completely evaporated — it was entirely a wiring-bug artifact.

**A perfect 0.0%-everywhere is itself a suspicious pattern** (real capability floors are usually
noisy-near-zero, not exactly zero — that's the classic signature of a scoring pipeline that isn't
scoring anything). Four blocking checks were required before accepting it (2026-07-09/10):
1. **Harness-sanity control — PASSED.** Re-verified Goedel-V2/DeepSeek-V2's historically-solved
   proofs (confirmed unaffected by all 3 bugs) against the current, fully-patched backend:
   **DeepSeek-Prover-V2-7B 40/40 still verify; Goedel-Prover-V2 37/37 still verify.** The exact code
   that produced the 0.0% floor correctly recognizes real, known-good proofs — the pipeline is
   sound, the 0.0% is not an artifact.
2. **Taint audit — zero Phase 0-7 headline results affected.** Every committed result (Phases 1-4,
   6, 7) used only Goedel-V2/DeepSeek-V2, both natively `whole_proof`, both unaffected regardless of
   any of the three bugs existing.
3. **`client.py` stop-sequence gap — real, investigated concretely, does not explain the 0.0%.** No
   template ever sets a Lean `stop` sequence. Scanned for genuine trailing content after a real
   closing fence (the one way this could mask a hidden correct solve) — found none in the most
   carefully-traced configs; a real but separate efficiency/quality debt, not a scoring bug.
4. **Cluster B breadth formally dropped** — the RL question is already closed via two clean,
   mutually-agreeing matched lineages; more models would add breadth to an established negative, not
   new information.

**Result stands, harness-validated: 0.0% pass rate at every training stage, every budget, both
benchmarks, both matched lineages.** Clean replication of a null (both lineages agree exactly, so
there is no RL-vs-SFT delta to compare in either — nothing solves anything, so there's nothing for
RL to differentially improve). **No headline verdict (discovery vs. definitive-negative paper
framing) was made in this doc — explicitly reserved as the coordinator's/user's call.**

**GPU-h:** ~150.7 GPU-h summed across the whole Phase 8 battery (including early failed/transient
shards from a node-contention episode) — over the 50 GPU-h soft line, logged per the project's
GPU-hour rule since the spend bought a real, harness-validated finding.

## 13. The independent post-Phase-8 audit (2026-07-10/16) and its two real findings

Before any further experiments were queued, a full independent audit re-verified this project's own
pipeline end-to-end (`AUDIT_PLAN.md`, ledger in `results/audit/AUDIT_FINDINGS.md`, ~30 checks, most
CLEAN). Two were real bugs with consequences worth detailing:

**Check A1 — a P0 verifier bug, found via the same continuation-style code path as the Phase 8
bugs above.** The `no_goal` soundness gate (added 2026-06-14) checked `not _DECL_RE.search(proof)`
on the *raw extracted completion* — but the 2026-07-06 header-reconstruction fix (§12 above) meant
the backend now assembles a full `theorem ... := by` wrapper around any proof lacking one. For
continuation-style templates (`DeepSeekV15Template`/`GoedelSFTTemplate`/`BFSProverTemplate` — the
model never restates the theorem by design), `_DECL_RE.search(proof)` was **structurally always
None**, so `no_goal` fired on *every* attempt regardless of correctness — an emergent interaction
between two independently-correct fixes. Reproduced directly against the real, patched Lean REPL: a
genuinely correct continuation-style proof compiled successfully (`backend.verify()` returned
`success=True`) yet `Verifier.verify()` still returned `ok=False, reason="no_goal"`. **Fixed**:
`RawVerification` gained a `declares_goal: bool` field computed from the *assembled* source, and the
verifier checks that instead of re-deriving it from the raw proof. Test-first, plus a dedicated
permanent real-Lean regression test (not just a mock).

**This directly implicates Phase 8's "0.0%-everywhere corrected floor"** for both matched lineages
(both continuation-style) — the harness-sanity control did NOT catch it, because that control only
covered `whole_proof`-format models, for which the gate was always a no-op. **Magnitude on the actual
reported headline is not directly measurable** — the exact completions behind the committed 0.0%
table were not retained (only summary JSONs). An indirect check on older, already-known-invalid,
pre-fix completions was inconclusive by design (small sample, checked against a pre-registered rule
that a zero/low-flip result there would NOT clear the headline anyway) and was intentionally aborted
partway to prioritize a higher-priority permanent regression test. **Recommendation, explicitly not
actioned by this session: Phase 8's continuation-style battery needs a GPU regeneration + reverify
under the now-fully-fixed harness before its 0.0%-everywhere headline can be fully trusted** — a
user decision (new GPU spend), still open as of this writing.

**Check B — does a Lean setting (`maxHeartbeats`) added partway through the project retroactively
change any Phase 0-7 `whole_proof` (Goedel-V2/DeepSeek-V2) result?** `set_option maxHeartbeats 0`
was added 2026-07-06 and had never been applied to Phase 0-7's original sweeps. A full offline CPU
re-verify (no GPU, no new generation) of every historically-failed attempt on the trapped core across
all 4 model×benchmark combinations:

| core | cells checked | problems | flipped |
|---|---|---|---|
| Goedel×miniF2F | 159 | 55 | **3** (2 distinct problems) |
| Goedel×ProofNet# | 450 | 150 | **3** (3 distinct problems) |
| DeepSeek×ProofNet# | 420 | 140 | **0** |
| DeepSeek×miniF2F | 183 | 61 | **7** (3 distinct problems) |

**Total: 13/1212 cells (1.1%), 8 distinct (problem, model) pairs recovered out of 406 trapped-
problem instances (2.0%).** Per the pre-registered decision rule ("material iff ≥1 trapped problem
flips per seed on ≥1 model"), this is unambiguously **material, not a no-op**. It is a scoring
correction, not a new capability finding — every flipped cell's correct proof was already present in
the *original* Phase 0-7 generation; nothing new was generated, only re-verified under the fixed
Lean setting. Because the fix can only ever widen (never narrow) what counts as solved, no reported
number was an over-count — if anything the old floor was a slight under-count. **The corrected
numbers have not yet been folded back into the summary tables** — an arithmetic-only follow-up, not
a new experiment, not expected to change the thesis at this magnitude. Step 4 (broadening the
reverify to a sample of all near-frontier failures, not just the trapped core, to check for a
similar mid-curve effect) was not performed — a flagged, non-blocking residual item.

*(Infra footnote for anyone re-running this: the reverify job needed 3 attempts on DeepSeek×miniF2F —
two crashes from a script with zero checkpointing, losing up to 24h and 175/183 cells of real Lean
work each time — fixed by adding append-only JSONL checkpointing and bumping the time limit from
24h to 72h; the resubmitted job's partial flip set exactly reproduced the earlier crashed run's
partial result, a strong determinism sanity check on the reverify logic itself.)*

Every other independent re-derivation the audit performed matched the committed numbers **exactly**:
the Goedel×ProofNet# pass@B curve (4.8/9.3/12.0/14.3%), the oracle ceiling (98.1% compute saved,
1,349,747 vs 71,424,000 tokens), and the Phase 1 ProofNet# flip table (all six components' exact
gain/loss counts) were all re-derived from raw cells by a fresh script that imports none of the
project's own analysis code — strong independent confirmation the numbers in §4-7 above are real.

## 14. Where the earlier verifier audit fit in (2026-06-14, before Phase 8 existed)

Found the verifier could score a truncated/malformed proof as "solved" under two conditions: a
truncated generation emitting a bare `def` preamble with no goal (compiles with nothing to check),
or a wedged/cross-talked REPL returning an empty no-error response. Fixed (commit `aa659f5`): a
solve now requires a declared theorem/lemma/example **and** a REPL response carrying an `env`. Blast
radius checked directly: miniF2F Phase 0 had **0** false positives (those headline numbers stand
as-reported); miniF2F Phase 1 had 6/3124 (0.2%); **only ProofNet# was materially corrupted**
(constant full-budget truncation was hitting the bug systematically) — the ProofNet# baseline and
every ablation were fully re-run on the fixed verifier before being reported anywhere in this
project.

## 15. What's NOT being built, and why

- **BFS / explicit proof-state search** — deferred early: prior work already showed search loses to
  plain best-of-N sampling, and F2/F3 (§5) say the bottleneck is execution depth, not approach
  finding, so search wouldn't address it.
- **Neural premise retrieval (ReProver-style)** — killed outright, not deferred: F2 shows ~0% of
  failures are from a missing lemma, so there's nothing to retrieve; the cheap version (BM25) was
  tried anyway (§4) and actively hurt on the hard benchmark.
- **A real hammer/SMT port (`duper`/Lean-SMT)** — NO-GO on current evidence (§6), though honestly
  not a decisive test (only a same-pin tactic portfolio was tried, not a true superposition prover).
- **Diversity-injection as a shippable feature** — served its purpose as the decisive causal test
  (§5, F6/Step C); it raises diversity but not solves and mildly degrades quality, so it is not
  something to build into a product.
- **A duper/SMT port, full Cluster B breadth in Phase 8, WS3 (standalone allocation-policy paper)**
  — each explicitly closed as low-EV given the converging evidence at the time (§6, §12, §8).

## 16. Methodology lessons worth carrying forward

1. Paired flips (which specific problems changed) are far more informative than mean deltas at only
   3 seeds — caught retrieval as noise-like churn (§4) rather than a real gain.
2. A second, harder, OOD benchmark earned its cost — corroborated the easy benchmark's null and
   surfaced two components (§4) the easy benchmark alone would have missed as harmful.
3. A second, independent model earned its cost — turned "a Goedel result" into a mechanism that
   generalizes (§3, §5) and surfaced the in-distribution/OOD dichotomy as a real training-recipe
   difference.
4. A null is only interpretable once you've shown the intervention actually fired — the
   budget-matched manipulation check (§5, F6/Step C) is what made that null meaningful rather than
   just another inconclusive negative.
5. Audit the verifier before trusting suspiciously good numbers — the impossible-looking early
   ProofNet# rates were the tell that caught the first verifier bug (§14).
6. A near-zero result deserves exactly the same base-rate skepticism as a too-good-to-be-true
   result. Phase 8's "training doesn't help at all" pattern (§12) looked like a real, if
   disappointing, finding right up until it was checked against the models' own published numbers
   and a byte-level prompt diff.
7. A newly-introduced model configuration exercises code paths existing tests never covered — all
   three structural Phase 8 bugs (§12) had sat in code that had been "passing" for weeks; they only
   surfaced the first time a genuinely different prompt template ran at real scale.
8. Infra: sharded jobs co-located on packed GPU nodes need per-shard isolation (node-local Lean
   staging, per-shard vLLM ports, staggered starts to avoid GPU-init contention/NVML herd) and
   known-bad nodes need excluding; always resume the full array range so shard striding stays
   consistent (§8's WS1.1 power-up hit this pattern directly); any job that can run >20 minutes
   needs disk checkpointing from the start, not added after a crash costs real compute (§13's
   heartbeat-reverify infra footnote).

## 17. Where things stand right now, and what's left

- **All planned experiments are complete.** WS1 (the DeepSeek seed power-up and Gate G1) closed out
  2026-07-21.
- **What's left is writing it up.** A first-pass paper skeleton exists (`paper/floor/main.tex`,
  compiles cleanly) with real numbers pulled in, but paper work is paused per an earlier explicit
  instruction until the user chooses to resume it — this document does not change that.
- **One small, non-blocking loose end:** the 13-cell heartbeat scoring correction (§13) needs
  arithmetic-only folding back into the summary tables.
- **One optional, not-yet-decided item:** whether to spend GPU time re-generating and re-verifying
  Phase 8's model-zoo results under the fully-fixed harness (§13, Check A1) to fully clear its
  headline number, vs. leaving it as a flagged, well-understood caveat.

**Overall assessment:** a systematic, heavily-audited elimination of a wide space of plausible
interventions — scaffolding (Phase 1), search-time diversity forcing (Phase 2), hammer/SMT tactics
(Phase 3), more of the same compute (Phase 5), likelihood-based fine-tuning (Phase 6 Stage A/B),
lightweight post-hoc RL (Phase 6 Stage C), verified-state re-grounding (Phase 7), and full-pipeline
lab-scale RL across two more model lineages (Phase 8) — all converging on one finding: there is a
hard execution floor that only a model's own from-scratch training seems to move, and nothing tried
here moves it after the fact. Alongside that, one smaller constructive result survives: compute
allocation policy helps, confirmed robustly on one model (Goedel, +26%±7%), genuinely inconclusive
on a second even at 8 seeds (DeepSeek, +10%±24%). That combination is a normal, publishable shape for
a paper — a well-supported negative result plus an honestly-scoped positive one — just not a flashy
one.
