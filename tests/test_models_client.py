"""Tests for the vLLM client + budget integration (Task 0.3).

Fast tests mock the HTTP server with a `ScriptedTransport`, so token counts are exact and we can
assert on the request payload (e.g. that `max_tokens` was clamped to the remaining budget). The
real `OpenAITransport` (needs a running vLLM server) is exercised by smoke/eval on a GPU node.
"""

from __future__ import annotations

import pytest

from atp.budget import BudgetExhausted, BudgetMeter
from atp.config import BASE_CONFIG, load_config
from atp.models import (
    Completion,
    ModelServerError,
    ScriptedTransport,
    VLLMClient,
    chat_completion_response,
    completion_response,
)


def _const_transport(text="proof", completion_tokens=10, **kw):
    return ScriptedTransport(lambda _p: completion_response(text, completion_tokens, **kw))


def test_generate_parses_and_charges_meter():
    meter = BudgetMeter(limit=100)
    client = VLLMClient(model="m", transport=_const_transport("by trivial", 12), meter=meter)
    res = client.generate("prompt", label="propose")
    assert isinstance(res, Completion)
    assert res.text == "by trivial"
    assert res.completion_tokens == 12
    assert meter.spent == 12  # exact server-reported count charged to the ledger
    assert meter.ledger[-1].label == "propose"


def test_no_meter_mode_works():
    """The client is usable without a meter (e.g. `make smoke`)."""
    client = VLLMClient(model="m", transport=_const_transport("x", 5))
    res = client.generate("prompt", max_tokens=50)
    assert res.completion_tokens == 5


def test_max_tokens_clamped_to_remaining_budget():
    meter = BudgetMeter(limit=100)
    meter.spend(90)
    transport = _const_transport("x", 5)
    client = VLLMClient(model="m", transport=transport, meter=meter)
    client.generate("prompt", max_tokens=50)
    # asked for 50, only 10 left -> server is told 10
    assert transport.calls[-1]["max_tokens"] == 10


def test_accounting_across_calls_stops_at_budget():
    """N calls account tokens exactly and the meter stops once the budget is spent."""
    meter = BudgetMeter(limit=30)
    client = VLLMClient(model="m", transport=_const_transport("x", 10), meter=meter)
    client.generate("p", max_tokens=10)
    client.generate("p", max_tokens=10)
    client.generate("p", max_tokens=10)
    assert meter.spent == 30
    assert meter.exhausted
    with pytest.raises(BudgetExhausted):
        client.generate("p", max_tokens=10)  # clean stop, no 4th server call


def test_budget_exhausted_is_clean_signal():
    meter = BudgetMeter(limit=10)
    meter.spend(10)
    transport = _const_transport("x", 5)
    client = VLLMClient(model="m", transport=transport, meter=meter)
    with pytest.raises(BudgetExhausted):
        client.generate("prompt")
    assert transport.calls == []  # never hit the server when there's no budget


def test_passes_stop_and_sampling_params():
    transport = _const_transport("x", 1)
    client = VLLMClient(model="m", transport=transport, temperature=0.7, top_p=0.9)
    client.generate("prompt", stop=("\n\n",))
    payload = transport.calls[-1]
    assert payload["temperature"] == 0.7
    assert payload["top_p"] == 0.9
    assert payload["stop"] == ["\n\n"]
    assert payload["model"] == "m"


def test_truncated_flag():
    client = VLLMClient(model="m", transport=_const_transport("x", 8, finish_reason="length"))
    res = client.generate("prompt")
    assert res.truncated is True


def test_bad_response_raises_model_server_error():
    client = VLLMClient(model="m", transport=ScriptedTransport(lambda _p: {"oops": True}))
    with pytest.raises(ModelServerError):
        client.generate("prompt")


def test_from_config_pulls_sampling_params():
    cfg = load_config(BASE_CONFIG)
    meter = BudgetMeter(limit=1000)
    client = VLLMClient.from_config(cfg, transport=_const_transport(), meter=meter)
    assert client.model == cfg.model.name
    assert client.temperature == cfg.model.temperature
    assert client.top_p == cfg.model.top_p
    assert client.chat == cfg.model.chat_completions  # base.yaml -> chat (Qwen3 reasoning prover)


def test_from_config_honors_served_model_override(monkeypatch):
    # ATP_SERVED_MODEL retargets the request to a LoRA adapter served alongside the base (Phase 6)
    cfg = load_config(BASE_CONFIG)
    monkeypatch.setenv("ATP_SERVED_MODEL", "goedel-B-seed0")
    client = VLLMClient.from_config(cfg, transport=_const_transport())
    assert client.model == "goedel-B-seed0"
    monkeypatch.delenv("ATP_SERVED_MODEL")
    assert VLLMClient.from_config(cfg, transport=_const_transport()).model == cfg.model.name


