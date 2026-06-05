# DECISIONS.md

Append-only log of design decisions. One entry per decision: date, decision, one-line rationale.
Never edit or delete past entries — supersede with a new dated entry if you change your mind.

---

### 2026-06-04 — Budget unit = LLM-generated tokens
Per-problem compute budget `B` is measured in total generation tokens summed across all model calls
(proposals, refinements, tactic steps). Rationale: reproducible across GPU types in a way wall-clock
is not. We also log wall-clock + GPU-hours for cross-checking, but **report** against token budget.
(Revisit if the team prefers GPU-seconds; it's a localized change in `src/atp/budget/`.)

### 2026-06-04 — Headline metric = pass@B curve, not pass@k
Report fraction solved within fixed budget `B`, as a curve over several `B` (e.g. 2k/8k/32k/128k
tokens), ≥3 seeds, mean±std. Rationale: this is the honest, novel axis for compute-constrained groups
and the framing that differentiates us from frontier pass@(thousands) results.

### 2026-06-04 — Base models: Goedel-Prover-V2-8B (primary) + BFS-Prover-V1-7B (tactic comparator)
Both open-weight and runnable/fine-tunable on our cluster. Goedel for whole-proof generation,
BFS-Prover for the tactic-level search axis in Phase 1. Rationale: strongest open small provers; lets
us study generation-mode crossover without training a prover from scratch.

### 2026-06-04 — Inference via persistent vLLM server; agent talks over HTTP
Decouples serving from agent logic, enables clean token accounting and throughput. Serve on l40s,
agent runs as separate (possibly CPU-light) process reading the endpoint from
`results/_vllm_endpoint.txt`.

### 2026-06-04 — Benchmarks: audited miniF2F + ProofNet#, with a novel/held-out split
Use corrected/audited splits and drop known-unprovable miniF2F items. Lead headline claims with the
novel split to mitigate contamination. Rationale: standard benchmarks are buggy and contamination is a
real reviewer concern.

### 2026-06-04 — Network confirmed available on compute nodes
Compute nodes have outbound access, so model/data download can happen in-job. Still set `HF_HOME` to
`scratch/hf-cache` so we don't re-download across jobs.

### TODO (decide in Task 0.2, then log here)
- [ ] **mathlib commit** and **Lean toolchain version** to pin (lock day one; record exact hashes).
- [ ] Training stack for Phase 2: TRL vs minimal GRPO (decide at Phase 2 start).

---

### 2026-06-04 — Config system = pydantic v2 (not OmegaConf) — RESOLVES Task 0.1 TODO
`src/atp/config.py` defines typed pydantic models mirroring `configs/base.yaml`, with
`extra="forbid"` so a typo'd or misplaced key fails loudly at load time (caught by a unit test).
Loader handles `defaults: base` by deep-merging the override onto the base config, then validating.
Rationale: typed validation + clear error messages + lossless round-trip (`load->dump->load`) matter
more here than OmegaConf's interpolation; one fewer dependency. `omegaconf` dropped from deps.

### 2026-06-04 — Dependency install split into LIGHT CORE (now) vs HEAVY GPU/LEAN (deferred)
Shared filesystem `/insomnia001` is at **100% (only ~20 GB free on the 5 TB mount)**. A full
`torch`+`vllm`+`lean-dojo` install (~10–15 GB) risks failing mid-install and starving other users on
this department space. So Task 0.1 installs only the light core needed for the fast suite + tooling
(env footprint **580 MB**); `torch/vllm/transformers/datasets` → `[gpu]`, `lean-dojo` → `[lean]`,
`trl/peft` → `[train]` optional groups, pinned when first installed (Task 0.2/0.3). **Flagged to the
team; awaiting go-ahead on the heavy install / disk cleanup before Task 0.2's Lean build.**

### 2026-06-04 — Light-core pinned versions (frozen on Insomnia, python 3.11.15)
pydantic==2.13.4 · pydantic-core==2.46.4 · PyYAML==6.0.3 · numpy==2.4.6 · pandas==3.0.3 ·
matplotlib==3.10.9 · rank-bm25==0.2.2 · tenacity==9.1.4 · openai==2.41.0 · huggingface-hub==1.17.0 ·
pytest==9.0.3 · pytest-timeout==2.4.0 · ruff==0.15.16 · setuptools==82.0.1. Recorded in
`pyproject.toml` `dependencies`. Rationale: reproducibility rule — exact pins, no floating ranges.

### 2026-06-04 — src/ layout, installed editable with `pip install -e . --no-deps`
Package lives under `src/atp/`; `[tool.setuptools.packages.find] where=["src"]`. Installed
`--no-deps` so the editable install does not pull the deferred heavy stack. Top-level `atp/__init__`
imports must stay light (no torch/vllm/lean at import time) so the fast suite runs on a login node.
Rationale: keeps the marker-gated fast/slow test split honest.

### 2026-06-04 — HF_HOME pointed into scratch via `apply_env(config)`
`config.project.hf_cache = scratch/hf-cache`; `apply_env` resolves it against `project.root` and sets
`HF_HOME` so model/data downloads land in shared scratch, never `$HOME` (storage-hygiene rule).
CLI entrypoints call it before any HF use.

### 2026-06-04 — Lean/mathlib pins LOCKED — RESOLVES Task 0.2 TODO (verified, not guessed)
**Lean toolchain:** `leanprover/lean4:v4.9.0-rc1`.
**mathlib4:** commit `2f65ba7f1a9144b20c8e7358513548e317d26de1` (2024-08-07) from the FORK
`https://github.com/xinhjBrant/mathlib4.git` (NOT upstream leanprover-community/mathlib4).
Rationale: this is the exact submodule (`mathlib4 @ 2f65ba7…`, url `xinhjBrant/mathlib4`) that
Goedel-Prover-V2 pins for compiling/verifying proofs; matching it makes our verifier agree with the
proof format the prover model was trained to emit. Verified by reading the repo's `.gitmodules` + root
tree submodule pointer and fetching `lean-toolchain` at that commit (the official-mathlib API 404'd on
this SHA, confirming it is fork-specific). Recorded into `configs/base.yaml` (`lean.toolchain`,
`lean.mathlib_commit`) + a new `lean.mathlib_repo`. The actual `lake build` of this mathlib into
`scratch/lean-cache` is DEFERRED (disk hold) — pin is locked now; build happens once disk is freed.
Flagged to the team before writing the Lean layer, per the Task 0.2 instruction.

### 2026-06-04 — Disk: filesystem has headroom (672 TB free); "100%/20 GB" was a stale view — SUPERSEDES the disk-hold note
Re-checked `df -h /insomnia001`: **1.7 PB filesystem, 61% used, ~672 TB available.** The earlier
"100% / ~20 GB free on a 5 TB mount" figure does not reflect the live filesystem (likely a transient
or a per-view/quota number captured during Task 0.1). So **raw space is not a blocker** for the heavy
install. The heavy `[gpu]`/`[lean]` install + multi-hour `lake build` are still deferred for a
different reason: they belong on a GPU/compute node (per CLAUDE.md) and shouldn't be kicked off
unattended from a login node. Action: confirm a per-project quota (if any) with the team, then run the
heavy install + `lake build` inside an interactive `srun` session. Token/verify code paths remain
fully mock-tested meanwhile.

### 2026-06-04 — Task 0.3 design: budget meter as the enforcement seam; vLLM via a `Transport` abstraction
**Budget meter (`src/atp/budget/meter.py`).** `BudgetMeter` is the single source of truth for the
per-problem token budget `B`. Accounting uses the server-reported `usage.completion_tokens` — never a
local estimate — so the budget equals what the GPU actually generated. API split: `request(n)` clamps
the next call to `min(n, remaining)` and raises `BudgetExhausted` when nothing remains (clean,
catchable stop — the agent saves partial state, doesn't crash); `spend(actual, label)` charges the
ledger after the call. `snapshot()`/`restore()` round-trip the spend+ledger for requeue (rule 0.3).
Rationale: clamp-then-spend keeps generations inside budget while accounting stays exact even if a
server returns a hair more than requested.

**Model client (`src/atp/models/client.py`).** `VLLMClient` talks to the persistent vLLM server over
a `Transport` Protocol: `OpenAITransport` (real — uses the `openai` SDK against vLLM's OpenAI-compatible
`/v1/completions`, `openai` **imported lazily** so `import atp.models` stays light) vs
`ScriptedTransport` (tests/smoke — exact token control, records payloads). Chose the `openai` SDK over
raw HTTP because it's already a pinned light-core dep and matches the "persistent vLLM + HTTP" decision
above. `generate()` is budget-aware: clamps `max_tokens` via the meter, then charges the returned
`completion_tokens`.

**Prompt templates (`src/atp/models/templates.py`).** `WholeProofTemplate` (Goedel-Prover-V2-8B) and
`TacticTemplate` (BFS-Prover) behind a `PromptTemplate` Protocol, selected by
`config.model.prompt_template`. Whole-proof renders a `lean4` fenced scaffold and extracts the **last**
fenced block from the completion (models draft in earlier blocks); tactic mode returns the first
non-empty line. NOTE: instruction wording follows the published model cards — if a card revision drifts,
update here and log it (the served `revision` is pinned, so prompt changes are deliberate + audited).

### 2026-06-04 — Task 0.4 design: budget is the stopping criterion; state checkpointed every attempt
**Loop shape (`src/atp/agents/whole_proof.py`).** `WholeProofAgent` runs *rounds*: a fresh proposal
then up to `max_refine` error-fed refinements, repeating rounds until solved or budget-out. The
**budget meter is the real stopping criterion** — `client.generate` raises `BudgetExhausted` when the
ledger is empty, which the agent catches as a clean stop (`stop_reason=budget_exhausted`), never a
crash. `max_rounds` is only a safety cap so a generous budget can't spin forever. Rationale: keeps the
loop honest to the project's central knob (fixed token budget) rather than an iteration count.

**State + resume (`src/atp/agents/state.py`).** `AgentState` checkpoints after *every* attempt
(atomic tmp+rename, so a preempt mid-write can't corrupt it) and carries the `BudgetMeter` snapshot.
On resume: a *finished* checkpoint short-circuits (no work redone); an *unfinished* one restores the
meter so spend continues from where the killed job stopped (rule 0.3). The attempt trail is retained
for later analysis / Phase-2 trajectory collection. Per-problem file fits the planned
`results/<run>/problems/<id>.json` layout.

**Dependency injection.** The agent takes an injected `VLLMClient` (carrying the meter) + `Verifier`,
so the whole loop is exercised end-to-end in the fast suite with `ScriptedTransport`+`ScriptedBackend`
— no GPU/Lean. The scripted server honors the meter's clamped `max_tokens`, so mocked budget
accounting equals production. The real end-to-end solve is a single `lean+gpu+slow` test, deferred
with the compute-node install.
