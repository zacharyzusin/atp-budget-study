#!/usr/bin/env python3
"""Stage C probe — G1/G2/G3 triple-gate verdict (STAGE_C_PROBE_SPEC.md §4).

Reads the base-vs-RL held-out gate eval (results/<base_run>, results/<rl_run>, both produced by
sweep_array.sh + `atp sweep --aggregate` on configs/phase6_grpo_heldout_deepseek.yaml, seeds 0-7,
budget 8192) plus the RL training's own probe_metrics.jsonl (for G3's KL-to-base), and prints the
pre-registered verdict. No GPU/Lean — pure post-hoc analysis of on-disk artifacts.

G1 (primary): RL pass@1 >= base pass@1 + 5pp, AND training reward curve rose.
G2 (soundness): RL held-out unsound (loophole) rate <= base + 2pp.
G3 (no collapse): RL distinct-3gram ratio >= 80% of base's, AND mean training KL under ceiling.

Usage:
  python scripts/phase6_stage_c_gate.py --base results/p6gate_base --rl results/p6gate_rl \
      --probe-metrics scratch/phase6/grpo/deepseek/probe/probe_metrics.jsonl --budget 8192
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path


def load_agent_states(run_dir: Path) -> list[dict]:
    states_dir = run_dir / "agent_states"
    return [json.loads(p.read_text()) for p in sorted(states_dir.glob("*.json"))]


def pass_at_1(states: list[dict], budget: int) -> float:
    """Mean over seeds of (fraction of problems solved within budget) — one attempt per cell."""
    by_seed: dict[int, list[dict]] = defaultdict(list)
    for s in states:
        seed = _seed_of(s)
        by_seed[seed].append(s)
    fracs = []
    for rs in by_seed.values():
        if not rs:
            continue
        n_solved = sum(1 for s in rs if _solved_within(s, budget))
        fracs.append(n_solved / len(rs))
    return statistics.fmean(fracs) if fracs else 0.0


def pass_at_k(states: list[dict], budget: int) -> float:
    """Fraction of DISTINCT problems solved within budget by >=1 of the k seeds (pass@k)."""
    by_problem: dict[str, list[dict]] = defaultdict(list)
    for s in states:
        by_problem[s["theorem_name"]].append(s)
    if not by_problem:
        return 0.0
    n_any = sum(
        1 for rows in by_problem.values() if any(_solved_within(s, budget) for s in rows)
    )
    return n_any / len(by_problem)


def unsound_rate(states: list[dict]) -> float:
    """Fraction of ATTEMPTS across all cells whose verifier reason == 'loophole'."""
    attempts = [a for s in states for a in s.get("attempts", [])]
    if not attempts:
        return 0.0
    n_loophole = sum(1 for a in attempts if a.get("reason") == "loophole")
    return n_loophole / len(attempts)


def distinct_trigram_ratio(states: list[dict]) -> float:
    """Mean over cells of (# distinct word-trigrams / # trigrams) in the FINAL attempt's proof."""
    ratios = []
    for s in states:
        attempts = s.get("attempts", [])
        if not attempts:
            continue
        proof = attempts[-1].get("proof", "") or ""
        toks = proof.split()
        if len(toks) < 3:
            continue
        trigrams = [tuple(toks[i : i + 3]) for i in range(len(toks) - 2)]
        ratios.append(len(set(trigrams)) / len(trigrams))
    return statistics.fmean(ratios) if ratios else 0.0


def _seed_of(state: dict) -> int:
    # AgentState doesn't carry seed itself; the eval harness names agent_states files
    # "<name>__seed<seed>.json" (atp/eval/run.py:71). Callers tag states with "_seed" from that
    # filename via load_tagged_agent_states below.
    return state["_seed"]


def _solved_within(state: dict, budget: int) -> bool:
    if not state.get("done") or state.get("stop_reason") != "solved":
        return False
    spent = state.get("budget", {}).get("spent")
    return spent is not None and spent <= budget


def load_tagged_agent_states(run_dir: Path) -> list[dict]:
    states_dir = run_dir / "agent_states"
    out = []
    for p in sorted(states_dir.glob("*.json")):
        d = json.loads(p.read_text())
        # filename: "<name>__seed<seed>.json"
        stem = p.stem
        seed = int(stem.rsplit("__seed", 1)[1])
        d["_seed"] = seed
        out.append(d)
    return out


def mean_kl(probe_metrics_path: Path) -> float | None:
    if not probe_metrics_path.exists():
        return None
    kls = []
    for line in probe_metrics_path.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if "kl" in rec:
            kls.append(rec["kl"])
    return statistics.fmean(kls) if kls else None


def training_reward_rose(probe_metrics_path: Path) -> bool | None:
    if not probe_metrics_path.exists():
        return None
    rewards = []
    for line in probe_metrics_path.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if "reward/cum_solve_rate" in rec:
            rewards.append((rec["step"], rec["reward/cum_solve_rate"]))
    if len(rewards) < 2:
        return None
    rewards.sort()
    first_half = [r for _, r in rewards[: len(rewards) // 2]]
    second_half = [r for _, r in rewards[len(rewards) // 2 :]]
    return statistics.fmean(second_half) > statistics.fmean(first_half)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="results/<base_run> dir")
    ap.add_argument("--rl", required=True, help="results/<rl_run> dir")
    ap.add_argument("--probe-metrics", required=True, help="scratch/.../probe_metrics.jsonl")
    ap.add_argument("--budget", type=int, default=8192)
    ap.add_argument("--kl-ceiling", type=float, default=0.05)
    args = ap.parse_args()

    base = load_tagged_agent_states(Path(args.base))
    rl = load_tagged_agent_states(Path(args.rl))
    print(f"[gate] base cells={len(base)} rl cells={len(rl)}")

    base_p1, rl_p1 = pass_at_1(base, args.budget), pass_at_1(rl, args.budget)
    base_p8, rl_p8 = pass_at_k(base, args.budget), pass_at_k(rl, args.budget)
    base_unsound, rl_unsound = unsound_rate(base), unsound_rate(rl)
    base_div, rl_div = distinct_trigram_ratio(base), distinct_trigram_ratio(rl)
    kl = mean_kl(Path(args.probe_metrics))
    reward_rose = training_reward_rose(Path(args.probe_metrics))

    delta_p1 = rl_p1 - base_p1
    delta_unsound = rl_unsound - base_unsound
    div_ratio = (rl_div / base_div) if base_div > 0 else float("nan")

    g1 = delta_p1 >= 0.05 and bool(reward_rose)
    g2 = delta_unsound <= 0.02
    g3 = (div_ratio >= 0.80) and (kl is not None and kl < args.kl_ceiling)

    print(f"[gate] pass@1  base={base_p1:.4f} rl={rl_p1:.4f} delta={delta_p1:+.4f} "
          f"(need >=+0.05 AND reward_rose={reward_rose}) -> G1={g1}")
    print(f"[gate] pass@8  base={base_p8:.4f} rl={rl_p8:.4f}")
    print(f"[gate] unsound base={base_unsound:.4f} rl={rl_unsound:.4f} delta={delta_unsound:+.4f} "
          f"(need <=+0.02) -> G2={g2}")
    print(f"[gate] distinct-3gram base={base_div:.4f} rl={rl_div:.4f} ratio={div_ratio:.4f} "
          f"(need >=0.80) mean_kl={kl} (need <{args.kl_ceiling}) -> G3={g3}")

    if g1 and g2 and g3:
        verdict = "c1: RL moves the floor -> fund full Stage C"
    elif reward_rose and (not g1 or not g2):
        verdict = "hack/overfit -> NO-GO (not c1)"
    elif not reward_rose:
        verdict = "c2: capacity ceiling -> close the training arc"
    else:
        verdict = "ambiguous -> inspect manually"
    print(f"[gate] VERDICT: {verdict}")

    out = {
        "base_pass_at_1": base_p1, "rl_pass_at_1": rl_p1, "delta_pass_at_1": delta_p1,
        "base_pass_at_8": base_p8, "rl_pass_at_8": rl_p8,
        "base_unsound_rate": base_unsound, "rl_unsound_rate": rl_unsound,
        "delta_unsound_rate": delta_unsound,
        "base_distinct_3gram": base_div, "rl_distinct_3gram": rl_div,
        "distinct_3gram_ratio": div_ratio, "mean_kl": kl, "training_reward_rose": reward_rose,
        "G1": g1, "G2": g2, "G3": g3, "verdict": verdict,
    }
    out_path = Path(args.rl).parent / "STAGE_C_GATE.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"[gate] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
