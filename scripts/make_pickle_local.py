"""Create the Mathlib env pickle from a node-LOCAL copy of the Lean env, then validate unpickle.

Why local: a cold `import Mathlib` opens ~4.7k oleans off GPFS; under contention (measured ~3.8 MB/s
sequential, >45 min random on 2026-06-05) that times out. Copying .lake to node-local SSD first
makes
the import hit local disk (no GPFS token storm), so it completes in seconds-to-minutes regardless of
cluster load. We pickle the loaded env to ONE file, which every sweep worker then `unpickleEnvFrom`s
(a single sequential read) instead of repeating the open-storm.

Usage:  python scripts/make_pickle_local.py <local_project_path> <out_pickle_path>
The out pickle is written locally first (fast), validated by a fresh unpickle, and its size
reported;
the caller copies it to GPFS.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from atp.config import BASE_CONFIG, load_config
from atp.lean import ReplBackend, Theorem, Verifier


def main() -> int:
    local_proj = Path(sys.argv[1]).resolve()
    out_pickle = Path(sys.argv[2]).resolve()
    out_pickle.parent.mkdir(parents=True, exist_ok=True)
    if out_pickle.exists():
        out_pickle.unlink()

    os.environ["ATP_MATHLIB_PICKLE"] = str(out_pickle)
    cfg = load_config(BASE_CONFIG)

    print(f"[mkpickle] host={os.uname().nodename} local_proj={local_proj}", flush=True)
    print(f"[mkpickle] out_pickle={out_pickle}", flush=True)

    # --- create: cold import from LOCAL disk -> pickle ---
    b = ReplBackend(cfg, project_path=local_proj)
    assert b._env_built(), f"env not built at {local_proj} (repl={b._repl_path()})"
    v = Verifier.from_config(cfg, b)
    t0 = time.time()
    ok = v.verify(
        Theorem(name="probe", statement="theorem probe : True"),
        "theorem probe : True := by\n  trivial",
    )
    dt_import = time.time() - t0
    assert ok.ok, f"trivial-true rejected during pickle creation: {ok.feedback}"
    assert out_pickle.exists(), "import succeeded but no pickle was written"
    size_gb = out_pickle.stat().st_size / 1e9
    print(f"[mkpickle] IMPORT+pickle {dt_import:.0f}s | pickle={size_gb:.2f} GB", flush=True)
    b.close()

    # --- validate: fresh process unpickles the file (no import) + checks verdicts ---
    b2 = ReplBackend(cfg, project_path=local_proj)
    v2 = Verifier.from_config(cfg, b2)
    t1 = time.time()
    good = v2.verify(
        Theorem(name="p7", statement="theorem p7 : Nat.Prime 7"),
        "theorem p7 : Nat.Prime 7 := by\n  decide",
    )
    dt_unpickle = time.time() - t1
    bad = v2.verify(
        Theorem(name="bad", statement="theorem bad : (1:Nat)=2"),
        "theorem bad : (1:Nat) = 2 := by\n  rfl",
    )
    print(
        f"[mkpickle] UNPICKLE+verify {dt_unpickle:.0f}s | "
        f"p7.ok={good.ok} bad.ok={bad.ok} bad.reason={bad.reason}",
        flush=True,
    )
    b2.close()

    ok_all = good.ok and (not bad.ok) and bad.reason == "compile_error"
    print(f"[mkpickle] RESULT: {'PASS' if ok_all else 'FAIL'}", flush=True)
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
