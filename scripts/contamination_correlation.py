#!/usr/bin/env python3
"""WS6 item 2 (free half): does overlap with the Lean-Workbook training corpus predict trapped status?

The "execution floor = training-set recall boundary" reading: if trapped problems are systematically
the ones LEAST similar to the training corpus, the floor could be a memorization boundary rather than
a genuine execution-depth ceiling. This extends the Phase 6 Section-0 disjointness gate
(`scripts/phase6_disjointness.py`, `results/phase6/disjointness.json`) from "flag near-duplicates" to
"correlate overlap score against solved/trapped status across the FULL 244-problem miniF2F eval set."

CPU-only, reuses the exact same TF-IDF cosine machinery as the existing disjointness gate (same
vectorizer settings) so the overlap score is directly comparable to the already-audited fuzzy-match
numbers, not a new ad-hoc metric.

Pre-registered decision rule (PLAN_NEXT.md WS6 item 2, committed before this script was run):
  NULL (no reframe needed): overlap score is not a significant predictor of trapped status.
  SIGNAL (reframe + escalate): trapped problems are significantly LESS similar to the training
    corpus than solved problems -- triggers a go/no-go conversation on paid mutation-probe follow-up.

Usage: python scripts/contamination_correlation.py
Writes results/phase6/CONTAMINATION_CORRELATION.md and .json.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer

from atp.data import load_minif2f
from atp.data.disjointness import exact_overlap, normalize_formal_statement

ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "scratch/phase6/lean_workbook.json"
TRAPPED_MINIF2F = ROOT / "scratch/phase2/trapped_minif2f.txt"
BASELINE_RUN = ROOT / "results/baseline"
OUT_JSON = ROOT / "results/phase6/contamination_correlation.json"
OUT_MD = ROOT / "results/phase6/CONTAMINATION_CORRELATION.md"


def per_problem_cosine(eval_formal: dict[str, str], train_formal: list[str]) -> dict[str, float]:
    """Same TF-IDF settings as phase6_disjointness.py's `_top_matches`, full 244-problem coverage."""
    names = list(eval_formal)
    eval_texts = [normalize_formal_statement(eval_formal[n]) for n in names]
    train_texts = [normalize_formal_statement(s) for s in train_formal]
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)
    X = vec.fit_transform(train_texts + eval_texts)
    Xtr, Xev = X[: len(train_texts)], X[len(train_texts):]
    sims = Xev @ Xtr.T
    out = {}
    for i, name in enumerate(names):
        row = sims.getrow(i)
        out[name] = float(row.data.max()) if row.nnz else 0.0
    return out


def solved_names(run_dir: Path) -> set[str]:
    solved = set()
    for f in glob.glob(str(run_dir / "problems" / "*.json")):
        d = json.load(open(f))
        if d.get("solved"):
            solved.add(d["problem_name"])
    return solved


def mann_whitney_u(a: list[float], b: list[float]) -> tuple[float, float]:
    """Two-sided Mann-Whitney U via scipy if available, else a simple rank-sum fallback (no p-value)."""
    try:
        from scipy.stats import mannwhitneyu
        u, p = mannwhitneyu(a, b, alternative="two-sided")
        return float(u), float(p)
    except ImportError:
        return float("nan"), float("nan")


