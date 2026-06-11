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
    from pathlib import Path

    from atp.eval.run import run_eval

    cfg = load_config(args.config)
    run_name = args.name or f"run_{config_hash(cfg)}"
    run_dir = Path(cfg.project.root) / cfg.project.results_dir / run_name
    print(f"[atp sweep] config={args.config} hash={config_hash(cfg)} run_dir={run_dir}")
    # Real path: needs the vLLM endpoint file + the built Goedel-pin Lean env; fails clearly if not.
    result = run_eval(cfg, run_dir, resume=args.resume)
    print(f"[atp sweep] cells: ran={result.n_ran} skipped={result.n_skipped}")
    for p in result.metrics["pass_at_b"]:
        print(f"  pass@{p['budget']:>7}: {p['mean']:.3f} ± {p['std']:.3f}  (n={p['n_problems']})")
    print(f"[atp sweep] wrote {run_dir}/metrics.json, run_manifest.json, pass_at_b.png")
    return 0


def _cmd_ablation(args: argparse.Namespace) -> int:
    import json
    from pathlib import Path

    from atp.eval.ablation import ablation_manifest, expand_ablation, validate_cells

    cfg = load_config(args.config)
    cells = expand_ablation(cfg)

    if args.list:
        print(f"[atp ablation] {len(cells)} cells from {args.config}:")
        for i, cell in enumerate(cells):
            h = config_hash(cell.config)
            print(f"  [{i:>2}] {cell.name:<24} axis={cell.axis:<16} hash={h}")
        return 0

    if args.check:
        validate_cells(cells)  # raises on the first bad cell
        print(f"[atp ablation] all {len(cells)} cells valid (schema + components)")
        return 0

    if args.cell_id is None:
        print("[atp ablation] specify one of --list | --check | --cell-id N", file=sys.stderr)
        return 2
    if not 0 <= args.cell_id < len(cells):
        msg = f"[atp ablation] cell-id {args.cell_id} out of range [0,{len(cells)})"
        print(msg, file=sys.stderr)
        return 2

    from atp.eval.run import run_eval

    cell = cells[args.cell_id]
    run_name = args.name or Path(args.config).stem
    run_dir = Path(cfg.project.root) / cfg.project.results_dir / run_name / cell.name
    print(f"[atp ablation] cell[{args.cell_id}]={cell.name} axis={cell.axis} run_dir={run_dir}")
    # Write the cell→override manifest next to the run so analysis can join results back.
    run_dir.parent.mkdir(parents=True, exist_ok=True)
    manifest = json.dumps(ablation_manifest(cells), indent=2)
    (run_dir.parent / "ablation_cells.json").write_text(manifest)
    result = run_eval(cell.config, run_dir, resume=args.resume)
    print(f"[atp ablation] cells: ran={result.n_ran} skipped={result.n_skipped}")
    for p in result.metrics["pass_at_b"]:
        print(f"  pass@{p['budget']:>7}: {p['mean']:.3f} ± {p['std']:.3f}  (n={p['n_problems']})")
    print(f"[atp ablation] wrote {run_dir}/metrics.json")
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

    p_sweep = sub.add_parser("sweep", help="run a restartable eval sweep → pass@B + manifest")
    p_sweep.add_argument("--config", required=True)
    p_sweep.add_argument("--name", default=None, help="run dir under results/ (default run_<hash>)")
    p_sweep.add_argument("--array-id", type=int, default=0)
    p_sweep.add_argument("--resume", action="store_true")
    p_sweep.set_defaults(func=_cmd_sweep)

    p_abl = sub.add_parser("ablation", help="expand a Phase 1 sweep config into OFAT cells")
    p_abl.add_argument("--config", required=True, help="a sweep config (e.g. phase1_ablation.yaml)")
    p_abl.add_argument("--list", action="store_true", help="list the expanded cells and exit")
    p_abl.add_argument("--check", action="store_true", help="validate all cells, then exit")
    p_abl.add_argument("--cell-id", type=int, default=None, help="run this cell index (array id)")
    p_abl.add_argument("--name", default=None, help="run dir under results/ (default: config stem)")
    p_abl.add_argument("--resume", action="store_true")
    p_abl.set_defaults(func=_cmd_ablation)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
