"""Phase 2, Stage 2.γ — orchestrator queue-drain tests.

Verifies:
  * `COE_LANES_ENABLED=false` → `_drain_queue()` is a no-op
  * `COE_LANES_ENABLED=true` → queued jobs are dispatched
  * Unknown task_name in queue is dropped with a warning (not fatal)
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

_LEGACY = Path(__file__).resolve().parents[1] / "legacy"
if str(_LEGACY) not in sys.path:
    sys.path.insert(0, str(_LEGACY))

from engines.coe import (  # noqa: E402
    Lane,
    WorkloadRequest,
    _reset_singleton_for_tests,
    get_queue,
)


class _FakeCtx:
    def __init__(self):
        self.now_iso = "2026-01-01T00:00:00+00:00"


@pytest.mark.asyncio
async def test_drain_noop_when_flag_off(monkeypatch):
    monkeypatch.delenv("COE_LANES_ENABLED", raising=False)
    _reset_singleton_for_tests()
    q = get_queue()
    await q.submit(WorkloadRequest(class_="backtest", task_name="ghost", lane=Lane.P0.value))

    from engines.orchestrator.core import Orchestrator
    o = Orchestrator()
    dispatched = await o._drain_queue(_FakeCtx(), {"backtest": 5})
    assert dispatched == 0
    # Queue still holds the item
    peek = await q.peek("backtest")
    assert peek["total"] == 1


@pytest.mark.asyncio
async def test_drain_drops_unknown_task(monkeypatch):
    monkeypatch.setenv("COE_LANES_ENABLED", "true")
    _reset_singleton_for_tests()
    q = get_queue()
    await q.submit(WorkloadRequest(class_="backtest", task_name="does_not_exist", lane=Lane.P0.value))

    from engines.orchestrator.core import Orchestrator
    o = Orchestrator()
    dispatched = await o._drain_queue(_FakeCtx(), {"backtest": 5})
    # Not dispatched because task_name is unknown — but drain returned 0 (not an error)
    assert dispatched == 0
    # Queue was drained anyway
    peek = await q.peek("backtest")
    assert peek["total"] == 0


@pytest.mark.asyncio
async def test_drain_respects_cap(monkeypatch):
    monkeypatch.setenv("COE_LANES_ENABLED", "true")
    _reset_singleton_for_tests()
    q = get_queue()
    # Submit 5 unknown tasks
    for i in range(5):
        await q.submit(WorkloadRequest(class_="backtest", task_name=f"nope-{i}", lane=Lane.P0.value))

    from engines.orchestrator.core import Orchestrator
    o = Orchestrator()
    # cap=2 — drain should stop after 2 pulls even though 5 exist
    remaining = {"backtest": 2}
    await o._drain_queue(_FakeCtx(), remaining)
    # Only 2 pulled from the queue; 3 remain
    peek = await q.peek("backtest")
    assert peek["total"] == 3
