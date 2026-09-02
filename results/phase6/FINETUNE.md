# Phase 6 — Mechanism-Targeted Execution Fine-Tuning: results

STATUS: FINAL (full 3-seed matrix complete, 2026-06-30). Regenerate anytime with
`python scripts/phase6_seed_aggregate.py`.

## Question
Does training targeted at the goal-closing bottleneck lift pass@B on the held-out benchmarks?
Arms (single-variable vs base, LoRA r=16): A = generic RFT; B = closing-targeted SFT
(deep_state -> closing, loss masked to closing tokens). Two models (Goedel-Prover-V2-8B,
DeepSeek-Prover-V2-7B), 3 seeds, miniF2F + ProofNet#, budgets {8000, 32000} tokens.

## Headline (NULL, two-model, per-seed robust)
Closing-targeted SFT does NOT lift the execution floor on either model. Paired B-base @32k =
Goedel -2.0+/-1.1pp (miniF2F) / -2.0+/-1.2pp (ProofNet#); DeepSeek -0.3+/-1.3pp / -0.9+/-0.3pp.
All flat-to-slightly-negative, NONE within reach of the pre-registered >=+3pp, tight bars across
3 seeds. This holds DESPITE low closing-token training loss (~0.07) -> the model assigns high
CONDITIONAL probability to the correct closings yet fails to GENERATE them autoregressively =
exposure bias, not missing knowledge. Generic RFT (A) actively hurts (-12..-20pp @32k miniF2F).
=> The F2/F3 execution floor is sampling/exposure-bound; teacher-forced likelihood SFT cannot
move it. Two live hypotheses remain (c1 exposure-bound vs c2 capacity-bound); see
STAGE_C_DECISION.md for the gated GRPO RL probe that separates them.

## Aggregate table (auto-generated)
```

##### model=goedel #####

=== minif2f (held-out) ===
  seeds present: base=[0, 1, 2]{0: 244, 1: 244, 2: 244} | A=[0, 1, 2]{0: 244, 1: 244, 2: 244} | B=[0, 1, 2]{0: 244, 1: 244, 2: 244}
    arm     pass@8000    pass@32000
   base      61.5±1.6     70.4±0.6
      A      49.2±3.3     50.7±3.9
      B      59.2±0.9     68.3±1.7
    paired@8000: A-base=-12.3±1.8pp (n=3)  B-base=-2.3±1.2pp (n=3)
    paired@32000: A-base=-19.7±4.4pp (n=3)  B-base=-2.0±1.1pp (n=3)

=== proofnet (held-out) ===
  seeds present: base=[0, 1, 2]{0: 186, 1: 186, 2: 186} | A=[0, 1, 2]{0: 186, 1: 186, 2: 186} | B=[0, 1, 2]{0: 186, 1: 186, 2: 186}
    arm     pass@8000    pass@32000
   base      12.2±0.8     14.2±0.6
      A       8.6±0.0      9.3±0.6
      B      10.2±1.1     12.2±0.6
    paired@8000: A-base=-3.6±0.8pp (n=3)  B-base=-2.0±1.9pp (n=3)
    paired@32000: A-base=-4.8±1.1pp (n=3)  B-base=-2.0±1.2pp (n=3)

Null check (pre-registered): B-base mean ~0, never >=+3pp robust => sampling/exposure-bound floor; A-base negative => generic RFT hurts.

##### model=deepseek #####

=== minif2f (held-out) ===
  seeds present: base=[0, 1, 2]{0: 244, 1: 244, 2: 244} | A=[0, 1, 2]{0: 244, 1: 244, 2: 244} | B=[0, 1, 2]{0: 244, 1: 244, 2: 244}
    arm     pass@8000    pass@32000
   base      57.4±0.8     65.4±0.5
      A      49.3±1.3     52.9±0.8
      B      54.2±0.9     65.2±1.4
    paired@8000: A-base=-8.1±1.7pp (n=3)  B-base=-3.1±1.7pp (n=3)
    paired@32000: A-base=-12.6±1.3pp (n=3)  B-base=-0.3±1.3pp (n=3)

=== proofnet (held-out) ===
  seeds present: base=[0, 1, 2]{0: 186, 1: 186, 2: 186} | A=[0, 1, 2]{0: 186, 1: 186, 2: 186} | B=[0, 1, 2]{0: 186, 1: 186, 2: 186}
    arm     pass@8000    pass@32000
   base      11.5±0.6     17.6±1.2
      A      13.4±1.4     15.1±1.6
      B      11.8±2.3     16.7±1.4
    paired@8000: A-base=+2.0±1.1pp (n=3)  B-base=+0.4±2.0pp (n=3)
    paired@32000: A-base=-2.5±2.0pp (n=3)  B-base=-0.9±0.3pp (n=3)

Null check (pre-registered): B-base mean ~0, never >=+3pp robust => sampling/exposure-bound floor; A-base negative => generic RFT hurts.
```

## Reading
- `paired@B` = mean +/- std over per-seed (arm - base) deltas on the problem intersection present
  in both arms at that seed (pairing removes shared per-seed sampling luck). At full completion
  (this table) the intersection == the full set (244 miniF2F / 186 ProofNet# every cell).
- Null criterion (pre-registered): B-base mean ~0, never robustly >=+3pp => sampling/exposure-
  bound floor, not closable by SFT; A-base negative => generic RFT narrows the policy.

## Provenance
- Serving byte-exact by construction (vLLM serves LoRA on base tokenizer/template); serving guard
  PASSED both models at seed-0 (adapter-served solved-set differs from base => adapter active).
- Training corpus = lean_workbook_clean (decontaminated vs both eval sets, DISJOINTNESS.md).
- Eval ops: single-shard/3-shard, --cpus-per-task=32 --mem=96G (NOT --exclusive; QOS cpu=80 cap);
  see DECISIONS.md 2026-06-29.
