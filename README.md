# Budget-Bounded Agentic Theorem Proving

**The question:** at a fixed per-problem token budget, what actually raises the solve rate of a
frozen whole-proof Lean prover?

**The answer, at 7-8B scale:** nothing we tried except spending more tokens. Ten interventions —
prompt scaffolding, symbolic automation, step-level search, supervised fine-tuning, RL — were each
compared against a baseline that simply spends the same tokens on repeated proof attempts and
error-guided revisions. None produced a gain that survived replication, and two measurably hurt. A
causal experiment locates the reason: these models are not short of proof ideas, they are unable to
carry one idea through to a closed goal.

---

## 1. Setup

### Why a fixed budget

Work on LLM theorem provers regularly reports gains from *scaffolding* — retrieve relevant lemmas,
let the model critique itself, remember what already failed, hint at a proof skeleton. Those gains
are normally measured at `pass@N`: draw `N` independent proofs, count the problem solved if any
verifies.

`pass@N` holds *tries* fixed, not *cost*. Attempts are not equally expensive — a chain-of-thought
prover can spend ten times the tokens per attempt of a terse one — and every scaffold adds cost of
its own: retrieval lengthens the prompt, a critic adds an entire extra generation, refinement spends
tokens re-reading compiler errors. At fixed `N` the scaffolded system is quietly handed more compute
than its baseline, so a reported gain can be partly, or entirely, the extra spend.

Fixing the budget instead leaves a sharper question:

> **Given a fixed number of tokens to spend on one Lean theorem, is there anything better to do with
> them than repeatedly sampling whole proofs and repairing them from compiler errors?**

An intervention now has to pay for itself out of tokens the baseline could have spent on more
attempts. For the two models tested, none did.

### The experiment

The unit of work is a **cell**: one (problem, seed) pair, running this loop over a single theorem
against a fixed token budget ([`src/atp/agents/whole_proof.py`](src/atp/agents/whole_proof.py)):

> **propose** a complete Lean proof → **verify** it with Lean → on failure, append the compiler error
> to the prompt and ask for a **revision** → repeat until Lean accepts a proof or the budget runs out.

Up to 4 revisions chain off a proposal before the agent discards it and starts a fresh one. The two
kinds of try are not interchangeable: a **proposal** is a new independent attempt — what `pass@N`'s
*N* counts — while a **revision** is another pass at the current one with the error attached. Both
spend from the same budget, and the budget is what ends the run, not a round count.

The model sees one theorem at a time: no cross-problem learning, no proof cache, no human in the
loop. The **baseline** is this loop with nothing added. Model weights are frozen for the baseline
and for every test-time intervention; two of the ten interventions instead retrain the model, and
are marked as such in §2.2.

**Solved** means the Lean REPL, checking against a pinned Mathlib, accepted a complete proof of the
stated theorem — a declared goal and no `sorry` or equivalent escape, not merely a response that
happened not to raise an error. Lean is the only authority; no LLM is ever in the accept path.

A benchmark's **trapped core** is the set of problems no baseline seed solved even at the largest
budget tested. Several interventions were tested there specifically, against a baseline that is 0%
by construction.

### Budget and `pass@B`

**`B`** is the number of tokens the model *generates* while working on one problem, added up across
every proposal and revision call in the loop. The software that runs the model (vLLM) reports
exactly how many tokens each response contained, so `B` is counted exactly, not estimated — and
because it counts tokens rather than wall-clock time, it doesn't depend on which GPU it ran on.
GPU-hours were logged too but are never the reported number, since they aren't comparable across
different GPU types. Only *generated* tokens are charged, not the prompt fed into the model — so an
intervention that works by adding context (retrieved lemmas, remembered failures, hints) gets that
context for free under this accounting, and still didn't win.

**`pass@B`** is the fraction of problems whose proof Lean accepted before cumulative generation
passed `B`, reported at 2k / 8k / 32k / 128k. Each cell is run once against a 128k-token cap,
recording the token count at which its proof verified; smaller budgets are then re-scored from that
same run rather than regenerated. The four columns of a curve are four readings of one trajectory,
not four separate runs.

### What a budget buys

