#!/usr/bin/env python3
"""Phase 6 §0 GATE: prove the training corpus (Lean Workbook) is disjoint from BOTH eval sets.

Two passes:
  1. EXACT — normalized (name+whitespace-invariant) formal-statement overlap. Any hit = confirmed
     contamination.
  2. FUZZY — TF-IDF cosine of (a) formal statements and (b) informal/NL statements between each eval
     problem and the whole corpus; report the top match per eval problem so the high-similarity tail
     can be read by hand (near-duplicates that survive renaming/reformalization).

Writes results/phase6/disjointness.json — the artifact the §0 check-in is gated on.

Usage:
  python scripts/phase6_disjointness.py
"""

from __future__ import annotations

import json
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer

from atp.data import load_minif2f
from atp.data.disjointness import exact_overlap, normalize_formal_statement

ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "scratch/phase6/lean_workbook.json"
PROOFNET = ROOT / "scratch/proofnet/test.jsonl"
OUT = ROOT / "results/phase6/disjointness.json"
TOPK = 25          # how many highest-similarity eval problems to surface for manual review
FLAG = 0.55        # cosine at/above which a pair is flagged for mandatory hand-check


def _load_workbook() -> list[dict]:
    return json.loads(WORKBOOK.read_text())


def _load_proofnet() -> list[dict]:
    rows = [json.loads(line) for line in PROOFNET.read_text().splitlines() if line.strip()]
    return rows


def _top_matches(eval_texts: list[str], train_texts: list[str], names: list[str],
                 train_names: list[str]) -> list[dict]:
    """For each eval text, the single most cosine-similar train text (TF-IDF, word 1-2 grams)."""
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)
    X = vec.fit_transform(train_texts + eval_texts)
    Xtr, Xev = X[: len(train_texts)], X[len(train_texts):]
    sims = Xev @ Xtr.T            # (n_eval, n_train) sparse cosine (tfidf rows are L2-normed)
    out = []
    for i in range(sims.shape[0]):
        row = sims.getrow(i)
        if row.nnz == 0:
            out.append({"eval": names[i], "best_train": None, "cosine": 0.0})
            continue
        j = row.indices[row.data.argmax()]
        out.append({"eval": names[i], "best_train": train_names[j],
                    "cosine": float(row.data.max())})
    return out


def main() -> int:
    wb = _load_workbook()
    wb_formal = [r["formal_statement"] for r in wb]
    wb_informal = [r.get("natural_language_statement", "") for r in wb]
    wb_names = [f"lean_workbook_{i}" for i in range(len(wb))]
    train_formal = {wb_names[i]: wb_formal[i] for i in range(len(wb))}

    # --- eval sets ---
    mf = load_minif2f("test", None)
    mf_problems = mf.problems if hasattr(mf, "problems") else mf
    mf_formal = {p.name: p.statement for p in mf_problems}
    mf_informal = {p.name: (p.informal_statement or "") for p in mf_problems}

    pn = _load_proofnet()
    pn_formal = {r["name"]: r["statement"] for r in pn}
    pn_informal = {r["name"]: r.get("informal_statement", "") for r in pn}

    report: dict = {"corpus": "internlm/Lean-Workbook", "n_train": len(wb), "evalsets": {}}

    for ev_name, ev_formal, ev_informal in [
        ("minif2f_test", mf_formal, mf_informal),
        ("proofnet_sharp_test", pn_formal, pn_informal),
    ]:
        exact = exact_overlap(train_formal, ev_formal)

        ev_names = list(ev_formal)
        # formal fuzzy
        formal_top = _top_matches(
            [normalize_formal_statement(ev_formal[n]) for n in ev_names],
            [normalize_formal_statement(s) for s in wb_formal], ev_names, wb_names)
        # informal fuzzy (only over eval problems that HAVE an informal statement)
        inf_idx = [i for i, n in enumerate(ev_names) if ev_informal.get(n, "").strip()]
        informal_top = []
        if inf_idx and any(t.strip() for t in wb_informal):
            informal_top = _top_matches(
                [ev_informal[ev_names[i]] for i in inf_idx],
                wb_informal, [ev_names[i] for i in inf_idx], wb_names)

        formal_sorted = sorted(formal_top, key=lambda d: -d["cosine"])
        informal_sorted = sorted(informal_top, key=lambda d: -d["cosine"])
        report["evalsets"][ev_name] = {
            "n_eval": len(ev_names),
            "flag_cosine": FLAG,
            "exact_overlap_count": len(exact),
            "exact_overlap_pairs": exact,
            "formal_flagged": [d for d in formal_sorted if d["cosine"] >= FLAG],
            "informal_flagged": [d for d in informal_sorted if d["cosine"] >= FLAG],
            "formal_top": formal_sorted[:TOPK],
            "informal_top": informal_sorted[:TOPK],
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print(f"[disjointness] corpus={report['corpus']} n_train={report['n_train']}")
    for ev_name, r in report["evalsets"].items():
        f_max = r["formal_top"][0]["cosine"] if r["formal_top"] else 0.0
        i_max = r["informal_top"][0]["cosine"] if r["informal_top"] else 0.0
        print(f"  {ev_name}: n={r['n_eval']}  EXACT_OVERLAP={r['exact_overlap_count']}  "
              f"formal_cos_max={f_max:.3f} (flagged≥{FLAG}: {len(r['formal_flagged'])})  "
              f"informal_cos_max={i_max:.3f} (flagged≥{FLAG}: {len(r['informal_flagged'])})")
    print(f"[disjointness] wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
