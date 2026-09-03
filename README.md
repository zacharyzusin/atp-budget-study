# Budget-Bounded Agentic Theorem Proving

**At a fixed per-problem token budget, what actually moves the solve rate of a frozen whole-proof
Lean prover?** Two open 7-8B provers, two benchmarks, at least 3 seeds everywhere.

Nine test-time interventions were tested against a plain resampling baseline. All nine were null and
two degraded performance. The contributions are the mechanism that explains the nulls, and five
harness bugs found while auditing the pipeline.

---

## 1. What we measured

Everything is scored against a hardware-independent compute budget `B`: total LLM-generated tokens
per problem, summed across every model call. `pass@B` is reported as a curve over 2k / 8k / 32k /
128k tokens. GPU-hours are logged but never used as the reported axis, as they are not comparable
across GPU types.

- **Two independently trained provers**, so any shared finding is a property of the model class
  rather than a quirk of one model: **Goedel-Prover-V2-8B** and **DeepSeek-Prover-V2-7B**.
- **Two benchmarks**: **miniF2F-test** (244 problems, competition style, in distribution) and
  **ProofNet#** (186 problems, undergraduate level, out of distribution, roughly 3-5x harder).
- **Lean is the sole authority.** Solves are verified by the official Lean REPL; no LLM judge decides
  whether a proof counts.
- **At least 3 seeds** per headline number, reported as mean plus or minus seed standard deviation.

---

## 2. Results

### 2.1 Baseline curves

`pass@B`, mean plus or minus seed standard deviation over 3 seeds:

| budget | miniF2F, Goedel | miniF2F, DeepSeek | ProofNet#, Goedel | ProofNet#, DeepSeek |
|--------|------------------|--------------------|--------------------|----------------------|
| 2k   | 29.6% ± 3.3% | 27.9% ± 2.1% | 4.8% ± 1.4% | 5.4% ± 0.5% |
| 8k   | 60.2% ± 1.9% | 57.9% ± 1.7% | 9.3% ± 1.1% | 13.1% ± 0.8% |
| 32k  | 69.7% ± 0.8% | 67.3% ± 0.6% | 12.2% ± 0.3% | 18.3% ± 1.6% |
| 128k | 75.3% ± 1.2% | 73.0% ± 0.4% | 14.9% ± 0.3% | 22.2% ± 1.7% |

- miniF2F saturates near 73-75% by 128k; ProofNet# is still climbing from a much lower base. Both
  models show the asymmetry independently, indicating a property of the task rather than of one model.
- The cross-model ordering flips between benchmarks: Goedel leads in distribution, DeepSeek leads out
  of it (+7pp at 128k, widening with budget). Both provers attempt identical statement sets, so the
  gap is not a coverage artifact.
- The 2k column is attempt-starved. The median cell completes zero attempts within 2k tokens, so it
  measures whether a truncated fragment happened to contain a proof.

### 2.2 An execution floor that nothing at test time moved

The nine interventions, all null against baseline at matched budget:

- **Scaffolding**: premise retrieval, failed-attempt memory, an LLM reviewer step, tactic-skeleton
  hints, forced approach diversity, within-problem budget allocation
- **Symbolic**: hammer/SMT closing tactics
- **Training**: supervised fine-tuning, reinforcement learning

The experiment that explains why: on the problems every baseline seed fails, we forced the model to
try more varied approaches. Measured diversity rose from 42% to 70%, confirming the manipulation took
effect. Solves stayed flat.

This is a causal result, and it locates the bottleneck. Approach discovery is not the constraint;
carrying one approach through to a finished proof is. Every intervention tested was aimed at helping
the model generate new ideas, so a single mechanism accounts for all nine nulls.

### 2.3 The one lever that moved something

A policy question rather than a model or scaffold change: given a fixed budget across a batch of
problems, how should it be split? Abandoning problems a difficulty predictor flags as likely hopeless
and reallocating that budget saves about 30% of compute at 90% of full-budget accuracy on Goedel with
ProofNet#. Reported as a point estimate; the paired bootstrap CI crosses zero.

### 2.4 Five harness bugs

Auditing the pipeline produced a result in its own right:

- **Elaboration timeout misconfigured.** Silently corrupted 17.8% of one benchmark's refinement
  feedback.
- **Soundness hole.** Truncated non-proofs scored as solved.
- **Hung process scored as success.** Failed cells counted as solves.
- **Gate reading the wrong operand.** Mechanically forced 0% for one class of model output.
- **Staging race condition.**

Two of our own headline results were retracted as a result. None of these bugs are specific to this
codebase. Each is written up with mechanism, blast radius, direction of error, and a regression test
in **[`results/audit/BUG_CATALOGUE.md`](results/audit/BUG_CATALOGUE.md)**, which is relevant to any
LLM-plus-verifier evaluation.

---

## 3. Validity checks

Null results are also what a broken harness produces, so the pipeline was validated against external
published numbers and internal positive controls before any null was trusted.

### 3.1 Positive controls

| Control | Result |
|---|---|
| External calibration | DeepSeek-Prover-V2-7B reproduces its own paper's number to within 0.2pp |
| Sensitivity | Baseline moves 29.6% to 75.3% across the budget sweep, so the metric responds to the variable that should move it |
| Manipulation check | Forced diversity took effect, 42% to 70%. The null came from a treatment that fired |
| Known-good proofs | 37/37 Goedel and 40/40 DeepSeek previously solved cells re-verify as `ok` on the fully patched backend |
| Self-detection | The harness caught two of its own false results; both were withdrawn |

### 3.2 Consistency with published results

