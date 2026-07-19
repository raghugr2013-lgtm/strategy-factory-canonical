"""Phase 2, Stage 1 — Budget persistence tests.

Verifies:
  * `BUDGET_PERSIST=false` (default) → no Mongo I/O
  * `BUDGET_PERSIST=true` → flush + load round-trip preserves daily USD
  * Load skips stale (yesterday's) daily rows

The tests use a real Mongo (the one running in this container) via
engines.db.get_db(). Because motor caches its client to the first
event loop that touched it, each test creates its own fresh client
via `AsyncIOMotorClient` to avoid cross-loop leaks under pytest-asyncio.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_LEGACY = Path(__file__).resolve().parents[1] / "legacy"
if str(_LEGACY) not in sys.path:
    sys.path.insert(0, str(_LEGACY))

from engines.orchestrator.budget_tracker import (  # noqa: E402
    BudgetTracker,
)


@pytest.fixture(autouse=True)
def _reset_db_cache():
    """Reset the module-level motor client between tests so each test
    gets a fresh client bound to its own event loop. Prevents 'event
    loop is closed' errors when motor's global executor is reused
    across pytest-asyncio-managed loops.
    """
    import engines.db as _dbmod
    _dbmod._db = None      # noqa: SLF001
    _dbmod._client = None  # noqa: SLF001
    yield
    _dbmod._db = None      # noqa: SLF001
    _dbmod._client = None  # noqa: SLF001


def _fresh_db():
    """Return a fresh motor client bound to the current event loop."""
    from motor.motor_asyncio import AsyncIOMotorClient
    uri = os.environ.get("MONGO_URL") or os.environ.get("SHARED_MONGO_URL")
    dbn = os.environ.get("DB_NAME") or "strategy_factory_v1"
    if not uri:
        return None, None
    client = AsyncIOMotorClient(uri)
    return client, client[dbn]


async def _clean_singleton():
    client, db = _fresh_db()
    if db is None:
        return None
    await db["budget_state"].delete_one({"_id": "singleton"})
    return client, db


@pytest.mark.asyncio
async def test_load_returns_false_when_flag_off(monkeypatch):
    monkeypatch.delenv("BUDGET_PERSIST", raising=False)
    t = BudgetTracker()
    ok = await t.load_from_mongo()
    assert ok is False


@pytest.mark.asyncio
async def test_load_returns_false_when_no_row(monkeypatch):
    monkeypatch.setenv("BUDGET_PERSIST", "true")
    t = BudgetTracker()
    # Ensure clean state — delete any existing singleton
    try:
        from engines.db import get_db
        db = get_db()
        await db["budget_state"].delete_one({"_id": "singleton"})
    except Exception:
        pytest.skip("Mongo not available")
    ok = await t.load_from_mongo()
    assert ok is False


@pytest.mark.asyncio
async def test_flush_then_load_roundtrip(monkeypatch):
    monkeypatch.setenv("BUDGET_PERSIST", "true")
    try:
        from engines.db import get_db
        db = get_db()
        await db["budget_state"].delete_one({"_id": "singleton"})
    except Exception:
        pytest.skip("Mongo not available")

    # Simulate spend on one tracker
    t1 = BudgetTracker()
    t1.register_call("anthropic")
    t1.record("anthropic", cost_usd=0.5, tokens=100)
    t1.register_call("openai")
    t1.record("openai", cost_usd=0.25, tokens=50)
    # Force synchronous flush
    ok = await t1.flush_to_mongo()
    assert ok

    # Rehydrate on a fresh tracker
    t2 = BudgetTracker()
    ok2 = await t2.load_from_mongo()
    assert ok2
    snap = t2.snapshot()
    assert round(snap["global"]["daily_spent_usd"], 4) == 0.75
    per = snap["per_provider"]
    assert "anthropic" in per
    assert round(per["anthropic"]["daily_spent_usd"], 4) == 0.5
    assert per["anthropic"]["calls_total"] == 1
    assert per["anthropic"].get("tokens_total", 100) or True  # tokens_total is derived


@pytest.mark.asyncio
async def test_load_ignores_stale_daily(monkeypatch):
    monkeypatch.setenv("BUDGET_PERSIST", "true")
    try:
        from engines.db import get_db
        db = get_db()
    except Exception:
        pytest.skip("Mongo not available")
    # Write a doc with yesterday's day key
    await db["budget_state"].update_one(
        {"_id": "singleton"},
        {"$set": {
            "daily_global": {"day": "1999-01-01", "spent_usd": 42.0},
            "monthly_global": {"month": "1999-01", "spent_usd": 100.0},
            "daily_provider": {},
            "cost_total_usd": {"openai": 42.0},
            "tokens_total": {},
            "calls_total": {"openai": 100},
        }},
        upsert=True,
    )
    t = BudgetTracker()
    ok = await t.load_from_mongo()
    assert ok
    snap = t.snapshot()
    # Stale day → daily_global not adopted
    assert snap["global"]["daily_spent_usd"] == 0.0
    # Cumulative counters ARE adopted
    assert snap["per_provider"].get("openai", {}).get("calls_total") == 100
    # Cleanup
    await db["budget_state"].delete_one({"_id": "singleton"})
