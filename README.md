# Budget-Bounded Agentic Theorem Proving

A controlled study of **what actually matters in LLM + Lean proof agents under a fixed, small
per-problem compute budget** — and whether a lightweight *learned budget-allocation controller* can
beat the best hand-designed loop at equal budget. We use only open ~7–8B provers on a
tens-of-GPU academic Slurm cluster (Columbia Insomnia), so every result is reproducible without a
datacenter.

> **Status:** active research, targeting publication. Phase 0 (harness + reproducible baseline) is
> complete and validated end-to-end; the full `pass@B` baseline sweep on audited miniF2F is currently
> running. No headline numbers are claimed here yet — see [`PROGRESS.md`](PROGRESS.md) for the live
> lab notebook and [`DECISIONS.md`](DECISIONS.md) for the design log.

---

## Motivation

Competition-level "prove this formal statement" is largely saturated by frontier systems (miniF2F
~99%), but those systems are 200B+ parameters and spend tens of GPU-days per problem — out of reach
for academic labs. Two facts create an opening:

- **Open 7–8B provers are now strong.** Goedel-Prover-V2-8B is competitive on miniF2F and runnable,
  searchable, and fine-tunable on a single L40S.
- **The cheap-agent regime is under-characterized.** A *basic* loop (LLM emits Lean → compiler
  verifies → feedback → retry) is surprisingly effective, but the literature reports `pass@(thousands)`
  and has not cleanly ablated *which components matter* or mapped the *Pareto frontier under a fixed
  small budget* — the honest, useful axis for everyone without a datacenter.

## The core idea: report `pass@B`, not `pass@k`

Everything is measured against a hardware-independent compute budget.

- **Budget unit `B`** — total LLM-generated tokens allotted per problem, summed across every model
  call (proposals, refinements, tactic steps). Reproducible across GPU types in a way wall-clock is
  not. Wall-clock and GPU-hours are *also* logged, but results are *reported* against `B`.
- **An agent** is any policy that spends `B` as it sees fit: one whole-proof sample, many samples,
  best-first tactic search, refine-on-compiler-error, retrieval, decomposition, etc.
- **Headline metric** — `pass@B` = fraction of problems Lean-verified within budget `B`, reported as
  a **curve** over several budgets (e.g. 2k / 8k / 32k / 128k tokens) with **≥3 seeds (mean ± std)**.
- **Companion metrics** — tokens-to-first-proof (efficiency) and reviewer false-accept rate
  (soundness).

## Research plan

| Phase | Goal | Status |
|-------|------|--------|
| **0 — Harness & baseline** | Tested, restartable harness that proves audited miniF2F with the minimal agent loop and produces a `pass@B` curve with full provenance. | ✅ complete; baseline sweep running |
| **1 — Fixed-budget ablation** | The core empirical contribution. Hold `B` fixed, vary one design axis at a time, map the `pass@B` Pareto frontier. | ⏳ next |
| **2 — Learned controller** | The upside contribution. Replace the best hand-designed allocation policy with a learned controller (state + remaining budget → next action) and beat it at equal `B`. | ⏳ planned |

**Phase 1 ablation axes** (each a composable, independently toggled component): generation mode
(whole-proof sampling vs. best-first tactic search), budget allocation (fresh samples vs. iterative
refinement), cross-attempt memory, reviewer/critic step, premise retrieval (none / BM25 / ReProver),
and inference-time tactic-skeleton priors. The full plan, including the Phase 2 controller design, is
in [`PROJECT_PLAN.md`](PROJECT_PLAN.md).

**Explicitly out of scope:** training a prover from scratch, chasing maximum `pass@k`, and
frontier-scale RL.

## Evaluation protocol

This protocol is part of the contribution and is applied throughout:

- **Fixed budget, as a curve** — always `pass@B`, never `pass@(thousands)`.
- **Audited benchmarks only** — miniF2F-audited (known-unprovable items excluded), ProofNet#, with a
  held-out *novel* split for generalization/contamination probes.
- **Contamination-aware** — the exact served model revision is recorded in every run manifest;
  leakage risk is noted per results file; headline claims lead with the novel split.
- **Soundness** — proofs containing `sorry` / `admit` / `native_decide` loopholes are rejected unless
  explicitly allowed; the reviewer's false-accept rate is a reported metric.
- **Variance** — ≥3 seeds for any headline number, reported as mean ± std.
- **Compute transparency** — GPU-hours and token budget are recorded in every results file.

## System architecture

A persistent **vLLM** server hosts the prover on a GPU node; the agent talks to it over the OpenAI
HTTP API and meters every generated token against the per-problem budget. Verification runs against a
persistent **Lean 4 REPL** (`leanprover-community/repl`, version-matched to the toolchain) with
Mathlib preloaded as a long-lived base environment, so each proof check is ~0.2 s warm. The eval
harness runs `(problem, seed)` cells through a thread pool that shares the vLLM transport and gives
each worker its own Lean REPL; every cell checkpoints to disk so a preempted/requeued job resumes
exactly where it stopped.