def main() -> int:
    wb = json.loads(WORKBOOK.read_text())
    wb_formal = [r["formal_statement"] for r in wb]
    wb_names = [f"lean_workbook_{i}" for i in range(len(wb))]
    train_formal = {wb_names[i]: wb_formal[i] for i in range(len(wb))}

    mf = load_minif2f("test", None)
    mf_problems = mf.problems if hasattr(mf, "problems") else mf
    mf_formal = {p.name: p.statement for p in mf_problems}

    cosine = per_problem_cosine(mf_formal, wb_formal)
    exact_hits = {ev for _, ev in exact_overlap(train_formal, mf_formal)}

    trapped = {ln.strip() for ln in TRAPPED_MINIF2F.read_text().splitlines() if ln.strip()}
    solved = solved_names(BASELINE_RUN)
    all_names = set(mf_formal)
    not_trapped_not_solved = all_names - trapped - solved  # partial: some seeds solve, some don't

    trapped_scores = [cosine[n] for n in trapped if n in cosine]
    solved_scores = [cosine[n] for n in solved if n in cosine]

    u, p = mann_whitney_u(trapped_scores, solved_scores)
    trapped_exact = sum(1 for n in trapped if n in exact_hits)
    solved_exact = sum(1 for n in solved if n in exact_hits)

    import statistics as st
    report = {
        "n_problems": len(all_names),
        "n_trapped": len(trapped),
        "n_solved_union": len(solved),
        "n_partial": len(not_trapped_not_solved),
        "trapped_cosine_mean": st.mean(trapped_scores) if trapped_scores else None,
        "trapped_cosine_median": st.median(trapped_scores) if trapped_scores else None,
        "solved_cosine_mean": st.mean(solved_scores) if solved_scores else None,
        "solved_cosine_median": st.median(solved_scores) if solved_scores else None,
        "mannwhitney_u": u,
        "mannwhitney_p": p,
        "trapped_exact_overlap_count": trapped_exact,
        "trapped_exact_overlap_frac": trapped_exact / len(trapped) if trapped else None,
        "solved_exact_overlap_count": solved_exact,
        "solved_exact_overlap_frac": solved_exact / len(solved) if solved else None,
        "total_exact_overlap_count": len(exact_hits),
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2))

    alpha = 0.05
    if p != p:  # NaN check
        verdict = "INCONCLUSIVE (scipy unavailable, no p-value computed -- see means/medians directly)"
    elif p < alpha and report["trapped_cosine_mean"] < report["solved_cosine_mean"]:
        verdict = "SIGNAL: trapped problems are significantly LESS similar to the training corpus than solved ones (p={:.4f}) -- escalate per WS6 item 2's decision rule.".format(p)
    else:
        verdict = "NULL: no significant overlap-score difference between trapped and solved problems (p={:.4f}) -- floor is not explained by training-corpus recall on this test.".format(p)

    md = f"""# Contamination-correlation check (WS6 item 2, free half) -- {verdict.split(':')[0]}

Pre-registered decision rule (committed before running, PLAN_NEXT.md WS6 item 2): NULL if overlap
score does not significantly predict trapped status; SIGNAL if trapped problems are significantly
LESS similar to the Lean-Workbook training corpus than solved ones.

## Result

- {report['n_problems']} miniF2F problems: {report['n_trapped']} trapped (0/3 baseline seeds solve),
  {report['n_solved_union']} solved by at least one baseline seed, {report['n_partial']} others.
- TF-IDF formal-statement cosine similarity to nearest Lean-Workbook training example (same metric as
  the Phase 6 Section-0 disjointness gate):
  - trapped: mean {report['trapped_cosine_mean']:.4f}, median {report['trapped_cosine_median']:.4f}
  - solved:  mean {report['solved_cosine_mean']:.4f}, median {report['solved_cosine_median']:.4f}
- Mann-Whitney U test (two-sided): U={report['mannwhitney_u']:.1f}, p={report['mannwhitney_p']:.4f}
- Exact (normalized-statement) overlap: {report['trapped_exact_overlap_count']}/{report['n_trapped']}
  ({100*(report['trapped_exact_overlap_frac'] or 0):.1f}%) of trapped problems vs.
  {report['solved_exact_overlap_count']}/{report['n_solved_union']}
  ({100*(report['solved_exact_overlap_frac'] or 0):.1f}%) of solved problems have an exact
  normalized-statement match in Lean-Workbook (of {report['total_exact_overlap_count']} total exact
  overlaps across the full eval set).

## Verdict

**{verdict}**

## Interpretation

{"The execution-floor thesis is not undermined by this check: trapped problems are not systematically the ones the model has NOT seen a near-duplicate of during training. This is consistent with (does not by itself confirm) F2/F3's reading of trapped failures as genuine execution-depth failures, not recall gaps." if "NULL" in verdict else "This reframes the central finding: the floor correlates with training-corpus dissimilarity, which is consistent with a recall-boundary reading rather than a pure execution-depth ceiling. Per WS6's pre-registration, this triggers a go/no-go conversation on the paid mutation-probe follow-up (MiniF2F-ALF-style statement perturbation, or a miniF2F-v2 re-run) before further action."}
"""
    OUT_MD.write_text(md)
    print(verdict)
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
