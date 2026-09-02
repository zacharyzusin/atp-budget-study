# The trapped cores

The benchmark subsets this project's mechanism work is built on. **A "trapped core" is the set of
problems that no baseline seed solved at the full 128k-token budget** — i.e. the population where the
execution floor actually lives. Phases 2, 3, 5, 7 and the WS6 decomposition probe all run against
these lists, and every "0% by construction" baseline in those phases means "0% on this file."

Ported here from `scratch/phase2/` at project close (2026-09-02) so they survive a clone — `scratch/`
is gitignored. Byte-identical copies; the originals remain in place.

| File | n | Model | Benchmark |
|---|---|---|---|
| `trapped_minif2f.txt` | 55 | Goedel-Prover-V2-8B | miniF2F-test |
| `trapped_proofnet.txt` | 150 | Goedel-Prover-V2-8B | ProofNet# |
| `trapped_minif2f_deepseek.txt` | 61 | DeepSeek-Prover-V2-7B | miniF2F-test |
| `trapped_proofnet_deepseek.txt` | 140 | DeepSeek-Prover-V2-7B | ProofNet# |
| `trapped_minif2f_decomp_smoke.txt` | 2 | Goedel / DeepSeek | miniF2F subset used for all five WS6 decomposition smoke rounds |

One canonical problem name per line, matching the loaders in `src/atp/data/`.

## Provenance

Derived from the Phase 0 baseline runs (`results/baseline`, `results/proofnet_baseline`,
`results/deepseek_minif2f_baseline`, `results/deepseek_proofnet_baseline`): a problem is in the core
iff **no seed** solved it within 128k tokens. Model revisions, Lean toolchains and mathlib commits for
those runs are in each run's `run_manifest.json` and summarized in `paper/floor/PINS.md`.

## Read this before using them as a benchmark

These lists are **model-specific and harness-specific**, and three caveats travel with them:

1. **They are defined against a specific harness version.** The `maxHeartbeats` re-verify (audit
   Check B) later showed 13 cells across these cores had correct proofs that the *old* Lean heartbeat
   setting rejected — 8 distinct (problem, model) pairs, 2.0% of trapped-problem instances. Those
   problems were genuinely solved by the original generation and are, strictly, no longer trapped.
   The lists here are the **as-used** definition, unchanged, because that is what every phase actually
   ran against; see `results/audit/HEARTBEAT_CORRECTED_CURVES.md` for exactly which cells moved.
2. **"Trapped" is not "unprovable."** A fresh-sampling calibration cell on `trapped_minif2f.txt`
   recovered 6/55 at pass@32 with no budget cap (≈11%, hazard still flat at N=32), of which 4 verify
   under clean generation conditions and 1 has a known training-corpus overlap. Trapped means "this
   agent loop, at this budget, did not solve it" — a statement about the regime, not the problem.
3. **Only Goedel×miniF2F has a dedicated resampling calibration cell.** DeepSeek's cores and
   Goedel×ProofNet# do not; that is a logged scope limit, not an oversight (`SYNTHESIS.md`
   corrections log #3).

Full derivation and caveats: `SYNTHESIS.md`'s corrections log, `results/phase2/MECHANISM.md`, and
`results/audit/AUDIT_FINDINGS.md`.
