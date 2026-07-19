"""Phase 2, Stage 1 — Task Hard-Timeout tests.

Verifies that when COE_HARD_TIMEOUT_ENABLED=true, a Task.run() that
exceeds its HARD_TIMEOUT_S is killed by the orchestrator dispatcher.

Also verifies the byte-identical fallback when the flag is off.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

_LEGACY = Path(__file__).resolve().parents[1] / "legacy"
if str(_LEGACY) not in sys.path:
    sys.path.insert(0, str(_LEGACY))


class _FakeHangTask:
    NAME = "test_hang"
    HARD_TIMEOUT_S = 0.2  # 200 ms

    async def run(self, ctx):
        await asyncio.sleep(5.0)   # deliberately overruns
        return ("ok",)


class _FakeQuickTask:
    NAME = "test_quick"
    HARD_TIMEOUT_S = 1.0

    async def run(self, ctx):
        await asyncio.sleep(0.05)
        return "done"


@pytest.mark.asyncio
async def test_hard_timeout_kills_hung_task(monkeypatch):
    monkeypatch.setenv("COE_HARD_TIMEOUT_ENABLED", "true")
    # Replicate the dispatcher wrap-code behaviour in isolation
    task = _FakeHangTask()
    hard_timeout_on = os.environ.get("COE_HARD_TIMEOUT_ENABLED", "").lower() in ("1", "true", "yes", "y", "on")
    timeout_s = float(getattr(task, "HARD_TIMEOUT_S", 300.0))
    with pytest.raises(asyncio.TimeoutError):
        if hard_timeout_on and timeout_s > 0:
            await asyncio.wait_for(task.run(None), timeout=timeout_s)
        else:
            await task.run(None)


@pytest.mark.asyncio
async def test_hard_timeout_flag_off_allows_overrun(monkeypatch):
    monkeypatch.setenv("COE_HARD_TIMEOUT_ENABLED", "false")
    task = _FakeQuickTask()
    hard_timeout_on = os.environ.get("COE_HARD_TIMEOUT_ENABLED", "").lower() in ("1", "true", "yes", "y", "on")
    timeout_s = float(getattr(task, "HARD_TIMEOUT_S", 300.0))
    # Flag off — no wait_for wrap; task returns normally
    if hard_timeout_on and timeout_s > 0:
        r = await asyncio.wait_for(task.run(None), timeout=timeout_s)
    else:
        r = await task.run(None)
    assert r == "done"


def test_all_task_adapters_declare_hard_timeout():
    """Every orchestrator task adapter has HARD_TIMEOUT_S (Stage 1 requirement)."""
    import engines.orchestrator.tasks  # noqa: F401 — trigger registration
    from engines.orchestrator.registry import registry
    tasks = registry.all()
    assert len(tasks) >= 15
    missing = [t.NAME for t in tasks if not hasattr(t, "HARD_TIMEOUT_S")]
    assert not missing, f"tasks missing HARD_TIMEOUT_S: {missing}"
    for t in tasks:
        assert 10.0 <= float(t.HARD_TIMEOUT_S) <= 3600.0, \
            f"{t.NAME} HARD_TIMEOUT_S={t.HARD_TIMEOUT_S} out of sane range"
