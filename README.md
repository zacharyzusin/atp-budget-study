# Budget-Bounded Agentic Theorem Proving

**The question:** at a fixed per-problem token budget, what actually raises the solve rate of a
frozen whole-proof Lean prover?

**The answer, at 7-8B scale:** nothing we tried except spending more tokens. Eleven interventions —
prompt scaffolding, symbolic automation, step-level search, supervised fine-tuning, RL — were each
compared against a baseline that simply spends the same tokens on repeated proof attempts and
error-guided revisions. None produced a gain that survived replication, and three measurably hurt. A
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
prover can spend ten times the tokens per attempt of a terse one — and every scaffold makes an
attempt dearer still: retrieval lengthens the prompt, a critic adds an entire extra generation,
refinement spends tokens re-reading compiler errors. At fixed `N` the scaffolded arm is quietly
handed more compute than its baseline, so a reported gain can be partly, or entirely, the extra
spend.

Fixing the budget instead leaves a sharper question:

> **Given a fixed number of tokens to spend on one Lean theorem, is there anything better to do with
> them than repeatedly sampling whole proofs and repairing them from compiler errors?**

A scaffold now has to pay for itself out of tokens the baseline could have spent on more attempts.
For the two models tested, none did.

### The experiment

The unit of work is a **cell**: one (problem, seed) pair, running this loop over a single theorem
against a fixed token ledger ([`src/atp/agents/whole_proof.py`](src/atp/agents/whole_proof.py)):

> **propose** a complete Lean proof → **verify** it with Lean → on failure, append the compiler error
> to the prompt and ask for a **revision** → repeat until Lean accepts a proof or the ledger empties.

Up to 4 revisions chain off a proposal before the agent discards it and starts a fresh one. The two
kinds of try are not interchangeable: a **proposal** is a new independent attempt — what `pass@N`'s
*N* counts — while a **revision** is another pass at the current one with the error attached. Both
spend from the same ledger, and the ledger is what ends the run.

The model sees one theorem at a time: no cross-problem learning, no proof cache, no human in the
loop. The **baseline** is this loop with nothing added, and weights are frozen for it and for every
test-time arm; the two training arms in §2.2 are marked as such.

**Solved** means the Lean REPL, on a pinned Mathlib, accepted a complete proof of the stated theorem
— a declared goal and no `sorry` or equivalent escape, not merely the absence of a compiler error.
Lean is the only authority; no LLM is ever in the accept path. Two of the five bugs in §2.6 were
cases where output that failed to raise an error was being scored as a proof.

A benchmark's **trapped core** is the set of problems no baseline seed solved even at 128k. Several
interventions were tested there specifically, against a baseline that is 0% by construction.

### Budget and `pass@B`

**`B`** is the number of tokens the model *generates* on one problem, across every call the loop
makes. It is metered from the serving stack's own `completion_tokens`, so it is exact and
hardware-independent; GPU-hours were logged but never reported, being incomparable across GPU types.
Only generated tokens are charged, not prompt tokens — so context-enlarging scaffolds got their
context free and still lost.

**`pass@B`** is the fraction of problems whose proof Lean accepted before cumulative generation
passed `B`, reported at 2k / 8k / 32k / 128k. Each cell is run once against the 128k cap, recording
the token count at which its proof verified; smaller budgets are re-scored from that same run. The
four columns of a curve are four readings of one trajectory, not four runs.

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
ledger emptied — failures at that budget by construction. The 2k column is therefore close to
uninformative, measuring mostly which problems admit a *short* proof, and no claim here rests on it.

At the other end, 128k buys Goedel a mean of 1.94 proposals on miniF2F, median 1 — nearer pass@2
than pass@32, which is why a headline 75.3% here and a published 84.6% at pass@32 are not in
conflict (§3.2).

### Models and benchmarks

- **Two independently trained provers**, so that any finding they share is a property of the model
  class rather than a quirk of one checkpoint: **Goedel-Prover-V2-8B** (chain-of-thought style) and
  **DeepSeek-Prover-V2-7B**.
- **Two benchmarks**: **miniF2F-test** (244 problems, competition style, in distribution) and
  **ProofNet#** (186 problems, undergraduate mathematics, out of distribution, roughly 3-5x harder).
  ProofNet# is the corrected Lean 4 ProofNet (`PAug/ProofNetSharp`), not the original.
- **Three or more seeds** on every headline number, as mean ± seed standard deviation. Exceptions
  are flagged in §4.