A `pass@B` number cannot be set beside a published `pass@N` without a conversion, and no constant
performs it. Complete proposals per problem, averaged across problems
([`results/phase0/ATTEMPTS_PER_BUDGET_TABLE.md`](results/phase0/ATTEMPTS_PER_BUDGET_TABLE.md)):

| budget | Goedel x miniF2F | Goedel x ProofNet# |
|---|---|---|
| 2k | 0.30 (median 0) | 0.16 (median 0) |
| 8k | 0.82 | 0.68 |
| 32k | 1.11 | 1.51 |
| 128k | 1.94 (median 1) | 4.71 |

These are averages over problems, not fractions of an attempt within one. "0.30 at 2k" means about
30% of problems completed a proposal inside 2k tokens while the rest were still generating when the
budget ran out — failures at that budget by construction. The 2k column is therefore close to
uninformative, measuring mostly which problems admit a *short* proof, and no claim here rests on it.

At the other end, 128k buys Goedel a mean of 1.94 proposals on miniF2F, median 1 — nearer pass@2
than pass@32, which is why a headline 75.3% here and a published 84.6% at pass@32 are not in
conflict (§4.2).

### Models and benchmarks

- **Two independently trained provers**, so that any finding they share is a property of the model
  class rather than a quirk of one checkpoint: **Goedel-Prover-V2-8B** (chain-of-thought style) and
  **DeepSeek-Prover-V2-7B**.
- **Two benchmarks**: **miniF2F-test** (244 problems, competition style, in distribution) and
  **ProofNet#** (186 problems, undergraduate mathematics, out of distribution, roughly 3-5x harder).
  ProofNet# is the corrected Lean 4 ProofNet (`PAug/ProofNetSharp`), not the original.
- **Three or more seeds** on every headline number, as mean ± seed standard deviation. Exceptions
  are flagged in the Limitations section (§3.3).

miniF2F shows what more budget buys on the problems these provers were trained for. ProofNet# is
where the ceiling shows: at 128k the baseline still fails about 85% of it.

### How the interventions were compared

One factor at a time — the baseline loop with exactly one thing changed, on the same problems, seeds
and budget, so a difference is attributable to that one change. No interaction terms between
interventions were measured. Deltas are paired per problem rather than compared as two independent
means, which is far more sensitive at these sample sizes. The two training interventions
(fine-tuning and RL) instead produce a new checkpoint, which is then evaluated with the ordinary
baseline loop at the same budget, so their numbers are directly comparable to the rest.

Results below take two shapes, depending on which population an intervention ran on: **percentage
point deltas** on a full benchmark, and **raw fractions** like 0/150 on a trapped core, where the
baseline solves nothing by construction and the only question is how many problems the intervention
closed.

---

## 2. Results

### 2.1 Baseline: budget buys solves, and saturates in distribution

`pass@B`, mean ± seed standard deviation over 3 seeds:

| budget | miniF2F, Goedel | miniF2F, DeepSeek | ProofNet#, Goedel | ProofNet#, DeepSeek |
|--------|------------------|--------------------|--------------------|----------------------|
| 2k   | 29.6% ± 3.3% | 27.9% ± 2.1% | 4.8% ± 1.4% | 5.4% ± 0.5% |
| 8k   | 60.2% ± 1.9% | 57.9% ± 1.7% | 9.3% ± 1.1% | 13.1% ± 0.8% |
| 32k  | 69.7% ± 0.8% | 67.3% ± 0.6% | 12.2% ± 0.3% | 18.3% ± 1.6% |
| 128k | 75.3% ± 1.2% | 73.0% ± 0.4% | 14.9% ± 0.3% | 22.2% ± 1.7% |

- A 64x budget increase moves miniF2F from ~29% to ~74% and then flattens. ProofNet# is still
  climbing at 128k from a far lower base. Both models show the same asymmetry independently, so it
  is a property of the task, not of one model.
- The cross-model ordering flips between benchmarks: Goedel leads in distribution, DeepSeek leads
  out of it by 7pp at 128k, and the gap widens with budget. Both provers attempt identical statement
  sets, so this is not a coverage artifact.

(These figures include a small upward correction found during a later audit of the scoring pipeline
— see §4.3.)

### 2.2 Ten interventions, none beat the baseline

Each row was run against the baseline at matched budget. Deltas are in percentage points; bracketed
ranges are 95% paired per-problem bootstrap confidence intervals.

