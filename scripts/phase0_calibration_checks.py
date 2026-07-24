"""Phase 0 calibration checks (CPU-only, read-only) — pass@N recount + truncation/timeout audit.

Validation of already-committed Phase 0 baseline results, NOT a new experiment. Reads the
per-problem `problems/*.json` summaries and per-attempt `agent_states/*.json` traces for the 4
Phase 0 baseline run dirs (Goedel x miniF2F, DeepSeek x miniF2F, Goedel x ProofNet#, DeepSeek x
ProofNet#) and answers two questions:

  1. What N (independent whole-proof samples) does the reported 128k-token budget correspond to,
     per model x benchmark? (Answers whether comparing our pass@128k-tokens number to the
     literature's pass@32 is an apples-to-apples comparison or an axis mismatch.)
  2. How often did a PROPOSE (fresh) attempt get cut off by the per-call token cap, and how often
     did a REFINE step get fed a Lean elaboration-heartbeat-timeout error (not a genuine proof
     error)? (Answers whether the missing `maxHeartbeats` setting, already known to flip ~1.1% of
     scores, also distorts the agent's refinement trajectories, not just final scoring.)

`kind` in an attempt is either "propose" (a fresh whole-proof sample) or "refine" (a
correction chained off a *specific* prior propose, fed that prior attempt's Lean error). This
harness's baseline is whole_proof + refinement (max_iters=4) — NOT plain independent sampling —
so "N" here counts PROPOSE attempts only (the closest analog to the literature's pass@N, which is
plain independent sampling with no agentic refinement layered on top); total (propose+refine)
attempt counts are reported separately since that's the other plausible reading of "how many shots
did the model get."
"""
from __future__ import annotations

import glob
import json
import statistics
from collections import Counter, defaultdict

RUN_DIRS = {
    "goedel_minif2f": "results/baseline",
    "deepseek_minif2f": "results/deepseek_minif2f_baseline",
    "goedel_proofnet": "results/proofnet_baseline",
    "deepseek_proofnet": "results/deepseek_proofnet_baseline",
}

# Per-call sample_max_tokens = config.model.max_model_len // 2 (src/atp/agents/whole_proof.py:80).
# Goedel base.yaml: max_model_len=40960 -> cap 20480. DeepSeek (both minif2f/proofnet configs):
# max_model_len=32768 -> cap 16384.
CALL_CAP = {
    "goedel_minif2f": 20480,
    "goedel_proofnet": 20480,
    "deepseek_minif2f": 16384,
    "deepseek_proofnet": 16384,
}

HEARTBEAT_MARKER = "maximum number of heartbeats"
WALLCLOCK_TIMEOUT_REASON = "timeout"  # separate from the Lean-internal heartbeat timeout


def load_agent_states(run_dir: str) -> list[dict]:
    out = []
    errs = 0
    for f in glob.glob(f"{run_dir}/agent_states/*.json"):
        try:
            out.append(json.load(open(f)))
        except Exception:
            errs += 1
    return out, errs


def load_problems(run_dir: str) -> list[dict]:
    return [json.load(open(f)) for f in glob.glob(f"{run_dir}/problems/*.json")]


def pct(n: int, d: int) -> str:
    return f"{100*n/d:.2f}%" if d else "n/a"


def check1_pass_at_n(states_by_run: dict[str, list[dict]]) -> str:
    lines = ["# Phase 0 — Recount as pass@N (vs pass@128k-tokens)\n"]
    lines.append(
        "Empirical pass@N computed from the SAME 128k-token-budget Phase 0 runs already reported "
        "in SYNTHESIS.md, just re-sliced by attempt count instead of token spend. N counts "
        "PROPOSE (fresh whole-proof sample) attempts only, per (problem, seed) — refinement "
        "iterations chained off a specific propose are a different mechanism (this harness's own "
        "scaffolding, present even in the 'no-frills' baseline via max_iters=4) and are reported "
        "separately below, not folded into N, since literature pass@N is plain independent "
        "sampling with no refinement layer.\n"
    )
    ns = [1, 2, 4, 8, 12, 16, 24, 32, 48, 64]
    for run_key, run_dir in RUN_DIRS.items():
        states = states_by_run[run_key]
        # group by problem (strip __seedN) -> seed -> ordered propose-outcome list
        by_problem_seed: dict[tuple[str, int], list[bool]] = {}
        propose_counts = []
        total_attempt_counts = []
        for st in states:
            name = st.get("theorem_name", "?")
            atts = st.get("attempts", [])
            total_attempt_counts.append(len(atts))
            proposes = [a for a in atts if a.get("kind") == "propose"]
            propose_counts.append(len(proposes))
            # a propose "succeeds" if IT (or a refine chained off it) was ultimately accepted;
            # approximate: the whole state is solved AND this was the propose that led there —
            # for a per-N pass@N curve we need, for attempt index i, whether the FIRST i propose
            # attempts (each with its refinement chain) contain a solve anywhere in their chain.
            # Reconstruct propose->outcome by walking attempts in order and attributing each
            # refine's eventual success back to the propose that started its chain: since we don't
            # have explicit chain IDs, use the ok flag stream directly per attempt in order and
            # take "solved by attempt k" = any attempt up to and including the k-th PROPOSE's
            # associated refine block being ok. Simplify conservatively: mark propose k as
            # "successful chain" if state.solved is True and this is the LAST propose in the
            # trace (since refinement stops on first success) OR any attempt within [this
            # propose's index, next propose's index) has ok=True.
            propose_idxs = [i for i, a in enumerate(atts) if a.get("kind") == "propose"]
            solved_state = bool(st.get("stop_reason") == "solved")
            chain_success = []
            for j, start in enumerate(propose_idxs):
                end = propose_idxs[j + 1] if j + 1 < len(propose_idxs) else len(atts)
                block = atts[start:end]
                chain_success.append(any(a.get("ok") for a in block))
            # sanity: if solved_state, exactly one chain should be True (first success stops loop)
            by_problem_seed[(name, st.get("seed"))] = chain_success

        # pass@N: fraction of (problem, seed) with a True in chain_success[:N]
        pass_at_n = {}
        for n in ns:
            solved = sum(1 for v in by_problem_seed.values() if any(v[:n]))
            pass_at_n[n] = solved / len(by_problem_seed) if by_problem_seed else 0.0

        # per-seed mean/std for the max N actually reached by most problems (report at a few N)
        lines.append(f"\n## {run_key} (`{run_dir}`)\n")
        lines.append(
            f"- propose-attempt count per (problem,seed): mean={statistics.mean(propose_counts):.2f}, "
            f"median={statistics.median(propose_counts):.0f}, "
            f"p90={sorted(propose_counts)[int(0.9*len(propose_counts))]}, "
            f"max={max(propose_counts)}\n"
            f"- total attempt count (propose+refine): mean={statistics.mean(total_attempt_counts):.2f}, "
            f"median={statistics.median(total_attempt_counts):.0f}, "
            f"p90={sorted(total_attempt_counts)[int(0.9*len(total_attempt_counts))]}, "
            f"max={max(total_attempt_counts)}\n"
        )
        lines.append("| N (propose attempts) | pass@N |")
        lines.append("|---|---|")
        for n in ns:
            lines.append(f"| {n} | {100*pass_at_n[n]:.1f}% |")
        lines.append("")
    return "\n".join(lines)