miniF2F shows what more budget buys on the problems these provers were trained for. ProofNet# is
where the ceiling shows: at 128k the baseline still fails about 85% of it.

### How the interventions were compared

One factor at a time — the baseline loop with exactly one thing changed, on the same problems, seeds
and budget. No interaction terms were measured. Deltas are paired per problem rather than compared
as two independent means, which is far more sensitive at these sample sizes. Training arms produce a
checkpoint that is then evaluated with the ordinary baseline loop at the same budget.

Results take two shapes, depending on the population an arm ran on: **percentage-point deltas** on a
full benchmark, and **raw fractions** like 0/150 on a trapped core, where the baseline solves
nothing by construction and the only question is how many problems the arm closed.

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
- These are the heartbeat-corrected curves (§2.6, bug 1). Before/after per cell:
  [`results/audit/HEARTBEAT_CORRECTED_CURVES.md`](results/audit/HEARTBEAT_CORRECTED_CURVES.md).

### 2.2 Eleven interventions, no surviving gain

Each was run against the baseline at matched budget. Deltas in percentage points; bracketed ranges
are 95% paired per-problem bootstrap CIs.

| # | Intervention | What it was | Result |
|---|---|---|---|
| 1 | Premise retrieval | BM25 top-8 Mathlib premises prepended to the prompt | miniF2F +3.4 `[+0.8, +6.2]` **did not replicate** — an independent rerun gave +0.7 `[-1.8, +3.1]`, a non-overlapping CI. ProofNet# **−6.5** `[-9.7, -3.8]` |
| 2 | Failed-attempt memory | prior failed attempts carried into the prompt | +0.4 / −0.4, both CIs span zero |
| 3 | LLM reviewer | a critic on Lean-rejected candidates, advisory only | +0.3 / +0.5. Separately: it accepted 17/249 already-failed candidates (6.8% false accepts) |
| 4 | Tactic-skeleton hints | scheduled strategy hints in the prompt | +1.0 / −0.5 |
| 5 | Within-problem budget split | fresh proposals vs. refinement, at 0.0 / 0.5 / 1.0 | flat across the full range on miniF2F; all-fresh **−3.4** `[-5.8, -1.3]` on ProofNet# |
| 6 | Forced approach diversity | approach-conditioned prompting on the trapped cores, 2 models x 2 benchmarks, budget-matched at 32k | diversity rose 42-70%; **5 verified solves in total** across all four arms, within seed noise of zero. Output quality got worse (see §2.4) |
| 7 | Hammer / SMT closing | `omega \| nlinarith \| norm_num \| simp_all \| decide \| aesop`, on the bare statement and swapped in at the model's failing tactic | **0/30** and **0/40** on the Goedel x ProofNet# trapped core; positive control fires 4/4 |
| 8 | Supervised fine-tuning | Stage A generic rejection-sampling FT; Stage B closing-targeted SFT | A: **−19.7 to −2.5** across both models and benchmarks. B: −2.1 to −0.3 |
| 9 | GRPO reinforcement learning | LoRA r=16, 80 steps, binary Lean-verified reward | held-out pass@1 **−1.6**; training reward flat for all 80 steps |
| 10 | State-grounded stepwise generation | re-grounding on the verified partial proof state, and true tactic-level search with backtracking — including on a tactic-native model (BFS-Prover-V1-7B) | 77/150 trapped problems reached genuine verified progress; **0/150 closed** |
| 11 | Subgoal decomposition | split the goal into independently provable `have` lemmas | closed at the smoke stage by a pre-registered stopping rule: 0/2 structurally valid decompositions over five rounds on two models, ~2.3 GPU-hours spent |

Evidence: rows 1-5 [`phase1/FINDINGS.md`](results/phase1/FINDINGS.md) and
[`EQUIVALENCE_BOUNDS.md`](results/EQUIVALENCE_BOUNDS.md); 6
[`phase2/MECHANISM.md`](results/phase2/MECHANISM.md); 7
[`phase3/HAMMER_PROBE.md`](results/phase3/HAMMER_PROBE.md); 8
[`phase6/FINETUNE.md`](results/phase6/FINETUNE.md); 9
[`phase6/STAGE_C_RESULT.md`](results/phase6/STAGE_C_RESULT.md); 10
[`phase7/STEPWISE.md`](results/phase7/STEPWISE.md); 11
[`phase_decomp/DESIGN.md`](results/phase_decomp/DESIGN.md).

Three arms did not merely fail to help — they hurt: BM25 retrieval and all-fresh budget splitting on
ProofNet#, and generic rejection-sampling fine-tuning everywhere.

