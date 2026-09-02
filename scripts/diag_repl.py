"""Diagnostic: capture the RAW leanprover-community/repl response for real proofs.

The Phase-0 smoke rejected EVERY real proof with "Proof rejected (no parseable error)" — the
Verifier's fallback when `raw.success` is False but no Lean error line was parsed. The only code
path
that produces that is the generic `except Exception` in ReplBackend.verify (output = "<Err>: ...",
which parse_lean_output can't read). This script calls the transport DIRECTLY (bypassing verify's
try/except) so the raw response dict — or the raw exception — is visible, for:
  (a) the trivial probe proof (known-good framing),
  (b) a short multi-line `have` proof,
  (c) the exact attempt0 proof from the smoke (mathd_algebra_182) that was wrongly rejected.

Run on a node with the env staged to local SSD and ATP_LEAN_PROJECT pointing at it (see the slurm
wrapper). Prints, per proof: the raw response (or exception), then _format_response +
parse_lean_output
so we see exactly where the verdict diverges.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from atp.config import load_config
from atp.lean.backends import Theorem
from atp.lean.errors import parse_lean_output
from atp.lean.repl import ReplBackend

PROOF_A = "theorem probe : True := by\n  trivial"

PROOF_B = (
    "theorem hav (y : ℂ) : 7 * (3 * y + 2) = 21 * y + 14 := by\n"
    "  have h : 7 * (3 * y + 2) = 21 * y + 14 := by ring\n"
    "  exact h"
)


def _attempt0_proof() -> str | None:
    p = Path("results/smoke/agent_states/mathd_algebra_182__seed0.json")
    if not p.exists():
        return None
    d = json.loads(p.read_text())
    return d["attempts"][0]["proof"]


def main() -> int:
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "configs/smoke.yaml")
    backend = ReplBackend(cfg)
    print(f"[diag] project_path={backend.project_path}")
    t0 = time.time()
    backend._ensure_started()  # noqa: SLF001 - diagnostic
    print(f"[diag] base env loaded in {time.time()-t0:.0f}s (env={backend._base_env})")  # noqa: SLF001
    transport = backend._transport  # noqa: SLF001
    assert transport is not None

    cases = [("probe_true", PROOF_A), ("short_have", PROOF_B)]
    a0 = _attempt0_proof()
    if a0:
        cases.append(("smoke_attempt0", a0))

    for name, proof in cases:
        thm = Theorem(name=name, statement="")
        source = backend._build_repl_source(thm, proof)  # noqa: SLF001
        print("\n" + "=" * 70)
        print(f"[case] {name}  (source {len(source)} chars, {source.count(chr(10))+1} lines)")
        cmd = {"cmd": source, "env": backend._base_env}  # noqa: SLF001
        t = time.time()
        try:
            raw = transport.request(cmd, float(cfg.lean.verify_timeout_s))
            dt = time.time() - t
            keys = list(raw.keys())
            print(f"  RAW OK in {dt:.1f}s | keys={keys}")
            print(f"  raw (first 1200 chars): {json.dumps(raw)[:1200]}")
            success, output = backend._format_response(thm, raw)  # noqa: SLF001
            parsed = parse_lean_output(output)
            print(f"  _format_response -> success={success}")
            print(f"  output (first 500): {output[:500]!r}")
            print(f"  parsed.has_error={parsed.has_error} n_msgs={len(parsed.messages)} "
                  f"earliest={parsed.earliest_error}")
        except Exception as exc:  # noqa: BLE001 - the whole point is to see it
            dt = time.time() - t
            print(f"  !! EXCEPTION in {dt:.1f}s: {type(exc).__name__}: {exc}")

    # --- Stateful replay: feed the smoke's real attempt sequence through ONE verify() ---------
    # Reproduces the production path (the "no parseable error" started at global verify #3). The
    # except-path in verify() folds the exception into raw.output, so we print it here.
    print("\n" + "#" * 70)
    print("[replay] feeding smoke attempts through ONE ReplBackend.verify() in order")
    from atp.lean.verifier import Verifier  # noqa: PLC0415

    verifier = Verifier.from_config(cfg, backend)
    order = ["amc12a_2019_p21", "amc12a_2015_p10", "amc12a_2008_p8"]
    gi = 0
    for name in order:
        sp = Path(f"results/smoke/agent_states/{name}__seed0.json")
        if not sp.exists():
            continue
        st = json.loads(sp.read_text())
        for at in st["attempts"]:
            proof = at.get("proof") or ""
            t = time.time()
            res = verifier.verify(Theorem(name=name, statement=""), proof)
            dt = time.time() - t
            tag = "OK" if res.ok else res.reason
            fb = res.feedback[:90].replace("\n", " ")
            print(f"  #{gi:02d} {name[:18]:18s} a{at['index']:02d} {dt:5.1f}s -> {tag:13s} | {fb}")
            if "no parseable" in res.feedback:
                print(f"      RAW OUTPUT (the exception): {res.raw_output[:400]!r}")
            gi += 1
            if gi >= 12:
                break
        if gi >= 12:
            break
    backend.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
