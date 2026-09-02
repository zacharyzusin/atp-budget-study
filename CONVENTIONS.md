# Engineering conventions

These are the rules the code in this repository was written under. They are cited by rule number
throughout `src/`, `tests/`, `configs/`, `scripts/`, `slurm/` and `results/`, which is why they are
recorded here rather than left implicit. **The numbering below is the one those citations use.**

> **Project status: complete (closed 2026-09-02). No further experiments are planned.**
> Read [`README.md`](README.md) first — it is the whole record: the question, the findings, the
> caveats, and what is still open.

## The rules

1. **Test-first.** Every module ships with `tests/test_<module>.py` in the same change. `make verify`
   (fast suite + ruff) must be green before anything is "done". Hardware-dependent tests are marked
   `@pytest.mark.{slow,gpu,lean}` so the fast suite runs in seconds on a login node.
   **Run `make verify`, not a bare `pytest`** — and if you add a check, make sure it covers the whole
   output, not part of it. Three separate bugs here survived because a gate only looked at a slice
   (see [`results/audit/BUG_CATALOGUE.md`](results/audit/BUG_CATALOGUE.md)).

2. **Log every session.** *(Historical — this rule shaped the comments you will read.)* Work sessions
   appended dated entries to two lab notebooks: `PROGRESS.md` (what was run and what came back) and
   `DECISIONS.md` (what was decided and why). Roughly 200 comments in this repository cite them by
   date — "see `DECISIONS.md` 2026-07-06" and the like — along with the phase planning documents
   (`PROJECT_PLAN.md`, `PLAN_NEXT.md`, `AUDIT_PLAN.md`, `PHASE2_PLAN.md`, `PHASE3_PLAN.md`) and two
   superseded narrative summaries (`SYNTHESIS.md`, `PROJECT_SUMMARY.md`, `HANDOFF.md`).

   **None of those files are in the working tree.** They were removed at project close, when
   [`README.md`](README.md) took over as the single record and `results/` as the evidence. Treat such
   a citation as a provenance stamp — it says *this decision was recorded on this date*, not *go read
   this file*. If you need the original entry, it is in git history through commit `baa9eb9`:

   ```bash
   git show baa9eb9:DECISIONS.md | less
   ```

3. **All jobs restartable.** The cluster preempts and **requeues from scratch**. Any job >20 min must
   checkpoint to disk and resume cleanly; sweeps must skip already-completed
   `(config, seed, problem)` cells on resume.

4. **Configs, not magic numbers.** Every experiment is driven by a versioned YAML in `configs/` and
   writes a `run_manifest.json` recording git SHA, config hash, seeds, model revision, Lean and
   mathlib versions, hostname and timestamps. The pins are load-bearing — a wrong pin lowers the pass
   rate silently instead of erroring.

5. **Smoke before scale.** Never `sbatch` a sweep before `make smoke` passes in an interactive
   session.

6. **Storage hygiene.** Code and configs in the project directory; conda envs, weights, caches and
   large intermediates in `scratch/`; **nothing large in `$HOME`** (tight quota). Model weights are
   pre-staged into the cache, so sweeps serve offline.

7. **Variance.** ≥3 seeds for any headline number; report mean ± standard deviation across seeds. A
   within-run bootstrap CI is not a replication — see
   [`results/RETRIEVAL_REPLICATION_CI.md`](results/RETRIEVAL_REPLICATION_CI.md) for what that
   distinction cost.

8. **Ask before** deleting checkpoints or launching a GPU job. The project is closed; new compute
   spend is a decision for the owner, not a default.

9. **Pre-register expensive work.** Added mid-project. Write the decision rule and the risk list
   *before* the run, not after seeing the result. Worked examples:
   [`results/phase4/PREDICTOR_V2_DESIGN.md`](results/phase4/PREDICTOR_V2_DESIGN.md),
   [`results/phase_decomp/DESIGN.md`](results/phase_decomp/DESIGN.md).

## Cluster operations (Columbia Insomnia, Slurm)

Environment setup, the cluster gotchas that will silently break new code, and the partition/GPU
guidance are in [`README.md` §4](README.md#4-running-it). The operational commands:

```bash
sbatch slurm/<script>.sh            # submit
squeue --me                         # watch
scancel <job-id>                    # cancel
sacct -j <job-id> --format=JobID,State,Elapsed,MaxRSS,ReqTRES%40   # accounting

# interactive GPU shell
srun --account=edu --partition=short --gres=gpu:l40s:1 -c4 --mem-per-cpu=4gb --time=1:00:00 --pty bash
```

Accounts: `edu` (primary), `free` (preemptible), `zgroup` (PI extras).
