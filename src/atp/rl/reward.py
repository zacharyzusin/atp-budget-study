"""Verifier-grounded reward for the Stage C GRPO probe.

The reward IS the eval verdict — nothing bespoke. A rollout earns **+1.0 iff the extracted Lean
proof VERIFIES AND passes the soundness gate** (`Verifier.ok`, i.e. `reason == "ok"`, which already
rejects `sorry`/`admit`/`native_decide`/loophole and no-goal truncations). Otherwise **0.0**, with a
small **+format_bonus** when the rollout at least emitted a parseable ```lean4 block — this keeps
degenerate non-parseable rollouts from stalling learning without rewarding wrong proofs. **No
progress/depth shaping** in the probe (STAGE_C_PROBE_SPEC.md §3/§6): binary reward minimizes the
reward-hacking surface the G2 soundness gate must police.

Inference-faithful by construction: the proof is pulled out with the SAME
`WholeProofTemplate.extract_proof` and judged by the SAME `Verifier` the held-out eval uses, so a
reward of 1.0 means exactly "would count as a solve in the eval."

Reward computation (Lean, CPU) is the throughput bottleneck, so a batch is verified across a
**persistent pool of thread-local REPL backends** — each worker thread owns one backend and
amortizes its `import Mathlib`, like the eval sweep (`atp.eval.run.build_solve_fn`). The pool
lives for the whole run; a fresh executor per step would re-import Mathlib every step.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from atp.lean.backends import LeanBackend, Theorem
from atp.lean.verifier import Verifier
from atp.models.templates import WholeProofTemplate, extract_lean_block
from atp.rl.diversity import diversity_snapshot

if TYPE_CHECKING:
    from atp.config import ExperimentConfig

# The verifier's verdict vocabulary (atp.lean.verifier.VerifyResult.reason).
REASONS: tuple[str, ...] = ("ok", "compile_error", "timeout", "loophole", "no_goal")
# The would-be-false-positive surface a naive (un-hardened) pipeline would accept: proofs with
# sorry/admit holes (loophole) or no-goal truncations. G2 (soundness) watches THIS rate base->RL.
UNSOUND_REASONS: tuple[str, ...] = ("loophole", "no_goal")


def normalize_completion(completion: Any) -> str:
    """trl passes completions as plain strings (text prompts) or as conversational message lists
    (chat prompts). Return the assistant text either way."""
    if isinstance(completion, str):
        return completion
    if isinstance(completion, list):  # [{"role": "assistant", "content": "..."}]
        return "".join(
            m.get("content", "") for m in completion if isinstance(m, dict)
        )
    return str(completion)


def score(reason: str, has_fence: bool, *, format_bonus: float) -> float:
    """Pure reward from a verifier verdict. +1.0 for a verified+sound proof; else the format bonus
    iff the rollout emitted a parseable Lean fence; else 0.0."""
    if reason == "ok":
        return 1.0
    return format_bonus if has_fence else 0.0


@dataclass
class SoundnessTally:
    """Running per-reason counts for G2 (soundness) + G1 (solve-rate) logging."""

    counts: dict[str, int] = field(default_factory=lambda: {r: 0 for r in REASONS})
    other: int = 0
    total: int = 0

    def add(self, reason: str) -> None:
        self.total += 1
        if reason in self.counts:
            self.counts[reason] += 1
        else:
            self.other += 1

    @property
    def solve_rate(self) -> float:
        return self.counts["ok"] / self.total if self.total else 0.0

    @property
    def unsound_rate(self) -> float:
        """loophole + no_goal over ALL rollouts — the false-positive surface (G2)."""
        n = sum(self.counts[r] for r in UNSOUND_REASONS)
        return n / self.total if self.total else 0.0

    def snapshot(self) -> dict[str, float]:
        out: dict[str, float] = {"reward/solve_rate": self.solve_rate,
                                 "reward/unsound_rate": self.unsound_rate}
        for r in REASONS:
            out[f"reward/frac_{r}"] = self.counts[r] / self.total if self.total else 0.0
        return out


def _coerce_seq(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    if isinstance(value, str):
        return (value,) if value else default
    return tuple(value)


class LeanReward:
    """trl `reward_funcs` callable: verify each rollout in Lean and return the binary reward.

    `backend_factory()` builds one `LeanBackend` (a REPL subprocess); we keep one per worker thread
    in a persistent thread pool. `__call__(prompts, completions, **cols)` receives the extra dataset
    columns (`name`, `statement`, `opens`, `imports`) aligned with `completions`.
    """

    def __init__(
        self,
        config: ExperimentConfig,
        backend_factory: Callable[[], LeanBackend],
        *,
        n_workers: int = 8,
        format_bonus: float = 0.05,
    ) -> None:
        self.__name__ = "lean_verified"  # trl uses this to label the reward column in its logs
        self._config = config
        self._backend_factory = backend_factory
        self._format_bonus = format_bonus
        self._template = WholeProofTemplate()
        self._tls = threading.local()
        self._created: list[LeanBackend] = []
        self._created_lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=max(1, n_workers))
        self.tally = SoundnessTally()  # cumulative over the whole run
        self._batch_metrics: list[dict[str, float]] = []  # per-call; drained by the callback

    def _verifier(self) -> Verifier:
        v = getattr(self._tls, "verifier", None)
        if v is None:
            backend = self._backend_factory()
            with self._created_lock:
                self._created.append(backend)
            v = Verifier.from_config(self._config, backend)
            self._tls.verifier = v
        return v

    def _score_one(self, text: str, theorem: Theorem) -> tuple[float, str]:
        proof = self._template.extract_proof(theorem, text)
        has_fence = extract_lean_block(text) is not None
        result = self._verifier().verify(theorem, proof)
        return score(result.reason, has_fence, format_bonus=self._format_bonus), result.reason

    def __call__(
        self,
        prompts: list[Any] | None = None,
        completions: list[Any] | None = None,
        **columns: Any,
    ) -> list[float]:
        completions = completions or []
        names = columns.get("name") or [f"thm_{i}" for i in range(len(completions))]
        statements = columns.get("statement") or [""] * len(completions)
        opens_col = columns.get("opens") or [None] * len(completions)
        imports_col = columns.get("imports") or [None] * len(completions)

        theorems = [
            Theorem(
                name=str(names[i]),
                statement=str(statements[i]),
                imports=_coerce_seq(imports_col[i], ("Mathlib",)),
                opens=_coerce_seq(opens_col[i], ()),
            )
            for i in range(len(completions))
        ]
        texts = [normalize_completion(c) for c in completions]

        results = list(self._pool.map(
            lambda args: self._score_one(*args), zip(texts, theorems, strict=True)
        ))
        rewards = [r for r, _ in results]
        batch = SoundnessTally()
        for _, reason in results:
            self.tally.add(reason)
            batch.add(reason)
        # Per-batch metrics for the G2 (soundness) / G3 (diversity) monitors; the callback drains
        # these into the trainer logs. G1 (held-out solve-rate) is the SEPARATE eval, not this.
        metrics = {"reward/batch_solve_rate": batch.solve_rate,
                   "reward/batch_unsound_rate": batch.unsound_rate, "reward/n": float(batch.total)}
        metrics.update(diversity_snapshot(texts))
        self._batch_metrics.append(metrics)
        return rewards

    def drain_metrics(self) -> dict[str, float]:
        """Mean of the per-batch metrics accumulated since the last drain (cleared after).
        Returns {} if no batches were scored — the callback then logs nothing."""
        if not self._batch_metrics:
            return {}
        keys = self._batch_metrics[0].keys()
        n = len(self._batch_metrics)
        out = {k: sum(m[k] for m in self._batch_metrics) / n for k in keys}
        out["reward/cum_solve_rate"] = self.tally.solve_rate
        out["reward/cum_unsound_rate"] = self.tally.unsound_rate
        self._batch_metrics.clear()
        return out

    def close(self) -> None:
        self._pool.shutdown(wait=False)
        with self._created_lock:
            backends = list(self._created)
        for b in backends:
            close = getattr(b, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # noqa: BLE001 - best-effort teardown
                    pass
