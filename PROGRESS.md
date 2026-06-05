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
