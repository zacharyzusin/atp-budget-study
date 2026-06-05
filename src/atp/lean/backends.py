"""Lean verification backends.

A backend turns (theorem, candidate proof) into a `RawVerification` (did Lean accept it, plus the
raw compiler output). The agent/verifier layer is backend-agnostic so we can:
  * unit-test orchestration with a `ScriptedBackend` (no Lean), and
  * swap in the real `LeanDojoBackend` once `scratch/lean-cache` is built (deferred — disk hold).

Nothing here imports lean-dojo at module load; the real backend imports it lazily so the package
stays login-node importable for the fast suite.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
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


class PantographBackend:
    """Real whole-proof verification via a persistent PyPantograph Lean REPL.

    Chosen over lean-dojo (see DECISIONS.md 2026-06-04): proven on this cluster, much lighter, and
    keeps ONE long-lived Lean process with Mathlib preloaded (slow startup, reused across calls).

    Whole-proof check: `server.check_compile(source)` → accepted iff Lean emits no error-severity
    message (an incomplete proof surfaces as an "unsolved goals" *error*; a `sorry` surfaces as a
    *warning*, which the Verifier layer then rejects as a loophole). The raw messages are formatted
    `name.lean:line:col: severity: text` so the Verifier's existing `errors.py` parsing, loophole,
    and earliest-failing-step logic (Task 0.2) are reused unchanged.

    `pantograph` is imported lazily and the env is checked, so the package stays login-node
    importable and the fast suite is unaffected; a real verify before the env is built raises a
    clear `LeanEnvNotReady`.
    """

    ENV_SUBDIR = "atp-lean-env"  # the lake project under cache_dir (scripts/setup_lean_env.sh)

    def __init__(self, config: ExperimentConfig, project_path: str | Path | None = None) -> None:
        self.config = config
        self.toolchain = config.lean.toolchain
        self.mathlib_commit = config.lean.mathlib_commit
        self.mathlib_repo = config.lean.mathlib_repo
        self.timeout_s = config.lean.verify_timeout_s
        # `project_path` override lets the contract test point at any built lake env (e.g. the
        # sibling v4.29.0 stack for plumbing/CI vs. the Goedel-pinned env for real numbers).
        if project_path is not None:
            self.project_path = Path(project_path).resolve()
        else:
            root = Path(config.project.root)
            self.project_path = (root / config.lean.cache_dir / self.ENV_SUBDIR).resolve()
        self._server = None  # lazily started PyPantograph Server

    def _toolchain(self) -> str:
        """Prefer the env's own lean-toolchain so LEAN_PATH matches whatever stack we target."""
        tc_file = self.project_path / "lean-toolchain"
        if tc_file.exists():
            return tc_file.read_text().strip()
        return self.toolchain

    # -- env wiring --------------------------------------------------------------------
    def _env_built(self) -> bool:
        """True once the from-source mathlib build has produced oleans (slurm/build_lean.sh)."""
        lake = self.project_path / ".lake"
        if not (self.project_path / "lake-manifest.json").exists() or not lake.exists():
            return False
        # Cheap existence check: at least one mathlib olean present.
        return next(lake.rglob("Mathlib*.olean"), None) is not None or next(
            lake.rglob("*.olean"), None
        ) is not None

    def _lean_path(self) -> str:
        """Compute LEAN_PATH from the filesystem (avoids `lake env` which can hang on an elan lock).

        Mirrors the sibling project's approach: toolchain lib + every package's build lib + project.
        Overridable via `ATP_LEAN_PATH` (e.g. a slurm script that pre-staged to local disk).
        """
        override = os.environ.get("ATP_LEAN_PATH", "").strip()
        if override:
            return override
        parts: list[str] = []
        elan_home = Path(os.environ.get("ELAN_HOME", Path.home() / ".elan"))
        mangled = self._toolchain().replace("/", "--").replace(":", "---")
        tc_lib = elan_home / "toolchains" / mangled / "lib" / "lean"
        if tc_lib.exists():
            parts.append(str(tc_lib))
        packages = self.project_path / ".lake" / "packages"
        if packages.exists():
            for pkg in sorted(packages.iterdir()):
                lib = pkg / ".lake" / "build" / "lib" / "lean"
                if lib.exists():
                    parts.append(str(lib))
        proj_lib = self.project_path / ".lake" / "build" / "lib" / "lean"
        if proj_lib.exists():
            parts.append(str(proj_lib))
        return os.pathsep.join(parts) or "."

    def _get_server(self):
        if self._server is not None:
            return self._server
        try:
            from pantograph.server import Server
        except ImportError as exc:  # pragma: no cover - env-dependent
            raise LeanEnvNotReady(
                "pantograph not installed (pip install pantograph into the env). "
                f"Pinned target: toolchain={self.toolchain}, mathlib={self.mathlib_repo}"
                f"@{self.mathlib_commit}."
            ) from exc
        if not self._env_built():
            raise LeanEnvNotReady(
                f"Lean env not built at {self.project_path} (no oleans). Run "
                "scripts/setup_lean_env.sh, then sbatch slurm/build_lean.sh (from-source build; "
                "cache-get missed for the fork)."
            )
        self._server = Server(
            imports=["Mathlib"],
            project_path=str(self.project_path),
            lean_path=self._lean_path(),
            timeout=self.timeout_s,
        )
        return self._server

    # -- verification ------------------------------------------------------------------
    def _build_source(self, theorem: Theorem, proof: str) -> str:
        """Assemble a self-contained Lean file: ensure imports/opens are present, then the proof."""
        if any(line.lstrip().startswith("import ") for line in proof.splitlines()):
            return proof  # model emitted a complete file
        header = [f"import {imp}" for imp in (theorem.imports or ("Mathlib",))]
        if theorem.opens:
            header.append("open " + " ".join(theorem.opens))
        return "\n".join(header) + "\n\n" + proof

    def _format_message(self, theorem: Theorem, msg) -> str:
        sev = msg.severity.name.lower()
        pos = getattr(msg, "pos", None)
        line = getattr(pos, "line", 0) or 0
        col = getattr(pos, "column", 0) or 0
        # Indent continuation lines so the errors.py parser folds them into this message.
        data = str(getattr(msg, "data", "")).replace("\n", "\n  ")
        return f"{theorem.name}.lean:{line}:{col}: {sev}: {data}"

    def verify(self, theorem: Theorem, proof: str) -> RawVerification:
        server = self._get_server()
        source = self._build_source(theorem, proof)
        t0 = time.perf_counter()
        try:
            units = server.check_compile(source)
        except Exception as exc:  # pragma: no cover - depends on live Lean process
            elapsed = time.perf_counter() - t0
            timed_out = "timeout" in str(exc).lower() or isinstance(exc, TimeoutError)
            return RawVerification(
                success=False,
                output=f"{type(exc).__name__}: {exc}",
                elapsed_s=elapsed,
                timed_out=timed_out,
            )
        elapsed = time.perf_counter() - t0
        messages = [m for unit in units for m in unit.messages]
        output = "\n".join(self._format_message(theorem, m) for m in messages)
        has_error = any(m.severity.name.upper() == "ERROR" for m in messages)
        return RawVerification(success=not has_error, output=output, elapsed_s=elapsed)
