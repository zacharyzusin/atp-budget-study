# Codebase & Results Audit Plan

> **For agentic workers (Sonnet implementer):** Execute task-by-task with `superpowers:executing-plans`.
> Steps use checkbox (`- [ ]`) syntax. This audit GATES `PLAN_NEXT.md` WS1 — no new GPU sweep is
> submitted until Tasks A0, A1, A2, and B clear (or their impact is quantified and bounded).

**Goal:** Independently establish whether any code defect has distorted a *reported* empirical number
(pass@B curves, the Phase 4 allocation result, the mechanism findings, the Phase 6–8 nulls), so we can
state each headline finding with justified confidence — not on the strength of the Phase 8 taint-audit
*reasoning* alone, but on direct re-verification.

**Why now:** Phase 8 surfaced **four** latent bugs that had shipped for weeks and passed the fast test
suite (SYNTHESIS.md Lesson 8). The taint audit concluded they touched only Phase 8 — but it examined
exactly one bug class (the `WholeProofAgent.from_config` template-wiring bug). Three findings from this
audit's own recon already show the taint audit was too narrow to be the last word:
1. **The Phase 7 + Phase 8 fixes are entirely UNCOMMITTED.** `git status` shows `src/atp/lean/repl.py`,
   `backends.py`, `whole_proof.py`, `models/templates.py` modified; last commit is `aec81a2` ("Phase 6").
   All four bug fixes + the results docs live only in the working tree — unversioned, one `git checkout`
   from deletion.
2. **`set_option maxHeartbeats 0` was added to the verifier on 2026-07-06 (Phase 8), in that uncommitted
   diff.** Every Phase 0–7 headline number was therefore produced under Lean's *default* heartbeat limit.
   If any prover's heavy `nlinarith`/`simp`/`field_simp` proofs spuriously timed out on heartbeats, the
   Phase 0–7 pass@B curves are **understated** and part of the "execution floor" could be a heartbeat
   artifact. The 37/37 & 40/40 harness-sanity control only proved *solved-stays-solved*; it never tested
   *previously-failed-now-passes*. **This is the audit's highest-value question.**
3. The `no_goal` soundness gate (`verifier.py:104`) and the source assembler (`repl.py:_build_repl_source`,
   `backends.py:_build_source`) touch *every* verdict and now disagree between the two backend classes on
   the complete-file (`whole_proof`) case — worth confirming the production path is internally consistent.

**Architecture of the audit:** Order tasks by *blast radius* — a bug in the scoring/verifier path
mis-scores every number, so it is audited first and hardest. Each task ends in a written verdict in the
findings ledger (`results/audit/AUDIT_FINDINGS.md`): **CLEAN** (with the evidence that shows it), **BUG**
(with a failing test against real data → fix → passing test → list of affected results to re-run), or
**AMBIGUOUS** (needs a GPU re-verify to resolve — becomes a user handoff). CPU-only wherever possible;
GPU re-verification of affected cells is a user handoff following `PLAN_NEXT.md` §0.3.

**Tech stack:** Python 3 / pytest (fast suite is login-node safe), the on-disk `results/**/agent_states/*.json`
and `results/**/problems/*.json` records (both store per-attempt `proof`, `ok`, `reason`,
`completion_tokens`), the Goedel-pin Lean REPL (`ReplBackend`) for offline re-verification, `git`.

## Global Constraints

- **Do not mutate any file under `results/` that records a past run.** The audit READS historical cells
  and WRITES only under `results/audit/`. Re-verification writes new files; it never overwrites originals.
- **Every claimed re-verification runs through the *current* patched `ReplBackend`** (the production path,
  `src/atp/eval/run.py:126`) — the same code `PLAN_NEXT.md` WS1 will use — so the audit certifies the
  exact harness the next phase depends on.
- **Test-first for every fix** (`feedback_test_before_submit`): the failing test must exercise the bug on
  **real recorded data**, not a synthetic example that dodges it (Lesson 8).