| Our result | Published | Verdict |
|---|---|---|
| DeepSeek baseline 73.0% ± 0.4% at 128k | pass@1024 of 73.2% ± 0.5%, ~443 tokens/attempt ([2504.21801](https://arxiv.org/abs/2504.21801)) | Match to 0.2pp |
| Goedel baseline 75.3% at 128k | pass@32 of 84.6% ([2508.03613](https://arxiv.org/abs/2508.03613)) | Explained, see below |
| Retrieval hurts out of distribution | ReProver degrades on its own novel-premises split ([2306.15626](https://arxiv.org/abs/2306.15626)) | Same direction |
| Reviewer step null | Intrinsic self-correction without ground truth is an established null ([2310.01798](https://arxiv.org/abs/2310.01798)) | Replicates |
| Allocation saves ~30% | Difficulty-aware allocation saves up to 4x ([2408.03314](https://arxiv.org/abs/2408.03314)) | Inside range, conservative |
| GRPO probe null, 80 steps | V1.5's RL stage gains +1.2 to +2.3pp on ~4,500 theorems ([2408.08152](https://arxiv.org/abs/2408.08152)) | Expected at our scale |

- **The Goedel gap resolves once budget is converted into attempts.** Goedel is a chain-of-thought
  model, and [`ATTEMPTS_PER_BUDGET_TABLE.md`](results/phase0/ATTEMPTS_PER_BUDGET_TABLE.md) shows a
  128k budget buys it a mean of 1.94 attempts, median 1, which is far closer to pass@2 than pass@32.
  The gap is the pass@B versus pass@N distinction the project is built on.
- **Published scaffolding gains are typically compute-unmatched**, comparing a scaffolded system
  against a cheaper baseline. Holding budget fixed is a stricter comparison, so a null where they
  report a gain is the expected outcome.
- **Both training nulls have a known mechanism.** The GRPO probe's flat KL divergence (0.0021 across
  all 80 steps) matches the documented advantage-collapse mode, where identical rewards within a
  sample group produce zero gradient, reported in 28-45% of training batches. The SFT signature,
  near-zero teacher-forced loss on a step in isolation yet failure when the model reaches that step
  through its own generated prefix, is exposure bias, named in scheduled sampling (Bengio et al.,
  2015) and DAgger (Ross and Bagnell, 2011).

---

## 4. Limitations

- **No compute-unmatched positive control.** Every intervention was run budget-matched. We argue that
  is why they came out null, but never demonstrated that this harness detects a scaffolding gain
  under the conditions where the literature reports one. Re-running one intervention at a
  deliberately unmatched budget is the highest-value remaining check.
- **The operating point is narrow.** At 128k, Goedel gets a mean of 1.94 attempts, so a scaffold
  costing 2x per attempt must nearly double per-attempt success to break even. This follows from
  matching budget rather than being a defect, but "nothing works" should be read as "nothing works at
  a budget buying roughly two attempts."
- **Some interventions are weaker than their published versions.** Our retrieval is untrained BM25
  into a whole-proof prompt, where ReProver uses a trained retriever in a stepwise loop; our hammer
  arm is a lite in-context closer, not a real hammer; our RL probe is far smaller than any published
  RL stage. Those nulls constrain our implementations, not the general techniques.
- **Scale and scope.** Everything is 7-8B parameters; whether the floor persists at larger scale is
  the largest open question. Models trained specifically for decomposition are a different class, and
  none of this is evidence against them.
- **The one positive result is a point estimate**, with a bootstrap CI crossing zero.

---

## 5. Running it

```bash
module load anaconda/2023.09
conda activate /insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study/scratch/conda-envs/atp

make verify   # fast suite (~700 tests, ~10s) + ruff. The gate before any commit.
make test-all # include slow/gpu/lean markers (run on a GPU node)
make smoke    # tiny 2-5 problem end-to-end sanity, needs an interactive GPU session

# Reproduce a baseline pass@B curve (miniF2F test, 3 seeds):
mkdir -p logs results
sbatch slurm/sweep.sh configs/phase0_baseline.yaml baseline
```

The sweep starts a vLLM server, runs the agent over the problem set, and writes per-problem JSON, a
`pass@B` curve, and a manifest to `results/baseline/`. Jobs are restartable: the cluster preempts and
requeues, and completed `(config, seed, problem)` cells are skipped on resume.

Four cluster constraints are baked into the harness. Code that ignores them fails silently:

- `unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy` atop every job script. Slurm jobs inherit a
  per-session SSH proxy that breaks all outbound downloads.
- Stage Mathlib's oleans to node-local SSD. Loading from shared GPFS causes an open storm that
  degrades the filesystem for all users.
- Drive the Lean REPL over a PTY with a recursive `LEAN_PATH`, and never pickle its environment,
  which silently corrupts verdicts. Force `PATH` after `conda activate`.
- Every GPU sweep is gated on a probe that must accept a `norm_num` proof and reject a false one, so
  a broken environment fails loudly rather than presenting as a low pass rate.

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
slurm/            # restartable sbatch scripts. Read the constraints above first.
scripts/          # analysis and one-off probes
results/          # the receipts, see results/README.md
tests/            # mirrors src/ (markers: slow, gpu, lean)
env/              # frozen pip + conda listings for the environment behind every result
```

---

## 7. Reproducibility pins

Runs write a `run_manifest.json` (git SHA, config hash, seed, model revision, mathlib commit, Lean
version, host, GPU type, timestamps). The toolchain is pinned exactly because Mathlib API drift
silently lowers a prover's pass rate instead of raising an error, so a wrong pin invalidates
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

Full package versions are in [`env/`](env/). The Lean toolchain and Mathlib fork live in `scratch/`
and are built from source via `scripts/setup_lean_env.sh`.

---

## License

None. This is unreleased academic research code; no license is granted. If you want to use it, ask.
