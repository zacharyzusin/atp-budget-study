#!/usr/bin/env python3
"""Phase 6 Stage B — continuation round-trip smoke (Task 6.3) + hard-target probe (Task 6.4).

The crux of Stage B (DECISIONS.md 2026-06-22): the closing-targeted training set must contain only
closings the BASE MODEL CANNOT already produce on its own — else B merely echoes A and the novelty
evaporates. This script feeds the base model the OPTION-1 continuation prompt (statement + verified
proof-prefix, byte-exact to inference via `WholeProofTemplate.render_continuation`) and asks it to
finish; a pair is HARD (kept for Stage B) iff the base fails to close it. Pairs the base closes are
A-like and dropped.

Faithful-to-inference classification: the model's completion is run through the SAME extract+verify
path the agent uses (`extract_proof` -> verify). A `--samples k` (different seeds) lets a pair count
as already-closable if ANY sample closes (conservative: keeps the hard set genuinely hard). A
secondary SPLICE diagnostic (prefix + bare continuation) flags whether an inference-time
continuation proposer would help — recorded, not used to gate, except when output is bare tactics.

Two roles, one machinery:
  * `--limit N` (small) = ROUND-TRIP SMOKE: confirms continuation prompts yield a parseable ```lean4
    block through the real serving path (catch the -36pp inference_mode_match mismatch BEFORE train)
    and that prefix+target verifies (it does by construction; spot-check).
  * full run = HARD-TARGET PROBE: writes the per-pair hard/closable verdict = Stage B's train set.

The pure core (`recompute_cont`, `classify_samples`, `probe_pairs`) takes injected generate/verify
callables, so it is unit-tested with no GPU and no Lean (tests/test_phase6_probe.py). `main()` wires
the real VLLMClient (from the vLLM endpoint file) + ReplBackend, exactly like atp.eval.run.

Usage (smoke, on a GPU node with the vLLM server up + ATP_VLLM_ENDPOINT_FILE set):
  python scripts/phase6_continuation_probe.py --config configs/phase6_harvest_goedel.yaml \
      --pairs scratch/phase6/sft/goedel/closing_targets.jsonl \
      --out scratch/phase6/sft/goedel/probe_smoke.json --limit 8 --samples 1 --budget 4096
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from atp.data.closing_targets import closing_truncations

ROOT = Path(__file__).resolve().parents[1]


def recompute_cont(row: dict) -> tuple[str, str] | None:
    """Return (cont_prefix, cont_target) for a closing_targets.jsonl row.

    Prefer the stored fields (full-harvest output carries them); else re-derive deterministically by
    matching `closing_truncations(proof)` on (depth, k, n_groups, closing) — no Lean, no GPU.
    """
    if row.get("cont_prefix") and row.get("cont_target"):
        return row["cont_prefix"], row["cont_target"]
    proof = row.get("proof")
    if not proof:
        return None
    key = (row.get("depth"), row.get("k"), row.get("n_groups"), (row.get("closing") or "").strip())
    matches = [
        c for c in closing_truncations(proof)
        if (c.depth, c.k, c.n_groups, c.closing.strip()) == key
    ]
    if len(matches) != 1:
        return None
    c = matches[0]
    return c.cont_prefix, c.cont_target


@dataclass
class SampleOutcome:
    parseable: bool          # the completion contained a ```lean4 fenced block
    whole_closed: bool       # verify(extract_proof(completion)) succeeded (faithful inference path)
    spliced_closed: bool     # verify(prefix + bare-continuation) succeeded (diagnostic)
    finished: bool = True    # model stopped naturally (finish_reason != "length" = not truncated)


def classify_samples(samples: list[SampleOutcome]) -> dict:
    """Verdict per pair. CLOSED if any sample verified (whole OR splice) => already-capable => DROP.
    Else HARD (keep for Stage B) ONLY if at least one non-closing sample FINISHED naturally — a
    conclusive failure. If every non-closing sample was TRUNCATED (finish_reason==length, e.g. the
    base re-emitting a long whole proof overran the budget), the pair is INDETERMINATE, not hard:
    counting it hard would pollute the train set with budget noise, not real closing failures."""
    any_close = any(s.whole_closed or s.spliced_closed for s in samples)
    conclusive_fail = any(s.finished and not (s.whole_closed or s.spliced_closed) for s in samples)
    return {
        "is_hard": (not any_close) and conclusive_fail,
        "indeterminate": (not any_close) and (not conclusive_fail),
        "n_samples": len(samples),
        "n_parseable": sum(s.parseable for s in samples),
        "n_finished": sum(s.finished for s in samples),
        "n_whole_closed": sum(s.whole_closed for s in samples),
        "n_spliced_closed": sum(s.spliced_closed for s in samples),
    }


@dataclass
class ProbeDeps:
    """Injected I/O so the core is testable. `generate(prompt, seed) -> completion text`;
    `verify(statement_or_theorem, proof) -> bool` (did it cleanly verify, no loophole)."""

    render_continuation: Callable[[object, str], str]
    extract_proof: Callable[[object, str], str]
    generate: Callable[[str, int], tuple[str, str]]  # (completion text, finish_reason)
    verify: Callable[[object, str], bool]
    has_fence: Callable[[str], bool]
    build_proof_from_prefix: Callable[[object, str, str], str]


def probe_pairs(
    rows: list[dict],
    theorems_by_name: dict,
    deps: ProbeDeps,
    *,
    samples: int = 1,
    seed: int = 1,
) -> list[dict]:
    """Probe each pair; return per-pair records with the hard/closable verdict + format stats."""
    records: list[dict] = []
    for row in rows:
        name = row["name"]
        thm = theorems_by_name.get(name)
        cont = recompute_cont(row)
        if thm is None or cont is None:
            records.append({"name": name, "skipped": True,
                            "reason": "no_theorem" if thm is None else "no_cont_fields"})
            continue
        cont_prefix, _cont_target = cont
        prompt = deps.render_continuation(thm, cont_prefix)
        outs: list[SampleOutcome] = []
        for s in range(samples):
            text, finish_reason = deps.generate(prompt, seed + s)
            parseable = deps.has_fence(text)
            extracted = deps.extract_proof(thm, text)
            whole = deps.verify(thm, extracted)
            # splice diagnostic only when the completion is NOT itself a full proof (no `theorem`/
            # `:= by` of the statement) — otherwise splicing duplicates the head.
            spliced = False
            if not whole and "theorem" not in extracted and ":= by" not in extracted:
                spliced = deps.verify(
                    thm, deps.build_proof_from_prefix(thm, cont_prefix, extracted))
            outs.append(SampleOutcome(parseable=parseable, whole_closed=whole,
                                      spliced_closed=spliced, finished=(finish_reason != "length")))
        rec = {"name": name, "depth": row.get("depth"), "k": row.get("k"),
               "n_groups": row.get("n_groups"), "skipped": False}
        rec.update(classify_samples(outs))
        records.append(rec)
    return records


def summarize(records: list[dict]) -> dict:
    probed = [r for r in records if not r.get("skipped")]
    n = len(probed)
    n_hard = sum(r["is_hard"] for r in probed)
    n_indet = sum(r.get("indeterminate", False) for r in probed)
    n_parse = sum(r["n_parseable"] for r in probed)
    n_fin = sum(r.get("n_finished", r["n_samples"]) for r in probed)
    n_samp = sum(r["n_samples"] for r in probed)
    return {
        "n_pairs": len(records),
        "n_probed": n,
        "n_skipped": len(records) - n,
        "n_hard": n_hard,
        "n_indeterminate": n_indet,
        "n_base_closes": n - n_hard - n_indet,
        "hard_rate": (n_hard / n) if n else 0.0,
        "indeterminate_rate": (n_indet / n) if n else 0.0,
        "parseable_rate": (n_parse / n_samp) if n_samp else 0.0,
        "finished_rate": (n_fin / n_samp) if n_samp else 0.0,
    }


def _load_rows(pairs_path: str, limit: int | None) -> list[dict]:
    rows = [json.loads(ln) for ln in Path(pairs_path).read_text().splitlines() if ln.strip()]
    return rows[:limit] if limit else rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--pairs", required=True, help="closing_targets.jsonl")
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=None, help="probe only the first N (smoke)")
    ap.add_argument("--samples", type=int, default=1, help="fresh continuation samples per pair")
    ap.add_argument("--budget", type=int, default=4096, help="max_tokens per continuation sample")
    ap.add_argument("--seed", type=int, default=1, help="base sampling seed (sample s uses seed+s)")
    ap.add_argument("--num-shards", type=int, default=1, help="split pairs across N array tasks")
    ap.add_argument("--shard-id", type=int, default=0, help="this task's stride index [0, N)")
    ap.add_argument("--merge", default=None,
                    help="glob of shard result jsons to combine into --out (no GPU/model needed)")
    args = ap.parse_args()

    if args.merge:
        import glob
        recs: list[dict] = []
        for fp in sorted(glob.glob(args.merge)):
            recs.extend(json.loads(Path(fp).read_text())["records"])
        merged = {"merged_from": sorted(glob.glob(args.merge)), "summary": summarize(recs),
                  "records": recs}
        Path(args.out).write_text(json.dumps(merged, indent=2, ensure_ascii=False))
        s = merged["summary"]
        print(f"[probe-merge] {s['n_probed']} probed | hard {s['n_hard']} ({s['hard_rate']:.0%}) | "
              f"indet {s['n_indeterminate']} | base-closes {s['n_base_closes']} -> {args.out}")
        return 0

    from atp.config import load_config
    from atp.data import load_dataset
    from atp.eval.run import resolve_endpoint_file
    from atp.lean.repl import ReplBackend
    from atp.lean.verifier import Verifier
    from atp.models.client import OpenAITransport, VLLMClient
    from atp.models.templates import extract_lean_block, template_from_config

    config = load_config(args.config)
    ds = load_dataset(config)
    problems = ds.problems if hasattr(ds, "problems") else ds
    thms = {p.name: p.to_theorem() for p in problems}

    template = template_from_config(config)
    transport = OpenAITransport.from_endpoint_file(
        resolve_endpoint_file(config),
        timeout_s=config.model.request_timeout_s,
        max_retries=config.model.request_max_retries,
    )
    client = VLLMClient.from_config(config, transport, None)
    verifier = Verifier.from_config(config, ReplBackend(config))

    def generate(prompt: str, seed: int) -> tuple[str, str]:
        client.seed = seed
        c = client.generate(prompt, max_tokens=args.budget, label="probe")
        return c.text, c.finish_reason

    def verify(thm, proof: str) -> bool:
        return verifier.verify(thm, proof).ok

    def build_proof_from_prefix(thm, cont_prefix: str, cont: str) -> str:
        # full proof string (statement + spliced body); the backend adds imports/opens on verify.
        body = f"{cont_prefix}\n{cont}".strip("\n")
        return f"{thm.statement.rstrip()} := by\n{body}"

    deps = ProbeDeps(
        render_continuation=template.render_continuation,
        extract_proof=template.extract_proof,
        generate=generate,
        verify=verify,
        has_fence=lambda t: extract_lean_block(t) is not None,
        build_proof_from_prefix=build_proof_from_prefix,
    )

    rows = _load_rows(args.pairs, args.limit)
    if args.num_shards > 1:
        rows = rows[args.shard_id::args.num_shards]  # disjoint stride; union == all pairs
        print(f"[probe] shard {args.shard_id}/{args.num_shards}: {len(rows)} pairs")
    records = probe_pairs(rows, thms, deps, samples=args.samples, seed=args.seed)
    summary = summarize(records)
    out = {"config": args.config, "pairs": args.pairs, "samples": args.samples,
           "budget": args.budget, "summary": summary, "records": records}
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"[probe] {summary['n_probed']} probed | hard {summary['n_hard']} "
          f"({summary['hard_rate']:.0%}) | indet {summary['n_indeterminate']} "
          f"({summary['indeterminate_rate']:.0%}) | base-closes {summary['n_base_closes']} | "
          f"parseable {summary['parseable_rate']:.0%} | finished {summary['finished_rate']:.0%} | "
          f"skipped {summary['n_skipped']}")
    print(f"[probe] report -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