```
src/atp/
├── lean/         # Lean 4 REPL backend, whole-proof verifier, compiler-error parser
├── models/       # vLLM client, budget meter, Goedel/BFS prompt templates
├── agents/       # whole-proof propose→verify→refine loop + resumable state
├── budget/       # token-budget accounting and stopping
├── data/         # miniF2F / ProofNet# loaders, exclusions, contamination flags
├── eval/         # pass@B metrics, run manifests, sweep harness, aggregation, plots
├── search/       # (Phase 1) best-first tactic search
└── controller/   # (Phase 2) learned budget-allocation policy
configs/          # one versioned YAML per experiment (+ base + smoke)
slurm/            # versioned, restartable sbatch scripts (vLLM server, sweep, Lean build)
tests/            # pytest, mirrors src/ (markers: slow, gpu, lean)
```

## Reproducibility

Every experiment is driven by a versioned YAML in `configs/` and writes a `run_manifest.json` (git
SHA, config hash, seed, model revision, mathlib commit, Lean version, host, GPU type, timestamps).
The toolchain is pinned exactly, because Mathlib API drift between releases silently invalidates a
prover trained against an older API:

| Component | Pin |
|-----------|-----|
| Prover (primary) | `Goedel-LM/Goedel-Prover-V2-8B` @ `dfd02e6271a58375dfbf3ece0175277cf6b6a89a` |
| Prover (Phase 1 tactic comparator) | `ByteDance-Seed/BFS-Prover-V1-7B` |
| Lean toolchain | `leanprover/lean4:v4.9.0-rc1` |
| Mathlib | `xinhjBrant/mathlib4` @ `2f65ba7f1a9144b20c8e7358513548e317d26de1` (custom fork; built from source) |
| Serving stack | vLLM `0.8.5.post1`, PyTorch `2.6.0+cu124`, transformers `4.51.3` |

> The Mathlib pin is a **custom fork** matched to the prover's training-time API; its oleans are not
> in Mathlib's public cache and must be built from source. Pin rationale and the full
> measurement-validity argument are in [`DECISIONS.md`](DECISIONS.md).

## Getting started (Columbia Insomnia / Slurm)

```bash
module load anaconda/2023.09
conda activate /insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study/scratch/conda-envs/atp

make test     # fast suite — login-node safe, no GPU/Lean (seconds)
make smoke    # tiny end-to-end sanity on an interactive GPU session (2–5 problems)
make lint     # ruff

# Reproduce the Phase-0 baseline pass@B curve (audited miniF2F test, 3 seeds):
mkdir -p logs results
sbatch slurm/sweep.sh configs/phase0_baseline.yaml baseline   # restartable; resume skips done cells
```

The sweep stages Mathlib oleans to node-local SSD, brings up the vLLM server, runs the agent over the
problem set, and writes per-problem JSON, a `pass@B` curve, and a manifest to `results/baseline/`.
Jobs are restartable by design (the cluster preempts and requeues): completed `(config, seed,
problem)` cells are skipped on resume.

### Engineering notes

A few hard-won cluster details are baked into the harness and documented in `DECISIONS.md` /
[`CLAUDE.md`](CLAUDE.md): Slurm jobs inherit a per-session SSH proxy that must be unset before any
download; Mathlib's ~4.7k-olean cold load must be staged to node-local SSD to avoid a shared-GPFS
storm; the Lean REPL must be driven over a PTY with a recursive `LEAN_PATH`; and the REPL env pickle
is *not* used (it silently corrupts verdicts on `@[init]` tactic extensions). The verification probe
gates every GPU sweep on accepting a `norm_num` proof and rejecting a false one, so a broken
environment fails fast instead of masquerading as a low pass rate.

## Repository conventions

- **Test-first.** Every module ships with `tests/test_<module>.py` in the same change; the fast suite
  (`make test`) must be green before any component is "done". Hardware-dependent tests are marked
  `@pytest.mark.{slow,gpu,lean}`.
- **Append-only lab notebook.** [`PROGRESS.md`](PROGRESS.md) (dated session/experiment log) and
  [`DECISIONS.md`](DECISIONS.md) (design decisions + rationale) are updated every session and never
  rewritten.
- **Configs, not magic numbers.** Every experiment is a versioned YAML that emits a run manifest.
- **Restartable everything.** Any job > 20 min checkpoints and resumes cleanly.

## Documentation map

- [`PROJECT_PLAN.md`](PROJECT_PLAN.md) — full research plan and phased task list (authoritative spec).
- [`PROGRESS.md`](PROGRESS.md) — append-only lab notebook (current state, numbers, next steps).
- [`DECISIONS.md`](DECISIONS.md) — append-only design-decision log with rationale.
- [`CLAUDE.md`](CLAUDE.md) — condensed operating rules + cluster cheatsheet.

## License & citation

License: TBD (not yet set). If you use this work, please cite the repository; a paper reference will
be added here on release.
