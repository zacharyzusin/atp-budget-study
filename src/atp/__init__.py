"""atp — Budget-bounded agentic theorem proving.

Top-level package. Keep this import light: nothing here may import torch/vllm/lean-dojo
at module load time, so the fast test suite stays runnable on a login node in seconds.
"""

from atp.config import (
    ExperimentConfig,
    apply_env,
    config_hash,
    dump_config,
    load_config,
)

__version__ = "0.1.0"

__all__ = [
    "ExperimentConfig",
    "apply_env",
    "config_hash",
    "dump_config",
    "load_config",
    "__version__",
]
