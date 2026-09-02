# Phase 8 — control/audit gate status (2026-07-10)

## All four blocking gates cleared

1. **Harness-sanity control: PASSED.** Goedel-Prover-V2 (37/37) and DeepSeek-Prover-V2-7B (40/40)
   historically-solved cells still verify as `ok` under the exact backend code (all 3 bug fixes
   applied) that produced Phase 8's 0.0%-everywhere corrected floor. The harness correctly recognizes
   real, known-good proofs — the perfect zeros are not a broken-pipeline artifact.

2. **Taint audit: clean.** Every Phase 0-7 committed/headline result (Phase 1 FINDINGS.md, Phase 2
   MECHANISM.md, Phase 3 HAMMER_PROBE.md, Phase 4 ALLOCATION.md — the compute-optimal positive
   result, Phase 6 FINETUNE.md/STAGE_C_RESULT.md, Phase 7 STEPWISE.md) used only Goedel-Prover-V2-8B
   and/or DeepSeek-Prover-V2-7B, both natively on `whole_proof` — unaffected by the
   `WholeProofAgent.from_config` wiring bug regardless of when it was introduced. Phase 7's
   tactic-stepwise mode uses a separate agent class (`TacticStepwiseAgent`) never routed through the
   buggy code at all. BFS-Prover/STP configs exist (pin-triaged) but were never swept — no data to
   taint. **Zero Phase 0-7 results require re-verification.** The wiring bug's blast radius is fully
   contained to Phase 8.

3. **client.py stop-sequence debt: real, but does not explain the floor.** Confirmed no template ever
   sets a `stop` sequence (`self.stop` stays `()` always). Investigated concretely whether this could
   mask a hidden correct solve behind trailing garbage — sampled cases show the trailing content is
   either preceded by disqualifying leading garbage (DeepSeek-V1.5-Base's immediate `sorry`) or
   refers to a hallucinated, wrong theorem (Leanabell GD-SFT/GD-RL), not a masked real solve. Recorded
   as real, non-blocking efficiency/quality debt for any future regeneration pass — not fixed now.

4. **Cluster B breadth: formally dropped.** RL is closed via two clean matched lineages
   (DeepSeek-Prover-V1.5 Base→SFT→RL, Leanabell GD-SFT→GD-RL) through a harness now confirmed sound.
   More models would add breadth to an already-established negative, not new information.
   `gdrl_minif2f` folded in at final coverage (541/732, 74%), still 0 solved.

## Bottom line

The 0.0%-everywhere corrected floor (5,586+ re-verified cells, both lineages, both benchmarks, every
budget) is **real and harness-validated**, not a scoring artifact. This now stands as a fourth
independent confirmation of the project's execution-floor thesis (after Phase 6 Stage B's SFT-exposure-
bias null, Stage C's LoRA-GRPO null, and now two full-pipeline lab-RL lineages).

`results/phase8/ZOO.md` has the full corrected floor table and honest history of every invalid attempt.
`SYNTHESIS.md` (repo root) has been extended through Phases 3-8 tying the whole arc together.

**Not yet decided (explicitly left to the coordinator/user):**
- The discovery-vs-definitive-negative headline call itself (working recommendation: definitive-
  negative, in its strongest form now that the harness is verified sound).
- Whether the final deliverable is a paper or an internal-only synthesis.
