"""
Phase 6 — Data Layer Integrity tests.

Exercises the append-only contract: never overwrites existing rows,
computes the correct `last_ts → now` window, handles the seed case,
respects source lock (bid_1m vs bi5), reuses gap fill, and ingests
BI5 chunk files idempotently via `bi5_ingest_log`.

Dukascopy fetcher is mocked — we don't want network IO in tests.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from dotenv import load_dotenv
load_dotenv()

from data_engine import incremental_updater as updater
from data_engine.data_manager import _merge_rows
from engines.db import get_db


SYMBOL = "EURUSD"


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def _fresh_db():
    """Force a fresh motor client per test (pytest-asyncio uses a new
    event loop per test) and wipe the collections we touch."""
    from engines import db as _db_module
    _db_module._client = None
    _db_module._db = None
    db = get_db()
    await db.market_data.delete_many({"symbol": SYMBOL})
    await db["bi5_ingest_log"].delete_many({"symbol": SYMBOL})
    yield
    await db.market_data.delete_many({"symbol": SYMBOL})
    await db["bi5_ingest_log"].delete_many({"symbol": SYMBOL})


def _row(ts: datetime, price: float = 1.1) -> dict:
    """Shape a single candle doc at the UTC-aware iso timestamp."""
    return {
        "symbol": SYMBOL, "source": "bid_1m", "timeframe": "1h",
        "timestamp": ts.isoformat(),
        "open": price, "high": price + 0.0005,
        "low": price - 0.0005, "close": price, "volume": 1000,
    }


async def _seed(n: int = 5, base: datetime | None = None,
                source: str = "bid_1m", tf: str = "1h") -> datetime:
    db = get_db()
    base = base or datetime(2026, 4, 10, 0, 0, tzinfo=timezone.utc)
    docs = []
    for i in range(n):
        ts = base + timedelta(hours=i)
        docs.append({
            "symbol": SYMBOL, "source": source, "timeframe": tf,
            "timestamp": ts.isoformat(),
            "open": 1.1, "high": 1.105, "low": 1.095,
            "close": 1.1 + i * 0.0001, "volume": 1000,
        })
    await db.market_data.insert_many(docs)
    return base + timedelta(hours=n - 1)  # last ts


# ─────────────────────────────────────────────────────────────────────
# get_last_timestamp + _range_snapshot
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_last_timestamp_respects_source_lock():
    await _seed(n=3, source="bid_1m")
    await _seed(n=2, base=datetime(2026, 5, 1, tzinfo=timezone.utc),
                source="bi5", tf="1m")

    bid_last = await updater.get_last_timestamp(SYMBOL, "bid_1m", "1h")
    bi5_last = await updater.get_last_timestamp(SYMBOL, "bi5", "1m")
    # bi5 is later in wall-clock but source-locked → returned separately
    assert bid_last == datetime(2026, 4, 10, 2, 0, tzinfo=timezone.utc)
    assert bi5_last == datetime(2026, 5, 1, 1, 0, tzinfo=timezone.utc)
    assert bid_last != bi5_last


@pytest.mark.asyncio
async def test_last_timestamp_empty_returns_none():
    assert await updater.get_last_timestamp(SYMBOL, "bid_1m", "1h") is None


@pytest.mark.asyncio
async def test_last_timestamp_rejects_unknown_source():
    with pytest.raises(ValueError):
        await updater.get_last_timestamp(SYMBOL, "not_a_source", "1h")


# ─────────────────────────────────────────────────────────────────────
# Append-only _merge_rows — NEVER overwrites
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_merge_rows_append_only_preserves_existing_values():
    db = get_db()
    ts = datetime(2026, 4, 10, 0, 0, tzinfo=timezone.utc)
    original = _row(ts, price=1.2345)
    await db.market_data.insert_one(original)

    # Incoming row with SAME timestamp but DIFFERENT prices — must be ignored.
    incoming = _row(ts, price=9.9999)
    stats = await _merge_rows(
        [incoming], SYMBOL, "bid_1m", "1h", append_only=True,
    )
    assert stats["upserted"] == 0
    assert stats["matched"] == 1
    assert stats["append_only"] is True

    stored = await db.market_data.find_one(
        {"symbol": SYMBOL, "timestamp": ts.isoformat()}, {"_id": 0}
    )
    # Values UNCHANGED — append-only protected manual data.
    assert stored["close"] == 1.2345
    assert stored["open"] == 1.2345


@pytest.mark.asyncio
async def test_merge_rows_default_still_overwrites():
    """Regression guard: the default (non-append_only) path must still
    overwrite — existing CSV-upload semantics preserved."""
    db = get_db()
    ts = datetime(2026, 4, 10, 0, 0, tzinfo=timezone.utc)
    await db.market_data.insert_one(_row(ts, price=1.0))
    await _merge_rows([_row(ts, price=5.0)], SYMBOL, "bid_1m", "1h")
    stored = await db.market_data.find_one(
        {"symbol": SYMBOL, "timestamp": ts.isoformat()}, {"_id": 0}
    )
    assert stored["close"] == 5.0  # overwritten as before


# ─────────────────────────────────────────────────────────────────────
# incremental_update_bid — window resolution + append-only
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bid_window_resolution_append_mode(monkeypatch):
    """When data exists, the fetch window MUST start just after last_ts."""
    last_ts = await _seed(n=5)  # 2026-04-10 04:00 UTC

    captured = {}
    async def fake_download(symbol, tf, df, dt):
        captured["from"] = df
        captured["to"] = dt
        return {"rows_inserted": 0, "rows_skipped": 0}

    monkeypatch.setattr(
        "data_engine.dukascopy_downloader.download_and_store", fake_download
    )
    monkeypatch.setitem(
        __import__("data_engine.dukascopy_downloader",
                   fromlist=["INSTRUMENT_MAP"]).INSTRUMENT_MAP,
        SYMBOL, "stubbed",
    )

    result = await updater.incremental_update_bid(
        SYMBOL, "1h", fix_gaps_after=False,
    )
    assert result["mode"] == "append_only"
    assert result["window_mode"] == "append"
    # Window starts at last_ts + 1h = 2026-04-10 05:00 → date 2026-04-10
    assert captured["from"] == "2026-04-10"
    assert result["last_timestamp_before"] == last_ts.isoformat()


@pytest.mark.asyncio
async def test_bid_window_resolution_seed_mode(monkeypatch):
    """Empty dataset → seed the last 7 days."""
    captured = {}
    async def fake_download(symbol, tf, df, dt):
        captured["from"] = df
        captured["to"] = dt
        return {"rows_inserted": 0, "rows_skipped": 0}

    monkeypatch.setattr(
        "data_engine.dukascopy_downloader.download_and_store", fake_download
    )
    monkeypatch.setitem(
        __import__("data_engine.dukascopy_downloader",
                   fromlist=["INSTRUMENT_MAP"]).INSTRUMENT_MAP,
        SYMBOL, "stubbed",
    )

    result = await updater.incremental_update_bid(SYMBOL, "1h", fix_gaps_after=False)
    assert result["window_mode"] == "seed"
    today = datetime.now(timezone.utc).date()
    expected_from = (today - timedelta(days=7)).isoformat()
    assert captured["from"] == expected_from


@pytest.mark.asyncio
async def test_bid_manual_override_window(monkeypatch):
    captured = {}
    async def fake_download(symbol, tf, df, dt):
        captured["from"] = df
        captured["to"] = dt
        return {"rows_inserted": 0, "rows_skipped": 0}
    monkeypatch.setattr(
        "data_engine.dukascopy_downloader.download_and_store", fake_download
    )
    monkeypatch.setitem(
        __import__("data_engine.dukascopy_downloader",
                   fromlist=["INSTRUMENT_MAP"]).INSTRUMENT_MAP,
        SYMBOL, "stubbed",
    )

    await updater.incremental_update_bid(
        SYMBOL, "1h",
        date_from="2025-01-01", date_to="2025-01-10",
        fix_gaps_after=False,
    )
    assert captured == {"from": "2025-01-01", "to": "2025-01-10"}


@pytest.mark.asyncio
async def test_bid_unknown_symbol_returns_warning_no_fetch():
    result = await updater.incremental_update_bid(
        "ABCDEF", "1h", fix_gaps_after=False,
    )
    assert result["candles_added"] == 0
    assert "not Dukascopy-fetchable" in (result.get("warning") or "")


# ─────────────────────────────────────────────────────────────────────
# incremental_update_bi5 — chunk ingest from disk
# ─────────────────────────────────────────────────────────────────────

def _write_bi5_chunk(tmpdir: str, filename: str, rows: list[tuple[str, float]]):
    """Write a minimal BI5-flavoured chunk CSV (timestamp + bid price)."""
    path = os.path.join(tmpdir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write("timestamp,bid,volume\n")
        for ts, price in rows:
            f.write(f"{ts},{price},100\n")
    return path


@pytest.mark.asyncio
async def test_bi5_chunk_ingest_appends_only_new_rows():
    with tempfile.TemporaryDirectory() as td:
        # Seed bi5 with one row at 12:00
        await _seed(n=1, base=datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc),
                    source="bi5", tf="1m")

        _write_bi5_chunk(td, "EURUSD_bi5_chunk_a.csv", [
            ("2026-04-10 12:00:00", 1.2345),  # ≤ last_ts → dropped
            ("2026-04-10 12:01:00", 1.2346),  # new → appended
            ("2026-04-10 12:02:00", 1.2347),  # new → appended
        ])

        result = await updater.incremental_update_bi5(
            SYMBOL, "1m", import_dir=td,
        )
        assert result["mode"] == "append_only"
        assert result["ticks_added"] == 2
        assert result["rows_below_cutoff"] == 1
        assert result["files_ingested"] == 1
        # The original seed row was NOT modified (only new rows were added).
        db = get_db()
        count = await db.market_data.count_documents(
            {"symbol": SYMBOL, "source": "bi5", "timeframe": "1m"}
        )
        assert count == 3


@pytest.mark.asyncio
async def test_bi5_idempotent_on_rerun():
    with tempfile.TemporaryDirectory() as td:
        _write_bi5_chunk(td, "EURUSD_bi5_chunk.csv", [
            ("2026-04-10 12:00:00", 1.1),
            ("2026-04-10 12:01:00", 1.2),
        ])

        r1 = await updater.incremental_update_bi5(SYMBOL, "1m", import_dir=td)
        r2 = await updater.incremental_update_bi5(SYMBOL, "1m", import_dir=td)

        assert r1["ticks_added"] == 2
        # Second run: file already in bi5_ingest_log → skipped entirely.
        assert r2["ticks_added"] == 0
        assert r2["files_ingested"] == 0
        assert r2["per_file"][0]["status"] == "already_ingested"


@pytest.mark.asyncio
async def test_bi5_symbol_and_token_filter():
    """Only files that match (symbol AND contain 'bi5') should be picked up."""
    with tempfile.TemporaryDirectory() as td:
        _write_bi5_chunk(td, "GBPUSD_bi5_chunk.csv", [("2026-04-10 12:00:00", 1.0)])
        _write_bi5_chunk(td, "EURUSD_daily.csv",     [("2026-04-10 12:00:00", 1.0)])  # no bi5
        _write_bi5_chunk(td, "EURUSD_bi5_v2.csv",    [("2026-04-10 12:00:00", 1.0)])

        result = await updater.incremental_update_bi5(SYMBOL, "1m", import_dir=td)
        assert result["files_scanned"] == 1
        assert result["files_ingested"] == 1
        assert result["per_file"][0]["file"] == "EURUSD_bi5_v2.csv"


# ─────────────────────────────────────────────────────────────────────
# Alignment health probe
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bid_bi5_alignment_detects_drift():
    await _seed(n=1, base=datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc),
                source="bid_1m", tf="1m")
    await _seed(n=1, base=datetime(2026, 4, 10, 18, 0, tzinfo=timezone.utc),
                source="bi5", tf="1m")

    a = await updater.validate_bid_bi5_alignment(SYMBOL, "1m", "1m")
    assert a["aligned"] is False          # 6h drift > 60 min threshold
    assert a["drift_minutes"] == 360.0


@pytest.mark.asyncio
async def test_bid_bi5_alignment_empty_sources():
    a = await updater.validate_bid_bi5_alignment(SYMBOL)
    assert a["aligned"] is False
    assert a["reason"] == "one_or_both_empty"
