# 32B calibration cell — feasibility scope (2026-07-26, free check, no GPU spend)

Requested by the user's paper-strength review as the highest-value remaining experiment; user's
2026-07-26 follow-up: draft first, but scope feasibility now since it's free and may resolve the
question either way before committing GPU-hours.

## Model
`Goedel-LM/Goedel-Prover-V2-32B` exists on HF (confirmed via `HfApi.model_info`). Config: Qwen3ForCausalLM,
hidden_size=5120, 64 layers, vocab 151936, `torch_dtype=bfloat16`, max_position_embeddings=40960 (same
context length class as the 8B). Total weight size (from `model.safetensors.index.json`): **65.52 GB**
in bf16 -- roughly 4x the 8B model's footprint, consistent with param count scaling.

## Does it fit this cluster without quantization?
A single l40s (48GB VRAM) cannot hold 65.5GB of weights alone. BUT `sinfo` shows **dual-l40s nodes
(`gpu:l40s:2`, 96GB combined) are available on the `short`/`burst`/`edu`-accessible partitions this
project already uses** (ins038-039, ins056-061, ins063 — the same partitions Phase 0-8 ran on). vLLM's
tensor-parallel serving (`--tensor-parallel-size 2`, a standard, well-supported feature for this vLLM
version 0.8.5.post1 / Qwen3 architecture) splits the model across both GPUs. 96GB total minus 65.5GB
weights leaves ~30.5GB for KV cache + activations across both GPUs -- tight but workable at the
project's usual n_workers concurrency (likely needs a lower n_workers than the 8B's n_workers=8, to be
tuned empirically rather than assumed).

**Verdict: no quantization needed.** The confound the user flagged ("a quantized 32B that
underperforms its published numbers tells you nothing about scale") does not apply -- this would be
the actual published bf16 model, served faithfully, just across 2 GPUs instead of 1.

## What it would actually cost
- Engineering: a new slurm script variant (copy of `slurm/calibration_trapped32_*` with
  `--gres=gpu:l40s:2` + vLLM `--tensor-parallel-size 2` + likely reduced `n_workers`), plus a new
  `configs/calibration_trapped32_goedel32b_minif2f.yaml`. Modest -- a few hours, not an infra project.
- GPU-h: the original estimate (~60-100 GPU-h) used 1-GPU-hour units; on 2 GPUs the WALL-CLOCK time
  may be similar to or somewhat longer than the 8B cell's wall-clock (larger model, TP communication
  overhead), but GPU-HOUR accounting doubles per wall-hour (2 GPUs running simultaneously) -- so the
  effective GPU-h cost is plausibly higher than the original single-GPU-equivalent estimate, likely in
  the 80-150 GPU-h range pending an actual smoke-test timing measurement. This still needs a real
  timed smoke test before committing to the full 55-problem array, per this project's own "smoke
  before scale" rule (CLAUDE.md rule 5) -- not estimated further here without one.
- Disk: 65.5GB new model download into `scratch/hf-cache` (or wherever `ATP_HF_HOME` points for this
  run) -- filesystem has ~1.2TB free (`df -h /insomnia001`), not a constraint.

## Decision (per user, 2026-07-26)
**Not run now.** Drafting proceeds first (explicit user call: "drafting shouldn't wait... the last
several rounds all landed as confirmations"). This feasibility scope is recorded so that IF drafting
surfaces the scale limitation as structurally load-bearing (not just a limitations-section sentence),
the decision to spend the GPU-h is an informed one, not a fresh investigation. If drafting shows the
scale caveat is adequately handled by an honest limitations statement ("established at 7-8B; whether
the floor persists at 32B+ is untested and is the most important open question"), this cell may never
need to run, and that is a legitimate, defensible scope choice per the user's own framing.
