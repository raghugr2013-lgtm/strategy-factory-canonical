"""P0B Phase 2 — Tests for engines/persistence_adapters/bi5_data_certification_store.py.

Uses ``mongomock_motor.AsyncMongoMockClient`` — no real Mongo needed.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from engines.persistence_adapters.bi5_data_certification_store import (
    BI5_DATA_CERT_COLL,
    find_data_certs_by_verdict,
    get_data_certification,
    get_latest_data_certification,
    upsert_data_certification,
)
from engines.tick_validator import BI5ScoreReport


def _naive_utc(dt: datetime) -> datetime:
    """Mongo round-trips datetimes as naive UTC (BSON Date carries no tz)."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


@pytest_asyncio.fixture
async def db():
    client = AsyncMongoMockClient()
    yield client["test_p0b_phase2_cert"]
    client.close()


def _report(
    *,
    symbol: str = "EURUSD",
    window_start: datetime = datetime(2026, 2, 3, 0, 0, tzinfo=timezone.utc),
    window_end: datetime = datetime(2026, 2, 3, 23, 0, tzinfo=timezone.utc),
    bi5_score: float = 0.95,
    verdict: str = "PASS",
    hours_decode_fail: int = 0,
) -> BI5ScoreReport:
    return BI5ScoreReport(
        symbol=symbol,
        window_start=window_start, window_end=window_end,
        hours_expected=24, hours_present=24, hours_missing=0,
        hours_expected_empty=0, hours_decode_fail=hours_decode_fail,
        ticks_total=600_000,
        non_monotonic_ticks=0, price_outlier_ticks=0, zero_vol_ticks=0,
        sparse_hours=0, low_density_hours=0, max_silent_gap_s=12.0,
        subscores={"cov": 1.0, "integrity": 1.0, "price": 1.0,
                   "density": 0.9, "continuity": 0.92},
        bi5_score=bi5_score, verdict=verdict,
    )


@pytest.mark.asyncio
async def test_upsert_certification_inserts(db) -> None:
    rep = _report()
    res = await upsert_data_certification(db, rep)
    assert res["upserted"] == 1
    assert await db[BI5_DATA_CERT_COLL].count_documents({}) == 1


@pytest.mark.asyncio
async def test_upsert_certification_idempotent_on_key(db) -> None:
    rep = _report(bi5_score=0.95, verdict="PASS")
    await upsert_data_certification(db, rep)
    # Same (symbol, window_start, window_end) — but different score/verdict.
    rep2 = replace(rep, bi5_score=0.70, verdict="FAIL")
    res2 = await upsert_data_certification(db, rep2)
    assert res2["upserted"] == 0
    docs = await db[BI5_DATA_CERT_COLL].find({}).to_list(length=10)
    assert len(docs) == 1
    assert docs[0]["verdict"] == "FAIL"
    assert docs[0]["bi5_score"] == pytest.approx(0.70)


@pytest.mark.asyncio
async def test_upsert_preserves_certified_at_on_reupsert(db) -> None:
    rep = _report()
    t1 = datetime(2026, 2, 3, 23, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 2, 4, 23, 0, tzinfo=timezone.utc)
    await upsert_data_certification(db, rep, certified_at_dt=t1)
    await upsert_data_certification(db, rep, certified_at_dt=t2)
    doc = await db[BI5_DATA_CERT_COLL].find_one({})
    assert doc["certified_at_dt"] == _naive_utc(t1)


@pytest.mark.asyncio
async def test_upsert_rejects_bad_verdict(db) -> None:
    rep = replace(_report(), verdict="MAYBE")
    with pytest.raises(ValueError):
        await upsert_data_certification(db, rep)


@pytest.mark.asyncio
async def test_get_certification_point_lookup(db) -> None:
    rep = _report()
    await upsert_data_certification(db, rep)
    doc = await get_data_certification(
        db, symbol="EURUSD",
        window_start_utc=rep.window_start,
        window_end_utc=rep.window_end,
    )
    assert doc is not None
    assert doc["verdict"] == "PASS"
    # Missing window → None.
    miss = await get_data_certification(
        db, symbol="EURUSD",
        window_start_utc=rep.window_start + timedelta(days=7),
        window_end_utc=rep.window_end + timedelta(days=7),
    )
    assert miss is None


@pytest.mark.asyncio
async def test_get_latest_certification_returns_newest(db) -> None:
    rep_old = _report()
    rep_new = replace(rep_old,
                      window_start=rep_old.window_start + timedelta(days=1),
                      window_end=rep_old.window_end + timedelta(days=1))
    t_old = datetime(2026, 2, 3, 23, 0, tzinfo=timezone.utc)
    t_new = datetime(2026, 2, 4, 23, 0, tzinfo=timezone.utc)
    await upsert_data_certification(db, rep_old, certified_at_dt=t_old)
    await upsert_data_certification(db, rep_new, certified_at_dt=t_new)
    latest = await get_latest_data_certification(db, symbol="EURUSD")
    assert latest is not None
    assert latest["window_start_utc"] == _naive_utc(rep_new.window_start)


@pytest.mark.asyncio
async def test_get_latest_certification_missing_symbol_returns_none(db) -> None:
    await upsert_data_certification(db, _report())
    out = await get_latest_data_certification(db, symbol="USDJPY")
    assert out is None


@pytest.mark.asyncio
async def test_find_by_verdict_lists_failures(db) -> None:
    pass_rep = _report(verdict="PASS", bi5_score=0.95)
    fail_rep = replace(
        _report(verdict="FAIL", bi5_score=0.0, hours_decode_fail=1),
        window_start=pass_rep.window_start + timedelta(days=2),
        window_end=pass_rep.window_end + timedelta(days=2),
    )
    warn_rep = replace(
        _report(verdict="WARN", bi5_score=0.80),
        window_start=pass_rep.window_start + timedelta(days=1),
        window_end=pass_rep.window_end + timedelta(days=1),
    )
    for r in (pass_rep, warn_rep, fail_rep):
        await upsert_data_certification(db, r)

    fails = await find_data_certs_by_verdict(db, verdict="FAIL")
    assert len(fails) == 1
    assert fails[0]["verdict"] == "FAIL"

    warns = await find_data_certs_by_verdict(db, verdict="WARN")
    assert len(warns) == 1


@pytest.mark.asyncio
async def test_find_by_verdict_since_filter(db) -> None:
    t_old = datetime(2026, 2, 3, 0, 0, tzinfo=timezone.utc)
    t_new = datetime(2026, 2, 5, 0, 0, tzinfo=timezone.utc)
    old = _report(verdict="FAIL", bi5_score=0.0)
    new = replace(
        _report(verdict="FAIL", bi5_score=0.0),
        window_start=old.window_start + timedelta(days=2),
        window_end=old.window_end + timedelta(days=2),
    )
    await upsert_data_certification(db, old, certified_at_dt=t_old)
    await upsert_data_certification(db, new, certified_at_dt=t_new)

    recent = await find_data_certs_by_verdict(
        db, verdict="FAIL", since_dt=t_old + timedelta(days=1),
    )
    assert len(recent) == 1
    assert recent[0]["window_start_utc"] == _naive_utc(new.window_start)


@pytest.mark.asyncio
async def test_find_by_verdict_rejects_bad_verdict(db) -> None:
    with pytest.raises(ValueError):
        await find_data_certs_by_verdict(db, verdict="OOPS")
