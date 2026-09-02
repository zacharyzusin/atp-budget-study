# `scripts/` — per-phase analysis and one-off probes

One-shot analysis, probes and job drivers, grouped by the phase they belong to. Most are CPU-only and
read already-logged data from `results/`; the ones that generate (`phase*_run.py`, `phase6_train_sft.py`,
`phase6_grpo.py`) need a live vLLM endpoint and are normally driven by a script in `slurm/`.

**The project is closed — don't run the generating scripts without asking.** The analysis scripts are
safe and re-derive published numbers from data already on disk.

Descriptions below are each script's own docstring. For what each phase asked and found, see
[`../README.md` §4](../README.md#4-phase-by-phase).


## Data & setup

| script | what it does |
|---|---|
| `build_premise_corpus.py` | Build the BM25 premise corpus (Phase 1 retrieval) by parsing pinned-Mathlib source. |
| `build_proofnet_sharp.py` | Stage ProofNet# (PAug/ProofNetSharp) into the loader's JSONL format. |
| `validate_statements.py` | Compile-gate: do a benchmark's statement HEADS elaborate against the pinned mathlib? |
| `setup_lean_env.sh` | Acquire the Goedel-pinned Lean verification env (Lean v4.9.0-rc1 + xinhjBrant/mathlib4 fork). |
| `make_pickle_local.py` | Create the Mathlib env pickle from a node-LOCAL copy of the Lean env, then validate unpickle. |
| `diag_repl.py` | Diagnostic: capture the RAW leanprover-community/repl response for real proofs. |

## General analysis (any run)

| script | what it does |
|---|---|
| `analyze_results.py` | Reusable analysis for a results/<run>/ dir — pass@B curve, run-vs-run comparison, paired flips. |

## Phase 0 — baselines & calibration

| script | what it does |
|---|---|
| `phase0_calibration_checks.py` | Phase 0 calibration checks (CPU-only, read-only) — pass@N recount + truncation/timeout audit. |

## Phase 2 — mechanism

| script | what it does |
|---|---|
| `analyze_mechanism.py` | Phase 2 mechanism analysis — explain the budget→solve asymmetry from data on disk. |
| `stepc_readout.py` | Phase 2 Step C readout: budget-matched manipulation check + solve flips + failure texture + soundness |

## Phase 3 — hammer/SMT probe (NO-GO)

| script | what it does |
|---|---|
| `hammer_extract.py` | Hammer probe — extract, per trapped problem, the statement + the model's deepest valid-prefix 'stuck |
| `hammer_arm0.py` | Hammer probe Arm 0 (+ Arm B if a hammer tactic is given) on ORIGINAL trapped statements — on-pin, |
| `hammer_arm_a.py` | Hammer probe Arm A-lite — symbolic closer at the model's STUCK LEAF, in-context, no new infra. |
| `hammer_arm_b_pantograph.py` | Off-pin Arm B — a REAL hammer (duper) on the trapped ProofNet# STATEMENTS, via Pantograph on the |

## Phase 3 — CPU hardening checks H1-H4

| script | what it does |
|---|---|
| `h1_intersection.py` | H1 — recompute the cross-model dichotomy on the compile-on-both-pins INTERSECTION. |
| `h2_taxonomy_audit.py` | H2 — corrected attempt-level failure taxonomy + the load-bearing knowledge rate. |
| `h2_taxonomy_sample.py` | H2 — sample unsolved attempts for human validation of the regex failure taxonomy. |
| `h3_soundness.py` | H3 — soundness-creep across ALL scaffolding components (generalizes Step C's C-3). |
| `h4_decompose.py` | H4 — decompose the OOD cross-model dichotomy (DeepSeek > Goedel on ProofNet#) through the F1/F3 lens. |

## Phase 4 — budget allocation (the positive result)

| script | what it does |
|---|---|
| `phase4_ceiling.py` | Task 4.1 check-in: tokens_to_solve distribution + oracle headroom ceiling, all four baselines. |
| `phase4_predictor.py` | Task 4.3 check-in: how early is trapped-ness predictable? (AUC-vs-checkpoint + importances) |
| `phase4_frontier.py` | Task 4.3-4.4: the efficiency frontier + capture-of-oracle, all four baselines (CPU-only). |
| `phase4_perseed.py` | Per-seed consistency of the realizable saving (sample-generalization from logged data, CPU-only). |
| `phase4_bootstrap_ci.py` | Paired per-problem bootstrap CI for the realizable-policy saving (replaces the 1-seed-std gate). |
| `analyze_allocation.py` | Phase 4 mechanism analysis (WS1.2, PLAN_NEXT.md) — why does budget allocation help when it helps? |
| `phase4_predictor_v2.py` | WS6 item 4: does the richer (v2) feature set improve the difficulty predictor? |

## Phase 5 — reclaim & reinvest

| script | what it does |
|---|---|
| `phase5_candidates.py` | Phase 5 Task 5.1: build reclaim-and-reinvest candidate sets offline (no GPU). |
| `phase5_pilot.py` | Phase 5 Task 5.2 PILOT GATE: extend a stratified sample of the extend set to E and count solves. |

## Phase 6 — fine-tuning (Stages A/B) and RL (Stage C)

| script | what it does |
|---|---|
| `phase6_disjointness.py` | Phase 6 §0 GATE: prove the training corpus (Lean Workbook) is disjoint from BOTH eval sets. |
| `phase6_decontaminate.py` | Phase 6 §0: decontaminate Lean Workbook against BOTH eval sets, write the clean corpus + proof. |
| `phase6_harvest.py` | Phase 6 Task 6.1: build the SFT datasets from a generation run on the clean Lean Workbook corpus. |
| `phase6_build_sft.py` | Phase 6 Task 6.5: build the Stage A (RFT) and Stage B (closing-targeted continuation) SFT data. |
| `phase6_train_sft.py` | Phase 6 Task 6.5: LoRA SFT for Stage A (RFT) / Stage B (closing-targeted continuation). |
| `phase6_continuation_probe.py` | Phase 6 Stage B — continuation round-trip smoke (Task 6.3) + hard-target probe (Task 6.4). |
| `phase6_pilot_compare.py` | Phase 6 Stage B pilot read-out: base vs A (RFT) vs B (closing-targeted). |
| `phase6_seed_aggregate.py` | Phase 6 3-seed read-out: per-seed pass@B + mean±std, PER MODEL, with PAIRED B-base deltas. |
| `phase6_select_subset.py` | Stage C probe Task: select the GRPO train + held-out subsets from a base K-seed generation run. |
| `phase6_grpo.py` | Stage C — GRPO RL feasibility probe (DeepSeek-Prover-V2-7B). See STAGE_C_PROBE_SPEC.md. |
| `phase6_stage_c_gate.py` | Stage C probe — G1/G2/G3 triple-gate verdict (STAGE_C_PROBE_SPEC.md §4). |
| `phase6_launch_eval.sh` | Phase 6 3-seed eval launcher. Submits ONE eval sweep (model, seed, arm, benchmark) with the exact |

## Phase 7 — verified-state re-grounding

| script | what it does |
|---|---|
| `phase7_offline_modes.py` | Phase 7 Track 1 — offline Modes 1/2 trapped pass@B (zero GPU/Lean). |
| `phase7_stepwise_run.py` | Phase 7 Track 1 — Mode 3 (verified-state re-grounding) real eval run. |
| `phase7_tactic_run.py` | Phase 7 Track 1 — Mode 4 (true stepwise, one tactic per call) real eval run. |
| `phase7_freshcontrol_run.py` | Phase 7 Track 1 — fresh-resample CONTROL (no re-grounding), same trapped set + fresh session. |
| `phase7_elaborate_gate_check.py` | Phase 7 Track 1 — sanity-check the Mode 3 `elaborate` boundary gate on REAL Lean (CPU-only). |
| `phase7_format_e_diagnostic.py` | Diagnostic: print RAW (unextracted) TacticTemplate completions for a few real trapped goal |

## Phase 8 — model zoo (headline WITHDRAWN, see ../README.md §5.1)

| script | what it does |
|---|---|
| `phase8_intersection.py` | Phase 8 step 2 — compile-on-ALL-pins intersection, generalized from scripts/h1_intersection.py |
| `phase8_floor_table.py` | Phase 8 step 4 — matched-pair floor table for the DeepSeek-Prover-V1.5 Base/SFT/RL triple. |
| `phase8_contamination.py` | Phase 8 — contamination-noted subset for the matched-pair floor table. |
| `phase8_control_check.py` | Harness-sanity control (coordinator-mandated 2026-07-09/10): confirm the CURRENT fully-patched |
| `phase8_reverify.py` | Phase 8 — re-verify already-collected p8battery2_* completions against the FIXED |
| `phase8_reverify_sanity_scan.py` | One-off sanity scan: re-verify EVERY attempt (not just until first solve) for N cells and report |
| `phase8_reverify_debug_one.py` | One-off debug: print the re-verify result + feedback for a single named cell's first attempt. |
| `phase8_smoke_quality.py` | Phase 8 — smoke-quality diagnostic: the check that WOULD have caught the Leanabell |

## Audit — the two real findings

| script | what it does |
|---|---|
| `audit_no_goal_gate_check.py` | AUDIT_PLAN.md Task A1 Step 3 (extended): does verifier.py's `no_goal` gate check the wrong |
| `audit_trapped_heartbeat_reverify.py` | AUDIT_PLAN.md Task B — does `set_option maxHeartbeats 0` (added 2026-07-06, absent for every |
| `header_confound_reverify.py` | External-calibration-sprint follow-up (DECISIONS.md 2026-07-25h) — the header-confound check. |

## WS6 — post-draft strengthening sprint

| script | what it does |
|---|---|
| `equivalence_bounds.py` | WS6 item 1: equivalence-testing reframe -- upper confidence bounds instead of "within noise." |
| `retrieval_replication_ci.py` | WS6 item 1 follow-up: paired bootstrap CI on the retrieval REPLICATION run, at each budget tier. |
| `contamination_correlation.py` | WS6 item 2 (free half): does overlap with the Lean-Workbook training corpus predict trapped status? |
| `phase_decomp_run.py` | WS6 item 3 — subgoal decomposition real eval run. |

## Watchers (long-running job babysitters)

| script | what it does |
|---|---|
| `baseline_watcher.sh` | Overnight watcher: keep the Phase-0 baseline sweep alive across 12h Slurm TIMEOUTs. |
| `proofnet_watcher.sh` | Re-chain the ProofNet# baseline (sweep) + Phase 1 ablation (array) across the 12h `short` wall. |
| `verify_deepseek_proofs.sh` | Phase 2 Step B — empirical pin confirmation: verify DeepSeek-Prover-V2's OWN published miniF2F proofs |