| # | Intervention | Strategy | Result |
|---|---|---|---|
| 1 | Premise retrieval | Lexical (BM25) search over a corpus of Mathlib declarations; the top 8 matches for the goal are prepended to each fresh proposal (not to revisions), so the model can cite a lemma instead of rediscovering it. | Looked like a real gain on miniF2F the first time (+3.4 `[+0.8, +6.2]`), but an independent rerun under identical conditions found less than a quarter of that effect (+0.7 `[-1.8, +3.1]`) — the original result did not replicate. On ProofNet# it actively hurt (**−6.5** `[-9.7, -3.8]`). Tracking which individual problems flipped solved/unsolved between runs showed it creates roughly as many new failures as new solves — it perturbs which proof the model tries without making a correct one more likely. |
| 2 | Failed-attempt memory | Before each fresh proposal, a short summary of this problem's own previous failed attempts (its approach plus the Lean error) is added to the prompt as a "don't repeat this" note. | No measurable effect on either benchmark (+0.4 / −0.4); both confidence intervals span zero. |
| 3 | LLM reviewer | After Lean rejects a candidate, a second model call is asked to critique it. The critique — not a verdict — is folded into the next revision's prompt alongside the real Lean compiler error. It never gets to accept or block a proof; Lean still has the only vote. | No measurable effect on solve rate (+0.3 / +0.5). Its real finding was diagnostic: asked to judge proofs Lean had already rejected, it said "this is fine" on 17 of 249 of them (a 6.8% false-accept rate) — a concrete number for why an LLM should never be the sole judge of a proof. |
| 4 | Tactic-skeleton hints | Each fresh proposal gets a one-line hint naming a common Lean proof pattern (e.g. an induction skeleton, a standard closing-tactic combination), cycling through a fixed list across successive samples so different samples are nudged toward different structures. | No measurable effect on either benchmark (+1.0 / −0.5). |
| 5 | Forced approach diversity | Run only on the trapped cores (problems no baseline seed had solved). Before each fresh proposal, the model is shown the list of opening tactics it has already tried on this problem and explicitly told to take a different approach, at matched budget. | Confirmed to work as intended — opening-tactic diversity rose 42-70% across all four model/benchmark combinations — but this did not produce solves: **5 verified proofs in total** across all four, indistinguishable from zero. Proof quality got worse: pushed toward novelty, the model produced far more syntactically broken output and used the `sorry` placeholder roughly three times as often, all caught by the verifier (interpreted in §3.1). |
| 6 | Hammer / SMT closing | A portfolio of Lean's own closing tactics (`omega`, `nlinarith`, `norm_num`, `simp_all`, `decide`, `aesop`), tried both directly on the bare unsolved goal and substituted in at the exact point where the model's own attempt got stuck. | Closed **0 of 30** trapped problems tried directly and **0 of 40** tried at the failing step. A sanity check confirms the portfolio does work when it should — it solved 4 of 4 trivial synthetic test goals — so this is a genuine null, not a broken setup. |
| 7 | Supervised fine-tuning | Two fine-tuning recipes on top of the frozen base weights, each then evaluated with the ordinary baseline loop: **Stage A** trains on proofs sampled at random from the model's own successful rollouts (generic rejection-sampling fine-tuning); **Stage B** trains specifically on the transition from a deep, stuck proof state to a correct closing, with the training loss restricted to just the closing tokens. | Stage A made things substantially worse everywhere, from −2.5 to **−19.7pp** across both models and both benchmarks. Stage B, the more targeted recipe, also did not help (−0.3 to −2.1pp). |
| 8 | GRPO reinforcement learning | A reinforcement-learning stage (GRPO, LoRA adapters, 80 steps) on top of the frozen weights, rewarding a binary "Lean verified and sound" signal, trained on a problem set disjoint from both benchmarks. | No improvement on a held-out test set (**−1.6pp** pass@1), and the training reward itself never trended upward across all 80 steps — the model wasn't gradually improving and then stalling, it made no measurable training progress at all. |
| 9 | Stepwise generation | Instead of one call producing a whole proof, the model is asked for one tactic at a time and shown the real, Lean-verified proof state after each step — never its own possibly-wrong guess of where the proof stands. Tried both on the reasoning model doing this directly, and on a tactic-native model (BFS-Prover-V1-7B) doing genuine search with backtracking. | 77 of 150 previously-unsolved problems reached real, further verified progress under this scheme — the model was not stuck immediately — but **0 of 150** ever closed. Perfect information about the true proof state at every step did not let it finish. |
| 10 | Subgoal decomposition | Prompt the model to split the target theorem into several smaller helper lemmas (`have` statements) that can each be proved independently, rather than attacking the whole theorem in one proof. | Stopped at the earliest checkpoint by a rule set in advance: across five trial rounds on two models, the model never once produced a structurally valid decomposition, so the direction was abandoned before any further compute was spent. |

