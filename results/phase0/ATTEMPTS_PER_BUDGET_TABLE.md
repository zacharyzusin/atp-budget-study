# Attempts-per-cell by budget, all 4 model x benchmark combinations

Phase 0 baseline runs only persist ONE trajectory per (problem,seed), generated against the
128000-token budget cap; the published pass@B curve at 2000/8000/32000 is reconstructed by
truncating that same trajectory to attempts whose CUMULATIVE `completion_tokens` fits within the
smaller budget (this is what `pass_at_b`/`solved_within` do internally — confirmed against
`src/atp/eval/metrics.py`). This table applies the identical truncation to attempt COUNTS, not just
solved/unsolved, so it directly shows how many propose/refine attempts a cell had actually completed
by the time each budget level was reached. `solved@budget%` reproduces the headline pass@B numbers
closely as a sanity check (e.g. goedel_minif2f 128000: 75.0% here vs the reported 74.9% ± 0.9%).

"propose" / "total" columns = mean/median/p90/max attempt count. "solved-1st-propose-within-budget"
= solved on the very first propose attempt (no refinement needed). "needed-refine" = solved, but
only after >=1 refinement step. "never-solved-within-budget" = unsolved at that budget level.

## goedel_minif2f (`results/baseline`)

| budget | n cells | propose mean/med/p90/max | total mean/med/p90/max | solved@budget% | solved-1st-propose-within-budget% | needed-refine% | never-solved-within-budget% |
|---|---|---|---|---|---|---|---|
| 2000 | 704 | 0.30/0/1/1 | 0.30/0/1/1 | 29.0% | 29.0% | 0.0% | 71.0% |
| 8000 | 704 | 0.82/1/1/1 | 0.92/1/1/4 | 59.8% | 58.1% | 1.7% | 40.2% |
| 32000 | 704 | 1.11/1/1/3 | 2.30/1/5/15 | 69.6% | 59.5% | 10.1% | 30.4% |
| 128000 | 704 | 1.94/1/4/14 | 6.33/1/19/67 | 75.0% | 59.5% | 15.5% | 25.0% |

## deepseek_minif2f (`results/deepseek_minif2f_baseline`)

| budget | n cells | propose mean/med/p90/max | total mean/med/p90/max | solved@budget% | solved-1st-propose-within-budget% | needed-refine% | never-solved-within-budget% |
|---|---|---|---|---|---|---|---|
| 2000 | 732 | 0.29/0/1/1 | 0.29/0/1/1 | 27.9% | 27.9% | 0.0% | 72.1% |
| 8000 | 732 | 0.84/1/1/1 | 0.92/1/1/4 | 57.9% | 57.0% | 1.0% | 42.1% |
| 32000 | 732 | 1.14/1/2/3 | 2.55/1/6/13 | 67.1% | 58.3% | 8.7% | 32.9% |
| 128000 | 732 | 2.22/1/5/12 | 7.75/1/22/55 | 72.0% | 58.3% | 13.7% | 28.0% |

## goedel_proofnet (`results/proofnet_baseline`)

| budget | n cells | propose mean/med/p90/max | total mean/med/p90/max | solved@budget% | solved-1st-propose-within-budget% | needed-refine% | never-solved-within-budget% |
|---|---|---|---|---|---|---|---|
| 2000 | 558 | 0.16/0/1/1 | 0.16/0/1/2 | 4.8% | 4.8% | 0.0% | 95.2% |
| 8000 | 558 | 0.68/1/1/2 | 1.25/1/3/7 | 9.3% | 6.8% | 2.5% | 90.7% |
| 32000 | 558 | 1.51/1/3/6 | 5.40/5/11/27 | 12.0% | 6.8% | 5.2% | 88.0% |
| 128000 | 558 | 4.71/4/8/23 | 21.14/18/39/112 | 14.3% | 6.8% | 7.5% | 85.7% |

## deepseek_proofnet (`results/deepseek_proofnet_baseline`)

| budget | n cells | propose mean/med/p90/max | total mean/med/p90/max | solved@budget% | solved-1st-propose-within-budget% | needed-refine% | never-solved-within-budget% |
|---|---|---|---|---|---|---|---|
| 2000 | 1488 | 0.13/0/1/1 | 0.13/0/1/2 | 5.8% | 5.8% | 0.0% | 94.2% |
| 8000 | 1488 | 0.87/1/1/2 | 1.47/1/3/7 | 13.0% | 10.5% | 2.6% | 87.0% |
| 32000 | 1488 | 1.79/2/3/7 | 6.82/6/12/31 | 18.0% | 10.6% | 7.4% | 82.0% |
| 128000 | 1488 | 5.85/6/10/19 | 26.79/26/46/93 | 22.8% | 10.6% | 12.2% | 77.2% |

## The single most notable pattern

**At budget=2000, the MEDIAN cell across all 4 runs completes ZERO full propose attempts** (median
propose count = 0 in every run at B=2000). The low-budget cells are not "one quick sample then done"
— for the majority of cells, the very first generation call itself doesn't finish within 2000 tokens,
so cumulative spend never crosses even one full attempt's cost before the ledger is exhausted. This
means the 2k point on every pass@B curve is measuring something closer to "did a partial/truncated
first attempt happen to already contain a complete, correct proof" than "did the model get to try."
Attempt counts scale roughly linearly with budget on miniF2F (mean propose 0.30 -> 0.82 -> 1.11 ->
1.94 across 2k->8k->32k->128k, i.e. ~1 extra propose attempt per ~4x budget increase, consistent with
median proof length being a few thousand tokens) but the SOLVE rate saturates much faster than
attempt count does (59.8% at 8k vs 75.0% at 128k despite propose attempts only going 0.82->1.94) —
i.e. most of the achievable gain from 8k to 128k already exists in the CURVE's low end, and the
refinement chain (not more propose samples) accounts for a growing share of solves at higher budgets
(needed-refine: 0.0% @2k -> 15.5% @128k on miniF2F, 0.0% -> 12.2% on DeepSeek-ProofNet#). ProofNet#
never even approaches this saturation — propose attempts keep climbing (0.16->4.71 on Goedel) while
solved% barely moves (4.8%->14.3%), the flattest of the four.
