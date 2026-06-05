"""atp.eval — eval harness + metrics (Task 0.6).

`run_sweep` is the restartable driver; `metrics`/`summarize` compute the pass@B curve and friends;
`build_run_manifest` records reproducibility. matplotlib is only pulled by `plot_pass_at_b` (lazy),
so importing this package stays login-node light.
"""

from atp.eval.harness import RunResult, run_sweep
from atp.eval.manifest import REQUIRED_KEYS, build_run_manifest
from atp.eval.metrics import (
    PassAtB,
    effective_accuracy,
    pass_at_b,
    summarize,
    tokens_to_first_proof,
)
from atp.eval.records import ProblemResult

__all__ = [
    "ProblemResult",
    "PassAtB",
    "pass_at_b",
    "tokens_to_first_proof",
    "effective_accuracy",
    "summarize",
    "run_sweep",
    "RunResult",
    "build_run_manifest",
    "REQUIRED_KEYS",
]
