# Decomposition agent — design note (WS6 item 3, written before code, per project discipline)

**Purpose of this note**: this is the highest-value, most expensive item in WS6 (a new agent
capability, not a config change), and the user has explicitly asked for care over speed here — get
the design right before spending GPU time, so we don't discover a semantic bug after a 40+ GPU-hour
run and have to redo it. Every non-obvious decision below is written down WITH its reasoning so a
later reviewer (or a later me) can check it, and so a bug found later can be traced to a specific,
falsifiable assumption rather than re-derived from scratch.

## What we're testing

Step C (Section~\ref{sec:stepc}) established causally that approach discovery is not the bottleneck —
within-approach execution depth is. Every intervention tested so far targets discovery (diversity,
retrieval, hints), post-hoc adaptation (SFT, RL), or verification (hammer). None targets execution
depth directly. Subgoal decomposition does: if a trapped problem's proof requires N sequential
reasoning steps the model cannot reliably execute in one continuous generation, splitting it into
independently-provable `have` lemmas turns one N-step execution problem into several shorter ones —
directly attacking the mechanism F2/F3 diagnosed, not working around it.

**Pre-registered bar** (already committed, `PLAN_NEXT.md` WS6 item 3, restated here for the
implementation to target): material iff decomposition solves **>=5/55** on **Goedel x miniF2F's**
trapped core (**corrected 2026-07-25** — the first draft of this note said ProofNet#, but the 55-count
and the 6/55 pass@32 calibration figure being compared against are both miniF2F's; ProofNet#'s trapped
core is 150 and was never calibrated on Goedel, so there is no "what plain resampling already bought"
number to beat there. Caught during implementation, before any config/GPU work assumed the wrong
benchmark). The calibration cell's pass@32 already bought 6/55 via plain resampling on miniF2F —
decomposition has to clear what fresh sampling alone already bought, not just tie it, to count as a
genuine execution-axis result rather than another sampling-volume effect.

## Mechanics

1. **Propose a decomposition.** Prompt the model with the theorem statement and ask for: (a) a
   numbered list of `have` sub-lemmas (name + Lean proposition, in the theorem's own variable/
   hypothesis context) that would let a short closing tactic block finish the goal, and (b) that
   closing tactic block itself (may reference the haves by name, is expected to be short — this is
   the "assembly" step, not itself hard). Parseable, delimited output format (not free JSON — Lean
   syntax inside JSON strings is an escaping minefield; use a plain `HAVE i: <name> : <stmt>` /
   `MAIN:` block format with a regex extractor, mirroring how `WholeProofTemplate.extract_proof`
   already pulls code out of a fenced block).

2. **Structural sketch check, BEFORE spending anything on subgoal proving.** Build a sketch proof:
   the theorem header, then for each have, `have <name> : <stmt> := sorry`, then the proposed MAIN
   block. Verify this sketch via `backend.verify(theorem, sketch)` **directly** (NOT
   `Verifier.verify`, which would reject on the loophole policy — `sorry` is expected and desired
   here, this is a structural check, not a solve attempt). Accept the sketch iff
   `raw.success and raw.declares_goal and not raw.timed_out` — i.e. Lean actually elaborates the
   MAIN block against the (unproved) haves and finds no error. **This is the load-bearing soundness
   check for the whole approach**: without it, we would waste subgoal-proving budget on a
   decomposition whose haves don't even compose to close the goal, or whose have TYPES are malformed
   Lean the subgoal-prover would then be asked to prove nonsense against. Reusing `backend.verify`
   directly (not a new code path) means this reuses the exact same REPL/source-assembly machinery
   every other result already depends on — no new verification logic, only a new call site.

