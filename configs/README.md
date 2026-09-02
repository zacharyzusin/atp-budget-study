# `configs/` — one versioned YAML per experiment

**Configs, not magic numbers**: every experiment in this project is driven by a file here, and every
run writes a `run_manifest.json` recording the config hash alongside the git SHA, seed, model
revision, mathlib commit, Lean version, host and GPU type. To find out what produced a run, read its
manifest — don't guess from the directory name.

`base.yaml` holds the shared defaults; the rest override it.

## Naming

`<model>_<benchmark>_<arm>[_s<seed>][_smoke].yaml` — for example `deepseek_proofnet_baseline.yaml`,
`phase6_eval_deepseek_minif2f_s1.yaml`, `leanabell_gdrl_proofnet_battery.yaml`.

- `*_smoke.yaml` — tiny 2–5 problem end-to-end sanity configs. **Always run the smoke config before
  submitting the full sweep** (`CONVENTIONS.md` rule 5).
- `*_battery.yaml` — the Phase 8 model-zoo batteries (whose headline is withdrawn; see
  [`../README.md` §5.1](../README.md#51-phase-8s-headline-is-withdrawn)).
- `phase6_*` — the SFT/RL training and eval arms.
- `calibration_trapped32_*` — the trapped-core resampling calibration cells.

## The families

| prefix | what |
|---|---|
| `base`, `smoke` | Shared defaults; the smoke sanity config |
| `phase0_*`, `goedel_*` | Goedel-Prover-V2-8B baselines (the primary model) |
| `deepseek_*` | DeepSeek-Prover-V2-7B baselines and arms (the replication model) |
| `deepseek_v15_*`, `leanabell_*`, `stp_*` | Phase 8 model-zoo lineages |
| `phase1_*` | Scaffolding OFAT ablation arms |
| `diversity_*` | Phase 2's forced-diversity causal intervention |
| `phase6_*` | Fine-tuning (Stage A/B) and RL (Stage C) |
| `calibration_*` | Trapped-core resampling calibration |
| `proofnet_*`, `validate_*` | ProofNet# staging and statement compile-gates |

## The pins are load-bearing

Model revisions and Lean/mathlib commits in these files are pinned exactly, and the two models use
**different** Lean toolchains and mathlib commits (Goedel needs a custom mathlib fork built from
source). Mathlib API drift silently lowers a prover's pass rate rather than erroring, so changing a
pin invalidates comparisons without failing loudly. The exact pins are tabulated in
[`../README.md` §9](../README.md#9-reproducibility-pins).
