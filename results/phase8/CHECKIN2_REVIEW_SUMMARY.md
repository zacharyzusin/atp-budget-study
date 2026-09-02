# Phase 8 check-in #2 — where things stand (review summary for coordinator)

## The arc

Phase 8 set out to test whether RL post-training moves this project's central "execution floor"
finding (Phases 0-6 established that scaffolding, search, hammers, budget reallocation, and even
SFT-style fine-tuning and LoRA-RL can't close the OOD gap — only training seems to matter). Phase 8's
plan was a natural experiment: take matched-lineage checkpoint triples/pairs (Base→SFT→RL) from labs
that already did full-pipeline RL, and see if the RL stage shows a lower floor than its own SFT
sibling.

**Round 1 result (looked like a discovery):** DeepSeek-Prover-V1.5 Base<SFT<RL, clean and monotonic
across all seeds, both benchmarks (miniF2F floor: 4.8→13.7→19.0pp). The coordinator correctly did not
accept this — flagging the Stage C contradiction, the RL-vs-more-training confound, and the missing
contamination check.

**What that scrutiny actually surfaced:** chasing those objections uncovered that the "discovery" was
built on sand. In order:

1. A project-wide wiring bug (`WholeProofAgent.from_config`, present since the very first commit)
   silently ignored every model's configured prompt template and served all of them
   `WholeProofTemplate`'s chat-style prompt regardless.
2. Fixing that exposed a second, independent bug: both Lean-verification backends
   (`PantographBackend`, `ReplBackend`) never reconstructed the `theorem ... := by` header for
   continuation-style completions — bare tactics landed as top-level Lean commands, guaranteed parse
   failures.
3. Fixing that exposed a third: missing `import Aesop` / `set_option maxHeartbeats 0`, byte-verified
   against the labs' own reference scripts.
4. A fourth candidate (dropped `informal_statement` doc-comment) was tested at increasing scale, moved
   completions modestly longer/more coherent but produced 0/160 solves — correctly not chased further
   per the pre-committed stop-rule.

**Corrected result, after all three real bugs fixed:** across both matched lineages (DeepSeek-V1.5
triple, Leanabell GD-SFT→GD-RL pair), both benchmarks, all three budgets, 5,586 re-verified cells —
**0.0% ± 0.0 everywhere.** Not noisy-near-zero: literally zero solves in every one of the 10 run
directories. The clean monotonic pattern from round 1 evaporated entirely; it was 100% a wiring-bug
artifact.

**Net effect on the project's central thesis:** this is now a *fourth* independent line of evidence
(after Stage B's SFT-exposure-bias null, Stage C's LoRA-GRPO null, and now two full-pipeline lab-RL
lineages) that RL — lightweight or full-scale — does not move the execution floor. The working read
is that this supports **definitive-negative**, but that headline call is explicitly the
coordinator's/user's.

## Questions to think over

1. **Do you agree with definitive-negative**, or does the sheer number of bugs found along the way
   make you want one more independent sanity check before trusting a literal 0.0% (e.g.,
   re-confirming Goedel-Prover-V2/DeepSeek-Prover-V2-7B — the two models *unaffected* by all three
   bugs — still score their expected nonzero numbers under the current, fully-patched codebase, as a
   "the harness itself isn't broken" control)?

2. **Is Phase 8 the natural end of the mechanism-hunting arc (Phases 6-8)?** If RL is closed as a
   lever, is there any remaining lever worth trying, or is the search over and this project ready to
   move to synthesis/writeup?

3. **What form should the final deliverable take** — a consolidated internal SYNTHESIS.md tying
   Phases 0-8 together, or something more like a paper writeup? (Note: there is a standing preference
   on record against paper-framing for the *separate* Neural AO* theorem-proving project — unclear if
   that preference extends to atp-budget-study, so flagging rather than assuming.)

4. **Loose ends worth closing before calling Phase 8 done, or worth abandoning:** the still-unfixed
   project-wide missing-`stop`-sequence issue in `client.py` (logged, never fixed, didn't explain any
   of the bugs found but is real debt); Cluster B breadth (STP, other Leanabell siblings) never
   started; the one still-running `gdrl_minif2f` re-verify job.

5. **GPU-h/scope going forward** — hard stop on new experiments now, or appetite for one more
   targeted probe if question 1's control check reveals anything?
