# Equivalence bounds for Phase 1 scaffolding components (WS6 item 1)

Paired per-problem bootstrap (clustered by problem, all seeds of a problem resampled
together), 95% CI on the mean solve-rate delta (variant - baseline), in percentage
points. Upper/lower bound columns are the one-sided 97.5th/2.5th percentiles (same
numbers as the two-sided CI ends, labeled for the equivalence-testing framing: "this
component's true effect is below +Xpp with ~97.5% one-sided confidence").

| benchmark | component | n problems | point (pp) | 95% CI (pp) | upper bound (pp) |
|---|---|---|---|---|---|
| minif2f | retrieval | 244 | +3.42 | [+0.82, +6.15] | +6.15 |
| minif2f | memory | 244 | +0.41 | [-2.19, +3.01] | +3.01 |
| minif2f | reviewer | 244 | +0.27 | [-2.32, +2.87] | +2.87 |
| minif2f | tactic_skeletons | 244 | +0.96 | [-1.37, +3.42] | +3.42 |
| minif2f | budget_alloc__0 | 244 | +0.55 | [-2.05, +3.14] | +3.14 |
| minif2f | budget_alloc__2 | 244 | +0.41 | [-1.64, +2.46] | +2.46 |
| proofnet_sharp | retrieval | 186 | -6.45 | [-9.68, -3.76] | -3.76 |
| proofnet_sharp | memory | 186 | -0.36 | [-1.79, +1.08] | +1.08 |
| proofnet_sharp | reviewer | 186 | +0.54 | [-1.25, +2.33] | +2.33 |
| proofnet_sharp | tactic_skeletons | 186 | -0.54 | [-2.51, +1.25] | +1.25 |
| proofnet_sharp | budget_alloc__0 | 186 | -3.43 | [-5.78, -1.27] | -1.27 |
| proofnet_sharp | budget_alloc__2 | 186 | -0.36 | [-2.15, +1.08] | +1.08 |

## Phase 6 Stage A/B (SFT exposure-bias pilot), both models, both benchmarks, 3 seeds

Same paired per-problem bootstrap, base vs. each arm (A = generic RFT, B = closing-targeted SFT), merged across 3 single-seed run dirs per arm (`p6eval_{g,d}_{mf,pn}_{base,A,B}[_s1|_s2]`).

| model | benchmark | arm | n problems | point (pp) | 95% CI (pp) | upper bound (pp) |
|---|---|---|---|---|---|---|
| Goedel | miniF2F | A (generic RFT) | 244 | -19.67 | [-24.04, -15.57] | -15.57 |
| Goedel | miniF2F | B (closing-targeted SFT) | 244 | -2.05 | [-4.23, +0.14] | +0.14 |
| Goedel | ProofNet# | A (generic RFT) | 186 | -4.84 | [-7.17, -2.69] | -2.69 |
| Goedel | ProofNet# | B (closing-targeted SFT) | 186 | -1.97 | [-3.76, -0.54] | -0.54 |
| DeepSeek | miniF2F | A (generic RFT) | 244 | -12.57 | [-16.53, -8.88] | -8.88 |
| DeepSeek | miniF2F | B (closing-targeted SFT) | 244 | -0.27 | [-2.60, +1.92] | +1.92 |
| DeepSeek | ProofNet# | A (generic RFT) | 186 | -2.51 | [-4.84, -0.18] | -0.18 |
| DeepSeek | ProofNet# | B (closing-targeted SFT) | 186 | -0.90 | [-3.05, +1.25] | +1.25 |
