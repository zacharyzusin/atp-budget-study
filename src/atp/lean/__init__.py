"""atp.lean — Lean 4 interaction layer (verification + error parsing).

Public API. Importing this package must NOT pull in pantograph (the real backend imports it lazily),
so the fast test suite stays login-node safe.
"""

from atp.lean.backends import (
    LeanBackend,
    LeanEnvNotReady,
    PantographBackend,
    RawVerification,
    ScriptedBackend,
    Theorem,
    always,
)
from atp.lean.errors import (
    LOOPHOLE_DEFAULT,
    FailingStep,
    LeanMessage,
    ParsedLeanOutput,
    attribute_failure,
    find_loopholes,
    parse_lean_output,
)
from atp.lean.verifier import Verifier, VerifyResult

__all__ = [
    "LeanBackend",
    "LeanEnvNotReady",
    "PantographBackend",
    "RawVerification",
    "ScriptedBackend",
    "Theorem",
    "always",
    "LOOPHOLE_DEFAULT",
    "FailingStep",
    "LeanMessage",
    "ParsedLeanOutput",
    "attribute_failure",
    "find_loopholes",
    "parse_lean_output",
    "VerifyResult",
    "Verifier",
]
