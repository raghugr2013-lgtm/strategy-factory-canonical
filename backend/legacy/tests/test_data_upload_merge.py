"""
Market-data upload MERGE behavior (previously: overwrite).

Verifies that uploading CSVs for the same (symbol, timeframe) APPENDS new
bars and OVERWRITES overlapping bars, instead of wiping the collection
and re-inserting.

Tests run in-process against the real MongoDB instance using a dedicated
test (symbol, timeframe) pair; each test cleans up after itself.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Load backend .env so MONGO_URL / DB_NAME are set before importing engines.
try:
    from dotenv import load_dotenv
    load_dotenv(BACKEND_DIR / ".env")
except ImportError:
    pass

from engines.db import get_db
from data_engine.data_manager import (
    parse_and_store_csv,
    parse_and_store_csv_streaming,
)

# Dedicated test namespace — NOT in ALLOWED_SYMBOLS to keep production
# data untouched. parse_and_store_csv itself doesn't validate symbol.
TEST_SYMBOL = "__TEST_MERGE__"
TEST_TIMEFRAME = "1m"


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) \
        if hasattr(asyncio, "get_event_loop") and asyncio.get_event_loop().is_running() is False \
        else asyncio.new_event_loop().run_until_complete(coro)


@pytest.fixture
def clean_db():
    async def _wipe():
        db = get_db()
        await db.market_data.delete_many(
            {"symbol": TEST_SYMBOL, "timeframe": TEST_TIMEFRAME}
        )
    asyncio.run(_wipe())
    yield
    asyncio.run(_wipe())


def _csv(rows: list) -> bytes:
    """Build a small CSV payload from (ts, open, high, low, close, volume) rows."""
    header = "timestamp,open,high,low,close,volume\n"
    body = "\n".join(",".join(str(x) for x in r) for r in rows)
    return (header + body).encode("utf-8")


def _bar(day: int, price: float):
    """Produce (ts, o, h, l, c, v) for day d of January 2024 at 00:00."""
    return (
        f"2024-01-{day:02d} 00:00:00",
        price, price + 0.5, price - 0.5, price + 0.1,
        1000,
    )


# ══════════════════════════════════════════════════════════════════════════
# 1. Append-only upload (no overlap)
# ══════════════════════════════════════════════════════════════════════════
class TestAppendNoOverlap:
    def test_second_upload_appends(self, clean_db):
        # Upload days 1-3
        first = asyncio.run(parse_and_store_csv(
            _csv([_bar(d, 1.10) for d in range(1, 4)]),
            TEST_SYMBOL, TEST_TIMEFRAME,
        ))
        assert first["previous_row_count"] == 0
        assert first["new_rows_added"] == 3
        assert first["rows_overwritten"] == 0
        assert first["total_rows_after"] == 3

        # Upload days 4-6 (disjoint)
        second = asyncio.run(parse_and_store_csv(
            _csv([_bar(d, 1.20) for d in range(4, 7)]),
            TEST_SYMBOL, TEST_TIMEFRAME,
        ))
        assert second["previous_row_count"] == 3
        assert second["new_rows_added"] == 3
        assert second["rows_overwritten"] == 0
        assert second["total_rows_after"] == 6
        # Merge response fields
        assert second["new_rows_pct"] == 100.0
        assert second["overlap_pct"] == 0.0
        assert "warning" not in second   # no overlap → no warning

    def test_second_upload_does_not_wipe_first(self, clean_db):
        asyncio.run(parse_and_store_csv(
            _csv([_bar(d, 1.10) for d in range(1, 4)]),
            TEST_SYMBOL, TEST_TIMEFRAME,
        ))
        asyncio.run(parse_and_store_csv(
            _csv([_bar(d, 1.20) for d in range(4, 7)]),
            TEST_SYMBOL, TEST_TIMEFRAME,
        ))
        async def _fetch():
            db = get_db()
            cur = db.market_data.find(
                {"symbol": TEST_SYMBOL, "timeframe": TEST_TIMEFRAME},
                {"_id": 0, "timestamp": 1},
            ).sort("timestamp", 1)
            return [d async for d in cur]
        docs = asyncio.run(_fetch())
        tss = [d["timestamp"] for d in docs]
        # Day-1 row MUST still be present after second upload.
        assert any("2024-01-01" in t for t in tss)
        assert len(docs) == 6


# ══════════════════════════════════════════════════════════════════════════
# 2. Overlap merge — "keep latest" policy
# ══════════════════════════════════════════════════════════════════════════
class TestOverlapMerge:
    def test_overlapping_rows_overwritten_with_new_values(self, clean_db):
        # Upload days 1-5 with price 1.10
        asyncio.run(parse_and_store_csv(
            _csv([_bar(d, 1.10) for d in range(1, 6)]),
            TEST_SYMBOL, TEST_TIMEFRAME,
        ))
        # Re-upload days 3-7 with different price (1.20) — overlap = days 3,4,5
        second = asyncio.run(parse_and_store_csv(
            _csv([_bar(d, 1.20) for d in range(3, 8)]),
            TEST_SYMBOL, TEST_TIMEFRAME,
        ))
        assert second["previous_row_count"] == 5
        assert second["rows_overwritten"] == 3    # days 3, 4, 5
        assert second["new_rows_added"] == 2      # days 6, 7
        assert second["total_rows_after"] == 7
        assert second["overlap_pct"] == 60.0      # 3 of 5 rows overlapped
        assert second["new_rows_pct"] == 40.0
        assert "warning" in second                 # overlap detected

        # Verify that the overlap rows now carry the NEW price (1.20), not 1.10.
        async def _fetch_day3():
            db = get_db()
            return await db.market_data.find_one(
                {
                    "symbol": TEST_SYMBOL,
                    "timeframe": TEST_TIMEFRAME,
                    "timestamp": {"$regex": "^2024-01-03"},
                },
                {"_id": 0, "open": 1},
            )
        doc = asyncio.run(_fetch_day3())
        assert doc is not None
        assert doc["open"] == 1.20   # overwritten

    def test_dataset_sorted_on_read(self, clean_db):
        # Upload out-of-order
        asyncio.run(parse_and_store_csv(
            _csv([_bar(5, 1.10), _bar(1, 1.10), _bar(3, 1.10)]),
            TEST_SYMBOL, TEST_TIMEFRAME,
        ))
        async def _fetch_sorted():
            db = get_db()
            cur = db.market_data.find(
                {"symbol": TEST_SYMBOL, "timeframe": TEST_TIMEFRAME},
                {"_id": 0, "timestamp": 1},
            ).sort("timestamp", 1)
            return [d["timestamp"] for d in [doc async for doc in cur]]
        tss = asyncio.run(_fetch_sorted())
        assert tss == sorted(tss)


# ══════════════════════════════════════════════════════════════════════════
# 3. Intra-batch duplicates are collapsed (keep latest occurrence)
# ══════════════════════════════════════════════════════════════════════════
class TestIntraBatchDuplicates:
    def test_last_occurrence_wins_within_single_upload(self, clean_db):
        # Same timestamp 3 times with different open prices; last wins.
        duplicates_csv = _csv([
            _bar(1, 1.10)[:],
            _bar(1, 1.50)[:],   # overwrites
            _bar(1, 1.99)[:],   # final keeper
            _bar(2, 1.10)[:],
        ])
        res = asyncio.run(parse_and_store_csv(duplicates_csv, TEST_SYMBOL, TEST_TIMEFRAME))
        assert res["intra_batch_duplicates"] == 2
        assert res["total_rows_after"] == 2

        async def _fetch_day1():
            db = get_db()
            return await db.market_data.find_one(
                {
                    "symbol": TEST_SYMBOL,
                    "timeframe": TEST_TIMEFRAME,
                    "timestamp": {"$regex": "^2024-01-01"},
                },
                {"_id": 0, "open": 1},
            )
        doc = asyncio.run(_fetch_day1())
        assert doc["open"] == 1.99


# ══════════════════════════════════════════════════════════════════════════
# 4. Streaming upload has the same merge semantics
# ══════════════════════════════════════════════════════════════════════════
class TestStreamingMerge:
    def test_streaming_merge_overlap(self, clean_db):
        # Seed via in-memory path
        asyncio.run(parse_and_store_csv(
            _csv([_bar(d, 1.10) for d in range(1, 6)]),
            TEST_SYMBOL, TEST_TIMEFRAME,
        ))

        # Re-upload overlapping range via streaming path
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="wb") as tmp:
            tmp.write(_csv([_bar(d, 1.20) for d in range(4, 9)]))
            tmp_path = tmp.name
        try:
            res = asyncio.run(parse_and_store_csv_streaming(
                tmp_path, TEST_SYMBOL, TEST_TIMEFRAME
            ))
        finally:
            os.unlink(tmp_path)

        assert res["previous_row_count"] == 5
        assert res["rows_overwritten"] == 2    # days 4, 5
        assert res["new_rows_added"] == 3      # days 6, 7, 8
        assert res["total_rows_after"] == 8
        assert "warning" in res


# ══════════════════════════════════════════════════════════════════════════
# 5. Validation — column mismatch rejected; symbol/timeframe validated at API
# ══════════════════════════════════════════════════════════════════════════
class TestValidation:
    def test_missing_columns_rejected(self, clean_db):
        bad = b"timestamp,price\n2024-01-01 00:00:00,1.10\n"
        with pytest.raises(ValueError) as exc:
            asyncio.run(parse_and_store_csv(bad, TEST_SYMBOL, TEST_TIMEFRAME))
        assert "Missing required columns" in str(exc.value)

    def test_empty_csv_rejected(self, clean_db):
        with pytest.raises(ValueError):
            asyncio.run(parse_and_store_csv(b"", TEST_SYMBOL, TEST_TIMEFRAME))

    def test_response_has_back_compat_keys(self, clean_db):
        res = asyncio.run(parse_and_store_csv(
            _csv([_bar(1, 1.10)]),
            TEST_SYMBOL, TEST_TIMEFRAME,
        ))
        # Legacy keys expected by existing API callers
        for k in ("rows_inserted", "rows_skipped", "symbol", "timeframe",
                  "first_timestamp", "last_timestamp"):
            assert k in res
        # New Phase-9 merge accounting keys
        for k in ("previous_row_count", "new_rows_added", "rows_overwritten",
                  "total_rows_after", "overlap_pct", "new_rows_pct",
                  "intra_batch_duplicates"):
            assert k in res
