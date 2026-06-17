# Phase 2 — From negative result to mechanism

**Thesis we are writing toward:** *Compute budget, not agentic scaffolding, is the lever for
whole-proof proving at this scale — and here is precisely where and why budget stops paying off
(diversity collapse / capability floor on OOD problems), validated across two prover models, with a
verifier-soundness caveat that recalibrates how these systems should be evaluated.*

We have the **what** (scaffolding doesn't help; budget saturates; ProofNet# curve is flat). Phase 2 gets
the **why**. The why is the cheapest thing left — it's an analysis pass on data already on disk — and it
is what turns a borderline negative-results note into a paper with a real claim. The crux is the
**asymmetry**: the model converts budget into solves beautifully on miniF2F (29.6→74.9% over 64×) and
almost not at all on ProofNet# (4.8→14.3%). Explaining that asymmetry retroactively explains the
scaffolding null (the components we tested can't address the actual bottleneck).

**Data is in place (verified 2026-06-17):** `results/<run>/agent_states/<problem>__seed<k>.json` holds
every attempt — `proof` (full generated Lean), `feedback` (Lean error, prefixed `Failed at step N
(`tactic`): ...`), `reason` ∈ {compile_error, ok, loophole, no_goal}, `kind` ∈ {propose, refine},
`completion_tokens`, plus a budget `ledger`. miniF2F baseline = 732 states; ProofNet# baseline = 558.
ProofNet# source `scratch/proofnet/test.jsonl` gives `name` (subfield prefix), `informal_statement`.

Per CLAUDE.md: every analysis ships with a test in `tests/`, runs CPU-only on a login node, is config/
arg-driven, and writes its outputs under `results/phase2/`. Append findings to PROGRESS.md.

---

## A. Analysis on existing data — NO new GPU-hours (gates everything below)

### A1. Sample-diversity collapse  *(the headline mechanism)*
Flat pass@B at high budget is the classic signature of the model resampling minor variants of the same
wrong idea, so extra tokens buy nothing. Test directly:
- Per (problem, seed): measure diversity across the attempt set — **distinct first tactics**, **distinct
  proof skeletons** (tactic-sequence n-gram / structural hash), and **embedding spread** of the `proof`
  texts (optional; sentence-transformer if a CPU model is cheap, else skip to keep it GPU-free).
- Correlate diversity with solve probability, **on both benchmarks**.
- **Hypothesis:** diversity collapses on ProofNet# but holds on miniF2F. If so → mechanism found, and the
  scaffolding null becomes *predictable* (none of retrieval/memory/reviewer/skeletons touch diversity).

### A2. Failure-mode taxonomy on the 128k unsolved set  *(gates every new-experiment direction)*
Classify each unsolved cell's attempts into:
- **formalization failure** — non-compiling Lean (`compile_error` at step 0/1, syntax/elaboration).
- **knowledge failure** — hallucinated / nonexistent mathlib lemmas (parse `feedback` for "unknown
  identifier", "unknown constant", "unknown" + ambiguous-name patterns).
- **reasoning failure** — compiles but wrong / `unsolved goals` early.
- **near-miss** — right approach, fails deep (`Failed at step N` with large N relative to proof length).
- (also bucket `loophole`=sorry-attempts and `no_goal`=truncation separately.)

**Decision gates:**
- knowledge-failure-dominant → relevance-filtered BM25 retrieval gets *one* principled shot (and we get
  a story for why naive BM25 poisoned the prompt: it injected plausible-but-irrelevant lemmas).
- approach/can't-start-dominant → retrieval doomed (no premise fixes not knowing the idea) and BFS doomed
  (search needs a per-step policy the OOD model lacks) → deferral becomes a justified claim, not a hunch.
- near-miss-dominant → the one case where revisiting search could pay; worth the bet then.

### A3. Tokens-to-solve distribution
Is the unsolved ProofNet# mass a long tail that is "almost solving," or a hard floor that never moves?
Plot tokens-to-first-proof CDF + the unsolved fraction vs budget. Directly explains the flatness.

### A4. Difficulty stratification
Correlate solve rate with **subfield** (ProofNet# `name` prefix: Artin/Rudin/Munkres/…) and a
proof-difficulty proxy (informal-statement length / statement complexity). Usually reveals the flat curve
is a hard *core* no budget cracks.

**Deliverable for A:** `results/phase2/MECHANISM.md` + figures; PROGRESS.md entry; and a verdict line per
A2 gate that says which (if any) of B/C/retrieval is worth GPU-hours.

---

## B. Second-model replication — DeepSeek-Prover-V2-7B  *(after A; for generality)*
A reviewer's first question about a negative result: "is this a Goedel-V2-8B quirk?" Replicate the
headline findings — pass@B curves + OOD flatness + the scaffolding null — on a second prover (different
training, similar scale). Needs its own Lean pin and a baseline + the components rerun on **at least
ProofNet#**. Moderate cost; run to *confirm the mechanism A identified generalizes*, not as a fishing
trip. (>50 GPU-h → confirm scope before launch per CLAUDE.md, though the GPU-h rule is soft here.)

## C. Diversity injection — ONLY if A1 supports it  *(contingent capstone)*
If A1 shows diversity collapse is the bottleneck, the one intervention that addresses it: temperature /
nucleus scheduling across the sample budget, or prompting for explicitly distinct approaches. This is the
"and here is the lever that *does* move the needle" capstone — but contingent on A1; do not pre-commit.

## Cross-cutting: verifier soundness as a contribution
Elevate the 2026-06-14 soundness bug (truncated generations / empty REPL responses scoring as false
solves) from caveat to a short methodological section: the failure mode, how to detect it, and that it
silently inflates pass rates. Many prior pipelines plausibly have this bug. Citable.

## Explicitly NOT doing (unless A2 resurrects one)
- A **third benchmark** (breadth without depth; two benchmarks + a mechanism is a complete story).
- A **fancier neural retriever** (ReProver) — unmotivated unless A2 says premise-gaps dominate.
- Any further **OFAT scaffolding** components.

---

## Order of operations
1. A1 + A2 first (cheap, CPU, gates everything, makes the thesis). → MECHANISM.md verdict.
2. A3 + A4 fold in alongside (same data pass).
3. B (second-model replication) to confirm generality once A has named the mechanism.
4. C (diversity injection) only if A1 points there.
Hold BFS, fancier retrieval, third benchmark unless A2 specifically resurrects one.
