# Reproducibility pins

Exact model revisions, Lean toolchains, and mathlib commits for every headline result in this paper.
Source of truth: `configs/base.yaml` (Goedel), `configs/deepseek_minif2f_baseline.yaml` /
`configs/deepseek_proofnet_baseline.yaml` (DeepSeek), cross-checked against `DECISIONS.md` 2026-06-04
(Lean/mathlib pins locked) and 2026-06-05 (model revision pinned).

## Goedel-Prover-V2-8B (Sections 3-9 headline results)

- **Model:** `Goedel-LM/Goedel-Prover-V2-8B` @ revision `dfd02e6271a58375dfbf3ece0175277cf6b6a89a`
  (pinned 2026-06-05, HuggingFace `main` branch at pin time).
- **Lean toolchain:** `leanprover/lean4:v4.9.0-rc1`.
- **mathlib4:** commit `2f65ba7f1a9144b20c8e7358513548e317d26de1` (2024-08-07), from the **fork**
  `https://github.com/xinhjBrant/mathlib4.git` (not upstream `leanprover-community/mathlib4`) --- this
  is the exact submodule pin Goedel-Prover-V2's own training/eval repository uses, verified against its
  `.gitmodules` and `lean-toolchain` files at pin time (DECISIONS.md 2026-06-04). This fork is
  custom-patched relative to upstream mathlib (its oleans are not hosted in mathlib's build cache;
  `lake exe cache get` returns 0% hits), so mathlib was built from source for this pin.

## DeepSeek-Prover-V2-7B (Sections 3-9 headline results)

- **Model:** `deepseek-ai/DeepSeek-Prover-V2-7B`.
- **Lean toolchain:** `leanprover/lean4:v4.9.0`.
- **mathlib4:** commit `f0957a7575317490107578ebaee9efaf8e62a4ab`, from **upstream**
  `https://github.com/leanprover-community/mathlib4.git` (standard mathlib, not a fork) --- this is
  the pin DeepSeek-Prover-V2's own release verifies against.

## DeepSeek-Prover-V1.5-{Base,SFT,RL} and Leanabell-Prover (Phase 6/7 training-lineage results)

Reuse the Goedel pin (`leanprover/lean4:v4.9.0-rc1` + `xinhjBrant/mathlib4@2f65ba7…`) --- confirmed via
each lineage's own `.gitmodules`/`lean-toolchain` at pin time, same toolchain family as Goedel-Prover-V2
despite the different training lab (DECISIONS.md 2026-06-04 risk note; resolved same pin, no divergent
mathlib build was needed).

- `deepseek-ai/DeepSeek-Prover-V1.5-Base`
- `deepseek-ai/DeepSeek-Prover-V1.5-SFT`
- `deepseek-ai/DeepSeek-Prover-V1.5-RL`
- `Goedel-LM/Goedel-Prover-SFT` (Leanabell-Prover lineage's SFT stage, per its own release)

## Why two different mathlib snapshots for the two headline models

Goedel-Prover-V2 and DeepSeek-Prover-V2 were released against their own labs' independently-chosen
Lean/mathlib pins (a custom Goedel fork vs. standard upstream mathlib, six weeks apart in 2024). We use
each model's own release pin rather than forcing a shared snapshot, so that any solve-rate gap between
the two models (Section~\ref{sec:passb}) reflects the model, not an artificial Lean-version mismatch
against training-time expectations. Both pins are materially older (2024-era) than mathlib4's current
upstream HEAD; Section~\ref{sec:discussion}'s limitations discussion addresses what this could mean for
the unresolved-identifier rate directly.

## Harness

- Verifier backend: `ReplBackend` (persistent Lean 4 REPL, mathlib preloaded) --- not
  `PantographBackend` (test/plumbing-only, never used for a reported result) and not `lean-dojo`.
- Full harness code: `src/atp/` at the git SHA recorded in each run's `run_manifest.json`
  (git SHA, config hash, seed, model revision, mathlib commit, Lean version, hostname, timestamps ---
  CLAUDE.md rule 4).
