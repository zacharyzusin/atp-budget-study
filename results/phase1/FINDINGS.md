# Phase 1 — Fixed-Budget OFAT Ablation (Task 1.6)

**Run:** Slurm array job `10436909` (`slurm/ablation.sh configs/phase1_ablation.yaml`), 7 cells,
all COMPLETED 2026-06-10, ~3.8h each (two waves on the `%4` throttle). No timeouts, no requeues.

**Setup:** Goedel-Prover-V2-8B, miniF2F-test (244 audited problems), **3 seeds**, budget **B=8000
tokens**, whole-proof mode, n_workers=8. Every cell reached **n_cells = 732/732** (244×3, zero failed).
Each axis varied one-factor-at-a-time against the minimal baseline (all components off, refinement
alloc_split=0.5).

## Results — pass@8000

| cell | component / setting | pass@8000 | Δ vs baseline | median tokens-to-proof |
|---|---|---|---|---|
| **baseline** | all off, alloc_split 0.5 | **60.1 ± 3.3%** | (ref) | 1953 |
| budget_alloc__0 | alloc_split 0.0 (all fresh samples) | 60.7 ± 1.8% | +0.5 pp | 1968 |
| budget_alloc__2 | alloc_split 1.0 (all refinement) | 60.5 ± 0.9% | +0.4 pp | 1965 |
| memory__1 | within-problem failure memory | 60.5 ± 3.1% | +0.4 pp | 1916 |
| reviewer__1 | LLM critic (non-authoritative) | 60.4 ± 2.3% | +0.3 pp | 1922 |
| **retrieval__1** | **BM25 premise selection (k=8)** | **63.5 ± 1.9%** | **+3.4 pp** | 1935 |
| tactic_skeletons__1 | strategy-hint schedule | 61.1 ± 2.3% | +1.0 pp | 1990 |

±values are across-seed std. Baseline seed std is **3.3pp**, so any |Δ| under ~3pp is within noise.

## Main effects

1. **Retrieval (BM25 premise selection) is the only component that moves the needle: +3.4pp
   (60.1→63.5%), and it also tightens variance (3.3→1.9pp).** It clears the baseline seed-noise band.
   This is the clear Phase 1 signal and the first candidate for the best-combo cell / a budget sweep.
2. **Everything else is within seed noise** at B=8000: tactic_skeletons +1.0, budget_alloc ±0.5,
   memory +0.4, reviewer +0.3 — all under the 3.3pp baseline std. No component *hurts*.
3. **budget_alloc is flat across the full 0.0↔0.5↔1.0 range.** At this budget, how we split tokens
   between fresh samples and refinement doesn't matter — neither all-fresh nor all-refine beats the
   even split. (Worth rechecking at smaller budgets where the trade-off should bite harder.)

## Reviewer safety check (the point of the non-authoritative design)

The critic is consulted **only on Lean-rejected candidates**, so by construction *every* ACCEPT it
emits is a false-accept. It accepted **17 of 249** reviewed (already-failed) candidates → **6.8%
false-accept rate**. Confirms an LLM critic is **not** a trustworthy verifier; Lean must stay
authoritative (which it does — the reviewer never blocks a solve, it only adds critique to refinement).
This is a validation of the design choice, not a usable accept gate.

## Takeaways / next

- **Promote retrieval.** Run it across budgets (2k/32k) to see whether the +3.4pp holds, grows, or
  shrinks with B; build the best-combo cell around it.
- **Deprioritize** memory / reviewer / budget_alloc as standalone levers at this budget — none beat noise.
- Tactic_skeletons (+1.0) is borderline; revisit only inside a combo or at other budgets.
- **Caveats:** single budget (8000) and a single model; miniF2F-test only (no novel held-out split yet
  — `use_novel_split=false`, novel_names not plumbed). Deltas are OFAT, no interaction terms measured.
- **Deferred:** BFS generation_mode (needs REPL proof-state stepping, Task 1.2); ReProver neural
  retrieval backend.

---

# Cross-budget retrieval rerun (2026-06-11, job 10461442 + resume 10481853)

