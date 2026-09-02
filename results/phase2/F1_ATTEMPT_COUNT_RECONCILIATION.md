# F1 attempt-count reconciliation (MECHANISM.md vs the Phase-0 pass@N recount)

**Verdict: reconciled exactly. No contradiction — different population and different counting
convention, both internally correct for what each claims to measure.**

## The two numbers

- `results/phase2/MECHANISM.md` Finding 1: "Per unsolved cell, across ~19-24 attempts the model
  commits to only ~2 distinct opening tactics" — table gives miniF2F unsolved mean attempts = **18.9**,
  ProofNet# unsolved = **23.6**, miniF2F solved = 2.1, ProofNet# solved = 6.3.
- `results/phase0/PASS_AT_N_RECOUNT.md`: Goedel x miniF2F overall mean PROPOSE-only attempts = **1.94**
  (max 14), overall mean TOTAL (propose+refine) = 6.33 (max 67) — computed over ALL cells (solved +
  unsolved combined).

## Root cause of the apparent mismatch

Two independent differences, confirmed by reading `scripts/analyze_mechanism.py`'s `diversity()`
function directly (not guessed): (1) `nat.append(len(ats))` counts `len(c["attempts"])` — EVERY
attempt in the cell, propose AND refine steps together, no `kind` filtering anywhere in the function;
(2) the table is split into `solved`/`unsolved` groups and reports each separately — F1's headline
number is the UNSOLVED-only mean, not an overall mean.

The recount's 1.94/6.33 are overall means across ALL cells (most of which solve on/near the first
propose attempt and stop, pulling the average way down — 68% solve at N=1 per the pass@N table).

## Direct recomputation confirms the match

Recomputed mean TOTAL attempts restricted to unsolved cells, straight from the same
`agent_states/*.json` files both analyses read:

| run | unsolved: mean TOTAL attempts | unsolved: mean PROPOSE-only | solved: mean TOTAL attempts |
|---|---|---|---|
| goedel_minif2f (n=704, 176 unsolved) | **18.90** | 4.27 | 2.14 |
| goedel_proofnet (n=558, 478 unsolved) | **23.63** | 5.18 | 6.30 |

18.90 and 23.63 match MECHANISM.md's reported 18.9 and 23.6 exactly. Solved-cell means (2.14, 6.30)
also match the table's 2.1 and 6.3 exactly.

## Bottom line

**F1's "18-33 attempts" = TOTAL (propose+refine) attempts, UNSOLVED cells only. The pass@N recount's
"1.94 mean propose attempts" = PROPOSE-only, ALL cells (solved+unsolved).** Same underlying data,
same `agent_states` files, no discrepancy — F1 is (and remains) a sound description of what happens
on cells the model never solves: it keeps refining/resampling for ~19-24 total attempts (~4-5
independent propose attempts plus their refinement chains) before exhausting budget, and still only
commits to ~2 distinct opening approaches across all of them. F1's mechanical basis is unaffected by
this session's calibration findings. (Separately, unsolved-cell PROPOSE-only means, 4.27/5.18, are
themselves still well short of a real pass@32 sample count — consistent with, and reinforcing, the
pass@N recount's finding that the trapped core was never tested at anything close to N=32.)
