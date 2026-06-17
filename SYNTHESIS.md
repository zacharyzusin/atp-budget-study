# Synthesis — Budget-Bounded Agentic Theorem Proving

*Consolidated findings as of 2026-06-17. Source of truth for the numbers: `PROGRESS.md` (dated lab
notebook), `DECISIONS.md`, `results/*/metrics.json`, and `results/phase1/FINDINGS.md`. This file is the
one-page story; those are the receipts.*

## The question

For a fixed theorem prover, how does solve rate scale with the per-problem **token budget** B, and do
**agentic scaffolding** components (premise retrieval, failure memory, an LLM reviewer, tactic-skeleton
hints, budget allocation between fresh samples and refinement) buy anything on top of plain
whole-proof sampling at a given budget?

- **Model:** Goedel-Prover-V2-8B (`Goedel-LM/Goedel-Prover-V2-8B` @ `dfd02e6`) on the Goedel Lean pin
  (Lean v4.9.0-rc1, mathlib4 `2f65ba7`). Lean is the authoritative verifier (REPL backend).
- **Benchmarks:** miniF2F-test (244 audited problems; competition-style) and ProofNet# (186 test;
  undergrad-level, out-of-distribution for this model).
- **Deliverable:** the pass@B curve, with paired-flip ablation of each scaffolding component.
- **Variance:** 3 seeds for every headline number; mean ± seed-std. Per-seed std runs ~1.5–3pp, so a
  single OFAT mean-delta under ~1 baseline-σ is treated as noise (the "noise bar," DECISIONS 2026-06-11).

## pass@B — the headline curves

| budget | miniF2F | ProofNet# |
|--------|---------|-----------|
| 2k   | 29.6% ± 3.3% | 4.8% ± 1.4% |
| 8k   | 60.1% ± 1.9% | 9.3% ± 1.1% |
| 32k  | 69.5% ± 0.6% | 12.0% ± 0.6% |
| 128k | 74.9% ± 0.9% | 14.3% ± 0.8% |

- **miniF2F:** steep early (29.6→60.1% over 2k→8k, +30pp), then saturating; ceiling ~75% at 128k.
  Most budget value is captured by 8k; beyond 32k is nearly flat.
- **ProofNet#:** ~5× harder at *every* budget and the curve is far flatter (4.8→14.3% over a 64× budget
  range). More budget keeps buying proofs but the absolute ceiling is low — consistent with
  undergrad-level / OOD problems for this prover. `tokens_to_first_proof`: miniF2F median 2534, mean
  8266; ProofNet# median 3855, mean 16872 (the harder benchmark burns far more of the ceiling per solve).

Both baselines are the **no-frills config**: whole_proof + refinement (max_iters 4, alloc_split 0.5),
all Phase 1 components OFF.

## Does agentic scaffolding help? No — and on hard problems some of it hurts.

Phase 1 was a one-factor-at-a-time ablation of each component against the no-frills baseline, judged by
**paired flips** (per (problem, seed), how many problems the variant solves that the baseline missed vs
vice-versa). A real lever makes *gains dominate losses*; symmetric flips are generation churn.

**miniF2F (B=8000, then re-checked across budgets):** No component cleared the noise bar.
Retrieval (BM25, k=8) *looked* like the one mover at +3.4pp@8k in the first OFAT pass — but it **did not
replicate**: an independent cross-budget campaign gave +2.2 / +0.7 / −0.8 pp at 2k/8k/32k, and the
paired-flip table showed gains ≈ losses at every budget (the BM25 context perturbs sampling rather than
injecting usable premises). Memory, reviewer, tactic_skeletons, and budget_alloc were all within seed
noise; none helped, none hurt. (Full detail: `results/phase1/FINDINGS.md`.)

**ProofNet# (B=128000, paired flips vs the ablation baseline):**

| component            | gains | losses | net | verdict             |
|----------------------|-------|--------|-----|---------------------|
| reviewer             |  13   |  10    |  +3 | noise-like          |
| budget_alloc__2      |   9   |  11    |  −2 | noise-like          |
| memory               |   8   |  10    |  −2 | noise-like          |
| tactic_skeletons     |   9   |  12    |  −3 | noise-like          |
| budget_alloc__0      |   6   |  25    | −19 | **directional (hurts)** |
| retrieval            |   6   |  42    | −36 | **directional (hurts)** |

On the harder OOD benchmark the "all noise" picture sharpens: 4/6 are still noise-like, but **two are
clearly directional and both *harmful*** — front-loaded allocation (`budget_alloc__0`, no escalation)
and BM25 retrieval (42 baseline solves lost for 6 gained). Retrieval actively poisons the prompt when
the model is out of its depth.

**Bottom line across both benchmarks:** *no Phase 1 scaffolding component is a net-positive lever.* The
result is consistent on the easy benchmark (everything is noise) and stronger on the hard one (the same
null, plus two components that measurably hurt). The harder, OOD benchmark is *more* sensitive to bad
context, not less.

## Verifier soundness — why these numbers are trustworthy

A 2026-06-14 audit found two verifier holes that produced false-positive solves on hard problems:
(1) a generation truncated at the token cap could emit a bare `def` preamble that Lean compiles with no
goal → scored as solved; (2) a wedged/cross-talked REPL could return an empty no-error response →
scored as success. Both are fixed (commit `aa659f5`): a solve now requires the proof to declare a
theorem/lemma/example **and** the REPL response to carry an `env`. Blast radius audited: miniF2F Phase 0
had **0** false positives (headline miniF2F numbers stand); miniF2F Phase 1 had 6/3124 (0.2%,
negligible); **only ProofNet# was materially corrupted** (constant full-budget truncation), which is why
the ProofNet# baseline and ablation were fully re-run with the fixed verifier — those are the numbers
reported above.

## What we are NOT building, and why

- **BFS / proof-state search (Task 1.2):** deferred and de-prioritized. The validate-premise evidence is
  against it — the prior was search < Pass@1, and the flat ProofNet# curve shows that even more budget
  *inside* whole-proof sampling yields sharply diminishing returns, so a more expensive search procedure
  is a poor bet on current evidence.
- **ReProver neural retrieval backend:** retrieval as a mechanism failed (churn, not premise injection);
  a fancier retriever is speculative and unmotivated by the data.

## Methodology lessons worth carrying forward

1. **Paired flips beat mean-deltas.** With n=3 seeds and ~1.5–3pp per-seed std, a single ~3pp OFAT delta
   is indistinguishable from noise; the flip table (gains vs losses) is far more informative and is what
   exposed retrieval as churn.
2. **A second, harder, OOD benchmark earns its cost.** It both corroborated the miniF2F null and
   surfaced harmful components that the easy benchmark masked.
3. **Audit the verifier before trusting "good" results.** The impossible-looking Phase 1 pass rates on
   ProofNet# were the tell that caught the soundness bug.
4. **Infra:** sharded co-located sweeps on packed A6000 nodes need per-shard isolation — node-local Lean
   env staging to `/dev/shm` (the Slurm epilog wipes `/local`/`/tmp` on every job end), per-shard vLLM
   port, and per-shard endpoint file. See `slurm/sweep_array.sh` and PROGRESS.md 2026-06-16/17.