### 2.3 How large an effect is ruled out

"Null" is only meaningful with a bound attached. A paired per-problem bootstrap (resampling by
problem, all seeds of a problem together) gives one-sided upper bounds on each scaffolding
component's true effect:

- **miniF2F**: every component's true effect is below **+3.4pp** with ~97.5% one-sided confidence
  (retrieval is the loosest at +6.2pp, and it is the one that failed to replicate).
- **ProofNet#**: every component's true effect is below **+2.3pp**, and two components are
  significantly *negative*.

Full table: [`results/EQUIVALENCE_BOUNDS.md`](results/EQUIVALENCE_BOUNDS.md).

### 2.4 The mechanism: an execution floor, not an idea shortage

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
   of the problem is why retrieval was doomed before it was run.
3. **Late solves never come from a new idea.** Among problems first solved on attempt 3 or later,
   **0.0%** used an opening tactic the model had not already tried and failed with.
4. **The causal test.** On the trapped cores, approach diversity was forced up by
   approach-conditioned prompting at matched budget. The manipulation fired — distinct opening
   tactics per attempt rose **42-70%** across all four model x benchmark arms (1.17 → 1.71 on Goedel
   x miniF2F) — and solves did not move: **5 verified flips in total**, within seed noise of zero.
   Quality got *worse*: pushed for novelty, the models emitted 1.5-2x more syntactically broken
   proofs and roughly triple the `sorry` loopholes, all caught by the verifier.

**Approach discovery is not the bottleneck; carrying one approach through to a closed proof is.**
That single mechanism accounts for most of §2.2: interventions 1-6 target idea generation and 8-9
target post-hoc adaptation, so none of them can touch what is actually binding. The three arms that
*do* attack execution depth — symbolic leaf-closing (7), stepwise state-grounding (10), subgoal
decomposition (11) — were run because the mechanism pointed at them, and are null as well. Handing a
model its own verified proof state at every step, and letting a search-native model backtrack over
it, still closes zero of 150 trapped problems.

### 2.5 The one lever that moved: abandon hopeless problems earlier

A policy question rather than a model or scaffold change: given a fixed budget across a *batch* of
problems, how should it be split? At a decision checkpoint, a logistic predictor — using only
information observable by then (tokens spent, attempts made, deepest verified proof step, progress
plateau) and out-of-fold predictions — flags problems as likely trapped. Those are abandoned and
their budget reallocated to the survivors.

| model x benchmark | compute saved at 90% of uniform's solves | per-seed | call |
|---|---|---|---|
| **Goedel x ProofNet#** | **+30%** | +26% ± 7% (3 seeds) | strong, seed-robust |
| DeepSeek x ProofNet# | +10% | +10% ± 24% (8 seeds) | below the pre-registered 15% bar |
| Both models x miniF2F | negative | negative on nearly every seed | the intended contrast |

Four caveats travel with this number and should not be dropped:

- **One-model-robust, not two.** DeepSeek's version sits below the bar registered before the run,
  and a paired per-problem bootstrap CI crosses zero for both models.
- **It works only at fractional accuracy.** Solving *every* winnable problem means keeping the
  hardest ones, whose cost is indistinguishable from that of trapped ones, so at a 100% target the
  policy keeps nearly everything and saves ~0. The claim is "retain 90-95% of solves for 25-30% less
  compute," not "same accuracy, less compute."
- **miniF2F is negative on purpose.** At a ~75% solve rate there is little wasted compute to
  reclaim, as pre-registered.
- **Simulated, not live-confirmed.** Computed offline over the committed baseline runs. It is
  realizable by construction — a trajectory does not depend on the announced budget, so abandoning a
  problem is exactly early-stopping a logged one — but no live confirming run was done.

For scale: an unrealizable oracle funding the cheapest proofs first saves 95-98%, so the realizable
policy captures about a third of the headroom; the rest is the cost of not knowing in advance which
problems are trapped. [`results/phase4/ALLOCATION.md`](results/phase4/ALLOCATION.md) also records
two multi-round variants that were pre-registered and then falsified.

### 2.6 Five harness bugs

Auditing the pipeline produced a result in its own right. Each bug would have shipped a wrong
headline number, silently, in a specific direction:

