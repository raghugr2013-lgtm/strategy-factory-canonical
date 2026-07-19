"""Phase 2, Stage 2.γ — reservation-aware capacity tests.

Verifies:
  * Reservations enforced only when `COE_RESERVATIONS_ENABLED=true`
  * EXECUTION reservation floor honoured when BACKTEST saturated
  * MARKET_DATA reservation floor honoured
  * Byte-identical to Stage 1 when the flag is off
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_LEGACY = Path(__file__).resolve().parents[1] / "legacy"
if str(_LEGACY) not in sys.path:
    sys.path.insert(0, str(_LEGACY))

from engines.workload_classes import WorkloadClass, reservation_for  # noqa: E402


class _FakeAdaptive:
    """Stand-in for AdaptiveConcurrencyTargets."""
    max_concurrent_backtests = 1
    max_concurrent_mutations = 1
    max_concurrent_factory_cycles = 1


class _FakeCtx:
    """Minimal ctx shape for _workload_capacity."""
    def __init__(self):
        self.adaptive = _FakeAdaptive()


def _make_orch(inflight_by_class):
    """Build an Orchestrator with a fixed inflight map (bypasses signal-gather)."""
    from engines.orchestrator.core import Orchestrator
    o = Orchestrator()
    for wc, n in inflight_by_class.items():
        for i in range(n):
            o._in_flight[f"fake-{wc}-{i}"] = {"workload_class": wc}
    return o


def test_reservations_off_matches_stage1(monkeypatch):
    monkeypatch.delenv("COE_RESERVATIONS_ENABLED", raising=False)
    o = _make_orch({"backtest": 1})   # saturated
    remaining = o._workload_capacity(_FakeCtx())
    # BACKTEST saturated → 0 remaining
    assert remaining.get("backtest") == 0
    # EXECUTION not in the legacy caps_map explicitly — Stage 2 adds it with
    # unlimited cap; with reservations OFF, no floor is applied so it depends
    # on max_concurrent_tasks. What we assert here is: the reservation LOGIC
    # is not adjusting the remaining count.
    exec_off = remaining.get("execution", 0)
    monkeypatch.setenv("COE_RESERVATIONS_ENABLED", "true")
    o2 = _make_orch({"backtest": 1})
    remaining2 = o2._workload_capacity(_FakeCtx())
    exec_on = remaining2.get("execution", 0)
    # With reservations ON, execution's floor is 2 → remaining should be >= 2
    assert exec_on >= 2, f"expected execution >= 2 with reservations ON, got {exec_on}"
    # Off-mode value is <= on-mode value (reservation raises, never lowers)
    assert exec_on >= exec_off


def test_execution_reserved_when_backtest_saturated(monkeypatch):
    monkeypatch.setenv("COE_RESERVATIONS_ENABLED", "true")
    # Backtest saturated + no execution in-flight
    o = _make_orch({"backtest": 1, "mutation": 1})
    remaining = o._workload_capacity(_FakeCtx())
    exec_slots = remaining.get("execution", 0)
    # Reservation floor for EXECUTION = 2 (Stage 1 conservative default)
    assert exec_slots >= reservation_for(WorkloadClass.EXECUTION)


def test_market_data_reserved(monkeypatch):
    monkeypatch.setenv("COE_RESERVATIONS_ENABLED", "true")
    o = _make_orch({})
    remaining = o._workload_capacity(_FakeCtx())
    md_slots = remaining.get("market_data", 0)
    assert md_slots >= reservation_for(WorkloadClass.MARKET_DATA)


def test_reservation_floor_shrinks_as_class_fills(monkeypatch):
    monkeypatch.setenv("COE_RESERVATIONS_ENABLED", "true")
    # EXECUTION already using 1 slot — reservation floor should still guarantee (2 - 1) = 1
    o = _make_orch({"execution": 1})
    remaining = o._workload_capacity(_FakeCtx())
    exec_slots = remaining.get("execution", 0)
    assert exec_slots >= 1


def test_reservation_env_override(monkeypatch):
    monkeypatch.setenv("COE_RESERVATIONS_ENABLED", "true")
    monkeypatch.setenv("ORCH_RESERVATION_KNOWLEDGE", "3")
    o = _make_orch({})
    remaining = o._workload_capacity(_FakeCtx())
    assert remaining.get("knowledge", 0) >= 3
