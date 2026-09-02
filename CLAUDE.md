# CLAUDE.md — operating rules for this repo

> **Project status: COMPLETE (closed 2026-09-02). No further experiments are planned.**
> Read [`HANDOFF.md`](HANDOFF.md) first — it is the guided tour of what was done, what was found, and
> what is still open. `PROJECT_PLAN.md` is a **historical** spec, not current state.
>
> The rules below still govern any work in this repo, and rules 1, 2, 4 and 8 are the ones most likely
> to matter to someone picking it up. **Do not launch GPU work without asking** — that is now a
> stronger default than rule 8's original threshold, because the project is closed.

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

The project is finished. Orient in this order:

1. [`HANDOFF.md`](HANDOFF.md) — the guided tour: aim, phase-by-phase index, caveats, open threads.
2. [`README.md`](README.md) — headline findings and how to run things.
3. [`SYNTHESIS.md`](SYNTHESIS.md) — the consolidated narrative, **including its corrections log**,
   which is required reading before quoting any number.
4. `results/*/` — the receipts behind every number cited above.

`PROGRESS.md` and `DECISIONS.md` are the append-only primary sources and win any dispute.

**Before changing anything:** run `make verify` (fast tests + lint) and confirm it is green, so you
know whether a failure is yours. **Before quoting a number:** check `SYNTHESIS.md`'s corrections log
and `HANDOFF.md` §5 — several claims carry caveats and Phase 8's headline is withdrawn.

## Quick commands

- `make test` — fast suite (login-node safe)   · `make test-all` — include slow/gpu/lean
- `make smoke` — 2–5 problem end-to-end sanity   · `make lint` / `make format` — ruff
- `make env` — print the conda activate line for this cluster
