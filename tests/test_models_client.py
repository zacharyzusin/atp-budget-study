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
