# `results/` — the receipts

Every number quoted in the top-level [`README.md`](../README.md) traces to a file here. That is the
narrative; this is the evidence.

## What's tracked, and what isn't

`results/` is bulk generated output and is gitignored wholesale, with narrow exceptions:

**Tracked** — the hand-written per-phase result docs listed below, the trapped-core problem lists,
and `metrics.json` for the four baseline runs (plus `run_manifest.json` for `baseline/`, the only one
that has it — manifest emission was added partway through the project).

**Not tracked** — per-problem attempt logs, raw completions, Lean feedback, agent checkpoints, and
the ~40 other run directories (every ablation arm, every training arm, every smoke run). All of it is
on the cluster at the project root; nothing here depends on it being present, except
`scripts/fold_heartbeat_correction.py`, which recomputes `pass@B` from the per-problem records and so
only runs where those exist.

Some of these documents cite `PROGRESS.md` and `DECISIONS.md`. Those were the dated lab notebooks;
they were removed from the working tree at project close and live in git history (through `baa9eb9`)
and on the cluster.

## The result docs, by phase

| Doc | What it establishes |
|---|---|
| **Phase 0 — baselines** | |
| `phase0/ATTEMPTS_PER_BUDGET_TABLE.md` | How many complete, independent propose attempts each budget actually buys. The source of the "2k is attempt-starved" caveat (median **zero** completed attempts) and of the pass@budget ≠ pass@N gap. |
| `phase0/PASS_AT_N_RECOUNT.md` | Recount of attempts per cell. |
| `phase0/PASS_AT_32_RECONCILIATION.md` | Reconciles our pass@32 (195/244 ≈ 80%) against published pass@N figures. |
| `phase0/TRUNCATION_AND_TIMEOUT_AUDIT.md` | The `maxHeartbeats` trajectory-distortion rates (17.8% of miniF2F refine steps). |
| **Phase 1 — scaffolding ablation** | |
| `phase1/FINDINGS.md` | The OFAT null, the retrieval non-replication, and the paired-flip tables (incl. BM25's −36 net flips on ProofNet#). |
| **Phase 2 — mechanism** | |
| `phase2/MECHANISM.md` | **The central result**: F1–F5 trace mining plus the Step C causal intervention. Execution depth, not approach discovery. |
| `phase2/F1_ATTEMPT_COUNT_RECONCILIATION.md` | Reconciles F1's attempt counts against the raw logs. |
| **Phase 3 — hammer/SMT** | |
| `phase3/HAMMER_PROBE.md` | The NO-GO: the closing-tactic portfolio solves 0/119. |
| **Phase 4 — allocation (the one positive)** | |
| `phase4/ALLOCATION.md` | The efficiency frontier, the realizable policy, the oracle ceiling, **and the bootstrap CI that crosses zero**. |
| `phase4/ALLOCATION_MECHANISM.md` | Why allocation helps when it helps; also covers Phase 5. |
| `phase4/PREDICTOR_V2_DESIGN.md` | A **pre-registration**, written before any code — decision rule + seed-holdout CV guard. A worked example of the practice. |
| `phase4/PREDICTOR_V2_RESULT.md` | The negative result (+0.033 AUC vs. a 0.05 bar) that the rule then closed. |
| **Phase 6 — training interventions** | |
| `phase6/DISJOINTNESS.md` | Proves the training corpus is disjoint from both eval sets — the gate that made Phase 6 interpretable. |
| `phase6/FINETUNE.md` | Stage A/B: null, plus the exposure-bias signature. |
| `phase6/STAGE_A_FORMAT_DIFF.md` | Why Stage A harms: the format mismatch. |
| `phase6/STAGE_C_PROBE_SPEC.md` | The GRPO probe's pre-registered triple gate. |
| `phase6/STAGE_C_DECISION.md` | The go/no-go reasoning. |
| `phase6/STAGE_C_RESULT.md` | The RL null and its saturated-policy signature. |
| `phase6/CONTAMINATION_CORRELATION.md` | The memorization-boundary objection, answered — p=0.049 in the **wrong direction** for it. |
| **Phase 7 — re-grounding** | |
| `phase7/STEPWISE.md` | The null, including the matched fresh-resample control that makes it a null rather than a weak positive. |
| **Phase 8 — model zoo (WITHDRAWN)** | |
| `phase8/ZOO.md` | ⚠️ **Headline withdrawn — do not cite its numbers.** Kept for the audit trail and the bug's mechanism. |
| `phase8/CONTROL_AUDIT_STATUS.md` | Why the harness-sanity control missed the bug: it only covered whole-proof-format models. |
| `phase8/CHECKIN2_REVIEW_SUMMARY.md` | Mid-phase review. |
| **The audit** | |
| `audit/BUG_CATALOGUE.md` | **The reusable artifact.** All five harness bugs + two measurement gaps: mechanism, blast radius, direction of error, the regression test that locks each, and a "check your own harness" test. |
| `audit/AUDIT_FINDINGS.md` | ~30 independent checks. **A1** = the `no_goal` bug that withdrew Phase 8; **B** = the `maxHeartbeats` correction. Most other checks re-derived committed numbers *exactly*, using code that imports none of this project's analysis. |
| `audit/HEARTBEAT_CORRECTED_CURVES.md` | The `maxHeartbeats` fold-in: per-cell before/after, plus the check that the uncorrected recompute reproduces every committed `metrics.json` exactly. |
| **WS6 — the final sprint** | |
| `EQUIVALENCE_BOUNDS.md` | Paired per-problem bootstrap CIs replacing "within noise". |
| `RETRIEVAL_REPLICATION_CI.md` | The within-run-CI vs. replication lesson, quantified: two non-overlapping CIs for the same effect. |
| `phase_decomp/DESIGN.md` | The decomposition probe: pre-registration, five smoke rounds, two-model NO-GO. A second worked example of a stopping rule doing its job (~2.3 GPU-h instead of a full array). |
| **Not run** | |
| `phase_scale32b/FEASIBILITY.md` | Scoping for a 32B calibration cell — fits via vLLM `--tensor-parallel-size 2`, no quantization. **Deliberately not run**, recorded so the decision is informed rather than re-investigated. |

## `trapped_cores/`

The five trapped-core problem lists — the population the execution floor lives in, and the definition
behind every "0% by construction" baseline in Phases 2/3/5/7 and WS6. See
[`trapped_cores/README.md`](trapped_cores/README.md) for provenance and the three caveats that travel
with them.

## Before quoting anything from here

Read the "Five harness bugs" and "Limitations" sections of the top-level
[`README.md`](../README.md). Several claims carry corrections added after the underlying document was
written, and Phase 8's headline is withdrawn.
