"""Stage ProofNet# (PAug/ProofNetSharp) into the loader's JSONL format.

ProofNet# is the corrected Lean 4 port of ProofNet (371 undergrad-math problems: 185 valid + 186
test), card-declared compatible with Lean v4.7.0..v4.16.0-rc2 — our pin (v4.9.0-rc1) is in range, so
the statements should typecheck against the pinned mathlib. Validate that separately before any GPU
run (scripts/validate_statements.py) — a benchmark whose heads don't elaborate is silently all-0.

Field mapping (HF schema -> atp.data.Problem / proofnet loader JSONL):
  id ("Textbook|lean_name")  -> name = "Textbook__lean_name"  (UNIQUE; bare lean names collide
                                across textbooks — 19 dups — but only the prefixed id is unique, and
                                result files are keyed by name. The bare name still lives inside
                                `statement`, which is what Lean compiles; `name` is only a label.)
  lean4_formalization        -> statement (declaration head, trailing ":=" stripped, miniF2F-style)
  lean4_src_header           -> imports + opens (parsed; `open scoped X` flattened like miniF2F)
  nl_statement               -> informal_statement

Output: scratch/proofnet/{valid,test}.jsonl  (gitignored — data lives in scratch/, never in git).
Run on a compute node (needs internet; unset the SSH proxy first):
    unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
    HF_HOME=scratch/hf-cache python scripts/build_proofnet_sharp.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pyarrow.parquet as pq
from huggingface_hub import hf_hub_download

REPO = "PAug/ProofNetSharp"
OUT_DIR = Path(__file__).resolve().parent.parent / "scratch" / "proofnet"
_NONWORD = re.compile(r"[^0-9A-Za-z_]+")


def parse_header(header: str) -> tuple[list[str], list[str]]:
    """Return (imports, opens) from a ProofNet# src header. `open scoped X` flattened into opens."""
    imports: list[str] = []
    opens: list[str] = []
    for line in header.splitlines():
        s = line.strip()
        if s.startswith("import "):
            imports.extend(s[len("import "):].split())
        elif s.startswith("open scoped "):
            opens.extend(s[len("open scoped "):].split())
        elif s.startswith("open "):
            opens.extend(s[len("open "):].split())
    # de-dup, preserve order
    return list(dict.fromkeys(imports)) or ["Mathlib"], list(dict.fromkeys(opens))


def to_record(row: dict) -> dict:
    name = _NONWORD.sub("__", row["id"]).strip("_")
    statement = row["lean4_formalization"].rstrip()
    if statement.endswith(":="):
        statement = statement[: -len(":=")].rstrip()
    imports, opens = parse_header(row["lean4_src_header"])
    return {
        "name": name,
        "statement": statement,
        "imports": imports,
        "opens": opens,
        "informal_statement": row.get("nl_statement"),
        "source_id": row["id"],
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for split in ("valid", "test"):
        pq_path = hf_hub_download(
            REPO, f"data/{split}-00000-of-00001.parquet", repo_type="dataset"
        )
        rows = pq.read_table(pq_path).to_pylist()
        recs = [to_record(r) for r in rows]
        names = [r["name"] for r in recs]
        assert len(set(names)) == len(names), "name collision after prefixing — id not unique?"
        out = OUT_DIR / f"{split}.jsonl"
        out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs))
        print(f"{split}: {len(recs)} problems -> {out}")


if __name__ == "__main__":
    main()
