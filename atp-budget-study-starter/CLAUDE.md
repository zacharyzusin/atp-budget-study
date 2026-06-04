# CLAUDE.md — operating rules for this repo

You are implementing the project specified in `PROJECT_PLAN.md`. Read that file in full once before
coding. This file is the condensed, always-on rule set. When the two conflict, `PROJECT_PLAN.md` wins
and you should flag the conflict.

## The non-negotiables

1. **Test-first.** Every module ships with `tests/test_<module>.py` in the same change. Run
   `pytest -q` (fast suite) before calling any task done. Slow/hardware tests are marked
   `@pytest.mark.slow`, `@pytest.mark.gpu`, `@pytest.mark.lean` so the fast suite runs in seconds on a
   login node. A task is not "done" without passing tests.
2. **Update memory every session.** Append a dated entry to `PROGRESS.md` after every work session and
   every experiment (what you did, pass/fail, key numbers, next step). Append to `DECISIONS.md`
   whenever you make a design choice. Both are append-only — never delete history. This is part of
   "done," like tests.
3. **All jobs restartable.** The cluster preempts and **requeues from scratch**. Any job >20 min must
   checkpoint to disk and resume cleanly. Sweeps must skip already-completed `(config, seed, problem)`
   cells on resume.
4. **Configs, not magic numbers.** Every experiment is driven by a versioned YAML in `configs/` and
   writes a `run_manifest.json` (git SHA, config hash, seed, model revision, mathlib commit, Lean
   version, hostname, GPU type, timestamps).
5. **Smoke before scale.** Never `sbatch` a sweep before `make smoke` passes on a tiny instance in an
   interactive session.
6. **Storage hygiene.** Code/results/checkpoints/configs in the project dir; conda envs, weights,
   caches, big intermediates in `scratch/`; **nothing big in `$HOME`** (tight quota). `mkdir -p logs
   results` before the first `sbatch`.
7. **Variance.** ≥3 seeds for any headline number; report mean ± std.
8. **Ask before** deleting checkpoints or launching >50 GPU-hour sweeps. Otherwise proceed
   autonomously through the task list in `PROJECT_PLAN.md`.

## Cluster cheatsheet (Columbia Insomnia, Slurm)

- **Project root:** `/insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study`
- **Env:** `module load anaconda/2023.09` then activate the env in
  `…/atp-budget-study/scratch/conda-envs/atp`. `module load cuda/12.3` if building CUDA-native deps.
- **Submit:** `sbatch slurm/<script>.sh` · **watch:** `squeue --me` · **cancel:** `scancel <id>` ·
  **accounting:** `sacct -j <id> --format=JobID,State,Elapsed,MaxRSS,ReqTRES%40`
- **Interactive GPU shell:**
  `srun --account=edu --partition=short --gres=gpu:l40s:1 -c4 --mem-per-cpu=4gb --time=1:00:00 --pty bash`
- **Accounts:** `edu` (primary), `free` (preemptible), `zgroup` (PI extras).
- **Partitions:** `short` (≤12h, GPUs), `burst` (≤14d, GPUs, preemptible — for sweeps/training).
- **GPUs:** `--gres=gpu:l40s:1` for **inference/eval**, `--gres=gpu:h100:1` for **training/RL**.
- **RAM:** capped ~6400 MB/CPU → request more CPUs (`-c`), not bigger `--mem-per-cpu`.
- **Network:** compute nodes have outbound access; still cache models/data to `scratch/` to avoid
  re-downloading (set `HF_HOME` into scratch).

## Where to start

Follow `PROJECT_PLAN.md` §12 "First actions": Task 0.1 (repo + memory bootstrap) → 0.2 (Lean layer,
pin mathlib/Lean versions in `DECISIONS.md`) → 0.3 (vLLM + budget meter) → down Phase 0 in order.
Stop and check in after Phase 0 exit criteria before launching the Phase 1 sweep.

## Quick commands

- `make test` — fast suite (login-node safe)   · `make test-all` — include slow/gpu/lean
- `make smoke` — 2–5 problem end-to-end sanity   · `make lint` / `make format` — ruff
- `make env` — print the conda activate line for this cluster
