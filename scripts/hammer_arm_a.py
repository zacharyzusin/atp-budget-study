#!/usr/bin/env python3
"""Hammer probe Arm A-lite — symbolic closer at the model's STUCK LEAF, in-context, no new infra.

For each trapped problem, take the model's deepest attempt and replace its single FAILING tactic (the one
the trace blames: 'Failed at step N (`<text>`)') with the portfolio combinator, keeping the rest of the
proof identical. If the modified full proof verifies, a symbolic closer discharged the leaf the model was
stuck at — the synergy signal. Sound (fixed verifier gates; sorry/admit/native_decide rejected). Recall-
lossy where the blamed tactic isn't a clean closing leaf (counts as 'no'), never a false positive.

Usage: python scripts/hammer_arm_a.py --config configs/proofnet_baseline.yaml \
         --run results/proofnet_baseline --trapped scratch/phase2/trapped_proofnet.txt --limit 30 --out OUT
"""
import argparse, glob, json, os, re, sys

CLOSER = "first | omega | nlinarith | norm_num | simp_all | decide | aesop"
_STEP = re.compile(r"Failed at step\s+(\d+)\s+\(`(.+?)`\)", re.DOTALL)

def deepest_failing(run_dir, name):
    """Return (full_proof, failing_tactic_text) for the globally deepest attempt of this problem."""
    best, best_step = None, -1
    for f in sorted(glob.glob(os.path.join(run_dir, "agent_states", f"{name}__seed*.json"))):
        try: d = json.load(open(f))
        except (json.JSONDecodeError, ValueError): continue
        for a in d.get("attempts", []):
            if a.get("reason") == "ok" or not a.get("proof"):
                continue
            m = _STEP.search(a.get("feedback") or "")
            if not m:
                continue
            step = int(m.group(1))
            if step > best_step:
                best, best_step = (a["proof"], m.group(2).strip()), step
    return best

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--trapped", required=True)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    sys.path.insert(0, "src")
    from atp.config import load_config
    from atp.lean import ReplBackend, Theorem

    config = load_config(a.config)
    names = [l.strip() for l in open(a.trapped) if l.strip()]
    if a.limit: names = names[: a.limit]
    env_dir = os.environ.get("ATP_LEAN_PROJECT") or os.environ.get("ATP_LEAN_ENV_DIR")
    backend = ReplBackend(config, project_path=env_dir) if env_dir else ReplBackend(config)

    results = []; n_closed = 0; n_probed = 0
    for i, nm in enumerate(names):
        df = deepest_failing(a.run, nm)
        if not df:
            results.append({"name": nm, "status": "no_failing_tactic"}); continue
        proof, fail_tac = df
        if fail_tac not in proof:
            results.append({"name": nm, "status": "tactic_not_located"}); continue
        n_probed += 1
        modified = proof.replace(fail_tac, f"({CLOSER})", 1)
        header = proof[: re.search(r":=\s*by\b", proof).end()] if re.search(r":=\s*by\b", proof) else proof
        rv = backend.verify(Theorem(name=nm, statement=header.rsplit(":=", 1)[0].strip()), modified)
        closed = bool(rv.success)
        n_closed += closed
        results.append({"name": nm, "status": "CLOSED" if closed else "no",
                        "failing_tactic": fail_tac[:80]})
        print(f"[{i+1}/{len(names)}] {nm}: {'CLOSED (leaf swapped for portfolio)' if closed else 'no'}"
              f"  [stuck on: {fail_tac[:60]}]", flush=True)

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump({"arm": "A-lite (failing-tactic -> portfolio, in-context)", "run": a.run,
               "n_problems": len(names), "n_probed": n_probed, "n_closed": n_closed,
               "closer": CLOSER, "results": results}, open(a.out, "w"), indent=2)
    print(f"\nARM A-lite: {n_closed}/{n_probed} probed ({len(names)} trapped) closed by portfolio-at-leaf -> {a.out}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
