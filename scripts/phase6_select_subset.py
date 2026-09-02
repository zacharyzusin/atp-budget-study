#!/usr/bin/env python3
"""Stage C probe Task: select the GRPO train + held-out subsets from a base K-seed generation run.

Input: an eval run dir where the DeepSeek BASE was swept over a decontaminated `lean_workbook_clean`
slice at budget 8192 with seeds 0..K-1 (see configs/phase6_grpo_subset_deepseek.yaml). Each
(problem, seed) cell's `agent_states/*.json` carries `solved`; the per-problem solve-COUNT over K
seeds is the empirical base difficulty.

We keep the sweet-spot band (default base solve-rate in [1/16, 10/16] — dense GRPO advantage: not
0/K no-signal, not K/K no-headroom), then draw a DISJOINT train (~256) and held-out gate (~200) set
from the same band (matched difficulty). Writes train.jsonl / heldout.jsonl (each row {name,
statement, opens, imports} — the columns the GRPO reward needs) + subset_summary.json.

The corpus is disjoint from miniF2F/ProofNet# by construction (§0 decontamination); this only adds
train ∩ heldout = ∅. Pure selection lives in atp.rl.subset (unit-tested); this is the thin IO shell.

Usage:
  python scripts/phase6_select_subset.py --config configs/phase6_grpo_subset_deepseek.yaml \
      --run-dir results/phase6_grpo_subset_deepseek --k 16 --out-dir scratch/phase6/grpo/deepseek
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from atp.agents.state import AgentState
from atp.config import load_config
from atp.data import load_dataset
from atp.rl.subset import select_by_solve_rate

ROOT = Path(__file__).resolve().parents[1]


def solve_counts(run_dir: str | Path) -> tuple[dict[str, int], dict[str, int]]:
    """Return ({theorem_name: #seeds solved}, {theorem_name: #seeds attempted}) over all cells in
    run_dir/agent_states (pure; no Lean)."""
    states = Path(run_dir) / "agent_states"
    counts: dict[str, int] = defaultdict(int)
    seen: dict[str, int] = defaultdict(int)
    for fp in sorted(states.glob("*.json")):
        st = AgentState.load(fp)
        if st is None:
            continue
        seen[st.theorem_name] += 1
        if st.solved:
            counts[st.theorem_name] += 1
    # ensure every attempted problem appears (0-solve problems are still bucketed -> excluded)
    for name in seen:
        counts.setdefault(name, 0)
    return dict(counts), dict(seen)


def _rows(names, by_name) -> list[dict]:
    out = []
    for n in names:
        p = by_name.get(n)
        if p is None:
            continue
        out.append(
            {
                "name": n,
                "statement": p.statement,
                "opens": list(p.opens),
                "imports": list(p.imports),
            }
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--k", type=int, required=True, help="number of seeds swept (samples/problem)")
    ap.add_argument("--lo-frac", type=float, default=1 / 16)
    ap.add_argument("--hi-frac", type=float, default=10 / 16)
    ap.add_argument("--n-train", type=int, default=256)
    ap.add_argument("--n-heldout", type=int, default=200)
    ap.add_argument(
        "--min-samples",
        type=int,
        default=8,
        help="drop problems with fewer attempted seeds than this (partial-coverage cells "
        "from cancelled shards): the absolute-count band assumes ~k samples, so a "
        "low-coverage all-solve problem would otherwise be mis-banded as in-band",
    )
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    cfg = load_config(args.config)
    ds = load_dataset(cfg, model_revision=cfg.model.revision)
    by_name = {p.name: p for p in ds.problems}

    counts, seen = solve_counts(args.run_dir)
    dropped = sorted(n for n, s in seen.items() if s < args.min_samples)
    counts = {n: c for n, c in counts.items() if seen.get(n, 0) >= args.min_samples}
    split = select_by_solve_rate(
        counts,
        k=args.k,
        lo_frac=args.lo_frac,
        hi_frac=args.hi_frac,
        n_train=args.n_train,
        n_heldout=args.n_heldout,
        seed=args.seed,
    )

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    train_rows = _rows(split.train, by_name)
    heldout_rows = _rows(split.heldout, by_name)
    (out / "train.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in train_rows)
    )
    (out / "heldout.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in heldout_rows)
    )

    # Held-out G1 gate eval reuses the standard lean_workbook loader, so emit the held-out slice as
    # a clean-corpus JSON (same schema as lean_workbook_clean.json) a workbook eval config reads via
    # `lean_workbook_path`. Filter the ORIGINAL clean corpus by the SAME names load_lean_workbook
    # derives (`_lw_id` or lean_workbook_<i>), so statements/tags are byte-identical to training.
    heldout_set = set(split.heldout)
    raw = json.loads(Path(cfg.data.lean_workbook_path).read_text())
    heldout_corpus = [
        d for i, d in enumerate(raw) if (d.get("_lw_id") or f"lean_workbook_{i}") in heldout_set
    ]
    (out / "heldout_corpus.json").write_text(
        json.dumps(heldout_corpus, ensure_ascii=False, indent=2)
    )

    # solve-count histogram for the smoke gate (a) check: is there any reward signal in the band?
    hist: dict[int, int] = {}
    for c in counts.values():
        hist[c] = hist.get(c, 0) + 1
    summary = {
        "config": args.config,
        "run_dir": args.run_dir,
        "k": args.k,
        "min_samples": args.min_samples,
        "n_dropped_low_coverage": len(dropped),
        "n_full_coverage": len(counts),
        "band": [split.band_lo, split.band_hi],
        "band_size": split.band_size,
        "n_train": len(train_rows),
        "n_heldout": len(heldout_rows),
        "disjoint": set(split.train).isdisjoint(split.heldout),
        "enough": split.enough,
        "solve_count_hist": {str(k): hist[k] for k in sorted(hist)},
        "select_seed": args.seed,
    }
    (out / "subset_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    assert set(split.train).isdisjoint(split.heldout), "train/heldout overlap"
    print(
        f"[subset] band [{split.band_lo},{split.band_hi}] of k={args.k}: {split.band_size} "
        f"eligible -> train {len(train_rows)} / heldout {len(heldout_rows)} "
        f"(attempted {len(counts)}); enough={split.enough}"
    )
    print(f"[subset] solve-count hist: {summary['solve_count_hist']}")
    print(f"[subset] wrote {out}/train.jsonl + heldout.jsonl + subset_summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
