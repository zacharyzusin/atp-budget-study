# Phase 0 — Recount as pass@N (vs pass@128k-tokens)

Empirical pass@N computed from the SAME 128k-token-budget Phase 0 runs already reported in SYNTHESIS.md, just re-sliced by attempt count instead of token spend. N counts PROPOSE (fresh whole-proof sample) attempts only, per (problem, seed) — refinement iterations chained off a specific propose are a different mechanism (this harness's own scaffolding, present even in the 'no-frills' baseline via max_iters=4) and are reported separately below, not folded into N, since literature pass@N is plain independent sampling with no refinement layer.


## goedel_minif2f (`results/baseline`)

- propose-attempt count per (problem,seed): mean=1.94, median=1, p90=4, max=14
- total attempt count (propose+refine): mean=6.33, median=1, p90=19, max=67

| N (propose attempts) | pass@N |
|---|---|
| 1 | 68.0% |
| 2 | 70.5% |
| 4 | 74.6% |
| 8 | 75.0% |
| 12 | 75.0% |
| 16 | 75.0% |
| 24 | 75.0% |
| 32 | 75.0% |
| 48 | 75.0% |
| 64 | 75.0% |


## deepseek_minif2f (`results/deepseek_minif2f_baseline`)

- propose-attempt count per (problem,seed): mean=2.22, median=1, p90=5, max=12
- total attempt count (propose+refine): mean=7.75, median=1, p90=22, max=55

| N (propose attempts) | pass@N |
|---|---|
| 1 | 64.8% |
| 2 | 69.3% |
| 4 | 72.1% |
| 8 | 72.1% |
| 12 | 72.5% |
| 16 | 72.5% |
| 24 | 72.5% |
| 32 | 72.5% |
| 48 | 72.5% |
| 64 | 72.5% |


## goedel_proofnet (`results/proofnet_baseline`)

- propose-attempt count per (problem,seed): mean=4.71, median=4, p90=8, max=23
- total attempt count (propose+refine): mean=21.14, median=18, p90=40, max=112

| N (propose attempts) | pass@N |
|---|---|
| 1 | 7.5% |
| 2 | 9.1% |
| 4 | 11.8% |
| 8 | 11.8% |
| 12 | 12.4% |
| 16 | 12.4% |
| 24 | 12.4% |
| 32 | 12.4% |
| 48 | 12.4% |
| 64 | 12.4% |


## deepseek_proofnet (`results/deepseek_proofnet_baseline`)

- propose-attempt count per (problem,seed): mean=5.85, median=6, p90=10, max=19
- total attempt count (propose+refine): mean=26.79, median=26, p90=46, max=93

| N (propose attempts) | pass@N |
|---|---|
| 1 | 16.7% |
| 2 | 18.8% |
| 4 | 19.4% |
| 8 | 21.0% |
| 12 | 22.0% |
| 16 | 22.0% |
| 24 | 22.6% |
| 32 | 22.6% |
| 48 | 22.6% |
| 64 | 22.6% |
