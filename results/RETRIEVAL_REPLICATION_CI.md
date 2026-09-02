# Retrieval replication run: paired bootstrap CI (WS6 item 1 follow-up)

Same paired per-problem bootstrap as `EQUIVALENCE_BOUNDS.md`, computed on the INDEPENDENT
replication run (`results/phase1_retrieval_budget`, job 10461442) instead of the original
Phase 1 run (job 10436909). Original-run CI @8k: [+0.82, +6.15]pp (entirely positive).

| budget | n problems | point (pp) | 95% CI (pp) |
|---|---|---|---|
| 2000 | 244 | +2.19 | [+0.00, +4.51] |
| 8000 | 244 | +0.68 | [-1.78, +3.14] |
| 32000 | 244 | -0.82 | [-2.73, +1.09] |

**Reading.** If these CIs do not all contain the original run's [+0.82,+6.15]pp @8k
point, that is direct, quantified confirmation that within-run bootstrap CIs bound
only sampling variance conditional on one generation campaign, not run-to-run
(campaign-level) variance -- the stronger, more general methods lesson (applies to
any paper reporting a bootstrap CI over a single generation run, not just this one).
