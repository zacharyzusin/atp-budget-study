"""Client for the prover served by vLLM (OpenAI-compatible HTTP API).

The agent never imports vLLM or torch; it talks to a persistent vLLM server over HTTP (see
`slurm/` + the `endpoint_file` the server writes). This module is the thin, **budget-aware** seam:

  * a `Transport` abstracts the actual HTTP call so fast tests inject a `ScriptedTransport`
    (no server, exact token control) while production uses `OpenAITransport` (vLLM completions);
  * `VLLMClient.generate` clamps `max_tokens` to the remaining budget, parses the server's
    `usage.completion_tokens`, and charges that exact count to the meter.

Token accounting uses the server-reported `completion_tokens` — never a local estimate — so the
budget is exact and matches what the GPU actually generated.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from atp.budget.meter import BudgetMeter
    from atp.config import ExperimentConfig

# vLLM's 400 when prompt+max_tokens exceeds the context window. The message reliably reports both
# the window and the prompt's own token count, e.g.:
#   "This model's maximum context length is 40960 tokens. However, you requested 41190 tokens
#    (20710 in the messages, 20480 in the completion)."
# We parse those numbers to shrink the completion to fit, then retry (_complete_fitting_context).
_CTX_LEN_RE = re.compile(
    r"maximum context length is (\d+) tokens.*?\((\d+) in the (?:messages|prompt)",
    re.DOTALL,
)


class ModelServerError(RuntimeError):
    """The server returned a response we couldn't interpret (missing choices/usage, etc.)."""


@dataclass(frozen=True)
class Completion:
    """One generation result, with the token accounting the budget meter needs."""

    text: str
    prompt_tokens: int
    completion_tokens: int
    finish_reason: str  # "stop" | "length" | ...

    @property
    def truncated(self) -> bool:
        """True when generation hit `max_tokens` (the budget clamp) rather than a stop token."""
        return self.finish_reason == "length"