Evidence: rows 1-4 [`phase1/FINDINGS.md`](results/phase1/FINDINGS.md) and
[`EQUIVALENCE_BOUNDS.md`](results/EQUIVALENCE_BOUNDS.md); 5
[`phase2/MECHANISM.md`](results/phase2/MECHANISM.md); 6
[`phase3/HAMMER_PROBE.md`](results/phase3/HAMMER_PROBE.md); 7
[`phase6/FINETUNE.md`](results/phase6/FINETUNE.md); 8
[`phase6/STAGE_C_RESULT.md`](results/phase6/STAGE_C_RESULT.md); 9
[`phase7/STEPWISE.md`](results/phase7/STEPWISE.md); 10
[`phase_decomp/DESIGN.md`](results/phase_decomp/DESIGN.md).

Two interventions didn't merely fail to help — they measurably hurt: BM25 retrieval on ProofNet#,
and generic-rollout fine-tuning (Stage A) everywhere.

"Null" is only meaningful with a bound attached — full table:
[`results/EQUIVALENCE_BOUNDS.md`](results/EQUIVALENCE_BOUNDS.md). A paired per-problem bootstrap
gives one-sided upper bounds on each scaffolding intervention's true effect. On miniF2F, memory, the
reviewer, and tactic-skeleton hints are all bounded below **+3.4pp**; retrieval's own bound is
looser, +6.2pp, consistent with it being the one result that looked real before failing to
replicate. On ProofNet#, those same three are bounded below **+2.3pp**; retrieval is the exception,
with a bound that sits entirely below zero — a real, not merely absent, negative effect.

### 2.3 Abandoning hopeless problems earlier

A different kind of question: not what to change about the loop, but how to split a fixed budget
across a *batch* of problems. At a decision checkpoint partway through generation, a logistic
predictor — using only information available by then (tokens spent, attempts made, deepest verified
proof step, whether progress has stalled) — flags problems it judges likely hopeless. Their
remaining budget is reallocated to problems that still look winnable.

| model x benchmark | compute saved at 90% of uniform's solves | per-seed |
|---|---|---|
| **Goedel x ProofNet#** | **+30%** | +26% ± 7% (3 seeds) |
| DeepSeek x ProofNet# | +10% | +10% ± 24% (8 seeds) |
| Both models x miniF2F | negative | negative on nearly every seed |

For scale, an oracle that could see in advance exactly which problems would eventually solve, and
funded the cheapest ones first, would save 95-98% of compute at equal accuracy. What this table does
and doesn't show is discussed in §3.2.
[`results/phase4/ALLOCATION.md`](results/phase4/ALLOCATION.md) also records two multi-round variants
of this policy that were pre-registered and then falsified.

---

## 3. Discussion

### 3.1 Why nothing at test time worked: an execution floor

Flat curves admit two explanations with opposite implications: either the model runs out of *ideas*,
or it has an adequate idea and cannot *execute* it to a closed goal. Four pieces of evidence, from
[`results/phase2/MECHANISM.md`](results/phase2/MECHANISM.md):

1. **Diversity does collapse.** On unsolved cells the model makes 19-24 attempts but commits to only
   ~2 distinct opening tactics across all of them, while downstream proof skeletons vary much more
   (6-9 distinct). It reshuffles tactics inside about two fixed frames rather than reconsidering the
   approach.
2. **But the failures are not idea failures.** Classifying the most advanced failure per unsolved
   cell: **95-99% are reasoning failures** — the proof elaborates, the goal will not close. Syntax
   accounts for 1-4%, a missing or hallucinated premise for ≤1%. Premise availability being under 1%
   of the problem is why retrieval (row 1) was doomed before it was run.
