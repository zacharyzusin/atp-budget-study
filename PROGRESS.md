# PROGRESS.md

Append-only lab notebook. Add a dated entry after every work session and every experiment.
Newest entries at the bottom. Never delete history.

**Entry template:**
```
### YYYY-MM-DD — <short title>
- Did: <what changed / what ran>
- Tests: <pytest result, which markers>
- Numbers: <key metrics, budget, seeds, GPU-hours> (link to results/<...> if applicable)
- Issues: <anything broken / surprising>
- Next: <the single next step>
```

---

### 2026-06-04 — Project bootstrapped from plan
- Did: Received `PROJECT_PLAN.md` + `CLAUDE.md` + seeded `DECISIONS.md`. Repo not yet created.
- Tests: n/a (no code yet).
- Numbers: n/a.
- Issues: none.
- Next: Task 0.1 — create repo layout, `pyproject.toml` (pytest markers slow/gpu/lean), `Makefile`,
  pre-commit/ruff; commit; then Task 0.2 (Lean layer) and pin mathlib/Lean versions in `DECISIONS.md`.

### 2026-06-04 — Task 0.1 complete: repo + memory bootstrap, config loader, green fast suite
- Did: `git init` (branch `main`); built repo layout per §4 (`src/atp/{lean,models,agents,
  agents/components,search,budget,controller,data,eval}`, `tests/`, `slurm/`, `scripts/`,
  `results/`, `checkpoints/`, `logs/`, `scratch/{hf-cache,conda-envs,lean-cache}`). Added
  `.gitignore` (scratch/results/logs/checkpoints + python caches ignored; `.gitkeep`s kept).
  Wrote `src/atp/config.py` (pydantic-v2 typed loader: `defaults: base` deep-merge, `extra=forbid`
  validation, lossless round-trip, `config_hash`, `apply_env`→HF_HOME into scratch), `src/atp/cli.py`
  (no-op `prove`/`sweep` for `make smoke`), and subpackage `__init__`s. Created conda env at
  `scratch/conda-envs/atp` (python 3.11.15); installed LIGHT CORE + dev deps and the package editable
  `--no-deps`. Pinned versions in `pyproject.toml` + `DECISIONS.md`; split heavy GPU/Lean stack into
  `[gpu]`/`[lean]`/`[train]` optional groups (deferred — disk).
- Tests: `make test` (fast suite, `-m "not slow and not gpu and not lean"`) → **26 passed in 0.18s**.
  `make lint` (ruff) clean. `make smoke` runs the no-op pipeline OK (loads+validates config, sets
  HF_HOME, prints config hash).
- Numbers: env footprint 580 MB. No GPU-hours used.
- Issues: **`/insomnia001` is at 100% (only ~20 GB free on the 5 TB shared mount).** Deferred the
  full `torch`+`vllm`+`lean-dojo` install (~10–15 GB) and flagged to the team — need a go-ahead /
  disk cleanup before Task 0.2's Lean build. Light core was enough to get the fast suite green.
- Next: **STOP for check-in** (show tree + pins + test output). Then Task 0.2 — pin exact mathlib
  commit + Lean toolchain in `DECISIONS.md` BEFORE writing the Lean layer; flag both to the team.

### 2026-06-04 — Task 0.2 (Lean layer): pins LOCKED + code + fast tests green; real build deferred
- Did: Researched & **locked the verification env to match Goedel-Prover-V2** (read its `.gitmodules`
  + submodule pointer via GitHub API): Lean `leanprover/lean4:v4.9.0-rc1`, mathlib4 fork
  `xinhjBrant/mathlib4` @ `2f65ba7f1a9144b20c8e7358513548e317d26de1` (2024-08-07). Recorded in
  `DECISIONS.md` + `configs/base.yaml` (added `lean.mathlib_repo`; `LeanCfg` schema updated). Wrote
  `src/atp/lean/`: `errors.py` (parse Lean output → messages; earliest-error by source position;
  fold continuation lines; `find_loopholes` word-boundary; `attribute_failure` → earliest failing
  tactic+step for Phase-2 reward), `backends.py` (`Theorem`, `RawVerification`, `LeanBackend`
  protocol, `ScriptedBackend` for tests/smoke, `LeanDojoBackend` skeleton that lazily imports
  lean-dojo and raises `LeanEnvNotReady`), `verifier.py` (`Verifier`: backend verdict + soundness
  policy → `VerifyResult` with reason ok/compile_error/timeout/loophole + `feedback`).
- Tests: `make test` → **47 passed, 2 deselected in 0.21s**. `make lint` clean. The 2 real-Lean
  tests (`test_verifier_accepts/rejects_known_*`) are `@lean@slow` and **skip cleanly** ("real Lean
  backend deferred (disk hold)"). Verified `import atp.lean` does NOT pull `lean_dojo` (fast suite
  stays login-node safe).