| Bug | Effect here | Direction |
|---|---|---|
| Lean `maxHeartbeats` left at its default | correct-but-slow proofs scored as failures, and spurious timeout text injected into **17.8% of miniF2F refinement steps** as if it were a real compiler error | understates capability |
| Truncated completions scored as solved | a truncated preamble compiles without error, and "no error" was read as "proved". Materially corrupted ProofNet#, which was fully re-run on the fixed verifier | **overstates** capability |
| A wedged Lean REPL scored as success | an empty response read as "no errors". Gets worse under concurrency, so it looks like a throughput win | **overstates** capability |
| A soundness gate reading the wrong operand | two independently correct fixes composed into a bug: a `no_goal` regex ran against the raw completion while the backend had begun assembling the theorem wrapper, so for continuation-style models the gate fired on every attempt | forced an exact 0.0%; withdrew a whole phase's headline |
| Lean staging concurrency race | intermittent load-dependent failures that present as flaky infrastructure | noise, masquerades as a low pass rate |

Consequences for this project: the Phase 8 model-zoo headline is **withdrawn** and must not be
cited, and the baseline curves in §2.1 are the post-correction ones. Each bug is written up with
mechanism, blast radius, direction of error, the regression test that locks it, and a concrete test
you can run against your own harness in
**[`results/audit/BUG_CATALOGUE.md`](results/audit/BUG_CATALOGUE.md)**. None of the five is specific
to this codebase.

The generalisable lesson is in the same file: four of the five were caught by a check that covered
*part* of the output surface, and three survived for a while for exactly that reason. When a gate
passes, ask what it does not look at.

---

## 3. Why the nulls should be believed

A broken harness produces nulls too, so the pipeline was validated against internal positive
controls and external published numbers before any null was trusted.

### 3.1 Positive controls

| Control | Result |
|---|---|
| Sensitivity | the baseline moves 29.6% → 75.3% across the budget sweep, so the metric responds to the variable that should move it |
| Manipulation check | forced diversity demonstrably fired (+42-70%) in all four arms, so the null in §2.4 came from a treatment that took effect |
| Symbolic positive control | the closing-tactic portfolio solves 4/4 synthetic trivial goals, then 0/70 real trapped ones |
| Known-good proofs | 37/37 Goedel and 40/40 DeepSeek previously solved cells re-verify as `ok` on the fully patched backend. This control covered only whole-proof-format models, which is exactly why it missed bug 4 |
| Independent recompute | ~30 audit checks re-derived committed numbers using code that imports none of this project's analysis; most reproduced them exactly |
| Self-detection | the audit invalidated the project's own Phase 8 headline and forced a correction to the published baseline curves, rather than confirming what was already believed |

### 3.2 Consistency with published results

