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
- [ ] Config system: pydantic vs OmegaConf (pick one, note why).
- [ ] Training stack for Phase 2: TRL vs minimal GRPO (decide at Phase 2 start).