3. **Prove each subgoal independently.** For each accepted have, build a synthetic `Theorem` (name =
   `<parent>__have<i>`, statement = the have's own Lean proposition, SAME `imports`/`opens` as the
   parent so the subgoal has the same ambient context) and run a plain propose-only loop (no
   refinement, matching the calibration cell's own protocol — refinement per subgoal would blow up
   the budget accounting and isn't the thing being tested) against it, using
   `WholeProofAgent` reused as-is (not reimplemented) with `refine_enabled=False`. Each subgoal draws
   from the SAME shared `BudgetMeter`/`client` as the parent problem, so total spend across the
   decomposition attempt (sketch + all subgoals) is accounted against one per-problem budget, same
   accounting discipline as every other agent.

4. **Compose and do the real final check.** If every subgoal is solved, splice the parent's MAIN
   block with each have's now-VERIFIED (no-sorry) subproof:
   `have <name> : <stmt> := by\n  <indented subproof>` for each, followed by the original MAIN
   block. Verify this fully-composed, sorry-free proof through the **normal** `Verifier.verify` (full
   loophole policy, exactly like every other reported solve) — this is the number that counts as
   "solved," not the sketch check. If it fails (e.g. a subtle scoping/name-shadowing issue between
   independently-proved haves), the decomposition attempt fails and a new round starts (new sketch).

5. **Budget/rounds.** One "round" = one sketch + (if accepted) all its subgoal-proving sub-budgets.
   `max_rounds` bounds sketch attempts, mirroring `WholeProofAgent`. A generous but bounded
   per-subgoal round cap (e.g. 8 propose-only attempts per subgoal before giving up on that
   decomposition) keeps one hard subgoal from consuming the entire problem's budget on a single
   decomposition attempt — the whole point is testing several DIFFERENT decompositions if the first
   one's subgoals don't all pan out, same spirit as the existing agent's round structure.

## Known risks / things to check before trusting a run at scale (write these down NOW, verify in the smoke test, not after the full array)

- **Risk: the model emits a have whose statement is trivially unrelated to the goal but happens to
  compose (e.g. `have h : True := sorry` then ignores it in MAIN).** Not actually a soundness risk —
  step 4's final full verify still has to close the REAL goal, so a useless have just wastes a
  subgoal-proving budget slot, doesn't produce a false solve. Confirmed by code inspection (step 2
  only checks the sketch closes the goal; step 4 re-verifies the FULL real statement, not a relaxed
  one) — no test needed beyond the existing final-verify path, but flag it here so a reviewer doesn't
  have to re-derive this argument.
- **Risk: subgoal statements reference the parent's bound variables/hypotheses incorrectly** (e.g.
  the model writes a have that doesn't type-check in context even before `sorry`). Caught by step 2's
  structural check itself — if the have doesn't type-check, the sketch fails to elaborate, `raw.success`
  is False, decomposition rejected before any subgoal-proving spend. This is exactly why step 2 runs
  BEFORE step 3, not as a cheap-to-skip nicety.
- **Risk: extraction regex is too strict/loose and silently drops valid haves or MAIN blocks.** Needs
  a dedicated unit test with a realistic multi-have sample completion, not just a trivial one-have
  case — write this test FIRST per TDD, verify the parser round-trips a hand-written realistic
  example before wiring it into the agent loop.
- **Risk: shared BudgetMeter accounting double-counts or under-counts sketch vs. subgoal spend.**
  Since subgoal proving reuses `WholeProofAgent` against the SAME `client`/meter, this should compose
  for free (the meter tracks total spend regardless of caller) — but verify with a scripted-client
  test that asserts total spend after a full decomposition round equals the sum of every individual
  generate() call's tokens, not assumed.
- **Risk: cost blowup.** Worst case per problem = sketch cost x max_rounds + (subgoals x per-subgoal
  cap x max_rounds) generations. Must compute this explicitly from smoke-test timing before
  submitting the full array, exactly like the calibration cell's own GPU-hour estimate — do not
  skip this step even though it feels like "we already know the pattern from the calibration cell."

## Test plan (write failing tests first, per CLAUDE.md rule 1)

1. `test_parse_decomposition_completion` — realistic multi-have + MAIN completion text -> correct
   parsed `(haves: list[(name, stmt)], main: str)`, including edge cases (single have, have with a
   forall/exists in its statement, extra prose around the delimited block).
2. `test_sketch_check_accepts_valid_decomposition_scripted` — `ScriptedReplTransport` returns success
   for a sketch with sorries -> sketch accepted.
