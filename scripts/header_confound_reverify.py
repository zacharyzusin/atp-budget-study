"""External-calibration-sprint follow-up (DECISIONS.md 2026-07-25h) — the header-confound check.

The 2026-07-25 calibration cell recovered 6/55 Goedel x miniF2F trapped-core problems under plain
pass@32 resampling. A user retraction (2026-07-25h) found the trapped population was never
attempt-starved (~33 union proposals across the original 3 baseline seeds, near parity with the
cell's N=32) -- so sample count alone doesn't explain 6 new solves. The leading alternative
explanation is the calibration cell's OFFICIAL HEADER (`import Aesop` + `set_option maxHeartbeats 0`
in the PROMPT), compounding with the fact that `ReplBackend._build_repl_source` has UNCONDITIONALLY
injected `set_option maxHeartbeats 0` at VERIFY time for every run since the 2026-07-06 fix (Task B,
`results/audit/AUDIT_FINDINGS.md`) -- i.e. every solve in the calibration cell was already verified
under the lenient (fixed) heartbeat setting, same as the baseline's own post-fix reverify would be.

This script re-verifies the 6 recovered proofs' EXACT text under a simulated OLD verifier (no
`set_option maxHeartbeats` override at all -- Lean's own default heartbeat limit applies, the
pre-2026-07-06 behavior) to see which of the 6 are genuine sampling recoveries (still verify under
the strict default) vs. header/verifier-fix recoveries (only verify because of the lenient setting,
same root cause as Check B's 2 already-confirmed flips).

Usage (real Lean env required, same staging as scripts/audit_trapped_heartbeat_reverify.py):
    ATP_LEAN_PROJECT=/local/$USER/atp-lean-env python scripts/header_confound_reverify.py \
        --config configs/calibration_trapped32_goedel_minif2f.yaml \
        --run-dir results/calibration_trapped32_goedel_minif2f
"""
from __future__ import annotations

import argparse
import json
import os

RECOVERED = [
    "aime_1988_p8",
    "aime_1997_p9",
    "algebra_apbon2pownleqapownpbpowon2",
    "amc12a_2021_p8",
    "amc12b_2021_p18",
    "imo_1968_p5_1",
]


def _load_proof(agent_state_path: str) -> str | None:
    try:
        with open(agent_state_path) as f:
            d = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    return d.get("proof")


def build_old_header_backend(config, ReplBackend):
    """A ReplBackend that skips the maxHeartbeats override -- simulates the pre-2026-07-06 verifier."""

    class OldHeaderReplBackend(ReplBackend):
        def _build_repl_source(self, theorem, proof: str) -> str:  # noqa: N802 (match base signature)
            body_lines = [ln for ln in proof.splitlines() if not ln.lstrip().startswith("import ")]
            body = "\n".join(body_lines).strip("\n")
            from atp.lean.repl import _DECL_RE  # local import: avoid a hard dep at module load time

            if not _DECL_RE.search(body):
                body = theorem.statement.rstrip() + " := by\n" + body
            has_open = any(ln.lstrip().startswith("open ") for ln in body_lines)
            if theorem.opens and not has_open:
                body = "open " + " ".join(theorem.opens) + "\n" + body
            # Deliberately NOT injecting `set_option maxHeartbeats 0` -- this is the whole point.
            return body

    return OldHeaderReplBackend(config)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--run-dir", required=True)
    args = ap.parse_args()

    from atp.config import load_config
    from atp.data import load_dataset
    from atp.lean import ReplBackend, Verifier

    config = load_config(args.config)
    ds = load_dataset(config)
    problems = ds.problems if hasattr(ds, "problems") else ds
    theorem_by_name = {p.name: p.to_theorem() for p in problems}

    agent_states_dir = os.path.join(args.run_dir, "agent_states")

    current_backend = ReplBackend(config)
    current_verifier = Verifier.from_config(config, current_backend)

    old_backend = build_old_header_backend(config, ReplBackend)
    old_verifier = Verifier.from_config(config, old_backend)

    results = []
    for name in RECOVERED:
        theorem = theorem_by_name.get(name)
        if theorem is None:
            print(f"[header-confound] SKIP {name}: not found in dataset")
            continue
        proof = _load_proof(os.path.join(agent_states_dir, f"{name}__seed0.json"))
        if not proof:
            print(f"[header-confound] SKIP {name}: no recorded proof")
            continue

        current = current_verifier.verify(theorem, proof)
        old = old_verifier.verify(theorem, proof)
        row = {
            "name": name,
            "verifies_current_lenient_heartbeat": bool(current.ok),
            "verifies_old_default_heartbeat": bool(old.ok),
            "header_dependent": bool(current.ok and not old.ok),
        }
        results.append(row)
        tag = "HEADER-DEPENDENT (old verifier rejects)" if row["header_dependent"] else "genuine (verifies under old default too)"
        print(f"[header-confound] {name}: current={current.ok} old={old.ok} -> {tag}", flush=True)

    n_header_dependent = sum(1 for r in results if r["header_dependent"])
    print(f"\n[header-confound] FINAL: {n_header_dependent}/{len(results)} of the 6 recoveries are "
          "header/verifier-fix dependent (fail under the pre-2026-07-06 default heartbeat setting).")

    out_path = os.path.join(args.run_dir, "header_confound_result.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"[header-confound] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