- **Pre-register** each re-verification's decision rule in `DECISIONS.md` before running it — including the
  threshold at which a delta is "material" (reuse the noise bar: a mean-delta < ~1 baseline-σ ≈ 1.5–3pp is
  noise; DECISIONS 2026-06-11).
- **≥3 seeds** for any re-computed headline number; report mean ± seed-std.
- Append a dated `PROGRESS.md` entry per session; log each verdict to the ledger as it lands.
- Infra: `unset *_PROXY` in every Slurm script (`reference_insomnia_compute_proxy`); node-local olean
  staging + `norm_num` probe gate (`reference_lean_repl_cluster`); never pickle the Lean env.

---

## Task A0 — Freeze a versioned baseline BEFORE auditing (BLOCKING, do first)

The audit cannot run against a working tree that a stray command could wipe, and it must be able to `git
diff` each fix against a known-good point. Commit the current state as the "post-Phase-8, pre-audit"
baseline.

**Files:** all currently-modified tracked files (`git status -s`), plus the untracked Phase 8 configs and
`RESEARCH_COMPILATION.md`. Do **not** commit anything under `results/` (gitignored — confirmed) or model
weights/caches (`scratch/`).

- [ ] **Step 1 — Inspect, don't trust.** `git status -s` and `git diff --stat HEAD`. Read the full diff of
  each `src/` file (`git diff HEAD -- src/`) and confirm every change corresponds to a documented Phase 7/8
  fix (wiring, assembly, maxHeartbeats, informal_statement, templates). Flag anything that does *not*.
- [ ] **Step 2 — Run the fast suite green first.** `make test` (or `pytest -q`). Record the pass count.
  Do not commit a red baseline.
- [ ] **Step 3 — Review staging for secrets/junk** before adding: no endpoint files, no `_vllm_endpoint*`,
  no tokens. `git add -p` the `src/`, `tests/`, `configs/`, and doc files deliberately.
- [ ] **Step 4 — Commit** with a message that names the four fixes and cites `PROGRESS.md`/`DECISIONS.md`
  2026-07-05…10. **Do NOT add the `Co-Authored-By` trailer only if this repo forbids it** — this repo has
  no such rule (that rule is `continual_alignment`-specific), so include the standard Claude trailer.
- [ ] **Step 5 — Tag it:** `git tag pre-audit-2026-07-10`. This is the rollback point and the diff base for
  every subsequent audit fix.
- [ ] **Step 6 — Ledger:** create `results/audit/AUDIT_FINDINGS.md` with a table header
  (`check | tier | verdict | evidence | affected results | fix commit`) and record A0 as the first row.

---

## Task A1 — Verifier decision layer: is a "solve" always a real solve, and vice-versa?

**Files:** `src/atp/lean/verifier.py` (the `ok`/`reason` decision, `_DECL_RE:34`, `no_goal:104`),
`src/atp/lean/errors.py` (`find_loopholes`, `parse_lean_output`, `uses_sorry_warning`),
`src/atp/lean/repl.py:_format_response:356` (the `env`-required spurious-success gate, `REPL_INFRA_ERROR`).
Test: extend `tests/test_lean_verifier.py`, `tests/test_lean_repl.py`.

**What to establish:** the 2026-06-14 audit (commit `aa659f5`) closed two false-positive holes (bare-`def`
no-goal; empty-response spurious success). Confirm they are still closed on the *current* code AND look for
their duals (false negatives) and any third hole.

- [ ] **Step 1 — Known-BAD control (the missing half of the harness-sanity control).** Write
  `scripts/audit_known_bad_reverify.py`: assemble a battery of proofs that MUST be rejected — `sorry`,
  `admit`, `native_decide` (if in `reject_loopholes`), a bare `def`/`#eval` preamble with no theorem, an
  incomplete `by` with unsolved goals, and an empty string — and assert `Verifier.verify` returns `ok=False`
  with the expected `reason` for each, through the real `ReplBackend`. Prior audits only ever confirmed
  *good* proofs verify; this confirms *bad* ones don't. Pre-register: any bad input scored `ok=True` is a
  P0 soundness bug.