- Numbers: no GPU-hours. Light env still 580 MB.
- Issues: **DISK STILL ON HOLD** — real `lake build` of the pinned mathlib into `scratch/lean-cache`
  + lean-dojo install are deferred until space is freed; the verify path is fully mocked-tested
  meanwhile. Goedel pins a mathlib *fork* (not upstream) — flagged; using the fork for format parity.
- Next: when disk freed → install `[lean]` + `lake build` the pinned mathlib, fill `LeanDojoBackend.
  verify`, flip the 2 skipped lean tests green. Otherwise proceed to Task 0.3 (vLLM client + budget
  meter) which is also mockable without the heavy install.

### 2026-06-04 — Task 0.3 (model client + budget meter): code + fast tests green; disk re-checked
- Did: **Re-checked disk** — `df -h /insomnia001` shows 1.7 PB / 61% used / **~672 TB free**; the prior
  "100% / 20 GB" note was a stale view (logged a superseding `DECISIONS.md` entry). Heavy install is
  not space-blocked, just belongs on a compute node — so proceeded with the mockable Task 0.3. Wrote
  `src/atp/budget/meter.py` (`BudgetMeter`: exact token ledger from server `completion_tokens`;
  `request()` clamps to remaining + raises `BudgetExhausted` cleanly; `spend()`; `snapshot/restore`
  for requeue; `from_config`), `src/atp/models/client.py` (`VLLMClient` + `Transport` Protocol;
  `OpenAITransport` real path uses the `openai` SDK against vLLM `/v1/completions`, imported LAZILY;
  `ScriptedTransport`+`completion_response` for tests; `Completion` with `truncated`), and
  `src/atp/models/templates.py` (`WholeProofTemplate` for Goedel, `TacticTemplate` for BFS-Prover,
  `extract_lean_block` taking the last fenced block, `get_template`/`template_from_config`). Wired
  `budget/__init__.py` + `models/__init__.py` exports.
- Tests: `make test` (env python) → **72 passed, 2 deselected in ~1.9s** (was 47; +25). `ruff check`
  clean. Verified `import atp.models`/`atp.budget` does NOT pull `openai` or `torch` (login-node safe).
  `python -m atp.cli prove --config configs/smoke.yaml` runs the no-op pipeline OK. (`make smoke`
  itself needs `conda activate` first — `make` used system python in this shell; not a code issue.)
- Numbers: no GPU-hours. Light env still ~580 MB. Required Task 0.3 tests present:
  `test_budget_meter_accounting`, `test_budget_exhausted_is_graceful` (+ clamp/snapshot/from_config).
- Issues: none in code. Open: confirm any per-project quota with the team before the heavy
  `[gpu]`/`[lean]` install + `lake build` (do it inside an interactive `srun`, not on a login node).
- Next: **Task 0.4 — minimal agent loop** (`src/atp/agents/`): proposer → verifier (0.2) → refine on
  error → repeat until solved or `BudgetExhausted`; persist state each iter for requeue. All mockable
  with `ScriptedBackend` + `ScriptedTransport`. (Real Lean build + 2 skipped lean tests still pending
  the compute-node install.)

### 2026-06-04 — Task 0.4 (minimal whole-proof agent loop): code + fast tests green
- Did: Wrote `src/atp/agents/state.py` (`AgentState`+`Attempt`: full resumable checkpoint — attempt
  trail, `BudgetMeter` snapshot, stop reason; atomic JSON save via tmp+rename; `load` returns None if
  absent) and `src/atp/agents/whole_proof.py` (`WholeProofAgent`: propose→verify→refine rounds; each
  `_step` does generate+verify+checkpoint and returns solved/no_progress/failed; `BudgetExhausted`
  from the metered client is the clean budget-out path; `max_rounds` safety cap; `from_config` wires
  `agent.refinement.{enabled,max_iters}` + `sample_max_tokens = max_model_len//2`). Resume restores
  the meter from the checkpoint so spend carries over; a finished checkpoint short-circuits (no redo).
  Added `WholeProofTemplate.render_refinement` (prev proof + Lean feedback → corrected proof) and a
  tactic-mode counterpart. Wired `agents/__init__.py` exports.
- Tests: `make test` → **79 passed, 3 deselected in ~2.6s** (+7; was 72). `ruff` clean. `import
  atp.agents` verified NOT to pull openai/torch/lean_dojo (login-node safe). New `tests/test_agents.py`
  drives the full loop with `ScriptedTransport`+`ScriptedBackend`; the scripted server respects the
  meter's clamped `max_tokens` so budget accounting matches production. Covers the three required
  tests: solves-trivial (mocked; real end-to-end is the `lean+gpu+slow` skip), state-resume (solved →
  no new generation; unsolved → carried budget), respects-budget (spend == B exactly, clean stop).
