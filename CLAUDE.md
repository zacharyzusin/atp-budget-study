# CLAUDE.md — operating rules for this repo

> **Project status: COMPLETE (closed 2026-09-02). No further experiments are planned.**
> Read [`README.md`](README.md) first — it is the whole record: the question, the findings, the
> caveats, and what's still open. **Do not launch GPU work without asking.**

## The non-negotiables

1. **Test-first.** Every module ships with `tests/test_<module>.py` in the same change. `make verify`
   (fast suite + ruff) must be green before anything is "done". Hardware-dependent tests are marked
   `@pytest.mark.{slow,gpu,lean}` so the fast suite runs in seconds on a login node.
   **Run `make verify`, not a bare `pytest`** — and if you add a check, make sure it covers the whole
   output, not part of it. Three separate bugs here survived because a gate only looked at a slice
   (see `results/audit/BUG_CATALOGUE.md`).
2. **All jobs restartable.** The cluster preempts and **requeues from scratch**. Any job >20 min must
   checkpoint to disk and resume cleanly; sweeps must skip already-completed
   `(config, seed, problem)` cells on resume.
3. **Configs, not magic numbers.** Every experiment is driven by a versioned YAML in `configs/` and
   writes a `run_manifest.json`. The model/Lean/mathlib pins are load-bearing — a wrong pin lowers
   the pass rate silently instead of erroring.
4. **Smoke before scale.** Never `sbatch` a sweep before `make smoke` passes in an interactive
   session.
5. **Pre-register expensive work.** Write the decision rule and the risk list *before* the run, not
   after seeing the result. Worked examples: `results/phase4/PREDICTOR_V2_DESIGN.md`,
   `results/phase_decomp/DESIGN.md`.
6. **Variance.** ≥3 seeds for any headline number; report mean ± std. A within-run bootstrap CI is
   not a replication.
7. **Storage hygiene.** Code/configs in the project dir; conda envs, weights, caches and big
   intermediates in `scratch/`; **nothing big in `$HOME`** (tight quota). `mkdir -p logs results`
   before the first `sbatch`.
8. **Ask before** deleting checkpoints or launching any GPU job. The project is closed; new compute
   spend is a decision for the owner, not a default.

## Cluster cheatsheet (Columbia Insomnia, Slurm)

- **Project root:** `/insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study`
- **Env:** `module load anaconda/2023.09`, then activate `…/atp-budget-study/scratch/conda-envs/atp`.
  `module load cuda/12.3` if building CUDA-native deps. **Force `PATH` after activating.**
- **Submit:** `sbatch slurm/<script>.sh` · **watch:** `squeue --me` · **cancel:** `scancel <id>` ·
  **accounting:** `sacct -j <id> --format=JobID,State,Elapsed,MaxRSS,ReqTRES%40`
- **Interactive GPU shell:**
  `srun --account=edu --partition=short --gres=gpu:l40s:1 -c4 --mem-per-cpu=4gb --time=1:00:00 --pty bash`
- **Accounts:** `edu` (primary), `free` (preemptible), `zgroup` (PI extras).
- **Partitions:** `short` (≤12h, GPUs) for eval · `burst` (≤14d, GPUs, preemptible) for sweeps/training.
- **GPUs:** `--gres=gpu:l40s:1` for inference/eval · `--gres=gpu:h100:1` for training/RL.
- **RAM:** capped ~6400 MB/CPU → request more CPUs (`-c`), not a bigger `--mem-per-cpu`.

### Four things that will silently break anything written from scratch

1. **Unset the proxy.** Slurm jobs inherit a per-session SSH proxy that breaks every download:
   `unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy` at the top of every job script. Compute
   nodes have direct internet; the inherited proxy is the problem.
2. **Stage Mathlib's ~4.7k oleans to node-local SSD.** Loading from shared GPFS causes an open-storm
   that degrades the filesystem for everyone.
3. **Drive the Lean REPL over a PTY**, with a recursive `LEAN_PATH`. **Never pickle the REPL env** —
   it silently corrupts verdicts on `@[init]` tactic extensions.
4. **Keep the verification probe.** Every GPU sweep is gated on accepting a `norm_num` proof and
   rejecting a false one, so a broken environment fails loudly instead of looking like a low pass
   rate.

## Quick commands

- `make verify` — fast suite + lint (**the gate**) · `make test` — fast suite only
- `make test-all` — include slow/gpu/lean (GPU node) · `make smoke` — 2–5 problem end-to-end sanity
- `make lint` / `make format` — ruff · `make env` — print the conda activate line