- [ ] **Step 2 — Re-verify a real sample of RECORDED verdicts end-to-end.** For ~200 historical attempts
  sampled across Phase 1/2/4 baseline runs (mix of `ok=True` and `ok=False`, both models, both benchmarks),
  re-run `Verifier.verify(theorem, attempt.proof)` on today's `ReplBackend` and compare the fresh `reason`
  to the recorded one. Solved→still-ok is the 37/37-style control; **failed→now-ok is the finding that
  matters** (feeds Task B). Write results to `results/audit/reverify/verdict_reproduction.json`.
- [ ] **Step 3 — `no_goal` gate operand check.** `verifier.py:104` runs `_DECL_RE.search(proof)` on the
  *extracted proof string*, while the backend assembles a *different* source (reconstructing the theorem
  header for continuation templates). Confirm that for the headline `whole_proof` models the operand is the
  full declaration (so the gate is correct), and document the continuation-template case explicitly. Add a
  test pinning both.
- [ ] **Step 4 — `_DECL_RE` duplication drift.** The pattern is defined twice (`verifier.py:34`,
  `backends.py:28`) by design, with a comment to keep them identical. Assert equality in a test so a future
  edit to one can't silently diverge.
- [ ] **Step 5 — Verdict & ledger:** CLEAN only if Steps 1–2 show zero false accepts and full verdict
  reproduction; otherwise open a BUG row with the failing real-data test.

---

## Task A2 — Source assembly parity: does the production backend build the file it should?

**Files:** `src/atp/lean/repl.py:_build_repl_source:319` (production), `src/atp/lean/backends.py:_build_source:216`
(Pantograph, non-production). Test: `tests/test_lean_repl.py`.

**What to establish:** the assembler decides what Lean actually compiles for every cell. Confirm the
production `ReplBackend` (a) reconstructs the theorem header for bare-tactic completions, (b) strips model
`import` lines, (c) preserves/injects `open`, (d) injects `set_option maxHeartbeats 0` exactly once, for
**all three** proof shapes — complete-file, self-declaring, and bare-tactic.

- [ ] **Step 1 — Three-shape table test** against real recorded completions (one whole_proof solve, one
  continuation-template completion, one that self-declares). Assert the assembled source compiles and that
  `maxHeartbeats` appears exactly once in each.
- [ ] **Step 2 — Backend disagreement.** `PantographBackend._build_source` returns complete-file proofs
  *without* `maxHeartbeats` (backends.py:233-234), while `ReplBackend` injects it unconditionally
  (repl.py:352). Determine whether any historical run used `PantographBackend`; if none did (expected —
  `run.py` wires `ReplBackend`), record that Pantograph is test/plumbing-only and note the divergence as
  benign but fix it for consistency + add a parity test. If any run used Pantograph, escalate.
- [ ] **Step 3 — Ledger** with the parity evidence.

---

## Task B — Does `maxHeartbeats 0` retroactively change Phase 0–7 results? (HIGHEST-VALUE)

**Premise (cheapest falsification first, `feedback_validate_premise_before_building`):** if the headline
`whole_proof` provers never needed >200000 heartbeats, this is a no-op and the floor is robust; if even a
few trapped-core failures flip to solved under `maxHeartbeats 0`, the Phase 0–7 curves and the
execution-floor thesis need revision. Resolve it directly instead of arguing from the taint audit.

**Files:** new `scripts/audit_heartbeat_reverify.py` (reuse `ReplBackend` + `Verifier`); read
`results/**/agent_states/*.json`. Deliverable: `results/audit/HEARTBEAT_AUDIT.md`.

