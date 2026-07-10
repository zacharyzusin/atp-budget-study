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
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from atp.config import ExperimentConfig

# The single source of truth for "does this text declare a theorem/lemma/example?" — used by both
# backends (source assembly + RawVerification.declares_goal) and imported by repl.py. Previously
# ALSO duplicated in verifier.py (a second copy checking the pre-assembly proof text, not the
# compiled source) — that copy was the root cause of the no_goal false-rejection bug for
# continuation-style templates (AUDIT_PLAN.md Task A1, 2026-07-10); removed, this is now the only
# copy, and verifier.py consumes `RawVerification.declares_goal` instead of matching it directly.
_DECL_RE = re.compile(r"(?m)^\s*(?:theorem|lemma|example)\b")


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
    # The informal (natural-language) problem statement, when the benchmark provides one (242/244
    # for miniF2F). Threaded through so DeepSeekV15Template/GoedelSFTTemplate can render it as the
    # `/-- ... -/` doc-comment their official inference scripts always include before the theorem —
    # dropped at this boundary was a confirmed bug (found live 2026-07-06, see PROGRESS.md/
    # DECISIONS.md that date).
    informal_statement: str | None = None


@dataclass(frozen=True)
class RawVerification:
    """A backend's raw verdict before loophole/timeout policy is applied."""

    success: bool  # Lean compiled the proof with no errors
    output: str  # raw compiler / REPL output (stderr+messages)
    elapsed_s: float = 0.0
    timed_out: bool = False
    # Did the source ACTUALLY COMPILED (post backend assembly -- imports/opens/theorem-header
    # reconstruction, NOT the model's raw extracted text) declare a real goal (theorem/lemma/
    # example)? Only the backend knows this: for continuation-style templates
    # (DeepSeekV15Template/GoedelSFTTemplate/BFSProverTemplate) the model's own completion never
    # restates the theorem by design, so a check against the raw extracted proof is structurally
    # always False for that whole template family -- see AUDIT_PLAN.md Task A1 / PROGRESS.md
    # 2026-07-10. Default True so a "dumb" ScriptedBackend/test that doesn't care about this axis
    # keeps its old (success-implies-a-real-goal) behavior; a backend that wants the no_goal
    # soundness gate to fire must compute this from what it actually compiled and pass it explicitly.
    declares_goal: bool = True


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


def always(
    success: bool, output: str = "", timed_out: bool = False, declares_goal: bool = True
) -> ScriptedBackend:
    """Convenience: a backend that returns the same verdict for every call."""
    return ScriptedBackend(
        lambda _t, _p: RawVerification(
            success, output, timed_out=timed_out, declares_goal=declares_goal
        )
    )