# -- chat-completions mode (the Goedel-V2 path) ----------------------------------------
def test_chat_mode_sends_messages_not_prompt_and_parses_content():
    """chat=True must hit the chat endpoint shape: send `messages`, read `message.content`."""
    transport = ScriptedTransport(
        lambda _p: chat_completion_response("```lean4\nby simp\n```", 7)
    )
    meter = BudgetMeter(limit=100)
    client = VLLMClient(model="m", transport=transport, meter=meter, chat=True)
    res = client.generate("solve this", label="propose", max_tokens=50)
    sent = transport.calls[-1]
    assert sent["messages"] == [{"role": "user", "content": "solve this"}]
    assert "prompt" not in sent
    assert res.text == "```lean4\nby simp\n```"
    assert res.completion_tokens == 7 and meter.spent == 7


def test_completions_mode_unchanged_sends_prompt():
    transport = _const_transport("by trivial", 3)
    client = VLLMClient(model="m", transport=transport, chat=False)
    res = client.generate("p")
    assert transport.calls[-1]["prompt"] == "p"
    assert "messages" not in transport.calls[-1]
    assert res.text == "by trivial"


def test_chat_mode_still_clamps_budget():
    meter = BudgetMeter(limit=100)
    meter.spend(95)
    transport = ScriptedTransport(lambda _p: chat_completion_response("x", 5))
    client = VLLMClient(model="m", transport=transport, meter=meter, chat=True)
    client.generate("p", max_tokens=50)
    assert transport.calls[-1]["max_tokens"] == 5  # clamped to remaining


# -- context-window clamp (regression: baseline 10304768 imo_2019_p1 BadRequest 400) -----------

def _ctx_error(prompt_tokens, completion, window=40960):
    """vLLM's real 400 message shape for prompt+completion exceeding the context window."""
    return (
        f"Error code: 400 - {{'message': \"This model's maximum context length is {window} "
        f"tokens. However, you requested {prompt_tokens + completion} tokens ({prompt_tokens} "
        f"in the messages, {completion} in the completion).\", 'type': 'BadRequestError'}}"
    )


def _ctx_overflow_transport(prompt_tokens=20710, window=40960):
    """First call raises vLLM's context-length 400 (sized from the requested max_tokens); second
    call (clamped) succeeds, echoing its max_tokens so the test can assert the clamp value."""
    state = {"n": 0}

    def responder(payload):
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError(_ctx_error(prompt_tokens, payload["max_tokens"], window))
        return chat_completion_response(
            "ok proof", payload["max_tokens"], prompt_tokens=prompt_tokens
        )

    return ScriptedTransport(responder)


def test_context_overflow_is_clamped_and_retried():
    transport = _ctx_overflow_transport()
    client = VLLMClient(model="m", transport=transport, meter=None, chat=True,
                        context_margin_tokens=32)
    res = client.generate("p", max_tokens=20480)
    assert len(transport.calls) == 2  # one rejected, one clamped retry
    # room = 40960 - 20710 - 32 = 20218, and <= the original 20480 request
    assert transport.calls[1]["max_tokens"] == 40960 - 20710 - 32
    assert res.text == "ok proof"


def test_context_clamp_respects_budget_cap():
    """The clamped max_tokens never exceeds the original (budget-limited) request."""
    meter = BudgetMeter(limit=500)  # remaining 500 -> first request clamped to 500
    transport = _ctx_overflow_transport(prompt_tokens=100)
    client = VLLMClient(model="m", transport=transport, meter=meter, chat=True)
    client.generate("p", max_tokens=20480)
    # window-room would be huge (40960-100-32), but the budget capped the request to 500
    assert transport.calls[1]["max_tokens"] == 500


def test_no_room_left_reraises_for_containment():
    """If the prompt alone leaves less than context_min_completion, re-raise so the sweep records
    the cell as failed rather than issuing a pointless tiny generation."""
    transport = _ctx_overflow_transport(prompt_tokens=40900)  # window 40960 -> room ~28 < 256
    client = VLLMClient(model="m", transport=transport, meter=None, chat=True)
    with pytest.raises(RuntimeError):
        client.generate("p", max_tokens=20480)
    assert len(transport.calls) == 1  # no retry attempted


def test_non_context_error_propagates_unchanged():
    """A non-context error (e.g. a timeout) must not be swallowed by the context-clamp path."""
    def responder(_p):
        raise RuntimeError("Request timed out.")
    transport = ScriptedTransport(responder)
    client = VLLMClient(model="m", transport=transport, meter=None, chat=True)
    with pytest.raises(RuntimeError, match="timed out"):
        client.generate("p", max_tokens=100)
    assert len(transport.calls) == 1
