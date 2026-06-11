"""Premise retrieval component (Phase 1 ablation axis).

Inject library lemmas that look relevant to the goal into the fresh-proposal prompt, so the prover
can cite them instead of rediscovering them. The plan's axis is *none vs BM25 vs ReProver, sweeping
#premises*; this implements the **BM25 baseline** (lexical, no GPU, no training). ReProver (a neural
retriever needing a trained index) is deferred — `backend: reprover` raises until built.

Retrieves over a **premise corpus** (`RetrievalCfg.corpus`): a JSONL of `{"name", "decl"}` library
declarations. That corpus is a separate data-prep artifact (a Mathlib declaration dump), NOT built
at runtime — so the retrieval arm of the sweep has a prerequisite (build/stage the corpus), flagged
in PROGRESS.md. Without a corpus the component cannot be enabled (`build_components` raises) rather
than silently retrieving nothing.

Decorates **fresh proposals only** (consistent with the other prompt-side components): the ablation
question is "does handing the prover relevant lemmas up front help at fixed budget?". Pure
CPU/string work — fast, login-node testable with a tiny temp corpus.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from rank_bm25 import BM25Okapi

from atp.agents.components.base import Component, PromptContext
from atp.config import RetrievalCfg

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
_RETRIEVAL_PREFIX = "Potentially useful library lemmas (you may cite these):"


def _tokenize(text: str) -> list[str]:
    """Lexical tokens for BM25: lowercased identifier runs (Lean ids drive the lexical match)."""
    return _TOKEN_RE.findall(text.lower())


@dataclass(frozen=True)
class Premise:
    name: str
    decl: str

    def line(self) -> str:
        decl = " ".join(self.decl.split())
        return f"- {self.name} : {decl}" if decl else f"- {self.name}"


def load_premises(path: str | Path) -> list[Premise]:
    """Read a premises JSONL ({"name","decl"} per line). Blank lines ignored; bad lines raise."""
    premises: list[Premise] = []
    for raw in Path(path).read_text().splitlines():
        if not raw.strip():
            continue
        obj = json.loads(raw)
        premises.append(Premise(name=str(obj["name"]), decl=str(obj.get("decl", ""))))
    if not premises:
        raise ValueError(f"premise corpus {path} is empty")
    return premises


class _BM25Index:
    """Thin BM25Okapi wrapper: build over premises once, return the top-k for a query string."""

    def __init__(self, premises: list[Premise]) -> None:
        self._premises = premises
        # Index over name + decl so both the lemma's identifier and its statement contribute.
        self._bm25 = BM25Okapi([_tokenize(f"{p.name} {p.decl}") for p in premises])

    def top_k(self, query: str, k: int) -> list[Premise]:
        scores = self._bm25.get_scores(_tokenize(query))
        # Highest score first; stable on ties via index. Cap k at corpus size.
        order = sorted(range(len(self._premises)), key=lambda i: (-scores[i], i))
        return [self._premises[i] for i in order[: min(k, len(self._premises))]]


@dataclass(frozen=True)
class Retrieval(Component):
    """BM25 premise retrieval: inject the top-k library lemmas for the goal into fresh proposals."""

    index: _BM25Index
    k: int
    name: str = "retrieval"

    @classmethod
    def from_config(cls, cfg: RetrievalCfg) -> Retrieval:
        if cfg.backend == "reprover":
            raise NotImplementedError(
                "retrieval backend 'reprover' is deferred (needs a trained neural index); "
                "use backend 'bm25' for now"
            )
        if cfg.backend != "bm25":
            raise ValueError(f"retrieval enabled but backend is {cfg.backend!r}; expected 'bm25'")
        if not cfg.corpus:
            raise ValueError("retrieval bm25 requires `corpus` (a premises JSONL path)")
        return cls(index=_BM25Index(load_premises(cfg.corpus)), k=cfg.k)

    def decorate_prompt(self, prompt: str, ctx: PromptContext) -> str:
        if ctx.kind != "propose":
            return prompt
        hits = self.index.top_k(ctx.theorem.statement, self.k)
        if not hits:
            return prompt
        block = "\n".join(p.line() for p in hits)
        return f"{prompt}\n\n{_RETRIEVAL_PREFIX}\n{block}"
