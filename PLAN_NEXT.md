# PLAN_NEXT.md — Post-Phase-8 Execution Plan

> **For agentic workers (Sonnet implementer):** Use `superpowers:executing-plans`. **WS0 (the audit,
> `AUDIT_PLAN.md`) runs first and gates WS1.** Everything in §0–§WS5 below is the user's plan verbatim;
> the **Operational Addendum** immediately below is Claude's grounding of it against the actual codebase
> (2026-07-10), read it first.

---

## Operational Addendum (Claude, 2026-07-10) — read before §0

**WS0 — CODEBASE & RESULTS AUDIT (new, gating). See `AUDIT_PLAN.md`.** The user asked, before executing
this plan, for a deep audit to be certain of the findings. It is now the critical-path prerequisite,
because **WS1 reuses the exact eval harness the audit certifies.** Do not submit any WS1 GPU sweep until
audit Tasks A0, A1, A2, B are terminal. Two audit findings already surfaced during planning that this plan
depends on:

1. **The Phase 7 + Phase 8 source fixes are UNCOMMITTED** (`git status`: `repl.py`, `backends.py`,
   `whole_proof.py`, `templates.py` modified; last commit `aec81a2` = "Phase 6"). **AUDIT_PLAN Task A0
   commits + tags `pre-audit-2026-07-10` first.** Until then, treat the working tree as fragile: no
   `git checkout`/`stash`/`reset` without a stash-with-`-u` backup first.
2. **`set_option maxHeartbeats 0` entered the verifier only on 2026-07-06 (Phase 8).** Every Phase 0–7
   headline number predates it. AUDIT_PLAN Task B resolves whether that retroactively understated the
   pass@B curves / softened the "execution floor." **WS1 and the WS2 floor paper both assume the floor is
   real — if Task B flips trapped-core problems, WS1's baseline and WS2's central claim change.** So Task B
   is a genuine gate on this whole plan, not just hygiene.

**UPDATE 2026-07-16 — WS0/Task B CLOSED, plan UNBLOCKED with a small known correction.** Full trapped-core
offline reverify completed across all 4 (model × benchmark) cores (`results/audit/AUDIT_FINDINGS.md` row B;
exit summary in `SYNTHESIS.md` "Independent audit, 2026-07-10/16"). Task B **DID** flip trapped-core
problems — 13/1212 re-verified cells (1.1%), 8 distinct (problem, model) pairs out of 406 (2.0%),
on 2 of 2 models — so per the pre-registered gate above this is not a clean no-op. **The floor is real but
was modestly inflated**: every flipped cell's proof was already present in the ORIGINAL Phase 0-7
generation (a scoring/verification-timeout artifact, not a new capability), and the fix only ever widens
what counts as solved, so no reported number was previously an over-count — this is a small upward
correction to the reported floor %, not a reversal of the thesis. WS1 and the WS2 floor paper's central
claim **survive at this magnitude**, but should carry a one-line footnote/erratum citing the corrected
counts once the affected curves are re-flowed (arithmetic-only, not a new experiment — not done yet). All
other audit-gating tasks (A0, A1, A2) are also terminal (A1's `no_goal` fix is Phase-8-only, confirmed
not to touch `whole_proof`/Goedel-V2/DeepSeek-V2). **WS1 GPU sweeps may now proceed.**

**Grounding notes keyed to the user's workstreams (exact reuse targets, verified to exist):**

- **WS1.1 (power-up):** the eval entrypoint is `src/atp/eval/run.py::run_eval` driven by `atp sweep` (see
  `src/atp/cli.py`) + `slurm/sweep_array.sh` (sharded; per-shard vLLM port + `/dev/shm` Lean staging +
  `--exclude=ins082,ins087` already wired). Existing Phase 4 configs/logs live in `results/phase4/`. New
  seeds = new `(config, seed, problem)` cells; resume/skip is automatic in `run_sweep`. Budget estimate:
  read realized GPU-h from `results/phase4/**/run_manifest.json` timestamps, not a guess.
- **WS1.2 (mechanism, CPU):** model on `scripts/analyze_mechanism.py` (Phase 2) and the allocation code in
  `src/atp/alloc/` (`extract.py`, `features.py`, `predict.py`, `frontier.py`). Per-problem
  budget-elasticity comes straight off `results/**/problems/*.json`'s `tokens_to_solve` — no GPU. Deliver
  `results/phase4/ALLOCATION_MECHANISM.md` + `scripts/analyze_allocation.py`.
