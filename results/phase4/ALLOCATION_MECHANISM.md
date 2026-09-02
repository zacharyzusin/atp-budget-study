# WS1.2 — Allocation mechanism analysis: why Goedel×ProofNet# STRONG, DeepSeek×ProofNet# WEAK

**Date:** 2026-07-16 · **Status:** exploratory CPU-only mechanism mining (PLAN_NEXT.md WS1.2), no new
GPU data. Reuses the four committed budget-independent baseline runs and the `solved(cell,b) ==
tokens_to_solve(cell) <= b` identity (ALLOCATION.md §0) — same cells, a different cut. Code:
`scripts/analyze_allocation.py` → `ALLOCATION_MECHANISM.json`. This is post-hoc mechanism mining, not
a pre-registered experiment with a decision rule — findings below are reported as directional evidence,
not a confirmed/falsified hypothesis.

**Question:** ALLOCATION.md found the realizable single-checkpoint policy is **STRONG and per-seed
robust on Goedel×ProofNet#** (+26% ± 7%) but **WEAK and fragile on DeepSeek×ProofNet#** (−13% ± 28%,
driven by a seed-2 collapse to −51%). PLAN_NEXT.md's hypothesis: the gain comes from harvesting "cheap
marginal" cells, i.e. pass@B slope heterogeneity across (problem, seed) cells — test whether Goedel has
more of it than DeepSeek.

## M1 — problem-level mixed-outcome heterogeneity

For each problem (pooled over its 3 seeds), classify as **trapped** (0/3 seeds solve),
**partial** (1–2/3, i.e. the SAME problem solves on some seeds and not others — pure search-path luck),
or **robust** (3/3 solve).

| model × benchmark | trapped% | **partial%** | robust% | n problems |
|---|---|---|---|---|
| goedel × ProofNet# | 80.6% | **9.7%** | 9.7% | 186 |
| deepseek × ProofNet# | 75.3% | **4.8%** | 19.9% | 186 |
| goedel × miniF2F | 22.5% | 4.5% | 73.0% | 244 |
| deepseek × miniF2F | 25.0% | 5.7% | 69.3% | 244 |

**Goedel×ProofNet# has ~2x the "partial" rate of DeepSeek×ProofNet#** (9.7% vs 4.8%) — real evidence
Goedel has more per-problem seed-luck heterogeneity to exploit. But DeepSeek×ProofNet# has **twice the
robust rate** (19.9% vs 9.7%): when DeepSeek solves a ProofNet# problem, it tends to solve it on every
seed, not just one. Both benchmarks' miniF2F rows look similar to each other and low-partial (~5%) —
consistent with ALLOCATION.md's own finding that miniF2F is saturated and has little wasted compute to
reclaim, i.e. little heterogeneity to exploit there regardless of model.

## M2 — post-c* population: what's left to harvest, and how spread out is it

Using each run's own already-fit c* (peak-logistic-AUC checkpoint from `predictor.json`, not refit
here), split cells still running at c* into **late bloomers** (eventually solve, cost in `(c*, Bmax]`)
vs **correctly-abandonable** (never solve — pure waste for uniform).

| model × benchmark | c* | n post-c* | late bloomers | late-bloomer % | cost CV | cost IQR/median |
|---|---|---|---|---|---|---|
| goedel × ProofNet# | 8k | 506 | **28** | 5.5% | **0.83** | 2.18 |
| deepseek × ProofNet# | 16k | 470 | **36** | 7.7% | **0.61** | 1.12 |

This is the surprising part: **DeepSeek×ProofNet# does not have a smaller harvestable population** —
it has *more* late bloomers in absolute terms (36 vs 28) and a *higher* late-bloomer rate (7.7% vs
5.5%). "Less to harvest" is not the explanation for DeepSeek's fragility. What differs is **dispersion**:
Goedel's late-bloomer costs are much more spread out (CV 0.83, IQR/median 2.18) than DeepSeek's (CV
0.61, IQR/median 1.12) — i.e. Goedel's late bloomers solve across a wide range of the 8k–128k budget
band, DeepSeek's cluster more tightly.

## Reading: a thin-population account, not a pure heterogeneity account

The clean "more heterogeneity → more robust" story is only half-supported: M1 (problem-level partial
rate) points the right way, M2 (post-c* population size/rate) points the *wrong* way. Combined with
ALLOCATION.md's own numbers — predictor AUC is close between models (goedel 8k=0.75 vs deepseek
16k=0.72) — the better-supported account is a **small-sample fragility** one: DeepSeek's 36 late
bloomers split roughly 12/seed. A single seed's predictor misranking (already diagnosed in ALLOCATION.md
§5 as "the pooled predictor misranks on seed 2") can swing that seed's realized saving by tens of points
when the harvestable population per seed is this thin — exactly the seed-2 collapse to −51% observed.
Goedel's higher partial-rate (9.7% vs 4.8%) gives it a **more diffuse, higher-count margin** (M1) that
is more robust to any single seed's misranking, even though its raw post-c* late-bloomer count (28) is
smaller than DeepSeek's (36) — the exploitable margin is distributed differently across seeds, not just
differently sized in total.

**Net:** the allocation gain is real and mechanistically tied to slope heterogeneity (M1), but
DeepSeek's fragility looks like a **per-seed small-N sampling problem layered on top of comparable
raw heterogeneity**, not "DeepSeek simply has less to exploit." This matters for WS1.1: power-up
(3→8 seeds) is the right lever precisely because it directly attacks a small-N fragility, not because
it's fishing for a different regime — if the account above is right, DeepSeek's realized saving should
stabilize (tighter seed-to-seed spread) as N grows, even if its point estimate doesn't move much.

## Caveats
- Exploratory / not pre-registered — no decision rule was committed before running this analysis;
  treat the "thin-population" reading as a hypothesis for WS1.1's 8-seed run to test, not a settled
  finding.
- M1/M2 are simple binning/dispersion statistics, not a fitted structural model — they describe the
  cell population, not a causal claim about *why* Goedel's search process produces more seed-luck
  variance than DeepSeek's.
- Late-bloomer/correctly-abandonable labels use the FINAL realized outcome at Bmax=128k (oracle
  hindsight), not the predictor's actual OOF score — this is a population-shape analysis, not a
  restatement of the realizable policy's own accuracy.