3. `test_sketch_check_rejects_malformed_decomposition_scripted` — scripted failure -> sketch rejected,
   zero subgoal-proving calls made (assert on the scripted transport's call count, not just the
   final verdict — catches a bug where rejection happens too late, after wasted spend).
4. `test_all_subgoals_solved_composes_and_verifies_final_proof` — scripted: sketch ok, both subgoals
   solve, final composed proof verifies -> `state.solved`, `state.proof` contains the composed text
   with real subproofs spliced in (not sorries).
5. `test_one_subgoal_unsolved_fails_round_tries_next_decomposition` — scripted: sketch ok, subgoal 2
   never solves within its cap -> round fails, agent proposes a fresh sketch (assert a second sketch
   prompt was rendered).
6. `test_budget_shared_across_sketch_and_subgoals` — scripted client counting total tokens spent,
   assert it equals the sum of all individual generate() calls (sketch + every subgoal attempt).

## Status

Design written 2026-07-25 (this session), before any implementation code. Implementation, tests, a
smoke config, and a smoke-test GPU run come next, in that order, before any decision about the full
55-problem x N-decomposition-rounds array. **Do not submit the full array until the smoke test has
been read carefully for all 5 risks above, not just "exit code 0."**

## Amendment 2026-07-26 — smoke3 result and a bounded final prompt iteration

smoke3 (job 11690238, budget=60000, max_rounds=3, revised have-sorry prompt from the first amendment)
completed cleanly (no truncation/infra issues) but scored 0/2, and — unlike smoke2's ambiguous mix of
truncation + one non-decomposed proof — this run gives a clean, decisive read: all 6 decompose attempts
(3 rounds x 2 problems) were `unparseable`, in exactly two failure shapes, both showing the model is
NOT decomposing, just choosing not to leave any usable sorry:
  (a) `aime_1988_p8`, all 3 rounds: a full brute-force attempt with ZERO sorries (nested nested `have`s,
      each closed with real tactics) — the model solved-or-tried-to-solve the whole thing inline.
  (b) `aime_1984_p7`, round 3 (not token-truncated, 19040/20480 tokens): a SINGLE `have` restating the
      entire goal, closed with `:= by sorry`, followed by a bare `sorry` MAIN — degenerate, correctly
      rejected by the bare-sorry-main check (this is exactly the failure mode that check exists for).
Rounds 1-2 of `aime_1984_p7` hit the 20480 sample_max_tokens ceiling before finishing at all.

This is now 3 independent smoke rounds (11684686, 11684726, 11690238) showing 3 different but
consistently non-decomposing behaviors from Goedel-Prover-V2-8B on trapped (i.e., hard-for-it)
problems: it either bulldozes a full attempt, or wraps the whole goal in one degenerate have+sorry.
Per DESIGN.md's own rule ("do not submit the full array until the smoke test has been read carefully
for all 5 risks, not just exit code 0"), this reads as risk #2 (the model does not reliably produce a
genuine multi-have decomposition) materializing, not risk #1 (parser bug) — the parser is behaving
exactly as designed on all 6 attempts.

