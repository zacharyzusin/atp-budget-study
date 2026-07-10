"""Whole-proof verification via the `leanprover-community/repl` persistent Lean process.

Why this and not PyPantograph (supersedes the 2026-06-04 Pantograph decision; see DECISIONS.md
2026-06-05): PyPantograph's REPL binary is compiled against a specific Lean toolchain and has NO
release matching the Goedel pin (Lean v4.9.0-rc1; its oldest tagged toolchain is v4.18.0). The
Goedel-pinned mathlib build already vendors `leanprover-community/repl` as a dependency package,
so we build that `repl` exe (version-matched by construction) and drive it over JSON on stdio.
Bonus: it needs NO Python package, and it is the exact REPL the Goedel/DeepSeek-Prover eval
harnesses use — strictly better for the measurement-validity guardrail.

Protocol (leanprover-community/repl): newline-delimited JSON, one object per command, objects
separated by a blank line. Load Mathlib ONCE as a base environment:

    >>> {"cmd": "import Mathlib"}                      -> {"env": 0}            # ~minutes cold
    >>> {"cmd": "<theorem ... := by ...>", "env": 0}   -> {"env": 1}           # accepted (no msgs)
    >>> {"cmd": "<false proof>", "env": 0}             -> {"messages": [...]}  # rejected (error)

Every proof is checked against the SAME base env 0 (independent of each other), so the slow Mathlib
load is paid once per process and amortized across the whole sweep. Messages are reformatted to
`name.lean:line:col: severity: text` so the Verifier's `errors.py` parsing/loophole/earliest-step
logic (Task 0.2) is reused unchanged.
"""

from __future__ import annotations

import json
import os
import pty
import queue
import subprocess
import threading
import time
import tty
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from atp.lean.backends import (
    _DECL_RE,
    LeanEnvNotReady,
    RawVerification,
    Theorem,
    compute_lean_path,
)

if TYPE_CHECKING:
    from atp.config import ExperimentConfig


def _encode_command(command: dict) -> bytes:
    """Serialize one REPL command to wire bytes: JSON + blank-line terminator, native UTF-8.

    ensure_ascii=False is load-bearing: send astral-plane (>U+FFFF) chars as raw UTF-8, NOT \\uXXXX
    escapes. The json default emits a UTF-16 surrogate pair (𝓝 -> \\ud835\\udcdd) that Lean's JSON
    reader mishandles, mangling the token -> "expected token". BMP notation (∫ -> \\u222b) round-
    trips fine, so this only bit astral math notation (𝓝 nhds, 𝓟 principal, 𝓤 uniformity, ...) —
    corrupting both such benchmark statements AND any model proof that emits them, every benchmark.
    """
    return (json.dumps(command, ensure_ascii=False) + "\n\n").encode("utf-8")


@runtime_checkable
class ReplTransport(Protocol):
    """A request/response channel to a Lean REPL. Real path = a subprocess; tests = scripted."""

    def request(self, command: dict, timeout_s: float) -> dict:
        """Send one JSON command, return the parsed JSON response. Raise TimeoutError on timeout."""
        ...

    def close(self) -> None: ...


