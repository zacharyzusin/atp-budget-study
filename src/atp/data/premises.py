"""Build a BM25 premise corpus by parsing pinned-Mathlib `.lean` source (Phase 1 retrieval).

The retrieval component (`atp.agents.components.retrieval`) needs a premise corpus: a JSONL of
`{"name", "decl"}` library declarations to retrieve over. This module produces it by *lexically*
parsing Mathlib source — no Lean process, no GPU, runs on a login node. It is deliberately a
data-prep artifact, kept out of the agent hot path and out of `retrieval.py` (which only reads the
JSONL).

Parsing is approximate (full Lean elaboration is out of scope): we track the `namespace` stack to
qualify names, and capture each declaration's signature text from its keyword up to `:=`/`where`.
That is exactly what a lexical BM25 index wants — the lemma's qualified name plus its statement
text — and imperfect captures only add mild noise to a bag-of-words index, never unsoundness (the
prover still has to produce a Lean-checked proof; a retrieved premise is only a hint).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

# Declaration kinds worth retrieving as citeable premises (theorems/lemmas dominate; defs/abbrevs/
# instances are citeable too). Structures/classes are skipped to keep the corpus proof-relevant.
_DECL_KINDS = ("theorem", "lemma", "def", "abbrev", "instance")
_MODIFIERS = ("private", "protected", "noncomputable", "scoped", "local", "partial", "unsafe")

_DECL_RE = re.compile(
    r"^(?:(?:" + "|".join(_MODIFIERS) + r")\s+)*"
    r"(?P<kind>" + "|".join(_DECL_KINDS) + r")\s+"
    r"(?P<name>[^\s:({\[\]}=]+)"
)
_NAMESPACE_RE = re.compile(r"^namespace\s+(\S+)")
_SECTION_RE = re.compile(r"^section(?:\s+(\S+))?\s*$")
_END_RE = re.compile(r"^end(?:\s+(\S+))?\s*$")
_ATTR_RE = re.compile(r"^@\[[^\]]*\]\s*")
# Cut a signature at the first top-level proof/term assignment or `where`.
_SIG_CUT_RE = re.compile(r"\s*(:=|\bwhere\b).*$", re.DOTALL)


def strip_comments(text: str) -> str:
    """Remove Lean block comments `/- … -/` (incl. `/-- … -/` docstrings; nestable) and `--`."""
    out: list[str] = []
    depth = 0
    i = 0
    n = len(text)
    while i < n:
        two = text[i : i + 2]
        if two == "/-":
            depth += 1
            i += 2
        elif two == "-/" and depth:
            depth -= 1
            i += 2
        elif depth:
            i += 1
        elif two == "--":  # line comment: skip to end of line
            j = text.find("\n", i)
            i = n if j == -1 else j
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def _qualified(stack: list[tuple[str, str]], name: str) -> str:
    prefix = ".".join(n for kind, n in stack if kind == "ns")
    return f"{prefix}.{name}" if prefix else name


def extract_premises(text: str) -> list[tuple[str, str]]:
    """Parse one Lean source file → list of (qualified_name, signature_text), in source order.

    Names are qualified by the enclosing `namespace` stack; `section`s don't affect names. Each
    signature is the declaration text from its keyword up to (but excluding) `:=`/`where`, with
    multi-line headers joined.
    """
    lines = strip_comments(text).splitlines()
    stack: list[tuple[str, str]] = []
    premises: list[tuple[str, str]] = []
    i = 0
    while i < len(lines):
        line = _ATTR_RE.sub("", lines[i].strip())

        ns = _NAMESPACE_RE.match(line)
        if ns:
            stack.append(("ns", ns.group(1)))
            i += 1
            continue
        sec = _SECTION_RE.match(line)
        if sec:
            stack.append(("sec", sec.group(1) or ""))
            i += 1
            continue
        end = _END_RE.match(line)
        if end:
            target = end.group(1)
            if target is None:
                if stack:
                    stack.pop()
            else:
                # Pop down to and including the entry named `target`.
                for j in range(len(stack) - 1, -1, -1):
                    if stack[j][1] == target:
                        del stack[j:]
                        break
            i += 1
            continue

        m = _DECL_RE.match(line)
        if m:
            # Join continuation lines until the signature is closed by `:=`/`where`, bounded.
            header = line
            k = i
            while ":=" not in header and not re.search(r"\bwhere\b", header) and k - i < 24:
                k += 1
                if k >= len(lines):
                    break
                header += " " + lines[k].strip()
            sig = _SIG_CUT_RE.sub("", header).strip()
            premises.append((_qualified(stack, m.group("name")), sig))
            i = k + 1
            continue

        i += 1
    return premises


def iter_lean_files(root: str | Path) -> Iterator[Path]:
    """All `.lean` files under `root`, sorted for deterministic corpus order."""
    yield from sorted(Path(root).rglob("*.lean"))


def build_corpus(root: str | Path, *, limit: int | None = None) -> Iterator[dict[str, str]]:
    """Yield `{"name","decl"}` premises across all Mathlib source under `root`, deduped by name.

    First occurrence of a name wins (deterministic via sorted file + source order). `limit` caps the
    number of source files scanned (for smoke runs).
    """
    seen: set[str] = set()
    for f_idx, path in enumerate(iter_lean_files(root)):
        if limit is not None and f_idx >= limit:
            break
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for name, decl in extract_premises(text):
            if name and name not in seen:
                seen.add(name)
                yield {"name": name, "decl": decl}