- [ ] **Step 1 — Pre-register in DECISIONS.md:** predicted result (likely no-op) + decision rule: re-verify
  every recorded **failed** attempt on the **trapped cores** (`scratch/phase2/trapped_*.txt`, both models,
  both benchmarks) under today's `ReplBackend` (which now injects `maxHeartbeats 0`). Material iff ≥1 trapped
  problem flips to a verified solve per seed on ≥1 model. Report the count and the specific problems.
- [ ] **Step 2 — Confirm the counterfactual is real:** verify (git-diff the uncommitted change; check run
  manifests' timestamps vs the maxHeartbeats add date 2026-07-06) that the historical sweeps ran *without*
  the option. If a `run_manifest.json` or served source shows they already had it, the whole task is moot —
  record and stop.
- [ ] **Step 3 — Offline re-verify.** For each trapped (problem, seed), take its recorded failed attempt
  proofs and re-run `Verifier.verify` under the patched backend. This is pure CPU Lean round-trip (no GPU,
  no generation) — the same offline-reverify pattern Phase 8 used (`scripts/phase8_reverify.py`). Count flips.
- [ ] **Step 4 — Broaden if Step 3 flips anything:** if trapped cores flip, extend to a sample of *all*
  recorded failures near the budget frontier (not just trapped), because a heartbeat effect there would
  shift the mid-curve pass@B, not just the floor.
- [ ] **Step 5 — Verdict:** CLEAN/no-op → one paragraph certifying the floor is not a heartbeat artifact
  (a genuine strengthening of the thesis, quotable in WS2). Material → list affected cells, hand off a
  GPU re-run of those cells to the user (fresh generation under the corrected harness, ≥3 seeds), and flag
  SYNTHESIS.md for revision. Ledger + `HEARTBEAT_AUDIT.md`.

---

## Task C — Budget accounting & the pass@B / `tokens_to_solve` invariant

**Files:** `src/atp/budget/meter.py`, `src/atp/eval/records.py` (`tokens_to_solve`, `solved_within:70`),
`src/atp/eval/metrics.py` (`pass_at_b:39`), `src/atp/agents/whole_proof.py` (halt-on-solve `_step:254`).
Test: `tests/test_budget.py`, `tests/test_eval.py`.

**What to establish:** the entire pass@B curve for every B<max is derived from the single recorded
`tokens_to_solve` per cell, and Phase 4 rests on the identity `solved(cell,b) == tokens_to_solve ≤ b`. A
bug here distorts every curve and the one positive result.

- [ ] **Step 1 — Halt-on-solve ⇒ `tokens_to_solve` is cumulative-at-solve.** Confirm the agent finishes
  immediately on a verified proof (it does: `whole_proof.py:254-257`) so `spent` at record time excludes any
  post-solve tokens. Add/verify a test that a solve on attempt *k* records `tokens_to_solve` = sum of the
  first *k* completions, not the full budget.
- [ ] **Step 2 — Overshoot edge.** `BudgetMeter.spend` can push `spent` slightly past `limit` when the
  server returns more than `request()` allowed (`meter.py:105`). Confirm this cannot (a) mis-attribute a
  solve to a budget bucket it shouldn't reach, or (b) make `solved_within(max_b)` ever False for a real
  solve. Pin with a test.
- [ ] **Step 3 — pass@B denominator homogeneity.** `pass_at_b` computes each seed's fraction over *that
  seed's own* completed-cell count (`metrics.py:46`) and takes `n_problems = max` across seeds
  (`metrics.py:42`). For a *fully-covered* run all denominators are equal and this is correct; for a
  partially-covered run it silently averages fractions with different denominators. **Audit every headline
  run** (`results/{baseline,minif2f,proofnet_sharp,phase1,phase1_proofnet,phase4/*}`) for full coverage:
  assert `len(cells) == n_problems × n_seeds` and every seed has every problem. Write the coverage table to
  `results/audit/COVERAGE.md`. Any headline number computed on ragged coverage is re-computed on the common
  subset and compared.
- [ ] **Step 4 — Seed-std convention.** `metrics._std` uses sample std (`statistics.stdev`, n−1). Confirm
  every reported "± std" in the result docs is sample std over seeds (not population, not SEM), and that the
  noise bar was applied consistently. Ledger.

---

## Task D — `from_config` wiring-bug-class sweep (the Phase 8 root cause, generalized)

**Files:** all eight `from_config` sites — `meter.py:131`, `whole_proof.py:61`, `verifier.py:84`,
`client.py:186`, and the four component configs (`diversity/skeletons/memory/retrieval/reviewer`).

**What to establish:** the Phase 8 wiring bug was a config field (`prompt_template`) silently ignored
because a `from_config` hardcoded a value. Prove no *other* config field meets the same fate — especially
fields that were toggled across Phase 1 ablations.

- [ ] **Step 1 — Field-flow test per site.** For each `from_config`, enumerate the config fields it *should*
  consume and assert each actually reaches the constructed object (e.g. `client.from_config` must propagate
  `temperature`, `top_p`, `chat_completions`; `verifier.from_config` must propagate `reject_loopholes`,
  `verify_timeout_s`). A field read nowhere = a candidate wiring bug. `whole_proof.from_config` already has
  `test_from_config_resolves_the_configured_prompt_template` — replicate that discipline everywhere.
- [ ] **Step 2 — The `stop` gap, quantified.** No config field sets a generation `stop` sequence
  (`config.py` has only `stop_on_first_success`; `client.generate` defaults `stop=()`), so provers generate
  to EOS/`max_tokens`. Confirm the *headline* models emit a natural EOS after their proof (so
  `completion_tokens` isn't inflated by post-proof rambling, which would inflate `tokens_to_solve` and
  understate low-B pass@B). Measure `finish_reason` distribution and post-fence token counts on a sample of
  Phase 1/2 headline attempts; if inflation is negligible, record CLEAN + note the debt; if not, escalate.
- [ ] **Step 3 — Ledger** with the field-flow matrix.

---

## Task E — Data & config fidelity

**Files:** `src/atp/data/{problems.py,minif2f.py,proofnet.py,contamination.py,exclusions.py}`,
`src/atp/data/manifest.py`, `src/atp/eval/manifest.py`. Test: `tests/test_data.py`.

- [ ] **Step 1 — Statement-set integrity.** Confirm the loaders produce exactly the canonical 244 miniF2F /
  186 ProofNet# with 0 disjoint names across the two Lean pins (H1 claim), and that every statement passes
  the CPU compile-gate (`scripts/validate_statements.py`) — the astral-char class of silent all-zeros
  (`reference_lean_repl_cluster` gotcha 6). Re-run the gate; record counts.
- [ ] **Step 2 — `informal_statement` threading.** The 2026-07-06 fix restored `informal_statement` through
  `Problem.to_theorem()` (backends.py:49). Confirm no headline (`whole_proof`) run depended on it being
  absent or present in a way that changes the served prompt for Goedel-V2/DeepSeek-V2 (their templates don't
  render it), so this is Phase-8-only. Pin with a test.
- [ ] **Step 3 — Contamination/novelty split.** Re-run the mechanical leak checks
  (`scripts/phase8_contamination.py`): miniF2F valid/test name overlap = 0; document that
  `novel_names`/held-out handling in `run_eval` (run.py:114) selects the intended split for each headline
  run. Note the residual unaudited-contamination caveat honestly (it's a known open item, not a bug).
- [ ] **Step 4 — Manifest completeness.** Spot-check `run_manifest.json` across phases records git SHA,
  config hash, seed, model revision, mathlib commit, Lean version. A missing field is a reproducibility gap
  to log, not necessarily a result bug.

---

## Task F — Analysis & statistics scripts (raw cells → reported numbers)

**Files:** `src/atp/alloc/*` (Phase 4), `scripts/analyze_mechanism.py` + `phase4_*.py` + `phase5_*.py` +
`phase6_seed_aggregate.py` + `phase8_floor_table.py`. Tests: `tests/test_alloc.py`, `test_reinvest.py`,
`test_analyze_mechanism.py`, `test_phase8_floor_table.py`.

- [ ] **Step 1 — Re-derive the Phase 4 identity from raw cells.** Independently recompute
  `solved(cell,b) == tokens_to_solve(cell) ≤ b` straight off `results/phase4/**/problems/*.json` and confirm
  the allocation code's "realized == simulated" claim holds cell-by-cell (the enabling trick, ALLOCATION.md).
  Then recompute the headline +26%±7% (Goedel×ProofNet#) and the −13%±28% (DeepSeek) from scratch with an
  independent script; they must match the committed numbers within rounding. This double-checks THE positive
  result before WS1 builds on it.
- [ ] **Step 2 — Paired-flip recount.** Re-count the Phase 1 ProofNet# flip table (retrieval −36, budget_alloc
  −19, etc.) independently from the per-cell records; confirm gains/losses are counted per (problem, seed) and
  match FINDINGS.md.
- [ ] **Step 3 — OOF-leakage check on the allocation predictor.** Confirm the logistic predictor's
  out-of-fold construction (`alloc/predict.py`) truly holds out the evaluated cell (no train/test leakage
  inflating the AUC). This is the one place a subtle leak would flatter the positive result.
- [ ] **Step 4 — Ledger** with the independently-recomputed headline numbers side-by-side with the reported
  ones.

---

## Task G — Test-suite quality audit (why the fast suite missed 4 bugs)

**Files:** `tests/**`. **What to establish (Lesson 8):** the four Phase 8 bugs passed the suite for weeks
because tests locked in buggy behavior or used synthetic data that dodged the bug. Find remaining tests of
this kind before they hide the next bug.

- [ ] **Step 1 — Real-data coverage gaps.** List result-critical invariants (verifier soundness, source
  assembly, budget/`tokens_to_solve`, pass@B denominator, each `from_config` field-flow) and mark which have
  a test that runs against a REAL recorded cell vs only synthetic mocks. Every gap gets a real-data test
  added (folds into the relevant task above).
- [ ] **Step 2 — Behavior-locking tests.** Grep for tests that assert the *old* shape of any code the Phase
  8 fixes changed (templates, assembly). Confirm each now asserts the corrected behavior, not the buggy one.
- [ ] **Step 3 — Ledger:** record the before/after real-data-coverage count.

---

## Exit criteria & handoff

- [ ] `results/audit/AUDIT_FINDINGS.md` complete: every task CLEAN / BUG(fixed) / AMBIGUOUS(handed off),
  each with evidence.
- [ ] Tasks **A0, A1, A2, B** are terminal (CLEAN or fixed-and-re-verified). These gate `PLAN_NEXT.md` WS1 —
  WS1 reuses this exact harness, so its numbers are only trustworthy once these clear.
- [ ] Any BUG that moved a *reported* number → affected cells re-run (GPU handoff), `SYNTHESIS.md` +
  the relevant `results/phase*/` doc corrected, fix committed with a test.
- [ ] A one-paragraph audit summary appended to `SYNTHESIS.md` ("Independent audit, 2026-07-10: …") stating
  which findings are now re-verified vs argued — this paragraph is itself a WS2 reviewer-defense asset
  ("we independently re-verified our own pipeline end-to-end").
- [ ] Final `git commit` of all fixes + tests; `PROGRESS.md`/`DECISIONS.md` updated.

**Recommended order:** A0 → A1 → A2 → B (the four gating tasks) → C, D, E, F, G in parallel-friendly order
(all CPU, independent). B is the one most likely to change a headline; do it early so any GPU re-run it
triggers overlaps WS1's queue time.
