#!/usr/bin/env python3
"""Hammer probe Arm 0 (+ Arm B if a hammer tactic is given) on ORIGINAL trapped statements — on-pin,
no goal extraction needed. For each trapped problem, try each closer tactic as `<stmt> := by <closer>`
and record the first that VERIFIES (fixed verifier; sorry/admit/native_decide rejected by policy).

Arm 0 = the basic portfolio (controls for "model didn't invoke available automation"). Pass extra
closers via --closers to add a hammer (Arm B) once one is built on-pin.

Usage: python scripts/hammer_arm0.py --config configs/proofnet_baseline.yaml \
          --trapped scratch/phase2/trapped_proofnet.txt --limit 30 --out results/phase3/arm0_goedel_proofnet.json
"""
import argparse, json, os, sys, time

PORTFOLIO = [
    "omega", "nlinarith", "norm_num", "simp_all", "decide", "aesop",
    "first | omega | nlinarith | norm_num | simp_all | decide | aesop",
]

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--trapped", required=True)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--closers", nargs="*", default=PORTFOLIO)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    sys.path.insert(0, "src")
    from atp.config import load_config
    from atp.data import load_dataset
    from atp.data.contamination import load_novel_names
    from atp.lean import ReplBackend

    config = load_config(a.config)
    trapped = set(l.strip() for l in open(a.trapped) if l.strip())
    # load full split, restrict to trapped names
    ds = load_dataset(config)
    probs = [p for p in ds.problems if p.name in trapped]
    if a.limit:
        probs = probs[: a.limit]

    env_dir = os.environ.get("ATP_LEAN_PROJECT") or os.environ.get("ATP_LEAN_ENV_DIR")
    backend = ReplBackend(config, project_path=env_dir) if env_dir else ReplBackend(config)

    if os.environ.get("HAMMER_SELFTEST"):
        # positive control: portfolio MUST close these trivial goals, else the probe is silently broken
        from atp.lean import Theorem
        ctrl = [("ctl_normnum", "theorem ctl_normnum : (2 : ℕ) + 2 = 4", "norm_num"),
                ("ctl_simp", "theorem ctl_simp (n : ℕ) : n + 0 = n", "simp"),
                ("ctl_omega", "theorem ctl_omega (n : ℕ) : n ≤ n + 1", "omega"),
                ("ctl_port", "theorem ctl_port : (3 : ℤ) < 5", PORTFOLIO[-1])]
        allok = True
        for nm, stmt, c in ctrl:
            rv = backend.verify(Theorem(name=nm, statement=stmt), f"{stmt} := by {c}")
            print(f"[selftest] {nm} `{c}`: {'PASS' if rv.success else 'FAIL — '+rv.output[:120]}")
            allok = allok and rv.success
        print(f"[selftest] {'ALL PASS — probe fires correctly' if allok else 'BROKEN'}")
        return 0 if allok else 3

    results = []; n_closed = 0
    for i, p in enumerate(probs):
        thm = p.to_theorem()
        closed_by = None
        for c in a.closers:
            t0 = time.time()
            rv = backend.verify(thm, f"{thm.statement} := by {c}")
            if rv.success:
                closed_by = c
                break
        results.append({"name": p.name, "closed": closed_by is not None, "closer": closed_by})
        if closed_by:
            n_closed += 1
        print(f"[{i+1}/{len(probs)}] {p.name}: {'CLOSED by `'+closed_by+'`' if closed_by else 'no'}", flush=True)

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    report = {"config": a.config, "trapped_file": a.trapped, "n_problems": len(probs),
              "n_closed": n_closed, "closer_list": a.closers, "results": results}
    json.dump(report, open(a.out, "w"), indent=2)
    print(f"\nARM 0: {n_closed}/{len(probs)} trapped problems closed by the portfolio -> {a.out}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
