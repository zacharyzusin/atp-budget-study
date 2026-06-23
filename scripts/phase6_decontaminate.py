#!/usr/bin/env python3
"""Phase 6 §0: decontaminate Lean Workbook against BOTH eval sets, write the clean corpus + proof.

For every Workbook problem we compute its MAX similarity to ANY eval problem (miniF2F-test ∪
ProofNet#-test), three ways: exact normalized-formal match (decisive), formal TF-IDF cosine,
informal TF-IDF cosine. A problem is DROPPED if it is an exact match OR exceeds a (conservative,
manually validated) cosine threshold on either text. The kept remainder is the training corpus; its
residual-max-cosine + the dropped/kept boundary are the §0 disjointness proof.

Modes:
  --analyze : print threshold distribution + boundary band, write nothing (pick τ from this)
  --formal-tau F --informal-tau I : write scratch/phase6/lean_workbook_clean.json + the proof JSON
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from atp.data import load_minif2f
from atp.data.disjointness import normalize_formal_statement

ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "scratch/phase6/lean_workbook.json"
PROOFNET = ROOT / "scratch/proofnet/test.jsonl"
CLEAN = ROOT / "scratch/phase6/lean_workbook_clean.json"
PROOF = ROOT / "results/phase6/disjointness_proof.json"


def _per_train_max(train_texts: list[str], eval_texts: list[str]) -> np.ndarray:
    """Max TF-IDF cosine of each train text to ANY eval text (word 1-2 grams)."""
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)
    X = vec.fit_transform(train_texts + eval_texts)
    Xtr, Xev = X[: len(train_texts)], X[len(train_texts):]
    sims = Xtr @ Xev.T                     # (n_train, n_eval)
    return np.asarray(sims.max(axis=1).todense()).ravel()


def _eval_sets() -> tuple[dict[str, str], dict[str, str]]:
    mf = load_minif2f("test", None)
    mf_problems = mf.problems if hasattr(mf, "problems") else mf
    ev_formal = {p.name: p.statement for p in mf_problems}
    ev_informal = {p.name: (p.informal_statement or "") for p in mf_problems}
    for line in PROOFNET.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            ev_formal[r["name"]] = r["statement"]
            ev_informal[r["name"]] = r.get("informal_statement", "")
    return ev_formal, ev_informal


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--analyze", action="store_true")
    ap.add_argument("--formal-tau", type=float, default=0.9)
    ap.add_argument("--informal-tau", type=float, default=0.8)
    args = ap.parse_args()

    wb = json.loads(WORKBOOK.read_text())
    wb_formal = [r["formal_statement"] for r in wb]
    wb_informal = [r.get("natural_language_statement", "") for r in wb]
    wb_norm = [normalize_formal_statement(s) for s in wb_formal]

    ev_formal, ev_informal = _eval_sets()
    ev_norm_to_name = {normalize_formal_statement(s): n for n, s in ev_formal.items()}
    ev_informal_texts = [t for t in ev_informal.values() if t.strip()]

    # exact normalized-formal overlap (decisive)
    exact = np.array([wb_norm[i] in ev_norm_to_name for i in range(len(wb))])

    f_max = _per_train_max(wb_norm, list(ev_formal.values()))
    i_max = _per_train_max(wb_informal, ev_informal_texts)

    if args.analyze:
        print(f"n_train={len(wb)}  exact_overlaps={int(exact.sum())}")
        print("threshold | #formal>=t | #informal>=t")
        for t in (0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.99, 1.0):
            nf, ni = int((f_max >= t).sum()), int((i_max >= t).sum())
            print(f"   {t:.2f}   |   {nf:6d}   |   {ni:6d}")
        # boundary band: non-exact problems just under cos 1.0 on formal, and the informal high band
        print("\n--- FORMAL boundary band (non-exact), cosine in [0.85,1.0], sample of 12 ---")
        band = [i for i in range(len(wb)) if not exact[i] and 0.85 <= f_max[i] <= 1.0]
        band.sort(key=lambda i: -f_max[i])
        for i in band[:12]:
            print(f"  cos={f_max[i]:.3f}  lean_workbook_{i}: {wb_norm[i][:110]}")
        print("\n--- INFORMAL high band, cosine in [0.7,0.95], sample of 8 ---")
        ib = [i for i in range(len(wb)) if 0.7 <= i_max[i] <= 0.95]
        ib.sort(key=lambda i: -i_max[i])
        for i in ib[:8]:
            print(f"  cos={i_max[i]:.3f}  lean_workbook_{i}: {wb_informal[i][:110]}")
        return 0

    drop = exact | (f_max >= args.formal_tau) | (i_max >= args.informal_tau)
    keep_idx = [i for i in range(len(wb)) if not drop[i]]
    clean = [wb[i] | {"_lw_id": f"lean_workbook_{i}"} for i in keep_idx]
    CLEAN.write_text(json.dumps(clean, ensure_ascii=False))

    proof = {
        "corpus": "internlm/Lean-Workbook",
        "n_train_raw": len(wb),
        "n_dropped": int(drop.sum()),
        "n_clean": len(keep_idx),
        "drop_rule": {
            "exact_normalized_formal_overlap": True,
            "formal_cosine_tau": args.formal_tau,
            "informal_cosine_tau": args.informal_tau,
            "eval_sets": ["minif2f_test", "proofnet_sharp_test"],
        },
        "n_exact_overlap": int(exact.sum()),
        "residual_max_formal_cosine": float(f_max[keep_idx].max()),
        "residual_max_informal_cosine": float(i_max[keep_idx].max()),
        "clean_corpus_path": str(CLEAN),
    }
    PROOF.parent.mkdir(parents=True, exist_ok=True)
    PROOF.write_text(json.dumps(proof, indent=2, ensure_ascii=False))
    print(f"[decontam] raw={len(wb)} dropped={int(drop.sum())} clean={len(keep_idx)}")
    print(f"[decontam] residual max cosine: formal={proof['residual_max_formal_cosine']:.3f} "
          f"informal={proof['residual_max_informal_cosine']:.3f}")
    print(f"[decontam] wrote {CLEAN} + {PROOF}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
