# Budget-Bounded Agentic Theorem Proving

**What actually moves the solve rate of a frozen whole-proof Lean prover at a fixed per-problem token
budget?** Two open ~7–8B provers, two benchmarks, ≥3 seeds everywhere, on one academic Slurm cluster.

The short answer: **almost nothing we tried**, and the interesting part is *why* — plus what auditing
our own measurement apparatus turned up along the way.

---

## 1. The question

A growing literature treats *test-time compute* — more sampling, agentic scaffolding, retrieval,
search over partial proof states — as a reliable lever for getting more out of a fixed
theorem-proving model. We asked a narrow, falsifiable version of that claim:

1. **Does agentic scaffolding help?** Premise retrieval, memory of failed attempts, an LLM reviewer
   step, tactic-skeleton hints, forced approach diversity, smarter within-problem budget allocation —
   does any of it buy solves over just sampling more whole-proof attempts at the same budget?
2. **If not, why not?** What is actually limiting the model, and does *any* lever move it — more
   search, more compute, fine-tuning, RL?
3. **Does it matter how a fixed total budget is split across a batch of different problems**,
   independent of any change to the model or its scaffolding?

Everything is measured against a hardware-independent compute budget `B` = total LLM-generated tokens
per problem, summed across every model call. `pass@B` is reported as a curve over 2k/8k/32k/128k
tokens, ≥3 seeds, mean ± seed-std. Wall-clock and GPU-hours are logged but never the reported axis —
they aren't comparable across GPU types.

---

## 2. Setup

- **Two independently-trained provers**, so any shared finding is a property of the class rather than
  of one model: **Goedel-Prover-V2-8B** and **DeepSeek-Prover-V2-7B**.
- **Two benchmarks**: **miniF2F-test** (244 problems, competition-style, in-distribution) and
  **ProofNet#** (186 problems, undergraduate, out-of-distribution and ~3–5× harder).
- **Lean is always the authoritative verifier** (official REPL backend). No LLM judge ever gates a
  solve.
- **≥3 seeds** for every headline number; mean ± seed-std.

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

miniF2F saturates to a ~73–75% ceiling by 128k; ProofNet# is still climbing from a much lower base.
The asymmetry replicates on both models independently, so it's a property of the task, not of a
model. The cross-model ordering also reverses between benchmarks: Goedel edges DeepSeek
in-distribution, but DeepSeek is clearly better out-of-distribution (+7pp at 128k, gap widening with
budget) — both provers attempt identical statement sets, so that gap is real, not a coverage artifact.

The 2k column is attempt-starved: the median cell completes zero full propose attempts within 2k
tokens, so it measures whether a truncated partial attempt happened to contain a proof, not whether
the model got a fair try.

### 3.2 An execution floor: nothing we tried at test time moves it

We ran nine different interventions at test time — retrieval, memory of failed attempts, a reviewer
step, tactic-skeleton hints, forced approach diversity, smarter budget allocation, hammer/SMT closing
tactics, extra fine-tuning, and reinforcement learning. All of them were null against the baseline, and
a couple actively hurt.

The key experiment explaining why: we directly forced the model to try more diverse approaches on the
population of problems every seed of the baseline gets stuck on. Diversity rose sharply (42–70%) under
the manipulation — so the model *did* explore more — but solves stayed flat. That establishes,
causally rather than by correlation, that **approach discovery isn't the bottleneck; carrying one
approach through to a finished proof is.** That single mechanism explains why every intervention aimed
at helping the model think of new ideas failed to help.

This floor is scoped to **frozen whole-proof provers** — systems that *train* for decomposition are a
different class, and this isn't evidence against them. Everything here is at 7–8B; whether the floor
persists at larger scale is untested and is the most important open question.

### 3.3 The one lever that did move something

Not a model change and not a scaffold change, but a policy question: given a fixed total budget, how
should it be split across a batch of different problems? Abandoning cells a difficulty predictor flags
as likely-trapped, and shifting that budget elsewhere, saves **~30% of compute at 90% of full-budget
accuracy** on Goedel×ProofNet#. That's the strongest lever we found — reported honestly as a point
estimate, since a paired bootstrap confidence interval on it still crosses zero.

### 3.4 The measurement contribution