@runtime_checkable
class Transport(Protocol):
    """Turns a `/v1/completions` request payload into the server's JSON response (as a dict)."""

    def complete(self, payload: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class ScriptedTransport:
    """Deterministic transport for tests/`make smoke`: `responder(payload) -> response dict`.

    Records every payload so tests can assert on what was sent (e.g. the clamped `max_tokens`).
    """

    responder: Callable[[dict[str, Any]], dict[str, Any]]
    calls: list[dict[str, Any]] = field(default_factory=list)

    def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(payload)
        return self.responder(payload)


def completion_response(
    text: str,
    completion_tokens: int,
    *,
    prompt_tokens: int = 0,
    finish_reason: str = "stop",
) -> dict[str, Any]:
    """Build an OpenAI-/vLLM-shaped `/v1/completions` response (test + smoke helper)."""
    return {
        "choices": [{"text": text, "finish_reason": finish_reason}],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def chat_completion_response(
    text: str,
    completion_tokens: int,
    *,
    prompt_tokens: int = 0,
    finish_reason: str = "stop",
) -> dict[str, Any]:
    """Build a `/v1/chat/completions` response (chat shape: choices[].message.content)."""
    return {
        "choices": [
            {"message": {"role": "assistant", "content": text}, "finish_reason": finish_reason}
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


class OpenAITransport:
    """Real transport: vLLM's OpenAI-compatible `/v1/completions` via the `openai` SDK.

    Imports `openai` lazily so this module stays importable in environments where only the light
    core is needed; the SDK itself is in the light core (see pyproject).
    """

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str = "EMPTY",
        timeout_s: float = 3600.0,
        max_retries: int = 4,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        from openai import OpenAI  # lazy: keep module import cheap/optional

        # max_retries lets the SDK absorb transient connection/5xx blips (incl. APITimeoutError)
        # rather than surfacing a one-off failure to the agent. timeout must exceed the longest
        # single generation (max_model_len//2 tokens at the concurrent per-stream rate).
        self._client = OpenAI(
            base_url=self.base_url, api_key=api_key, timeout=timeout_s, max_retries=max_retries
        )

    @classmethod
    def from_endpoint_file(cls, path: str, **kwargs: Any) -> OpenAITransport:
        """Read `host:port` (written by the vLLM slurm job) and build a transport for it."""
        from pathlib import Path

        raw = Path(path).read_text().strip()
        base = raw if raw.startswith("http") else f"http://{raw}"
        if "/v1" not in base:
            base = base.rstrip("/") + "/v1"
        return cls(base, **kwargs)

    def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Route to chat vs text completions by payload shape (chat carries `messages`). The chat
        # endpoint makes vLLM apply the model's own chat template (needed for Qwen3 reasoners).
        if "messages" in payload:
            resp = self._client.chat.completions.create(**payload)
        else:
            resp = self._client.completions.create(**payload)
        # Normalize the SDK object to the plain dict shape the client parses.
        return resp.model_dump()


@dataclass
class VLLMClient:
    """Budget-aware client over a `Transport`.

    `meter` is optional so the client is usable for un-metered probing (e.g. `make smoke`), but the
    agent loop always passes one: every `generate` clamps to and charges the per-problem budget.
    """

    model: str
    transport: Transport
    meter: BudgetMeter | None = None
    default_max_tokens: int = 2048
    temperature: float = 1.0
    top_p: float = 0.95
    stop: tuple[str, ...] = ()
    seed: int | None = None  # vLLM sampling seed for reproducibility (set per eval seed)
    chat: bool = False  # True -> /v1/chat/completions (server applies the model's chat template)
    context_margin_tokens: int = 32  # safety gap below the window when clamping a too-long request
    context_min_completion: int = 256  # below this much room, the request can't do useful work

    @classmethod
    def from_config(
        cls,
        config: ExperimentConfig,
        transport: Transport,
        meter: BudgetMeter | None = None,
    ) -> VLLMClient:
        m = config.model
        # ATP_SERVED_MODEL overrides the requested model name without editing the config — used by
        # the Phase 6 eval to target a LoRA adapter served ALONGSIDE the base (vLLM --lora-modules
        # <name>=<dir>): set it to the adapter name to eval the FT model, leave unset for the base
        # control, against the SAME held-out config + server.
        return cls(
            model=os.environ.get("ATP_SERVED_MODEL") or m.name,
            transport=transport,
            meter=meter,
            temperature=m.temperature,
            top_p=m.top_p,
            chat=m.chat_completions,
        )

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int | None = None,
        stop: tuple[str, ...] | None = None,
        label: str = "",
    ) -> Completion:
        """Generate a completion, clamped to and charged against the budget (if a meter is set).

        Propagates `BudgetExhausted` from the meter when nothing remains — a clean stop signal the
        agent catches to save partial state rather than crash.
        """
        want = self.default_max_tokens if max_tokens is None else max_tokens
        allowed = self.meter.request(want) if self.meter is not None else want

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": allowed,
            "temperature": self.temperature,
            "top_p": self.top_p,
        }
        if self.chat:
            payload["messages"] = [{"role": "user", "content": prompt}]
        else:
            payload["prompt"] = prompt
        stops = self.stop if stop is None else stop
        if stops:
            payload["stop"] = list(stops)
        if self.seed is not None:
            payload["seed"] = self.seed

        completion = self._parse(self._complete_fitting_context(payload))

        if self.meter is not None:
            self.meter.spend(completion.completion_tokens, label=label)
        return completion

    def _complete_fitting_context(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send the request; if vLLM rejects it for exceeding the context window, shrink the
        completion to what's left and retry ONCE.

        A long refinement prompt (theorem + prior proof + Lean error) plus the requested
        `max_tokens` (up to max_model_len//2) can exceed the model's context window, which vLLM
        rejects with a 400 *before* generating — so the retry is essentially free. We parse the
        window and prompt-token count from the error, set `max_tokens = window - prompt - margin`
        (also capped by the original request so the budget is still respected), and retry. If the
        prompt alone leaves less than `context_min_completion`, there's no useful room — re-raise
        and let the caller (sweep containment) record the cell as failed. Regression: baseline
        10304768 cell imo_2019_p1 seed=0 hit this 400 (PROGRESS.md 2026-06-07).
        """
        try:
            return self.transport.complete(payload)
        except Exception as exc:  # noqa: BLE001 - narrowed immediately by parsing the message
            m = _CTX_LEN_RE.search(str(exc))
            if m is None:
                raise  # not a context-length 400 — propagate (timeouts, etc. handled elsewhere)
            window, prompt_tokens = int(m.group(1)), int(m.group(2))
            room = window - prompt_tokens - self.context_margin_tokens
            room = min(room, int(payload.get("max_tokens", room)))
            if room < self.context_min_completion:
                raise
            return self.transport.complete({**payload, "max_tokens": room})

    @staticmethod
    def _parse(resp: dict[str, Any]) -> Completion:
        try:
            choice = resp["choices"][0]
            usage = resp["usage"]
            # /v1/completions puts the text in choice["text"]; /v1/chat/completions in
            # choice["message"]["content"]. Support both so the client is endpoint-agnostic.
            text = choice.get("text")
            if text is None:
                text = (choice.get("message") or {}).get("content", "")
            return Completion(
                text=text or "",
                prompt_tokens=int(usage["prompt_tokens"]),
                completion_tokens=int(usage["completion_tokens"]),
                finish_reason=choice.get("finish_reason") or "stop",
            )
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelServerError(f"unparseable completion response: {resp!r}") from exc