- Numbers: no GPU-hours. Light env ~580 MB.
- Issues: none in code. Real end-to-end solve (`test_agent_solves_trivial`, lean+gpu+slow) still
  deferred behind the vLLM server + `scratch/lean-cache` build (compute-node install).
- Next: **Task 0.5 — data layer** (`src/atp/data/`): loaders for audited miniF2F + ProofNet#,
  known-unprovable exclusion list, contamination/novel-split utility, per-problem provenance. Mockable
  (small fixture manifests) without the heavy install. Then Task 0.6 (eval harness + baseline) — which
  is the first task that genuinely needs the GPU + Lean build, i.e. the natural point to do that
  install inside an `srun` session.

### 2026-06-04 — Lean stack decided (hybrid + Pantograph); Goedel-pin mathlib build kicked off
- Did: Inspected the sibling project `…/theorem-proving-research` (user pointer). It has a working
  Lean stack on this cluster: `elan` at `~/.elan` (toolchains incl. v4.29.0), a **fully-built upstream
  mathlib** (`lean_env/.lake`, 7.3 GB, Lean v4.29.0), **PyPantograph 0.3.15** (persistent REPL), and
  **miniF2F (Lean4 port)** + PutnamBench data. Their toolchains (v4.6/4.22/4.29) DON'T match our pinned
  v4.9.0-rc1, so their build can't be reused for reported numbers. **Decision (per user): HYBRID with a
  hard guardrail** — v4.29.0/Pantograph quarantined to plumbing/CI/smoke; **every reported number
  (from the Phase 0 baseline repro onward) runs on the Goedel pin** (v4.9.0-rc1 + xinhjBrant fork).
  Rationale = measurement validity (mathlib API drift would corrupt pass@B). Recorded as superseding
  entries in DECISIONS.md (+ saved as a cross-session memory).
- Code: **Replaced the LeanDojo skeleton with a real `PantographBackend`** (`src/atp/lean/backends.py`):
  lazy `pantograph` import, persistent `Server` (Mathlib preloaded), `check_compile` → success iff no
  ERROR-severity message; messages reformatted to `name.lean:line:col: sev: text` so the Task-0.2
  `errors.py`/loophole/earliest-step logic is reused unchanged. Filesystem LEAN_PATH (avoids `lake env`
  hang), `project_path` override + reads the env's own `lean-toolchain` so it can target EITHER stack.
  Updated `lean/__init__`, `pyproject` `[lean]` (lean-dojo→pantograph, version must match toolchain),
  and the verifier tests. Added the **version-agnostic contract tests** (`test_contract_accepts_trivial_true`
  / `test_contract_rejects_false`, `lean`+`slow`) — trivial True / `1=2` proofs that must behave the
  same on both stacks; the gate that lets us swap envs with confidence. Point them at any built env via
  `ATP_LEAN_ENV_DIR`; they skip cleanly when none is built.
- Acquisition: `scripts/setup_lean_env.sh` installed toolchain v4.9.0-rc1 + `lake update`d the fork.
  **`lake exe cache get` MISSED** (0% — fork oleans not hosted) → from-source build required. Killed the
  build it started on the LOGIN node; moved it to **`slurm/build_lean.sh`** (CPU-only `short`, 32 cores,
  128G, `--requeue`, incremental-resumable). First submit failed on a bad `-j` flag (this lake has none);
  fixed and **resubmitted as job 10223218** (full Mathlib from source; multi-hour).
- Tests: `make test` → **80 passed, 3 deselected**; ruff clean; imports don't pull pantograph/openai/
  torch/lean_dojo. (3 deselected = 2 lean contract tests + 1 lean+gpu agent end-to-end.)
- Issues: pantograph version must match the target Lean (0.3.15↔v4.29.0; Goedel-pin pantograph TBD when
  first run there). Logged the BFS-Prover-may-need-different-mathlib confound for Phase 1.
- Next: while the mathlib build runs → **Task 0.5 data layer**, reusing the sibling's miniF2F (Lean4)
  statements. When the build finishes → install pantograph for the Goedel env + run the contract tests
  green on it (flip the deferred lean tests).

