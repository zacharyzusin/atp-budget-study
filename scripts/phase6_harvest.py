#!/usr/bin/env python3
"""Phase 6 Task 6.1: build the SFT datasets from a generation run on the clean Lean Workbook corpus.

Input: a generation run dir (produced by sweeping configs/phase6_harvest_<model>.yaml — the prover
run on the decontaminated corpus). Outputs two datasets + a summary:
  - rft.jsonl              : {name, statement, proof} for every VERIFIED whole proof (RFT/STaR pool)
  - closing_targets.jsonl  : {name, deep_state, closing, k, n_groups, proof} — the closing-targeted
                             pairs (Stage B novel ingredient). For each verified TACTIC-mode proof
                             we truncate at deep top-level boundaries, elaborate `<prefix> … sorry`
                             in Lean, and keep candidates that cleanly hit EXACTLY ONE sorry goal
                             (the `deep_state`). Re-verifies by construction (full proof verified).
  - harvest_summary.json   : base solve rate, #RFT, #closing pairs, candidate->valid rate.

Needs the built Lean env (REPL) for the closing-target elaboration — CPU + Lean, NO GPU.

Usage:
  python scripts/phase6_harvest.py --config configs/phase6_harvest_goedel.yaml \
      --run-dir results/phase6_harvest_goedel --out-dir scratch/phase6/sft/goedel
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from atp.agents.state import AgentState
from atp.config import load_config
from atp.data import load_dataset
from atp.data.closing_targets import closing_truncations
from atp.lean.backends import Theorem

ROOT = Path(__file__).resolve().parents[1]


def collect_verified_proofs(run_dir: str | Path) -> list[tuple[str, str]]:
    """(name, proof) for every solved cell in `run_dir/agent_states` (pure; no Lean)."""
    states = Path(run_dir) / "agent_states"
    out: list[tuple[str, str]] = []
    for fp in sorted(states.glob("*.json")):
        st = AgentState.load(fp)
        if st is not None and st.solved and st.proof:
            out.append((st.theorem_name, st.proof))
    return out


def _depth_interleave(cands: list) -> list:
    """Order candidates so depth-diverse ones come first: depth1 (nested, deep goal-closing — the
    on-mechanism prize) and depth0 (top-level last-mile closings) alternate. With a small
    `max_per_proof` this keeps a MIX per proof rather than all-shallow (depth0 is emitted first
    upstream, so without this a 2-cap would drop every nested closing)."""
    d1 = [c for c in cands if c.depth == 1]
    d0 = [c for c in cands if c.depth == 0]
    out: list = []
    for a, b in zip(d1, d0, strict=False):
        out.extend((a, b))
    longer = d1 if len(d1) > len(d0) else d0
    out.extend(longer[min(len(d1), len(d0)):])
    return out


def build_closing_targets(proofs, by_name, backend, *, max_per_proof: int = 2) -> tuple[list, dict]:
    """Elaborate truncation candidates; keep clean single-sorry ones as (deep_state, closing)."""
    pairs: list[dict] = []
    n_cand = n_valid = n_tactic_proofs = n_d1 = 0
    for name, proof in proofs:
        cands = _depth_interleave(closing_truncations(proof))
        if cands:
            n_tactic_proofs += 1
        prob = by_name.get(name)
        opens = tuple(prob.opens) if prob is not None else ()
        thm = Theorem(name=name, statement=(prob.statement if prob else name), opens=opens)
        kept = 0
        for c in cands:
            if kept >= max_per_proof:
                break
            n_cand += 1
            res = backend.elaborate(thm, c.prefix_with_sorry)
            if res["infra_error"] or res["errors"] != 0 or len(res["sorries"]) != 1:
                continue
            n_valid += 1
            kept += 1
            n_d1 += int(c.depth == 1)
            pairs.append({"name": name, "deep_state": res["sorries"][0], "closing": c.closing,
                          "k": c.k, "n_groups": c.n_groups, "depth": c.depth,
                          "cont_prefix": c.cont_prefix, "cont_target": c.cont_target,
                          "proof": proof})
    stats = {"n_tactic_proofs": n_tactic_proofs, "n_candidates": n_cand,
             "n_valid_pairs": n_valid, "n_nested_pairs": n_d1,
             "candidate_valid_rate": (n_valid / n_cand) if n_cand else 0.0}
    return pairs, stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--max-per-proof", type=int, default=2)
    ap.add_argument("--skip-closing", action="store_true",
                    help="build only the RFT set (no Lean/REPL needed)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    ds = load_dataset(cfg, model_revision=cfg.model.revision)
    by_name = {p.name: p for p in ds.problems}
    n_total = len(ds.problems)

    proofs = collect_verified_proofs(args.run_dir)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    rft = [{"name": n, "statement": (by_name[n].statement if n in by_name else ""), "proof": p}
           for n, p in proofs]
    (out / "rft.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rft))

    summary = {
        "config": args.config, "run_dir": args.run_dir,
        "n_problems": n_total, "n_solved": len(proofs),
        "base_solve_rate": (len(proofs) / n_total) if n_total else 0.0,
        "n_rft": len(rft),
    }

    if not args.skip_closing and proofs:
        from atp.lean.repl import ReplBackend
        backend = ReplBackend(cfg)
        try:
            pairs, stats = build_closing_targets(proofs, by_name, backend,
                                                 max_per_proof=args.max_per_proof)
        finally:
            backend.close()
        (out / "closing_targets.jsonl").write_text(
            "\n".join(json.dumps(p, ensure_ascii=False) for p in pairs))
        summary.update({"n_closing_pairs": len(pairs), **stats})

    (out / "harvest_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"[harvest] solved {summary['n_solved']}/{summary['n_problems']} "
          f"(base solve rate {summary['base_solve_rate']:.3f}); RFT={summary['n_rft']}; "
          f"closing_pairs={summary.get('n_closing_pairs', '(skipped)')}")
    print(f"[harvest] wrote {out}/rft.jsonl + closing_targets.jsonl + harvest_summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
