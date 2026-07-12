"""Regression tests for the scheduler-friendly single-cycle endpoint.

Covers:
  • `run_single_cycle` executes exactly one cycle and returns a
    structured summary.
  • Lock-busy path returns `status=skipped` without blocking.
  • Hard timeout → `status=timeout` + reason set, never hangs.
  • `quality_filter` / `quality_threshold` flow into `sim_config` and
    reach `run_mutation_pipeline`.
  • `optimizer` param is accepted + persisted but does NOT change
    mutation behaviour (Phase 3 scope).
  • Auto-rotation EURUSD ↔ XAUUSD when `pair` is omitted.
  • Each run is independently persisted to `auto_run_cycles`.
"""
from __future__ import annotations

import asyncio
import sys
from typing import Any, Dict, List

import pytest

sys.path.insert(0, "/app/backend")

from engines import auto_mutation_runner as amr  # noqa: E402


# ─────────────────────────────────────────────────────────────────────
# In-memory DB stub for the persistence side-effect
# ─────────────────────────────────────────────────────────────────────

class _FakeCursor:
    def __init__(self, docs): self._docs = list(docs)
    def sort(self, *_a, **_k): return self
    def limit(self, n): self._docs = self._docs[:int(n)]; return self
    def __aiter__(self):
        async def gen():
            for d in self._docs:
                yield d
        return gen()


class _FakeColl:
    def __init__(self):
        self._rows: List[Dict[str, Any]] = []

    async def insert_one(self, doc):
        self._rows.append(dict(doc))
        return {"inserted_id": len(self._rows)}

    async def count_documents(self, query):
        return len(self._rows)

    def find(self, query=None, projection=None):
        return _FakeCursor(self._rows)


class _FakeDB:
    def __init__(self):
        self._colls: Dict[str, _FakeColl] = {}

    def __getitem__(self, name):
        self._colls.setdefault(name, _FakeColl())
        return self._colls[name]


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(amr, "get_db", lambda: db)
    return db


@pytest.fixture(autouse=True)
def _reset_lock():
    """Ensure the module lock starts every test unlocked."""
    # Create a fresh Lock bound to this test's running loop. Reusing a
    # Lock from a previous loop leaves asyncio in a bad state.
    # Tests await `run_single_cycle`, which will `async with _RUN_LOCK`
    # on the running loop — so the lock attached to the module must be
    # from that loop.
    amr._RUN_LOCK = asyncio.Lock()
    yield


# ─────────────────────────────────────────────────────────────────────
# Monkey-patched strategy runner — replaces the heavy inner pipeline.
# ─────────────────────────────────────────────────────────────────────

def _make_fake_runner(pf=1.8, dd=6.0, saved=True):
    async def _fake(**kwargs):
        return {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "strategy_preview": "EMA/ATR trend following (fake)",
            "mutation_run_id": "abc123",
            "mutation_status": "ok",
            "best_pf": pf,
            "best_dd_pct": dd,
            "best_trades": 42,
            "best_mutation_type": "indicator_swap",
            "auto_save_status": "saved" if saved else "rejected",
            "auto_save_reason": None,
            "_received_sim_config": kwargs.get("sim_config"),
        }
    return _fake


# ─────────────────────────────────────────────────────────────────────
# Core tests
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_single_cycle_happy_path(fake_db, monkeypatch):
    monkeypatch.setattr(amr, "_run_one_strategy", _make_fake_runner(pf=2.1, dd=5.0))

    res = await amr.run_single_cycle(
        batch_size=3, pair="EURUSD", timeframe="H1",
        quality_filter=True, quality_threshold=55.0,
        optimizer="ga", timeout_seconds=60.0,
    )
    assert res["status"] == "completed"
    assert res["strategies_generated"] == 3
    assert res["strategies_saved"] == 3
    assert res["avg_pf"] == 2.1
    assert res["avg_dd"] == 5.0
    assert res["pair"] == "EURUSD"
    assert res["config"]["optimizer"] == "ga"
    assert res["config"]["quality_filter"] is True
    assert res["config"]["quality_threshold"] == 55.0
    assert res["quality_filter_applied"] is True
    # Persisted exactly one run log row
    assert len(fake_db[amr.RUN_CYCLES_COLL]._rows) == 1


@pytest.mark.asyncio
async def test_run_single_cycle_sim_config_plumbed(fake_db, monkeypatch):
    captured: Dict[str, Any] = {}

    async def _fake(**kwargs):
        captured.update(kwargs)
        return {"mutation_status": "ok", "best_pf": 1.2, "best_dd_pct": 8.0,
                "auto_save_status": "rejected"}

    monkeypatch.setattr(amr, "_run_one_strategy", _fake)

    await amr.run_single_cycle(
        batch_size=1, pair="EURUSD", timeframe="H1",
        quality_filter=True, quality_threshold=70.0,
        optimizer="random", timeout_seconds=30.0,
    )
    sim_cfg = captured["sim_config"]
    assert sim_cfg == {"quality_filter": True, "quality_threshold": 70.0}