def check2_truncation_and_timeout(states_by_run: dict[str, list[dict]]) -> str:
    lines = ["# Phase 0 — Truncation (token-cap) and heartbeat-timeout audit\n"]
    lines.append(
        "(a) Truncation proxy: no `finish_reason` was persisted per attempt in these runs "
        "(`client.py`'s `finish_reason` field exists in the live client response but is not saved "
        "into `agent_states`), so we proxy truncation as `completion_tokens >= CALL_CAP - 8` on "
        "PROPOSE attempts (CALL_CAP = `max_model_len // 2`: 20480 for Goedel, 16384 for DeepSeek — "
        "src/atp/agents/whole_proof.py:80). This is a lower bound: a completion could also be "
        "clamped below CALL_CAP by remaining budget, which this proxy would miss.\n"
        "(b) Heartbeat-in-refinement: among REFINE attempts, how many were preceded by a prior "
        "attempt (in the same chain) whose feedback contains the Lean heartbeat-timeout marker "
        "text, vs. a separate harness-level wall-clock verification timeout (`reason == 'timeout'`, "
        "distinct bucket, 120s Lean-process timeout, not a Lean elaboration heartbeat).\n"
    )
    for run_key, run_dir in RUN_DIRS.items():
        states = states_by_run[run_key]
        cap = CALL_CAP[run_key]
        reason_counts = Counter()
        propose_total = 0
        propose_truncated = 0
        refine_total = 0
        refine_after_heartbeat = 0
        refine_after_wallclock_timeout = 0
        for st in states:
            atts = st.get("attempts", [])
            for i, a in enumerate(atts):
                reason_counts[a.get("reason")] += 1
                if a.get("kind") == "propose":
                    propose_total += 1
                    if (a.get("completion_tokens") or 0) >= cap - 8:
                        propose_truncated += 1
                elif a.get("kind") == "refine":
                    refine_total += 1
                    prev = atts[i - 1] if i > 0 else None
                    if prev is not None:
                        fb = prev.get("feedback") or ""
                        if HEARTBEAT_MARKER in fb:
                            refine_after_heartbeat += 1
                        elif prev.get("reason") == WALLCLOCK_TIMEOUT_REASON:
                            refine_after_wallclock_timeout += 1

        lines.append(f"\n## {run_key} (`{run_dir}`)\n")
        lines.append(f"- attempt `reason` histogram: {dict(reason_counts)}\n")
        lines.append(
            f"- PROPOSE attempts at/near the per-call token cap ({cap} tokens): "
            f"{propose_truncated}/{propose_total} ({pct(propose_truncated, propose_total)})\n"
        )
        lines.append(
            f"- REFINE steps immediately preceded by a Lean heartbeat-timeout error: "
            f"{refine_after_heartbeat}/{refine_total} ({pct(refine_after_heartbeat, refine_total)})\n"
        )
        lines.append(
            f"- REFINE steps immediately preceded by a harness wall-clock verification timeout "
            f"(120s, distinct from the Lean heartbeat): {refine_after_wallclock_timeout}/{refine_total} "
            f"({pct(refine_after_wallclock_timeout, refine_total)})\n"
        )
    return "\n".join(lines)


def main() -> None:
    states_by_run = {}
    load_errs = {}
    for key, d in RUN_DIRS.items():
        states, errs = load_agent_states(d)
        states_by_run[key] = states
        load_errs[key] = errs
        print(f"{key}: loaded {len(states)} agent_states files, {errs} unreadable")

    out1 = check1_pass_at_n(states_by_run)
    with open("results/phase0/PASS_AT_N_RECOUNT.md", "w") as f:
        f.write(out1)
    print("wrote results/phase0/PASS_AT_N_RECOUNT.md")

    out2 = check2_truncation_and_timeout(states_by_run)
    with open("results/phase0/TRUNCATION_AND_TIMEOUT_AUDIT.md", "w") as f:
        f.write(out2)
    print("wrote results/phase0/TRUNCATION_AND_TIMEOUT_AUDIT.md")


if __name__ == "__main__":
    main()