class SubprocessReplTransport:
    """Drives the real `repl` executable as a long-lived subprocess, over a PTY.

    Why a PTY and not plain pipes: the repl responds with `IO.println` and never flushes stdout
    per command (REPL/Main.lean), and Lean block-buffers stdout when it is a pipe — so a response
    sits in the child's buffer until the process exits, and a persistent driver hangs forever
    (verified 2026-06-05: a trivial command got no pipe response in 25 s but a 1 s PTY response).
    A pseudo-terminal makes stdout line-buffered (flushed per line), which is exactly how the
    production harnesses (pexpect-based) drive this REPL. The slave is set raw to suppress echo
    and CRLF translation. A daemon thread assembles master-fd bytes into lines on a queue (the
    request path blocks on the queue with a wall-clock timeout); stderr is drained separately.
    """

    def __init__(self, exe: Path, cwd: Path, lean_path: str) -> None:
        self.exe = Path(exe)
        self.cwd = Path(cwd)
        self.lean_path = lean_path
        self._proc: subprocess.Popen | None = None
        self._master_fd: int | None = None
        self._out_q: queue.Queue[str | None] = queue.Queue()
        self._stderr_tail: deque[str] = deque(maxlen=50)

    def _ensure_proc(self) -> subprocess.Popen:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        env = dict(os.environ)
        env["LEAN_PATH"] = self.lean_path
        # Avoid the per-session SSH proxy leaking into the child (cluster proxy trap).
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            env.pop(k, None)
        master_fd, slave_fd = pty.openpty()
        tty.setraw(slave_fd)  # no echo, no LF->CRLF translation
        self._proc = subprocess.Popen(
            [str(self.exe)],
            cwd=str(self.cwd),
            env=env,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=subprocess.PIPE,
            close_fds=True,
        )
        os.close(slave_fd)  # parent keeps only the master end
        self._master_fd = master_fd
        self._out_q = queue.Queue()
        self._stderr_tail = deque(maxlen=50)
        threading.Thread(target=self._pump_stdout, args=(master_fd,), daemon=True).start()
        threading.Thread(target=self._pump_stderr, args=(self._proc,), daemon=True).start()
        return self._proc

    def _pump_stdout(self, master_fd: int) -> None:
        buf = b""
        try:
            while True:
                data = os.read(master_fd, 65536)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    self._out_q.put(line.decode("utf-8", "replace"))
        except OSError:  # EIO when the slave side closes (child exit) — expected
            pass
        finally:
            self._out_q.put(None)  # sentinel: process closed stdout / exited

    def _pump_stderr(self, proc: subprocess.Popen) -> None:
        if proc.stderr is None:
            return
        for raw in proc.stderr:
            self._stderr_tail.append(raw.decode("utf-8", "replace").rstrip("\n"))

    def request(self, command: dict, timeout_s: float) -> dict:
        self._ensure_proc()
        assert self._master_fd is not None
        os.write(self._master_fd, _encode_command(command))
        return self._read_response(timeout_s)

    def _read_response(self, timeout_s: float) -> dict:
        """Collect queued stdout lines until a blank line ends one JSON object (time-bounded)."""
        deadline = time.monotonic() + timeout_s
        lines: list[str] = []
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"REPL read timed out after {timeout_s:.0f}s")
            try:
                line = self._out_q.get(timeout=remaining)
            except queue.Empty:
                raise TimeoutError(f"REPL read timed out after {timeout_s:.0f}s") from None
            if line is None:  # process exited
                tail = "\n".join(self._stderr_tail)
                raise RuntimeError(f"REPL process exited unexpectedly. stderr tail:\n{tail}")
            if line.strip() == "":
                if lines:  # blank line after content => end of this response
                    break
                continue  # skip leading blank/echo lines before the JSON
            lines.append(line)
        return json.loads("\n".join(lines))

    def close(self) -> None:
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None
        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = None


class ScriptedReplTransport:
    """Deterministic transport for the fast suite: maps a sent command -> a canned JSON response."""

    def __init__(self, responder: Callable[[dict], dict]) -> None:
        self.responder = responder
        self.sent: list[dict] = []
        self.closed = False

    def request(self, command: dict, timeout_s: float) -> dict:
        self.sent.append(command)
        resp = self.responder(command)
        if resp.get("_timeout"):
            raise TimeoutError("scripted timeout")
        return resp

    def close(self) -> None:
        self.closed = True


