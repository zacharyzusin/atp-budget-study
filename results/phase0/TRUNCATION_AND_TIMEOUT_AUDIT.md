# Phase 0 — Truncation (token-cap) and heartbeat-timeout audit

(a) Truncation proxy: no `finish_reason` was persisted per attempt in these runs (`client.py`'s `finish_reason` field exists in the live client response but is not saved into `agent_states`), so we proxy truncation as `completion_tokens >= CALL_CAP - 8` on PROPOSE attempts (CALL_CAP = `max_model_len // 2`: 20480 for Goedel, 16384 for DeepSeek — src/atp/agents/whole_proof.py:80). This is a lower bound: a completion could also be clamped below CALL_CAP by remaining budget, which this proxy would miss.
(b) Heartbeat-in-refinement: among REFINE attempts, how many were preceded by a prior attempt (in the same chain) whose feedback contains the Lean heartbeat-timeout marker text, vs. a separate harness-level wall-clock verification timeout (`reason == 'timeout'`, distinct bucket, 120s Lean-process timeout, not a Lean elaboration heartbeat).


## goedel_minif2f (`results/baseline`)

- attempt `reason` histogram: {'ok': 528, 'compile_error': 3638, 'loophole': 133, 'timeout': 160}

- PROPOSE attempts at/near the per-call token cap (20480 tokens): 67/1369 (4.89%)

- REFINE steps immediately preceded by a Lean heartbeat-timeout error: 550/3090 (17.80%)

- REFINE steps immediately preceded by a harness wall-clock verification timeout (120s, distinct from the Lean heartbeat): 129/3090 (4.17%)


## deepseek_minif2f (`results/deepseek_minif2f_baseline`)

- attempt `reason` histogram: {'ok': 527, 'compile_error': 4977, 'timeout': 79, 'loophole': 90}

- PROPOSE attempts at/near the per-call token cap (16384 tokens): 17/1627 (1.04%)

- REFINE steps immediately preceded by a Lean heartbeat-timeout error: 718/4046 (17.75%)

- REFINE steps immediately preceded by a harness wall-clock verification timeout (120s, distinct from the Lean heartbeat): 61/4046 (1.51%)


## goedel_proofnet (`results/proofnet_baseline`)

- attempt `reason` histogram: {'compile_error': 11460, 'ok': 80, 'loophole': 246, 'no_goal': 9, 'timeout': 3}

- PROPOSE attempts at/near the per-call token cap (20480 tokens): 220/2627 (8.37%)

- REFINE steps immediately preceded by a Lean heartbeat-timeout error: 307/9171 (3.35%)

- REFINE steps immediately preceded by a harness wall-clock verification timeout (120s, distinct from the Lean heartbeat): 2/9171 (0.02%)


## deepseek_proofnet (`results/deepseek_proofnet_baseline`)

- attempt `reason` histogram: {'compile_error': 38144, 'ok': 339, 'loophole': 780, 'timeout': 605, 'no_goal': 2}

- PROPOSE attempts at/near the per-call token cap (16384 tokens): 8/8702 (0.09%)

- REFINE steps immediately preceded by a Lean heartbeat-timeout error: 511/31168 (1.64%)

- REFINE steps immediately preceded by a harness wall-clock verification timeout (120s, distinct from the Lean heartbeat): 493/31168 (1.58%)
