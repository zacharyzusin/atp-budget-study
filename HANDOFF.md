# HANDOFF — read this first

This project is **complete**; no further experiments are planned. This document is the guided tour for
someone picking it up with zero context: what the aim was, what was actually run, what came out, what
you should and should not trust, and what is still open.

**Written 2026-09-02, at project close.** If it ever conflicts with `PROGRESS.md` / `DECISIONS.md`,
those are the primary sources and win — they are the dated, append-only record; this is a digest.

---

## 1. The aim, in one paragraph

A growing literature treats *test-time compute* — more sampling, agentic scaffolding, retrieval,
search over partial proof states — as a reliable lever for getting more out of a fixed theorem-proving
model. We asked a narrow, falsifiable version of that claim: **for a frozen whole-proof Lean prover at
a fixed per-problem token budget `B`, what actually moves the solve rate?** The answer turned out to
be "essentially none of the usual levers," so the project became (a) an account of *why* — a
causally-tested mechanism, not a bare null — and (b) an audit of the measurement apparatus itself,
which turned out to be a contribution in its own right. One constructive result survived: how a fixed
budget is allocated *across different problems* does matter.

**Two provers** (Goedel-Prover-V2-8B, DeepSeek-Prover-V2-7B — independently trained, so any shared
finding is a property of the class, not one model). **Two benchmarks** (miniF2F-test, 244 audited
problems, in-distribution; ProofNet#, 186, out-of-distribution and ~3–5× harder). **≥3 seeds**
everywhere. Lean itself is always the authoritative verifier.

---

## 2. Which documents are live, and which are history

The repo has a lot of markdown. Roles, explicitly:

### Live — current, maintained, trust these
| Doc | What it is |
|---|---|
| `README.md` | Front door: question, headline findings, status, how to run |
| **`HANDOFF.md`** | This file — the guided tour |
| `SYNTHESIS.md` | Consolidated narrative + **the corrections log** (see §5 below — important) |
| `PROJECT_SUMMARY.md` | Per phase: exactly what ran, on what data, with what config, and the exact number |
| `results/*/*.md` | The receipts each summary cites. Tracked in git as of project close. |
| `CLAUDE.md` | Operating rules + cluster cheatsheet |
| `paper/floor/main.tex` | The paper draft (14pp, compiles clean) |

### Primary sources — large, append-only, authoritative on any dispute
| Doc | What it is |
|---|---|
| `PROGRESS.md` (4.3k lines) | Dated lab notebook: every session and experiment, pass/fail, numbers, next step |
| `DECISIONS.md` (2.8k lines) | Dated design-decision log with rationale, plus every pre-registration |

Both are **append-only by policy**. Superseded claims are corrected by *appending* a correction with a
pointer, never by editing the original. If you find two conflicting numbers, the later-dated entry
wins — and the fact that both are visible is deliberate.

### Historical — plans that were executed and superseded. Do not read as current state.
`PROJECT_PLAN.md` (the original spec), `PLAN_NEXT.md` (post-Phase-8 plan, incl. the WS6 sprint),
`PHASE2_PLAN.md`, `PHASE3_PLAN.md`, `AUDIT_PLAN.md`. Each carries a banner at the top saying when it
was written and what superseded it. `CALIBRATION_FINDINGS.md` and `RESEARCH_COMPILATION.md` are
reference documents from specific sprints — still accurate, but scoped to their moment.

---

## 3. Phase index — what was asked, what was run, what came out

Each row's "receipt" is the file with the derivation and raw numbers.

| Phase | Question | What was run | Result | Receipt |
|---|---|---|---|---|
| **0** | What does `pass@B` actually look like? | Whole-proof baseline sweep, 2 models × 2 benchmarks × 3 seeds × [2k,8k,32k,128k] | The headline curves (README §1). miniF2F flattens ~73–75% by 128k; ProofNet# still climbing at 15–22%. Asymmetry replicates on both models. | `results/phase0/*.md` |
| **1** | Does agentic scaffolding help? | OFAT ablation of 6 components (retrieval, memory, reviewer, skeletons, budget alloc ×2), 3 seeds, both benchmarks, + paired-flip analysis | **Null.** Retrieval's apparent +3.4pp did not replicate (+0.7pp on a second run) and paired flips show symmetric churn (+46/−41), not premise injection. On ProofNet# two components are *harmful*: BM25 retrieval −36 net flips, front-loaded allocation −19. | `results/phase1/FINDINGS.md` |
| **2** | *Why* doesn't it help? | CPU trace mining (F1–F4) + **a causal intervention** (F6: force approach diversity on the fully-trapped core, with a budget-matched manipulation check) | **The mechanism.** Diversity rises 42–70% — the manipulation worked — yet solves stay flat and quality mildly degrades. **Approach discovery is not the bottleneck; within-approach execution depth is.** This explains every other null in this table. | `results/phase2/MECHANISM.md` |
| **3** | Do hammer/SMT closing tactics break the floor? | Tactic portfolio on trapped problems | **NO-GO.** Portfolio closes 0/40. | `results/phase3/HAMMER_PROBE.md` |
| **4** | Does *cross-problem* budget allocation matter? | Difficulty predictor + allocation policies + frontier vs. uniform vs. oracle | **The one positive.** ~30% compute saved at 90% of full-budget accuracy (Goedel×ProofNet#). **Caveat: a paired bootstrap CI on that estimate crosses zero**; the second model is weaker and also inconclusive at 8 seeds. | `results/phase4/ALLOCATION.md`, `ALLOCATION_MECHANISM.md` |
| **5** | Does more of the same budget help trapped problems? | Extend trapped cells past 128k | **~0 new solves** (Goedel 1, DeepSeek 0). Fourth independent confirmation of the floor. | `PROGRESS.md` (2026-06-21) |
| **6 A/B** | Does closing-likelihood SFT move it? | SFT on closing steps, two models, eval at 3 seeds/arm | **Null** — and diagnostic: surfaces an *exposure-bias* signature rather than a fix. One combination (Goedel×ProofNet#, the weakest base cell) is measurably *harmed*. | `results/phase6/FINETUNE.md`, `STAGE_A_FORMAT_DIFF.md` |
| **6 C** | Does lightweight post-hoc RL move it? | GRPO probe on DeepSeek, pre-registered triple gate | **Null**, with a *saturated-policy* signature (near-zero KL, flat reward) — a narrower and more honest reading than "capacity ceiling." Corroborated by an independent report on the same base model. | `results/phase6/STAGE_C_RESULT.md` |
| **7** | Does re-grounding on verified proof states help? | Stepwise/tactic-level re-grounding, incl. a matched fresh-resample control, later extended to 3 seeds | **Null in its strongest form.** Mode 3: 5/450 solved cells vs. fresh control 2/450 — Fisher exact p=0.45. The control matters: without it this looks like a weak positive. | `results/phase7/STEPWISE.md` |
| **8** | Does full lab-scale Base→SFT→RL move it? | Model zoo, two matched training lineages | **WITHDRAWN — do not cite its numbers.** Our own audit found a verifier bug specific to this phase's completion format that mechanically forces 0% regardless of model quality. See §5. | `results/phase8/ZOO.md` (+ its withdrawal note) |
| **Audit** | Is any of the above actually trustworthy? | ~30 independent checks, most re-deriving numbers with code that imports none of the project's own analysis | Found the Phase 8 P0 bug and a material `maxHeartbeats` scoring correction. **Independently re-derived Phase 0–5 numbers exactly.** | `results/audit/AUDIT_FINDINGS.md` |
| **WS6** | Post-draft strengthening sprint | 6 items: equivalence bounds/bootstrap CIs, contamination-boundary test, decomposition arm, predictor v2, artifact release, housekeeping | Closed 2026-07-26. Highlights below. | `results/EQUIVALENCE_BOUNDS.md`, `results/phase_decomp/DESIGN.md`, `results/phase6/CONTAMINATION_CORRELATION.md`, `results/phase4/PREDICTOR_V2_RESULT.md` |

### WS6 in more detail (the last work done)
- **Equivalence bounds** — replaced "within noise" hand-waving with paired per-problem bootstrap CIs
  throughout. This is what turned Phase 4's positive into an honestly-caveated one, and what caught
  the within-run-vs-replication CI gap (README §4).
- **Contamination boundary** — is the floor just "where training-set recall ends"? **No.** Trapped
  problems are marginally *more* similar to the training corpus, not less (p=0.049, rank-biserial
  r=−0.17). Stated carefully: *no evidence for the memorization account, weak evidence against.* Two
  caveats travel with it (fragile at n=55 vs 189; TF-IDF is a proxy for one corpus, not either
  model's actual pretraining mix).
- **Decomposition** — can either prover be *prompted* into an honest `sorry`-deferred subgoal
  decomposition on a problem it can't solve? **No, on both models, across 5 rounds.** DeepSeek stated
  three correct intermediate facts and still could not defer them. This is the finding that scopes the
  whole paper to *frozen* provers. Closed by its own pre-registered stopping rule at ~2.3 GPU-h
  instead of the full array.
- **Predictor v2** — richer generation-signal features for the Phase 4 predictor, with a seed-holdout
  guard. **Negative** (max AUC gain +0.033 vs. a pre-registered 0.05 bar). Reported as a small
  independent corroboration: trapped-ness isn't more legible in the generation signal than elapsed
  spend already makes it.

---

## 4. What was tried and eliminated

Useful if you're deciding whether to revisit something. Each of these was actually run, not reasoned
away:

**Test-time:** premise retrieval (BM25), failure memory, LLM reviewer/critic, tactic-skeleton hints,
within-problem budget allocation (both extremes), forced approach diversity, hammer/SMT closing
portfolios, extending trapped problems past 128k, verified-state re-grounding at two granularities,
prompted subgoal decomposition.

**Training-time:** closing-likelihood SFT, lightweight post-hoc GRPO RL, full lab-scale Base→SFT→RL on
two matched lineages (withdrawn — see §5).

**Deliberately not built, with reasons on record:** BFS/proof-state search (prior was search < Pass@1,
and a flat ProofNet# curve says more *search* won't fix an *execution* problem); ReProver/neural
retrieval (F2 shows ~0% terminal knowledge failures, and BM25 already hurt OOD); diversity injection as
a shipped feature (it raises diversity without raising solves).

---

## 5. What you should NOT trust, and other caveats

Read this section before quoting any number out of this repo.

1. **Phase 8's "0.0%-everywhere" headline is WITHDRAWN.** A `no_goal` verifier bug — an emergent
   interaction between two independently-correct fixes — made continuation-style completions
   structurally unable to ever score as solved. It is fixed, with a permanent real-Lean regression
   test. The number is not reported in the paper and should not be cited. Clearing it properly would
   need a GPU regeneration + reverify, which was a deliberate no-go.
2. **The `SYNTHESIS.md` corrections log is required reading.** Six framing corrections from an
   external-calibration sprint, appended 2026-07-25. None retract a headline, but several change the
   precise claim — notably: the 2k budget point is attempt-starved (median *zero* completed propose
   attempts); "miniF2F saturates to a ceiling" needs a two-clause statement; and F2's failure taxonomy
   is right as *terminal* failure mode but buries premise errors encountered along the way (ProofNet#:
   1.0% terminal vs. **51.9% encountered**) — cite both rates, not the 1% alone.
3. **Phase 4's positive is honestly inconclusive at 95%.** The ~30% saving is a point estimate whose
   paired bootstrap CI crosses zero on both models. It is the strongest lever found; it is not a
   settled result.
4. **A within-run bootstrap CI is not a replication.** Learned the hard way here — see README §4. If
   you take one methodological lesson from this repo, take that one.
5. **Everything is at 7–8B.** Whether the floor persists at 32B+ is untested and is the single most
   important open question. Feasibility of a 32B calibration cell is fully scoped (fits via vLLM
   `--tensor-parallel-size 2` on this cluster's existing dual-l40s nodes, no quantization needed) in
   `results/phase_scale32b/FEASIBILITY.md` — deliberately **not run**.
6. **DeepSeek's trapped cores have no dedicated resampling calibration cell** (only Goedel×miniF2F
   does). A logged scope limit, not a to-do — the leverage math didn't justify ~157 GPU-h.

---

## 6. Open threads

None are blocking; all are documented.

| # | Thread | Status |
|---|---|---|
| ~~1~~ | ~~The 13-cell `maxHeartbeats` scoring correction has not been folded back into the summary tables.~~ **DONE 2026-09-02.** Folded into every headline table (`README.md`, `SYNTHESIS.md`, `PROJECT_SUMMARY.md` §3, `paper/floor/main.tex`); largest movement +1.0pp, no qualitative change. See `results/audit/HEARTBEAT_CORRECTED_CURVES.md`. | **Closed** |
| 2 | **Paper finishing work**: citation pass, three figures (generation scripts exist under `scripts/`), author list. Per a standing note, Figure 1 should be the attempts-per-budget / effective-independent-samples curve promoted to the front, not left as appendix numbers. | Open |
| 3 | **Scale (32B+)** — see §5.5. Feasibility scoped, not run. | Open by choice |
| 4 | **Phase 4 confirmation on a second model** — the natural next validation if anyone continues. | Open |
| 5 | **Artifact release packaging** — trapped-core benchmark subsets with provenance, the failed-attempt trace corpus, and the harness with its five-bug catalogue + regression tests. Genuinely reusable; queued but never done. | Open |
| 6 | Audit step 4: broaden the reverify from the trapped core to a sample of near-frontier failures, to check for a similar mid-curve heartbeat effect. | Flagged, not done |

---

## 7. Working in this repo

```bash
module load anaconda/2023.09
conda activate /insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study/scratch/conda-envs/atp
make verify    # fast tests (698, ~10s) + ruff. The gate before any commit.
```

**Layout:** `src/atp/` is the library (see README "Repository tour"), `configs/` holds 81 versioned
experiment YAMLs, `slurm/` holds 31 restartable sbatch scripts, `scripts/` holds per-phase analysis
and one-off probes (named by phase — `phase4_frontier.py`, `phase8_reverify.py`, …), `results/` holds
the receipts, `tests/` mirrors `src/`.

**Non-obvious things that will bite you** (all learned the hard way, all in `DECISIONS.md`):
- Slurm jobs inherit a per-session SSH proxy that breaks every download — `unset HTTP_PROXY
  HTTPS_PROXY http_proxy https_proxy` at the top of every job script.
- Mathlib's ~4.7k oleans must be staged to node-local SSD; loading from shared GPFS causes a storm.
- The Lean REPL must be driven over a PTY, with a recursive `LEAN_PATH`.
- **Never pickle the REPL env** — it silently corrupts verdicts on `@[init]` tactic extensions.
- Force `PATH` after `conda activate`.
- Every GPU sweep is gated on a probe that must accept a `norm_num` proof and reject a false one — so a
  broken environment fails loudly instead of masquerading as a low pass rate. Keep that gate.

**Conventions worth preserving if you continue:** test-first; append-only notebooks; configs not magic
numbers; restartable jobs; and **pre-registration** — write the decision rule and risk list *before*
the expensive run. Two probes here were closed early by their own pre-registered stopping rules
(decomposition at ~2.3 GPU-h instead of a full array; predictor v2 on a committed AUC bar), which is
the practice doing its job. Worked examples: `results/phase_decomp/DESIGN.md`,
`results/phase4/PREDICTOR_V2_DESIGN.md`.

---

## 8. The one-sentence version

Across eight phases, two independently-trained provers, and four training lineages, no test-time
intervention and no training intervention we could trust moved the solve rate of a frozen whole-proof
prover at fixed budget — because the bottleneck is within-approach execution depth, not approach
discovery (tested causally, not inferred) — with one constructive exception, cross-problem budget
allocation, and one methodological contribution that may outlast the rest: five structural harness bugs
and two reporting gaps that reproduce silently in any comparable evaluation.