### 2026-06-04 — Task 0.5 (data layer + audited splits): code + fast tests green; mathlib build still running
- Did: Built `src/atp/data/` — `problems.py` (`Problem`: statement head + imports/opens + provenance +
  flags unprovable/contaminated/novel; `to_theorem()` bridges to the verifier), `minif2f.py` (pure-text
  parser: splits `theorem … := sorry` blocks, strips the proof tail, parses the import/open header
  (flattening `open scoped`), attaches informal JSON, stamps git repo+commit+file+line provenance;
  default source = sibling's miniF2F-lean4 @ d2e847c, overridable via `data.minif2f_dir`),
  `proofnet.py` (JSONL loader; raises until `data.proofnet_dir` is staged), `exclusions.py` +
  `minif2f_exclusions.txt` (data-file-driven known-unprovable list; **validates names against loaded
  problems and reports unmatched** so typos/version-mismatch surface — shipped empty pending the
  AUDITED correction set), `contamination.py` (tag NOVEL, flag the rest CONTAMINATED — public benchmarks
  are training-suspect; novel split is the mitigation), `manifest.py` (`DatasetManifest` for
  run_manifest.json: counts/source/exclusions/model_revision). `__init__.load_dataset(config)`
  orchestrates: load split → flag/drop exclusions → contamination/novel → limit → manifest. Added
  `data.{minif2f_dir,proofnet_dir,exclusions_file}` to `DataCfg`.
- Tests: `make test` → **92 passed, 3 deselected** (+12). ruff clean. `import atp.data` stays light.
  The guarded real-data test confirms the **staged miniF2F = 244 valid / 244 test** with commit
  provenance. Honest caveat baked in: the rahul3613 port (Lean v4.6) may not be the *audited* miniF2F —
  source is config-driven + provenance-stamped so swapping to an audited version is a config change.
- Numbers: no GPU-hours. **Mathlib build (job 10223218) still RUNNING** (~14 min, oleans climbing;
  resumed from the killed login attempt's partial progress) — comfortably inside the 12 h `short` cap.
- Issues: ProofNet# not staged on this cluster (loader fixture-tested, ready when data lands).
- Next: when the build finishes → `pip install pantograph` (version matching v4.9.0-rc1) into the env,
  run the contract tests against the Goedel pin (flip the deferred lean tests green). Then **Task 0.6**
  (eval harness + baseline reproduction) — the first task that needs the GPU (vLLM serve) + the built
  Lean env, and where the Goedel-pin guardrail starts mattering for real numbers.

### 2026-06-04 — Task 0.6 (eval harness + metrics) CODE COMPLETE (mockable parts); awaiting GPU+env for real numbers
- Did: Built `src/atp/eval/` — `records.py` (`ProblemResult` per (problem,seed): records
  `tokens_to_solve` so the whole pass@B curve comes from ONE run at max budget; atomic JSON =
  resume signal), `metrics.py` (`pass_at_b` mean±std over seeds, `tokens_to_first_proof`,
  `effective_accuracy` with reviewer false-accept discount, `summarize`), `manifest.py`
  (`build_run_manifest`: git sha, config hash+dump, model/lean/dataset provenance, host/GPU, timing;
  `REQUIRED_KEYS`), `harness.py` (`run_sweep`: restartable — skips completed cells; proving injected
  as `solve_fn` so it's fully mocked), `plot.py` (pass@B curve, lazy matplotlib), `run.py`
  (`run_eval`: assembles the REAL stack — dataset→vLLM client→Pantograph verifier→WholeProofAgent→
  sweep→metrics→manifest→plot; transport+backend injectable). Added `seed` to `VLLMClient` (vLLM
  sampling seed → reproducible per-seed runs). Wired `atp sweep` CLI (one-command) + `make eval` /
  `make baseline`, and `slurm/vllm_server.sh` + `slurm/sweep.sh` (l40s; sweep brings up vLLM, waits,
  runs the restartable sweep; guards on the Goedel-pin env marker).
- Tests: `make test` → **101 passed, 3 deselected** (+9). ruff clean. `import atp.eval` stays light
  (no matplotlib/openai/pantograph/torch). Includes `test_pass_at_b_metric`, `test_manifest_completeness`,
  a restartable-sweep test, AND `test_run_eval_end_to_end_mocked` — the full production assembly driven
  by `ScriptedTransport`+`ScriptedBackend` over a fixture miniF2F (no GPU/Lean), asserting pass@B==1,
  manifest, and a rendered plot.
- Numbers: no GPU-hours. Mathlib build (job 10223218) ~87% (4050/4652 modules, ~27 min) — finishing soon.
- Issues: real baseline reproduction is **gated** on: build finishing → `pip install pantograph` for the
  Goedel env → pin `config.model.revision` → serve vLLM. Per the guardrail those numbers run on the
  Goedel pin only.
- Next: (when build done) install pantograph + flip the lean contract tests green on the Goedel pin;
  pin the Goedel-Prover-V2-8B revision; `sbatch slurm/sweep.sh configs/phase0_baseline.yaml baseline`
  for the real pass@B curve → log numbers + GPU-hours here. That closes Phase 0.
