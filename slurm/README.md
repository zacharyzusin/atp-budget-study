# `slurm/` — restartable batch scripts

Every job here is **restartable by design**: the cluster preempts and requeues from scratch, so any
job over ~20 minutes checkpoints to disk and skips already-completed `(config, seed, problem)` cells
on resume. That is a hard convention (`CLAUDE.md` rule 3), not a nicety.

**The project is closed — do not submit these without asking.**

## Before you touch any of these

Two cluster facts are baked into every script and will silently break anything you write from
scratch:

1. **`unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy` at the top.** Slurm jobs inherit a
   per-session SSH proxy that breaks every outbound download. Compute nodes have direct internet;
   the inherited proxy is the problem.
2. **Stage Mathlib oleans to node-local SSD** (`/local`). Loading ~4.7k oleans from shared GPFS
   causes an open-storm that degrades the whole filesystem.

Also: `--account=edu`; `short` (≤12h) for eval, `burst` (≤14d, preemptible) for sweeps and training;
`--gres=gpu:l40s:1` for inference, `gpu:h100:1` for training. RAM is capped ~6400 MB/CPU, so request
more CPUs rather than a bigger `--mem-per-cpu`.

## The scripts

| script | what it runs |
|---|---|
| **Core harness** | |
| `vllm_server.sh` | Brings up the persistent vLLM server the agent talks to |
| `sweep.sh` | The main eval sweep — one config, all seeds. The usual entry point |
| `sweep_array.sh` | Array version for multi-cell campaigns; model identity read from config at runtime |
| `ablation.sh` | Phase 1 OFAT ablation across scaffolding components |
| **Environment build** | |
| `build_lean.sh` | Builds the Goedel-pinned Lean env (custom mathlib fork, from source — no cache hits) |
| `build_deepseek_lean.sh` | Same for DeepSeek's pin (standard mathlib) |
| `validate_statements.sh` | Compile-gate: do a benchmark's statement heads elaborate against the pin? |
| `diag_repl.sh` | REPL diagnostics |
| `gate_deepseek.sh` | DeepSeek readiness gate |
| **Phase 3 — hammer probe** | |
| `hammer_smoke.sh`, `offpin_arm_b.sh`, `offpin_elab_probe.sh` | The three hammer/SMT arms (on-pin, off-pin duper via Pantograph, elaboration probe) |
| **Phase 5** | |
| `phase5_pilot.sh` | Reclaim-and-reinvest pilot gate |
| **Phase 6 — SFT and RL** | |
| `phase6_harvest_extract.sh` | Harvest SFT data from a generation run |
| `phase6_train.sh` | LoRA SFT for Stages A/B |
| `phase6_probe.sh` | Continuation round-trip + hard-target probe |
| `phase6_grpo.sh` | Stage C GRPO RL probe |
| **Phase 7 — re-grounding** | |
| `phase7_stepwise_run.sh` / `phase7_stepwise_smoke.sh` | Mode 3, verified-state re-grounding |
| `phase7_tactic_run.sh` | Mode 4, true stepwise (one tactic per call) |
| `phase7_freshcontrol_run.sh` | **The matched fresh-resample control** — the reason Phase 7's null is a null and not a weak positive |
| `phase7_gate_check.sh`, `phase7_format_e_diagnostic.sh` | Gate sanity + format diagnostics |
| **Phase 8 — model zoo (headline withdrawn)** | |
| `phase8_reverify.sh` | Re-verify collected completions against the fixed verifier |
| `phase8_reverify_sanity_scan.sh`, `phase8_reverify_debug_one.sh` | Narrower re-verify variants |
| `phase8_control_check.sh` | The harness-sanity control — note it only covered whole-proof-format models, which is why it missed the `no_goal` bug |
| **Audit** | |
| `audit_trapped_reverify.sh` | Check B: offline CPU re-verify of every historically-failed trapped attempt under `maxHeartbeats 0` |
| `header_confound_reverify.sh` | The header-confound follow-up |
| **WS6** | |
| `phase_decomp_run.sh` | Decomposition probe (Goedel) |
| `phase_decomp_deepseek_run.sh` | Decomposition probe (DeepSeek) — config-driven model identity |

## Typical invocation

```bash
mkdir -p logs results
sbatch slurm/sweep.sh configs/phase0_baseline.yaml baseline   # resume-safe: rerun to continue
squeue --me                                                   # watch
sacct -j <id> --format=JobID,State,Elapsed,MaxRSS,ReqTRES%40  # accounting
```

Logs land in `logs/` (gitignored). Results land in `results/<name>/`.