**Decision:** rather than either (i) blind-launching the 55-problem array against a prompt that just
produced 0/2 structurally-valid decompositions across 3 independent smoke rounds, or (ii) open-ended
prompt iteration (explicitly against the WS6 stopping-rule discipline), take ONE more bounded shot:
added a concrete few-shot example to `_DECOMP_PROMPT` showing a genuine multi-`have` decomposition with
a real (non-sorry) closing tactic, plus an explicit "use MORE THAN ONE have unless the goal is
genuinely one step" instruction (directly targeting failure mode (b) above). Fast suite re-run green
(20/20, prompt-only change). This is smoke4 (submitted next). **Pre-registered stopping rule:** if
smoke4 does not produce at least one structurally-accepted sketch (sketch_accepted) on either of the 2
smoke problems, close WS6 item 3 as a documented NO-GO — no smoke5, no further prompt engineering. The
finding itself ("this model does not decompose into provable sub-lemmas without training for it, at
least via zero/few-shot prompting on problems it can't already solve") is a legitimate, reportable
negative result consistent with the paper's existing floor-mechanism story, not a wasted cycle.

## Amendment 2026-07-26 (cont.) — smoke4 result: NO-GO, item 3 CLOSED

smoke4 (job 11691968, few-shot prompt + explicit "use MORE THAN ONE have" instruction) still scored
0/2 with all 6 decompose attempts `unparseable` — zero `sketch_accepted` on either problem. Reading
`aime_1988_p8`'s attempts confirms the same failure mode as smoke3: the model writes a full inline
proof attempt (this time via a `have h_contradiction : False := by ...` proof-by-contradiction
skeleton with real, if unsuccessful, tactics) rather than deferring any step to `sorry`. Adding a
concrete few-shot example and an explicit anti-degenerate instruction did not change this.

**Per the pre-registered stopping rule (see amendment above): this is a NO-GO.** No smoke5, no further
prompt engineering. **Finding:** Goedel-Prover-V2-8B does not reliably produce `have`-`sorry`
decompositions via zero/few-shot prompting on problems it cannot already solve (trapped-core, by
construction the model has already failed all 3 baseline seeds at 128k tokens on these). Across 4
independent smoke rounds (11684686 wrong-format, 11684726 truncation+zero-sorry, 11690238
zero-sorry+degenerate-single-have, 11691968 zero-sorry despite few-shot), the model consistently
prefers to attempt a full (typically unsuccessful, since these ARE trapped problems) solution inline
rather than admit an unproven sub-step. This is consistent with the project's existing floor-mechanism
story (Step C: approach discovery isn't the bottleneck, within-approach execution is) — it further
suggests the model's training doesn't include an "honest decomposition with acknowledged gaps" mode at
all, which would itself require targeted training data to elicit (out of scope for a prompting-only
probe). **WS6 item 3 is CLOSED as a negative result: no 55-problem array launched, no GPU spent beyond
the ~4 smoke rounds (~2 GPU-h total).**

## Amendment 2026-07-26 (cont.) — DeepSeek-Prover-V2-7B probe: same NO-GO, second model

Per the user's 2026-07-26 request, ran the identical probe (already-validated few-shot prompt, no
further redesign) against DeepSeek-Prover-V2-7B on the same 2 trapped miniF2F problems (job 11693853,
new `slurm/phase_decomp_deepseek_run.sh`, `DecompositionAgent`/parser code unchanged). Result: 0/6
decompose attempts `sketch_accepted`, same as Goedel. Failure shapes:
  - `aime_1988_p8`: attempt 0 a full zero-sorry inline attempt; attempts 1-2 (byte-identical, model
    repeated its own completion deterministically) show THREE genuine `have`s (h3/h4/h5, each a real
    intermediate fact), closed by a bare `sorry` MAIN -- structurally closer to a real decomposition
    than anything Goedel produced (multiple genuine haves, not one degenerate wrapper), but still
    rejected by the same anti-vacuous-sketch check, correctly.
  - `aime_1984_p7`: attempt 0 truncated at the 16384-token sample cap without ever reaching Lean code
    (pure informal reasoning); attempts 1-2 (again byte-identical) a full zero-sorry nested-have
    attempt, same shape as Goedel's zero-sorry failure mode.

**This closes as NO-GO for DeepSeek too, under the same pre-registered rule** (this probe already used
the strongest prompt version, i.e. it is the "smoke4-equivalent" for this model — no further iteration).
Combined with the Goedel result, this is now a genuine **two-model finding**: neither
Goedel-Prover-V2-8B nor DeepSeek-Prover-V2-7B can be prompted into a genuine sorry-deferred
decomposition on a problem it cannot already solve, across 4 (Goedel) + 1 (DeepSeek, using the
already-matured prompt) independent generation attempts covering both models' own reasoning styles.
DeepSeek's near-miss (3 genuine haves, bare-sorry MAIN) is a useful texture note: the gap is
specifically in producing a real *closing* step from acknowledged sub-facts, not in generating
sub-facts at all -- consistent with the project's broader "closing/execution is the bottleneck" thesis
(Phase 6 Stage B, Phase 2 Step C), not a contradiction of it. WS6 item 3 total GPU spend: ~2.3 GPU-h
across 5 smoke rounds (4 Goedel + 1 DeepSeek).
