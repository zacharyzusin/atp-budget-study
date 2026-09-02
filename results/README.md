# `results/` — the receipts

Every number quoted in `README.md`, `SYNTHESIS.md`, `PROJECT_SUMMARY.md` and the paper traces to a
file here. This directory is the evidence layer; those are the narratives.

## What's tracked in git, and what isn't

**Tracked** (~0.9 MB, so a clone is self-contained):
- `**/*.md` — the hand-written per-phase result docs indexed below.
- `*/metrics.json` — the headline numbers for each run (`pass@B` per budget, per seed).
- `*/run_manifest.json` — provenance for each run: git SHA, config hash, seed, model revision,
  mathlib commit, Lean version, hostname, GPU type, timestamps.
- `*/*.json` — top-level analysis outputs (`phase4/frontier.json`, `equivalence_bounds.json`, …).

**Not tracked** (GB-scale, lives only on the cluster): `*/problems/` — per-problem attempt logs,
raw completions, Lean feedback, and agent checkpoints. If you need those, they are on the Insomnia
filesystem at the project root; nothing else here depends on them being present.

## The result docs, by phase

| Doc | What it establishes |
|---|---|
| **Phase 0 — baselines** | |
| `phase0/ATTEMPTS_PER_BUDGET_TABLE.md` | How many independent propose attempts each budget actually buys. Source of the "2k is attempt-starved" caveat (median **zero** completed attempts at 2k) and the pass@budget ≠ pass@N gap. |
| `phase0/PASS_AT_N_RECOUNT.md` | Recount of attempts per cell; source of corrections-log item #1. |
| `phase0/PASS_AT_32_RECONCILIATION.md` | Reconciles our pass@32 (195/244 ≈ 80%) against published pass@N figures. |
| `phase0/TRUNCATION_AND_TIMEOUT_AUDIT.md` | The `maxHeartbeats` trajectory-distortion rates (17.8% of miniF2F refine steps). |
| **Phase 1 — scaffolding ablation** | |
| `phase1/FINDINGS.md` | The OFAT null, the retrieval non-replication, and the paired-flip tables (incl. BM25's −36 net flips on ProofNet#). |
| **Phase 2 — mechanism** | |
| `phase2/MECHANISM.md` | **The central mechanism result**: F1–F4 trace mining plus the F6 causal intervention. Execution depth, not approach discovery. |
| `phase2/F1_ATTEMPT_COUNT_RECONCILIATION.md` | Reconciles F1's attempt counts against the raw logs. |
| **Phase 3 — hammer/SMT** | |
| `phase3/HAMMER_PROBE.md` | The NO-GO: the closing-tactic portfolio solves 0/40 trapped problems. |
| **Phase 4 — allocation (the positive)** | |
| `phase4/ALLOCATION.md` | The efficiency frontier, the realizable policy, the oracle ceiling, **and the bootstrap CI that crosses zero**. |
| `phase4/ALLOCATION_MECHANISM.md` | Why allocation helps when it helps. |
| `phase4/PREDICTOR_V2_DESIGN.md` | WS6 item 4 **pre-registration**, written before any code — decision rule + seed-holdout CV guard. A worked example of the practice. |
| `phase4/PREDICTOR_V2_RESULT.md` | The negative result (+0.033 AUC vs. a 0.05 bar) that the rule then closed. |
| **Phase 6 — training interventions** | |
| `phase6/DISJOINTNESS.md` | Proves the training corpus is disjoint from both eval sets — the gate that made Phase 6 interpretable. |
| `phase6/FINETUNE.md` | Stage A/B results: null, plus the exposure-bias signature. |
| `phase6/STAGE_A_FORMAT_DIFF.md` | Why Stage A harms: the format mismatch. |
| `phase6/STAGE_C_PROBE_SPEC.md` | The GRPO probe's pre-registered triple gate. |
| `phase6/STAGE_C_DECISION.md` | The go/no-go reasoning. |
| `phase6/STAGE_C_RESULT.md` | The RL null and its saturated-policy signature. |
| `phase6/CONTAMINATION_CORRELATION.md` | WS6 item 2: the memorization-boundary objection, answered (p=0.049 in the **wrong direction** for it, r=−0.173) with both caveats. |
| **Phase 7 — re-grounding** | |
| `phase7/STEPWISE.md` | The null, including the matched fresh-resample control that makes it a null rather than a weak positive. |
| **Phase 8 — model zoo (WITHDRAWN)** | |
| `phase8/ZOO.md` | ⚠️ **Its headline is withdrawn.** Kept for the audit trail and for the bug's mechanism. Do not cite its numbers — see `audit/AUDIT_FINDINGS.md` Check A1. |
| `phase8/CONTROL_AUDIT_STATUS.md` | Why the harness-sanity control did not catch the bug (it only covered whole-proof-format models). |
| `phase8/CHECKIN2_REVIEW_SUMMARY.md` | Mid-phase review. |
| **The audit** | |
| `audit/AUDIT_FINDINGS.md` | ~30 independent checks. **Check A1** = the P0 `no_goal` verifier bug that withdrew Phase 8; **Check B** = the material `maxHeartbeats` scoring correction (13/1212 cells). Most other checks re-derived committed numbers *exactly*, with code importing none of the project's own analysis. |
| **WS6 — strengthening sprint** | |
| `EQUIVALENCE_BOUNDS.md` | Paired per-problem bootstrap CIs replacing "within noise" — Phase 1 components and Phase 6 Stage A/B. |
| `RETRIEVAL_REPLICATION_CI.md` | The within-run-CI vs. replication lesson, quantified: two non-overlapping CIs for the same effect. |
| `phase_decomp/DESIGN.md` | The decomposition probe: pre-registration, all five smoke rounds, and the two-model NO-GO. The second worked example of a pre-registered stopping rule doing its job (~2.3 GPU-h instead of a full array). |
| **Not run** | |
| `phase_scale32b/FEASIBILITY.md` | Scoping for a 32B calibration cell — fits via vLLM `--tensor-parallel-size 2` on this cluster's dual-l40s nodes, no quantization. **Deliberately not run.** Recorded so the decision is informed rather than re-investigated. |

## Run directories

The ~150 other directories are individual runs, named `<model>_<benchmark>_<arm>[_s<seed>]` or by
phase (`p6eval_g_pn_A_s1`, `p8battery2_*`, `calibration_trapped32_*`, …). Each holds a
`metrics.json`, a `run_manifest.json`, and (on the cluster only) a `problems/` directory. The config
that produced any run is identified in its manifest.

To read a run:

```bash
python scripts/analyze_results.py results/<run_dir>          # pass@B curve
python scripts/analyze_results.py results/<a> results/<b>    # run-vs-run paired flips
```

## Before quoting anything from here

Read `SYNTHESIS.md`'s **corrections log** and [`../HANDOFF.md`](../HANDOFF.md) §5. Several claims
carry caveats that were added after the underlying doc was written, and Phase 8's headline is
withdrawn.
