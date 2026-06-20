#!/usr/bin/env python3
"""Hammer probe — extract, per trapped problem, the statement + the model's deepest valid-prefix 'stuck
leaf' from existing traces. CPU-only, no REPL. Output feeds the on-pin arm runners.

For each trapped problem (unsolved by all seeds @128k), pick the attempt that reached the deepest step
(F3), then:
  - statement  = the theorem header up to and including ':= by' (for Arm 0 / Arm B).
  - prefix     = the proof-body tactic lines BEFORE the failing step N (from 'Failed at step N'); this is
                 the longest cleanly-applying prefix candidate -> its open goal is the 'stuck leaf' (Arm A).
The candidate 'statement := by <prefix>\n <closer>' is verified on-pin by the runner; a mis-parsed prefix
just fails to compile (costs recall, never soundness — the fixed verifier gates).
"""
import json, os, re

_STEP = re.compile(r"Failed at step\s+(\d+)")

def _split_header_body(proof: str):
    m = re.search(r":=\s*by\b", proof)
    if not m:
        return None, None
    return proof[:m.end()], proof[m.end():]

def _body_lines(body: str):
    # tactic lines as the trace tokenizer sees them: split on newlines, keep non-blank non-comment
    out = []
    for raw in body.split("\n"):
        s = raw.rstrip()
        if s.strip() and not s.strip().startswith("--"):
            out.append(s)
    return out

def deepest_attempt(state: dict):
    best, best_step = None, -1
    for a in state.get("attempts", []):
        if a.get("reason") == "ok":
            continue
        m = _STEP.search(a.get("feedback") or "")
        step = int(m.group(1)) if m else 0
        if step > best_step and a.get("proof"):
            best, best_step = a, step
    return best, best_step

def extract_for_problem(run_dir: str, name: str):
    """Across seeds, return {statement, prefix_lines, stuck_step, seed} for the globally deepest attempt."""
    best = None
    for f in sorted(__import__("glob").glob(os.path.join(run_dir, "agent_states", f"{name}__seed*.json"))):
        try:
            d = json.load(open(f))
        except (json.JSONDecodeError, ValueError):
            continue
        a, step = deepest_attempt(d)
        if a and (best is None or step > best["stuck_step"]):
            header, body = _split_header_body(a["proof"])
            if header is None:
                continue
            lines = _body_lines(body)
            prefix = lines[:step] if step > 0 else []   # steps 0..N-1 applied; N failed
            best = {"name": name, "statement": header, "prefix_lines": prefix,
                    "stuck_step": step, "n_body_lines": len(lines),
                    "seed": int(re.search(r"seed(\d+)", os.path.basename(f)).group(1))}
    return best

if __name__ == "__main__":
    import argparse, glob
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("trapped_file")
    ap.add_argument("--n", type=int, default=5)
    a = ap.parse_args()
    names = [l.strip() for l in open(a.trapped_file) if l.strip()][: a.n]
    for nm in names:
        e = extract_for_problem(a.run_dir, nm)
        if not e:
            print(f"\n### {nm}: NO extractable attempt"); continue
        print(f"\n### {nm}  (deepest stuck_step={e['stuck_step']} of {e['n_body_lines']} body lines, seed{e['seed']})")
        print(f"STATEMENT: {e['statement'][:200]}")
        print(f"PREFIX ({len(e['prefix_lines'])} lines):")
        for ln in e["prefix_lines"][:12]:
            print(f"   {ln[:120]}")