Auditing our own harness turned into a first-class result in its own right. We found five structural
bugs in the verification pipeline — a Lean elaboration-timeout misconfiguration that silently
corrupted 17.8% of one benchmark's refinement feedback, a soundness hole scoring truncated non-proofs
as solved, a hung-process bug scoring failures as success, a gate that mechanically forced 0% for one
class of model output, and a staging race condition — plus two measurement gaps (pass@budget is not
the same axis as pass@N; a single run's confidence interval is not a replication). Full write-up with
mechanism, blast radius, and a regression test for each:
**[`results/audit/BUG_CATALOGUE.md`](results/audit/BUG_CATALOGUE.md)**.

---

## 4. Running it

```bash
module load anaconda/2023.09
conda activate /insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study/scratch/conda-envs/atp

make verify   # fast suite (~700 tests, ~10s) + ruff. The gate before any commit.
make test     # fast suite only (login-node safe, no GPU/Lean)
make test-all # include slow/gpu/lean markers (run on a GPU node)
make smoke    # tiny 2-5 problem end-to-end sanity, needs an interactive GPU session

# Reproduce a baseline pass@B curve (miniF2F test, 3 seeds):
mkdir -p logs results
sbatch slurm/sweep.sh configs/phase0_baseline.yaml baseline   # restartable; resume skips done cells
```

The sweep stages Mathlib oleans to node-local SSD, brings up a vLLM server, runs the agent over the
problem set, and writes per-problem JSON, a `pass@B` curve, and a manifest to `results/baseline/`.
Jobs are restartable — the cluster preempts and requeues, and completed `(config, seed, problem)`
cells are skipped on resume.

### Cluster gotchas baked into the harness

- **Slurm jobs inherit a per-session SSH proxy** that breaks every outbound download. `unset
  HTTP_PROXY HTTPS_PROXY http_proxy https_proxy` at the top of every job script.
- **Stage Mathlib's ~4.7k oleans to node-local SSD.** Loading from shared GPFS causes an open-storm
  that degrades the whole filesystem.
- **Drive the Lean REPL over a PTY**, with a recursive `LEAN_PATH`. Never pickle the REPL env — it
  silently corrupts verdicts.
- **Force `PATH` after `conda activate`.**
- Every GPU sweep is gated on a probe that must accept a `norm_num` proof and reject a false one, so a
  broken environment fails loudly instead of masquerading as a low pass rate.

Partitions: `short` (≤12h, GPUs) for eval, `burst` (≤14d, preemptible) for sweeps and training.
`--gres=gpu:l40s:1` for inference, `gpu:h100:1` for training. Account: `edu`.

---

## 5. Repository layout

```
README.md         # this file
CONVENTIONS.md    # the engineering rules the code was written under, cited by rule number
Makefile          # make verify / test / smoke / lint
pyproject.toml    # package + pinned dependencies + ruff/pytest config

src/atp/
├── lean/         # Lean 4 REPL backend, whole-proof verifier, compiler-error parser
├── models/       # vLLM client, budget meter, prompt templates
├── agents/       # propose→verify→refine loop; components/ = the scaffolding ablation axes
├── alloc/        # cross-problem budget allocation: features, difficulty predictor, policies
├── budget/       # token accounting and stopping
├── data/         # miniF2F / ProofNet# loaders, exclusions, contamination + disjointness checks
├── eval/         # pass@B metrics, run manifests, sweep harness, aggregation, plots
└── rl/           # GRPO reward, diversity, subset selection

configs/          # one versioned YAML per experiment (+ base + smoke). Pins are load-bearing.
slurm/            # restartable sbatch scripts. Read the gotchas above first.
scripts/          # analysis and one-off probes
results/          # the receipts — see results/README.md
tests/            # mirrors src/ (markers: slow, gpu, lean)
env/              # frozen pip + conda listings for the environment that produced every result
```

---

## 6. Reproducibility pins

Runs write a `run_manifest.json` (git SHA, config hash, seed, model revision, mathlib commit, Lean
version, host, GPU type, timestamps). The toolchain is pinned exactly, because Mathlib API drift
between releases silently lowers a prover's pass rate rather than erroring — a wrong pin invalidates
comparisons without failing loudly.

| Component | Pin |
|---|---|
| Prover A | `Goedel-LM/Goedel-Prover-V2-8B` @ `dfd02e6271a58375dfbf3ece0175277cf6b6a89a` |
| — toolchain | `leanprover/lean4:v4.9.0-rc1` |
| — mathlib4 | `xinhjBrant/mathlib4` @ `2f65ba7f1a9144b20c8e7358513548e317d26de1` — a custom fork matched to the prover's training-time API. Not in Mathlib's public cache; must be built from source. |
| Prover B | `deepseek-ai/DeepSeek-Prover-V2-7B` @ `a8d9e144` |
| — toolchain | `leanprover/lean4:v4.9.0` |
| — mathlib4 | `leanprover-community/mathlib4` @ `f0957a7575317490107578ebaee9efaf8e62a4ab` (upstream) |
| Serving stack | vLLM `0.8.5.post1`, PyTorch `2.6.0+cu124`, transformers `4.51.3` |

Full package versions: [`env/`](env/). The Lean toolchain and Mathlib fork are built from source via
`scripts/setup_lean_env.sh`.

---

## License

None. This is unreleased academic research code; no license is granted. If you want to use it, ask.