- **WS1.3 (online policy backtest):** the OOF logistic predictor already exists (`src/atp/alloc/predict.py`,
  features observable at a checkpoint c*); the backtest reuses `alloc/frontier.py` + `policies.py` against
  logged traces (no GPU). Pre-register the "fraction-of-oracle-gain captured" metric in `DECISIONS.md`.
- **WS2 (floor paper):** every figure is generable from `results/**/metrics.json` + `scripts/analyze_*.py`.
  The verifier-audit defense (WS2.2 "your harness is broken") is now **stronger** — cite the independent
  audit (WS0) + commit `aa659f5` + the 37/37, 40/40 controls + AUDIT_PLAN Task A1's new known-BAD control.
- **WS4 (drift):** Stage A/B closing-target data is on disk at `scratch/phase6/sft/*/closing_targets.jsonl`
  ({name, deep_state, closing, proof, depth}) — the raw material for per-token drift analysis, CPU-only.
- **Lab-convention enforcement is partly automatable:** the noise bar, ≥3-seed rule, and paired-flip
  counting all have existing implementations in `src/atp/eval/metrics.py` + the `phase*` scripts — reuse
  them, don't reimplement.

**Autonomy calibration for this plan (`feedback_atp_autonomy`):** drive WS0→WS1→(WS2 in parallel)
autonomously; log to PROGRESS/DECISIONS and proceed. Stop and hand off / ask only at: any GPU submission
(user submits — §0.3); the Gate G1 one-paper-vs-two-paper call (§WS1 Gate G1); any change to a
pre-registered prediction; final paper framing/venue; a Task-B "material" outcome (it forces a re-run and a
SYNTHESIS revision). The GPU-h soft-limit rule (`feedback_gpuh_limit_flexible`) applies — don't cap a run
purely to stay under 50 GPU-h if the spend buys the finding, but still surface the estimate in the handoff.

**UPDATE 2026-07-16 (later) — WS2 (paper) PAUSED, not "in parallel."** The user does not want any more
paper-writing time spent until the experiment workstreams are done: "i dont want to do this until we are
doing writing code completely... i just want to focus on experiments not writing the paper." A first-pass
skeleton (`paper/floor/main.tex`) already exists and compiles — leave it as-is, do not extend it (no more
figures, no citation pass, no further sections) until told otherwise. Effective immediately, "drive
WS0→WS1→(WS2 in parallel)" above is superseded: **drive WS1 (and any other experiment workstream) only;
WS2 is off until the user reopens it.**

---

*[Below: the user's plan as authored, 2026-07-10, verbatim.]*

## 0. Ground rules (read before doing anything)

1. **Read first, in this order:** `PROGRESS.md` (most recent entries), `DECISIONS.md`,
   `results/phase4/ALLOCATION.md`, `SYNTHESIS.md`. Do not re-derive conclusions those documents
   already settle; do not contradict a DECISIONS entry without flagging it to the user.
2. **Lab conventions are binding:**
   - 3 seeds minimum for any headline number; report mean ± seed-std. (WS1 raises this — see below.)
   - The noise bar: a mean-delta under ~1 baseline-σ is noise (DECISIONS 2026-06-11).
   - Paired flips, not mean-deltas, for variant-vs-baseline comparisons.
   - Pre-register predictions in `DECISIONS.md` *before* running any experiment whose outcome will
     be reported. Include the decision rule (what result triggers what action).
   - Any new experimental cell gets a **harness-sanity control** before its results are trusted —
     re-verify a set of historically-solved proofs under the exact config (Lesson 7, Phase 8).
   - Every work session appends a dated entry to `PROGRESS.md`.
3. **Division of labor:** Claude Code writes code, analysis scripts, configs, SLURM scripts, docs,
   and paper drafts, and runs anything CPU-only locally. **GPU jobs are submitted by the user** —
   prepare the sbatch files and a one-line submit command, then stop and hand off. Follow the
   sharded-sweep infra conventions in `slurm/sweep_array.sh` and PROGRESS.md 2026-06-16/18
   (per-shard `/dev/shm` Lean staging, per-shard vLLM ports, staggered starts, exclude
   ins082/ins087, resume full array ranges only).
4. **Things that need explicit user sign-off before proceeding:** any change to a pre-registered
   prediction; the WS3 go/no-go call at Gate G1; final paper framing and venue choice; anything
   that would consume >1 week of cluster time.

---

## WS1 — Phase 4 validation & mechanism (CRITICAL PATH)

**Question:** Is compute-optimal budget allocation a general property of budget-bounded proving, or
a Goedel-specific artifact? Current state: Goedel × ProofNet# **+26% ± 7%** (strong, per-seed
robust); DeepSeek × ProofNet# **−13% ± 28%** (weak, enormous variance). Note the DeepSeek number is
*noise-dominated, not a confirmed negative* — σ=28% means we cannot distinguish "hurts," "null,"
and "helps moderately." The first job is to buy statistical power, the second is mechanism.

