"""Compile-gate: do a benchmark's statement HEADS elaborate against the pinned mathlib?

For each problem we compile `<statement> := by sorry`. A head that typechecks yields only a `sorry`
*warning* (RawVerification.success=True); a head with an unknown identifier / bad notation / wrong
arity yields an *error* (success=False), with the reason in `output`. No GPU, no model — pure Lean
elaboration against the env the verifier uses.

Run this BEFORE any baseline GPU run on a newly staged benchmark (e.g. ProofNet#): a benchmark whose
heads don't elaborate against our mathlib pin is silently all-zeros — every proof attempt fails at
the statement-compile stage and you burn GPU for a flat 0. The gate is cheap and decisive.

    python scripts/validate_statements.py --config configs/proofnet_baseline.yaml [--limit N]

Writes results/<benchmark>/statement_validation.json and prints a summary + sample failures.
Backend is injected (`_run`) so the tally logic is unit-tested with a ScriptedBackend, no Lean.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from atp.config import load_config
from atp.data import load_dataset


def _first_error(output: str) -> str:
    for line in output.splitlines():
        if ": error:" in line:
            return line.strip()
    return (output.strip().splitlines() or [""])[0][:200]


def _run(problems, backend) -> list[dict]:
    """Compile `<statement> := by sorry` per problem; record elaboration success + first error."""
    out = []
    for p in problems:
        thm = p.to_theorem()
        rv = backend.verify(thm, f"{thm.statement} := by sorry")
        out.append({
            "name": p.name,
            "ok": bool(rv.success),
            "error": "" if rv.success else _first_error(rv.output),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--limit", type=int, default=None, help="check only the first N (smoke)")
    args = ap.parse_args()

    config = load_config(args.config)
    ds = load_dataset(config)
    problems = ds.problems[: args.limit] if args.limit else ds.problems

    # Import the real Lean backend lazily so the unit test (which injects a ScriptedBackend) needs
    # no Lean. Done here, not at module top, to keep `_run` pure.
    from atp.lean import ReplBackend

    backend = ReplBackend(config)
    t0 = time.time()
    records = _run(problems, backend)
    elapsed = time.time() - t0

    n = len(records)
    n_ok = sum(r["ok"] for r in records)
    fails = [r for r in records if not r["ok"]]
    out_dir = Path(config.project.root) / config.project.results_dir / config.data.benchmark
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "benchmark": config.data.benchmark,
        "split": config.data.split,
        "lean_toolchain": config.lean.toolchain,
        "mathlib_commit": config.lean.mathlib_commit,
        "n_problems": n,
        "n_elaborated": n_ok,
        "elaboration_rate": (n_ok / n) if n else 0.0,
        "elapsed_s": round(elapsed, 1),
        "failures": fails,
    }
    out_path = out_dir / "statement_validation.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print(f"[validate] {config.data.benchmark}/{config.data.split}: "
          f"{n_ok}/{n} statements elaborate ({100 * n_ok / max(n, 1):.1f}%) in {elapsed:.0f}s")
    for r in fails[:15]:
        print(f"  FAIL {r['name']}: {r['error']}")
    if len(fails) > 15:
        print(f"  ... and {len(fails) - 15} more (see {out_path})")
    print(f"[validate] report -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
