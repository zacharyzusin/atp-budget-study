# Budget-Bounded Agentic Theorem Proving — Project Plan & Coding-Agent Manual

> ## ⓘ HISTORICAL DOCUMENT — not current state
>
> This is the **original project spec**, written at project start (2026-06-04) as the authoritative
> plan for implementation. It was executed and then substantially revised by what the experiments
> actually found: the "Phase 2 — learned controller" arc described below was superseded by the
> mechanism work and the cross-problem allocation study (the repo's actual Phases 2 and 4), and the
> project ultimately ran through Phase 8 plus an independent audit.
>
> **For current state read [`HANDOFF.md`](HANDOFF.md) and [`README.md`](README.md).** This file is
> kept for the audit trail — it shows what was planned before the evidence came in.

---


> **Audience:** this document is written to be handed to a coding agent (Claude Code) as the
> authoritative spec for implementation, **and** to the human research team as the project plan.
> Read the whole thing once before writing any code.
>
> **One-line thesis:** Under a *fixed, small* compute budget per problem, characterize which
> LLM+Lean agent design choices actually matter (controlled ablation), then beat the best
> hand-designed loop with a lightweight learned budget-allocation controller — using only
> open ~7–8B provers and a tens-of-GPU cluster.

---

## 0. Working agreement for the coding agent (READ FIRST)

These rules are non-negotiable and apply to every task in this project.

1. **Test-first discipline.** No component is "done" until it has unit tests that pass. For each
   module you write, write `tests/test_<module>.py` *in the same change*. Run `pytest -q` before
   declaring any task complete. If a thing talks to Lean or a GPU, write a fast mocked unit test
   **and** a slow integration test marked `@pytest.mark.slow` / `@pytest.mark.gpu` so the fast
   suite stays runnable on a login node in seconds.
2. **Maintain the memory/lab notebook continuously.** Two living files (created in Task 0.1):
   - `PROGRESS.md` — append-only running log. After *every* work session and *every* experiment,
     append a dated entry: what you did, what passed/failed, key numbers, next step. Never delete
     old entries.
   - `DECISIONS.md` — append-only log of design decisions with a one-line rationale each
     (e.g. "Budget unit = generated tokens, not wall-clock, for reproducibility across GPU types").
   Treat updating these as part of "done," like tests.
3. **Everything is restartable.** This cluster preempts and **requeues jobs from scratch**
   (`PreemptMode=REQUEUE`). Any job >20 min must checkpoint progress to disk and resume cleanly
   on restart. Assume any job can die at any time.
4. **Reproducibility.** Every experiment is driven by a versioned YAML config in `configs/` and
   writes a `run_manifest.json` (git SHA, config hash, seed, model revision, mathlib commit,
   Lean version, hostname, GPU type, start/end time). No magic numbers in code — they go in configs.
5. **Smoke before scale.** Never `sbatch` a big sweep before running the same code path on a tiny
   smoke instance (2–5 problems) in an interactive session. There is a `make smoke` target for this.
6. **Storage hygiene (cluster-specific, see §3).** Code/results/checkpoints/conda envs live in the
   project space or `scratch/`, **never** in `$HOME` (home quota is tight). Create `logs/` before
   submitting or `--output` paths fail silently.
7. **Determinism caveat.** LLM sampling and Lean timeouts introduce nondeterminism. Fix seeds
   where possible; where not, record them and report variance (≥3 seeds for headline numbers).
8. **Ask before large irreversible actions** (deleting checkpoints, launching >50 GPU-hour sweeps).
   Otherwise proceed autonomously through the task list.

---

## 1. Research context (why this project, in brief)

The "prove a theorem given its formal statement" task at competition level is largely saturated by
frontier systems (miniF2F ~99%, IMO 2025 gold-equivalent), but those systems are huge (200B+ params)
and spend tens of GPU-days per problem — out of reach for us. Two facts create our opening:

- **Open 7–8B provers are now strong.** Goedel-Prover-V2-8B is competitive on miniF2F; BFS-Prover-V1-7B
  is an open tactic-level model. We can run, search over, and fine-tune these on our cluster.
- **The cheap-agent regime is under-characterized.** Recent work found that a *basic* loop
  (LLM generates Lean → compiler verifies → feedback → retry) is surprisingly effective, but nobody
  has cleanly ablated *which components matter* or studied the *Pareto frontier under a fixed small
  budget*. Frontier papers report pass@(thousands); we report pass@(fixed budget), which is the
  honest and useful axis for everyone without a datacenter.

**Our contributions (target):**
1. A controlled, fixed-budget ablation of agent design choices for formal proving (guaranteed
   empirical contribution).
2. A lightweight **learned budget-allocation controller** that, given proof state + remaining
   budget, chooses the next action (sample more / refine / retrieve / decompose) and beats the best
   hand-designed loop at equal budget (upside contribution).
3. A rigorous, contamination-aware, fixed-budget evaluation protocol on audited benchmarks.

**Out of scope (do not attempt):** training a prover from scratch; chasing max pass@k; frontier-scale
RL. If a task drifts toward these, stop and flag it.

---

## 2. The budget abstraction (the core design idea — get this right)

Everything hinges on a clean, hardware-independent notion of "compute budget per problem." Define:

- **Budget unit `B`:** total number of LLM-generated tokens allotted per problem (generation tokens,
  summed across all model calls — proposals, refinements, tactic steps). This is reproducible across
  GPU types in a way wall-clock is not. Record wall-clock too, but *report* against token budget.
- An **agent** is a policy that spends `B` however it likes: it may draw one whole-proof sample,
  many samples, do best-first tactic search, refine after compiler errors, call retrieval, etc.
- **Headline metric:** `pass@B` = fraction of problems solved (Lean-verified) within budget `B`,
  reported as a curve over several `B` values (e.g. 2k, 8k, 32k, 128k tokens), with ≥3 seeds.
- Also report **effective accuracy** when autoformalization is in the loop (formalize *then* prove),
  and **tokens-to-first-proof** as an efficiency view.

This abstraction is what makes the comparison fair and the paper's framing novel. Implement budget
accounting as a first-class, unit-tested component (Task 1.x).

---

## 3. Cluster specifics — Columbia Insomnia (Slurm) — BAKE THESE IN

**Project root (home base):**
```
/insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study
```
(Create this new project dir. The existing `theorem-proving-research` dir on the same space can be
mined for working Lean/venv setup patterns, but keep this project self-contained.)

**Storage rules:**
- Code/results/checkpoints/configs → project dir above.
- Conda envs, caches, model weights, large intermediates → `…/atp-budget-study/scratch/`.
- **Never** put envs/weights/datasets in `/insomnia001/home/zwz2000` (tight quota).
- Node-local `/local` or `/tmp` for hot temp files during a job; copy results back to project space
  before the job exits (node-local is wiped on job end).

**Environment:**
```bash
module load anaconda/2023.09
module load cuda/12.3          # if building anything CUDA-native
conda create -p /insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study/scratch/conda-envs/atp python=3.11
conda activate /insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study/scratch/conda-envs/atp
```

**Accounts / partitions / GPUs:**
- Accounts: `--account=edu` (primary), `free` (preemptible CPU), `zgroup` (PI, extra nodes if available).
- `short` partition: ≤12 h, GPUs (`h100`, `l40`, `l40s`). Default for GPU work.
- `burst` partition: ≤14 days, GPUs, **preemptible/requeued** — for long sweeps or RL.
- Request GPUs via `--gres=gpu:N` or typed `--gres=gpu:h100:1` / `--gres=gpu:l40s:1`.
  - **Use `l40s` for inference/eval** (cheaper, plentiful); **`h100` for training/RL**.
- Memory cap ~6400 MB/CPU on short/burst — to get more RAM request **more CPUs (`-c`)**, not bigger
  `--mem-per-cpu`.
- All partitions `PreemptMode=REQUEUE` → checkpoint and make jobs restartable (rule 0.3).

**Core Slurm commands:** `sbatch`, `squeue --me`, `scancel <id>`, `sinfo`,
`scontrol show job <id>`, `sacct -j <id> --format=JobID,State,Elapsed,MaxRSS,ReqTRES%40`.
Interactive GPU shell:
```bash
srun --account=edu --partition=short --gres=gpu:l40s:1 -c4 --mem-per-cpu=4gb --time=1:00:00 --pty bash
```

---

## 4. Repository layout (create in Task 0.1)

```
atp-budget-study/
├── README.md
├── PROJECT_PLAN.md            # this file
├── CLAUDE.md                  # condensed operating rules (§0) for the agent, repo-root
├── PROGRESS.md                # append-only lab notebook  (rule 0.2)
├── DECISIONS.md               # append-only decision log  (rule 0.2)
├── Makefile                   # smoke / test / lint / eval targets
├── pyproject.toml             # deps + pytest config (markers: slow, gpu, lean)
├── env/environment.yml
├── src/atp/
│   ├── lean/                  # Lean interaction layer (LeanDojo wrapper, verifier, parsing)
│   ├── models/                # prover model wrappers (vLLM server client, tokenization, budget meter)
│   ├── agents/                # agent loop, components (memory, reviewer, retrieval, refinement)
│   ├── search/                # whole-proof sampling + best-first tactic search
│   ├── budget/                # budget accounting + stopping
│   ├── controller/            # Phase 2 learned controller (policy, features, training)
│   ├── data/                  # benchmark loaders, contamination filters, audited-split handling
│   ├── eval/                  # metrics (pass@B, effective acc), run_manifest, aggregation
│   └── cli.py                 # entrypoints: prove, sweep, train_controller, eval
├── configs/                   # one YAML per experiment + base configs
├── slurm/                     # versioned sbatch scripts (vllm_server.sh, sweep.sh, train.sh, smoke.sh)
├── scripts/                   # one-off utilities (download models, build mathlib cache)
├── tests/                     # pytest; mirrors src/ layout
├── results/                   # metrics json, curves, per-problem logs
├── checkpoints/               # (or scratch/ if large)
└── logs/                      # slurm-%x_%j.out/.err  (create before sbatch!)
```

---

## 5. Tech stack & key dependencies

- **Lean interaction:** [LeanDojo](https://leandojo.org) for programmatic Lean 4 interaction, premise
  data, and proof-state stepping. Pin a specific **mathlib commit** and **Lean toolchain version** in
  `DECISIONS.md` and `run_manifest.json`; mathlib drift is a top time-sink — lock it day one.
- **Base provers (open weights):**
  - `Goedel-LM/Goedel-Prover-V2-8B` — primary whole-proof model.
  - `ByteDance-Seed/BFS-Prover-V1-7B` — tactic-level comparator for the search axis.
- **Inference serving:** vLLM (run as a persistent server on a GPU node; agent talks to it over HTTP).
  This decouples model serving from the agent logic and is essential for budget accounting + throughput.
- **Training (Phase 2):** TRL or a minimal GRPO/DPO loop; LoRA/QLoRA on the 8B to stay within budget.
- **Retrieval:** start with LeanDojo's premise retriever (ReProver-style) / BM25 baseline.
- **Testing/tooling:** pytest, ruff, pre-commit; configs via pydantic or OmegaConf.

> If a dependency needs network access at runtime on compute nodes and the cluster blocks egress,
> pre-download models/data on a login node or via a network-enabled job into `scratch/` and point the
> code at the local path. Record this in `DECISIONS.md`.

---

## 6. Phase 0 — Harness & reproducible baseline (Weeks 1–4)

**Goal:** a tested, restartable harness that can prove miniF2F problems with the minimal agent loop
and reproduce a sane baseline number. This is the foundation everything else stands on.

### Task 0.1 — Repo + memory bootstrap
- Create the repo layout (§4), `pyproject.toml` with pytest markers (`slow`, `gpu`, `lean`),
  `Makefile` (`make test`, `make smoke`, `make lint`), pre-commit (ruff).
- Create `CLAUDE.md` (condensed §0 rules), `PROGRESS.md`, `DECISIONS.md` with their first entries.
- **Tests:** `tests/test_repo_smoke.py` — imports work, config loader round-trips a YAML.
- **Done when:** `pytest -q` green; `make smoke` runs a no-op pipeline.

### Task 0.2 — Lean interaction layer (`src/atp/lean/`)
- Wrap LeanDojo: open a theorem, apply a tactic, run/verify a whole proof, capture compiler
  output, detect success, and parse **the earliest failing tactic + error message** (we need this
  signal in Phase 2). Pin mathlib + Lean versions; build/cache the dependency in `scratch/`.
- **Tests:**
  - `test_verifier_accepts_known_good` (slow/lean): a trivially true theorem with a known proof verifies.
  - `test_verifier_rejects_known_bad`: a wrong proof fails with a parseable error.
  - `test_error_parser`: given canned Lean stderr fixtures, extracts earliest-failing-step + message.
  - Mock the LeanDojo call in fast tests; gate real Lean behind `@pytest.mark.lean`.
- **Done when:** can verify/reject proofs and parse errors deterministically on fixtures.

### Task 0.3 — Model wrapper + budget meter (`src/atp/models/`, `src/atp/budget/`)
- vLLM server client: send prompt, stream/return completion, **count generated tokens** and attribute
  them to the current problem's budget ledger. Budget meter raises `BudgetExhausted` cleanly.
- Prompt templates for Goedel-Prover-V2-8B (whole-proof) and BFS-Prover (tactic) per their model cards.
- **Tests:**
  - `test_budget_meter_accounting`: tokens summed correctly across calls; stops at limit.
  - `test_budget_exhausted_is_graceful`: agent receives a clean signal, no crash, partial state saved.
  - Mock the HTTP server in fast tests.
- **Done when:** a fake "model" driven through N calls accounts tokens exactly and stops at budget.

### Task 0.4 — Minimal agent loop (`src/atp/agents/`)
- Implement: **proposer** (writes whole Lean proof) → **verifier** (Task 0.2) → on failure, feed
  error back into proposer for a **refinement** attempt → repeat until solved or budget exhausted.
- Persist agent state to disk each iteration so a requeued job resumes (rule 0.3).
- **Tests:**
  - `test_agent_solves_trivial` (lean+gpu, slow): solves a trivial theorem end-to-end.
  - `test_agent_state_resume`: kill mid-loop, reload state, continue without redoing solved work.
  - `test_agent_respects_budget`: never exceeds `B`.
- **Done when:** end-to-end solve of an easy miniF2F problem inside budget, resumable.

### Task 0.5 — Data layer + audited splits (`src/atp/data/`)
- Loaders for **miniF2F (audited)**, **ProofNet#** (corrected), and an exclusion list for the
  **known-unprovable** miniF2F items. Store provenance per problem.
- **Contamination utility:** record base-model revision; flag any benchmark items whose proofs/names
  could plausibly be in the model's training corpus; support a held-out "novel" split.
- **Tests:** loaders return expected counts; exclusion list applied; manifest records split + versions.

### Task 0.6 — Eval harness + reproduce baseline (`src/atp/eval/`, `slurm/`)
- Implement `pass@B` curve computation, `run_manifest.json`, per-problem JSON logs, aggregation +
  plot. Implement `slurm/vllm_server.sh` (serve model on a GPU node) and `slurm/sweep.sh`
  (run agent over a problem set, restartable, l40s).
- Run the minimal agent over miniF2F-test at a few budgets; sanity-check the number is in a
  believable range for an 8B whole-proof model (it will be below the headline pass@32 figures because
  our budget is smaller and fixed — that's expected and fine).
- **Tests:** `test_pass_at_b_metric` on synthetic solve/fail records; `test_manifest_completeness`.
- **Done when:** a `results/baseline/` curve + manifest exist and the eval is one command.
- **PROGRESS.md:** log the baseline numbers, GPU-hours used, and any surprises.

**Phase 0 exit criteria:** green fast test suite; one-command restartable eval producing a `pass@B`
curve with manifests; baseline logged in `PROGRESS.md`.

---

## 7. Phase 1 — Controlled fixed-budget ablation (Weeks 5–12)

**Goal:** the core empirical contribution. Hold `B` fixed; vary one design axis at a time; map the
Pareto frontier of `pass@B`. Every axis is a config flag, every run is logged + seeded ×3.

### Ablation axes (each an independent, composable component)
1. **Generation mode:** whole-proof sampling (Goedel) vs. best-first tactic search (BFS-Prover).
   Implement BFS in `src/atp/search/` with length normalization (per BFS-Prover findings).
2. **Budget allocation:** spend `B` on many fresh samples vs. iterative refinement of fewer proofs.
   Sweep the split (e.g. 100/0, 50/50, 0/100).
3. **Memory module:** on/off — carry solved lemmas / past errors as context across attempts.
4. **Reviewer/critic step:** on/off — a second pass that double-checks before accepting (guards
   against degenerate/`sorry`-laden proofs; also measure false-accept rate).
5. **Premise retrieval:** none vs. BM25 vs. ReProver retriever; sweep #premises injected.
6. **Inference-time structural priors:** none vs. a fixed schedule of common tactic skeletons
   (cheap, reported to give large relative gains at equal samples — verify or refute this).

### Tasks
- **1.1** Build the composable component system (`src/atp/agents/components/`) so each axis is a
  toggle/param in YAML. **Tests:** each component has an isolated unit test + a "composes with others"
  test; a config-validation test rejects incompatible combos.
- **1.2** Implement BFS tactic search + length normalization. **Tests:** search expands/orders nodes
  as expected on a toy tree; respects budget; finds a known short proof.
- **1.3** Implement memory, reviewer, retrieval, tactic-skeleton scheduler as components, each tested.
- **1.4** Build the sweep runner: cartesian/【factorial】configs × 3 seeds, each a restartable Slurm
  array job on `burst`/`short` (l40s). Resume skips completed (config, seed, problem) cells.
- **1.5** Run the ablation on audited miniF2F + ProofNet#, novel split included. Produce per-axis
  `pass@B` curves, a main effects table, and an efficiency (tokens-to-first-proof) view.
- **1.6** Analysis: which axes move `pass@B` most at small `B`? Do BFS vs whole-proof cross over as
  `B` grows? Does the reviewer trade pass-rate for soundness? Write findings into `PROGRESS.md` and a
  `results/phase1/FINDINGS.md`.

**Phase 1 exit criteria:** a defensible "what matters under fixed small budget" map with ≥3 seeds,
audited splits, contamination notes, and reproducible configs. This alone is a workshop-paper-sized
result.

---

## 8. Phase 2 — Learned budget-allocation controller (Weeks 13–20)

**Goal:** the upside contribution. Replace the best *hand-designed* allocation policy from Phase 1
with a learned one and beat it at equal `B`.

### Design
- **State features:** current proof-state embedding (from the prover's hidden states or a small
  encoder), remaining budget, recent compiler error type, depth, #open goals, retrieval hit/miss.
- **Action space:** {draw fresh whole-proof sample, refine current best, expand via tactic search,
  call retrieval, decompose into subgoal}. (Keep it small initially.)
- **Reward:** terminal Lean-verified success (sparse) **plus** the dense, sound **earliest-failing-step
  signal** from Task 0.2 for tactic-level credit (closer steps to completion get more credit).
- **Training:** collect trajectories by running Phase 1 agents on a *training* problem set
  (e.g. Lean Workbook / miniF2F-valid — never the test sets). Train the controller with GRPO or DPO
  over state→action with LoRA; keep the prover frozen to stay in budget.

### Tasks
- **2.1** Trajectory collection + serialization from the Phase 1 harness. **Tests:** round-trip
  serialization; reward labels match compiler outcomes; no test-set leakage (assert split membership).
- **2.2** Reward computation (sparse + earliest-failing-step shaping). **Tests:** reward is sound
  (a verified proof always gets max terminal reward; a proof failing at step k credits steps <k).
- **2.3** Controller policy + feature extractor. **Tests:** forward pass shapes; action masking when an
  action is unavailable/over-budget.
- **2.4** Training loop (GRPO/DPO, LoRA, restartable, checkpoint every N steps). **Tests:** a
  `--smoke` training run of a few steps on CPU/1-GPU decreases loss on a toy task; checkpoints resume.
  Run real training on `h100` via `slurm/train.sh`.
- **2.5** Evaluation: controller vs. best Phase 1 hand-designed loop at matched `B`, ≥3 seeds, on
  held-out test splits. Report `pass@B` deltas with variance; ablate the dense reward vs sparse-only.
- **2.6** Analysis + write-up of when/why the controller helps; failure cases; `results/phase2/`.

**Phase 2 exit criteria:** a fair, seeded comparison showing the learned controller's effect (positive
or, honestly reported, null) at equal budget, with the dense-reward ablation.

---

## 9. Evaluation protocol (apply throughout — this is a selling point)

- **Always report against a fixed token budget `B`**, as a curve, not pass@(thousands).
- **Audited benchmarks only:** miniF2F-audited (drop known-unprovable items), ProofNet#. Keep a
  **novel/held-out split** to probe generalization and contamination.
- **Contamination:** record exact model revision; note any leakage risk in every results file; prefer
  the novel split for headline claims.
- **Soundness checks:** reject proofs containing `sorry`/`admit`/`native_decide` loopholes unless
  explicitly allowed; the reviewer's **false-accept rate** is a reported metric, not an afterthought.
- **Variance:** ≥3 seeds for any headline number; report mean ± std.
- **Compute transparency:** every results file records GPU-hours and token budget. The paper's table
  has a "compute" column — that honesty is part of the contribution.

---

## 10. Slurm script templates (versioned in `slurm/`)

**vLLM server (inference node, l40s):**
```bash
#!/bin/bash
#SBATCH --account=edu
#SBATCH --partition=short
#SBATCH --job-name=vllm
#SBATCH --gres=gpu:l40s:1
#SBATCH -c 8
#SBATCH --mem-per-cpu=4gb
#SBATCH --time=12:00:00
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
set -euo pipefail
echo "vLLM up on $(hostname) [$SLURM_JOB_PARTITION] $(date)"; nvidia-smi
module load anaconda/2023.09
conda activate /insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study/scratch/conda-envs/atp
cd /insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study
# write the node:port to a file the sweep job reads
echo "$(hostname):8000" > results/_vllm_endpoint.txt
python -m vllm.entrypoints.openai.api_server \
  --model "$MODEL_PATH" --port 8000 --max-model-len 16384
```

**Restartable sweep (problem set × configs × seeds, array job):**
```bash
#!/bin/bash
#SBATCH --account=edu
#SBATCH --partition=burst          # >12h sweeps; short if <=12h
#SBATCH --job-name=sweep
#SBATCH --gres=gpu:l40s:1
#SBATCH -c 8
#SBATCH --mem-per-cpu=4gb
#SBATCH --time=2-00:00:00
#SBATCH --array=0-31%8             # 32 cells, 8 concurrent
#SBATCH --output=logs/%x_%A_%a.out
#SBATCH --error=logs/%x_%A_%a.err
set -euo pipefail
module load anaconda/2023.09
conda activate /insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study/scratch/conda-envs/atp
cd /insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study
# resume-safe: each (config,seed,problem) cell checks for an existing result and skips if done
python -m atp.cli sweep --array-id "$SLURM_ARRAY_TASK_ID" --config configs/phase1_base.yaml --resume
```

**Training (h100, Phase 2):** copy the above, `--partition=burst`, `--gres=gpu:h100:1`,
checkpoint every N steps to `scratch/checkpoints/`, resume from latest on start.

> Reminder: `mkdir -p logs results` before first submit. To raise RAM, raise `-c`, not `--mem-per-cpu`.

---

## 11. Risks & mitigations

- **Scoop risk (the minimal-agent ablation is only months old):** move fast through Phase 0–1; let the
  *fixed-budget framing* + *learned controller* (Phase 2) be the hard-to-scoop parts.
- **mathlib/Lean version drift:** pin versions day one; cache the build in `scratch/`; record in manifest.
- **Preemption:** every long job restartable + checkpointed; sweeps skip completed cells.
- **Contamination undermining claims:** lead headline claims with the novel/held-out split.
- **Null result in Phase 2:** acceptable and publishable *because* Phase 1 is a standalone contribution;
  report honestly.
- **Budget-unit disputes:** token-budget is the primary axis; also log wall-clock + GPU-hours so
  reviewers can cross-check.

---

## 12. First actions for the coding agent (start here)

1. Do **Task 0.1** (repo + `CLAUDE.md` + `PROGRESS.md` + `DECISIONS.md` + Makefile + pytest markers).
   Commit. Append the first `PROGRESS.md` entry.
2. Do **Task 0.2** (Lean layer) behind mocked fast tests + `@pytest.mark.lean` integration tests;
   pin and record the mathlib/Lean versions in `DECISIONS.md`.
3. Stand up the vLLM server script and confirm an interactive `l40s` session can serve
   Goedel-Prover-V2-8B and return a completion (Task 0.3 plumbing).
4. Proceed down Phase 0 in order. After each task: `pytest -q` green, then update `PROGRESS.md`.

Stop and check in with the team after Phase 0 exit criteria are met, before launching the Phase 1 sweep.
