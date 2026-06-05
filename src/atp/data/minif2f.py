"""miniF2F (Lean 4) loader.

Parses the benchmark's per-split `.lean` files (`formal/<split>.lean`) into `Problem`s, attaches
the informal statement (`informal/<split>/<name>.json`) when present, and stamps provenance
(source repo + commit + file + line) on every problem.

Pure text parsing — no Lean/Pantograph — so it runs on a login node and unit-tests without the env.

Source: the file format is the `theorem NAME … := sorry` statement bank shared by the miniF2F Lean4
ports. Default location points at the sibling project's vendored copy (see DEFAULT_MINIF2F_DIR);
override via `config.data.minif2f_dir`. NOTE: that port is not necessarily the *audited* miniF2F —
provenance records the exact commit so a later swap to an audited source is a config change, and the
exclusion list (exclusions.py) validates its names against what actually loads.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from atp.data.problems import Problem

# Default vendored copy: the sibling theorem-proving-research project's miniF2F submodule.
DEFAULT_MINIF2F_DIR = Path(
    "/insomnia001/depts/edu/COMS-E6998-012/zwz2000/theorem-proving-research/miniF2F"
)

# A theorem block starts at a line beginning with `theorem ` (or `lemma `).
_DECL_START = re.compile(r"(?m)^(?=(?:theorem|lemma)\s)")
_DECL_NAME = re.compile(r"^(?:theorem|lemma)\s+([A-Za-z_][\w']*)")
# The proof assignment that terminates a statement: `:= sorry` / `:= by sorry` at block end.
_PROOF_TAIL = re.compile(r"\s*:=\s*(?:by\s+)?sorry\s*$", re.DOTALL)


def _parse_header(text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Collect `import X` and `open …` clauses from the file preamble (before the first decl)."""
    imports: list[str] = []
    opens: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("import "):
            imports.append(s[len("import ") :].strip())
        elif s.startswith("open "):
            clause = s[len("open ") :].strip()
            # `open scoped BigOperators` → keep the namespaces, drop the `scoped` keyword for our
            # single-`open` reconstruction (notation still resolves on the target mathlib).
            clause = clause.replace("scoped ", "").strip()
            opens.extend(tok for tok in clause.split() if tok)
        elif s.startswith(("theorem ", "lemma ")):
            break
    return tuple(imports) or ("Mathlib",), tuple(dict.fromkeys(opens))


def parse_minif2f_lean(text: str) -> list[tuple[str, str, int]]:
    """Parse a miniF2F `.lean` file body into (name, statement, line_no) tuples.

    `statement` is the declaration head with the trailing `:= sorry` stripped.
    """
    out: list[tuple[str, str, int]] = []
    starts = [m.start() for m in _DECL_START.finditer(text)]
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        block = text[start:end]
        m = _DECL_NAME.match(block)
        if not m:
            continue
        name = m.group(1)
        statement = _PROOF_TAIL.sub("", block).strip()
        line_no = text.count("\n", 0, start) + 1
        out.append((name, statement, line_no))
    return out


def _git_provenance(repo_dir: Path) -> dict[str, str]:
    """Best-effort source repo URL + commit (empty dict if not a git checkout)."""
    prov: dict[str, str] = {}
    for key, args in (("source_commit", ["rev-parse", "HEAD"]),
                      ("source_repo", ["config", "--get", "remote.origin.url"])):
        try:
            res = subprocess.run(
                ["git", "-C", str(repo_dir), *args],
                capture_output=True, text=True, timeout=10, check=True,
            )
            prov[key] = res.stdout.strip()
        except (subprocess.SubprocessError, OSError):
            pass
    return prov


def _load_informal(minif2f_dir: Path, split: str) -> dict[str, str]:
    """Map problem_name → informal_statement from `informal/<split>/*.json` (if present)."""
    out: dict[str, str] = {}
    idir = minif2f_dir / "informal" / split
    if not idir.is_dir():
        return out
    for jf in idir.glob("*.json"):
        try:
            data = json.loads(jf.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        name = data.get("problem_name") or jf.stem
        if data.get("informal_statement"):
            out[name] = data["informal_statement"]
    return out


def load_minif2f(split: str, minif2f_dir: str | Path | None = None) -> list[Problem]:
    """Load miniF2F `Problem`s for one split. Raises FileNotFoundError if the data isn't staged."""
    root = Path(minif2f_dir) if minif2f_dir else DEFAULT_MINIF2F_DIR
    lean_file = root / "formal" / f"{split}.lean"
    if not lean_file.is_file():
        raise FileNotFoundError(
            f"miniF2F split not found: {lean_file}. Set config.data.minif2f_dir or stage the data."
        )
    text = lean_file.read_text()
    imports, opens = _parse_header(text)
    informal = _load_informal(root, split)
    git_prov = _git_provenance(root)

    problems: list[Problem] = []
    for name, statement, line_no in parse_minif2f_lean(text):
        prov = {
            "benchmark": "minif2f",
            "split": split,
            "source_file": str(lean_file),
            "source_line": line_no,
            **git_prov,
        }
        problems.append(
            Problem(
                name=name,
                statement=statement,
                benchmark="minif2f",
                split=split,
                imports=imports,
                opens=opens,
                informal_statement=informal.get(name),
                provenance=prov,
            )
        )
    return problems
