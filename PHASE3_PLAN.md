# Phase 3 — Hardening & Writeup Plan (lock the negative thesis, reviewer-proof)

*Created 2026-06-20. Origin: external review of the completed Phase 2 arc (see scratch/NEXT_STEPS_QUERY.md
for the results message that prompted it). Verdict from that review: the scientific arc is COMPLETE and
reached the right way (Phase 1 null → Phase 2 mechanism → F6 interventional close, on two provers). Before
locking, do four cheap CPU-only hardening checks that protect exactly the claims a sharp reviewer attacks,
apply two reframings, then write the paper. NO new GPU sweeps — that arc is saturated.*

## Guiding principle
Every load-bearing claim must be reviewer-proof. The four checks below are ordered by falsification
payoff: H1 and H2 can in principle overturn a conclusion (do them first); H3/H4 strengthen and unify.

## Hardening tasks (all CPU / analysis / human-reading — no GPU)

### H1 — Recompute the cross-model dichotomy on the compile-on-both-pins INTERSECTION  [GATE: highest scrutiny]
The dichotomy (DeepSeek 22.2 vs Goedel 14.3 @128k on ProofNet#) is our one positive, most-scrutinized
thread. Baselines ran on NATIVE ports (Goedel = mathlib fork files; DeepSeek = standard mathlib files) →
different statement sets, so part of the gap could be a coverage artifact. We built the intersection gate
for exactly this.
- Find/define the intersection: problems whose STATEMENT compiles/validates on BOTH Lean pins.
- Recompute pass@B for BOTH models restricted to that intersection (both benchmarks).
- Report: intersection size; native-port vs intersection pass@B side by side; does the dichotomy SURVIVE?
- Outcome: gap survives → real, lean on it. Gap shrinks → caught a confound before a reviewer; reframe.

### H2 — Human-validate the failure taxonomy  [GATE: could overturn the retrieval-killing claim]
"~0% knowledge / 94–100% reasoning_deep" is what KILLS retrieval (not defers it); it rests entirely on the
regex auto-classifier (_classify in analyze_mechanism.py). Hand-audit a stratified sample of 50–100
unsolved attempts PER PROVER by reading the actual Lean feedback, assign a human label, compare to the
auto-label. Report a confusion matrix + agreement rate, and specifically the false "reasoning vs knowledge"
rate. Turns "we assert" into "we verified." (Claude reads the raw feedback as the human labeler; surface a
handful of ambiguous cases for the user to adjudicate if needed.)

### H3 — Quantify soundness-creep across ALL scaffolding components (not just Step C)
Generalize C-3. From existing logs, compute malformed / loophole_sorry / would-be-false-positive rates for
every Phase 1 component (retrieval, memory, reviewer, tactic_skeletons, budget_alloc) AND Step C diversity,
vs baseline. If creep appears across components to varying degrees, the claim upgrades from "forced
diversity degrades output" to "scaffolding systematically shifts proving output toward less-sound regions;
a naive (un-hardened) pipeline would report inflated pass rates." Backbone, not headline.

### H4 — Decompose the OOD dichotomy through the F1/F3 lens (cheap "chase")
Don't chase the dichotomy with sweeps (that's a model-zoo paper). Instead run our OWN F1/F3 mechanism
analysis on the dichotomy: does DeepSeek's OOD advantage come from (a) LESS diversity collapse (more
viable approaches explored) or (b) DEEPER within-approach execution (closing goals Goedel stalls on)?
CPU-only on existing traces, on the intersection (post-H1). Converts "DeepSeek mysteriously better OOD"
into a mechanistic statement and UNIFIES the spine: search-time scaffolding can't move the execution
floor, but the prover's TRAINING can, substantially, on OOD → the real OOD lever is the model, not
scaffolding. Tighter thesis than "budget is the lever."

## Reframings (apply in SYNTHESIS.md / MECHANISM.md / paper)
- R1 — Dichotomy is TRAINING-DISTRIBUTION / RECIPE, not model size. A 1B param diff (8B vs 7B) across
  models differing in data, RL recipe, base model, and mathlib cannot carry a size claim. State that
  isolating the cause needs a controlled model-zoo study (future work).
- R2 — Soften F3: "attempts elaborate substantially before failing" (NOT "real progress into proofs").
  deepest-step-reached is depth-before-failure, not verified correct progress.

## Output / writeup
- W1 — Paper for TMLR (empirical/analysis; no novelty bar, values rigor over SOTA, archival; the right home
  for a carefully-executed mechanistic negative result). Working title: "Budget, Not Scaffolding: A
  Mechanistic, Two-Model Study of Whole-Proof Theorem Proving at Modest Scale."
  Lead thesis (for compute-constrained ATP groups — "where NOT to spend"): at fixed model scale, compute
  budget is the only effective lever among the agentic scaffolding components tested; it saturates because
  the model collapses to ~2 approaches per hard problem and the residual is an EXECUTION floor, not a
  premise gap; the real lever for OOD math is the prover's TRAINING, not search-time scaffolding; and
  verifier hardening is non-optional because scaffolding worsens soundness.
  Soundness-creep = a dedicated section / secondary methodological contribution (backbone, not headline).
- W2 — Short version to a formal-reasoning/math-AI workshop (NeurIPS MATH-AI or ICML AI-for-Math) in
  parallel for early feedback. Check current deadlines (they move).
- W3 — Artifact release regardless: arXiv preprint + code + figures + metrics.json + analysis scripts.
  Practicing what the paper preaches (reproducible, auditable) — a real strength given the soundness thread.
- Figures: pass@B 2×2 (both models × both benchmarks); native-vs-intersection dichotomy; Step C
  manipulation-check-vs-solves bar; soundness-creep-across-components bar; H4 decomposition.

## Execution order
H1 → H4 (depends on H1's intersection) → H3 → H2 → apply R1/R2 to docs → draft paper (W1) + figures →
workshop/arXiv/artifact (W2/W3). H1–H4 first because they gate what we can claim. Lock the thesis once
H1–H4 pass. No GPU.
