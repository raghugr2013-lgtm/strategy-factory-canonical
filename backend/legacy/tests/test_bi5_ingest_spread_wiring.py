"""P0B Phase 2 — Integration test: bi5_ingest_runner persists market_spread.

Re-uses the synthetic BI5 payload helper + fake adapter + _merge_rows
spy pattern from test_bi5_ingest_runner_e2e.py. Adds a mongomock-backed
db and verifies that for every ingested hour the runner:

    1. Still emits 1m bars to market_data via _merge_rows (P0A path,
       unchanged), AND
    2. Upserts the corresponding per-minute SpreadBars into
       market_spread via the Phase 2 adapter.
"""
from __future__ import annotations

import lzma
import struct
from datetime import datetime, timedelta, timezone
from typing import Dict, List

import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from data_engine import bi5_ingest_runner as runner_module
from data_engine.adapters.base import BI5Adapter, BI5HourBlob, normalize_hour_utc
from data_engine.bi5_ingest_runner import BI5IngestRunner
from data_engine.tick_archive import BI5TickArchive
from engines.persistence_adapters.market_spread_store import MARKET_SPREAD_COLL


def _naive_utc(dt: datetime) -> datetime:
    """Mongo round-trips datetimes as naive UTC (BSON Date carries no tz)."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


_TICK_STRUCT = struct.Struct(">IIIff")


def _build_bi5_payload(ticks, *, price_multiplier: float = 1e5) -> bytes:
    raw_parts = []
    for ms_offset, bid, ask, bid_vol, ask_vol in ticks:
        bid_fp = int(round(bid * price_multiplier))
        ask_fp = int(round(ask * price_multiplier))
        raw_parts.append(_TICK_STRUCT.pack(
            int(ms_offset), int(ask_fp), int(bid_fp),
            float(ask_vol), float(bid_vol),
        ))
    return lzma.compress(b"".join(raw_parts), format=lzma.FORMAT_ALONE)


class _FakeAdapter(BI5Adapter):
    source_id = "dukascopy"

    def __init__(self, payloads: Dict[datetime, bytes]) -> None:
        self._payloads = {normalize_hour_utc(k): v for k, v in payloads.items()}

    async def fetch_hour(self, symbol: str, hour_utc: datetime) -> BI5HourBlob:
        hour_utc = normalize_hour_utc(hour_utc)
        return BI5HourBlob(
            symbol=symbol, hour_utc=hour_utc,
            payload=self._payloads.get(hour_utc, b""),
            source=self.source_id,
        )

    async def close(self) -> None:
        pass


class _MergeRowsSpy:
    """Stand-in for data_engine.data_manager._merge_rows (no Mongo touch)."""

    def __init__(self) -> None:
        self.calls: List[dict] = []

    async def __call__(self, rows, symbol, source, timeframe, *, append_only=False):
        self.calls.append({
            "rows": list(rows), "symbol": symbol, "source": source,
            "timeframe": timeframe, "append_only": append_only,
        })
        return {"upserted": len(rows), "matched": 0,
                "intra_batch_duplicates": 0, "append_only": append_only}


@pytest_asyncio.fixture
async def mock_db():
    client = AsyncMongoMockClient()
    yield client["test_bi5_ingest_spread_wiring"]
    client.close()


@pytest.mark.asyncio
async def test_runner_persists_spread_bars_when_db_supplied(
    tmp_path, monkeypatch, mock_db,
) -> None:
    archive = BI5TickArchive(root=str(tmp_path))
    hour0 = datetime(2024, 1, 2, 7, tzinfo=timezone.utc)

    # 3 ticks across 2 distinct minutes inside hour 0.
    payload = _build_bi5_payload([
        (    0, 1.10000, 1.10001, 1.0, 1.0),   # minute 00
        (30_000, 1.10003, 1.10004, 1.0, 1.0),  # minute 00
        (75_000, 1.10005, 1.10010, 2.0, 2.0),  # minute 01 (wider spread)
    ])
    adapter = _FakeAdapter({hour0: payload})

    spy = _MergeRowsSpy()
    monkeypatch.setattr(runner_module, "_merge_rows", spy)

    runner = BI5IngestRunner(adapter=adapter, archive=archive, db=mock_db)
    try:
        report = await runner.run_for_symbol(
            "EURUSD", start_utc=hour0, end_utc=hour0 + timedelta(hours=1),
        )
    finally:
        await runner.close()

    # P0A path untouched: bars still routed to market_data via _merge_rows.
    assert len(spy.calls) == 1
    assert spy.calls[0]["source"] == "bi5"
    assert spy.calls[0]["timeframe"] == "1m"

    # P0B Phase 2 path: spread bars must be persisted to market_spread.
    spread_docs = await mock_db[MARKET_SPREAD_COLL].find({}).to_list(length=10)
    assert len(spread_docs) == 2, "expected one bar per minute with ticks"
    minutes = sorted(d["minute_utc"] for d in spread_docs)
    assert minutes == [_naive_utc(hour0), _naive_utc(hour0 + timedelta(minutes=1))]

    # The wider minute (01) must have a larger spread_mean than minute 00.
    by_min = {d["minute_utc"]: d for d in spread_docs}
    assert by_min[_naive_utc(hour0 + timedelta(minutes=1))]["spread_mean"] > \
           by_min[_naive_utc(hour0)]["spread_mean"]

    # Report counters reflect the spread write path.
    assert report.spread_bars_emitted_total == 2
    assert report.spread_bars_upserted_total == 2


@pytest.mark.asyncio
async def test_runner_skips_spread_writes_when_db_is_none(
    tmp_path, monkeypatch,
) -> None:
    """db=None keeps the P0A test contract intact (no Mongo dependency)."""
    archive = BI5TickArchive(root=str(tmp_path))
    hour0 = datetime(2024, 1, 2, 7, tzinfo=timezone.utc)
    payload = _build_bi5_payload([
        (0, 1.10000, 1.10001, 1.0, 1.0),
    ])
    adapter = _FakeAdapter({hour0: payload})

    spy = _MergeRowsSpy()
    monkeypatch.setattr(runner_module, "_merge_rows", spy)

    runner = BI5IngestRunner(adapter=adapter, archive=archive, db=None)
    try:
        report = await runner.run_for_symbol(
            "EURUSD", start_utc=hour0, end_utc=hour0 + timedelta(hours=1),
        )
    finally:
        await runner.close()

    assert report.spread_bars_emitted_total == 1
    # No db handle → no Mongo writes counted.
    assert report.spread_bars_upserted_total == 0


@pytest.mark.asyncio
async def test_runner_spread_upserts_are_idempotent_across_reruns(
    tmp_path, monkeypatch, mock_db,
) -> None:
    archive = BI5TickArchive(root=str(tmp_path))
    hour0 = datetime(2024, 1, 2, 7, tzinfo=timezone.utc)
    payload = _build_bi5_payload([
        (    0, 1.10000, 1.10001, 1.0, 1.0),
        (75_000, 1.10005, 1.10006, 1.0, 1.0),
    ])
    adapter = _FakeAdapter({hour0: payload})
    monkeypatch.setattr(runner_module, "_merge_rows", _MergeRowsSpy())

    runner = BI5IngestRunner(adapter=adapter, archive=archive, db=mock_db)
    try:
        await runner.run_for_symbol(
            "EURUSD", start_utc=hour0, end_utc=hour0 + timedelta(hours=1),
        )
        # Re-run the same window. With cache_hit + idempotent upserts,
        # market_spread must NOT accumulate duplicate rows.
        await runner.run_for_symbol(
            "EURUSD", start_utc=hour0, end_utc=hour0 + timedelta(hours=1),
        )
    finally:
        await runner.close()

    count = await mock_db[MARKET_SPREAD_COLL].count_documents({})
    assert count == 2  # one per minute, NOT 4.
