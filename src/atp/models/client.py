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

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from atp.budget.meter import BudgetMeter
    from atp.config import ExperimentConfig


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
    """Build an OpenAI-/vLLM-shaped completion response (test + smoke helper)."""
    return {
        "choices": [{"text": text, "finish_reason": finish_reason}],
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

    def __init__(self, base_url: str, *, api_key: str = "EMPTY", timeout_s: float = 600.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        from openai import OpenAI  # lazy: keep module import cheap/optional

        self._client = OpenAI(base_url=self.base_url, api_key=api_key, timeout=timeout_s)

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

    @classmethod
    def from_config(
        cls,
        config: ExperimentConfig,
        transport: Transport,
        meter: BudgetMeter | None = None,
    ) -> VLLMClient:
        m = config.model
        return cls(
            model=m.name,
            transport=transport,
            meter=meter,
            temperature=m.temperature,
            top_p=m.top_p,
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
            "prompt": prompt,
            "max_tokens": allowed,
            "temperature": self.temperature,
            "top_p": self.top_p,
        }
        stops = self.stop if stop is None else stop
        if stops:
            payload["stop"] = list(stops)

        completion = self._parse(self.transport.complete(payload))

        if self.meter is not None:
            self.meter.spend(completion.completion_tokens, label=label)
        return completion

    @staticmethod
    def _parse(resp: dict[str, Any]) -> Completion:
        try:
            choice = resp["choices"][0]
            usage = resp["usage"]
            return Completion(
                text=choice.get("text", ""),
                prompt_tokens=int(usage["prompt_tokens"]),
                completion_tokens=int(usage["completion_tokens"]),
                finish_reason=choice.get("finish_reason") or "stop",
            )
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelServerError(f"unparseable completion response: {resp!r}") from exc