Scope note: "replicate across the zoo" is off the table — Phase 8 lineages score 0.0% and have no
solve signal to allocate over. The feasible replication targets are DeepSeek-Prover-V2 (power-up)
and the two benchmarks × two models we already have curves for.

### WS1.1 — Power-up the DeepSeek cell
- Extend DeepSeek-Prover-V2 × ProofNet# allocation runs from 3 → **8 seeds** (5 new). Also add
  the two cells never run: Goedel × miniF2F and DeepSeek × miniF2F allocation (3 seeds each), so
  the paper can show the full 2×2.
- Pre-register in DECISIONS.md before launch: (a) predicted sign per cell, (b) the decision rule —
  if the 8-seed DeepSeek mean is within 1σ of zero, the claim in all write-ups becomes
  "one-model-robust, model-dependent," full stop; if positive and >1σ, claim generality; if
  negative and >1σ, the Goedel/DeepSeek divergence becomes the headline mechanism question.
- Prepare configs + sbatch, hand off for submission. Budget estimate: comparable to one Phase 4
  arm × (5 seeds + 6 new-cell runs); confirm against `results/phase4/` logs and state the estimate
  in the handoff note.

### WS1.2 — Mechanism: why does allocation work (when it works)?
CPU-only trace mining, can start immediately without GPUs, on existing Phase 4 run artifacts:
- Reconstruct, per seed, which problems the allocator moved budget *to* and *from*, and where the
  net solves came from. Hypothesis to test: the gain comes from harvesting "cheap marginal"
  problems (solved at low B on some seeds) — i.e., allocation exploits the pass@B curve's local
  slope heterogeneity across problems.
- Compute per-problem budget-elasticity from the existing pass@B attempt traces (both models, both
  benchmarks). Directly test whether Goedel-ProofNet# has more slope heterogeneity than
  DeepSeek-ProofNet# — if yes, that's a clean mechanistic account of the model-dependence and the
  core figure of the allocation story.
- Deliverable: `results/phase4/ALLOCATION_MECHANISM.md` + figures
  (`scripts/analyze_allocation.py`, follow the style of `scripts/analyze_mechanism.py`).

### WS1.3 — From oracle to policy (only if WS1.2 finds usable structure)
- If per-problem elasticity is predictable from cheap observable signals (early-attempt failure
  taxonomy class, deepest-step-reached at low B, first-attempt compile distance), implement and
  backtest an **online** allocation policy against the existing traces (no new GPU time needed for
  the backtest). A deployable online policy is what upgrades Phase 4 from "an observation" to "a
  method," and is the strongest version of the WS3 paper.
- Pre-register the backtest metric: fraction of oracle-allocation gain captured, at matched total
  budget, vs flat baseline.

### Gate G1 (end of WS1)
Report to the user with a recommendation:
- **Two-paper world** (allocation generalizes or an online policy captures ≥~50% of oracle gain):
  WS3 becomes a standalone main-track paper; WS2 cites it and stays the mechanism/null paper.
- **One-paper world** (allocation stays one-model-robust): fold Phase 4 into WS2 as the
  constructive section, honestly scoped.
The user makes this call; prepare the evidence, don't make it unilaterally.

---

## WS2 — The floor paper (negative-result / analysis paper)

Can proceed in parallel with WS1 from day one; it needs no new GPU results.

