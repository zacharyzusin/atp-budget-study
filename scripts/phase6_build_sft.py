#!/usr/bin/env python3
"""Phase 6 Task 6.5: build the Stage A (RFT) and Stage B (closing-targeted continuation) SFT data.

Both are CONVERSATIONAL jsonl ({"messages":[{user},{assistant}]}) so trl's SFTTrainer applies the
model's OWN chat template + completion-only loss — byte-identical to the inference path (VLLMClient
posts the user turn to /v1/chat/completions; the served chat template wraps it). This is the
inference_mode_match guard at the data level: train on exactly what the model sees at eval.

  * Stage A (RFT/STaR control): user = whole-proof prompt (`render`), assistant = the verified proof
    in a ```lean4 fence. Generic self-training on the model's own successes.
  * Stage B (closing-targeted, the novel method): user = the OPTION-1 continuation prompt
    (`render_continuation`, statement+deep-prefix), assistant = the SAME verified proof fenced. The
    prompt hands the model the proof-so-far and asks it to finish — and we keep ONLY the HARD pairs
    (probe verdict: the base model could NOT close them on its own). Same completion shape as A; the
    single variable is the prompt (prefix given) + the hard-target data selection.

Hard-set reconstruction: the probe sharded the pairs as rows[shard::N]; we replay that stride to map
each hard probe record back to its closing_targets row (validated by name), so we recover the exact
cont_prefix for each hard pair without re-running the GPU probe. (New probe records also carry k/
n_groups directly; we prefer those when present.)

Pure core (`make_example`, `hard_rows_from_shards`) is unit-tested with no model/GPU (test_phase6).

Usage:
  python scripts/phase6_build_sft.py --config configs/phase6_harvest_goedel.yaml \
      --sft-dir scratch/phase6/sft/goedel --num-shards 8
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _fenced(proof: str) -> str:
    return f"```lean4\n{proof.strip()}\n```"


def make_example(kind: str, template, thm, proof: str, cont_prefix: str | None,
                 cont_target: str | None = None) -> dict:
    """One conversational SFT example. A: whole-proof prompt; B: continuation prompt (needs prefix).
    Assistant turn is the verified proof fenced in BOTH (same completion shape — single variable is
    the user prompt + which pairs are selected). For B we also record `supervise_after`=cont_target
    so training masks loss to the CLOSING tokens only (the prompt already hands over the prefix, so
    supervising the full proof would just reward copying it — see phase6_train_sft.build_labels)."""
    if kind == "A":
        user = template.render(thm)
    elif kind == "B":
        if not cont_prefix:
            raise ValueError("Stage B example needs a cont_prefix")
        user = template.render_continuation(thm, cont_prefix)
    else:
        raise ValueError(f"unknown kind {kind!r}")
    ex = {
        "kind": kind,
        "name": thm.name,
        "messages": [
            {"role": "user", "content": user},
            {"role": "assistant", "content": _fenced(proof)},
        ],
    }
    if kind == "B" and cont_target:
        # the closing block appears verbatim as the proof's tail; mask loss up to its start
        ex["supervise_after"] = cont_target.strip("\n")
    return ex


def hard_rows_from_shards(all_rows: list[dict], shard_glob: str, num_shards: int) -> list[dict]:
    """Replay the probe's rows[shard::N] stride to recover the closing_targets rows the probe marked
    HARD. Validates each record-row mapping by name; prefers a record's own (k,n_groups) if present
    (newer probe output) for an exact match, else trusts the positional stride."""
    hard: list[dict] = []
    for fp in sorted(glob.glob(shard_glob)):
        shard = int(fp.rsplit(".s", 1)[1].split(".")[0])
        recs = json.loads(Path(fp).read_text())["records"]
        for j, rec in enumerate(recs):
            row = all_rows[shard + j * num_shards]
            if row["name"] != rec["name"]:
                raise ValueError(f"stride mismatch in {fp}: row {row['name']} != rec {rec['name']}")
            if rec.get("k") is not None and (row.get("k"), row.get("n_groups")) != (
                    rec.get("k"), rec.get("n_groups")):
                raise ValueError(f"key mismatch in {fp} for {row['name']}")
            if rec.get("is_hard"):
                hard.append(row)
    return hard


def _write_jsonl(path: Path, examples: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in examples) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--sft-dir", required=True,
                    help="dir w/ rft.jsonl + closing_targets.jsonl + probe_hard.s*.json; "
                         "writes sft_A.jsonl + sft_B.jsonl")
    ap.add_argument("--num-shards", type=int, default=8, help="the probe's --num-shards")
    args = ap.parse_args()

    from atp.config import load_config
    from atp.data import load_dataset
    from atp.data.closing_targets import closing_truncations
    from atp.models.templates import template_from_config

    config = load_config(args.config)
    ds = load_dataset(config)
    problems = ds.problems if hasattr(ds, "problems") else ds
    thms = {p.name: p.to_theorem() for p in problems}
    template = template_from_config(config)
    sft_dir = Path(args.sft_dir)

    # --- Stage A: every verified proof (RFT) ---
    rft = [json.loads(ln) for ln in (sft_dir / "rft.jsonl").read_text().splitlines() if ln.strip()]
    a_examples = [make_example("A", template, thms[r["name"]], r["proof"], None)
                  for r in rft if r["name"] in thms]

    # --- Stage B: HARD continuation pairs only ---
    all_pairs = [json.loads(ln) for ln in
                 (sft_dir / "closing_targets.jsonl").read_text().splitlines() if ln.strip()]
    hard = hard_rows_from_shards(all_pairs, str(sft_dir / "probe_hard.s*.json"), args.num_shards)

    def cont_of(row: dict) -> tuple[str, str] | None:
        """(cont_prefix, cont_target) — stored if present, else re-derived from the proof."""
        if row.get("cont_prefix") and row.get("cont_target"):
            return row["cont_prefix"], row["cont_target"]
        key = (row.get("depth"), row.get("k"), row.get("n_groups"),
               (row.get("closing") or "").strip())
        m = [c for c in closing_truncations(row["proof"])
             if (c.depth, c.k, c.n_groups, c.closing.strip()) == key]
        return (m[0].cont_prefix, m[0].cont_target) if len(m) == 1 else None

    b_examples = []
    for row in hard:
        cont = cont_of(row)
        if cont and row["name"] in thms:
            cp, ct = cont
            b_examples.append(
                make_example("B", template, thms[row["name"]], row["proof"], cp, ct))

    _write_jsonl(sft_dir / "sft_A.jsonl", a_examples)
    _write_jsonl(sft_dir / "sft_B.jsonl", b_examples)
    summary = {"n_rft": len(rft), "n_A": len(a_examples), "n_hard": len(hard),
               "n_B": len(b_examples),
               "n_B_distinct_proofs": len({e["name"] for e in b_examples})}
    (sft_dir / "sft_build_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"[build-sft] A(RFT)={len(a_examples)}  B(continuation-hard)={len(b_examples)} "
          f"from {summary['n_B_distinct_proofs']} proofs -> {sft_dir}/sft_A.jsonl, sft_B.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
