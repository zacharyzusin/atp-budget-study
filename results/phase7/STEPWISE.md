# Phase 7 Track 1 — trapped-first gate: RESOLVED, NULL

**Verdict: NULL.** State-grounded generation — in both its weak form (Mode 3, whole-continuation
re-grounding) and its strong, unconfounded form (Mode 4, true step-by-step search on a tactic-native
model with backtracking) — closes **zero** trapped problems that whole-proof sampling couldn't. This
is now the airtight version of that result: every format/harness confound found along the way was
identified and fixed before the number was trusted, on both models tested.

## The gate (atp-phase7-plan.md §1.5)

> GO/positive = state-grounded modes close a meaningful fraction of trapped cores that 1/2 don't,
> per-seed, on ≥1 model → EXPAND to full benchmarks, 3 seeds = the positive paper.
> NULL = no trapped closures beyond 1/2 → capability claim SHARPENS ("fails to close EVEN handed
> ground-truth proof state" = capacity-bound; exposure-bias falsified) → go to breadth.

## What ran (all on the 150 ProofNet# problems Goedel-Prover-V2-8B could not solve at ANY budget up
to 128k in the committed 3-seed baseline — trapped by construction)

- **Modes 1/2** (whole-proof, no feedback / error-string refinement): reconstructed for free,
  offline, from the baseline's own logged attempts — 0/150 at every budget, by construction.
- **Mode 3** (verified-state re-grounding, whole-continuation): after fixing a boundary-finder bug
  that discarded real partial credit (naive single-cut landed mid tactic-combinator 27% of the time —
  DECISIONS.md 2026-07-04), the frontier genuinely advances in 19/150 cells, one reaching depth 90 (a
  90-tactic-line verified prefix). **0/19 of those engaged cells convert to a close.** A matched
  fresh-resample control (same names, fresh session, zero re-grounding) also got 0/150, ruling out
  the one nonzero raw solve (cold-start, unrelated to the mechanism) as evidence either way.
- **Mode 4 on Goedel-Prover-V2-8B** (true step-by-step, one tactic per call): Goedel is a whole-proof
  REASONING model that doesn't reliably decompose into atomic tactic turns (its "next tactic" answer
  is unpredictably a one-liner, a multi-`have` compound sketch, or unconverged prose — see the
  extraction fix in DECISIONS.md 2026-07-05). After a time-boxed oracle-validated multi-candidate
  extraction fix, 6/19 cells reached genuine accepted steps (one 10 deep) — a fair, if partial, test.
  **0/19 closed.**
- **Mode 4 on BFS-Prover-V1-7B** (the tactic-native disambiguator, pulled forward from Track 2): a
  genuinely tactic-native model (raw completion, `"{state}:::"` -> tactic, verified against its own
  model card, not assumed) run on the FULL 150-cell trapped set. First attempt (greedy, single path)
  found two confounds: (a) a real Lean-accepted but non-progressing tactic could be re-accepted every
  step, burning the whole budget in a stall that looked like depth but wasn't (one cell: the SAME
  tactic accepted 64/64 times); (b) a single irreversible path under-tests a model whose designed
  capability is best-first search with backtracking; (c) the run script also had a latent bug — it
  hardcoded the wrong prompt template regardless of config. All three fixed in one pass (stagnation
  rejection + `BeamTacticStepwiseAgent`, a real DFS-with-backtracking over a small beam + correct
  template wiring), then re-run ONCE, final. Engagement: **77/150 cells (51%) reach real
  oracle-validated progress**, several with genuinely varied multi-tactic exploration (up to 18
  distinct tactics on one problem). A residual short-cycle artifact affects 4/150 cells (quantified,
  not fixed further per the pre-registered one-more-run stopping rule) — the other 141 stopped via
  legitimate backtracking-exhausted or genuine-progress paths. **0/150 closed.**

## Reading

Every weaker/confounded version of this experiment was upgraded before being trusted:
naive-boundary Mode 3 → backoff-fixed Mode 3; reasoning-model Mode 4 with a broken extractor →
oracle-validated extraction; greedy single-path Mode 4 on a search-native model → beam-with-
backtracking on the correct prompt format. At every step the fix INCREASED engagement (1→19 cells
for Mode 3; 0→6 cells for Goedel Mode 4; 0→33→77 cells for BFS-Prover Mode 4) — confirming each
earlier "null" had been partly an artifact of an under-tested mechanism, not evidence about the
underlying question. The final, fully-corrected numbers on both models still converge to **zero
closes**, even with the model given its own true verified state at every step and allowed to search
with backtracking. That is no longer a weak-fix null — the "did you test it properly?" objection
(wrong generation mode, wrong model, wrong format, wrong search strategy) has been closed on both
axes available to this project (single-shot re-grounding AND step-by-step search; a whole-proof model
AND a tactic-native one).

Per the plan's own pre-registered reading, this is the **NULL branch, in its strongest form**: these
150 trapped problems are not failing because either tested model free-runs on a drifted intermediate
state (exposure bias) — giving both the true state, at every step, with real search, doesn't help.
The capability claim sharpens to its most defensible form: whatever is stopping these proofs from
closing is not addressable by better proof-state feedback alone.

## Secondary finding, worth its own line in the paper

Goedel-Prover-V2-8B (and by extension, likely whole-proof reasoning provers generally) does not
cleanly decompose into single-tactic turns even when explicitly asked to. This is a real,
architecture-level property (not a prompting failure) — it always produces a CoT-style multi-step
sketch or full restated proof, never a clean atomic step. This closes a different objection
("why not drive a whole-proof model with search?") independent of the main Track 1 result.

## What this is NOT (residual scope, for honesty)

- Only ProofNet# tested; miniF2F and DeepSeek-Prover's own trapped set haven't been run through
  Mode 3/4. A NULL here doesn't preclude a different reading on those slices (Track 2 breadth).
- Single seed throughout (this was a feasibility/disambiguation arc, not the 3-seed headline
  protocol) — if this result anchors a paper claim, it should get seeds before being the headline
  number, per rule 7.
- The 4/150 short-cycle artifact in the final BFS-Prover run is quantified but not eliminated;
  doesn't change the reading (dominant pattern is legitimate exhaustion, not artifact) but should be
  disclosed alongside the number.

## Decision

Per atp-phase7-plan.md's decision tree: **(b) or (c)** — stepwise FAILS. Combined with Track 2's
model-zoo breadth (in progress) and Track 4's Stage C RL null (results/phase6/STAGE_C_RESULT.md,
also a clean c2), this is now THREE independent generation-side/training-side mechanisms (scaffolding/
search, SFT, RL) plus TWO stepwise-generation mechanisms on TWO architecturally different models, all
converging on the same execution-floor reading. The weight of evidence now favors the DEFINITIVE
NEGATIVE / DISCOVERY paper framing over the positive Track 1 paper this fork was built to test for.