### WS2.1 — Skeleton and framing
Draft in `paper/floor/` (LaTeX, standard NeurIPS/ICLR style files; keep a TMLR-formatted branch
ready since that's the fallback venue). Working thesis, one sentence: *inference-time interventions
cannot move the execution floor of whole-proof provers — the floor is a property of within-approach
execution depth set by training, and at fixed compute only allocation policy moves outcomes.*

Structure the paper around the **causal chain**, not the chronology:
1. pass@B curves + the in-distribution-saturates / OOD-stays-hungry asymmetry (2 models).
2. Scaffolding null (Phase 1, paired flips; lead with the ProofNet# flip table — two components
   *hurt*, which is the memorable result).
3. Mechanism F1–F4 (diversity collapse, reasoning_deep failure taxonomy killing the retrieval
   hypothesis, capability floor, no easy subfield).
4. **F6/Step C as the centerpiece**: pre-registered interventional test, manipulation check passed
   (+42–70% diversity), outcome null, quality degradation caught by verifier. This is the section
   reviewers will judge the paper on.
5. The exhaustion sweep as corroboration, compressed: hammers (P3), more-budget (P5), SFT (P6A/B
   incl. the exposure-bias signature), LoRA RL (P6C), re-grounding (P7), full-pipeline RL zoo (P8).
6. Phase 4 as the constructive counterpoint (scoped per Gate G1).
7. Methodology section: verifier audit, paired flips, harness-sanity controls, symmetric skepticism
   of nulls. Draw on SYNTHESIS.md "lessons" 1–8 — Lesson 7 deserves a named subsection; it is the
   paper's most transferable idea.

### WS2.2 — Anticipate the reviewer kill-shots (write these defenses in from the start)
- "Your harness is broken" → the Phase 8 bug-hunt + 37/37, 40/40 harness-sanity controls + the
  verifier audit (commit `aa659f5`) go in the main text, not the appendix.
- "Only two models" → four lineages including two matched Base/SFT/RL lineages; be precise that the
  zoo tests *training-stage* effects, not more datapoints on the curves.
- "Scaffolding was implemented weakly" → the manipulation check is the answer: the intervention
  demonstrably fired and still didn't move solves. Say this explicitly.
- "miniF2F is saturated/contaminated" → that's *why* ProofNet# carries the OOD claims; the
  dichotomy is a finding, not a bug.
- "Negative results aren't contributions" → position against the test-time-compute and agentic-
  scaffolding literature explicitly: the field is actively shipping the components we show are null
  or harmful. Cite the self-correction-negative-result lineage as precedent.

### WS2.3 — Figures and repro package
- Figure list (generate from existing data, `scripts/` + `results/*/metrics.json`): (F1) pass@B
  2×2 grid; (F2) ProofNet# flip table as a figure; (F3) failure-taxonomy stacked bars; (F4) Step C
  before/after diversity + solve panel; (F5) allocation result; (F6) the Phase 8 corrected-vs-
  artifact contrast (a strong honesty signal).
- Build `repro/`: pinned model revisions, Lean/mathlib pins, canonical statement sets, verifier
  commit, one-command re-scoring of released attempt traces. Anonymize for submission.

---

## WS3 — The allocation paper (contingent on Gate G1)

Do not start drafting before G1. If greenlit: title-level claim is the policy result (WS1.3), the
mechanism figure is elasticity heterogeneity (WS1.2), the floor paper is the citation for "why not
scaffolding instead." Target: main-track ICLR/NeurIPS as a test-time-compute paper. If G1 lands in
the one-paper world, this workstream is deleted, not deferred.

## WS4 — Exposure-bias characterization (background, CPU-first, opportunistic)

The Stage B signature (near-zero teacher-forced loss on verified closings; autoregressive failure
to reach them) is the project's most interesting open question and is analysis-shaped, not
training-shaped. Low-priority background work:
- From existing traces: for trapped problems with a known verified closing (Stage A data), measure
  per-token divergence between the model's free-running path and the closeable path — where does
  drift start, and is it early-committal (first ~20% of proof) or late?
- Deliverable: `results/phase9/DRIFT.md`. If a crisp drift signature emerges, it's a follow-up
  paper seed; if not, one paragraph in WS2's discussion. Pre-register that decision rule too.

## WS5 — Workshop pressure-test

Once WS2.1 has a full draft: cut a 4–8 page version for the next AITP / MathAI-adjacent workshop
deadline (check current CFPs — do a web search; do not trust remembered deadlines). Purpose is
framing calibration before the archival submission, not a publication target in itself.

---

## Sequencing summary

- **Immediately, no GPUs needed:** WS1.2 (allocation trace mining), WS2.1/2.2/2.3 (paper draft,
  figures, repro), WS1.1 config prep.
- **First user handoff:** WS1.1 sbatch submission (after pre-registration is committed).
- **Gate G1** when WS1.1 + WS1.2 land → user decides one-paper vs two-paper world.
- **Then:** WS3 (if greenlit) and WS5; WS4 fills idle cycles throughout.

## Standing anti-footgun checklist (apply to every new run in this plan)
- Pre-registered prediction + decision rule committed to DECISIONS.md before launch.
- Harness-sanity control passes under the exact new config before results are read.
- Base-rate check on any surprising number — high, low, or suspiciously clean (Lesson 7).
- New config = new code path: write the failing test against real data first (Lesson 8).
- PROGRESS.md dated entry per session; SYNTHESIS.md updated only at workstream close, not per-run.

---

## WS6 — Post-draft strengthening sprint (2026-07-25, user-directed, stopping rule set)

Triggered by the user's review of the WS2 draft: six candidate additions, ranked by "changes what the
paper can claim" not "tidies it." **Stopping rule (explicit, per the user's own caution about
open-ended audit sprints): items 1, 2-free, and 6-arithmetic are written up and closed by
2026-08-08 (two weeks) regardless of outcome — surprises get one follow-up round, not an open-ended
chase.** Item 3 (decomposition) gets a go/no-go decision once item 2-free lands, not before. Items 4
and 5 are opportunistic, not gated to the two-week window.

