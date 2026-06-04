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