3. **Late solves never come from a new idea.** Among problems first solved on attempt 3 or later,
   **0.0%** used an opening tactic the model had not already tried and failed with.
4. **The causal test.** Row 5 (forced approach diversity) is this project's direct manipulation of
   the pattern above: diversity was pushed up on purpose, it demonstrably rose, and solves still did
   not move. That is the strongest form of evidence available — not just a correlation, but a forced
   intervention that had the intended effect on diversity and no effect on solving.

**Approach discovery is not the bottleneck; carrying one approach through to a closed proof is.**
That single mechanism accounts for most of §2.2: rows 1-5 target idea generation and 7-8 target
post-hoc adaptation, so none of them can touch what is actually binding. The three interventions
that *do* attack execution depth — symbolic leaf-closing (6), stepwise state-grounding (9), subgoal
decomposition (10) — were run because the mechanism pointed at them, and are null as well. Handing a
model its own verified proof state at every step, and letting a search-native model backtrack over
it, still closes zero of 150 trapped problems.

### 3.2 What the allocation result does and doesn't show

Four things temper the headline +30% for Goedel x ProofNet# in §2.3:

- **It only really holds for one model.** DeepSeek's version of the same policy sits below the bar
  set before the run, and a bootstrap confidence interval crosses zero for both models — a one-model
  result, not a two-model one.
- **It only works short of full accuracy.** Solving *every* winnable problem means keeping the
  hardest ones too, whose cost looks identical to a genuinely trapped problem's, so at a 100% target
  the policy keeps almost everything and saves close to nothing. The real claim is "keep 90-95% of
  the solves for 25-30% less compute," not "same accuracy, less compute."
- **miniF2F coming out negative is expected, not a failure.** At a ~75% solve rate there is little
  wasted compute left to reclaim, which is exactly what was predicted before the run.
- **It was never run live.** The saving is computed by replaying the already-collected baseline runs
  and checking what an early-abandonment policy would have kept. Because a proof attempt's
  trajectory never actually depends on the announced budget, that replay is equivalent to really
  running the policy — but a live confirming run was never done.

For scale, the realizable policy captures roughly a third of the oracle's headroom (§2.3); the rest
is the cost of not knowing in advance which problems are trapped.

### 3.3 Limitations

- **No compute-unmatched positive control.** Everything was run budget-matched. The argument is that
  this is *why* the interventions came out null, but the harness was never shown to detect a
  scaffolding gain under the conditions where the literature reports one. Re-running one
  intervention at a deliberately unmatched budget is the highest-value remaining check.
- **The operating point is narrow.** At `B`=128k Goedel gets ~1.94 attempts, so an intervention
  costing 2x per attempt must nearly double per-attempt success to break even. That follows from
  matching budget rather than being a defect, but "nothing works" should be read as "nothing works
  at a budget buying roughly two attempts."
- **Several interventions are weaker than their published counterparts.** Retrieval (row 1) is
  untrained BM25 into a whole-proof prompt, where ReProver uses a trained retriever in a stepwise
  loop. The hammer intervention (row 6) uses a lite in-context tactic portfolio, not `duper` or an
  SMT bridge — neither is available on the Lean version pinned for this project. The RL probe (row
  8) is LoRA rank 16 for 80 steps, far smaller than any published RL stage. These nulls constrain
  our implementations, not the general techniques.
- **Not everything got the full seed protocol.** The stepwise arc (row 9) was single-seed and
  covers only the Goedel ProofNet# trapped core; miniF2F and DeepSeek's own trapped set were never
  run through it. The allocation result (§2.3) was never confirmed live.
- **Scale and scope.** Everything is 7-8B parameters; whether the execution floor persists at larger
  scale is the largest open question, and a scoped 32B calibration cell was deliberately not run
  ([`results/phase_scale32b/FEASIBILITY.md`](results/phase_scale32b/FEASIBILITY.md)). Models trained
  specifically for decomposition are a different class, and none of this is evidence against them.
- **The trapped cores are a regime, not a property of the problems.** Fresh resampling at pass@32
  with no budget cap recovered 6/55 of the Goedel miniF2F core (~11%). "Trapped" means "this loop,
  at this budget, did not solve it."

---

## 4. Appendix: why these results should be trusted

