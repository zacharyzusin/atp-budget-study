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

### Why the question is asked at a fixed budget

Work on LLM theorem provers regularly reports gains from *scaffolding*: retrieve relevant lemmas,
let the model critique its own output, remember what already failed, hint at a proof skeleton. Those
gains are normally measured at a fixed number of attempts — `pass@N`, meaning "draw `N` independent
proofs, count the problem solved if any of them verifies."

`pass@N` holds *tries* fixed, which is not the same as holding *cost* fixed. Attempts are not
equally expensive: a chain-of-thought prover can spend ten times as many tokens per attempt as a
terse one. And every scaffold makes an attempt more expensive — retrieval lengthens the prompt, a
critic step adds an entire extra generation, refinement spends tokens re-reading compiler errors.
Scored at fixed `N`, a scaffolded system is quietly handed a larger compute budget than the baseline
it is compared against, so a reported gain can be partly, or entirely, the extra spend.

Fixing the budget instead of the attempt count removes that confound and leaves a sharper question:

> **Given a fixed number of tokens to spend on one Lean theorem, is there anything better to do with
> them than repeatedly sampling whole proofs and repairing them from compiler errors?**

Under this accounting a scaffold has to pay for itself out of tokens the baseline could otherwise
have spent on more attempts. For the two models tested, nothing did.

### The experiment

The unit of work is a **cell**: one (problem, seed) pair. A cell runs this loop over a single
theorem statement, against a fixed token ledger
([`src/atp/agents/whole_proof.py`](src/atp/agents/whole_proof.py)):

> **propose** a complete Lean proof → **verify** it with Lean → on failure, append the compiler error
> to the prompt and ask for a **revision** → repeat until Lean accepts a proof or the ledger empties.

Up to 4 revisions chain off a proposal before the agent discards that line of attack and draws a
fresh proposal from scratch. So there are two kinds of try, and they are not interchangeable: a
**proposal** is a new independent attempt — this is what `pass@N`'s *N* counts — while a
**revision** is another pass at the current attempt with the error message attached. Both spend from
the same ledger, and the ledger, not any round count, is what ends the run.

The model sees one theorem at a time. There is no cross-problem learning, no proof cache and no
human in the loop; the failed-attempt memory tested in §2.2 is within a single problem. The
**baseline** is exactly the loop above with nothing added. Model weights are frozen for the baseline
and for every test-time intervention; two of the eleven arms deliberately modify the weights, and
are marked as training arms.

**Solved** means the Lean REPL, running against a pinned Mathlib, accepted a complete proof of the
stated theorem. It does not mean "compiled without error": a solve requires a declared goal and a
proof free of `sorry` or equivalent escapes. Lean is the only authority — no LLM ever decides
whether a proof counts. That distinction is not pedantic; two of the five harness bugs in §2.6 were
cases where output that merely failed to raise an error was being scored as a proof.

One term recurs below: a benchmark's **trapped core** is the set of problems that no baseline seed
solved even at the full 128k budget. It is the population where the ceiling actually sits, and
several interventions were tested there specifically, against a baseline that is 0% by construction.

### How the budget is counted, and what `pass@B` means

**Budget `B`** is the total number of tokens the model *generates* on one problem, summed across
every call the loop makes — proposals and revisions alike. It is metered exactly, from the serving
stack's own `completion_tokens`, and the loop stops the moment the ledger is empty. Because it
counts tokens rather than seconds, it is hardware-independent; GPU-hours were logged but are never
the reported axis, since they are not comparable across GPU types.

**`pass@B`** is the fraction of problems for which Lean accepted a proof before cumulative
generation passed `B` tokens, reported at 2k / 8k / 32k / 128k.

The curves are produced by running each cell once against the 128k cap, recording the cumulative
token count at which its proof verified, and re-scoring at smaller `B`: a cell counts as solved@B if
its proof arrived within `B` tokens. Nothing is regenerated per budget level, so the four columns of
a curve are four readings of one run, not four runs.

One asymmetry is worth knowing, because it cuts in favour of the interventions rather than against
them: only generated tokens are charged, not prompt tokens. A scaffold that works by enlarging the
prompt — retrieved premises, remembered failures, strategy hints — gets that context for free under
this accounting. It was still unable to beat the baseline.

The cost of choosing `pass@B` is that these numbers cannot be set beside published `pass@N` numbers
without a conversion, and no constant performs it — how many attempts a budget buys depends on the
model and on the problem set. The next section is that conversion.

### What a budget actually buys, and what a fractional attempt means

Complete proposals per problem, by budget — mean across problems, from
[`results/phase0/ATTEMPTS_PER_BUDGET_TABLE.md`](results/phase0/ATTEMPTS_PER_BUDGET_TABLE.md):

