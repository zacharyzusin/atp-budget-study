"""AUDIT_PLAN.md Task A1 Step 3 (extended): does verifier.py's `no_goal` gate check the wrong
operand for continuation-style templates, and if so, does the real Lean REPL ever accept a
reconstructed source whose extracted `proof` text has no declaration and no real tactics?

`Verifier.verify(theorem, proof)` runs `not _DECL_RE.search(proof)` on the RAW EXTRACTED proof
string, but the backend (`ReplBackend._build_repl_source`) reconstructs a full declaration around
`proof` for continuation-style templates before compiling. So the gate is checking the wrong
string for those templates by construction. This script:

  1. Confirms the mismatch exists (pure Python, no Lean).
  2. Feeds a REAL comment-only "proof" (the exact shape recorded in
     results/p8battery2_leanabell_gdrl_proofnet's no_goal attempts) through the REAL Lean REPL to
     see what the backend actually returns — is it a genuine accept (env, no messages), or does
     Lean legitimately error and `no_goal` is reached only via a route that doesn't matter (i.e.
     coincides with what compile_error would have produced anyway)?
  3. Feeds a real, CORRECT continuation-style proof (bare tactics that actually solve a trivial
     goal, no theorem line) through the real backend, bypassing the Verifier's no_goal gate by
     calling backend.verify directly, to see whether the underlying Lean accept is genuine — i.e.
     whether the `no_goal` gate could ever suppress a TRUE POSITIVE.

Run directly (not pytest) against a real built env:
    ATP_LEAN_ENV_DIR=/local/zwz2000/atp-lean-env python scripts/audit_no_goal_gate_check.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from atp.config import BASE_CONFIG, load_config  # noqa: E402
from atp.lean.backends import Theorem  # noqa: E402
from atp.lean.repl import ReplBackend  # noqa: E402
from atp.lean.verifier import Verifier  # noqa: E402


def main() -> None:
    env_dir = os.environ.get("ATP_LEAN_ENV_DIR")
    if not env_dir:
        raise SystemExit("set ATP_LEAN_ENV_DIR to the staged env (e.g. /local/$USER/atp-lean-env)")

    cfg = load_config(BASE_CONFIG)
    backend = ReplBackend(cfg, project_path=env_dir)
    if not backend._env_built():
        raise SystemExit(f"env not built at {env_dir}")

    verifier = Verifier(backend)

    print("=" * 70)
    print(
        "CASE 1: comment-only 'proof' (the exact recorded p8battery2_leanabell_gdrl_proofnet shape)"
    )
    print("=" * 70)
    thm1 = Theorem(
        name="exercise_5_7",
        statement=(
            "theorem exercise_5_7 {f g : ℝ → ℝ} {x : ℝ}\n"
            "  (hf : DifferentiableAt ℝ f x) (hg : DifferentiableAt ℝ g x) : True"
        ),
    )
    comment_only_proof = (
        "-- We need to show that the limit of the function \\( f(t) / g(t) \\) as \\( t \\) "
        "approaches \\( x \\) is \\( \\frac{f'(x)}{g'(x)} \\).\n"
        "  -- Given that \\( f \\) and \\( g \\) are differentiable"
    )
    src1 = backend._build_repl_source(thm1, comment_only_proof)
    print("--- reconstructed source ---")
    print(src1)
    raw1 = backend.verify(thm1, comment_only_proof)
    print(f"--- backend.verify raw result: success={raw1.success} output={raw1.output!r} ---")
    res1 = verifier.verify(thm1, comment_only_proof)
    print(f"--- Verifier.verify: ok={res1.ok} reason={res1.reason} ---")
    print()

    print("=" * 70)
    print("CASE 2: a REAL, CORRECT continuation-style bare-tactic proof (no theorem/lemma line)")
    print("=" * 70)
    thm2 = Theorem(name="triv2", statement="theorem triv2 : True")
    bare_correct_proof = (
        "  trivial"  # what DeepSeekV15Template extraction produces for a trivial goal
    )
    src2 = backend._build_repl_source(thm2, bare_correct_proof)
    print("--- reconstructed source ---")
    print(src2)
    raw2 = backend.verify(thm2, bare_correct_proof)
    print(f"--- backend.verify raw result: success={raw2.success} output={raw2.output!r} ---")
    res2 = verifier.verify(thm2, bare_correct_proof)
    print(f"--- Verifier.verify: ok={res2.ok} reason={res2.reason} feedback={res2.feedback!r} ---")
    print()
    if raw2.success and not res2.ok and res2.reason == "no_goal":
        print(
            "*** CONFIRMED BUG: backend genuinely ACCEPTED a correct continuation-style proof, "
            "but Verifier.verify rejected it as no_goal because it checks the wrong operand. ***"
        )
    elif raw2.success and res2.ok:
        print("No bug on this case: Verifier correctly scored a genuinely-accepted proof as ok.")
    else:
        print(
            f"Backend itself did not accept the bare proof (success={raw2.success}) -- "
            "no_goal-gate question is moot for this case; investigate the raw output above."
        )


if __name__ == "__main__":
    main()