Promoted retrieval per the §Takeaways: reran **baseline vs retrieval (BM25, k=8)** with the budget
metered to **32k** so a single run reports the whole [2k, 8k, 32k] curve (`configs/phase1_retrieval_budget.yaml`),
3 seeds, full 244-test. Both cells reached **732/732, n_failed=0**. (Retrieval cell hit the 12h wall
10 seed2-tail problems short; resume job 10481853 finished them — resume-safe, skips completed cells.)

## Contemporaneous within-campaign Δ (baseline vs retrieval, same job)

| B    | baseline        | retrieval       | Δ (pp) |
|------|-----------------|-----------------|--------|
| 2000 | 0.3033 ± 0.0309 | 0.3251 ± 0.0237 | **+2.2** |
| 8000 | 0.5943 ± 0.0148 | 0.6011 ± 0.0144 | **+0.7** |
| 32000| 0.7008 ± 0.0071 | 0.6926 ± 0.0082 | **−0.8** |

**Retrieval's lift shrinks with budget and goes negative by 32k.** At 8k it is **+0.7pp — not the
+3.4pp Phase 1 reported.** Both Phase 1 (60.1→63.5) and this run (59.4→60.1) are legitimate
within-campaign baseline-vs-retrieval comparisons; the +3.4 vs +0.7 gap between them is **run-to-run
variance** (separate vLLM processes are not bitwise-reproducible — batch-nondeterministic sampling +
n=3 seeds; per-seed std ~1.5–3pp). i.e. the Phase 1 +3.4pp **did not replicate**. NB: the meter only
limits to `max(values)` and the agent loop ignores the ceiling (`alloc_split` is not even read by
WholeProofAgent), so an 8k point is a valid 8k measurement *within* its run — it just isn't bitwise
equal to a different run's 8k point.

## Paired flip analysis — the effect is prompt-perturbation churn, not premise signal

Per seed, problems solved-within-B by each cell (paired by problem name), counting flips both ways:

| B    | gained (retr solves, base didn't) | lost (base solved, retr didn't) | net | per-seed net |
|------|-----------------------------------|----------------------------------|-----|--------------|
| 2000 | +47 | −31 | **+16** | +5 / +1 / +10 |
| 8000 | +46 | −41 | **+5**  | −6 / +5 / +6 |
| 32000| +20 | −26 | **−6**  | −1 / +1 / −6 |

Gains ≈ losses at every budget. A genuinely helpful premise block would make gains **dominate**
losses (asymmetric); instead the BM25 context flips problems roughly **symmetrically** — it perturbs
the stochastic generation more than it injects usable premises. As B grows the baseline already
solves the easy problems, so the extra context mostly *distracts* → losses overtake gains (net −6 at
32k). The small net at any budget is just which way the churn happened to lean for those 3 seeds.

## Revised conclusion (supersedes the §Takeaways above)

- **Retrieval is NOT a robust lever.** Its Phase 1 +3.4pp@8k was within the seed-noise band (flagged
  even then) and **did not replicate** — a second independent campaign gives +0.7pp@8k, and the
  cross-budget trend is +2.2 → +0.7 → −0.8 as B goes 2k→8k→32k. The mechanism is prompt-perturbation
  churn, not premise injection.
- **Do NOT anchor a best-combo cell on BM25 retrieval.** At most it offers a marginal low-budget
  (2k) nudge that is gone by 8k and negative by 32k.
- **Methodology lesson:** with per-seed std ~1.5–3pp and n=3, a single ~3pp OFAT delta is
  indistinguishable from noise. Real-effect claims need either more seeds or paired/within-run
  analysis (the flip table is far more informative than the means). Apply this bar to *every* Phase 1
  component delta — by it, none of the components (incl. retrieval) cleared noise.
- **Open:** if premise retrieval is to help at all, it likely needs (a) a relevance filter / smaller
  k so it stops distracting, or (b) the deferred ReProver neural backend rather than BM25. Both are
  speculative; neither is justified by current evidence. Re-prioritize behind generation-mode (BFS)
  and a genuinely held-out novel split.
