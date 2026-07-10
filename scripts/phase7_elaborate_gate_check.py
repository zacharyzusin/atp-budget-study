#!/usr/bin/env python3
"""Phase 7 Track 1 — sanity-check the Mode 3 `elaborate` boundary gate on REAL Lean (CPU-only).

The smoke run (11110019/11110049) showed the gate correctly REJECTS a dangling prefix, but a smoke
that only ever rejects is equally consistent with a bug that rejects EVERYTHING (vacuous rejection).
This directly tests the ACCEPT path too, reusing an already-verified Stage B proof
(`closing_targets.jsonl`, whose truncations were themselves validated offline by the same
elaborate+sorry check during the Phase 6 harvest) so a known-good prefix is expected to validate,
and a deliberately-truncated dangling prefix of the SAME proof is expected to be rejected — both
through the EXACT `elaborate` wrapper `phase7_stepwise_run.py` wires into `RegroundStepwiseAgent`.
"""

from __future__ import annotations

import json
import sys

from atp.config import load_config
from atp.data.closing_targets import closing_truncations
from atp.lean.backends import Theorem
from atp.lean.repl import ReplBackend


def check(theorem: Theorem, prefix: str, backend: ReplBackend) -> bool:
    src = f"{theorem.statement.rstrip()} := by\n{prefix}\n  sorry"
    resp = backend.elaborate(theorem, src)
    ok = (not resp["infra_error"]) and resp["errors"] == 0 and len(resp["sorries"]) == 1
    print(f"  errors={resp['errors']} n_sorries={len(resp['sorries'])} "
          f"infra_error={resp['infra_error']} -> {'ACCEPT' if ok else 'reject'}")
    return ok


def main() -> int:
    config = load_config(sys.argv[1] if len(sys.argv) > 1 else "configs/proofnet_baseline.yaml")
    backend = ReplBackend(config)

    row = json.loads(open("scratch/phase6/sft/goedel/closing_targets.jsonl").readline())
    proof = row["proof"]
    marker = ":= by"
    idx = proof.find(marker)
    assert idx != -1, "expected a `:= by` in the harvested proof"
    statement = proof[:idx].rstrip()
    theorem = Theorem(name=row["name"], statement=statement)

    # A KNOWN-VALID prefix: `closing_truncations` is the SAME logic Stage B's harvest used to find
    # clean, non-trivial, non-dangling cut points (it filters `_is_trivial_closing` /
    # `_closing_is_dangling` before returning candidates) — reuse it rather than guess a line number
    # (the first naive attempt at this script picked a proof's own first line, which happened to
    # itself be a dangling `have ... := by` opener — the SAME failure mode, not a real acceptance
    # test; this is the fix).
    candidates = closing_truncations(proof)
    assert candidates, f"no non-trivial/non-dangling truncation found for {row['name']!r}"
    valid_prefix = candidates[0].cont_prefix
    print(f"[gate-check] {row['name']}: {len(candidates)} valid candidates available")
    print(f"[gate-check] (a) valid prefix (from closing_truncations): ...{valid_prefix[-80:]!r}")
    accepted = check(theorem, valid_prefix, backend)

    # (b) a DELIBERATELY DANGLING prefix: append a fresh, unclosed `have ... := by` after the SAME
    # valid prefix — the exact real failure mode from the smoke (a `have` opener with no sub-proof).
    dangling_prefix = f"{valid_prefix}\n  have __gate_check_dangling : True := by"
    print(f"[gate-check] (b) dangling prefix: ...{dangling_prefix[-70:]!r}")
    rejected = not check(theorem, dangling_prefix, backend)

    print(f"[gate-check] RESULT: valid-accepted={accepted} dangling-rejected={rejected}")
    if accepted and rejected:
        print("[gate-check] PASS — the gate discriminates both ways, not vacuous.")
        return 0
    print("[gate-check] FAIL — the gate is not discriminating correctly.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
