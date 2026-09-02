# The paper

`main.tex` — *the execution-floor paper.* Status at project close (2026-09-02): **drafted, compiles
clean at 14 pages, not finished.** What remains is writing, not experiments.

## Build

```bash
cd paper/floor
pdflatex -interaction=nonstopmode main.tex
bibtex main
pdflatex -interaction=nonstopmode main.tex
pdflatex -interaction=nonstopmode main.tex
```

Verified clean at close: 14 pages, 0 LaTeX errors, 0 undefined references, 0 undefined citations.
Build artifacts (`.aux`, `.log`, `.bbl`, `main.pdf`) are gitignored — only sources are tracked.

## Files

| File | What |
|---|---|
| `main.tex` | The paper |
| `refs.bib` | Bibliography |
| `PINS.md` | Exact model revisions, Lean toolchains and mathlib commits behind every headline number |
| `neurips_2026.sty`, `environ.sty`, `trimspaces.sty` | Style files (vendored) |

## What's left (the `\todo`s in `main.tex`)

1. **Author list** — deliberately blank for anonymized submission.
2. **Related-work positioning** vs. the test-time-compute scaling literature — needs a citation pass.
3. **Phase 4 vs. the adaptive-allocation literature.** A candidate framing, recorded but not yet
   written against real paragraphs: existing adaptive-allocation work optimizes where the
   difficulty-to-payoff mapping is *smooth*; this setting differs on two axes — the winnable
   population is *thin*, and success is *verifier-certain* rather than probabilistic. Sharpen against
   actual related work rather than adopting verbatim.
4. **Three figures**, generation scripts already exist under `scripts/`:
   - F1 — the 2×2 pass@B grid (miniF2F/ProofNet# × Goedel/DeepSeek).
   - F4 — Step C before/after diversity + solve panel, all four cells.
   - F5 — the allocation efficiency frontier (realizable vs. uniform vs. oracle).
   Standing note on F1: the attempts-per-budget / effective-independent-samples curve is the methods
   finding most likely to travel beyond this project, so it belongs **on the front page**, not as
   appendix numbers.
5. ~~Fold the 13 corrected `maxHeartbeats` cells back into the summary tables.~~ **DONE
   2026-09-02** — Table~\ref{tab:passb} and the two prose references now carry the corrected values.
   Largest movement +1.0pp; no qualitative reading changes. Before/after and the reproduction check
   are in `results/audit/HEARTBEAT_CORRECTED_CURVES.md`.

## Framing notes worth preserving

- The abstract **leads with the measurement contributions** (five harness bugs, pass@budget ≠ pass@N,
  the within-run-CI vs. replication gap) before the substantive null. Those contributions don't
  inherit the "only tested at 8B" objection, and they're reusable independent of whether a reader
  cares about the model question.
- The scope qualifier **"frozen whole-proof provers" must survive into the first two sentences.** It
  is what the two-model decomposition finding actually earned, and without it stated early a reviewer
  can cite a decomposition-trained or agentic system as a one-line rebuttal. The abstract is the last
  thing written and the most likely place to drift back toward the old overclaim ("hard execution
  floor, nothing moves it") — watch for that specifically.
- **Phase 8 is reported as withdrawn, with its bug and mechanism, not as a number.** That is
  deliberate and should not be "fixed" by quietly restoring the 0.0% table.
- **Phase 4 is a counterpoint scoped to what is confirmed**, not a settled positive: its paired
  bootstrap CI crosses zero on both models.

For the project's full context see [`../../HANDOFF.md`](../../HANDOFF.md).