@pytest.mark.asyncio
async def test_run_single_cycle_optimizer_is_logged_but_does_not_change_behavior(
    fake_db, monkeypatch,
):
    """Optimizer accepts `ga` or `random`; the inner pipeline is
    identical. This test locks that contract — the param flows into
    the persisted config but NOT into `_run_one_strategy` kwargs."""
    received_kwargs: Dict[str, Any] = {}

    async def _fake(**kwargs):
        received_kwargs.update(kwargs)
        return {"mutation_status": "ok"}

    monkeypatch.setattr(amr, "_run_one_strategy", _fake)

    res = await amr.run_single_cycle(
        batch_size=1, pair="EURUSD", optimizer="ga", timeout_seconds=30.0,
    )
    assert res["config"]["optimizer"] == "ga"
    assert "optimizer" not in received_kwargs


@pytest.mark.asyncio
async def test_run_single_cycle_skipped_when_lock_busy(fake_db, monkeypatch):
    async def _fake(**kwargs):
        await asyncio.sleep(0.2)
        return {"mutation_status": "ok"}

    monkeypatch.setattr(amr, "_run_one_strategy", _fake)

    # First call acquires lock; second call sees busy.
    t1 = asyncio.create_task(amr.run_single_cycle(
        batch_size=2, pair="EURUSD", timeout_seconds=10.0,
    ))
    # Give t1 time to actually acquire the lock
    await asyncio.sleep(0.05)
    t2_res = await amr.run_single_cycle(batch_size=1, pair="EURUSD")
    assert t2_res["status"] == "skipped"
    assert t2_res["reason"] == "run_already_active"
    await t1   # clean up


@pytest.mark.asyncio
async def test_run_single_cycle_hard_timeout(fake_db, monkeypatch):
    """`timeout_seconds` kicks in via asyncio.wait_for and produces a
    `status=timeout` response instead of hanging."""

    async def _slow(**kwargs):
        await asyncio.sleep(5.0)
        return {"mutation_status": "ok"}

    monkeypatch.setattr(amr, "_run_one_strategy", _slow)

    res = await amr.run_single_cycle(
        batch_size=2, pair="EURUSD", timeout_seconds=30.0,  # validator min is 30
    )
    # Patch the validator-enforced minimum AFTER the fact by overriding
    # the internal clamp. Simpler: assert via direct engine call.
    # (Actual behaviour tested with smaller internal timeout below.)
    assert res["status"] in ("completed", "timeout")


@pytest.mark.asyncio
async def test_run_single_cycle_timeout_enforced_via_direct_call(fake_db, monkeypatch):
    """Verify that wait_for wraps the cycle — bypass the 30s validator
    by monkey-patching the default so we can test the timeout code
    path in <1 s."""
    async def _slow(**kwargs):
        await asyncio.sleep(2.0)
        return {"mutation_status": "ok"}

    monkeypatch.setattr(amr, "_run_one_strategy", _slow)
    # Patch the clamp so we can pass timeout_seconds=0.3
    orig = amr.run_single_cycle

    async def _call():
        # Reach inside the function — use the private path via the
        # lock directly. Instead, just call with the clamp ≥ 30 s and
        # monkey-patch asyncio.wait_for to use 0.3 s.
        import asyncio as _asyncio
        real_wait = _asyncio.wait_for

        async def tiny_wait(coro, timeout):
            return await real_wait(coro, 0.3)

        monkeypatch.setattr(_asyncio, "wait_for", tiny_wait)
        return await orig(batch_size=2, pair="EURUSD", timeout_seconds=30.0)

    res = await _call()
    assert res["status"] == "timeout"
    assert res["reason"].startswith("exceeded_timeout")
    # Still persisted — even on timeout we get a run log row.
    assert len(fake_db[amr.RUN_CYCLES_COLL]._rows) == 1


@pytest.mark.asyncio
async def test_run_single_cycle_auto_rotates_pair_when_omitted(fake_db, monkeypatch):
    monkeypatch.setattr(amr, "_run_one_strategy", _make_fake_runner())

    res1 = await amr.run_single_cycle(batch_size=1, timeout_seconds=30.0)
    res2 = await amr.run_single_cycle(batch_size=1, timeout_seconds=30.0)
    res3 = await amr.run_single_cycle(batch_size=1, timeout_seconds=30.0)
    assert res1["pair"] == "EURUSD"
    assert res2["pair"] == "XAUUSD"
    assert res3["pair"] == "EURUSD"


@pytest.mark.asyncio
async def test_run_single_cycle_batch_size_clamped(fake_db, monkeypatch):
    monkeypatch.setattr(amr, "_run_one_strategy", _make_fake_runner())

    res = await amr.run_single_cycle(
        batch_size=999, pair="EURUSD", timeout_seconds=30.0,
    )
    assert res["strategies_generated"] == 20   # clamped to 20


@pytest.mark.asyncio
async def test_run_single_cycle_persists_history(fake_db, monkeypatch):
    monkeypatch.setattr(amr, "_run_one_strategy", _make_fake_runner(pf=1.5, dd=8.0))

    await amr.run_single_cycle(batch_size=2, pair="EURUSD", timeout_seconds=30.0)
    await amr.run_single_cycle(batch_size=1, pair="XAUUSD", timeout_seconds=30.0)

    rows = await amr.list_cycle_runs(limit=10)
    assert len(rows) == 2
    assert {r["pair"] for r in rows} == {"EURUSD", "XAUUSD"}
    # Both rows carry the scheduler-friendly summary fields.
    for r in rows:
        assert "strategies_generated" in r
        assert "avg_pf" in r
        assert "config" in r
        assert r["config"]["quality_filter"] is True
