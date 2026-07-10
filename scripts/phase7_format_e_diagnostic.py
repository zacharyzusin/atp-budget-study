#!/usr/bin/env python3
"""Diagnostic: print RAW (unextracted) TacticTemplate completions for a few real trapped goal
states. Mode 4's first real run got 0/19 with n_attempts=0 on every cell (stuck at step 0, every
retry rejected) and the Format-E guard's own sample looked like a restated theorem header, not a
tactic — this prints the model's actual raw output (before `extract_proof` truncates to "first
non-empty line") to see whether it's ignoring the single-tactic instruction entirely.

Usage: python scripts/phase7_format_e_diagnostic.py --config configs/proofnet_baseline.yaml \
    --names Artin__exercise_6_4_12 Herstein__exercise_2_10_1
"""

from __future__ import annotations

import argparse

from atp.budget.meter import BudgetMeter
from atp.config import apply_env, load_config
from atp.data import load_dataset
from atp.eval.run import resolve_endpoint_file
from atp.lean.repl import ReplBackend
from atp.models.client import OpenAITransport, VLLMClient
from atp.models.templates import template_from_config


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--names", nargs="+", required=True)
    ap.add_argument("--max-tokens", type=int, default=256)
    args = ap.parse_args()

    config = load_config(args.config)
    apply_env(config)
    dataset = load_dataset(config, model_revision=config.model.revision)
    by_name = {p.name: p for p in dataset.problems}

    transport = OpenAITransport.from_endpoint_file(
        resolve_endpoint_file(config),
        timeout_s=config.model.request_timeout_s,
        max_retries=config.model.request_max_retries,
    )
    client = VLLMClient.from_config(config, transport, BudgetMeter(limit=1_000_000))
    backend = ReplBackend(config)
    template = template_from_config(config)

    for name in args.names:
        problem = by_name.get(name)
        if problem is None:
            print(f"=== {name}: NOT FOUND in dataset ===")
            continue
        thm = problem.to_theorem()
        src = f"{thm.statement.rstrip()} := by\n  sorry"
        resp = backend.elaborate(thm, src)
        state = resp["sorries"][0] if resp["sorries"] else ""
        prompt = template.render(thm, state=state, prev_tactics=())
        print(f"\n=== {name} ===")
        print(f"--- PROMPT ---\n{prompt}\n--- END PROMPT ---")
        completion = client.generate(prompt, max_tokens=args.max_tokens, label="diag")
        print(f"--- RAW COMPLETION ---\n{completion.text!r}\n--- END RAW ---")
        extracted = template.extract_proof(thm, completion.text)
        print(f"--- EXTRACTED TACTIC ---\n{extracted!r}")

    backend.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
