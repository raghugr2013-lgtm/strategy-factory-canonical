"""Phase 2, Stage 2 — WorkloadQueue tests.

Verifies:
  * Protocol compliance (LocalQueueDriver + DistributedQueueDriver stub)
  * P0 > P1 > P2 lane ordering
  * FIFO within lane
  * cancel() removes queued jobs
  * peek() and snapshot() shapes
  * Driver selection via COE_QUEUE_DRIVER env
  * Distributed stub raises with a clear message
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_LEGACY = Path(__file__).resolve().parents[1] / "legacy"
if str(_LEGACY) not in sys.path:
    sys.path.insert(0, str(_LEGACY))

from engines.coe import (  # noqa: E402
    DistributedQueueDriver,
    Lane,
    LocalQueueDriver,
    WorkloadQueue,
    WorkloadRequest,
    _reset_singleton_for_tests,
    get_queue,
    get_queue_driver_name,
)


def test_local_driver_satisfies_protocol():
    d = LocalQueueDriver()
    assert isinstance(d, WorkloadQueue)


def test_distributed_driver_satisfies_protocol():
    d = DistributedQueueDriver()
    assert isinstance(d, WorkloadQueue)


@pytest.mark.asyncio
async def test_local_submit_and_next_fifo_within_lane():
    d = LocalQueueDriver()
    r1 = WorkloadRequest(class_="backtest", task_name="t1", lane=Lane.P1.value)
    r2 = WorkloadRequest(class_="backtest", task_name="t2", lane=Lane.P1.value)
    r3 = WorkloadRequest(class_="backtest", task_name="t3", lane=Lane.P1.value)
    for r in (r1, r2, r3):
        await d.submit(r)
    assert (await d.next("backtest", 10)).task_name == "t1"
    assert (await d.next("backtest", 10)).task_name == "t2"
    assert (await d.next("backtest", 10)).task_name == "t3"
    assert await d.next("backtest", 10) is None


@pytest.mark.asyncio
async def test_p0_beats_p1_beats_p2():
    d = LocalQueueDriver()
    # Submit in reverse-priority order
    p2 = WorkloadRequest(class_="backtest", task_name="p2", lane=Lane.P2.value)
    p1 = WorkloadRequest(class_="backtest", task_name="p1", lane=Lane.P1.value)
    p0 = WorkloadRequest(class_="backtest", task_name="p0", lane=Lane.P0.value)
    await d.submit(p2)
    await d.submit(p1)
    await d.submit(p0)
    assert (await d.next("backtest", 10)).task_name == "p0"
    assert (await d.next("backtest", 10)).task_name == "p1"
    assert (await d.next("backtest", 10)).task_name == "p2"


@pytest.mark.asyncio
async def test_cancel_removes_queued_job():
    d = LocalQueueDriver()
    r = WorkloadRequest(class_="backtest", task_name="t1", lane=Lane.P1.value)
    await d.submit(r)
    ok = await d.cancel(r.job_id)
    assert ok
    assert await d.next("backtest", 10) is None
    # Second cancel is a no-op
    assert await d.cancel(r.job_id) is False


@pytest.mark.asyncio
async def test_cancel_unknown_job_id():
    d = LocalQueueDriver()
    assert await d.cancel("does_not_exist") is False


@pytest.mark.asyncio
async def test_peek_shape():
    d = LocalQueueDriver()
    await d.submit(WorkloadRequest(class_="agent", task_name="a", lane=Lane.P0.value))
    await d.submit(WorkloadRequest(class_="agent", task_name="b", lane=Lane.P0.value))
    await d.submit(WorkloadRequest(class_="agent", task_name="c", lane=Lane.P1.value))
    p = await d.peek("agent")
    assert p == {"P0": 2, "P1": 1, "P2": 0, "total": 3}


@pytest.mark.asyncio
async def test_peek_unknown_class_returns_zero():
    d = LocalQueueDriver()
    p = await d.peek("no_such_class")
    assert p["total"] == 0


@pytest.mark.asyncio
async def test_snapshot_shape_multi_class():
    d = LocalQueueDriver()
    await d.submit(WorkloadRequest(class_="agent", task_name="a", lane=Lane.P0.value))
    await d.submit(WorkloadRequest(class_="backtest", task_name="b", lane=Lane.P1.value))
    s = await d.snapshot()
    assert s["driver"] == "local"
    assert s["class_count"] == 2
    assert s["total_enqueued"] == 2
    assert "agent" in s["classes"] and "backtest" in s["classes"]


@pytest.mark.asyncio
async def test_size_across_classes():
    d = LocalQueueDriver()
    await d.submit(WorkloadRequest(class_="agent", task_name="a"))
    await d.submit(WorkloadRequest(class_="backtest", task_name="b"))
    await d.submit(WorkloadRequest(class_="execution", task_name="c"))
    assert await d.size() == 3


@pytest.mark.asyncio
async def test_next_with_zero_cap_returns_none():
    d = LocalQueueDriver()
    await d.submit(WorkloadRequest(class_="backtest", task_name="t"))
    assert await d.next("backtest", 0) is None
    # But cap=1 pulls
    assert (await d.next("backtest", 1)).task_name == "t"


@pytest.mark.asyncio
async def test_submit_requires_class():
    d = LocalQueueDriver()
    r = WorkloadRequest(task_name="orphan")   # class_ empty
    with pytest.raises(ValueError, match="class_"):
        await d.submit(r)


@pytest.mark.asyncio
async def test_invalid_lane_falls_back_to_p1():
    d = LocalQueueDriver()
    r = WorkloadRequest(class_="backtest", task_name="t", lane="XYZ")
    await d.submit(r)
    p = await d.peek("backtest")
    assert p[Lane.P1.value] == 1
    assert p[Lane.P0.value] == 0
    assert p[Lane.P2.value] == 0


@pytest.mark.asyncio
async def test_distributed_driver_stub_raises_with_clear_message():
    d = DistributedQueueDriver()
    with pytest.raises(NotImplementedError, match="Phase 3"):
        await d.submit(WorkloadRequest(class_="x", task_name="y"))
    with pytest.raises(NotImplementedError, match="Phase 3"):
        await d.next("x", 1)
    # snapshot() intentionally doesn't raise — returns diagnostic dict
    s = await d.snapshot()
    assert s["driver"] == "distributed" and s["status"] == "stub"


def test_driver_selection_default_local(monkeypatch):
    monkeypatch.delenv("COE_QUEUE_DRIVER", raising=False)
    _reset_singleton_for_tests()
    assert get_queue_driver_name() == "local"
    q = get_queue()
    assert isinstance(q, LocalQueueDriver)


def test_driver_selection_distributed(monkeypatch):
    monkeypatch.setenv("COE_QUEUE_DRIVER", "distributed")
    _reset_singleton_for_tests()
    assert get_queue_driver_name() == "distributed"
    q = get_queue()
    assert isinstance(q, DistributedQueueDriver)


def test_driver_selection_invalid_falls_back_to_local(monkeypatch):
    monkeypatch.setenv("COE_QUEUE_DRIVER", "garbage")
    _reset_singleton_for_tests()
    assert get_queue_driver_name() == "local"
