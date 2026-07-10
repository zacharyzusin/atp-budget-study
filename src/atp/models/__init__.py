"""atp.models — prover model client (vLLM/OpenAI-compatible) + prompt templates.

Importing this package must NOT pull in `openai`/`torch` (the real transport imports `openai`
lazily), so the fast test suite stays login-node safe.
"""

from atp.models.client import (
    Completion,
    ModelServerError,
    OpenAITransport,
    ScriptedTransport,
    Transport,
    VLLMClient,
    chat_completion_response,
    completion_response,
)
from atp.models.templates import (
    BFSProverTemplate,
    DeepSeekV15Template,
    GoedelSFTTemplate,
    PromptTemplate,
    TacticTemplate,
    WholeProofTemplate,
    candidate_tactic_lines,
    extract_lean_block,
    get_template,
    template_from_config,
)

__all__ = [
    "Completion",
    "ModelServerError",
    "OpenAITransport",
    "ScriptedTransport",
    "Transport",
    "VLLMClient",
    "chat_completion_response",
    "completion_response",
    "PromptTemplate",
    "TacticTemplate",
    "WholeProofTemplate",
    "BFSProverTemplate",
    "DeepSeekV15Template",
    "GoedelSFTTemplate",
    "candidate_tactic_lines",
    "extract_lean_block",
    "get_template",
    "template_from_config",
]
