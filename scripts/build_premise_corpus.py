"""Build the BM25 premise corpus (Phase 1 retrieval) by parsing pinned-Mathlib source.

Walks the Mathlib `.lean` source vendored in the staged Lean env, extracts each declaration's
qualified name + signature (see `atp.data.premises`), and writes a `{"name","decl"}` JSONL the
retrieval component reads (`RetrievalCfg.corpus`). CPU-only, login-node safe.

Defaults derive the source root + pinned commit from the repo's base config, so the corpus is tied
to the same Mathlib the prover is verified against. Provenance (commit, root, counts) is written to
a sidecar `<out>.meta.json` and echoed to stdout.

    python scripts/build_premise_corpus.py                       # defaults → scratch/premises/...
    python scripts/build_premise_corpus.py --limit 50            # smoke: first 50 source files
    python scripts/build_premise_corpus.py --source <dir> --out <path>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from atp.config import BASE_CONFIG, load_config
from atp.data.premises import build_corpus

# Mathlib source lives under the staged Lean env's lake packages.
_MATHLIB_SUBPATH = ".lake/packages/mathlib/Mathlib"


def _default_source(cfg) -> Path:
    return (Path(cfg.lean.cache_dir) / "atp-lean-env" / _MATHLIB_SUBPATH).resolve()


def main() -> None:
    cfg = load_config(BASE_CONFIG)
    commit = cfg.lean.mathlib_commit
    ap = argparse.ArgumentParser(description="Build the BM25 premise corpus from Mathlib source.")
    ap.add_argument("--source", type=Path, default=_default_source(cfg),
                    help="Mathlib source root (the dir containing Mathlib/*.lean).")
    ap.add_argument("--out", type=Path,
                    default=Path("scratch/premises") / f"mathlib_{commit[:8]}.jsonl",
                    help="Output premises JSONL path.")
    ap.add_argument("--limit", type=int, default=None,
                    help="Cap source files scanned (smoke runs).")
    args = ap.parse_args()

    if not args.source.exists():
        raise SystemExit(
            f"Mathlib source not found at {args.source} — stage the Lean env first "
            f"(scripts/setup_lean_env.sh) or pass --source."
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with args.out.open("w", encoding="utf-8") as fh:
        for row in build_corpus(args.source, limit=args.limit):
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1

    meta = {
        "mathlib_commit": commit,
        "mathlib_repo": cfg.lean.mathlib_repo,
        "source_root": str(args.source),
        "n_premises": n,
        "file_limit": args.limit,
    }
    Path(str(args.out) + ".meta.json").write_text(json.dumps(meta, indent=2))
    print(f"[premises] wrote {n} premises -> {args.out}")
    print(f"[premises] provenance -> {args.out}.meta.json  (mathlib {commit[:8]})")


if __name__ == "__main__":
    main()
