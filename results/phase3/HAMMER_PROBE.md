# Hammer / SMT Leaf-Closing Probe — results & go/no-go

*2026-06-20. Decision gate for the neuro-symbolic direction (neural skeleton + symbolic leaf). CPU-only,
no GPU. Pre-registered thresholds in DECISIONS.md 2026-06-20.*

## Motivation
H4 showed the OOD floor is **within-approach execution / leaf-closing**, not approach discovery — the
natural lever to test is "hand the model's stuck leaf to a symbolic closer."

## Results so far (Goedel, ProofNet# trapped core; on-pin, v4.9.0-rc1)

| Arm | what | result |
|-----|------|--------|
| **Positive control** | portfolio on 4 synthetic trivial goals | **4/4 PASS** (probe fires correctly) |
| **Arm 0** | portfolio on the **original** trapped statement | **0 / 30** |
| **Arm A-lite** | portfolio swapped in for the model's **failing tactic**, in-context | **0 / 40** |

Portfolio = `omega | nlinarith | norm_num | simp_all | decide | aesop` (the on-pin tactics; `grind`/`duper`/
Lean-SMT/LeanHammer are not on the v4.9.0 pin). All closures would be re-verified by the fixed verifier;
none occurred.

## Reading
- **The portfolio provides zero leaf-closing synergy.** Neither on the bare statement (Arm 0) nor swapped
  in at the model's stuck leaf (Arm A-lite) does standard Lean tactic automation close a single trapped
  problem. This is consistent with H2 (the model already invokes `nlinarith`/`simp`/`omega` inline) and
  with H4/Step C (the floor is a deep-execution floor that resists search-time intervention).
- **Two honest caveats:**
  1. *Portfolio ≠ hammer.* A real superposition prover (`duper`) or SMT (`Lean-SMT`/cvc5) reasons beyond
     the portfolio. Arm-A-lite = 0 rules out "the model forgot easy automation," but does **not** test
     whether a strong hammer would close these leaves. That decisive test needs `duper`/Lean-SMT built on
     the v4.9.0 pin **and** proper REPL proofState extraction (trapped proofs are nested-monolithic — flat
     prefix/failing-tactic swap is recall-lossy, so 0/40 is a lower bound).
  2. *Recall-lossy.* Arm-A-lite fires cleanly only when the blamed tactic is a closing leaf; nested
     failures produce structurally-broken swaps counted as "no." So the true portfolio-at-leaf rate is
     ≥ 0/40 but still small.

## Go/no-go call (against pre-registered thresholds)
Pre-registered NO-GO = closure < ~2pp across arms → **met for the portfolio** (0pp on both cheap arms).
The decisive duper/SMT Arm A is **not yet run** — it requires real infra investment (v4.9.0 port +
proofState extraction) whose EV is **low** given the converging negatives (Arm0=0, Arm-A-lite=0, H4
execution-floor, Step C forced-diversity null, nested-degenerate proofs).

**Recommendation: NO-GO on current evidence — do NOT port duper.** Fold the probe into the negative
thesis as a strengthening result: *"even handing the model's deepest stuck leaf to standard Lean tactic
automation closes 0/40 trapped problems — the OOD execution floor is not a thin automation gap."* This
pre-empts the obvious reviewer objection ("did you try a hammer?") with a concrete, if portfolio-level,
answer, and is honest about what a full superposition/SMT hammer at properly-extracted leaves was not
tested. If a reviewer or the team wants the decisive version, the scoped follow-up is: build proofState
extraction + port `duper` to v4.9.0 (≈1–2 days) and re-run Arm A on the extracted leaves.
