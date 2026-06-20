#!/usr/bin/env python3
"""H1 — recompute the cross-model dichotomy on the compile-on-both-pins INTERSECTION.

Both models attempted the IDENTICAL canonical statement sets (244 miniF2F, 186 ProofNet#; verified:
0 disjoint problem names). The only way native-port pass@B could be a coverage artifact is if a statement
elaborates on one pin but not the other (-> auto-0 on that side). So the intersection per benchmark =
all problems MINUS (Goedel-pin failures  UNION  DeepSeek-pin failures), read from each pin's
statement_validation.json. We then recompute pass@B for BOTH models restricted to the intersection and
compare to the native-port numbers (which must reproduce metrics.json as a self-check).

pass@B convention (matches src/atp/eval/metrics.py): mean over seeds of the fraction of problems with
solved & tokens_to_solve <= B.
"""
import glob, json, os, statistics as st, sys

BUDGETS = [2000, 8000, 32000, 128000]

def failures(path):
    if not os.path.exists(path):
        return None
    d = json.load(open(path))
    return set(f["name"] if isinstance(f, dict) else f for f in d.get("failures", [])), d

def load_cells(run_dir):
    """(problem, seed) -> (solved, tokens_to_solve)."""
    cells = []
    for f in glob.glob(os.path.join(run_dir, "problems", "*.json")):
        d = json.load(open(f))
        cells.append((d["problem_name"], d["seed"], bool(d["solved"]), d.get("tokens_to_solve")))
    return cells

def pass_at_b(cells, names, budgets=BUDGETS):
    """names=None -> all. Returns {b: (mean, std, n_problems)} over seeds."""
    by_seed = {}
    for name, seed, solved, tts in cells:
        if names is not None and name not in names:
            continue
        by_seed.setdefault(seed, []).append((solved, tts))
    out = {}
    n_problems = max((len(v) for v in by_seed.values()), default=0)
    for b in budgets:
        fr = [sum(1 for s, t in rs if s and t is not None and t <= b) / len(rs)
              for rs in by_seed.values() if rs]
        out[b] = (round(100 * st.fmean(fr), 1) if fr else 0.0,
                  round(100 * (st.stdev(fr) if len(fr) >= 2 else 0.0), 1), n_problems)
    return out

ARMS = [
    ("miniF2F",   "Goedel",   "results/baseline",                  "results/minif2f/statement_validation.json"),
    ("miniF2F",   "DeepSeek", "results/deepseek_minif2f_baseline", "results/phase2/deepseek/statement_validation/minif2f_deepseekpin.json"),
    ("ProofNet#", "Goedel",   "results/proofnet_baseline",         "results/proofnet_sharp/statement_validation.json"),
    ("ProofNet#", "DeepSeek", "results/deepseek_proofnet_baseline","results/phase2/deepseek/statement_validation/proofnet_deepseekpin.json"),
]

# per-benchmark intersection = full set - union of both pins' failures
fails = {}
for bench, model, run, valpath in ARMS:
    fv = failures(valpath)
    if fv is None:
        print(f"!! missing validation file (pin not yet validated): {valpath}")
        continue
    fset, meta = fv
    fails.setdefault(bench, set())
    fails[bench] |= fset
    print(f"[validate] {bench:9s} {model:8s} pin={meta.get('lean_toolchain')} "
          f"mathlib={(meta.get('mathlib_commit') or '')[:10]} "
          f"elaborated={meta.get('n_elaborated')}/{meta.get('n_problems')} failures={len(fset)}")

print()
for bench, model, run, _ in ARMS:
    cells = load_cells(run)
    allnames = set(c[0] for c in cells)
    excl = fails.get(bench, set())
    inter = allnames - excl
    native = pass_at_b(cells, None)
    isect = pass_at_b(cells, inter)
    print(f"===== {bench} · {model}  (full={len(allnames)}  excluded={len(excl)}  intersection={len(inter)}) =====")
    print("        budget |   native (n)   | intersection (n)")
    for b in BUDGETS:
        nm, ns, nn = native[b]; im, isd, ino = isect[b]
        print(f"      {b:7d} | {nm:5.1f}±{ns:<4.1f}({nn}) | {im:5.1f}±{isd:<4.1f}({ino})")
    print()