### Priority order (this session starts on 1, 2-free, 6-arithmetic in parallel)

1. **Equivalence-testing reframe for every reported null (free, CPU).** Replace "within noise" with a
   paired-per-problem-bootstrap upper confidence bound on the true effect, for: all 7 Phase 1
   scaffolding components (both benchmarks), Stage B (SFT exposure-bias), Step C (diversity
   injection), and the Phase 4 realizable-vs-uniform comparisons already redone in WS2's last pass.
   Generalizes `scripts/phase4_bootstrap_ci.py`'s clustered-by-problem bootstrap pattern to arbitrary
   paired before/after flip data. Deliverable: a bound per intervention ("retrieval's true effect is
   below +Xpp at 95% confidence") plus a flag on any intervention whose CI is unexpectedly loose (a
   power problem worth knowing before a reviewer finds it). Script:
   `scripts/equivalence_bounds.py` (new). Folds into `paper/floor/main.tex` Section 4
   (scaffolding) and the mechanism/exhaustion sections as a table, replacing "noise bar" language.

2. **Contamination-boundary test — free half only (CPU).** Test whether solve rate correlates with
   miniF2F↔Lean-Workbook overlap score, using the already-built Phase 6 §0 disjointness machinery
   (`scripts/phase6_disjointness.py`, `results/phase6/DISJOINTNESS.md`) extended from the trapped-core
   subset to the FULL 244/186-problem eval sets. Decision rule pre-registered below. **The paid half
   (MiniF2F-ALF-style mutation probes or a miniF2F-v2 re-run) is explicitly NOT authorized yet** — only
   greenlit if the free correlation check shows signal (see decision rule).
   - **Pre-registered decision rule**: compute overlap score (exact/near-exact match against the
     Lean-Workbook corpus, reusing the existing §0 matcher) for every miniF2F problem; correlate
     against per-problem solve rate (pooled over seeds, both models) and against trapped/not-trapped
     status specifically. **Null (no reframe needed)**: overlap score is not a significant predictor of
     trapped status (e.g. trapped problems are not disproportionately non-overlapping) — one paragraph
     in limitations, already partially covered by the existing "10 exact overlaps" note.
     **Signal (reframe + escalate)**: trapped problems are significantly less likely to be
     high-overlap than solved problems (the "floor = recall boundary" reading) — triggers a go/no-go
     conversation on the paid mutation-probe option before spending anything further.
   - Deliverable: `results/phase6/CONTAMINATION_CORRELATION.md`.

