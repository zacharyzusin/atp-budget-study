# atp-budget-study

Budget-bounded agentic theorem proving. We study, under a **fixed small compute budget per problem**,
which LLM+Lean agent design choices actually matter (controlled ablation), then try to beat the best
hand-designed loop with a **learned budget-allocation controller** — using open ~7–8B provers on a
tens-of-GPU Slurm cluster (Columbia Insomnia).

## Read these first
- **`PROJECT_PLAN.md`** — full research plan + phased task list (the authoritative spec).
- **`CLAUDE.md`** — condensed operating rules + cluster cheatsheet (the coding agent reads this).
- **`DECISIONS.md`** / **`PROGRESS.md`** — append-only design log and lab notebook (keep them current).

## Quickstart (on the cluster)
```bash
module load anaconda/2023.09
conda activate /insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study/scratch/conda-envs/atp
make test        # fast suite, login-node safe
make smoke       # tiny end-to-end sanity (interactive GPU session)
# then: serve a model and run the baseline
sbatch slurm/vllm_server.sh
sbatch slurm/sweep.sh        # reads configs/phase0_baseline.yaml or phase1_ablation.yaml
```

## Status
Bootstrapping (Phase 0). See `PROGRESS.md` for the live state.
