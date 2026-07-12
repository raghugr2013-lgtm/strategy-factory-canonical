"""P0B Phase 2 — Tests for engines/persistence_adapters/market_spread_store.py.

Uses ``mongomock_motor.AsyncMongoMockClient`` — no real Mongo needed.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from engines.persistence_adapters.market_spread_store import (
    MARKET_SPREAD_COLL,
    find_spread_bars,
    upsert_spread_bars,
)
from engines.spread_analyzer import SpreadBar


@pytest_asyncio.fixture
async def db():
    client = AsyncMongoMockClient()
    yield client["test_p0b_phase2"]
    client.close()


def _naive_utc(dt: datetime) -> datetime:
    """Mongo round-trips datetimes as naive UTC (BSON Date carries no tz)."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _bar(symbol: str, ts: datetime, *, n: int = 1, mean: float = 0.0001):
    return SpreadBar(
        symbol=symbol, ts=ts,
        spread_open=mean, spread_high=mean, spread_low=mean,
        spread_close=mean, spread_mean=mean, tick_count=n,
    )


@pytest.mark.asyncio
async def test_upsert_spread_bars_inserts_new_rows(db) -> None:
    base = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    bars = [_bar("EURUSD", base + timedelta(minutes=i)) for i in range(3)]
    res = await upsert_spread_bars(db, bars)
    assert res["upserted"] == 3
    count = await db[MARKET_SPREAD_COLL].count_documents({})
    assert count == 3


@pytest.mark.asyncio
async def test_upsert_spread_bars_is_idempotent_on_key(db) -> None:
    base = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    bars = [_bar("EURUSD", base, mean=0.0001)]
    r1 = await upsert_spread_bars(db, bars)
    # Re-upsert same minute with a corrected OHLC — should update in place.
    bars2 = [_bar("EURUSD", base, mean=0.0002)]
    r2 = await upsert_spread_bars(db, bars2)
    assert r1["upserted"] == 1
    assert r2["upserted"] == 0   # not a new insert
    docs = await db[MARKET_SPREAD_COLL].find({}).to_list(length=10)
    assert len(docs) == 1
    assert docs[0]["spread_mean"] == pytest.approx(0.0002)


@pytest.mark.asyncio
async def test_upsert_spread_bars_preserves_created_at_on_reupsert(db) -> None:
    base = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    now1 = datetime(2026, 2, 3, 10, 0, tzinfo=timezone.utc)
    now2 = datetime(2026, 2, 5, 10, 0, tzinfo=timezone.utc)
    await upsert_spread_bars(db, [_bar("EURUSD", base)], now_dt=now1)
    await upsert_spread_bars(db, [_bar("EURUSD", base)], now_dt=now2)
    doc = await db[MARKET_SPREAD_COLL].find_one({})
    # created_at_dt is $setOnInsert so the re-upsert MUST NOT touch it.
    assert doc["created_at_dt"] == _naive_utc(now1)


@pytest.mark.asyncio
async def test_upsert_spread_bars_empty_input_is_noop(db) -> None:
    res = await upsert_spread_bars(db, [])
    assert res == {"matched": 0, "upserted": 0, "modified": 0}
    assert await db[MARKET_SPREAD_COLL].count_documents({}) == 0


@pytest.mark.asyncio
async def test_upsert_normalises_to_minute_boundary(db) -> None:
    # Non-floored input — adapter must store the floored minute.
    ts = datetime(2026, 2, 3, 9, 0, 42, 123456, tzinfo=timezone.utc)
    await upsert_spread_bars(db, [_bar("EURUSD", ts)])
    doc = await db[MARKET_SPREAD_COLL].find_one({})
    assert doc["minute_utc"] == _naive_utc(ts.replace(second=0, microsecond=0))


@pytest.mark.asyncio
async def test_find_spread_bars_time_range_and_sort(db) -> None:
    base = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    await upsert_spread_bars(db, [
        _bar("EURUSD", base + timedelta(minutes=i)) for i in range(5)
    ])
    out = await find_spread_bars(
        db, symbol="EURUSD",
        start_utc=base + timedelta(minutes=1),
        end_utc=base + timedelta(minutes=4),
    )
    assert [d["minute_utc"] for d in out] == [
        _naive_utc(base + timedelta(minutes=1)),
        _naive_utc(base + timedelta(minutes=2)),
        _naive_utc(base + timedelta(minutes=3)),
    ]


@pytest.mark.asyncio
async def test_find_spread_bars_filters_by_symbol(db) -> None:
    base = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    await upsert_spread_bars(db, [
        _bar("EURUSD", base),
        _bar("GBPUSD", base),
    ])
    eur = await find_spread_bars(
        db, symbol="EURUSD",
        start_utc=base, end_utc=base + timedelta(minutes=1),
    )
    assert len(eur) == 1
    assert eur[0]["symbol"] == "EURUSD"