3. **Decomposition arm (GPU, gated on item 2's outcome, not started this session).** Pre-registration
   drafted below so it's ready to launch on a go decision, not written from scratch under time
   pressure. **Scope**: Goedel×miniF2F trapped core (55 problems) only, not the full battery.
   **[CORRECTED 2026-07-25 — the original draft of this item said "Goedel×ProofNet#" while citing
   the 55-count and the 6/55 calibration figure, both of which are miniF2F's, not ProofNet#'s
   (ProofNet#'s trapped core is 150). Fixed to miniF2F throughout, which is also the ONLY benchmark
   with an actual pass@32 calibration result on record to compare against — Goedel×ProofNet#'s
   calibration cell was explicitly declined as NO-GO earlier in the sprint on cost grounds, so there
   is no "what plain resampling already bought" number to beat there. Caught before any GPU spend,
   not after.]** Model-generated subgoal decomposition (prompt the model to state intermediate
   `have` lemmas, then attempt each subgoal independently against the Lean REPL, composing verified
   subgoal proofs into the full proof), token-matched against the existing baseline's per-problem
   budget. **Pre-registered bar** (set now, before running, per the user's explicit ask): material
   iff decomposition solves $\geq$5/55 trapped miniF2F problems (a level clearly above Step C's
   diversity-injection null and the miniF2F pass@32 calibration cell's 6/55, i.e. must beat what
   plain resampling already bought on the SAME population, not just tie it) — anything below 5/55 is
   a null and folds into the existing exhaustion-sweep section, extending
   near-comprehensiveness; $\geq$5/55 is a genuine positive requiring a new results subsection.
   **Not launched this session** — GPU cost + new-agent-mode code path both argue for it going through
   the standard test-first + smoke-before-scale discipline once item 2 resolves whether it's still the
   most informative next spend.

4. **Predictor improvement for Phase 4 (mostly CPU, opportunistic).** Current logistic-on-hand-features
   predictor is 0.72-0.75 AUC, dominated by tokens_so_far. Untried signals available offline in
   existing `agent_states/`: generation logprobs (if retained), verified-prefix depth trajectory,
   error-type sequence (from the F2 taxonomy classifier), per-attempt token cost distribution.
   Success metric pre-registered: if AUC clears 0.85 on the existing OOF CV protocol, recompute
   `scripts/phase4_frontier.py`/`phase4_perseed.py`/the new bootstrap CI on the improved predictor; if
   DeepSeek's CI then clears zero, the model-dependence caveat weakens materially. Below 0.85, report
   the predictor experiment as a negative result in a footnote, not a rewrite.

5. **Artifact release packaging (engineering, no research risk, opportunistic).** Three release
   candidates: (a) the trapped-core problem lists as a benchmark subset with per-problem provenance
   (which of the 8 interventions were tried against it, all null/withdrawn); (b) the verified-failed
   attempt trace corpus (Lean feedback at scale) as potential closing-model training data; (c) the
   harness + regression tests + corrections log as a documented bug-catalog artifact (four structural
   bugs: hardcoded template, missing header reconstruction, missing heartbeat option, and the emergent
   no_goal/header-reconstruction interaction). No pre-registration needed; standard anonymize-for-
   release hygiene applies. Not started this session.

6. **Housekeeping.**
   - **6a — pass@32 reconciliation (free, arithmetic, do now)**: 189 baseline solves + 6 calibration
     recoveries = 195/244 ≈ 79.9% $\approx$ 80% on Goedel×miniF2F pass@32-ish union coverage, between
     the model authors' reported 84.6% and GAR's third-party ~78% reproduction. State with the
     union-vs-single-run caveat (this is a union across the 3 original seeds plus 32 fresh calibration
     samples, not one clean pass@32 run) and close the calibration question on the record.
   - **6b — Phase 7 to 3 seeds (GPU, cheap, this window)**: currently single-seed on ProofNet#-only,
     the project's strongest null (re-grounding). Widen to 3 seeds matching every other headline
     result's protocol.
   - **6c — DeepSeek trapped-core calibration on miniF2F (GPU, cheap, this window)**: 61 problems,
     mirrors the already-run Goedel calibration cell. Closes the "DeepSeek's trapped cores are
     uncalibrated" scope limit for at least one benchmark.

### Anti-footgun note (per the user's own caution)

This plan is explicitly bounded: three items on a two-week clock, one item gated behind a decision
rule rather than run speculatively, two items opportunistic/unscheduled. Draft `paper/floor/main.tex`
in parallel with 1/2-free/6, not after — per the user's own observation, writing surfaces which
claims are load-bearing faster than further analysis does.
