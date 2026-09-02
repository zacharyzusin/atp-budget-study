# Budget-Bounded Agentic Theorem Proving

**What actually moves the solve rate of a frozen whole-proof Lean prover at a fixed per-problem token
budget?** Two open ~7–8B provers, two benchmarks, ≥3 seeds everywhere, on one academic Slurm cluster.

The short answer: **almost nothing we tried**, and the interesting part is *why* — plus what auditing
our own measurement apparatus turned up along the way.

> **Status: complete (closed 2026-09-02). No further experiments are planned.**
> This README is the whole record. The dated lab notebooks, the paper draft, and the superseded
> planning documents are in git history, not the working tree.

---

## Contents

1. [The question](#1-the-question)
2. [Setup](#2-setup)
3. [Findings](#3-findings)
4. [Phase by phase](#4-phase-by-phase)
5. [What NOT to trust](#5-what-not-to-trust)
6. [Reusable artifacts](#6-reusable-artifacts)
7. [Running it](#7-running-it)
8. [Repository layout](#8-repository-layout)
9. [Reproducibility pins](#9-reproducibility-pins)
10. [What's left open](#10-whats-left-open)

---

## 1. The question

A growing literature treats *test-time compute* — more sampling, agentic scaffolding, retrieval,
search over partial proof states — as a reliable lever for getting more out of a fixed
theorem-proving model. We asked a narrow, falsifiable version of that claim, in three parts, in the
order they were actually asked:

1. **Does agentic scaffolding help?** Premise retrieval, memory of failed attempts, an LLM reviewer
   step, tactic-skeleton hints, forced approach diversity, smarter *within-problem* budget
   allocation — does any of it buy solves over just sampling more whole-proof attempts at the same
   budget?
2. **If not, why not?** What is actually limiting the model, and does *any* lever move it — more
   search, more compute, fine-tuning, RL?
3. **(Emerged mid-project, became the one positive result)** Does *how a fixed total budget is split
   across a batch of different problems* matter, independent of any change to the model or its
   scaffolding?

### Report `pass@B`, not `pass@k`

Everything is measured against a hardware-independent compute budget `B` = total LLM-generated tokens
per problem, summed across every model call (proposals, refinements, tactic steps). `pass@B` is
reported as a **curve** over 2k/8k/32k/128k tokens, ≥3 seeds, mean ± seed-std. Wall-clock and
GPU-hours are logged but are never the reported axis — they aren't comparable across GPU types.

---

## 2. Setup

- **Two independently-trained provers**, so any shared finding is a property of the class rather than
  of one model: **Goedel-Prover-V2-8B** and **DeepSeek-Prover-V2-7B**.
- **Two benchmarks**: **miniF2F-test** (244 audited problems, competition-style, in-distribution) and
  **ProofNet#** (186 problems, undergraduate, out-of-distribution and ~3–5× harder).
- **Lean is always the authoritative verifier** (official REPL backend). No LLM judge ever gates a
  solve.
- **≥3 seeds** for every headline number; mean ± seed-std.
- **The verifier was audited twice** (2026-06-14, 2026-07-10/16). This matters more than it sounds:
  essentially every claim here is "the model could/couldn't solve X," and that is only as good as the
  thing deciding "solved." See [§5](#5-what-not-to-trust).

---

## 3. Findings

### 3.1 The headline curves

`pass@B`, mean ± seed-std over 3 seeds:

| budget | miniF2F · Goedel | miniF2F · DeepSeek | ProofNet# · Goedel | ProofNet# · DeepSeek |
|--------|------------------|--------------------|--------------------|----------------------|
| 2k   | 29.6% ± 3.3% | 27.9% ± 2.1% | 4.8% ± 1.4% | 5.4% ± 0.5% |
| 8k   | 60.2% ± 1.9% | 57.9% ± 1.7% | 9.3% ± 1.1% | 13.1% ± 0.8% |
| 32k  | 69.7% ± 0.8% | 67.3% ± 0.6% | 12.2% ± 0.3% | 18.3% ± 1.6% |
| 128k | 75.3% ± 1.2% | 73.0% ± 0.4% | 14.9% ± 0.3% | 22.2% ± 1.7% |

*These include the `maxHeartbeats` correction (see [§5.2](#52-corrections-that-were-applied));
before/after per cell is in [`results/audit/HEARTBEAT_CORRECTED_CURVES.md`](results/audit/HEARTBEAT_CORRECTED_CURVES.md),
regenerable with `python scripts/fold_heartbeat_correction.py`.*

miniF2F saturates to a ~73–75% ceiling by 128k; ProofNet# is still climbing from a much lower base.
The asymmetry replicates on both models independently, so it is a property of the task, not of a
model. Note that the cross-model ordering **reverses** between benchmarks: Goedel edges DeepSeek
in-distribution but DeepSeek is clearly better out-of-distribution (+7pp at 128k, gap widening with
budget). That gap is real, not a coverage artifact — both provers attempt identical statement sets
and every statement elaborates on both Lean pins.

**Two caveats on this table.** The 2k column is *attempt-starved*: the median cell completes **zero**
full propose attempts within 2k tokens, so that point measures whether a truncated partial attempt
happened to contain a proof, not whether the model got one fair try. At 8k it is still only 0.68–0.87
attempts. Don't read the budget axis as a `pass@N` axis — see
[`results/phase0/ATTEMPTS_PER_BUDGET_TABLE.md`](results/phase0/ATTEMPTS_PER_BUDGET_TABLE.md) for the
conversion.

### 3.2 An execution floor: nothing we tried at test time moves it

| Intervention | Phase | Result |
|---|---|---|
| Agentic scaffolding (retrieval, memory, reviewer, skeletons, diversity, alloc) | 1 | **Null** one-factor-at-a-time; two components actively *hurt* out-of-distribution (BM25 retrieval: −36 net flips on ProofNet#) |
| Forced approach diversity, on the fully-trapped core | 2 (Step C) | **Null, causally.** Diversity rises 42–70% under a budget-matched manipulation check; solves stay flat; output quality mildly degrades |
| Hammer / SMT closing tactics | 3 | **NO-GO** — portfolio closes 0/119 trapped problems |
| More of the same budget on already-trapped problems | 5 | **~0 new solves** (Goedel 1, DeepSeek 0) |
| Closing-likelihood SFT | 6 A/B | **Null** — surfaces an exposure-bias signature instead of a fix |
| Lightweight post-hoc GRPO RL | 6 C | **Null** (−1.6pp), with a saturated-policy signature: mean KL 0.0021, training reward flat for all 80 steps |
| Verified-state re-grounding | 7 | **Null** in its strongest form, including a matched fresh-resample control |
| Full lab-scale Base→SFT→RL, two lineages | 8 | **WITHDRAWN** — our own audit found a verifier bug that mechanically forces 0% regardless of model quality. We report the bug, not the number. |
| Prompted `sorry`-deferred subgoal decomposition | WS6 | **NO-GO on both models**, 5 rounds. One model stated three correct intermediate facts and still could not *defer* them |

**The mechanism, established causally rather than inferred (Phase 2): approach *discovery* is not the
bottleneck; within-approach *execution depth* is.** That one result explains the entire column above
— any lever that only changes *which* approach gets tried should not be expected to help, and none
did.

**Scope, stated honestly.** This floor is scoped to **frozen whole-proof provers** and to the
interventions we could actually run and trust. Systems that *train* for decomposition are a different
class and none of this is evidence against them. Everything is established at **7–8B**; whether the
floor persists at 32B+ is untested and is the most important question this project leaves open.

### 3.3 The one lever that did move something

Not a model change and not a scaffold change, but a *policy* question: given a fixed total budget,
how should it be split across a batch of *different* problems? A realizable, mechanism-informed
allocation policy — abandon cells a logistic predictor flags as trapped at a decision checkpoint —
saves **~30% of compute at 90% of full-budget accuracy** on Goedel×ProofNet#.

Reported as the strongest lever found, **not** as a settled positive: a paired per-problem bootstrap
CI on that estimate **crosses zero**, and the second model's estimate is weaker and also inconclusive
at 95% even at 8 seeds. See [`results/phase4/ALLOCATION.md`](results/phase4/ALLOCATION.md).

### 3.4 The measurement contribution

Auditing our own harness turned out to be a first-class result. Five structural bugs, each of which
would have shipped a wrong headline in a specific silent direction:

1. A Lean elaboration-**heartbeat** misconfiguration that silently corrupted **17.8%** of miniF2F
   refinement-loop feedback and flipped 13/1212 final verdicts.
2. A **soundness hole** scoring truncated non-proofs as solved.
3. A **wedged-REPL** bug scoring a hung process as success.
4. A phase-specific **`no_goal` gate** mechanically forcing 0% for continuation-style completions —
   this is what withdrew Phase 8, and it was an *emergent interaction between two independently
   correct fixes*.
5. A **Lean-staging concurrency race**.

Plus two gaps that change how any comparable result should be read:

- **pass@budget ≠ pass@N**, and they diverge in a budget-dependent way that is not a fixed offset.
- **A within-run bootstrap CI is not a replication.** We caught this the hard way: a retrieval effect
  whose CI was entirely positive on one run (`[+0.82,+6.15]`pp at 8k) failed to reproduce on an
  independent replication whose own CI (`[−1.78,+3.14]`pp) does not overlap it at all.

Full write-up, with mechanism, blast radius, direction of error, and a "check your own harness" test
for each: **[`results/audit/BUG_CATALOGUE.md`](results/audit/BUG_CATALOGUE.md)**.

---

## 4. Phase by phase

Each row's receipt is the file with the derivation and raw numbers.

| Phase | Question | What ran | Result | Receipt |
|---|---|---|---|---|
| **0** | What does `pass@B` look like? | Baseline sweep, 2 models × 2 benchmarks × 3 seeds × 4 budgets | The curves in §3.1 | [`results/phase0/`](results/phase0/) |
| **1** | Does scaffolding help? | OFAT ablation of 6 components, 3 seeds, both benchmarks, + paired-flip analysis | **Null.** Retrieval's apparent +3.4pp did not replicate (+0.7pp on a second run); paired flips show symmetric churn (+46/−41), not premise injection. On ProofNet#, BM25 retrieval −36 net flips and front-loaded allocation −19 | [`results/phase1/FINDINGS.md`](results/phase1/FINDINGS.md) |
| **2** | *Why* doesn't it help? | Trace mining (F1–F5) + **a causal intervention** (Step C: force diversity on the trapped core, budget-matched manipulation check) | **The mechanism.** Diversity rose 42–70% — the manipulation fired — yet solves stayed at 0–1.2% and quality degraded. Execution depth, not approach discovery | [`results/phase2/MECHANISM.md`](results/phase2/MECHANISM.md) |
| **3** | Do hammer/SMT tactics break it? | Tactic portfolio on trapped problems | **NO-GO**, 0/119 | [`results/phase3/HAMMER_PROBE.md`](results/phase3/HAMMER_PROBE.md) |
| **4** | Does cross-problem allocation matter? | Difficulty predictor + policies + frontier vs. uniform vs. oracle | **The one positive**, honestly caveated (§3.3) | [`results/phase4/ALLOCATION.md`](results/phase4/ALLOCATION.md) |
| **5** | Does more budget help trapped problems? | Extend trapped cells past 128k | **~0 new solves.** Fourth independent confirmation | [`results/phase4/ALLOCATION_MECHANISM.md`](results/phase4/ALLOCATION_MECHANISM.md) |
| **6 A/B** | Does closing-likelihood SFT move it? | SFT on closing steps, two models, 3 seeds/arm | **Null**, and diagnostic: near-zero teacher-forced loss on the closing, yet the model still fails generating its own path there — an exposure-bias signature | [`results/phase6/FINETUNE.md`](results/phase6/FINETUNE.md) |
| **6 C** | Does lightweight post-hoc RL move it? | GRPO probe, pre-registered triple gate | **Null** (−1.6pp). G2/G3 clean: no reward hacking, no KL blow-up, no diversity collapse | [`results/phase6/STAGE_C_RESULT.md`](results/phase6/STAGE_C_RESULT.md) |
| **7** | Does verified-state re-grounding help? | Stepwise/tactic re-grounding + matched fresh-resample control, 3 seeds | **Null.** Mode 3: 5/450 cells vs. control 2/450 — Fisher exact p=0.45. The control is what makes this a null rather than a weak positive | [`results/phase7/STEPWISE.md`](results/phase7/STEPWISE.md) |
| **8** | Does full lab-scale RL move it? | Model zoo, two matched lineages | **WITHDRAWN** — see §5.1 | [`results/phase8/ZOO.md`](results/phase8/ZOO.md) |
| **Audit** | Is any of this trustworthy? | ~30 independent checks, most re-deriving numbers with code importing none of our own analysis | Found the Phase 8 bug and the heartbeat correction. **Independently re-derived Phase 0–5 numbers exactly** | [`results/audit/AUDIT_FINDINGS.md`](results/audit/AUDIT_FINDINGS.md) |

### WS6 — the post-draft strengthening sprint (the last work done)

Six items, all closed 2026-07-26. Every one landed as a *confirmation* — nothing changed a headline,
several claims got materially more precise. That pattern is what closed the analysis track.

- **Equivalence bounds** — replaced "within noise" with paired per-problem bootstrap CIs throughout.
  Sharpened Phase 6 Stage B from "flat" to "null on 3/4 combinations, genuinely harmful on the
  fourth" (Goedel×ProofNet#, −1.97pp, CI `[−3.76,−0.54]` — the weakest base cell, i.e. Stage A's
  mechanism at smaller amplitude).
  [`results/EQUIVALENCE_BOUNDS.md`](results/EQUIVALENCE_BOUNDS.md)
- **Contamination boundary** — is the floor just "where training-set recall ends"? **No.** Trapped
  problems are marginally *more* similar to the training corpus, not less (p=0.049, rank-biserial
  r=−0.17) — the wrong direction for the memorization account. Stated precisely: *no evidence for it,
  weak evidence against*, with two caveats (fragile at n=55 vs 189; TF-IDF is a proxy for one corpus,
  not either model's pretraining mix).
  [`results/phase6/CONTAMINATION_CORRELATION.md`](results/phase6/CONTAMINATION_CORRELATION.md)
- **Decomposition** — neither prover can be *prompted* into an honest `sorry`-deferred decomposition
  on a problem it can't already solve, across 5 rounds and both models. DeepSeek stated three correct
  intermediate facts and still could not defer them: the gap is treating sub-facts as separable
  obligations, not identifying them. **This is what scopes the whole floor claim to *frozen*
  provers.** Closed by its own pre-registered stopping rule at ~2.3 GPU-h.
  [`results/phase_decomp/DESIGN.md`](results/phase_decomp/DESIGN.md)
- **Predictor v2** — richer features for the Phase 4 predictor, seed-holdout guarded. **Negative**
  (+0.033 AUC vs. a pre-registered 0.05 bar). Trapped-ness is not more legible in the generation
  signal than elapsed spend already makes it — a small independent corroboration of the floor.
  [`results/phase4/PREDICTOR_V2_RESULT.md`](results/phase4/PREDICTOR_V2_RESULT.md)
- **Housekeeping** — pass@32 reconciliation (195/244 ≈ 80%); Phase 7 fresh-control to 3 seeds
  (confirms the null); DeepSeek miniF2F trapped-core calibration (clean rate 1/61 after overlap
  correction).

---

## 5. What NOT to trust

Read this before quoting any number from this repo.

### 5.1 Phase 8's headline is WITHDRAWN

The "0.0%-everywhere" result for both matched lineages is retracted and must not be cited. A
`no_goal` gate checked a regex against the *raw completion*, while a separate, independently correct
fix made the backend assemble a theorem wrapper around proofs lacking one. For continuation-style
templates — where the model never restates the theorem, by design — the regex was then structurally
always `None`, so the gate fired on every attempt regardless of proof quality. The harness-sanity
control missed it because that control only covered `whole_proof`-format models, for which the gate
was a no-op. Fixed, with a permanent real-Lean regression test. The thesis does not depend on Phase 8
— seven other phases converge independently.

### 5.2 Corrections that were applied

- **`maxHeartbeats` (applied 2026-09-02).** 13/1212 trapped-core cells had correct proofs rejected by
  Lean's old internal elaboration limit. Folded into §3.1; largest movement +1.0pp, the 2k row
  unchanged, nothing moved down. No qualitative reading changed.
- **The 2k budget point is attempt-starved** — footnote it, don't treat it as a comparable point on
  the same curve as 8k/32k/128k.
- **"miniF2F saturates to a ceiling"** needs two clauses: the curve *near the origin* is
  attempt-starved; the *flat tail* past N≈14 is genuinely unmeasured. Neither implies the other.
- **The failure taxonomy** is accurate as *terminal* failure mode but buries premise errors
  encountered along the way. On ProofNet#: **1.0% terminal** knowledge failures vs. **51.9%
  encountered**. Cite both, never the 1% alone. This weakens the taxonomy-based argument that
  retrieval is doomed; it does *not* reverse the retrieval decision, which rests on Phase 1's direct
  experimental harm of −36 net flips.
- **Phase 1's `budget_alloc__0` OFAT result**, not "20.7% of solves used refinement," is the
  load-bearing reason `alloc_split=0.0` was never run at 128k. The 20.7% figure is an attribution
  share, not a counterfactual.

### 5.3 Standing caveats

- **Phase 4's positive is inconclusive at 95%** — the ~30% saving is a point estimate whose paired
  bootstrap CI crosses zero on both models.
- **"Trapped" is not "unprovable."** Fresh sampling at pass@32 with no budget cap recovers ~11% of
  Goedel×miniF2F's trapped core. Trapped means "this loop, at this budget, did not solve it" — a
  statement about the regime, not the problem.
- **Only Goedel×miniF2F has a dedicated resampling calibration cell.** DeepSeek's cores and
  Goedel×ProofNet# do not — a logged scope limit, not an oversight.
- **Everything is at 7–8B.** 32B is untested; feasibility is scoped (fits via vLLM
  `--tensor-parallel-size 2` on this cluster's dual-l40s nodes, no quantization) in
  [`results/phase_scale32b/FEASIBILITY.md`](results/phase_scale32b/FEASIBILITY.md) and deliberately
  not run.

---

## 6. Reusable artifacts

If you take one thing from this repo, take one of these — each is written to be useful without caring
about our specific model question:

- **[`results/audit/BUG_CATALOGUE.md`](results/audit/BUG_CATALOGUE.md)** — the five harness bugs and
  two measurement gaps, each with mechanism, blast radius, **direction of error**, the regression
  test that locks it, and a concrete "check your own harness" test.
- **[`results/trapped_cores/`](results/trapped_cores/)** — the five trapped-core problem lists (the
  population the floor lives in), with provenance and the caveats that travel with them.
- **[`results/phase0/ATTEMPTS_PER_BUDGET_TABLE.md`](results/phase0/ATTEMPTS_PER_BUDGET_TABLE.md)** —
  the pass@budget → pass@N conversion table.

---

## 7. Running it

```bash
module load anaconda/2023.09
conda activate /insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study/scratch/conda-envs/atp

make verify   # fast suite (~700 tests, ~10s) + ruff. The gate before any commit.
make test     # fast suite only (login-node safe, no GPU/Lean)
make test-all # include slow/gpu/lean markers (run on a GPU node)
make smoke    # tiny 2-5 problem end-to-end sanity, needs an interactive GPU session

# Reproduce a baseline pass@B curve (audited miniF2F test, 3 seeds):
mkdir -p logs results
sbatch slurm/sweep.sh configs/phase0_baseline.yaml baseline   # restartable; resume skips done cells
```

The sweep stages Mathlib oleans to node-local SSD, brings up a vLLM server, runs the agent over the
problem set, and writes per-problem JSON, a `pass@B` curve, and a manifest to `results/baseline/`.
Jobs are restartable by design — the cluster preempts and requeues, and completed
`(config, seed, problem)` cells are skipped on resume.

### Cluster gotchas baked into the harness

Every one of these was learned the hard way; they will silently break anything written from scratch:

- **Slurm jobs inherit a per-session SSH proxy** that breaks every outbound download. `unset
  HTTP_PROXY HTTPS_PROXY http_proxy https_proxy` at the top of every job script. Compute nodes have
  direct internet; the inherited proxy is the problem.
- **Stage Mathlib's ~4.7k oleans to node-local SSD.** Loading from shared GPFS causes an open-storm
  that degrades the whole filesystem.
- **Drive the Lean REPL over a PTY**, with a recursive `LEAN_PATH`.
- **Never pickle the REPL env** — it silently corrupts verdicts on `@[init]` tactic extensions.
- **Force `PATH` after `conda activate`.**
- Every GPU sweep is gated on a probe that must accept a `norm_num` proof and reject a false one, so
  a broken environment fails loudly instead of masquerading as a low pass rate. **Keep that gate.**

Partitions: `short` (≤12h, GPUs) for eval, `burst` (≤14d, preemptible) for sweeps and training.
`--gres=gpu:l40s:1` for inference, `gpu:h100:1` for training. RAM is capped ~6400 MB/CPU, so request
more CPUs rather than a bigger `--mem-per-cpu`. Account: `edu`.

---

## 8. Repository layout

```
src/atp/
├── lean/         # Lean 4 REPL backend, whole-proof verifier, compiler-error parser
├── models/       # vLLM client, budget meter, prompt templates
├── agents/       # propose→verify→refine loop; components/ = the Phase 1 ablation axes;
│                 #   stepwise/tactic_stepwise (Phase 7); decomposition (WS6)
├── alloc/        # Phase 4: features, difficulty predictor, policies, frontier, halving
├── budget/       # token accounting and stopping
├── data/         # miniF2F / ProofNet# loaders, exclusions, contamination + disjointness checks
├── eval/         # pass@B metrics, run manifests, sweep harness, aggregation, plots
└── rl/           # Phase 6 Stage C: GRPO reward, diversity, subset selection

configs/          # one versioned YAML per experiment (+ base + smoke). Pins are load-bearing.
slurm/            # restartable sbatch scripts. Read the gotchas above first.
scripts/          # per-phase analysis and one-off probes, named by phase
results/          # the receipts — see results/README.md
tests/            # mirrors src/ (markers: slow, gpu, lean)
env/              # frozen pip + conda listings for the environment that produced every result
```

**Conventions**, if you continue the work: test-first (`make verify` before anything is "done");
configs, not magic numbers — every experiment is a versioned YAML emitting a `run_manifest.json`;
restartable everything (>20 min ⇒ checkpoint and resume); and **pre-registration** — write the
decision rule and risk list *before* the expensive run. Two probes here were closed early by their
own pre-registered stopping rules (decomposition at ~2.3 GPU-h instead of a full array; predictor v2
on a committed AUC bar), which is that practice doing its job. Worked examples:
[`results/phase_decomp/DESIGN.md`](results/phase_decomp/DESIGN.md),
[`results/phase4/PREDICTOR_V2_DESIGN.md`](results/phase4/PREDICTOR_V2_DESIGN.md).

---

## 9. Reproducibility pins

Runs write a `run_manifest.json` (git SHA, config hash, seed, model revision, mathlib commit, Lean
version, host, GPU type, timestamps). **Caveat on what's actually in this repo:** manifest emission
was added partway through the project, so of the four baselines only `results/baseline/` has one —
the other three predate it. Their provenance is recoverable a different way: every per-problem record
carries a `config_hash` identifying the `configs/` YAML that produced it, and the pins below are
those configs' contents. The remaining ~40 manifests live on the cluster, not here.

The toolchain is pinned exactly, because **Mathlib API drift between releases silently lowers a
prover's pass rate rather than erroring** — a wrong pin invalidates comparisons without failing
loudly.

| Component | Pin |
|---|---|
| Prover A | `Goedel-LM/Goedel-Prover-V2-8B` @ `dfd02e6271a58375dfbf3ece0175277cf6b6a89a` |
| — toolchain | `leanprover/lean4:v4.9.0-rc1` |
| — mathlib4 | `xinhjBrant/mathlib4` @ `2f65ba7f1a9144b20c8e7358513548e317d26de1` — a **custom fork** matched to the prover's training-time API. Not in Mathlib's public cache (`lake exe cache get` returns 0% hits); must be built from source. |
| Prover B | `deepseek-ai/DeepSeek-Prover-V2-7B` @ `a8d9e144` |
| — toolchain | `leanprover/lean4:v4.9.0` |
| — mathlib4 | `leanprover-community/mathlib4` @ `f0957a7575317490107578ebaee9efaf8e62a4ab` (upstream, not a fork) |
| Serving stack | vLLM `0.8.5.post1`, PyTorch `2.6.0+cu124`, transformers `4.51.3` |

The Phase 6/7/8 training lineages (`DeepSeek-Prover-V1.5-{Base,SFT,RL}`, `Goedel-Prover-SFT`) reuse
Prover A's pin, confirmed against each lineage's own `.gitmodules` / `lean-toolchain`. Full package
versions: [`env/`](env/). The Lean toolchain and Mathlib fork are **not** captured there — they live
in `scratch/` and are built from source via `scripts/setup_lean_env.sh`.

---

## 10. What's left open

None of these block anything; all are documented.

| Thread | Status |
|---|---|
| **Scale.** Everything is at 7–8B; whether the floor persists at 32B+ is the most important untested question. Feasibility scoped, deliberately not run. | Open by choice |
| **Phase 4 confirmation on a second model** — the natural next validation if anyone continues. | Open (needs GPU) |
| **The failed-attempt trace corpus** as a released artifact — GB-scale, needs a hosting decision rather than a repo change. | Open |
| **Audit Step 4** — broaden the heartbeat re-verify from the trapped core to near-frontier failures, to check for a similar mid-curve effect. | Flagged, not done |

---

## License

None. This is unreleased academic research code; no license is granted. If you want to use it, ask.
