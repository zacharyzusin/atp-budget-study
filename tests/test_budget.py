"""Tests for the budget meter (Task 0.3).

The meter is the project's core experimental knob, so accounting must be exact and exhaustion
must be a clean, catchable signal (not a crash). Restartability is part of "done" (rule 0.3).
"""

from __future__ import annotations

import pytest

from atp.budget import BudgetExhausted, BudgetMeter, LedgerEntry
from atp.config import BASE_CONFIG, load_config


def test_budget_meter_accounting():
    """Tokens are summed exactly across calls and the ledger tracks the running total."""
    m = BudgetMeter(limit=100)
    assert m.remaining == 100 and m.spent == 0

    m.spend(30, label="propose")
    m.spend(45, label="refine")
    assert m.spent == 75
    assert m.remaining == 25
    assert [e.cumulative for e in m.ledger] == [30, 75]
    assert m.ledger[0] == LedgerEntry(label="propose", tokens=30, cumulative=30)


def test_request_clamps_to_remaining():
    """`request` never hands back more than what's left, so generations stay inside budget."""
    m = BudgetMeter(limit=100)
    m.spend(90)
    assert m.request(50) == 10  # clamped to remaining
    assert m.request(5) == 5  # under remaining -> unchanged


def test_stops_at_limit():
    """Once spent reaches the limit the meter is exhausted and `request` refuses to go further."""
    m = BudgetMeter(limit=50)
    allowed = m.request(50)
    m.spend(allowed)
    assert m.exhausted
    assert m.remaining == 0
    with pytest.raises(BudgetExhausted):
        m.request(1)


def test_budget_exhausted_is_graceful():
    """The exhaustion signal is a catchable exception carrying the numbers, not a crash."""
    m = BudgetMeter(limit=10)
    m.spend(10)
    with pytest.raises(BudgetExhausted) as exc:
        m.request(5)
    err = exc.value
    assert err.spent == 10
    assert err.limit == 10
    assert err.requested == 5
    # state is intact after the signal -> caller can persist partial progress
    assert m.spent == 10
    assert len(m.ledger) == 1


def test_check_guard():
    m = BudgetMeter(limit=10)
    m.check()  # not exhausted -> no raise
    m.spend(10)
    with pytest.raises(BudgetExhausted):
        m.check()


def test_snapshot_restore_roundtrip():
    """A requeued job rebuilds the exact spend + ledger from a checkpoint (rule 0.3)."""
    m = BudgetMeter(limit=200)
    m.spend(40, label="a")
    m.spend(60, label="b")
    restored = BudgetMeter.restore(m.snapshot())
    assert restored.limit == 200
    assert restored.spent == 100
    assert restored.remaining == 100
    assert restored.ledger == m.ledger
    # continues accounting from where it left off
    restored.spend(50, label="c")
    assert restored.spent == 150


def test_from_config_defaults_to_max_budget():
    cfg = load_config(BASE_CONFIG)
    m = BudgetMeter.from_config(cfg)
    assert m.limit == max(cfg.budget.values)


def test_from_config_validates_value():
    cfg = load_config(BASE_CONFIG)
    chosen = cfg.budget.values[0]
    assert BudgetMeter.from_config(cfg, value=chosen).limit == chosen
    with pytest.raises(ValueError):
        BudgetMeter.from_config(cfg, value=999_999)  # not a configured budget point


def test_rejects_negative():
    with pytest.raises(ValueError):
        BudgetMeter(limit=-1)
    m = BudgetMeter(limit=10)
    with pytest.raises(ValueError):
        m.spend(-1)
    with pytest.raises(ValueError):
        m.request(-1)
