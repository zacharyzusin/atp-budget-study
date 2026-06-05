"""atp.agents — the proof-search agents (Task 0.4+).

Importing this package stays light (no model/Lean import at module load): the whole-proof agent
takes an injected `VLLMClient` + `Verifier`, so the fast suite drives it with scripted mocks.
"""

from atp.agents.state import (
    STOP_BUDGET,
    STOP_MAX_ROUNDS,
    STOP_NO_PROGRESS,
    STOP_SOLVED,
    AgentState,
    Attempt,
)
from atp.agents.whole_proof import WholeProofAgent

__all__ = [
    "AgentState",
    "Attempt",
    "WholeProofAgent",
    "STOP_SOLVED",
    "STOP_BUDGET",
    "STOP_MAX_ROUNDS",
    "STOP_NO_PROGRESS",
]