| Our result | Published | Verdict |
|---|---|---|
| Goedel miniF2F, 195/244 ≈ 80% at roughly pass@32-scale sampling | authors report 84.6% at pass@32 ([2508.03613](https://arxiv.org/abs/2508.03613)); a third-party reproduction reports ~78% | lands between the two |
| Goedel baseline 75.3% at `B`=128k | 84.6% at pass@32 | explained by the budget-to-attempts conversion, below |
| Retrieval hurts out of distribution | ReProver degrades on its own novel-premises split ([2306.15626](https://arxiv.org/abs/2306.15626)) | same direction |
| Reviewer step null | intrinsic self-correction without ground truth is an established null ([2310.01798](https://arxiv.org/abs/2310.01798)) | replicates |
| Allocation saves ~30% | difficulty-aware allocation saves up to 4x ([2408.03314](https://arxiv.org/abs/2408.03314)) | inside range, conservative |
| GRPO probe null at 80 steps | V1.5's RL stage gains +1.2 to +2.3pp over ~4,500 theorems ([2408.08152](https://arxiv.org/abs/2408.08152)) | expected at this probe's scale |

The first row is a calibration check, not a headline: it unions the 3 baseline seeds with 32 fresh
samples on the previously unsolved subset, so it is not a clean pass@32 run. It exists only to test
whether this harness produces numbers wildly out of line with published ones
([`results/phase0/PASS_AT_32_RECONCILIATION.md`](results/phase0/PASS_AT_32_RECONCILIATION.md)).

Three points do most of the reconciling:

- **The Goedel gap closes once budget is converted into attempts.** As set out in §1, `B`=128k buys
  Goedel a mean of 1.94 proposals — nearer pass@2 than pass@32 — so the apparent 9pp shortfall is
  the `pass@B` vs `pass@N` distinction, not a harness defect.
- **Published scaffolding gains are typically compute-unmatched**, comparing a scaffolded system
  against a cheaper baseline. Holding the budget fixed is a strictly harder test, so a null where
  the literature reports a gain is the expected outcome, not a contradiction of it.
- **Both training nulls have an identifiable signature.** The GRPO probe's training reward never
  trended over 80 steps while KL stayed at 0.0021 and output diversity was unchanged — the clean
  "reward flat, no pathology" branch of the pre-registered decision map, not a mis-tuned stall. The
  SFT signature — near-zero teacher-forced loss on a step in isolation, yet failure when the model
  reaches that step through its own generated prefix — is exposure bias, named in scheduled sampling
  (Bengio et al., 2015) and DAgger (Ross and Bagnell, 2011).

---

## 4. Limitations

- **No compute-unmatched positive control.** Everything was run budget-matched. The argument is that
  this is *why* the arms came out null, but the harness was never shown to detect a scaffolding gain
  under the conditions where the literature reports one. Re-running one intervention at a
  deliberately unmatched budget is the highest-value remaining check.
- **The operating point is narrow.** At `B`=128k Goedel gets ~1.94 attempts, so a scaffold costing
  2x per attempt must nearly double per-attempt success to break even. That follows from matching
  budget rather than being a defect, but "nothing works" should be read as "nothing works at a
  budget buying roughly two attempts."
- **Several arms are weaker than their published counterparts.** Retrieval is untrained BM25 into a
  whole-proof prompt, where ReProver uses a trained retriever in a stepwise loop. The hammer arm is
  a lite in-context tactic portfolio, not `duper` or an SMT bridge — neither is available on the
  v4.9.0 pin and neither was ported. The RL probe is LoRA r=16 for 80 steps, far smaller than any
  published RL stage. These nulls constrain our implementations, not the general techniques.
- **Not everything got the full seed protocol.** The stepwise arc (item 10) was single-seed and
  covers only the Goedel ProofNet# trapped core; miniF2F and DeepSeek's own trapped set were never
  run through it. The allocation result was never confirmed live.
- **Scale and scope.** Everything is 7-8B parameters; whether the floor persists at larger scale is
  the largest open question, and a scoped 32B calibration cell was deliberately not run
  ([`results/phase_scale32b/FEASIBILITY.md`](results/phase_scale32b/FEASIBILITY.md)). Models trained
  specifically for decomposition are a different class, and none of this is evidence against them.
- **The trapped cores are a regime, not a property of the problems.** Fresh resampling at pass@32
  with no budget cap recovered 6/55 of the Goedel miniF2F core (~11%). "Trapped" means "this loop,
  at this budget, did not solve it."

---

## 5. What may be useful outside this project

- **[`results/audit/BUG_CATALOGUE.md`](results/audit/BUG_CATALOGUE.md)** — five harness bugs and two
  measurement gaps, each with a check you can run against your own LLM-plus-verifier pipeline. Two
  of the five overstate capability, the direction that gets published. The most portable thing here.
- **[`results/phase0/ATTEMPTS_PER_BUDGET_TABLE.md`](results/phase0/ATTEMPTS_PER_BUDGET_TABLE.md)** —
  the budget-to-attempts conversion for four model x benchmark combinations, needed by anyone
  comparing a compute-bounded result against a published `pass@N` figure.
- **[`results/trapped_cores/`](results/trapped_cores/README.md)** — the five problem lists no
  baseline seed solved at 128k, with the three caveats that must travel with them. A ready-made hard
  slice for testing an execution-depth intervention.
- **[`results/EQUIVALENCE_BOUNDS.md`](results/EQUIVALENCE_BOUNDS.md)** — bounded nulls rather than
  bare ones, plus a worked case where a within-run bootstrap CI and an independent replication's CI
  do not overlap at all for the same intervention.
- **Two pre-registrations that did their job.**
  [`phase4/PREDICTOR_V2_DESIGN.md`](results/phase4/PREDICTOR_V2_DESIGN.md) set a bar, the result
  missed it, and the direction closed. [`phase_decomp/DESIGN.md`](results/phase_decomp/DESIGN.md)
  set a stopping rule that ended an expensive direction after ~2.3 GPU-hours instead of a full
  array.
- **The harness itself** — budget-metered `pass@B` evaluation over a Lean REPL backend, restartable
  under preemption, with the cluster constraints in §6 already solved.

---

## 6. Running it

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

## 7. Repository layout

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
slurm/            # restartable sbatch scripts. Read the constraints in §6 first.
scripts/          # analysis and one-off probes
results/          # the evidence for every number above; see results/README.md
tests/            # mirrors src/ (markers: slow, gpu, lean)
env/              # frozen pip + conda listings for the environment behind every result
```

---

## 8. Reproducibility pins

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