| budget | Goedel x miniF2F | Goedel x ProofNet# |
|---|---|---|
| 2k | 0.30 (median 0) | 0.16 (median 0) |
| 8k | 0.82 | 0.68 |
| 32k | 1.11 | 1.51 |
| 128k | 1.94 (median 1) | 4.71 |

These are averages over problems, not fractions of an attempt within a problem. "0.30 attempts at
2k" means roughly 30% of problems got one complete proposal inside 2k tokens while the other 70% did
not finish even their first — for those, generation was still running when the ledger emptied, and
they are failures at that budget by construction.

At small `B`, then, a large share of problems cannot succeed no matter what, which makes the 2k
column close to uninformative. What survives there is mostly the set of problems the model happened
to answer *briefly*, and brevity correlates with easiness. It is reported for the shape of the curve;
no claim in this project rests on it.

The same table is what reconciles these numbers against published `pass@N` figures. At `B`=128k
Goedel completes a mean of 1.94 independent proposals on miniF2F, median 1, so the 128k column sits
nearer pass@2 than pass@32 — which is why a headline 75.3% here and a published 84.6% at pass@32 are
not in conflict (§3.2).

### Models, benchmarks, protocol

- **Two independently trained provers**, so that any finding they share is a property of the model
  class rather than a quirk of one checkpoint: **Goedel-Prover-V2-8B** (chain-of-thought style) and
  **DeepSeek-Prover-V2-7B**.
- **Two benchmarks**: **miniF2F-test** (244 problems, competition style, in distribution for both
  provers) and **ProofNet#** (186 problems, undergraduate mathematics, out of distribution, roughly
  3-5x harder). ProofNet# is the corrected Lean 4 ProofNet (`PAug/ProofNetSharp`), not the original.
- **Three or more seeds** on every headline number, reported as mean ± seed standard deviation.
  Exceptions are flagged in §4.

The two benchmarks do different jobs. miniF2F shows what more budget buys on the kind of problem
these provers were trained for. ProofNet# is where the ceiling is visible: at 128k the baseline
still fails about 85% of it.

### How each intervention was compared

One factor at a time. Each arm is the baseline loop with exactly one thing changed, run on the same
problems, the same seeds and the same budget, so a difference is attributable to that one change. No
interaction terms between components were measured. Deltas are paired per problem — the same problem
under both arms — rather than compared as two independent means, because paired comparison is far
more sensitive at these sample sizes.

Two shapes of result appear in §2.2, and the difference is just which population an arm was run on:

- **Percentage-point deltas** — the arm ran on a full benchmark, so its solve rate is compared
  against the baseline's on the same problems. "−6.5pp" means it solved 6.5% fewer of the 186
  problems.
- **Raw fractions like 0/150** — the arm ran on a trapped core, where the baseline solves nothing by
  construction. There is no percentage to compare against; the only question is how many previously
  unsolved problems it closed, so the count is reported directly.

Training arms (supervised fine-tuning, RL) produce a new checkpoint, which is then evaluated with
the ordinary baseline loop at the same budget, so their numbers are comparable to the rest.

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

Evidence, by row:

- **1-5** — [`phase1/FINDINGS.md`](results/phase1/FINDINGS.md),
  [`EQUIVALENCE_BOUNDS.md`](results/EQUIVALENCE_BOUNDS.md)
- **6** — [`phase2/MECHANISM.md`](results/phase2/MECHANISM.md)
- **7** — [`phase3/HAMMER_PROBE.md`](results/phase3/HAMMER_PROBE.md)
- **8** — [`phase6/FINETUNE.md`](results/phase6/FINETUNE.md)
- **9** — [`phase6/STAGE_C_RESULT.md`](results/phase6/STAGE_C_RESULT.md)
- **10** — [`phase7/STEPWISE.md`](results/phase7/STEPWISE.md)
- **11** — [`phase_decomp/DESIGN.md`](results/phase_decomp/DESIGN.md)

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

Two stories are consistent with flat curves. Either the model runs out of *ideas* — it resamples the
same couple of approaches forever and never considers a third — or it has an adequate idea and
cannot *execute* it to a closed goal. These imply opposite research programs, so the project tested
which one holds.

Four pieces of evidence, from [`results/phase2/MECHANISM.md`](results/phase2/MECHANISM.md):