def compute_lean_path(project_path: Path, toolchain: str) -> str:
    """Compute LEAN_PATH from the filesystem (avoids `lake env`, which can hang on an elan lock).

    Toolchain stdlib lib + every dependency package's build lib + the project's own build lib,
    shared by every real backend. Overridable via `ATP_LEAN_PATH` (e.g. a slurm script that
    pre-staged oleans to node-local disk).

    IMPORTANT — Lean version layout: newer toolchains put oleans under `.lake/build/lib/lean/`,
    but the Goedel pin (v4.9.0-rc1) puts them directly under `.lake/build/lib/`. We probe BOTH so
    the same code targets either stack; without the bare `build/lib` branch, LEAN_PATH would miss
    all of mathlib on the v4.9.0-rc1 env (verified empirically on this cluster, 2026-06-05).
    """
    override = os.environ.get("ATP_LEAN_PATH", "").strip()
    if override:
        return override
    parts: list[str] = []
    elan_home = Path(os.environ.get("ELAN_HOME", Path.home() / ".elan"))
    mangled = toolchain.replace("/", "--").replace(":", "---")
    tc_lib = elan_home / "toolchains" / mangled / "lib" / "lean"
    if tc_lib.exists():
        parts.append(str(tc_lib))

    def _libs(base: Path) -> None:
        # Prefer the nested `lib/lean` (new layout); fall back to the bare `lib` (v4.9 layout).
        # Probe RECURSIVELY: some packages (e.g. importGraph, REPL) keep NO top-level `*.olean`,
        # only nested ones (`build/lib/ImportGraph/*.olean`). A non-recursive glob skips them, and
        # dropping importGraph — a mathlib dependency — makes `import Mathlib` silently yield an
        # EMPTY env (no error), which corrupts every verdict. `next(rglob, ...)` stops at the first
        # hit, so this stays cheap even for mathlib's thousands of oleans. (Bug found 2026-06-05.)
        for candidate in (base / "lean", base):
            if candidate.is_dir() and next(candidate.rglob("*.olean"), None) is not None:
                parts.append(str(candidate))
                return

    packages = project_path / ".lake" / "packages"
    if packages.exists():
        for pkg in sorted(packages.iterdir()):
            lib = pkg / ".lake" / "build" / "lib"
            if lib.exists():
                _libs(lib)
    proj_lib = project_path / ".lake" / "build" / "lib"
    if proj_lib.exists():
        _libs(proj_lib)
    return os.pathsep.join(parts) or "."


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
        """LEAN_PATH for this env (delegates to the shared, version-aware `compute_lean_path`)."""
        return compute_lean_path(self.project_path, self._toolchain())

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
        """Assemble a self-contained Lean file: ensure imports/opens AND the theorem declaration
        are present, then the proof body.

        Three shapes, in order:
        1. The model emitted a complete file (has its own `import` line, e.g. `WholeProofTemplate`'s
           models, which re-emit the whole fenced block including imports+theorem) -> use as-is.
        2. No `import` line, but the proof already restates its own `theorem`/`lemma`/`example`
           declaration -> just prepend imports/opens (the original fallback behavior).
        3. No `import` line AND no declaration (continuation-style templates —
           `DeepSeekV15Template`/`GoedelSFTTemplate` — ask the model to continue directly after
           `:= by`, so the extracted proof is a BARE tactic body) -> reconstruct
           `<imports>\n<opens>\n\n<theorem statement> := by\n<proof>`. Missing this case is a
           confirmed bug (found live 2026-07-06, see PROGRESS.md/DECISIONS.md that date): bare
           tactics landing at the top level of the file are a guaranteed Lean parse error, not a
           real proof failure — `theorem_stmt := by` must precede them.
        """
        if any(line.lstrip().startswith("import ") for line in proof.splitlines()):
            # A complete self-contained file -> only ensure the heartbeat safety net is present
            # (AUDIT_PLAN.md Task A2, 2026-07-10: this branch previously returned `proof` verbatim,
            # diverging from `ReplBackend._build_repl_source`, which applies `maxHeartbeats`
            # unconditionally regardless of shape. `PantographBackend` is not used by any production
            # run — `eval/run.py` wires `ReplBackend` exclusively — so this was never live-impactful,
            # but kept consistent for any future caller.).
            if "set_option maxHeartbeats" in proof:
                return proof
            lines = proof.splitlines()
            insert_at = 0
            for i, ln in enumerate(lines):
                if ln.lstrip().startswith("import "):
                    insert_at = i + 1
                else:
                    break
            lines.insert(insert_at, "set_option maxHeartbeats 0")
            return "\n".join(lines)
        # `import Aesop` + `set_option maxHeartbeats 0`: the DeepSeek-Prover-V1.5/Goedel-Prover-SFT
        # family's own official header convention (verified byte-for-byte 2026-07-06 against
        # quick_start.py / eval/step1_inference.py's LEAN4_DEFAULT_HEADER — see PROGRESS.md/
        # DECISIONS.md that date). These two non-"complete file" branches are, in current practice,
        # only exercised by that family's continuation-style templates, so applying their own
        # official convention here is correct, not an unjustified default. Missing
        # `set_option maxHeartbeats 0` in particular disables Lean's default elaboration-heartbeat
        # limit — without it, otherwise-valid nlinarith/field_simp/simp-heavy proofs can spuriously
        # fail, indistinguishable from a genuinely wrong proof.
        header = [f"import {imp}" for imp in (theorem.imports or ("Mathlib",))]
        header.append("import Aesop")
        header.append("")
        header.append("set_option maxHeartbeats 0")
        if theorem.opens:
            header.append("")
            header.append("open " + " ".join(theorem.opens))
        if _DECL_RE.search(proof):
            return "\n".join(header) + "\n\n" + proof
        return "\n".join(header) + "\n\n" + theorem.statement.rstrip() + " := by\n" + proof

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
        # Compute against the ASSEMBLED `source` actually compiled (post header reconstruction),
        # not the raw `proof` param -- see RawVerification.declares_goal docstring.
        declares_goal = bool(_DECL_RE.search(source))
        return RawVerification(
            success=not has_error, output=output, elapsed_s=elapsed, declares_goal=declares_goal
        )
