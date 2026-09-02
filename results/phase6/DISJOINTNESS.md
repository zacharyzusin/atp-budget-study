# Phase 6 §0 — Train/Test Disjointness Proof

**Gate status: GREEN (after decontamination).** Nothing trains until this holds; this document +
`disjointness.json` + `disjointness_proof.json` are the artifact.

## Corpus & eval sets
- **Training corpus:** `internlm/Lean-Workbook` — 140,214 autoformalized problems
  (`formal_statement` + `natural_language_statement`). Raw → `scratch/phase6/lean_workbook.json`.
- **Eval sets (disjointness required against BOTH):** miniF2F-test (244) and ProofNet#-test (186).

## Method (`scripts/phase6_disjointness.py`, `scripts/phase6_decontaminate.py`)
Three overlap signals, each Workbook problem vs the **union** of both eval sets:
1. **Exact** — normalized formal-statement match (`normalize_formal_statement`: strip
   `theorem/lemma/example/def <name>`, proof tail, collapse whitespace). Decisive — any hit is a
   confirmed duplicate up to name/formatting. Tested: `tests/test_disjointness.py` (6).
2. **Formal cosine** — TF-IDF (word 1–2 grams) over normalized formal statements.
3. **Informal cosine** — TF-IDF over the natural-language statements.

## What the raw scan found (the gate did its job)
- **miniF2F: 10 EXACT overlaps** — `imo_1983_p6`, `amc12a_2021_p25`, `amc12a_2021_p8`,
  `amc12b_2020_p2`, `algebra_absapbon1pabsapbleqsumabsaon1pabsa` (each twice in Workbook). Competition
  problems sourced from AoPS — verbatim leakage. Training on raw Workbook would have contaminated the
  miniF2F headline.
- **ProofNet#: 0 exact overlaps.**

## Threshold choice (evidence-based, from the boundary band)
Reading the boundary band drove the rule:
- **Formal cosine is dominated by *thematic* similarity, not duplication.** The 0.85–0.98 non-exact
  band is distinct problems sharing notation (`Real.log/sqrt/cos`, ℕ binders, inequality shape) — e.g.
  `cos(2π/7)+cos(4π/7)+cos(8π/7)=0`. These are legitimate **same-technique** training data; dropping
  them would hurt training utility without improving eval validity (30k problems sit ≥0.5).
- **Informal cosine is the clean duplicate signal.** The ≥0.9 band is unambiguous near-dups
  (`cos(π/9)cos(2π/9)cos(4π/9)=1/8`), only ~60 problems ≥0.9 / ~24 at 1.0.

**Drop rule (conservative on the duplicate axis, keeps same-technique data):**
`exact ∪ (formal cosine ≥ 0.95) ∪ (informal cosine ≥ 0.85)`.
- formal ≥0.95 catches near-identical *reformalizations* (incl. binder-renamed dups exact-match misses)
  at negligible cost; the thematic 0.5–0.95 band is **kept**.
- informal ≥0.85 sweeps the near-duplicate natural-language tail with margin below the clear-dup 0.9 line.

## Result (`disjointness_proof.json`)
| | value |
|---|---|
| raw corpus | 140,214 |
| **dropped** | **202 (0.14%)** |
| **clean corpus** | **140,012** → `scratch/phase6/lean_workbook_clean.json` |
| residual max formal cosine | 0.95 (thematic, verified non-duplicate) |
| residual max informal cosine | 0.845 |
| residual exact overlaps | **0** |

Every checkpoint manifest will record `corpus=lean_workbook_clean` + this proof. The §0 gate is GREEN:
training proceeds on the 140,012-problem clean corpus. Next: Task 6.1 harvest.