1. **Diversity does collapse.** On unsolved cells the model produces 19-24 attempts but commits to
   only ~2 distinct opening tactics across all of them (a mean of 1.94 distinct openings on miniF2F,
   2.28 on ProofNet#), while downstream proof skeletons vary much more (6-9 distinct). It reshuffles
   tactics inside about two fixed frames rather than reconsidering the approach.
2. **But the failures are not idea failures.** Classifying the most advanced failure reached per
   unsolved cell: **95-99% are reasoning failures** — the proof elaborates, the goal will not close.
   Formalization and syntax account for 1-4%, and a hallucinated or missing premise for ≤1%. Premise
   availability being under 1% of the problem is why retrieval was doomed before it was run.
3. **Late solves never come from a new idea.** Among problems first solved on attempt 3 or later,
   **0.0%** used an opening tactic the model had not already tried and failed with. Wins arrive by
   executing an approach the model already had.
4. **The causal test.** On the trapped cores — problems no baseline seed solved at 128k — approach
   diversity was forced up by approach-conditioned prompting at matched budget. The manipulation
   fired: distinct opening tactics per attempt rose **42-70%** across all four model x benchmark
   arms (for example 1.17 → 1.71 on Goedel x miniF2F). Solves did not move: **5 verified flips in
   total** across all four arms, within seed noise of zero. Proof quality got *worse* — pushed for
   novelty, the models emitted 1.5-2x more syntactically broken proofs and roughly triple the
   `sorry` loopholes, all of which the verifier caught.

**Approach discovery is not the bottleneck; carrying one approach through to a closed proof is.**
That single mechanism accounts for most of §2.2. Interventions 1-6 all target idea generation and
8-9 target post-hoc adaptation, so none of them can touch the thing that is actually binding. The
three arms that *do* attack execution depth directly — symbolic leaf-closing (7), stepwise
state-grounding (10) and subgoal decomposition (11) — were run precisely because the mechanism
pointed at them, and they are null as well. Handing a model its own true verified proof state at
every step, and letting a search-native model backtrack over it, still closes zero of 150 trapped
problems.

### 2.5 The one lever that moved: abandon hopeless problems earlier

This is a policy question rather than a model or scaffold change. Given a fixed budget across a
batch of problems, how should it be split? A logistic predictor, using only information observable
at a decision checkpoint (tokens spent so far, attempts made, deepest verified proof step, progress
plateau) and out-of-fold predictions, flags problems as likely trapped. Those are abandoned and
their budget is reallocated to the survivors.

| model x benchmark | compute saved at 90% of uniform's solves | per-seed | call |
|---|---|---|---|
| **Goedel x ProofNet#** | **+30%** | +26% ± 7% (3 seeds) | strong, seed-robust |
| DeepSeek x ProofNet# | +10% | +10% ± 24% (8 seeds) | below the pre-registered 15% bar |
| Both models x miniF2F | negative | negative on nearly every seed | the intended contrast |

Four caveats travel with this number and should not be dropped:

- **One-model-robust, not two.** DeepSeek's version sits below the bar that was registered before
  the run, and a paired per-problem bootstrap CI crosses zero for both models.
- **It works only at fractional accuracy.** To solve *every* winnable problem you must keep the
  hardest ones, whose cost is indistinguishable from that of trapped ones, so at a 100% target the
  policy keeps nearly everything and saves ~0. The claim is "retain 90-95% of solves for 25-30% less
  compute," not "same accuracy, less compute."
- **miniF2F is negative on purpose.** At a ~75% solve rate there is little wasted compute to
  reclaim, which is what was pre-registered.
- **Simulated, not live-confirmed.** The policy is computed offline over the committed baseline
  runs. It is realizable by construction — the agent's trajectory does not depend on the announced
  budget, so abandoning a problem is exactly early-stopping a logged trajectory — but a live
  confirming run was never done.

For scale: an unrealizable oracle that funds the cheapest proofs first saves 95-98%. The realizable
policy captures about a third of that headroom on Goedel x ProofNet#; the rest is the cost of not
knowing in advance which problems are trapped.
[`results/phase4/ALLOCATION.md`](results/phase4/ALLOCATION.md) also records two multi-round policy
variants that were pre-registered and then falsified.

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

The first row is a calibration check, not a headline: it is a union over the 3 baseline seeds plus
32 fresh samples on the previously unsolved subset, not a clean pass@32 run over all 244 problems.
It is reported only to answer "is this harness producing numbers wildly out of line with what is
published"
([`results/phase0/PASS_AT_32_RECONCILIATION.md`](results/phase0/PASS_AT_32_RECONCILIATION.md)).

Three points do most of the reconciling:

- **The Goedel gap closes once budget is converted into attempts.** Goedel is a chain-of-thought
  model; at `B`=128k it completes a mean of 1.94 independent propose attempts, median 1. That is
  much closer to pass@2 than to pass@32. The apparent 9pp shortfall is the `pass@B` vs `pass@N`
  distinction, not a harness defect — which is why the pass@32-scale reconciliation in the first row
  lands in the published band.
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

- **No compute-unmatched positive control.** Every intervention was run budget-matched. The argument
  is that this is *why* they came out null, but the harness was never shown to detect a scaffolding
  gain under the conditions where the literature reports one. Re-running one intervention at a
  deliberately unmatched budget is the highest-value remaining check.
- **The operating point is narrow.** At `B`=128k Goedel gets a mean of 1.94 attempts, so a scaffold
  costing 2x per attempt has to nearly double per-attempt success just to break even. This follows
  from matching budget rather than being a defect, but "nothing works" should be read as "nothing
  works at a budget that buys roughly two attempts."
- **Several interventions are weaker than their published counterparts.** The retrieval arm is
  untrained BM25 into a whole-proof prompt, where ReProver uses a trained retriever in a stepwise
  loop. The hammer arm is a lite in-context tactic portfolio, not `duper` or an SMT bridge — those
  are not available on the v4.9.0 pin and were not ported. The RL probe is LoRA r=16 for 80 steps,
  far smaller than any published RL stage. These nulls constrain our implementations, not the
  general techniques.
- **Not everything got the full seed protocol.** The stepwise arc (§2.2 item 10) was a single-seed
  feasibility and disambiguation effort, not a 3-seed headline run, and it covers only the Goedel
  ProofNet# trapped core — miniF2F and DeepSeek's own trapped set were never run through it. The
  allocation result was never confirmed by a live run.
- **Scale and scope.** Everything is 7-8B parameters; whether the execution floor persists at larger
  scale is the largest open question, and a scoped 32B calibration cell was deliberately not run
  ([`results/phase_scale32b/FEASIBILITY.md`](results/phase_scale32b/FEASIBILITY.md)). Models trained
  specifically for decomposition are a different class, and none of this is evidence against them.
- **The trapped cores are a regime, not a property of the problems.** Fresh resampling at pass@32
  with no budget cap recovered 6/55 of the Goedel miniF2F core (~11%). "Trapped" means "this loop,
  at this budget, did not solve it."

---

## 5. What may be useful outside this project

- **[`results/audit/BUG_CATALOGUE.md`](results/audit/BUG_CATALOGUE.md)** — five harness bugs and two
  measurement gaps, each with a check you can run against your own LLM-plus-verifier pipeline. Two
  of the five overstate capability, which is the direction that gets published. This is the most
  portable thing here.
- **[`results/phase0/ATTEMPTS_PER_BUDGET_TABLE.md`](results/phase0/ATTEMPTS_PER_BUDGET_TABLE.md)** —
  the budget-to-attempts conversion for four model x benchmark combinations. Needed by anyone
  comparing a compute-bounded result against a published `pass@N` figure.
- **[`results/trapped_cores/`](results/trapped_cores/README.md)** — the five problem lists that no
  baseline seed solved at 128k, with the three caveats that must travel with them. A ready-made hard
  slice for testing an execution-depth intervention, and the population every "0% by construction"
  baseline here is defined against.
- **[`results/EQUIVALENCE_BOUNDS.md`](results/EQUIVALENCE_BOUNDS.md)** — bounded nulls rather than
  bare ones, and a worked case where a within-run bootstrap CI and an independent replication's CI
  do not overlap at all for the same intervention.
- **Two pre-registrations that did their job.**
  [`phase4/PREDICTOR_V2_DESIGN.md`](results/phase4/PREDICTOR_V2_DESIGN.md) set a bar, the result
  missed it, and the direction closed. [`phase_decomp/DESIGN.md`](results/phase_decomp/DESIGN.md)
  set a stopping rule that ended an expensive direction after ~2.3 GPU-hours instead of a full
  array.
- **The harness itself** — budget-metered `pass@B` evaluation with a Lean REPL backend, restartable
  under preemption, with the four cluster constraints in §6 already solved.

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

Four cluster constraints are baked into the harness. Code that ignores them fails silently rather
than loudly:

- `unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy` at the top of every job script. Slurm jobs
  inherit a per-session SSH proxy that breaks all outbound downloads.
- Stage Mathlib's `.olean` files to node-local SSD. Loading them from shared GPFS causes an open
  storm that degrades the filesystem for every user on it.
- Drive the Lean REPL over a PTY with a recursive `LEAN_PATH`, and never pickle its environment —
  doing so silently corrupts verdicts. Force `PATH` after `conda activate`.
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

---

## License

None. This is unreleased academic research code; no license is granted. If you want to use it, ask.