class ReplBackend:
    """Real whole-proof verification via a persistent `leanprover-community/repl` process.

    Keeps ONE Lean process with Mathlib preloaded as base env 0; each `verify` runs the candidate
    proof against env 0 and accepts iff Lean emits no error-severity message. A `sorry` shows up as
    a warning (and in the REPL's `sorries` field) which the Verifier layer rejects as a loophole.

    The `repl` exe and the env are checked lazily so importing this module stays login-node safe;
    a real verify before the env is built raises a clear `LeanEnvNotReady`. The transport is
    injectable so the whole backend is exercised in the fast suite without a Lean install.
    """

    ENV_SUBDIR = "atp-lean-env"
    REPL_REL = Path(".lake/packages/REPL/.lake/build/bin/repl")

    def __init__(
        self,
        config: ExperimentConfig,
        project_path: str | Path | None = None,
        transport: ReplTransport | None = None,
    ) -> None:
        self.config = config
        self.toolchain = config.lean.toolchain
        self.mathlib_commit = config.lean.mathlib_commit
        self.mathlib_repo = config.lean.mathlib_repo
        self.timeout_s = config.lean.verify_timeout_s
        env_proj = os.environ.get("ATP_LEAN_PROJECT", "").strip()
        if project_path is not None:
            self.project_path = Path(project_path).resolve()
        elif env_proj:
            # Sweeps stage the env to node-local SSD (see slurm/sweep.sh) and point here, so the
            # cold `import Mathlib` reads oleans off local disk instead of the GPFS open-storm.
            self.project_path = Path(env_proj).resolve()
        else:
            root = Path(config.project.root)
            self.project_path = (root / config.lean.cache_dir / self.ENV_SUBDIR).resolve()
        self._transport = transport
        self._injected = transport is not None
        self._base_env: int | None = None

    # -- env wiring --------------------------------------------------------------------
    def _toolchain(self) -> str:
        tc_file = self.project_path / "lean-toolchain"
        if tc_file.exists():
            return tc_file.read_text().strip()
        return self.toolchain

    def _repl_path(self) -> Path:
        override = os.environ.get("ATP_REPL_BIN", "").strip()
        return Path(override) if override else (self.project_path / self.REPL_REL)

    def _env_built(self) -> bool:
        """True once mathlib oleans AND the repl exe exist (build_lean.sh + lake build repl)."""
        lake = self.project_path / ".lake"
        if not (self.project_path / "lake-manifest.json").exists() or not lake.exists():
            return False
        has_oleans = next(lake.rglob("Mathlib*.olean"), None) is not None
        return has_oleans and self._repl_path().exists()

    def _load_base_env(self, transport: ReplTransport) -> int:
        """Get a Mathlib-loaded base env via a fresh `import Mathlib` (NO pickle).

        DO NOT use the REPL pickle (`pickleTo`/`unpickleEnvFrom`). Confirmed harmful 2026-06-06:
        an `unpickleEnvFrom`-restored env is a lazy olean *index*, not a real snapshot, and it
        CANNOT evaluate compiled `@[init]` meta extensions — the Lean process aborts with
        `libc++abi: ... cannot evaluate '[init]' declaration 'Mathlib.Meta.NormNum.normNumExt' in
        the same module` the first time a proof uses `norm_num`/`nlinarith`/etc. That crash made the
        Phase-0 smoke score every real proof as "no parseable error" (pass@B = 0) while a fresh
        import handled the same proofs perfectly. A fresh `import Mathlib` off node-local SSD is
        ~95-141s — paid once per process (and once per restart), which is cheap and CORRECT. The
        cold-load problem is solved by node-local staging (slurm/sweep.sh + ATP_LEAN_PROJECT), not
        by pickling.
        """
        timeout = self._import_timeout_s()
        resp = transport.request({"cmd": "import Mathlib"}, timeout)
        if "env" not in resp:
            raise LeanEnvNotReady(f"REPL failed to load Mathlib: {resp}")
        return int(resp["env"])

    def _ensure_started(self) -> ReplTransport:
        if self._transport is not None and self._base_env is not None:
            return self._transport
        if self._transport is None:
            if not self._env_built():
                raise LeanEnvNotReady(
                    f"Lean env not built at {self.project_path} (need mathlib oleans + the repl "
                    f"exe at {self._repl_path()}). Run scripts/setup_lean_env.sh, sbatch "
                    "slurm/build_lean.sh, then `lake build repl` in the env."
                )
            self._transport = SubprocessReplTransport(
                exe=self._repl_path(),
                cwd=self.project_path,
                lean_path=compute_lean_path(self.project_path, self._toolchain()),
            )
        # Load Mathlib once -> base environment (slow cold start; reused across all verifies).
        self._base_env = self._load_base_env(self._transport)
        return self._transport

    def _import_timeout_s(self) -> float:
        """Ceiling for the one-time `import Mathlib` load (NOT the per-proof timeout).

        Cold on a fresh compute node, reading ~4.7k oleans off GPFS can take many minutes (a 600s
        ceiling timed out a real sweep node 2026-06-05 — warm it was ~130-270s). The load is paid
        once per worker, so the ceiling is generous; override via ATP_IMPORT_TIMEOUT_S.
        """
        override = os.environ.get("ATP_IMPORT_TIMEOUT_S", "").strip()
        if override:
            return float(override)
        return max(float(self.timeout_s), 1800.0)

    # -- source assembly ---------------------------------------------------------------
    def _build_repl_source(self, theorem: Theorem, proof: str) -> str:
        """Proof to run against the Mathlib-loaded base env.

        Mathlib is already imported in env 0, and `import` is only legal as the first command of a
        fresh env — so strip any `import ...` lines the model emitted. Preserve `open` namespaces:
        keep the model's, else prepend the theorem's.

        CRITICAL (found live 2026-07-06, see PROGRESS.md/DECISIONS.md that date — same root cause as
        `PantographBackend._build_source`, a separate class): continuation-style templates
        (`DeepSeekV15Template`/`GoedelSFTTemplate`) ask the model to continue directly after `:= by`,
        so their extracted proof is a BARE tactic body with no `theorem`/`lemma`/`example`
        declaration. Without reconstructing that declaration here, the bare tactics land as top-level
        commands against env 0 — a guaranteed parse error, not a real proof failure. If the proof
        already declares its own goal (self-contained, e.g. `WholeProofTemplate`'s models), leave it
        untouched.
        NOTE on `set_option maxHeartbeats 0` (found live 2026-07-06, see PROGRESS.md/DECISIONS.md
        that date): the DeepSeek-Prover-V1.5/Goedel-Prover-SFT family's own official header always
        sets this (disables Lean's elaboration heartbeat limit — without it, otherwise-valid
        nlinarith/field_simp/simp-heavy proofs can spuriously fail, indistinguishable from a
        genuinely wrong proof). Prepended here as its own top-level command, same convention as
        `open`. Deliberately NOT adding `import Aesop` here (unlike `PantographBackend._build_source`,
        which builds an isolated fresh file and needs it): env 0 already has Mathlib imported, whose
        own modules transitively depend on Aesop, so its tactics are already available — and `import`
        is only legal as a fresh env's FIRST command, so injecting one here as a later command would
        be a genuine (avoidable) Lean error, not a fix.
        """
        body_lines = [ln for ln in proof.splitlines() if not ln.lstrip().startswith("import ")]
        body = "\n".join(body_lines).strip("\n")
        if not _DECL_RE.search(body):
            body = theorem.statement.rstrip() + " := by\n" + body
        has_open = any(ln.lstrip().startswith("open ") for ln in body_lines)
        if theorem.opens and not has_open:
            body = "open " + " ".join(theorem.opens) + "\n" + body
        if "set_option maxHeartbeats" not in body:
            body = "set_option maxHeartbeats 0\n" + body
        return body

    def _format_response(self, theorem: Theorem, resp: dict) -> tuple[bool, str]:
        """Map a REPL response to (success, Lean-style diagnostic text for errors.py)."""
        lines: list[str] = []
        has_error = False
        for msg in resp.get("messages", []):
            sev = str(msg.get("severity", "error")).lower()
            if sev == "error":
                has_error = True
            pos = msg.get("pos") or {}
            line = pos.get("line", 0) or 0
            col = pos.get("column", 0) or 0
            data = str(msg.get("data", "")).replace("\n", "\n  ")  # indent => folded by parser
            lines.append(f"{theorem.name}.lean:{line}:{col}: {sev}: {data}")
        # `sorries` are reported out-of-band; surface as a sorry warning so the Verifier rejects it.
        for s in resp.get("sorries", []):
            pos = s.get("pos") or {}
            line = pos.get("line", 0) or 0
            col = pos.get("column", 0) or 0
            lines.append(f"{theorem.name}.lean:{line}:{col}: warning: declaration uses 'sorry'")
        # A genuinely accepted command returns a NEW environment id (see module docstring). A
        # response carrying neither `env` nor any message is malformed/spurious -- e.g. a wedged or
        # cross-talked REPL returning `{}` under co-location -- and must NOT be scored as verified.
        # (This silent false-success inflated the ProofNet# reviewer/memory cells, 2026-06-14.)
        if "env" not in resp and not has_error:
            lines.append(
                f"{theorem.name}.lean:0:0: error: REPL_INFRA_ERROR malformed response "
                f"(no 'env', no messages): {resp!r}"
            )
            return False, "\n".join(lines)
        return (not has_error), "\n".join(lines)

    # -- verification ------------------------------------------------------------------
    # If the Lean process dies mid-verify (infra glitch, NOT a compile error), restart and retry
    # once on the fresh process — otherwise a transient crash would score a *valid* proof as failed
    # (the agent would then waste budget refining a correct proof). The restart's fresh
    # `import Mathlib` gives a healthy env. A clean compile error / timeout never retries.
    INFRA_RETRIES = 1

    def verify(self, theorem: Theorem, proof: str) -> RawVerification:
        source = self._build_repl_source(theorem, proof)
        t0 = time.perf_counter()
        last_infra: str | None = None
        for _attempt in range(self.INFRA_RETRIES + 1):
            transport = self._ensure_started()
            command = {"cmd": source, "env": self._base_env}
            try:
                resp = transport.request(command, float(self.timeout_s))
            except TimeoutError as exc:
                self._restart()  # process may be mid-elaboration; restart for the next proof
                return RawVerification(
                    success=False,
                    output=f"TimeoutError: {exc}",
                    elapsed_s=time.perf_counter() - t0,
                    timed_out=True,
                )
            except Exception as exc:  # pragma: no cover - depends on live process
                # Grab the child's stderr tail BEFORE restart so a crash is visible in raw_output.
                tail = ""
                stail = getattr(transport, "_stderr_tail", None)
                if stail:
                    tail = "\n  stderr: " + " | ".join(list(stail)[-5:])
                last_infra = f"REPL_INFRA_ERROR {type(exc).__name__}: {exc}{tail}"
                self._restart()  # next iteration reloads a fresh (healthy) env and retries
                continue
            elapsed = time.perf_counter() - t0
            success, output = self._format_response(theorem, resp)
            return RawVerification(success=success, output=output, elapsed_s=elapsed)
        # Exhausted retries — report the last infra error (distinct prefix, not a compile error).
        return RawVerification(
            success=False,
            output=last_infra or "REPL_INFRA_ERROR: verify failed",
            elapsed_s=time.perf_counter() - t0,
        )

    def elaborate(self, theorem: Theorem, source: str) -> dict:
        """Elaborate `source` against base env 0, returning its sorry goals (Phase 6).

        Unlike `verify` (pass/fail), this surfaces the REPL `sorries` so a `<prefix> … sorry` source
        yields the intermediate goal state(s). Returns
        `{"errors": <#error-severity msgs>, "sorries": [goal_text, …], "infra_error": bool}`.
        A clean single-goal truncation is `errors == 0 and len(sorries) == 1`; its `sorries[0]` is
        the `deep_state` for the closing-targeted pair. Mirrors `verify`'s infra-retry/restart.
        """
        src = self._build_repl_source(theorem, source)
        for _attempt in range(self.INFRA_RETRIES + 1):
            transport = self._ensure_started()
            try:
                resp = transport.request({"cmd": src, "env": self._base_env}, float(self.timeout_s))
            except TimeoutError:
                self._restart()
                return {"errors": 1, "sorries": [], "infra_error": True, "timed_out": True}
            except Exception:  # pragma: no cover - live process only
                self._restart()
                continue
            n_err = sum(
                1 for m in resp.get("messages", [])
                if str(m.get("severity", "error")).lower() == "error"
            )
            goals = [s.get("goal", "") for s in resp.get("sorries", [])]
            return {"errors": n_err, "sorries": goals, "infra_error": False}
        return {"errors": 1, "sorries": [], "infra_error": True}

    def _restart(self) -> None:
        """Drop the (possibly wedged) process so the next verify reloads Mathlib cleanly."""
        if self._injected:
            return  # scripted transport in tests: don't tear it down
        if self._transport is not None:
            try:
                self._transport.close()
            finally:
                self._transport = None
                self._base_env = None

    def close(self) -> None:
        if self._transport is not None:
            self._transport.close()
        self._transport = None
        self._base_env = None
