"""atp command-line entrypoints.

In Phase 0 / Task 0.1 these are deliberately thin: `prove` and `sweep` load + validate a
config and run a *no-op* pipeline so `make smoke` exercises the config path end-to-end
without needing a GPU, vLLM, or Lean. Real proving lands in Tasks 0.2–0.6.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from atp.config import apply_env, config_hash, load_config


def _cmd_prove(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    env = apply_env(cfg)
    print(f"[atp prove] config={args.config} hash={config_hash(cfg)} resume={args.resume}")
    print(f"[atp prove] HF_HOME={env['HF_HOME']}")
    print(
        f"[atp prove] benchmark={cfg.data.benchmark} split={cfg.data.split} "
        f"budgets={cfg.budget.values} seeds={cfg.eval.seeds}"
    )
    print("[atp prove] no-op pipeline OK (Phase 0 scaffold)")
    return 0


def _cmd_sweep(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    apply_env(cfg)
    print(
        f"[atp sweep] config={args.config} hash={config_hash(cfg)} "
        f"array_id={args.array_id} resume={args.resume}"
    )
    print("[atp sweep] no-op pipeline OK (Phase 0 scaffold)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atp", description="Budget-bounded agentic theorem proving"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_prove = sub.add_parser("prove", help="run the agent over a problem set (no-op in Phase 0)")
    p_prove.add_argument("--config", required=True)
    p_prove.add_argument("--resume", action="store_true")
    p_prove.set_defaults(func=_cmd_prove)

    p_sweep = sub.add_parser("sweep", help="restartable array sweep (no-op in Phase 0)")
    p_sweep.add_argument("--config", required=True)
    p_sweep.add_argument("--array-id", type=int, default=0)
    p_sweep.add_argument("--resume", action="store_true")
    p_sweep.set_defaults(func=_cmd_sweep)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
