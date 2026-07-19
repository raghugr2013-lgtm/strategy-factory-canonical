"""Phase 2, Stage 2.δ — I/O pool tests.

Verifies:
  * `USE_IO_POOL=false` → falls through to `asyncio.to_thread` (no pool created)
  * `USE_IO_POOL=true` → dedicated pool used; workers isolated
  * Metric counters increment on submit
  * pool_size() honours `IO_POOL_SIZE` env override
  * Bursty I/O does not block a concurrent CPU-like task (isolation smoke)
"""
from __future__ import annotations

import asyncio
import sys
import threading
import time
from pathlib import Path

import pytest

_LEGACY = Path(__file__).resolve().parents[1] / "legacy"
if str(_LEGACY) not in sys.path:
    sys.path.insert(0, str(_LEGACY))

from engines import io_pool  # noqa: E402


@pytest.fixture(autouse=True)
def _reset():
    io_pool._reset_for_tests()
    yield
    io_pool._reset_for_tests()


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("USE_IO_POOL", raising=False)
    assert io_pool.is_enabled() is False


def test_enabled_via_env(monkeypatch):
    monkeypatch.setenv("USE_IO_POOL", "true")
    assert io_pool.is_enabled() is True


def test_pool_size_default_bounded(monkeypatch):
    monkeypatch.delenv("IO_POOL_SIZE", raising=False)
    n = io_pool.pool_size()
    assert 1 <= n <= 32


def test_pool_size_env_override(monkeypatch):
    monkeypatch.setenv("IO_POOL_SIZE", "8")
    assert io_pool.pool_size() == 8


def test_pool_size_env_invalid_falls_back(monkeypatch):
    monkeypatch.setenv("IO_POOL_SIZE", "not_a_number")
    n = io_pool.pool_size()
    assert 1 <= n <= 32


@pytest.mark.asyncio
async def test_submit_falls_through_when_disabled(monkeypatch):
    monkeypatch.delenv("USE_IO_POOL", raising=False)
    def _work(x):
        return x * 2
    result = await io_pool.submit_io(_work, 21)
    assert result == 42
    # Pool must NOT have been initialised
    st = io_pool.get_pool_state()
    assert st["pool_initialized"] is False


@pytest.mark.asyncio
async def test_submit_uses_dedicated_pool_when_enabled(monkeypatch):
    monkeypatch.setenv("USE_IO_POOL", "true")
    def _work(x):
        return x + 1
    result = await io_pool.submit_io(_work, 100)
    assert result == 101
    st = io_pool.get_pool_state()
    assert st["pool_initialized"] is True
    assert st["enabled"] is True


@pytest.mark.asyncio
async def test_metric_counters(monkeypatch):
    monkeypatch.setenv("USE_IO_POOL", "true")
    from engines.metrics import get_metrics
    get_metrics().reset()
    def _noop():
        return None
    for _ in range(3):
        await io_pool.submit_io(_noop, workload_class="market_data")
    for _ in range(2):
        await io_pool.submit_io(_noop, workload_class="knowledge")
    st = io_pool.get_pool_state()
    assert st["submit_count_total"] == 5
    assert st["submit_count_by_class"]["market_data"] == 3
    assert st["submit_count_by_class"]["knowledge"] == 2


@pytest.mark.asyncio
async def test_bursty_io_does_not_block_short_task(monkeypatch):
    """Isolation smoke: 20 concurrent 100 ms I/O jobs should not
    prevent a short lightweight coroutine from completing quickly."""
    monkeypatch.setenv("USE_IO_POOL", "true")
    monkeypatch.setenv("IO_POOL_SIZE", "8")

    def _slow_io():
        time.sleep(0.1)  # simulate blocking I/O
        return "done"

    async def _short_task():
        await asyncio.sleep(0.01)
        return time.perf_counter()

    t0 = time.perf_counter()
    burst = [asyncio.create_task(io_pool.submit_io(_slow_io)) for _ in range(20)]
    short_done_at = await _short_task()
    short_elapsed_ms = (short_done_at - t0) * 1000.0
    await asyncio.gather(*burst)

    # Short task should complete in well under 100 ms even with 20 blocking
    # tasks queued up on the I/O pool. Generous bound (200 ms) to absorb
    # CI variance.
    assert short_elapsed_ms < 200, f"short task took {short_elapsed_ms:.1f} ms — I/O pool not isolating"


@pytest.mark.asyncio
async def test_shutdown_clears_pool(monkeypatch):
    monkeypatch.setenv("USE_IO_POOL", "true")
    await io_pool.submit_io(lambda: 1)
    assert io_pool.get_pool_state()["pool_initialized"] is True
    await io_pool.shutdown_pool()
    assert io_pool.get_pool_state()["pool_initialized"] is False
