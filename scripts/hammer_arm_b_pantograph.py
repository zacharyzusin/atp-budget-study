#!/usr/bin/env python3
"""Off-pin Arm B — a REAL hammer (duper) on the trapped ProofNet# STATEMENTS, via Pantograph on the
sibling v4.29.0 mathlib stack. This is the cheap decisive test the reviewer asked for: the portfolio
(Arm 0) is the automation the model already calls inline; duper is a genuine superposition ATP that
reasons beyond it. No proofState extraction (that's Arm A), no v4.9.0 port.

Per statement: load_sorry("<opens> in <stmt> := by sorry") -> initial goal; apply `duper` (timed);
closed iff no remaining goals. Elaboration falls out per-statement (no batch-file name collisions).
Sound: duper reconstructs kernel-checked proofs. Records elaborated / closed per problem.

Env: run under the sibling venv (PyPantograph 0.3.15) with project_path pointing at a lean_env that has
Duper built in, imports=["Mathlib","Duper"].
"""
import argparse, json, os, sys, time

# opens: the dataset's ProofNet opens + the namespaces the v4.29 drift analysis showed are needed
OPENS = ("Function Fintype Subgroup Ideal Polynomial Submodule BigOperators "
         "Filter Set Topology Real Module Metric Finset Complex")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--statements", required=True, help="json: {name: statement}")
    ap.add_argument("--project", required=True, help="lean_env (with Duper built) path")
    ap.add_argument("--out", required=True)
    ap.add_argument("--tactic", default="duper", help="closer tactic (duper / 'duper [*]' / hammer)")
    ap.add_argument("--timeout", type=int, default=90)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()

    from pantograph import Server
    stmts = json.load(open(a.statements))
    items = list(stmts.items())[: a.limit] if a.limit else list(stmts.items())

    def start():
        t0 = time.time()
        s = Server(imports=["Mathlib", "Duper"], project_path=a.project, timeout=a.timeout)
        print(f"[armB] server (re)started in {time.time()-t0:.0f}s", flush=True)
        return s

    print(f"[armB] starting Pantograph: project={a.project} imports=Mathlib,Duper timeout={a.timeout}", flush=True)
    server = start()

    results = []; n_elab = 0; n_closed = 0
    for i, (name, stmt) in enumerate(items):
        src = f"open {OPENS} in\n{stmt} := by sorry"
        rec = {"name": name, "elaborated": False, "closed": False, "err": ""}
        # up to 2 attempts: a duper call can crash the Lean server, after which load_sorry asserts.
        # Restart the server and retry THIS statement once; if it crashes again, record + move on.
        for attempt in (1, 2):
            try:
                units = server.load_sorry(src)
                states = [u.goal_state for u in units if getattr(u, "goal_state", None)] if units else []
                if not states:
                    rec["err"] = "no_goal_state"; break
                rec["elaborated"] = True
                st = states[0]
                try:
                    t1 = time.time()
                    new = server.goal_tactic(st, a.tactic)
                    rec["tac_s"] = round(time.time() - t1, 1)
                    if getattr(new, "goals", None) is not None and len(new.goals) == 0:
                        rec["closed"] = True
                except Exception as e:
                    rec["err"] = f"tactic:{type(e).__name__}:{str(e)[:70]}"
                    # a tactic that crashed the server (not a clean TacticFailure) -> restart for next stmt
                    if "TacticFailure" not in type(e).__name__:
                        try: server.close()
                        except Exception: pass
                        server = start()
                break  # got a verdict (elaborated, closed-or-not)
            except Exception as e:
                rec["err"] = f"elab:{type(e).__name__}:{str(e)[:70]}"
                # server likely dead -> restart and retry once
                if attempt == 1:
                    rec["elaborated"] = False
                    try: server.close()
                    except Exception: pass
                    server = start()
                    continue
                break
        n_elab += rec["elaborated"]; n_closed += rec["closed"]
        results.append(rec)
        print(f"[{i+1}/{len(items)}] {name}: elab={rec['elaborated']} closed={rec['closed']} {rec['err'][:50]}", flush=True)

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump({"arm": "B (duper on original statement, off-pin v4.29)", "tactic": a.tactic,
               "n_problems": len(items), "n_elaborated": n_elab, "n_closed": n_closed,
               "results": results}, open(a.out, "w"), indent=2)
    print(f"\nARM B ({a.tactic}): elaborated {n_elab}/{len(items)}, CLOSED {n_closed}/{n_elab} -> {a.out}")

if __name__ == "__main__":
    main()
