"""Lean verification backends.

A backend turns (theorem, candidate proof) into a `RawVerification` (did Lean accept it, plus the
raw compiler output). The agent/verifier layer is backend-agnostic so we can:
  * unit-test orchestration with a `ScriptedBackend` (no Lean), and
  * swap in the real `LeanDojoBackend` once `scratch/lean-cache` is built (deferred — disk hold).

Nothing here imports lean-dojo at module load; the real backend imports it lazily so the package
stays login-node importable for the fast suite.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from atp.config import ExperimentConfig


class LeanEnvNotReady(RuntimeError):
    """Raised when a real Lean verification is attempted before the toolchain/mathlib is built."""


@dataclass(frozen=True)
class Theorem:
    """A theorem to prove, enough to build a compilable Lean source for whole-proof verification."""

    name: str
    statement: str  # e.g. "theorem foo (n : Nat) : n + 0 = n"
    imports: tuple[str, ...] = ("Mathlib",)
    opens: tuple[str, ...] = ()
    source_file: str | None = None  # provenance: benchmark file this came from


@dataclass(frozen=True)
class RawVerification:
    """A backend's raw verdict before loophole/timeout policy is applied."""

    success: bool  # Lean compiled the proof with no errors
    output: str  # raw compiler / REPL output (stderr+messages)
    elapsed_s: float = 0.0
    timed_out: bool = False


@runtime_checkable
class LeanBackend(Protocol):
    def verify(self, theorem: Theorem, proof: str) -> RawVerification: ...


@dataclass
class ScriptedBackend:
    """Deterministic backend for tests and `make smoke`.

    `responder` maps (theorem, proof) -> RawVerification, so tests can model any compiler outcome
    without a Lean install.
    """

    responder: Callable[[Theorem, str], RawVerification]
    calls: list[tuple[Theorem, str]] = field(default_factory=list)

    def verify(self, theorem: Theorem, proof: str) -> RawVerification:
        self.calls.append((theorem, proof))
        return self.responder(theorem, proof)


def always(success: bool, output: str = "", timed_out: bool = False) -> ScriptedBackend:
    """Convenience: a backend that returns the same verdict for every call."""
    return ScriptedBackend(lambda _t, _p: RawVerification(success, output, timed_out=timed_out))


class LeanDojoBackend:
    """Real whole-proof verification against the pinned Lean+mathlib env.

    DEFERRED: the actual `lake build` of mathlib into `scratch/lean-cache` is on hold for disk.
    This class lazily imports lean-dojo and raises a clear `LeanEnvNotReady` until that build
    exists, so the package imports fine and the fast suite is unaffected. The `verify` body lands
    with the build step (still Task 0.2).
    """

    def __init__(self, config: ExperimentConfig) -> None:
        self.config = config
        self.toolchain = config.lean.toolchain
        self.mathlib_commit = config.lean.mathlib_commit
        self.mathlib_repo = config.lean.mathlib_repo
        self.cache_dir = config.lean.cache_dir
        self.timeout_s = config.lean.verify_timeout_s

    def _require_env(self) -> None:
        try:
            import lean_dojo  # noqa: F401
        except ImportError as exc:  # pragma: no cover - env-dependent
            raise LeanEnvNotReady(
                "lean-dojo not installed and scratch/lean-cache not built (deferred on disk hold). "
                f"Pinned target: toolchain={self.toolchain}, mathlib={self.mathlib_repo}"
                f"@{self.mathlib_commit}."
            ) from exc

    def verify(self, theorem: Theorem, proof: str) -> RawVerification:  # pragma: no cover
        self._require_env()
        raise LeanEnvNotReady(
            "Real Lean verification is implemented once scratch/lean-cache is built (Task 0.2 "
            "build step, deferred). Use ScriptedBackend for fast tests until then."
        )
