# WS6 item 4: v2 predictor result (seed-holdout guarded)

Pre-registration: `results/phase4/PREDICTOR_V2_DESIGN.md`. All CV AUCs computed on seeds {0,1} only; seed 2 evaluated exactly once, held out from feature/model selection.

| model | c | AUC v1 (s01) | AUC v2 (s01) | gain | AUC v2 (heldout s2) |
|---|---|---|---|---|---|
| goedel | 2000 | 0.644 | 0.639 | -0.005 | 0.531 |
| goedel | 4000 | 0.710 | 0.663 | -0.047 | 0.529 |
| goedel | 8000 | 0.517 | 0.499 | -0.018 | 0.560 |
| goedel | 16000 | 0.728 | 0.734 | 0.006 | 0.617 |
| goedel | 32000 | 0.539 | 0.548 | 0.009 | 0.484 |
| deepseek | 2000 | 0.411 | 0.443 | 0.033 | 0.569 |
| deepseek | 4000 | 0.582 | 0.532 | -0.049 | 0.689 |
| deepseek | 8000 | 0.588 | 0.521 | -0.067 | 0.684 |
| deepseek | 16000 | 0.685 | 0.656 | -0.029 | 0.652 |
| deepseek | 32000 | 0.711 | 0.604 | -0.107 | 0.518 |

**Max AUC gain (v2 vs v1, seeds 0,1 CV) across all cells: +0.033**