Everything above assumes the measurement pipeline itself is sound. This section is the case for
that: internal sanity checks, agreement with independently published numbers, and — kept brief here
since none of it changes any finding above — the handful of scoring bugs found and fixed while
building the pipeline.

### 4.1 Positive controls

| Control | Result |
|---|---|
| Sensitivity | the baseline moves 29.6% → 75.3% across the budget sweep, so the metric responds to the variable that should move it |
| Manipulation check | forced diversity (§2.2 row 5) demonstrably fired (+42-70%) in all four model/benchmark combinations, so the null in §3.1 came from an intervention that took effect, not one that silently failed to run |
| Symbolic positive control | the closing-tactic portfolio (row 6) solves 4/4 synthetic trivial goals, then 0/70 real trapped ones |
| Known-good proofs | 37/37 Goedel and 40/40 DeepSeek previously solved cells re-verify as correct on the fully patched backend |
| Independent recompute | roughly 30 audit checks re-derived committed numbers using code that imports none of this project's analysis; most reproduced them exactly |
| Self-detection | the audit itself invalidated one of this project's own results (§4.3) and forced a correction to the published baseline curves, rather than only confirming what was already believed |

### 4.2 Consistency with published results

| Our result | Published | Verdict |
|---|---|---|
| Goedel miniF2F, 195/244 ≈ 80% at roughly pass@32-scale sampling | authors report 84.6% at pass@32 ([2508.03613](https://arxiv.org/abs/2508.03613)); a third-party reproduction reports ~78% | lands between the two |
| Goedel baseline 75.3% at `B`=128k | 84.6% at pass@32 | explained by the budget-to-attempts conversion in §1 |
| Retrieval hurts out of distribution | ReProver degrades on its own novel-premises split ([2306.15626](https://arxiv.org/abs/2306.15626)) | same direction |
| Reviewer step null | intrinsic self-correction without ground truth is an established null ([2310.01798](https://arxiv.org/abs/2310.01798)) | replicates |
| Allocation saves ~30% | difficulty-aware allocation saves up to 4x ([2408.03314](https://arxiv.org/abs/2408.03314)) | inside range, conservative |
| GRPO probe null at 80 steps | V1.5's RL stage gains +1.2 to +2.3pp over ~4,500 theorems ([2408.08152](https://arxiv.org/abs/2408.08152)) | expected at this probe's scale |

The first row is a calibration check, not a headline: it unions the 3 baseline seeds with 32 fresh
samples on the previously unsolved subset, so it is not a clean pass@32 run. It exists only to test
whether this harness produces numbers wildly out of line with published ones
([`results/phase0/PASS_AT_32_RECONCILIATION.md`](results/phase0/PASS_AT_32_RECONCILIATION.md)).

Two points do most of the reconciling. First, the Goedel gap closes once budget is converted into
attempts: as set out in §1, `B`=128k buys Goedel a mean of 1.94 proposals — nearer pass@2 than
pass@32 — so the apparent 9pp shortfall is the `pass@B` vs `pass@N` distinction, not a harness
defect. Second, published scaffolding gains are typically compute-unmatched, comparing a scaffolded
system against a cheaper baseline; holding the budget fixed is a strictly harder test, so a null
where the literature reports a gain is the expected outcome, not a contradiction of it.

### 4.3 Harness bugs found during the audit

While building the pipeline, five scoring bugs were found and fixed — two that made the model look
more capable than it was, and three that made it look less capable. The most consequential: a
soundness check read the wrong part of a proof completion and forced one entire model-comparison
sweep ("Phase 8") to a flat, meaningless 0% regardless of quality; that sweep is **withdrawn** and
no number in this document cites it. A second bug — a Lean elaboration-timeout setting left at its
default — caused a small number of genuinely correct proofs to be scored as failures; the baseline
curves in §2.1 already include this correction (up to +1.0pp per cell). None of the five bugs
affects any other number in this document.

Each is written up in full — mechanism, which results it touched, and a check you can run against
your own harness — in
**[`results/audit/BUG_CATALOGUE.md`](results/audit/BUG_CATALOGUE.md)**. None of the five is specific
to this codebase; they are the kind of error that reproduces silently in any pipeline pairing an LLM
with an automated verifier.

---

## 5. Running it

```bash
module load anaconda/2023.09
conda activate /insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study/scratch/conda-envs/atp

make verify   # fast suite (~700 tests, ~10s) + ruff. The gate before any commit.
make test-all # adds the slow/gpu/lean markers (run on a GPU node)
make smoke    # 2-5 problem end-to-end sanity check, needs an interactive GPU session

# Reproduce a baseline pass@B curve (miniF2F-test, 3 seeds):
mkdir -p logs results
sbatch slurm/sweep.sh configs/phase0_baseline.yaml baseline
```

The sweep starts a vLLM server, runs the agent over the problem set, and writes per-problem JSON, a
`pass@B` curve, and a run manifest to `results/baseline/`. Jobs are restartable: the cluster
preempts and requeues, and completed `(config, seed, problem)` cells are skipped on resume.

Four cluster constraints are baked into the harness; code that ignores them fails silently:

- `unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy` atop every job script — Slurm jobs inherit a
  per-session SSH proxy that breaks all outbound downloads.
- Stage Mathlib's `.olean` files to node-local SSD. Loading from shared GPFS causes an open storm
  that degrades the filesystem for every user on it.
- Drive the Lean REPL over a PTY with a recursive `LEAN_PATH`, and never pickle its environment,
  which silently corrupts verdicts. Force `PATH` after `conda activate`.
- Every GPU sweep is gated on a probe that must accept a `norm_num` proof and reject a false one, so
  a broken environment fails loudly instead of presenting as a low pass rate.

Partitions: `short` (12h) for eval, `burst` (14 days, preemptible) for sweeps and training.
`gpu:l40s:1` for inference, `gpu:h100:1` for training. Account `edu`.

---

## 6. Repository layout

```
CONVENTIONS.md    # engineering rules the code was written under, cited by rule number
Makefile          # make verify / test / smoke / lint

src/atp/
├── lean/         # Lean 4 REPL backend, whole-proof verifier, compiler-error parser
├── models/       # vLLM client, budget meter, prompt templates
├── agents/       # propose-verify-refine loop; components/ = the scaffolding ablation axes
├── alloc/        # cross-problem budget allocation: features, difficulty predictor, policies
├── budget/       # token accounting and stopping
├── data/         # miniF2F / ProofNet# loaders, exclusions, contamination checks
├── eval/         # pass@B metrics, run manifests, sweep harness, aggregation, plots
└── rl/           # GRPO reward, diversity, subset selection

configs/          # one versioned YAML per experiment. Pins are load-bearing.
slurm/            # restartable sbatch scripts. Read the constraints in §5 first.
scripts/          # analysis and one-off probes
results/          # the evidence for every number above; see results/README.md
tests/            # mirrors src/ (markers: slow, gpu, lean)
env/              # frozen pip + conda listings for the environment behind every result
```

---

## 7. Reproducibility pins

Runs write a `run_manifest.json` recording git SHA, config hash, seed, model revision, Mathlib
commit, Lean version, host, GPU type and timestamps. The toolchain is pinned exactly because Mathlib
API drift lowers a prover's pass rate silently instead of raising an error — a wrong pin invalidates
comparisons without failing loudly.

| Component | Pin |
|---|---|
| Prover A | `Goedel-LM/Goedel-Prover-V2-8B` @ `dfd02e6271a58375dfbf3ece0175277cf6b6a89a` |
| Prover A toolchain | `leanprover/lean4:v4.9.0-rc1` |
| Prover A mathlib4 | `xinhjBrant/mathlib4` @ `2f65ba7f1a9144b20c8e7358513548e317d26de1`, a custom fork matched to the prover's training-time API. Not in Mathlib's public cache; must be built from source. |
| Prover B | `deepseek-ai/DeepSeek-Prover-V2-7B` @ `a8d9e144` |
| Prover B toolchain | `leanprover/lean4:v4.9.0` |
| Prover B mathlib4 | `leanprover-community/mathlib4` @ `f0957a7575317490107578ebaee9efaf8e62a4ab` (upstream) |
| Serving stack | vLLM `0.8.5.post1`, PyTorch `2.6.0+cu124`, transformers `4.51.3` |

Full package versions are in [`env/`](env/). The Lean toolchain and the Mathlib fork live in
`scratch/` and are built from source by `scripts/setup_lean_env.sh`.
