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

### 2026-06-05 — Real Lean verification WORKING on the Goedel pin (REPL backend); lean+slow contract tests green
- Did: Mathlib build (job 10223218) **COMPLETED** 2026-06-04 23:21 (4675 oleans, ready marker written).
  Went to flip the deferred lean tests green and hit a wall: **PyPantograph has no release matching the
  Goedel pin** (Lean v4.9.0-rc1) — its oldest tagged toolchain is v4.18.0 (walked every PyPantograph tag's
  `src` submodule → `leanprover/Pantograph` `lean-toolchain`), and the sibling's prebuilt binary is v4.29.0
  (olean format is version-specific → can't load our oleans). **Pivoted the verification backend to
  `leanprover-community/repl`** — already vendored in the mathlib build as the `REPL` package, so it's
  version-matched by construction; built its exe with a 40 s `lake build repl` (depends only on Lean core,
  no Mathlib recompile). It's also the REPL Goedel/DeepSeek's own harnesses use. Wrote `src/atp/lean/repl.py`
  (`ReplBackend` + injectable transport: `SubprocessReplTransport` real / `ScriptedReplTransport` for tests),
  superseding PantographBackend for all reported numbers (Pantograph kept for the v4.29.0 plumbing stack
  only). Updated `slurm/build_lean.sh` (now also `lake build repl`), `pyproject.toml` `[lean]` note,
  `DECISIONS.md` (2 entries), `lean/__init__` exports, and the contract tests (now drive ReplBackend, no
  pantograph importorskip). 
- **Three real bugs found + fixed while bringing the REPL up against the live env (each would have silently
  corrupted every verdict):**
  1. **LEAN_PATH layout**: `compute_lean_path` looked only under `.lake/build/lib/lean`, but v4.9.0-rc1 puts
     oleans in bare `.lake/build/lib` → mathlib missing from LEAN_PATH. Probe both.
  2. **LEAN_PATH recursion** (the nasty one): the olean probe used a NON-recursive `glob("*.olean")`, so
     packages with only nested oleans — **`importGraph` (a mathlib dependency)** and `REPL` — were dropped.
     Missing importGraph makes `import Mathlib` return an **empty env 0 with NO error** (even core `True`/
     `trivial` vanish) in ~0 s — indistinguishable from a loaded env except every proof fails. Fixed with
     `rglob` (stops at first hit; 6→9 LEAN_PATH parts, matching the proven manual build).
  3. **stdout buffering / PTY**: the repl responds with `IO.println` and never flushes; Lean block-buffers
     stdout to a pipe → a persistent pipe driver hangs forever (a trivial command got no pipe response in
     25 s; 1 s over a PTY). Drive it through a **pseudo-terminal** (raw slave; daemon reader thread → queue;
     stderr drained separately) — the same trick pexpect-based harnesses use.
- Tests: `make test` (fast) → **115 passed, 3 deselected** (+14: new `tests/test_lean_repl.py`, incl. the two
  LEAN_PATH-layout regressions and the recursion regression). ruff clean. `import atp.lean.repl` stays
  login-node safe (no pantograph/torch/openai). **REAL `lean+slow` contract tests GREEN for the first time:
  `2 passed in 126s`** (`test_contract_accepts_trivial_true`, `test_contract_rejects_false`) against the
  Goedel pin. End-to-end smoke through `ReplBackend`+`Verifier`: TRUE→ok, `Nat.Prime 7 by decide`→ok (proves
  Mathlib genuinely loaded), `1=2 by rfl`→compile_error, `sorry`→loophole.
- Numbers: **cold Mathlib load ≈ 130–270 s (one-time per process), warm verify ≈ 0.2 s** — the persistent
  REPL amortizes the load exactly as intended (this is the whole reason for a long-lived process). No GPU yet.
- Issues: cold load is GPFS-IO-bound and slow; fine because it's paid once per worker. `make smoke`/sweep
  must run the repl from a context with `~/.elan/bin` on PATH + the env's LEAN_PATH (handled by the backend).
- Next: **the verification half of Phase 0 is DONE.** Remaining for the baseline: pin the Goedel-Prover-V2-8B
  model revision, bring up vLLM on an l40s (`slurm/vllm_server.sh`), then `sbatch slurm/sweep.sh
  configs/phase0_baseline.yaml baseline` for the real pass@B curve → log numbers + GPU-hours. (Wire a sweep
  guard that asserts a non-empty LEAN_PATH / a successful trivial-true probe before spending GPU, so a
  silent env regression can't masquerade as low pass@B.)

## 2026-06-06 — GPFS open-storm defeated by node-local staging; smoke pipeline running
- **Blocker resolved.** The 2026-06-05 "pickle the env to dodge the open-storm" plan failed: cold
  `import Mathlib` kept timing out at the 2700 s ceiling (jobs 10244652 etc.), because (a) you can't
  pickle without one successful cold import, and (b) under GPFS contention even a *sequential* read of
  the 4.2 GB / 4686-olean tree ran at **~3.8 MB/s (19m14s)**; random opens were >45 min.
- **Root-caused the pickle.** Produced one (via local route) — it's **1112 bytes**: a lazy `olean.`
  *index* (module→hash/offset) that mmaps oleans at unpickle. NOT self-contained → a GPFS pickle just
  re-opens all 4.7k oleans. (DECISIONS 2026-06-06.)
- **Fix = stage env to node-local SSD.** Copy the built env to `/local/$USER/atp-lean-env` once per
  node, point `ReplBackend` at it via new `ATP_LEAN_PROJECT` override. Measured on ins071:
  `cp -a` ≈ **10 min** (bounded sequential), then `import Mathlib` from local = **141 s** (vs >2700 s
  GPFS timeout), warm unpickle = **2 s**, verdicts correct (`Nat.Prime 7`→ok, `1=2 by rfl`→
  compile_error, RESULT: PASS via `scripts/make_pickle_local.py`).
- **Code:** `ReplBackend.__init__` honors `ATP_LEAN_PROJECT` (explicit arg still wins);
  `slurm/sweep.sh` stages to local SSD (restart-safe `.staged_ok` + olean-count match) before the
  GPU/probe steps; corrected the misleading pickle docstrings. New test
  `test_lean_project_env_override_points_at_local_stage`. **Fast suite: 118 passed; ruff clean.**
- **Running:** smoke job **10257669** (`sbatch slurm/sweep.sh configs/smoke.yaml smoke`) — first
  end-to-end test of stage→import→vLLM→5-problem pass@B on a fresh GPU node.
- **Next:** confirm smoke green (esp. real fresh-node staging + import time, vLLM up, pass@B writes),
  then `sbatch slurm/sweep.sh configs/phase0_baseline.yaml baseline` for the real curve (≥3 seeds);
  log numbers + GPU-hours.

## 2026-06-06 (cont.) — GPU stack up; chat-format fix; conda-activate & verifier bugs
- **GPU stack pinned & working.** vllm **0.8.5.post1** / torch **2.6.0+cu124** / transformers
  **4.51.3** is the unique sweet spot (l40s driver 550.54.14 = CUDA 12.4 → cu126/cu128/cu130 wheels
  fail "driver too old"; vllm≥0.9 needs torch 2.7+cu126; transformers 5.x breaks vllm 0.8.5). Verified
  cuda.is_available on l40s; vLLM serves Goedel-Prover-V2-8B. (DECISIONS 2026-06-06.)
- **Inference-format fix (smoke 10258932 had pass@4000 = 0/5).** Goedel-V2 is a Qwen3 *reasoning*
  prover; raw `/v1/completions` made it emit prose, not Lean. Switched to `/v1/chat/completions` +
  the official Goedel-V2 prompt (```lean4 + plan suffix) + max_model_len **40960** + budget 32000.
  Confirmed live: the model now emits real ```lean4 proof blocks, extraction works, the propose→refine
  loop runs. (templates.py, client.py, configs/base.yaml.)
- **conda-activate silent-failure ROOT-CAUSED & fixed.** Smoke 10260159 died at the Lean probe with
  `No module named 'atp'`; diag jobs showed why: on some nodes (ins095) `conda activate <prefix>`
  returns **rc=0 but does NOT switch python** (stays base anaconda python) → base python has no atp.
  Node-dependent (ins082 fine). Fix: after `conda activate`, **force** `export PATH="$ATP_ENV/bin:$PATH"`
  (+ CONDA_PREFIX) and verify `python`==env python AND `import atp`, retry ×3, fail-fast BEFORE the
  ~15min stage. Applied to sweep.sh, vllm_server.sh, diag_repl.sh. Also wrap activation in `set +u`
  (conda scripts trip nounset on some nodes).
- **VERIFIER BUG found (smoke 10266928: ran=5, pass@32000 = 0/5).** Every real proof rejected with
  "Proof rejected (no parseable error)" — the Verifier's fallback when `raw.success` is False but no
  Lean error parsed; reachable ONLY via ReplBackend.verify's generic `except` path. **The proofs are
  valid**: a clean CPU-only replay (scripts/diag_repl.py) of the exact `mathd_algebra_182` attempt0
  COMPILES (only `unreachableTactic` warnings), and replaying the smoke's first 12 attempts through one
  ReplBackend.verify() is all-correct (real errors, OK proofs, loophole detected). So the bug manifests
  ONLY live (vLLM + Lean co-resident): degradation starts at **global verify #3** (problem index 1,
  amc12a_2015_p10) and persists. NOT memory (MaxRSS 6.1G/64G, no OOM), NOT wall-timeout (reason was
  compile_error, not timeout) → a non-TimeoutError exception under live timing, most likely
  `_read_response` stream-framing desync (blank-line framing) or REPL process death.
- **In progress:** added per-attempt `raw_output` persistence (whole_proof.py/state.py) + tagged the
  infra exception `REPL_INFRA_ERROR` with child stderr tail (repl.py); running focused 2-problem LIVE
  repro (job 10269064, configs/smoke2.yaml) to capture the exact exception, THEN fix precisely +
  regression test. Fast suite 125 passed. **Baseline NOT launched** — blocked on this fix.
- **Throughput note for baseline:** harness drives vLLM single-stream (~38–42 tok/s = expected l40s
  8B decode). Sequential full baseline (732 cells × 128000 budget) ≈ **340 GPU-h** (> the 50 GPU-h ask
  threshold). Cell-level concurrency (shared vLLM batches; per-thread ReplBackend) → ~20 GPU-h at the
  SAME GPU cost, no effect on results. Decide before launching.

## 2026-06-06 (cont. 2) — SMOKE GREEN: pass@32000 = 3/5; full pipeline correct
- **Verifier bug FIXED** (see DECISIONS 2026-06-06 "REMOVE the REPL env pickle"). Root cause was the
  `unpickleEnvFrom` env crashing the Lean process on `norm_num`'s `@[init]` extension; removed the
  pickle (always fresh `import Mathlib`), strengthened the probe to require a `norm_num` proof, and
  added a verify retry-once-on-crash. Captured the exact crash via per-attempt `raw_output` in a
  2-problem live repro (job 10269064).
- **Decisive smoke (job 10270058, configs/smoke.yaml, 5 problems, seed 0, budget 32000): GREEN.**
  Probe: fresh `import Mathlib` 128s, `true + norm_num accepted, false rejected`. Live verification
  produced REAL compile errors, ZERO `REPL_INFRA_ERROR`/"no parseable error".
  **pass@32000 = 0.600 ± 0.000 (3/5).** Solved (1st attempt each): mathd_algebra_182 (707 tok),
  amc12a_2008_p8 (2326), amc12a_2015_p10 (2681). Unsolved (hard, budget-exhausted): amc12a_2019_p21,
  aime_1984_p5. tokens_to_first_proof median 2326. Elapsed ~1.5h on 1×l40s (stage 981s + import 128s
  + vLLM + eval; single-stream ~40 tok/s).
- **Confirms the whole chain end-to-end:** conda-activate PATH fix + chat-format/40960 inference fix +
  pickle-removal/norm_num fix all working together. Phase-0 smoke criterion MET.
- **Next (BLOCKED on a decision):** the real baseline. Sequential it is ~340 GPU-h (732 cells ×
  128000 budget at single-stream ~40 tok/s) — over the 50 GPU-h ask threshold. Need to choose:
  (a) add cell-level concurrency (shared vLLM batches; per-thread ReplBackend) → ~20 GPU-h, same GPU
  cost, no effect on results; (b) reduce scope (e.g. cap budget at 32000, fewer seeds); (c) shard via
  array jobs (more GPUs). Recommend (a). Asking the user before launching.

## 2026-06-06 (cont. 3) — cell-level concurrency implemented + validated; baseline launched
- **Implemented cell-level concurrency** (user-approved over scope-reduction/array-sharding). The
  harness runs (problem,seed) cells through a `ThreadPoolExecutor(eval.n_workers)`; one shared vLLM
  transport batches the concurrent requests; each worker thread gets its OWN `ReplBackend` (Lean REPL
  subprocess) via a thread-local factory in `build_solve_fn` (amortizes its `import Mathlib`), cleaned
  up via `close_backends()`. `eval.n_workers` config field (default 1 = sequential, safe for
  tests/smoke). Resume still loads finished cells serially; results deterministically ordered.
  sweep.sh bumped to 16 CPU / 110 GB for 8 Lean procs + vLLM. New tests: concurrent-runs-all-cells
  (asserts real overlap), concurrent-resume. Fast suite 128 passed, ruff clean.
- **Concurrency smoke (job 10272321, configs/smoke_concurrent.yaml, n_workers=4): GREEN.**
  pass@32000 = 0.600 (3/5) — IDENTICAL to the sequential smoke (same 3 solved: mathd_algebra_182,
  amc12a_2008_p8, amc12a_2015_p10); REPL_INFRA_ERROR count = 0. **Elapsed 19m01s vs ~90m sequential
  (~4.7x)** at n_workers=4. Confirms correctness preserved + real throughput gain + per-thread REPL
  correctness + concurrent Mathlib imports OK.
- **Baseline LAUNCHED:** `sbatch slurm/sweep.sh configs/phase0_baseline.yaml baseline` — miniF2F test
  split, 3 seeds [0,1,2], budgets [2000,8000,32000,128000], n_workers=8. Restartable (requeues skip
  done cells). Will log pass@B curve + GPU-hours when complete.

### 2026-06-07 — Baseline mid-run cost projection (corrected)
- Job 10272937 healthy at 9.3h: **162/732 cells, 126 solved, 0 REPL_INFRA_ERROR**. Startup paid
  once: stage 1014s, import 137s, probe green (true + norm_num accepted, false rejected), vLLM up.
- Throughput (last-30-cells): **14.6 cells/h** (avg-so-far 18.5/h; the easy head is exhausted).
  5.8M tokens spent so far; **22% of cells (36/162) burn the full 128k budget** — these dominate cost.
  Median tokens_to_solve on solved cells = 2628.
- **Projection: ~570 cells remaining → ~39h more wall (~3–4 requeues) → ~48–50 total GPU-h** on one
  L40s. This is ~2x the "~20–30 GPU-h" estimate the concurrency choice was approved on; the gap is
  the full-budget tail, not infra. User said **continue** (2026-06-07) → run to completion, full
  3-seed curve. Restartable; requeues skip done cells. Will log final pass@B + actual GPU-h on finish.

### 2026-06-07 — Baseline 10272937 CRASHED at 165/732 (masqueraded as COMPLETED); hardened + resubmitted
- **Failure:** job 10272937 exited 0 / sacct COMPLETED / log said "[sweep] done" — but `metrics.json`
  was MISSING and only 165/732 cells existed. Root cause in `.err`: a single
  `openai.APITimeoutError: Request timed out` propagated through `ThreadPoolExecutor.map` (re-raises
  the first worker exception) → killed the whole `run_sweep` before it wrote metrics. Two defects:
  (1) **no per-cell isolation** — one transient timeout aborts the run; (2) **bash masked it** —
  `set -uo pipefail` (no -e) let the crashed `python … sweep` fall through to the success echo + exit 0,
  so Slurm logged COMPLETED. The 600s transport timeout was the trigger: one request = up to
  max_model_len//2 = 20480 tok; at ~6-15 tok/s per stream under 8-way concurrency that's 30-45 min > 600s.
- **Fixes (all unit-tested, ruff clean, bash -n OK):**
  - `harness.py`: `_run_cell` now catches every exception, logs `CELL FAILED`, returns None (NO cell
    file written → retried on next resume). Sweep finishes + writes metrics regardless. New manifest
    field `n_failed`. Tests: `test_one_cell_failure_does_not_abort_sweep`, `test_failed_cell_is_retried_on_resume`.
  - `config.py` ModelCfg: `request_timeout_s=3600` (safe ceiling > worst-case generation) + `request_max_retries=4`.
  - `client.py` `OpenAITransport`: accept `timeout_s`/`max_retries`; `run.py` wires them from config.
  - `sweep.sh`: capture sweep exit code → FATAL+exit on non-zero; also FATAL if metrics.json missing
    after a clean exit. No more silent COMPLETED-on-crash.
- **Resubmitted:** job 10304768 (`configs/phase0_baseline.yaml baseline`, --resume). Skips the 165
  saved cells, continues to 732. Dataset confirmed 244 problems × 3 seeds = 732 cells.

### 2026-06-07 — Context-window overflow (contained); fixed client-side clamp
- Job 10304768 (hardened sweep) running healthy; at ~177 cells the new containment caught its first
  real failure: `imo_2019_p1 seed=0` → `openai.BadRequestError 400`: requested 20710 (prompt) + 20480
  (completion) = 41190 > 40960 context. **Sweep kept running** (containment working as designed).
- Cause: the agent requests a fixed `max_model_len//2 = 20480` completion regardless of prompt length;
  long *refinement* prompts (theorem + failed proof + Lean error) push prompt+completion past the
  window. Deterministic, so that cell would fail every resume → never complete.
- Fix (client-side, unit-tested): `VLLMClient._complete_fitting_context` catches the context-length
  400 (the 400 is returned BEFORE generation, so the retry is ~free), parses window + prompt tokens
  from the message, sets `max_tokens = window - prompt - margin` (also capped by the original budgeted
  request), retries once. If room < `context_min_completion` (256) it re-raises → cell recorded failed.
  New ModelCfg-independent client fields `context_margin_tokens=32`, `context_min_completion=256`.
  Tests: test_context_overflow_is_clamped_and_retried / _respects_budget_cap / _no_room_left_reraises /
  _non_context_error_propagates_unchanged. Full fast suite green, ruff clean.
- **Not cancelling 10304768** (failure rate ~0.6%): cancel would lose in-flight cells + re-stage. Failed
  cells write no file, so the end-of-run resubmit (carrying this fix) retries exactly them; any Slurm
  requeue also auto-loads the fixed code. Will resubmit to mop up if n_failed>0 at completion.

### 2026-06-08 — Baseline status check + empty-checkpoint resume bug fixed
- **Baseline still running, healthy.** Job 10304768 (the hardened resume) hit the 12h Slurm TIMEOUT
  at 2026-06-08T02:57 (165→further cells, killed mid-run); manually requeued as **job 10347059**
  (ins057), started 15:00, ~6.5h in at check time. Startup green: staged 4686 oleans (586s), import
  Mathlib + first verify 64s, probe OK (true + norm_num accepted, false rejected), vLLM up. Actively
  writing cells (now on seed-2 problems). **527/732 cells done (~72%)**, ~205 remaining. 0
  REPL_INFRA_ERROR. Raw per-cell tally: 408/527 solved (NOT the pass@B curve — that's metrics.json at
  completion). At ~14-15 cells/h this 12h window will TIMEOUT again ~03:00 → ≥1 more manual requeue
  to reach 732.
- **BUG FOUND: empty-checkpoint deterministic resume failure.** The 10304768 TIMEOUT kill left **38
  zero-byte agent_state JSON files**. On resume `AgentState.load` did `json.loads("")` →
  `JSONDecodeError: Expecting value: line 1 column 1`. Of the 38, 28 belong to already-completed cells
  (resume skips them via the problems/ cell, harmless); **10 are genuinely stuck** (empty state + no
  problems/ cell) and showed up as the 10 `CELL FAILED` lines in sweep-10347059.out — all seed=1
  (aime_1983_p3, aime_1984_p7, amc12_2001_p21, amc12a_2002_p13, amc12a_2019_p12, imo_2019_p1,
  amc12a_2021_p8, amc12a_2021_p12, mathd_algebra_362, amc12a_2002_p13, numbertheory_3pow..., amc12a_2019_p12).
  Containment held (sweep didn't crash) but these would fail EVERY requeue forever — same
  deterministic-failure class as the earlier context-overflow bug. (Atomic tmp+rename in save() can't
  prevent a 0-byte file from a kill *before* the first save.)
- **FIX (user-approved "harden load + test now"):** `AgentState.load` now treats an empty/whitespace
  OR unparseable checkpoint as "no state → start fresh" (returns None) instead of raising. So the next
  requeue auto-mops-up the 10 stuck cells with no manual file surgery. Two regression tests added
  (test_load_empty_checkpoint_returns_none, test_load_corrupt_checkpoint_returns_none). Fast suite
  green (137 passed, exit 0), ruff clean. NOTE: not committed/deployed to the running job — the fix
  takes effect on the NEXT requeue (Slurm requeue reloads code) or a fresh resubmit.
- **Next:** let 10347059 finish its pass; on its TIMEOUT, requeue (now carries the load fix → 10 stuck
  cells start fresh and complete). When n_failed==0 and 732/732 done, read metrics.json for the real
  3-seed pass@B curve + actual GPU-h.

### 2026-06-10 — Phase 0 baseline COMPLETE (732/732, n_failed=0)
- Did: Final requeue **job 10403513** (ins038) ran COMPLETED 2026-06-09 19:24, elapsed 7h32m. The
  empty/corrupt-checkpoint `AgentState.load` fix worked: the 10 previously-stuck seed-1 cells started
  fresh and finished. This pass ran=109, skipped=623 → full coverage.
- Tests: n/a this session (load fix + regression tests landed previous session; carried in via git_sha
  77795e1).
- Numbers: **732/732 cells, n_failed=0, 0 REPL_INFRA_ERROR.** 3-seed pass@B (seeds 0,1,2; 244 problems):
  - pass@2000   = 0.296 ± 0.033
  - pass@8000   = 0.601 ± 0.019
  - pass@32000  = 0.695 ± 0.006
  - pass@128000 = 0.749 ± 0.009   (= effective_accuracy @128k)
  tokens_to_first_proof: median 2534, mean 8266 (n_solved=548). Curve steep 2k→8k (+30pp), flat after
  32k (+5.4pp for 4× budget). results/baseline/{metrics.json,run_manifest.json,pass_at_b.png}.
  Config = whole_proof + refinement(max_iters=4, alloc_split=0.5); all OTHER agent components
  (memory/retrieval/reviewer/tactic_skeletons) DISABLED — this is the true no-frills baseline.
- Issues: none. Clean run, deterministic-failure bug classes all contained/fixed.
- Next: Phase 0 baseline pass@B curve is the reference. Next sweeps = turn on agent components one at a
  time (refinement-only already in baseline; retrieval/reviewer/tactic_skeletons) to measure marginal
  lift vs baseline at matched budget.

### 2026-06-10 — Phase 1 kickoff: component framework + tactic-skeletons (Task 1.1 + first 1.3 slice)
- Did: Built the composable component framework (`src/atp/agents/components/base.py`:
  `Component`, `PromptContext`, `ComponentPipeline`; `__init__.py`: `build_components(config)`) and
  the **tactic-skeletons** component (`skeletons.py`) — the first Phase 1 ablation axis. Wired the
  pipeline into `WholeProofAgent` (`from_config` builds it; `_search` threads propose/refine prompts
  through `decorate_prompt`). Empty pipeline = no-op = byte-identical baseline (so Phase 0 pass@B
  stays the valid reference). User chose tactic-skeletons as the first axis; sweep held for approval.
- Tests: new `tests/test_components.py` — 11 tests (framework no-op/compose, skeletons
  propose-only + schedule cycling + bad-schedule raises, build_components wiring, and two
  agent-integration tests incl. baseline-carries-no-hint). Full fast suite green (148 passed,
  was 137), ruff clean. No GPU/Lean touched.
- Numbers: n/a (no run this session).
- Issues: none.
- Next: continue Phase 1 component implementation per plan order — BFS tactic search (1.2) and the
  remaining 1.3 components (memory, reviewer, retrieval), each test-first. THEN check in before the
  GPU ablation sweep (1.4–1.5), which is gated on team sign-off (PROJECT_PLAN §12). Tactic-skeletons
  is ready to include in that sweep when it runs.

### 2026-06-10 — Phase 1 cont.: memory component + discovered the BFS stepping-layer fork
- Did: Implemented the **memory** component (`src/atp/agents/components/memory.py`) — second Phase 1
  axis. Within-problem, prompt-side: summarises recent failed attempts into fresh proposals as a
  "don't repeat" block (propose-only; round 0 is a no-op). Threaded read-only attempt history into
  `PromptContext` (new `history` field, default empty → backward-compatible); agent passes
  `tuple(state.attempts)`. Added `MemoryCfg.max_items` (default 3) + base.yaml. Wired into
  `build_components` with fixed order memory→skeletons.
- Tests: +6 in `tests/test_components.py` (no-op without failures, summarise propose-only,
  max_items cap = most recent, build order, agent-integration recall across rounds). Full fast
  suite green (**154 passed**, was 148), ruff clean. No GPU/Lean.
- Numbers: n/a (no run).
- Issues / decision: **BFS (Task 1.2) is not a drop-in** — the Lean backend is whole-proof only
  (no proofState/tactic stepping). Real tactic-level BFS needs a REPL stepping layer first
  (separable Lean-infra subsystem). Logged as a fork in DECISIONS.md; did NOT build it unprompted.
- Next: get a steer on the BFS fork (build the stepping layer now vs. finish the cheaper
  prompt-/accept-side axes first: reviewer, retrieval). Whichever — still test-first, and the GPU
  ablation sweep stays gated on team sign-off (PROJECT_PLAN §12). Skeletons + memory ready for it.

### 2026-06-10 — Phase 1 cont.: reviewer/critic component (3rd axis) + false-accept metric
- Did: Implemented the **reviewer** component (`src/atp/agents/components/reviewer.py`) and its
  framework hook (`Component.review` / `ComponentPipeline.review` / `ReviewVerdict` in base.py).
  Semantics pinned (DECISIONS.md): critic runs ONLY on Lean-rejected candidates → Lean stays
  authoritative, a solve is never blocked, false-accept rate is exactly accepts/reviewed. Wired into
  the agent: `_step` consults the critic on failures (budget-metered, new "budget" return value if it
  exhausts mid-step), records `Attempt.review_accept`/`review_critique`, and `_search` threads the
  critique into the refinement prompt. Added `ReviewerCfg.max_tokens` (256) + base.yaml.
  Eval: `ProblemResult.{n_reviewed,n_review_false_accept}` + `metrics.reviewer_false_accept_rate`
  (surfaced in metrics.json only when the reviewer ran).
- Tests: +12 in `tests/test_components.py` (verdict parsing incl. ambiguous→reject; critic calls
  model + spends budget + respects max_tokens; prompt-only components have no review opinion;
  build_components wiring; end-to-end false-accept recorded + critique reaches refinement + metric
  =1.0; metric None without reviewer). Full fast suite green (**166 passed**, was 154), ruff clean.
  Backward-compatible: new Attempt/ProblemResult fields all default → old baseline checkpoints load.
- Numbers: n/a (no run).
- Issues: none.
- Next: **retrieval** (last cheap axis: BM25 premise injection; ReProver backend deferred — needs an
  index). Then the BFS stepping-layer decision. GPU ablation sweep still gated on team sign-off.
  Built so far and sweep-ready: tactic-skeletons, memory, reviewer.

### 2026-06-10 — Phase 1 cont.: retrieval component (4th axis, BM25 baseline)
- Did: Implemented the **retrieval** component (`src/atp/agents/components/retrieval.py`): BM25
  (rank-bm25, already a dep) over a premise-corpus JSONL (`RetrievalCfg.corpus`), injecting top-k
  library lemmas into fresh proposals (propose-only). `_BM25Index` + `load_premises` + `Premise`.
  ReProver backend deferred (raises). bm25-without-corpus raises at build (fail fast). Added
  `RetrievalCfg.corpus` + k≥1 validation + base.yaml. Wired into build_components; fixed pipeline
  order retrieval→memory→skeletons→reviewer.
- Tests: +7 in `tests/test_components.py` (load_premises parse/skip-blank/empty-raises; BM25 ranks
  the additive goal's add_comm above mul_comm; propose-only; reprover deferred; bm25 requires corpus;
  build order retrieval-first). Full fast suite green (**173 passed**, was 166), ruff clean. No
  GPU/Lean — tested with a tiny temp corpus.
- Numbers: n/a (no run).
- Issues / prerequisite: the retrieval sweep arm needs a real **premise corpus** (a Mathlib
  declaration dump → JSONL). Not built yet; `scripts/build_premise_corpus.py` is the follow-up data
  task. The other three axes need no such artifact.
- Next: all CPU/prompt-side + accept-side Phase 1 axes are now built (skeletons, memory, reviewer,
  retrieval). Remaining: BFS (1.2, blocked on the REPL proof-state stepping layer) + the retrieval
  corpus data task. Decision point for the team: (a) build the premise corpus + BFS stepping layer,
  or (b) run the fixed-budget ablation sweep now over the 4 ready axes (3 need no new data; retrieval
  waits on the corpus). GPU ablation sweep still gated on team sign-off (PROJECT_PLAN §12).

### 2026-06-10 — Phase 1 cont.: built the Mathlib premise corpus (unblocks retrieval sweep arm)
- Did: Wrote the premise-corpus parser (`src/atp/data/premises.py`: strip_comments / extract_premises
  with namespace-stack qualification + multi-line signature capture / build_corpus) and the CLI
  (`scripts/build_premise_corpus.py`). Ran it over all 4361 pinned-Mathlib source files →
  **148,727 premises** at `scratch/premises/mathlib_2f65ba7f.jsonl` (24 MB, +.meta.json provenance),
  in 18s. Verified end-to-end: BM25 index builds in 2.1s, ~250ms/query; retrieval returns the exact
  lemma for concept-named goals (Real.cos_sq_add_sin_sq for the trig identity; spot-on gcd hits),
  weak for bare algebra (expected lexical limitation). Wired the corpus path into
  phase1_ablation.yaml's bm25 retrieval cell (reprover cell commented out — deferred).
- Tests: +7 in `tests/test_premises.py` (comment stripping incl. nested/docstring; namespace-not-
  section qualification; multi-line signature join; attributes/modifiers; anonymous-instance skip;
  dedup; file limit). Full fast suite green (**180 passed**, was 173), ruff clean (src+tests).
- Numbers: corpus = 148,727 premises; index 2.1s; query ~250ms. No GPU.
- Issues: none.
- Next: ALL FOUR Phase 1 axes are now sweep-ready with no missing data (skeletons, memory, reviewer,
  retrieval+corpus). Remaining builds: BFS (1.2, REPL stepping layer) and ReProver retrieval (trained
  index) — both deferred. Open decision: prep+launch the fixed-budget ablation sweep over the 4 ready
  axes (Task 1.4 sweep-runner axis-expansion may need a check first), vs. build BFS next. GPU sweep
  still gated on team sign-off (PROJECT_PLAN §12).

### 2026-06-10 — Phase 1: built the ablation sweep machinery (Task 1.4) — sweep is launch-ready
- Did: Discovered Task 1.4 was never built — the CLI `sweep` ran a SINGLE config; `phase1_ablation.yaml`'s
  `sweep.axes` had no consumer (the baseline only ever exercised one cell). Built it:
  `src/atp/eval/ablation.py` (expand_ablation → OFAT cells, hash-dedup, validate_cells pre-flight,
  ablation_manifest) + `atp ablation` CLI (--list / --check / --cell-id N → run_eval into
  results/<run>/<cell>/, writes ablation_cells.json). Added correctness guards so an unimplemented
  `mode=bfs` cell can't silently run as whole-proof (agent raises; --check flags it); commented the
  bfs variant out of phase1_ablation.yaml (deferred, like reprover).
- Tests: +13 in `tests/test_ablation.py` (baseline-first; OFAT differs-only-in-axis; hash-dedup;
  retrieval cell carries corpus; invalid-override + bfs-mode + retrieval-without-corpus all raise with
  cell name; manifest; CLI --list/--cell-id; **the shipped phase1 config passes --check end-to-end**,
  which loads the real 148k corpus to validate the BM25 cell). Full fast suite green (**193 passed**,
  was 180), ruff clean. No GPU/Lean.
- Numbers: phase1_ablation.yaml → **7 runnable cells**: baseline, budget_alloc__0 (0.0) /__2 (1.0),
  memory__1, reviewer__1, retrieval__1 (bm25+corpus), tactic_skeletons__1. `atp ablation --check`
  passes; `--list` shows all 7 with distinct hashes.
- Issues: none.
- Next: the ONLY thing between here and the ablation sweep is `slurm/ablation.sh` — an array wrapper
  (array-id→--cell-id) reusing sweep.sh's hardening (proxy/conda/Lean-staging/norm_num probe/vLLM).
  Untestable off-cluster + GPU-gated, so deferred to its own step (smoke 1 cell first). After that:
  team sign-off → launch the fixed-budget ablation (PROJECT_PLAN §12 gate). Then BFS (1.2) + ReProver.

### 2026-06-10 — Phase 1: ablation Slurm array wrapper — sweep is one `sbatch` from launch (gated)
- Did: Wrote `slurm/ablation.sh` (array wrapper: array-id→cell, per-task vLLM port+endpoint file,
  flock-guarded node-local Lean staging, range-guard skip, norm_num probe, loud failure). Added the
  `ATP_VLLM_ENDPOINT_FILE` override (`run.resolve_endpoint_file`) so co-located array tasks don't read
  each other's vLLM. sweep.sh left untouched (duplicated the hardening, not refactored — lower risk to
  the green baseline path). Both scripts `bash -n` clean.
- Tests: +1 (`test_resolve_endpoint_file_honors_env_override`). Full fast suite green (**194 passed**,
  was 193), ruff clean.
- Numbers: n/a (no run — launch is GPU-gated).
- Issues: none. Scripts are untestable off-cluster, so smoke ONE cell (small data.limit on an
  interactive l40s, or `--array=0-0`) before the full 7-cell array.
- Next: TEAM SIGN-OFF → launch the fixed-budget ablation: `sbatch slurm/ablation.sh` (7 cells:
  baseline + budget_alloc 0.0/1.0 + memory + reviewer + retrieval(bm25) + tactic_skeletons), ≥3 seeds,
  results/phase1_ablation/<cell>/metrics.json each. Then analysis (per-axis pass@B vs baseline +
  reviewer false-accept) → results/phase1/FINDINGS.md (Task 1.6). Deferred: BFS (1.2), ReProver.

### 2026-06-10 — Phase 1: ablation smoke config ready to fire (pre-flight green)
- Did: Added `configs/phase1_ablation_smoke.yaml` — the same 7-cell ablation axes on tiny data
  (split=valid, limit=3, seeds=[0], budget=[32000], n_workers=2) to validate the end-to-end machinery
  on GPU+Lean before the full sweep. `atp ablation --list` → 7 cells; `--check` passes (loads the real
  148k corpus to validate the BM25 cell). Header documents the fire commands.
- Tests: +1 (`test_smoke_config_is_tiny_and_same_shape_as_phase1`). Full fast suite green (**197
  passed**, was 194), ruff clean.
- Numbers: n/a (no run — GPU-gated).
- Fire commands (interactive l40s or sbatch):
    atp ablation --config configs/phase1_ablation_smoke.yaml --check          # pre-flight, no GPU
    sbatch --array=0-0 slurm/ablation.sh configs/phase1_ablation_smoke.yaml phase1_smoke  # baseline cell only
    sbatch            slurm/ablation.sh configs/phase1_ablation_smoke.yaml phase1_smoke   # all 7 cells
- Next: TEAM fires the smoke (1 cell) → confirm a real metrics.json under results/phase1_smoke/baseline/.
  Then sign-off → full sweep: `sbatch slurm/ablation.sh` (configs/phase1_ablation.yaml). Then Task 1.6
  analysis (per-axis pass@B vs baseline + reviewer false-accept) → results/phase1/FINDINGS.md.

### 2026-06-10 — Phase 1: fixed-budget OFAT ablation COMPLETE (job 10436909)
- Did: Ran the full 7-cell ablation (`slurm/ablation.sh configs/phase1_ablation.yaml`). All 7 array
  tasks COMPLETED, ~3.8h each, two waves on `%4`. No timeouts/requeues. Every cell **n_cells=732/732**
  (244 problems × 3 seeds, n_failed=0). Concurrency fixes held under real co-location (tasks 0&1 shared
  ins056 → distinct ports 8000/8001 + flock-shared Lean staging, no collision).
- Numbers (pass@8000, ±seed std; baseline seed std=3.3pp = the noise band):
    baseline            60.1 ± 3.3%   (ref)
    retrieval (BM25)    63.5 ± 1.9%   +3.4pp  ← ONLY mover; also tightens variance
    tactic_skeletons    61.1 ± 2.3%   +1.0pp  (borderline, within noise)
    budget_alloc 0.0    60.7 ± 1.8%   +0.5pp  | 1.0  60.5 ± 0.9%  +0.4pp  (flat across full range)
    memory              60.5 ± 3.1%   +0.4pp
    reviewer            60.4 ± 2.3%   +0.3pp
  Reviewer false-accept (consulted only on Lean-rejected → every accept is a false-accept):
    **17/249 = 6.8%** → LLM critic is NOT a reliable verifier; Lean stays authoritative (design validated).
- Analysis written: `results/phase1/FINDINGS.md` (Task 1.6 DONE).
- Issues: none. (Earlier-caught config bugs n_workers 1→8 and use_novel_split true→false were fixed
  pre-launch; this run was clean.)
- Next: PROMOTE retrieval — rerun BM25 across budgets (2k / 32k) to see if +3.4pp holds/grows/shrinks
  with B, and build the best-combo cell around it. Deprioritize memory/reviewer/budget_alloc as
  standalone levers at this budget. Deferred still: BFS (1.2, needs REPL stepping), ReProver backend.

### 2026-06-11 — Novel-split CLI plumbing (wait-window task while job 10461442 runs)
- Did: Wired the held-out novel split end-to-end (the data layer already accepted `novel_names`, but
  nothing fed it). Added `data.novel_names_file` (config field, newline- or JSON-list of held-out
  problem names, resolved relative to project.root) + `load_novel_names(config)` loader in
  `data/contamination.py` (skips blanks/`#` comments, de-dups, raises on missing-but-configured or
  empty-after-parse). Threaded it through `run_eval` at a single DRY point — explicit `novel_names`
  (tests) win, else fall back to the config file — so `atp sweep` / `atp ablation` / Slurm all pick it
  up with no per-call-site plumbing. Updated base.yaml (+field) and the stale "not wired into the CLI
  yet" comments in phase1_ablation.yaml.
- Tests: +10 (9 in test_data.py: newline/json/none/relative-path/missing/empty/bad-json/load_dataset
  composition; 1 in test_eval.py: `run_eval` restricts to the held-out split from the config file
  alone, n_ran 6→3, manifest split="novel"). Full fast suite **210 passed, 1 skipped**, ruff clean.
- Numbers: n/a (no run). Note: still need a genuinely held-out problem set to populate the file —
  miniF2F-test has novel=0. This unblocks that follow-up; it doesn't create the held-out set.
- Next: cross-budget retrieval job 10461442 (baseline+retrieval @ 2k/8k/32k) still running; completion
  watcher armed → append the 2k/8k/32k retrieval table to results/phase1/FINDINGS.md when it lands.

## 2026-06-11 — Cross-budget retrieval rerun: the +3.4pp did NOT replicate
- Did: ran baseline vs retrieval (BM25 k=8) metered to 32k → whole [2k/8k/32k] curve in one campaign
  (job 10461442; retrieval cell timed out 10 seed2-tail problems short of 732, resume job 10481853
  finished them — resume-safe). Both cells 732/732, n_failed=0.
- Numbers: within-campaign retrieval Δ = **+2.2pp @2k, +0.7pp @8k, −0.8pp @32k** (baseline 0.303/0.594/
  0.701; retrieval 0.325/0.601/0.693). Phase 1's **+3.4pp @8k did NOT replicate** (+0.7pp here). Both
  are valid within-campaign comparisons; the gap is run-to-run vLLM variance (separate processes aren't
  bitwise-reproducible; per-seed std ~1.5–3pp, n=3). NB confirmed in code: meter limits to max(values)
  and WholeProofAgent ignores the ceiling (`alloc_split` is never read), so an 8k point is a valid 8k
  measurement within its run — just not bitwise-equal across runs (my earlier "reproduces exactly" was
  too strong: in expectation, not bitwise).
- Key evidence: paired flip analysis — gains≈losses at every B (+47/−31, +46/−41, +20/−26). Symmetric
  churn ⇒ BM25 context perturbs generation more than it injects usable premises; net sign is just which
  way the noise leaned. As B grows, losses overtake gains (baseline already gets the easy ones).
- Decision: retrieval is NOT a robust lever; do NOT anchor a best-combo cell on it (see DECISIONS).
  Revised conclusion appended to results/phase1/FINDINGS.md (supersedes its earlier "promote retrieval"
  takeaway). Methodology bar raised: a single ~3pp OFAT delta at n=3 is noise — need more seeds or
  paired/within-run analysis; by that bar no Phase 1 component cleared noise.
- Next: re-prioritize behind (a) generation-mode BFS (Task 1.2, needs REPL proof-state stepping) and
  (b) a genuinely held-out novel split (plumbing landed; still need the held-out problem set). BM25
  retrieval parked; only revisit with a relevance filter / smaller k or the ReProver neural backend.

## 2026-06-11 — Pivot to ProofNet# (2nd benchmark); found+fixed a latent REPL verification bug
- Decision: pursue a second audited benchmark (ProofNet#) over the BFS build — validate-premise
  (search<Pass@1 prior + saturating baseline curve argue against the large BFS build now); ProofNet#
  is foundational (generalization + contamination probe) and reuses existing infra. (DECISIONS.)
- Did: staged ProofNet# (PAug/ProofNetSharp, 186 test / 185 valid) via scripts/build_proofnet_sharp.py
  -> scratch/proofnet/{test,valid}.jsonl (prefixed-unique names — bare lean names collide 19x across
  textbooks; per-row opens parsed; trailing ":=" stripped). Added a CPU-only compile-gate
  (scripts/validate_statements.py + slurm/validate_statements.sh): compile "<head> := by sorry", a
  bad head -> error, run BEFORE GPU (a bench whose heads don't elaborate is silently all-zeros).
- Gate caught a REAL bug: first pass 168/186 (90.3%), 18 fail "expected token", ALL on 𝓝/𝓟 filter
  notation (Rudin/Shakarchi/Pugh/Munkres analysis). Diagnosis (3 diag jobs): NOT my flattening
  (verbatim headers fail too), NOT a homoglyph (mathlib registers 𝓝 = U+1D4DD, ProofNet uses
  U+1D4DD), NOT the env (∫ U+222B parses, ascii parses). Root cause: REPL transport used
  json.dumps default ensure_ascii=True -> astral-plane (>U+FFFF) chars sent as a UTF-16 surrogate
  pair (𝓝 -> 𝓝) that Lean's JSON reader mangles. BMP escapes (∫ -> ∫) round-trip, so
  only astral notation bit. Fix: ensure_ascii=False (native UTF-8) in src/atp/lean/repl.py
  (extracted _encode_command + regression test). Re-gate: **186/186 (100%)**.
- Impact on prior results: LATENT, never triggered on miniF2F — scanned results/baseline (1466 json,
  244x3 + attempts): 0 contain any astral char (competition math doesn't use 𝓝). Phase 0 + Phase 1
  miniF2F numbers STAND, no re-run needed. (The fix is still a correctness win for any future astral
  notation in model proofs, on every benchmark.)
- Tests: +3 (encode-command astral regression; gate tally + first-error). Fast suite green, ruff clean.
  Pushed @ 0852dac (staging+gate) and 5e31745 (astral fix).
- Next: ProofNet# baseline pass@B (job below) — the generalization number + a 2nd-benchmark check on
  the "Phase 1 components are noise" conclusion.

## 2026-06-12 — ProofNet# baseline hit the 12h wall at 78/558; capped ceiling 128k->32k, resumed
- Ran ProofNet# baseline (job 10511630, configs/proofnet_baseline.yaml, [2k/8k/32k/128k], 3 seeds).
  Env/probe/staging all clean (Lean probe OK, vLLM up, refinement loop confirmed feeding Lean errors
  back as corrected-proof prompts). But it completed only **78/558 cells in the full 12h wall**
  (sacct TIMEOUT 11:55:13). Measured throughput ~7 cells/h.
- Root cause = ProofNet# is MUCH harder for the prover than miniF2F. The model rarely solves these
  undergrad-math problems, so nearly every cell goes unsolved and burns the FULL 128k ceiling (vs
  miniF2F where ~75% stop early via stop_on_first_success). Finishing all 558 at 128k would take
  ~76 GPU-h / ~6 more requeues — over the CLAUDE.md >50 GPU-h ask-first line, and wasteful given
  miniF2F's 32k->128k tier is nearly flat (+5pp).
- Decision: cap the budget ceiling 128k -> 32k (configs/proofnet_baseline.yaml). ~1/4 the per-cell
  cost on unsolved cells -> ~27 GPU-h total, ~2 requeues. (DECISIONS.) The 128k point is dropped;
  2k/8k/32k is sufficient for the generalization number + the Phase-1-noise recheck.
- KEPT the 78 already-done cells (no re-run): pass@{2k,8k,32k} = (tokens_to_solve <= b), and the
  ceiling never alters pre-ceiling generation, so a 128k-ceiling cell's 2k/8k/32k columns are
  identical to a 32k-ceiling run (anything solved in 32k..128k is "unsolved" at b<=32k either way).
  Resume skips them by filename (harness.py:84, no config_hash guard) -> the dir carries a mixed
  config_hash (old 0ca3f6631081 for the 78, new for the rest); cosmetic, the curve data is correct.
- Resubmitted: job 10527591 (resume, capped config). Monitor re-armed for terminal/requeue.
- Next: on completion verify 558/558, report ProofNet# pass@B [2k/8k/32k] next to miniF2F, and
  re-test "all Phase 1 components are noise" on this 2nd benchmark.

## 2026-06-12 (cont.) — reverted ProofNet# ceiling to 128k on burst (GPU-h rule relaxed)
- User relaxed the >50 GPU-h ask-first rule: if the spend buys good findings, break it. So I reverted
  the 32k cap back to the full **[2k,8k,32k,128k]** grid. Rationale beyond cost: (a) directly
  comparable to the miniF2F baseline curve; (b) on harder ProofNet# problems the extra refinement
  budget may matter MORE than on miniF2F (whose 32k->128k was ~flat) — whether it does is itself a
  finding; (c) the 78 already-done cells ALREADY computed their 128k data, so capping discarded it.
- Cancelled the capped resume (10527591, was just RUNNING, 0 new cells lost), reverted config,
  resubmitted on **partition=burst --time=4-00:00:00** (job 10534104). burst is preemptible but
  --requeue makes Slurm auto-requeue preemptions from the last completed cell — far less babysitting
  than chaining ~6 short 12h walls. The 78 done cells are skipped on resume. Monitor re-armed (bzwnzow53).
- Saved the GPU-h guidance to user memory (feedback_gpuh_limit_flexible).

## 2026-06-12 (cont.) — meantime tooling while the ProofNet# baseline runs
- Built scripts/analyze_results.py (reusable; the FINDINGS analysis was ad-hoc before): `curve`
  (pass@B mean±std + tokens-to-first-proof), `compare` (two runs side by side + per-B Δ), `flips`
  (paired per-(problem,seed) gains/losses at fixed B = the project's noise bar). CPU-only, works on a
  partial in-flight dir. VALIDATED: reproduces the miniF2F baseline exactly (2k=29.6 8k=60.1 32k=69.5
  128k=74.9). +5 unit tests (synthetic records), fast suite green, ruff clean.
- Live preliminary ProofNet# read off the 78 in-flight cells (seed0, alphabetically-early Artin/analysis
  problems — biased): pass@{2k,8k,32k,128k} = {7.7, 16.7, 17.9, 20.5}%. Two early signals: ProofNet#
  is much harder (~20% vs miniF2F ~75% @128k — real generalization gap), and 32k->128k still rises
  (+2.6pp), so keeping the 128k tier looks justified (not flat). Preliminary — not representative.
- Staged configs/phase1_ablation_proofnet.yaml (ProofNet# OFAT, mirrors phase1_ablation.yaml; expands
  to 7 cells; reuses the existing Mathlib premise corpus). LAUNCH GATE in-file: only run after the
  baseline lands and shows pass@8k comfortably > 0 (validate-premise; partial read ~17% looks fine).
- Pre-existing ruff E501s remain in throwaway diag scripts (diag_repl.py, make_pickle_local.py); left
  untouched (not this session's work).

## 2026-06-13 — ProofNet# baseline relaunch + Phase 1 ablation launched in parallel
- Baseline job 10534104 died 08:05 (exit 0:53, 0s elapsed, no log) — a burst preempt/cancel that
  did NOT requeue; monitor lost across session compaction. 78/558 cells intact. Resubmitted as
  **job 10582326** on burst (3d wall, --requeue + --resume skips the 78 done). Durable monitor armed.
- Validated scripts/analyze_results.py on the 78 real ProofNet# cells (seed0, biased preliminary):
  pass@B 2k=7.7% 8k=16.7% 32k=17.9% 128k=20.5%; 16/78 solved, median 2789 tok to first proof.
  → validate-premise gate (pass@8k comfortably >0) MET on real data; tool works on ProofNet# JSONs.
- Decision (user: launch in parallel): submitted Phase 1 OFAT ablation on ProofNet# as
  **array job 10582331** (`_[0-6%4]`, 7 cells, budget=8000, seeds 0/1/2) → results/phase1_proofnet/.
  Runs concurrently with the baseline on burst (18 idle nodes). Re-tests the miniF2F finding
  ("no agent component beat noise") on the 2nd, harder benchmark.

## 2026-06-14 05:14 — burst starvation → moved both ProofNet# runs to `short` + durable watcher
- Burst contention: both jobs sat PENDING (reason=Priority) ~3.5h with ZERO progress (last cell
  01:34, checked 05:14). Resume-keying preserved all work (baseline 82, ablation budget_alloc__2
  245/558), but burst kept losing the priority queue after each preempt. Starvation trigger hit.
- Cancelled burst 10582326/10582331; resubmitted on `short` (non-preemptible, 12h wall, 10 idle
  nodes): baseline **10584314**, ablation array **10584315**. Both resume from where burst left off.
- Added scripts/proofnet_watcher.sh — re-chains BOTH runs across the 12h short wall (resubmits
  sweep.sh / ablation.sh when absent from queue and unfinished; cap 30). Runs detached via
  nohup+setsid so it survives Claude/session restarts (the burst Monitors kept dying on session
  interrupts). In-session Monitor b5nocbrrg also alerts if the watcher process goes DOWN.

## 2026-06-14 05:32 — shard the 128k baseline across 8 GPUs (days → ~1 wall)
- The single-GPU 128k baseline was the long pole (~73 GPU-h remaining = ~6 chained 12h walls).
  Added problem-set sharding so N array tasks split the (seed,problem) cells across N GPUs into the
  SAME resume-keyed dir. SAME total GPU-h — pure wall-clock parallelism.
- Code (test-first, fast suite 231 green, ruff clean):
  - harness.run_sweep: `shard=(id,n)` slices the flattened cell list; `write_summary` guard so shards
    emit per-cell JSONs only (no racing/partial metrics.json).
  - run.run_eval: threads `shard`; skips plot when sharded. New `aggregate_metrics()` writes
    metrics.json + plot from all cells on disk (CPU-only, no GPU/Lean).
  - cli `atp sweep`: `--num-shards/--shard-id` (replaces dead `--array-id`) + `--aggregate`.
  - tests: shards partition disjointly & union==unsharded; out-of-range raises; aggregate==unsharded.
  - slurm/sweep_array.sh: --array=0-7%8, passes SLURM_ARRAY_TASK_{ID,COUNT} as shard/num-shards.
  - proofnet_watcher.sh: resubmits sweep_array.sh; runs `--aggregate` once all 558 cells exist
    (that now produces metrics.json, the completion signal).
- Validated `--aggregate` on the real 82 partial cells (matches the live curve). Cancelled the
  single-GPU baseline 10584314; launched sharded array **10584316** (`_[0-7%8]`). Ablation 10584315
  continues unaffected. Watcher PID relaunched; monitor bbct1m1ge re-armed.
- Gotcha logged: `pkill -f proofnet_watcher.sh` is too broad — it matches the monitor's own pgrep
  command line and kills it. Use `pkill -f 'bash scripts/proofnet_watcher.sh'`.

## 2026-06-14 09:30 — fix: sweep_array.sh Lean-staging race (all 8 shards FAILED in <1min)
- First sharded baseline array (10584316) DID get GPUs at 09:22 but all 8 shards crashed in 9-59s
  (exit 1). Cause: each `short` GPU node has 2 l40s, so two shards co-locate and BOTH `rm -rf` + `cp`
  the Lean env into the shared /local/$USER/atp-lean-env → "Directory not empty"/"File exists"/
  "Permission denied". sweep_array.sh was copied from the OLD sweep.sh (one-sweep-per-node, no lock).
- Fix: ported ablation.sh's flock-guarded staging (exec 9>.atp_stage.lock; flock 9; stage-or-reuse;
  flock -u 9) so the first shard on a node stages and the rest block then reuse .staged_ok. The
  crashed copies are incomplete (cp died <1min « 10-20min) so N_LOCAL<N_GPFS → next run re-stages
  cleanly; no manual node cleanup. Resubmitted as array **10584643**; watcher restarted.
- Op note: `pkill -f <pat>` self-matches the running shell (the pattern is in its own argv) AND any
  monitor whose pgrep line contains <pat> — killed my Bash shell twice (exit 144) + an earlier
  monitor. Kill background helpers by PID (ps -eo pid,cmd | grep), not pattern.

## 2026-06-14 (cont.) — CRITICAL verifier soundness bug found; ProofNet# runs invalidated; fix landed
- Checking the runs we were waiting on. **(1) ProofNet# baseline (sharded array 10584643): was at
  378/558**, 1/8 shards running + 7 PENDING(Resources) after hitting the 12h `short` wall; the
  detached watcher had died on a session interrupt (log stops 09:33), so nothing re-chained.
  **(2) Phase 1 ProofNet# ablation (array 10584315): COMPLETED all 7 cells** (3124 solve-records).
- **The ablation reported impossible "wins"** (pass@8k): reviewer 0.556, memory 0.525,
  budget_alloc__2 0.375 vs baseline 0.120 — and per-seed they were wildly split (reviewer
  [0.11,0.74,0.82]). No config tweak can 6x the solve rate on a fixed set → smelled like false
  positives, NOT a finding. Investigated instead of reporting.
- **ROOT CAUSE — two independent verifier soundness holes:**
  1. **Truncation / no-goal (all runs):** a generation cut off at the token cap can emit only a
     preamble, e.g. `def is_topology (X) (T) := univ ∈ T ∧ ...` with NO `theorem`. `_build_repl_source`
     submits it raw; Lean compiles a bare def with no errors; `verifier.py` set `ok` purely on
     "no error-severity message" → scored **solved**. Confirmed on a real baseline cell
     (`Munkres__exercise_13_4a2__seed0`, completion_tokens=8000, feedback "Proof verified.").
  2. **Spurious REPL success (concurrency):** `repl._format_response` returned `success = (not
     has_error)` — so an EMPTY/malformed response (`{}`) with no messages scored as success. A
     wedged/cross-talked REPL under array co-location returns such responses → mass false solves.
     This is the extra amplifier in the reviewer/memory/budget_alloc__2 cells (the inflation that
     SURVIVES the structural check below; the stored agent_states only persist Lean output on
     FAILURE, so these can't be re-scored — they must be re-run).
- **Blast radius (audited stored results):** miniF2F **Phase 0 baseline = 548 solved, 0 false
  positives → headline pass@B numbers STAND**; miniF2F Phase 1 ablation = 6/3124 (0.2%, doesn't move
  noise-level conclusions). The bug only bites hard on ProofNet# (hard problems → frequent full-budget
  truncation). **All ProofNet# numbers (baseline + ablation) are INVALID and must be re-run.**
- **FIX (test-first, fast suite green, ruff clean):**
  - `verifier.py`: new soundness gate — a clean compile that declares no `theorem`/`lemma`/`example`
    is `reason="no_goal"`, ok=False (validated: 528/528 real solves declare one → 0 false negatives;
    removes the truncation FPs, knocking the clean cells to their true ~0.11).
  - `repl.py` `_format_response`: require `env` in the response for success (a genuinely accepted
    command returns a new env id). Empty/malformed response → REPL_INFRA_ERROR, not success.
  - tests: +3 in test_lean_verifier (no-goal preamble, pure prose, lemma/example accepted),
    +2 in test_lean_repl (no-env `{}` and `{messages:[]}` not success). All pass.
- **User decisions this session:** cancelled the running baseline 10584643 (generations can't be
  trusted to re-score for hole #2); fix verifier first (done); audit miniF2F (done — clean).
- **NEXT:** re-run ProofNet# baseline + Phase 1 ablation with the fixed verifier (on `short`, sharded,
  resume-keyed; relaunch the watcher). Old results/proofnet_baseline + results/phase1_proofnet are
  invalid — archive/clear before re-run so resume doesn't skip tainted cells. Then re-test the "all
  Phase 1 components are noise" claim on ProofNet#. Commit the fix.

## 2026-06-14 (cont.) — verifier fix committed; ProofNet# re-run launched
- Committed the two-hole verifier fix as **aa659f5** (local; not pushed). Editable install confirmed
  (`atp` -> repo src) so jobs pick up the fix.
- Archived the invalid runs to `results/_invalid_2026-06-14_verifier_bug/` (proofnet_baseline,
  phase1_proofnet, proofnet_smoke_old) — moved not deleted; clears resume so re-run starts fresh.
- Real-Lean smoke (10591889) sat PENDING(Resources) 35min on heavy GPU contention; cancelled it
  (also: it shares job-name `atp_sweep` with the sharded baseline, which fooled the watcher's
  "is a sweep queued?" guard and blocked the baseline submit). Fix safety instead established by
  reasoning: `_load_base_env` already requires `env` in the REPL import response, so a real accept
  ALWAYS carries `env` → the new env-required check can't reject legit proofs; +unit tests +528/528
  no_goal audit. First real cells will serve as the live smoke.
- Relaunched detached watcher (nohup setsid). It submitted **ablation 10592340 (`_[0-6%4]`)** and
  **sharded baseline 10592350 (`_[0-7%8]`)**, both resume-keyed → results/phase1_proofnet +
  results/proofnet_baseline. Both PENDING on GPU contention; watcher re-chains across the 12h `short`
  wall (cap 30) and runs `--aggregate` once all 558 baseline cells land.
- NEXT: sanity-check first cells (real accepts carry env, no mass no_goal/REPL_INFRA_ERROR), then on
  completion report ProofNet# pass@B vs miniF2F + re-test the "Phase 1 = noise" claim. Consider
  pushing aa659f5.

## 2026-06-15 (cont.) — ProofNet# baseline unblocked: L40S→A6000 GPU switch
- The resumed baseline sweep array sat PENDING(Resources) with a ~7h projected start: every L40S on
  the cluster (ins038-039,056-061) was fully allocated. `slurm/sweep_array.sh` pinned `gpu:l40s:1`.
- Switched the sbatch gres to `gpu:A6000:1` (many idle A6000 on `short`: ins081-094). A6000 = 48 GB
  VRAM like L40S, vLLM-supported, Goedel-8B fits — drop-in for inference. Cancelled the stuck L40S
  job 10616874, resubmitted as 10628090: all 8 shards RUNNING within seconds (ins091/ins092), no
  staging-race (flock held despite 7 shards co-located on ins092).
- Caveat (recorded, not a problem): cells 423–558 run on A6000 while 1–422 ran on L40S. Each cell is
  an independent solve-rate measurement and generation is already batch-nondeterministic across vLLM
  processes, so mixing GPU type does not affect pass@B correctness; GPU type is captured per cell in
  run_manifest.json. The edit persists for all watcher re-chains.
- Also restarted the detached watcher twice today (the Bash-launched background shell doesn't survive
  long on this node); pid 431017 alive. Ablation COMPLETE (7/7); baseline 422/558 → resuming.

## 2026-06-15 (cont.2) — staging-race fix + CPU/mem trim to schedule on A6000
- First A6000 resubmit (10628090) FAILED silently: all 8 "COMPLETED" exit 0 but 70/22/17/23 cells/shard
  logged LeanEnvNotReady. Root cause = node-local staging race, now severe: l40s packs 2 shards/node,
  A6000 packs up to 8. On ins092, 6 shards REUSED a stale env while shard 3 ran `rm -rf $LOCAL_ENV` +
  a 253s cp — deleting the live env (incl. repl exe) out from under the 6 mid-run. Two holes: (a) the
  reuse guard checked only olean COUNT, not the repl exe (a stale exe-less env with matching count was
  reused); (b) `rm -rf`+long-cp leaves the env ABSENT ~250s.
- Fix (slurm/sweep_array.sh, tested in isolation — 4 cases: stage / reuse / missing-exe→restage /
  count-mismatch→restage all correct): reuse requires marker + full olean count + `-x repl`; staging
  goes to a PRIVATE per-task dir then publishes via atomic `mv -T` (sub-ms swap, never deletes the live
  env). Verified LIVE on 10634722: ins086 had 5 co-located shards — 1 staged to its private dir while
  4 reused the valid env concurrently, zero LeanEnvNotReady.
- Scheduling: the slimmed-but-still-16c/110G A6000 job then sat PENDING ~20h — free-A6000 nodes are
  CPU-saturated (192 cores, ~186-188 alloc → only 4-10 free/node); the 8-GPU-free nodes had ~4 free
  cores, and no free-A6000 node had 16c+110G together. Trimmed to 4c/48G + eval.n_workers 8→3
  (proofnet_baseline.yaml). All 8 shards scheduled INSTANTLY (ins086×5/088/093/091). n_workers is a
  concurrency knob — pass@B invariant; new cells carry a new config_hash (cosmetic, aggregate doesn't
  guard on it). Throughput/shard lower but 8 shards parallel; remaining 134 cells est ~6-9h, 1 wall.
- Watcher restarted several times today (Bash-launched bg shell doesn't persist on this node); resubmit
  count resets per start (fine). Ablation COMPLETE (7/7); baseline resuming 424/558 on job 10634722.

### 2026-06-16 (later) — staging race REGRESSED; root-caused to shared reuse; per-shard env fix
- Job 10634722 (A6000) made almost no progress (424->428/558): 5 of 8 shards co-located on ins086,
  and 3 (shards 2/4/5) failed with `LeanEnvNotReady` mid-eval (sacct: all COMPLETED 0:0 but exited in
  6-30min after fast-failing their cells; shard5 `ran=0 skipped=53`).
- ROOT CAUSE (deeper than the 2026-06-15 publish-window fix): atomic-publish closed the window during
  `mv`, but REUSE *shares the published inodes* — it doesn't copy. When one co-located shard re-staged
  (`mv live->.old; rm -rf .old`), the `rm -rf .old` destroyed files that the OTHER co-located shards
  were actively reading via the shared `/local/$USER/atp-lean-env` path -> their REPL hit
  LeanEnvNotReady. ins086 timeline: shards 2/3/5/6 reused a prior-job env; shard 4 re-staged and
  yanked it out from under them (3/6 died at 6min, 2 at 12min, 4/5 limped to ~28min).
- FIX: PER-SHARD node-local env — `LOCAL_ENV=$LOCAL_BASE/atp-lean-env-s${SLURM_ARRAY_TASK_ID}`. No shard
  ever reads/moves/deletes another's files, so co-location can't race no matter how many pack a node.
  Cost: 4.2G/shard on SSD (<=8 -> ~34G/node, fine) + N concurrent first-stage copies off GPFS; a shard
  reuses its own dir free on requeue to the same node. Lock is now per-shard (guards only a requeued
  duplicate of the same id). The reuse guard (marker + full olean count + repl exe) is unchanged.
  Validated in isolation: 5 co-located shards + a forced re-stage of shard 4 -> all 5 envs stay VALID.
- Detached watcher won't persist on this node; switched to self-monitoring via the /loop. Resubmitted
  baseline as job 10642214 (array 0-7%8) with the fixed script. Ablation already DONE (7/7 components,
  558 cells each). Remaining: ~130 baseline cells -> aggregate metrics.json -> final ProofNet# pass@B.

### 2026-06-16 (later still) — per-shard dirs NOT enough; 3 real co-location root causes found+fixed
- Job 10642214 (per-shard dirs) ALSO made zero progress (still 428/558). But the failures finally
  exposed the ACTUAL root causes — co-location of many shards per A6000 node (4-5/node), 3 distinct:
  1. EPILOG WIPE (the env-vanishing mystery): `/etc/slurm/epilogs/cleanup.sh` runs
     `find /local -user $SLURM_JOB_UID -maxdepth 1 -exec rm -rf {} \;` on EVERY job end. So the first
     of my co-located shards to finish deletes ALL of /local/$USER — including the live -sN envs of my
     other still-running shards (ins085: shard6 ended at 8min -> shard5's -s5 vanished -> LeanEnvNotReady
     even though its vLLM was happily generating at 84 tok/s). Per-shard dirs can't help; the wipe is
     node-wide on my uid. /local is 200G (capacity was never the issue); the epilog only touches
     /tmp + /local, NOT /dev/shm (504G tmpfs). FIX: stage to /dev/shm/$USER (RAM, epilog-proof, faster).
  2. PORT COLLISION: every shard bound vLLM on 8000 -> 4 co-located shards on ins087 collided ->
     "Engine core initialization failed", vLLM died. FIX: PORT = 8000 + SLURM_ARRAY_TASK_ID.
  3. ENDPOINT-FILE CLOBBER (the APIConnectionErrors): all shards wrote the shared
     results/_vllm_endpoint.txt (last writer wins) and the eval read it -> shards talked to another
     shard's/node's vLLM. eval/run.py:96 already honors ATP_VLLM_ENDPOINT_FILE; sweep_array.sh just
     never set it. FIX: per-shard endpoint file + export ATP_VLLM_ENDPOINT_FILE (mirrors slurm/ablation.sh,
     which had 2+3 already — THAT is why the ablation completed and the sweep didn't).
- Cross-check: slurm/ablation.sh (proven 7/7) already does per-task port + endpoint; it survived shared
  /local only by luck (long component runs finish near-together, dodging the mid-run epilog wipe). The
  /dev/shm staging here is strictly safer. Bumped --mem 48G->64G for the 4.2G tmpfs env in RAM.
- All three fixes are shell-level + dry-run validated (port 8000+id, paths /dev/shm/.../-sN, endpoint
  override resolves). Resubmitting baseline with the corrected sweep_array.sh. Self-monitoring via /loop.

### 2026-06-17 — ProofNet# baseline COMPLETE (558/558); pass@B + Phase 1 noise re-test
- Co-location fixes WORKED: ProofNet# baseline ground out to 558/558 cells, zero LeanEnvNotReady,
  only tolerated transient node-flakiness (one NVML hit on a shard, self-healed on requeue). Aggregated
  to results/proofnet_baseline/metrics.json (config_hash 1728bc3977ef; whole_proof + refinement
  max_iters4 alloc0.5; all Phase 1 components OFF; 186 problems x 3 seeds, metered to 128k).

- **ProofNet# pass@B (mean ± seed-std, n=186)   vs   miniF2F baseline:**
  |  budget |  ProofNet#        | miniF2F |
  |---------|-------------------|---------|
  |    2000 | 4.8% ± 1.4%       | 29.6%   |
  |    8000 | 9.3% ± 1.1%       | 60.1%   |
  |   32000 | 12.0% ± 0.6%      | 69.5%   |
  |  128000 | 14.3% ± 0.8%      | 74.9%   |
  tokens_to_first_proof: n_solved=80 median=3855 mean=16872. ProofNet# is ~5x harder than miniF2F at
  every budget for this model — the curve is far flatter (4.8->14.3% over 64x budget vs 29.6->74.9%),
  i.e. more budget keeps buying proofs but the absolute ceiling is low. Consistent with ProofNet being
  undergrad-level / out-of-distribution vs miniF2F competition problems for Goedel-Prover-V2-8B.

- **Re-test of "all Phase 1 components are noise" on ProofNet#** (paired flips per (problem,seed) at
  B=128000, each component vs the ABLATION baseline results/phase1_proofnet/baseline — same config
  family, NOT the metered proofnet_baseline above; ablation baseline plateaus at 10.9% from 8k):
  | component          | gains | losses | net | verdict      |
  |--------------------|-------|--------|-----|--------------|
  | reviewer__1        |  13   |  10    |  +3 | noise-like   |
  | budget_alloc__2    |   9   |  11    |  -2 | noise-like   |
  | memory__1          |   8   |  10    |  -2 | noise-like   |
  | tactic_skeletons__1|   9   |  12    |  -3 | noise-like   |
  | budget_alloc__0    |   6   |  25    | -19 | DIRECTIONAL (hurts) |
  | retrieval__1       |   6   |  42    | -36 | DIRECTIONAL (hurts) |
  VERDICT: the "all noise" claim does NOT fully transfer. 4/6 are noise-like (gains≈losses, churn), but
  TWO are clearly directional on ProofNet# — and both HARM: budget_alloc__0 (the front-loaded/no-escalation
  alloc) net -19, and retrieval__1 net -36 (retrieval actively poisons the prompt on OOD undergrad
  problems, 42 baseline solves lost for 6 gained). So the substantive finding is UNCHANGED and stronger:
  no Phase 1 component is a net-positive lever on ProofNet#; two are net-negative. Same direction as
  miniF2F (no helpful lever), with ProofNet# additionally surfacing retrieval/alloc as harmful — the
  harder OOD benchmark is more sensitive to bad context, not less. budget_alloc__0 ran 554/558 cells
  (4 short, A6000 flakiness); flips are over the 554 paired cells — does not change the verdict.

### 2026-06-17 (Phase 2 Step A) — mechanism found on existing data (no GPU): diversity collapse + reasoning floor
- Pivot to MECHANISM not levers (DECISIONS 2026-06-17, PHASE2_PLAN.md). Built scripts/analyze_mechanism.py
  (CPU-only, 9 tests pass) mining results/*/agent_states (full per-attempt corpus). Run over miniF2F
  baseline (704/732 cells; 28 empty states skipped) + ProofNet# baseline (558/558). Output:
  results/phase2/{mechanism.json, MECHANISM.md}.
- **F1 — diversity collapse at the APPROACH level is the saturation mechanism.** Unsolved cells try ~19-24
  times but commit to only ~2 distinct opening tactics (miniF2F 1.94, ProofNet# 2.28); skeletons vary more
  (6-9) → reshuffles downstream tactics inside ~2 fixed frames, doesn't reconsider the approach. Identical
  on both benchmarks → property of hard problems, NOT OOD-specific; the asymmetry is just the fraction
  trapped (miniF2F 25% unsolved vs ProofNet# 86%). Explains the flat pass@B tail on both curves.
- **F2 — bottleneck is REASONING, not knowledge/formalization (the gate).** Unsolved taxonomy: reasoning
  (deep+shallow) 98.9% miniF2F / 95.2% ProofNet#; formalization/syntax 1-4%; hallucinated-lemma 0% / 1.0%.
  → Retrieval doomed by construction (premises aren't missing; explains its Phase 1 null+harm: BM25 injected
  irrelevant premises into reasoning-bound problems) → retrieval + ReProver KILLED with data. BFS HELD
  (failure is closing goals with ~2 ideas; stepping same policy adds no idea). 3rd benchmark unmotivated.
- **F3 — capability floor, not almost-solving tail.** Deepest-step-before-error: miniF2F median 64 (p90 137,
  1% never past step1) = long elaborated unclosable proofs; ProofNet# median 23 (p90 65, 10% never past
  step1) = stalls earlier + more can't-starts but 90% get going. (Caveat: depth = first-error depth, not
  near-correctness.)
- **F4 — no easy subfield on ProofNet#** (best Dummit .26/Rudin .22/Artin .21, worst Axler .12); miniF2F
  easy core amc12/mathd .94. Flat curve = uniformly hard set.
- **NEXT (GPU): promote Step C (diversity injection — temp/nucleus schedule or distinct-approach prompting),
  now the best-justified lever since it targets F1; and Step B (DeepSeek-Prover-V2-7B replication) for
  generality.** All Phase 2 Step A artifacts committed; not pushed.

### 2026-06-17 (Phase 2 Step A, pre-flight) — F5: diversity collapse is SYMPTOMATIC, not causal
- Added A5 late_solve_approach to analyze_mechanism.py (+test, 10 pass). Question: when a problem solves
  LATE (first verifying attempt index w>=3), does the win use an opening tactic NOT tried before (explora-
  tion unlocked it = causal) or an already-used approach (better execution = symptomatic)?
- RESULT: late solves **0.0% new-approach** on BOTH benchmarks (miniF2F n=64, ProofNet# n=31; switched-
  from-first 1.6%/0.0%). The model wins late by executing one of its already-tried ~2 approaches correctly,
  essentially never by discovering a new one. → collapse is symptomatic of the F2/F3 capability floor, not
  the lever. **Predicts Step C (diversity injection) will NULL.** Reframes C as the decisive causal-vs-
  symptomatic confirmation (measure diversity-moved AND solves; a null only counts if diversity provably
  rose). Caveat: correlational, observes only natural sampling — C still needed to test FORCED diversity.
- Pushed Step A (3 commits) to origin/main before any sweep (hygiene). NEXT: decide whether to run C to
  confirm-null vs treat pre-flight as sufficient; start Step B's DeepSeek Lean-pin setup in parallel
  (independent of C).

### 2026-06-17 (Phase 2 Step C) — built + held for launch; pre-registered the null prediction
- DECISION (full reasoning + pre-registration in DECISIONS.md): RUN C, not skip — F5 is correlational &
  conditions on survivors + the model's natural sampling, so it can't observe the FORCED off-distribution
  regime. C closes that gap; it's decisive. Build now, hold launch, run on BOTH provers in the B campaign.
- BUILT (zero GPU, test-first): `diversity_injection` component (src/atp/agents/components/diversity.py) —
  approach-conditioning, propose-only: lists the distinct opening tactics already tried on a problem and
  instructs a fundamentally different approach; first proposal is a no-op; refine untouched. config.
  DiversityCfg (off by default) + wired into build_components. Tests: tests/test_diversity_component.py
  (6) + trapped_problems in test_analyze_mechanism (11 total); full fast suite 250 pass; no config-hash
  breakage (default-off).
- SCOPING: scripts/analyze_mechanism.py trapped_problems() → problems unsolved by ALL seeds @128k:
  ProofNet# 150/186, miniF2F 55/244 (scratch/phase2/trapped_{proofnet,minif2f}.txt). Configs
  configs/diversity_{proofnet,minif2f}.yaml (defaults: proofnet_baseline / phase0_baseline) override
  budgets [8k,32k] + restrict to the trapped subset via split=test+use_novel_split (NOT split=novel,
  which forces base=valid — caught + fixed in config-load validation). Validated: both load, restrict to
  exactly the trapped set (150/55), diversity ON.
- READOUT pre-registered: (a) manipulation check distinct-first-tactics↑ (analyze_mechanism A1), (b) solves
  vs baseline @8k/32k + paired flips, (c) failure texture (A2), watch syntax/truncation. PREDICTION:
  diversity↑ ∧ solves-flat ∧ new approaches still die at goal-closing = symptomatic confirmed.
- HOLD: not sbatch'd. Remaining pre-launch gate = `make smoke` (GPU/Lean) then launch with B. NEXT: B —
  DeepSeek-Prover-V2-7B Lean-pin setup + core replication (weights already cached at .hf_cache; prior
  theorem-proving-research/deepseek_prover_eval env + mathlib cache to mine → setup cheaper than feared).

### 2026-06-17 (Phase 2 Step B recon) — DeepSeek pin found; old repo is a NO-MATCH (don't reuse)
Zero-GPU recon for the DeepSeek-Prover-V2-7B replication. Success bar = "intact AND matches DeepSeek's
authoritative pin", sourced from DeepSeek, not the old project.
- AUTHORITATIVE PIN: paper (ar5iv 2504.21801) states verbatim **"All experimental results of
  DeepSeek-Prover-V2 are conducted with Lean 4.9.0"**. NO mathlib commit published (checked GitHub README,
  HF card, paper). Repo ships only the PDF + minif2f-solutions.zip + figures — no Lean project / toolchain
  / manifest. Verification tool unspecified (REPL fine — kernel is kernel). → faithful pin = Lean v4.9.0 +
  STANDARD mathlib at a v4.9.0-compatible commit, disambiguated by requiring DeepSeek's OWN published
  miniF2F proofs (minif2f-solutions.zip, 217 test/221 valid solved, `import Mathlib`) to verify against it.
  KEY: v4.9.0 ≈ Goedel's v4.9.0-rc1 → the atp Lean layer transfers with minimal change; ONLY mathlib
  differs (DeepSeek standard mathlib vs Goedel's xinhjBrant fork @2f65ba7).
- OLD-REPO MATCH = **NO. Do not reuse for reported numbers.** theorem-proving-research Lean envs are
  v4.6.0 (miniF2F proj, mathlib e3e4eeab), v4.22.0 (Putnam), v4.29.0 (lean_env, mathlib 8a178386) — none
  is v4.9.0 (the v4.29.0 stack is exactly the API-drift trap). It also verified via `lake env lean`, not a
  REPL, so the harness isn't reusable either. Earlier "265cb026 mathlib" read was WRONG — that's the old
  repo's own git HEAD (git walked up to the parent repo; .xdg_cache/mathlib is just an ltar cache). Mine
  the old repo ONLY for benchmark statement files, not the env.
- PORT INTERSECTION: paper evaluates DeepSeek-V2 natively on BOTH miniF2F-test (244) AND ProofNet-test
  (186) — the SAME two benchmarks we use → B can do cross-model on BOTH (not just miniF2F). Intersection ≈
  full canonical sets; exact size pending validate_statements.py gate against the DeepSeek standard-mathlib
  pin (statements audited on the Goedel fork may differ). Report cross-model on the compile-on-BOTH-pins
  intersection only (so a gap is model, not port).
- VERDICT: B is the BUILD path (authoritative fetch), not reuse — but cheap-ish: atp Lean layer is one rc
  off (v4.9.0-rc1→v4.9.0), point at standard mathlib @v4.9.0 (try `lake exe cache get`), rebuild REPL,
  gate-validate miniF2F+ProofNet# statements, green contract tests INCL sorry/admit/native_decide rejection
  (a soundness contribution — must hold in env #2). Protocol-invariance for B: hold benchmarks
  (intersection), budget schedule, 3 seeds, minimal-baseline agent, metrics, fixed-verifier handling
  constant; only model + its matched Lean env (+ matched statement files) change. Recon artifacts in
  scratch/phase2/deepseek_recon/ (gitignored). ZERO GPU until contract tests green.

### 2026-06-17 (Phase 2 Step B) — DeepSeek pin chosen + env build launched (job 10671073)
- PIN (self-decided): Lean v4.9.0 + STANDARD mathlib4 @ f0957a7575317490107578ebaee9efaf8e62a4ab. The
  v4.9.0-final window collapses to ONE commit (f0957a7 is the sole mathlib4 commit on v4.9.0-final; next
  commit bumped to v4.10.0-rc1) → no bisection, just max-verify DeepSeek's 438 published proofs against it.
  REPL = leanprover-community/repl @ bump_to_v4.9.0 (toolchain == v4.9.0, confirmed; canonical, not fork).
- SCAFFOLD: scratch/lean-cache/deepseek-lean-env/{lean-toolchain,lakefile.lean,DeepseekLeanEnv/Probe.lean}.
  Build job slurm/build_deepseek_lean.sh (10671073, short partition, 16cpu/96G/6h, CPU-only, proxy unset).
  STANDARD mathlib → `lake exe cache get` expected HIT (minutes); from-source fallback in-script if MISS.
- NOTE: /insomnia001 at 99% (97G free) — enough for one env but tight (shared FS).
- NEXT (all zero-GPU, gated before any sweep): (1) confirm env ready + max-verify the 438 DeepSeek miniF2F
  proofs → verification fraction; (2) validate_statements.py miniF2F+ProofNet# on this pin → compile-on
  -both-pins intersection size; (3) contract tests incl sorry/admit/native_decide rejection in env #2.
  REPORT-BACK checkpoint = {commit (have), fraction, intersection} before first GPU.

### 2026-06-17 (Phase 2 Step B) — DeepSeek env BUILT + all pre-GPU gates GREEN (checkpoint)
Env built (job 10671645): Lean v4.9.0 + standard mathlib4 @ f0957a7 + repl@bump_to_v4.9.0. NOTE: `lake
exe cache get` only PARTIALLY hit the year-old commit (3483/4737 oleans) → ~45min from-source build for
the rest; so env #2 cost ~ the Goedel fork build, not the minutes I'd hoped. HOME quota was exhausted by
OTHER projects' toolchains (~8G in ~/.elan) → relocated DeepSeek toolchains to scratch via ELAN_HOME (did
NOT delete others' caches). Gates run on a compute node with the env staged to /dev/shm (GPFS olean
open-storm otherwise) — slurm/gate_deepseek.sh + a G1 rerun.
- **G3 soundness (contract tests -m lean vs env #2): PASS** — env-backed verify-accept + sorry/loophole
  rejection hold in the second env (the 1 skip is the model-dependent agent test, not soundness).
- **G2 intersection (validate_statements on this pin): miniF2F 244/244 (100%) + ProofNet# 186/186 (100%)
  elaborate.** Both also compile on the Goedel fork (baselines ran) → compile-on-both-pins intersection =
  the FULL sets (430 problems); a cross-model gap can't be a port artifact. (results/{minif2f,
  proofnet_sharp}/statement_validation.json)
- **G1 pin confirmation (verify DeepSeek's OWN 438 published miniF2F proofs): 435/438 = 99.3% VERIFY.**
  Faithful pin confirmed. The 3 misses: aime_1984_p7 (54KB) + imo_1992_p1 (27KB) hit my 300s/file cap
  (timeout artifact, not API drift); imo_1977_p5 (1KB) is a lone candidate-genuine miss. True faithful
  fraction is ≥99.3% (≈100% sans the timeout cap). (results/phase2/deepseek_proof_verification.txt)
- Fixed: recon files were one dir up (zwz2000/scratch vs repo scratch) — moved into repo scratch.
- CHECKPOINT COMPLETE (all zero-GPU): {pin = v4.9.0 + mathlib f0957a7 ✓, verification 99.3%, intersection
  244+186=430 ✓, soundness ✓}. CLEARED for B's GPU work. NEXT: build B's eval plumbing (DeepSeek model
  config + sweep env-staging for deepseek-lean-env + ELAN_HOME), then run baseline pass@B + the F1/F2
  mining on DeepSeek, and the Step C diversity arm on both provers. STILL NO GPU touched.

### 2026-06-18 (Phase 2 Step B) — DeepSeek GPU plumbing built + smoke GREEN; baselines launching
- Parameterized slurm/sweep_array.sh (model from config hf_repo/name; ATP_HF_HOME/ATP_LEAN_ENV_NAME/
  ELAN_HOME env overrides; Goedel defaults unchanged) so ONE script serves both provers. DeepSeek
  baselines inherit the Goedel baselines (phase0_baseline/proofnet_baseline) → protocol-invariant (only
  model + matched Lean env change). DeepSeek's official prompt == WholeProofTemplate (inference-matched).
- SMOKE caught 3 real bugs before scale (the gate working): (1) staging cp enumerated hardcoded
  AtpLeanEnv lib → stage whole env dir (DeepSeek lib is DeepseekLeanEnv); (2,3) orphaned vLLM from prior
  runs squats port 8000 on some nodes + the wait-loop hung instead of failing fast → run DeepSeek on
  ATP_VLLM_PORT=8200 base. SMOKE PASS (job 10675775): vLLM serves DeepSeek-V2-7B, Lean probe OK on env #2,
  pass@2000=0.500 (1/2) on miniF2F, verified clean.
- LAUNCHING DeepSeek baselines (sharded, port base 8200, deepseek env): miniF2F 244×3 then ProofNet#
  186×3, full [2k/8k/32k/128k]. Submit env: ATP_HF_HOME=~/.hf_cache, ATP_LEAN_ENV_NAME=deepseek-lean-env,
  ELAN_HOME=scratch/elan-deepseek, ATP_VLLM_PORT=8200.

### 2026-06-18 (Phase 2 Step B) — DeepSeek baselines launched; 3 scale-up infra fixes
Smoke green → launched both DeepSeek baselines. First attempt surfaced scale-only failures (smoke can't);
fixed three:
1. ENDPOINT-FILE COLLISION: per-shard _vllm_endpoint.sN.txt keyed only by task-id → two concurrent
   arrays (miniF2F + ProofNet#) with overlapping task-ids clobber each other → eval talks to wrong vLLM.
   FIX: key by SLURM_ARRAY_JOB_ID too + distinct ATP_VLLM_PORT bases per array (miniF2F 8200, ProofNet# 8300).
2. NVML THUNDERING HERD: many co-located shards init CUDA/NVML at once → NVMLError_Unknown → "Engine core
   init failed" → vLLM dies at startup (15/16 ProofNet# shards died launching the 16-way atop miniF2F).
   FIX: stagger vLLM start by (task_id%8)*25s. Helped miniF2F (healthy) but NOT ProofNet#.
3. FLAKY NODE ins082: ALL 14 remaining ProofNet# NVMLError deaths were on ins082 (bad A6000s); Slurm kept
   reassigning it. FIX: resubmit ProofNet# with --exclude=ins082. (Healthy nodes: ins086/087/092/093.)
STATE: miniF2F baseline 10676442 (8-way, base 8200) HEALTHY — 121/732 cells, 7 running. ProofNet#
baseline 10677640 (0-15%8, base 8300, --exclude=ins082) ramping. Submit env: ATP_HF_HOME=~/.hf_cache,
ATP_LEAN_ENV_NAME=deepseek-lean-env, ELAN_HOME=scratch/elan-deepseek. Confirmed DeepSeek serves with its
CORRECT chat template (<｜begin▁of▁sentence｜><｜User｜>). Multi-day grind; monitor + babysit node flakiness.

## 2026-06-18 — DeepSeek-Prover-V2-7B BASELINES COMPLETE (both benchmarks, 3 seeds)
Both DeepSeek baselines finished and aggregated to metrics.json. Cross-model pass@B (mean±seed-std):

  miniF2F (in-distribution):           DeepSeek-V2-7B    Goedel-V2-8B
    pass@2k    27.9±2.1    29.6
    pass@8k    57.9±1.7    60.1
    pass@32k   67.1±0.9    69.5
    pass@128k  72.0±0.5    74.9
  ProofNet# (OOD undergrad):           DeepSeek-V2-7B    Goedel-V2-8B
    pass@2k     5.4±0.5     4.8
    pass@8k    13.1±0.8     9.3
    pass@32k   18.3±1.6    12.0
    pass@128k  22.2±1.7    14.3

FINDINGS:
1. CORE THESIS REPLICATES on a 2nd independent prover: same curve shape both models — steep 2k->8k,
   sharp flatten to ~72-75% ceiling on miniF2F, much flatter & still-climbing-at-128k on ProofNet#.
   Budget-is-the-lever + saturation-asymmetry is NOT a Goedel artifact.
2. MODEL DICHOTOMY: Goedel edges DeepSeek on miniF2F (-2 to -3pp), but DeepSeek BEATS Goedel on the
   harder OOD ProofNet# at every budget, gap WIDENS with budget (+8pp at 128k: 22.2 vs 14.3). On OOD
   math the 7B model both scores higher and extracts more from extra compute.

INFRA POSTMORTEM (this campaign):
- ins082 AND ins087 are both bad-A6000 nodes (all their shards die at vLLM startup). Standing rule:
  --exclude=ins082,ins087.
- RESUME BUG (cost 2 wasted submissions 10687932/10687933): sweep_array.sh derives NSHARDS from
  SLURM_ARRAY_TASK_COUNT, so you CANNOT resume a sparse array subset (--array=7 or --array=3,6,9,...)
  -> "bad shard N/M" exit 2 / wrong-width partition. ALWAYS relaunch the full original contiguous range
  (--array=0-7%8 / --array=0-15%4..8); --resume is filename-keyed so done cells skip-complete in <1min.
- Final good jobs: miniF2F 10702125 (0-7%8 base8200), ProofNet# 10702126 (0-15, throttle bumped 4->8,
  base8300), both --exclude=ins082,ins087.

NEXT: F1/F2 mechanism mining (analyze_mechanism.py) on DeepSeek agent_states -> cross-model on the
430-problem (244 miniF2F + 186 ProofNet#) compile-on-both-pins intersection -> Step C diversity arm on
BOTH provers (Goedel C built/held in configs/diversity_*.yaml; DeepSeek C needs its trapped cells computed).

## 2026-06-18b — DeepSeek mechanism mining (F1-F5) REPLICATES Goedel; Step C arms prepped
Ran scripts/analyze_mechanism.py on both DeepSeek baselines -> results/phase2/deepseek/mechanism.json.
All five mechanism findings replicate on the 2nd prover:
- F1 diversity-collapse: unsolved cells try only ~1.8 distinct opening tactics over 22-33 attempts
  (miniF2F 1.76/22.2, ProofNet# 1.86/32.5) — same ~2-approach collapse as Goedel.
- F2 taxonomy (GPU-spend gate): unsolved = 100% reasoning_deep (miniF2F) / 94% reasoning + 3% shallow
  + 3% syntax (ProofNet#), ~0% knowledge/hallucinated-lemma -> retrieval/ReProver stays KILLED on the
  2nd model; bottleneck is deep reasoning, not missing lemmas.
- F3 floor: unsolved reach median deepest step 53/26, frac_never_past_step1 ~0 -> real progress, can't close.
- F4 no-easy-subfield: ProofNet# subfields all 21-33% (Artin .33 ... Axler .21); miniF2F mathd .92 easy.
- F5 (Step C pre-flight): late-solves (w3+) show 0.0% new-approach on BOTH benchmarks -> predicts the
  diversity-injection intervention NULLS (late wins are more samples of the same approach).

STEP C PREPARED (interventional test of F5 on BOTH provers):
- DeepSeek trapped cores computed: 61 miniF2F (>55 Goedel), 140 ProofNet# (<150 Goedel) — consistent
  with DeepSeek slightly worse in-dist, better OOD. Files scratch/phase2/trapped_{minif2f,proofnet}_deepseek.txt
  (regen: analyze_mechanism.trapped_problems on the baselines).
- New configs: configs/diversity_{minif2f,proofnet}_deepseek.yaml (defaults deepseek_*_baseline,
  budgets [8k,32k], diversity enabled, trapped subset). Validated: load resolves model=deepseek-prover-v2-7b
  + subset loads 61/61 & 140/140 names, 0 unmatched. Fast suite 51/51 pass (diversity+analyzer+components).
- Goedel C configs already built/held: configs/diversity_{minif2f,proofnet}.yaml (55/150 trapped).
- Smoke 10726039 (diversity_smoke_deepseek: 2 trapped probs, seed0, 8k) submitted before the 4-arm launch.
NEXT: smoke pass -> launch all 4 C arms (2 Goedel + 2 DeepSeek) on trapped cores @8k/32k -> readout =
manipulation check (A1 diversity rose?) + 2x2 solves vs baseline + A2 failure texture.

## 2026-06-18c — STEP C diversity arms LAUNCHED on both provers (interventional test of F5)
Smoke 10726039 (diversity_smoke_deepseek, 2 trapped probs @8k) PASSED clean (exit 0, 9:52): the
DiversityInjection component runs end-to-end in the real loop with DeepSeek serving + trapped subset.
Launched all 4 Step C arms on the trapped cores @8k/32k (each cell runs to 32k -> both budget points),
3 seeds, all --exclude=ins082,ins087, distinct vLLM ports (100-spaced, unique endpoint files/job):
  - Goedel  miniF2F  C: job 10726054 (configs/diversity_minif2f.yaml,          55 trapped, 0-7%8,  8200)
  - Goedel  ProofNet# C: job 10726055 (configs/diversity_proofnet.yaml,        150 trapped, 0-15%8, 8300)
  - DeepSeek miniF2F  C: job 10726056 (configs/diversity_minif2f_deepseek.yaml, 61 trapped, 0-7%8,  8400)
  - DeepSeek ProofNet# C: job 10726057 (configs/diversity_proofnet_deepseek.yaml,140 trapped,0-15%8, 8500)
PRE-REGISTERED PREDICTION (both provers): diversity injection raises approach-diversity (A1
mean_distinct_first_tactics up) but leaves solve rate FLAT vs baseline @8k/32k on the trapped names;
forced-new approaches still die at reasoning/goal-closing (A2 >=94-95%). A null is only interpretable if
the manipulation check (A1 rose) passes. Cheaper than baselines (32k not 128k ceiling).
READOUT when done: (1) A1 manipulation check on each diversity run vs its baseline; (2) 2x2 solves —
analyze_results compare baseline vs diversity @8k/32k restricted to trapped names + paired flips;
(3) A2 failure texture; (4) verifier-soundness guard (syntax/truncation must NOT creep up).

## 2026-06-18d — Step C arm 1/4 done (Goedel miniF2F); others running clean
Goedel miniF2F C COMPLETE 165/165, aggregated. pass@8k=0.6%±1.0, pass@32k=1.2%±2.1 on the 55 trapped
problems (baseline=0% on these BY CONSTRUCTION: trapped = unsolved by all seeds @128k, budget monotonic).
=> near-null with a 1-2 cell positive blip (within seed-std). Consistent with pre-registered prediction.
METHOD NOTE for the full readout: the A1 manipulation check MUST be budget-matched. Raw distinct-first-
tactic counts are confounded by attempt count (baseline 18.1 attempts @128k vs diversity 4.9 @32k).
Per-attempt proxy DOES show injection working (0.348 vs 0.108 distinct/attempt, ~3x), but the clean
check is baseline TRUNCATED to 32k vs diversity@32k — implement once for all 4 arms at completion.
Other 3 arms running clean (0 failures all): Goedel ProofNet# 87/450, DeepSeek miniF2F 74/183,
DeepSeek ProofNet# 25/420 (long pole). All --exclude=ins082,ins087, ports 8300/8400/8500.

## 2026-06-18e — Step C arm 2/4 done (DeepSeek miniF2F): EXACT null
DeepSeek miniF2F C COMPLETE 183/183, aggregated. pass@8k=0.0%±0.0, pass@32k=0.0%±0.0 on the 61 trapped
problems — diversity injection solved ZERO (vs Goedel miniF2F's 1-2 cell blip 0.6/1.2%). Both miniF2F
arms confirm the pre-registered prediction (solves flat/null on trapped) ACROSS BOTH PROVERS.
ProofNet# arms still running clean (0 failures): Goedel 182/450, DeepSeek 123/420.
Budget-matched A1 manipulation check still pending (run once all 4 done).

## 2026-06-18f — STEP C COMPLETE (all 4 arms): F5 confirmed interventionally, both provers
All 4 diversity arms done + aggregated. FULL readout via scripts/stepc_readout.py (budget-matched).
VERDICT: pre-registered prediction CONFIRMED on Goedel+DeepSeek × miniF2F+ProofNet#.
- MANIPULATION CHECK PASSED (budget-matched @32k, attempts matched): diversity raised distinct openings
  per attempt +44/42/68/70% (abs distinct-first-tactic ~1.0-1.3 -> ~1.7-1.8). Intervention fired => null
  is interpretable.
- SOLVES NULL: trapped pass@8k/32k = Goedel miniF2F 0.6/1.2, Goedel ProofNet# 0/0.7, DeepSeek miniF2F 0/0,
  DeepSeek ProofNet# 0/0 (%). Exactly 5 genuine verified flips total (2 Goedel miniF2F, 3 Goedel ProofNet#,
  0 DeepSeek), all within seed-std. Approach discovery is NOT the bottleneck; within-approach execution
  (F2/F3 reasoning floor) is. Closes F5's correlational gap interventionally on 2 provers.
- SECONDARY: diversity DEGRADES quality — last-attempt failures shift reasoning_deep(38-88%)->~0, become
  majority formalization_syntax(62-74%)+loophole_sorry(23-36%); soundness rates creep up (loophole ~3x:
  1-3%->4-10%; syntax 1.5-2x). ALL caught by the fixed verifier (0 false solves) => result soundness
  intact; forced-diversity scaffolding is mildly COUNTERPRODUCTIVE not neutral. Reinforces soundness contribution.
BOTTOM LINE: compute budget, not agentic scaffolding, is the lever for whole-proof proving at this scale,
across 2 models, with the verifier-soundness caveat. Phase 1 OFAT-null + Phase 2 mechanism (F1-F4) +
F5 correlational + F6/Step C interventional all converge. New artifact: scripts/stepc_readout.py.
NEXT: consolidate the paper-shaped writeup (SYNTHESIS.md) tying Phase 1 + Phase 2 (F1-F6) across both
provers + the soundness thread; figures (pass@B both models both benchmarks; manip-check vs solves bar).

## 2026-06-20 — Phase 3 H1 (PASS) + H2 (taxonomy correction — revises F2's retrieval justification)

H1 — dichotomy on the compile-on-both-pins INTERSECTION. PASS, gap is REAL.
- Both models attempted IDENTICAL statement sets (244 miniF2F, 186 ProofNet#; 0 disjoint names).
- Statement elaboration on BOTH pins = 100%: Goedel v4.9.0-rc1/mathlib 2f65ba7 244/244 + 186/186 (jobs
  10750335/6); DeepSeek v4.9.0/mathlib f0957a7 244/244 + 186/186 (build gate). 0 failures either pin.
- => intersection = full set; native pass@B == intersection pass@B for all 4 arms (scripts/h1_intersection.py,
  which reproduces metrics.json exactly). The cross-model dichotomy (DeepSeek 22.2 vs Goedel 14.3 @128k
  ProofNet#, gap widens with budget) is NOT a port/coverage artifact. Lean on it (with R1 training-not-size).

H2 — human-validated the failure taxonomy. The original "F2: ~0% knowledge / 94-100% reasoning_deep" is an
ARTIFACT of A2's CELL-level most-advanced labeling (reasoning_deep outranks knowledge in priority, so any
cell with >=1 deep attempt is tagged reasoning_deep, masking its knowledge-failure attempts). Corrected,
ATTEMPT-level taxonomy (scripts/h2_taxonomy_audit.py), with REPL-infra crashes + markdown-prose split out:
  miniF2F (in-dist): reasoning_deep 78.9%/82.1% (Goedel/DeepSeek), KNOWLEDGE 1.7%/1.8% — original claim HOLDS.
  ProofNet# (OOD): Goedel  reasoning_deep 38.9%, syntax 16.2%, INFRA-crash 14.6%, KNOWLEDGE 13.3%, shallow
                   8.0%, markdown 6.8%, loophole 2.1%.
                   DeepSeek reasoning_deep 58.4%, syntax 18.1%, KNOWLEDGE 12.6%, shallow 6.5%, markdown 2.3%.
TWO corrections: (a) KNOWLEDGE/missing-identifier is ~13% on OOD, NOT ~0% — read the unknown ids: a mix of
real-concept-wrong-name (Finrank->finrank, Open->IsOpen, Compact->IsCompact, IsGroupHomomorphism->IsGroupHom)
which ARE retrievable in principle, plus invented composites (Submodule.map_sum, exists_normal_Sylow).
(b) ~14.6% of Goedel ProofNet# attempts are REPL-infra crashes mislabeled reasoning_shallow (infra noise).
CONSEQUENCE: the retrieval-kill CONCLUSION still holds EMPIRICALLY (Phase 1: BM25 retrieval HURT -36 net on
ProofNet#), but its MECHANISTIC justification must change from "nothing to retrieve (~0% knowledge)" to "BM25
premise selection injects distractors rather than the needed identifier; ~13% of OOD failures ARE knowledge/
name-resolution gaps, so a targeted premise/name-resolution method is NOT ruled out by the mechanism (untested,
future work)." Core thesis (budget is the dominant lever; tested components don't help; F1/F3/F5/F6; dichotomy)
is UNAFFECTED. TODO at doc-rewrite: fix F2 in MECHANISM.md + SYNTHESIS.md accordingly; soften F3 (R2); add
infra category to analyze_mechanism._classify.

## 2026-06-20 — Phase 3 H4: OOD dichotomy = deeper EXECUTION, not more diversity (unifies the thesis)
Decomposed DeepSeek's ProofNet# advantage (46 vs 36 problems solved on the shared 186) via F1/F3
(scripts/h4_decompose.py). Two independent views agree:
- WIN ATTRIBUTION (14 DeepSeek-only wins): 100% EXECUTION / 0% APPROACH — in all 14, Goedel TRIED the
  same opening tactic DeepSeek won with but failed to close it. (Caveat: first-tactic `have` is ubiquitous
  so this is a coarse upper bound on execution-wins.)
- MATCHED-DIFFICULTY (136 problems BOTH models fail, removes survivorship): DeepSeek explores FEWER
  distinct openings (3.08 vs Goedel 4.07) yet reaches DEEPER (median deepest-step 29 vs 24).
=> DeepSeek's OOD edge is DEEPER WITHIN-APPROACH EXECUTION, not more approach diversity. It uses the same
approaches, diversifies LESS, but closes goals Goedel stalls on. UNIFIES the thesis: search-time scaffolding
(Phase 1 null + F6 Step C forced-diversity null) cannot move the execution floor, but the prover's TRAINING
can, substantially, on OOD. The real OOD lever is the MODEL (training-distribution/recipe, R1 — NOT size),
not search-time scaffolding. Also internally consistent: Goedel diversifies MORE yet solves FEWER (more
openings != more solves), echoing F1 + the Step C null.

## 2026-06-20 — Phase 3 H3: soundness-creep across components — PARTIAL (scope the claim honestly)
scripts/h3_soundness.py: per-failed-attempt "unsound surface" = loophole(sorry) + truncation(no_goal) =
the would-be-false-positive modes a NAIVE verifier would accept. Per component vs its matched baseline:
  miniF2F (base surface 18.8%): retrieval +3.1, budget_alloc__0 +3.3, budget_alloc__2 +1.8 (inflate);
    memory +0.2, reviewer +0.4, tactic_skeletons -1.0 (flat); diversity(Step C) +6.6 vs its baseline.
  ProofNet# (base surface 16.2%): ALL Phase 1 components DECREASE the surface (retrieval -11.8, budget_alloc__0
    -5.7, ...) — they trade sorry-loopholes for honest compile_errors; diversity(Step C) +3.3 vs its baseline.
VERDICT: the strong generalization "scaffolding SYSTEMATICALLY shifts output toward less-sound regions" is
NOT supported — it's mixed (inflates on miniF2F for retrieval/budget_alloc; reduces on ProofNet# as the
failure mix shifts to compile-errors). What IS robustly supported and citable:
  (1) the BASELINE would-be-false-positive surface is LARGE (~16-19% of failed attempts carry sorry/no-goal,
      3-19% across runs) — verifier hardening is NON-OPTIONAL independent of scaffolding;
  (2) FORCED-DIVERSITY (Step C) reliably inflates the surface (+3 to +7pp on both benchmarks);
  (3) throughout, the FIXED verifier caught everything — 0 false accepts (soundness of results intact).
So scope the H3 claim to (1)+(2)+(3), NOT a blanket "all scaffolding inflates unsoundness."
ALL FOUR HARDENING CHECKS DONE (H1 pass, H2 revise F2, H4 unify, H3 scope). Next: apply reframes to docs
(F2 attempt-level + knowledge~13% OOD; R1 training-not-size; R2 soften F3; add infra category) then write.

## 2026-06-20 — Hammer probe Arm 0 = 0/30 (CONFIRMED): the floor is not an automation gap
Arm 0 (on-pin portfolio omega/nlinarith/norm_num/simp_all/decide/aesop on ORIGINAL trapped statements),
30 Goedel ProofNet# trapped problems: 0/30 closed (job 10752062). Positive control (job 10752946):
portfolio closes 4 synthetic trivial goals incl the `first|...` combinator (ALL PASS) -> the 0/30 is real,
not a silent bug. CONCLUSION: the trapped floor is NOT an automation-invocation gap — the model already
invokes nlinarith/simp/omega inline (per H2), and basic automation on the bare statement closes nothing.
=> Arm B (hammer on bare statement) is unlikely to help on hard OOD theorems; the value (if any) is Arm A
(symbolic closer at the model's STUCK LEAF). Next: cheapest Arm-A-lite = replace the model's single failing
tactic with the portfolio combinator in-context, verify (no new infra, sound — verifier gates). If that
closes >0, justifies proofState extraction + duper; if 0 (with Arm0=0), strong NO-GO that strengthens the
negative thesis. DO NOT port duper until Arm-A-lite shows life (validate-premise-before-building).

## 2026-06-20 — Hammer probe Arm-A-lite = 0/40; go/no-go = NO-GO (portfolio level)
Arm-A-lite (swap model's failing tactic -> portfolio combinator in-context), 40 Goedel ProofNet# trapped:
0/40 closed (job 10753705; all 40 located+probed). With Arm0=0/30 + positive-control PASS, the on-pin
portfolio gives ZERO leaf-closing synergy. CALL: NO-GO on current evidence — do NOT port duper. Caveats:
(1) portfolio != hammer (a real superposition/SMT closer reasons beyond it; not tested — needs v4.9.0 port
+ proofState extraction); (2) recall-lossy (0/40 is a lower bound; nested failures = broken swaps). EV of
the duper build is low given converging negatives (Arm0=0, ArmA-lite=0, H4 execution-floor, Step C null,
nested-degenerate proofs). Fold into the negative thesis as a strengthening result + reviewer-objection
pre-empt. Decisive follow-up if wanted: proofState extraction + duper@v4.9.0 (~1-2 days). Full writeup:
results/phase3/HAMMER_PROBE.md.

## 2026-06-20 — Off-pin Arm-B elaboration gate PASSED (≥71%); proceeding to real-hammer build
Gate 1 (do trapped ProofNet# statements elaborate in sibling v4.29.0 mathlib): 106/150 (71%) elaborate
(job 10757662; after two probe-bug fixes — missing `open` preamble, then the count grep wanted v4.29's
backtick `declaration uses \`sorry\`` not single-quotes). The ~44 non-elaborating are MOSTLY shallow
missing-opens (Tendsto/limsup/𝓝→open Filter; Icc/Ioi→Set; IsTopologicalBasis/MetrizableSpace→Topology;
sqrt/sin→Real; End/finrank/ker→Module), not deep drift — true rate is higher with full opens. Off-pin
Arm B is VIABLE. The real Arm-B run (Pantograph, per-statement) elaborates each goal individually so the
count falls out of the run (no batch-file collisions). NEXT (Gate 2): stand up a real hammer (duper, pure-
Lean) on an ISOLATED copy of theorem-proving-research/lean_env, then run Arm B via PyPantograph on the
elaborating trapped statements (60-90s/goal). NO-GO stays UNLOCKED until a real hammer runs (reviewer point).

## 2026-06-20 — Off-pin Arm-B build: isolated path (in progress; smoke failed on proxy+LEAN_PATH, fixed)
First Arm-B smoke (10759553) failed: (A) `lake update Duper` git clone -> code 128 (compute node can't use
the login per-session proxy; direct git blocked); (B) Pantograph couldn't find Mathlib (raw Server needs
LEAN_PATH; sibling client computes it). Diagnosed + de-risked:
- duper v4.29.0 deps = lean-auto@v4.29.0-hammer + batteries@v4.29.0; batteries v4.29.0 == env's 756e3321
  EXACTLY -> adding duper does NOT rebuild mathlib. Disk fine (620T free; earlier 99% was transient).
- Classifier (correctly) blocked modifying the SHARED sibling lean_env in place -> using an ISOLATED COPY
  (scratch/lean-cache/lean_env_duper, copying now ~7.3G).
PLAN: (1) copy done -> add duper require to the COPY's lakefile; (2) `lake update Duper` on LOGIN (network
works there; clones duper+auto into the copy; verify batteries unchanged); (3) sbatch slurm/offpin_arm_b.sh
(staging copy->/local, `lake build Duper` OFFLINE on compute, export LEAN_PATH from filesystem, run
scripts/hammer_arm_b_pantograph.py). Smoke ARM_B_LIMIT=8 first, then full 150. NO-GO stays UNLOCKED until
the real-hammer (duper) number lands. NB the off-pin Arm-B build is more involved than the reviewer's
"few hours" estimate (compute-node proxy + duper's lean-auto transitive dep + isolation), but feasible.

## 2026-06-20 — Off-pin Arm-B SMOKE healthy: real hammer (duper) runs; 0/7 closed (small sample)
Smoke (job 10761092) end-to-end SUCCESS: lake build Duper OFFLINE on compute (duper 74 + auto 78 oleans,
NO mathlib recompile, deps reused); LEAN_PATH from filesystem worked; Pantograph started (server ready 8s,
found Mathlib+Duper). Of 8 trapped Goedel ProofNet# statements: 7 elaborated, duper CLOSED 0/7 (failures
are genuine 'Duper failed to prove'/'Duper encountered' = real superposition attempts at 90s, not infra).
=> the REAL-hammer pipeline the reviewer required now WORKS. Launching FULL 150 for the decisive number.
Pipeline cost note: ~13min/job (382s stage + fast offline build + 8 stmts); full 150 ~2-3h.

## 2026-06-20 — Off-pin Arm B DECISIVE: duper (real superposition prover) closes 0/119 trapped
Crash-robust rerun (job 10762328) COMPLETE: 150/150 processed, 34 server restarts (survived the duper OOMs
that killed the prior run at stmt 48). ELABORATED 119/150, duper CLOSED 0/119. Failures genuine ('Duper
failed to prove' = saturated search; few 90s timeouts). So a real superposition prover on the full
elaborable trapped statement set (<=90s each) closes ZERO. With Arm0=0/30 (portfolio bare) + ArmA-lite=0/40
(portfolio at leaf): Δ ProofNet# pass@B = 0pp, far below the <2pp NO-GO threshold.
NUANCE (being fair to the reviewer's premise-selection point): bare `duper` = the superposition PROVER;
the full hammer adds mathlib-wide PREMISE SELECTION (lean-auto). Checking if lean-auto's premise-selection
tactic is runnable as a final fairness variant before locking NO-GO.

## 2026-06-20 — Phase 4 Task 4.1: oracle ceiling = MASSIVE headroom (proceed to realizable policies)
Pivot to the POSITIVE result (compute-optimal budget allocation; see memory atp-phase4-plan). Built
src/atp/alloc/ (extract + policies: solve_cost/uniform/oracle/oracle_min_T) on the §0 identity
solved(cell,b)==(tokens_to_solve<=b), 10 tests incl real-cell identity + uniform-reproduces-logged-
pass@B (exact) + oracle≥uniform. Fast suite 288 green, ruff clean. scripts/phase4_ceiling.py over all
4 budget-independent baselines -> results/phase4/ceiling.json:
  EFFICIENCY ceiling (oracle matches uniform@128k solve rate for far less compute):
    goedel  miniF2F   95.2% saved (4.53M vs 93.7M tok)   |  goedel  ProofNet# 98.1% (1.35M vs 71.4M)
    deepseek miniF2F  95.1% saved (4.58M vs 93.7M tok)   |  deepseek ProofNet# 96.9% (2.22M vs 71.4M)
  ACCURACY ceiling (oracle vs uniform at EQUAL total compute T=N×b), headline mid-budgets:
    goedel ProofNet#:  +9.1pp @2k, +5.0pp @8k, +2.3pp @32k, 0 @128k
    deepseek ProofNet#:+14.5pp @2k, +9.1pp @8k, +3.9pp @32k, 0 @128k
    miniF2F (both):    ~+35pp @2k, ~+14.8pp @8k (huge low-budget upside)
Solve-cost distn is heavy-tailed (ProofNet# Goedel: med 3855, p90 61613, max 124116) -> over-funding
reclaim is real AND the trapped ~80% (cost=inf, never funded) is the big efficiency source. Ceiling
clears the STRONG threshold (≥30% saved OR ≥+5pp) by a wide margin on every cell. NB accuracy delta=0
at 128k/cell (oracle can't solve unsolvable cells; the upside is a CONSTRAINED-budget phenomenon; the
efficiency win — same final accuracy for ~2-5% of compute — is the robust headline). GATE = GO:
proceed to Task 4.2/4.3 realizable policies (successive-halving + learned difficulty predictor) — the
real question is now how much of this ceiling a policy using only during-run F1/F3 signals can capture.

## 2026-06-20 — Phase 4 Task 4.3 check-in: predictability AUC-vs-checkpoint (MODERATE, peaks mid-run)
Built src/atp/alloc/features.py (leakage-free checkpoint features) + predict.py (grouped-CV AUC).
KEY DATA WIN: the whole-proof verifier already logs "Failed at step N" (97.8% of ProofNet# failures,
100% have completion_tokens) → real F3 step-depth is FREE, no error-locus parse and no length-proxy
needed; the staged plan collapsed to "cheap == faithful". Feature set: tokens_so_far, n_attempts,
best_depth, last_depth, depth_growth, stalled_attempts (plateau), distinct_openings (F1), compiled_
past_step1. 20 alloc tests incl causality (only attempts finished by c) + no-leakage + grouped-CV
no-problem-in-both. Added scikit-learn 1.9.0 to the atp env (login-node pip WITH proxy; compute-node
unset still applies).

scripts/phase4_predictor.py (predict eventual-solve among still-RUNNING cells, problem-grouped 5-fold
CV) -> results/phase4/predictor.json. ProofNet# (EV) AUC_logistic by checkpoint:
  goedel   ProofNet#: 2k .64 | 4k .71 | 8k .75 | 16k .72 | 32k .46(13 pos, noise)
  deepseek ProofNet#: 2k .47 | 4k .65 | 8k .67 | 16k .72 | 32k .62
  miniF2F both: rises to .73-.75 by 32k.
FINDINGS: (1) MODERATE predictability ~0.65-0.75, peaks MID-run (c≈8-16k). (2) Logistic > GBT almost
everywhere (GBT overfits the tiny positive class) → logistic is the realizable model. (3) Top feature
is consistently tokens_so_far = elapsed-spend-without-success (a survival/hazard signal); depth_growth
(the plateau/stuck signal) becomes a top-3 feature at c=16k as predicted; best_depth/last_depth carry
the early checkpoints. So the cheap feature set works; error-locus F3 NOT needed (best_depth already IS
real depth). IMPLICATION for capture: moderate AUC means EFFICIENCY capture can still be high (only need
to confidently abandon obviously-trapped cells, high-precision/low-recall), but ACCURACY capture (needs
good ranking) will be more limited. Next: simulate the realizable policy (successive-halving + predictor
abandonment) to measure ACTUAL capture vs the oracle frontier — that's the headline number.

## 2026-06-20 — Phase 3 hammer NO-GO fully LOCKED: lean-auto full = 0/119 (matches duper)
Full lean-auto premise-selection run (job 10772318, ARM_B_TIMEOUT=180 after 10771425 died on a <90s
Pantograph server-startup timeout — pure infra, not a result): elaborated 119/150, CLOSED 0/119, same
as duper full (0/119). So on the full elaborable trapped ProofNet# set, BOTH a real superposition prover
(duper) AND mathlib-wide premise selection (lean-auto `auto`) close ZERO. Δ ProofNet# pass@B = 0pp, far
under the <2pp NO-GO threshold. Hammer thread CLOSED: scaffolding/automation null is robust to the
reviewer's "did you try a real hammer + premise selection" challenge. Decisive artifacts:
arm_b_duper_FULL_0of119.json + arm_b_auto_FULL.json. Negative thesis ("Budget, Not Scaffolding") stands;
the positive contribution is Phase 4 (compute-optimal allocation).

## 2026-06-20 — Phase 4 Task 4.3-4.4: efficiency frontier = POSITIVE on ProofNet# (STRONG on Goedel)
Built src/atp/alloc/frontier.py (uniform/oracle/realizable curves on one compute-vs-solves axis; OOF
predictions, no leakage) + scripts/phase4_frontier.py -> frontier.json + 4 PNGs + results/phase4/
ALLOCATION.md. 25 alloc tests, fast suite 303 green, ruff clean.
KEY RESULT (realizable = abandon predictor-flagged-trapped at c*=argmax-AUC, reallocate; honest OOF):
  goedel  ProofNet#: save +15%@80acc, +30%@90, +24%@95, -2%@100  -> STRONG (≥30% @90%)
  deepseek ProofNet#: -16/+10/+1/+14  -> POSITIVE (noisier, AUC 0.72)
  miniF2F both: NEGATIVE (contrast; ~75% solve rate => little wasted compute to reclaim, as preregistered)
TWO honest caveats baked into the writeup: (1) win is at FRACTIONAL accuracy (90-95%), ~0 at 100% — the
hardest winnable cells cost ≈128k = indistinguishable from trapped (recall wall, not a tuning failure);
(2) efficiency is the robust axis (accuracy-at-fixed-compute only +0.2-0.5pp) because the single
checkpoint imposes a compute floor c*·N blocking the cheap regime. Realizable captures ~1/3 of the
oracle's ~98% ceiling on Goedel ProofNet#@90%. predictor.json AUC moderate 0.65-0.75 peak mid-run;
top feature tokens_so_far (survival signal), plateau depth_growth top-3 at c=16k, F1 never ranks;
logistic>GBT. Frontier PNG shows realizable above uniform through the 5-35M-token band. NEXT (optional):
successive-halving (lower floor) to lift DeepSeek + loose targets; small live confirming run (Task 4.4).
