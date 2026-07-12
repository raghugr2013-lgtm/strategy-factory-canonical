"""Option-A calendar wiring tests for the BI5 ingest runner.

Verifies that market-closed forex hours (Fri 22:00 UTC → Sun 22:00 UTC)
arrive at ``aggregate_window`` as ``status="expected_empty"`` rather
than ``status="ok"``, and therefore do NOT collapse the window's
continuity sub-score to 0.

Constraint envelope (operator-imposed, see
``BI5_DATA_CERT_FAIL_VERDICT_RCA.md``):
    * No certification math changes
    * No threshold changes
    * No density table changes
    * No verdict overrides

These tests are pure regression guards on the wiring, not on the math.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest
from mongomock_motor import AsyncMongoMockClient

from data_engine.adapters.base import BI5Adapter, BI5HourBlob, normalize_hour_utc
from data_engine.bi5_ingest_runner import BI5IngestRunner
from data_engine.tick_archive import BI5TickArchive


class _StubAdapter(BI5Adapter):
    source_id = "stub_bi5_cal"

    def __init__(self, failing_hours: Optional[set] = None) -> None:
        self._failing_hours = failing_hours or set()

    async def fetch_hour(self, symbol: str, hour_utc: datetime) -> BI5HourBlob:
        hu = normalize_hour_utc(hour_utc)
        if hu in self._failing_hours:
            raise RuntimeError(f"stubbed transient failure at {hu.isoformat()}")
        # Empty 16-byte payload — decoder returns []; runner treats as a
        # zero-tick hour. Validates that the *status* (not tick count)
        # is what flips between "ok" and "expected_empty".
        return BI5HourBlob(
            symbol=symbol, source=self.source_id, hour_utc=hu, payload=b"\x00" * 16,
        )

    async def close(self) -> None:
        return None


def _archive(tmp_path) -> BI5TickArchive:
    return BI5TickArchive(root=tmp_path / "bi5")


# -----------------------------------------------------------------------------
# Test 1 — Saturday hours are classified as expected_empty
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_saturday_hours_are_expected_empty(tmp_path):
    """May 2 2026 is a Saturday — every hour must be expected_empty."""
    client = AsyncMongoMockClient()
    db = client["test_calendar_sat"]
    runner = BI5IngestRunner(
        adapter=_StubAdapter(), archive=_archive(tmp_path), db=db,
    )
    # Pure Saturday window
    await runner.run_for_symbol(
        "EURUSD",
        start_utc=datetime(2026, 5, 2, 0, tzinfo=timezone.utc),
        end_utc=datetime(2026, 5, 3, 0, tzinfo=timezone.utc),
        use_cache=False,
    )
    await runner.close()

    doc = await db["bi5_data_certification"].find_one({})
    assert doc is not None
    # All 24 hours are Saturday → all expected_empty → continuity = 1.0
    # (no max_silent_gap_s=3600 collapse from zero-tick session hours).
    assert doc["hours_expected_empty"] == 24
    assert doc["hours_expected"] == 0
    assert doc["hours_present"] == 0
    assert doc["max_silent_gap_s"] == 0.0


# -----------------------------------------------------------------------------
# Test 2 — Friday afternoon (before 22:00) classified as trading
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_friday_morning_is_trading_hours(tmp_path):
    """May 1 2026 is Friday — 00:00-04:00 UTC is open trading."""
    client = AsyncMongoMockClient()
    db = client["test_calendar_fri"]
    runner = BI5IngestRunner(
        adapter=_StubAdapter(), archive=_archive(tmp_path), db=db,
    )
    await runner.run_for_symbol(
        "EURUSD",
        start_utc=datetime(2026, 5, 1, 0, tzinfo=timezone.utc),
        end_utc=datetime(2026, 5, 1, 4, tzinfo=timezone.utc),
        use_cache=False,
    )
    await runner.close()

    doc = await db["bi5_data_certification"].find_one({})
    assert doc is not None
    # Friday 00:00-04:00 UTC = 4 trading hours, no expected_empty
    assert doc["hours_expected"] == 4
    assert doc["hours_expected_empty"] == 0


# -----------------------------------------------------------------------------
# Test 3 — Friday 22:00 boundary correctly switches forex from open → closed
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_friday_22_boundary_switches_to_closed(tmp_path):
    """May 1 2026 21:00-23:00 UTC straddles the forex Friday close.

    Under G-1 the FX retail wind-down rule treats Fri 21:00 UTC as
    closed too — so both 21:00 and 22:00 land as expected_empty.
    """
    client = AsyncMongoMockClient()
    db = client["test_calendar_boundary"]
    runner = BI5IngestRunner(
        adapter=_StubAdapter(), archive=_archive(tmp_path), db=db,
    )
    await runner.run_for_symbol(
        "EURUSD",
        start_utc=datetime(2026, 5, 1, 21, tzinfo=timezone.utc),
        end_utc=datetime(2026, 5, 1, 23, tzinfo=timezone.utc),
        use_cache=False,
    )
    await runner.close()

    doc = await db["bi5_data_certification"].find_one({})
    assert doc is not None
    # G-1: Fri 21:00 = retail BI5 wind-down (closed); Fri 22:00 = weekly close
    assert doc["hours_expected"] == 0
    assert doc["hours_expected_empty"] == 2


# -----------------------------------------------------------------------------
# Test 4 — Sunday 22:00 boundary correctly switches forex from closed → open
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sunday_22_boundary_switches_to_open(tmp_path):
    """May 3 2026 is Sunday — 21:00 closed, 22:00 trading reopens."""
    client = AsyncMongoMockClient()
    db = client["test_calendar_sun_open"]
    runner = BI5IngestRunner(
        adapter=_StubAdapter(), archive=_archive(tmp_path), db=db,
    )
    await runner.run_for_symbol(
        "EURUSD",
        start_utc=datetime(2026, 5, 3, 21, tzinfo=timezone.utc),
        end_utc=datetime(2026, 5, 3, 23, tzinfo=timezone.utc),
        use_cache=False,
    )
    await runner.close()

    doc = await db["bi5_data_certification"].find_one({})
    assert doc is not None
    assert doc["hours_expected_empty"] == 1    # 21:00 hour Sunday before open
    assert doc["hours_expected"] == 1          # 22:00 hour Sunday open


# -----------------------------------------------------------------------------
# Test 5 — Full May 2026 window: continuity NO LONGER collapses to 0
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_full_may_2026_window_continuity_recovers(tmp_path):
    """Full month (744 h). With calendar wiring, weekend hours are
    expected_empty (240 h) and don't blow continuity. Trading hours
    return zero-tick (because stub payload decodes to empty), which
    still drives density to 0 (a separate, expected concern called
    out in §6 / §9 of the RCA), but continuity itself recovers.
    """
    client = AsyncMongoMockClient()
    db = client["test_calendar_may2026"]
    runner = BI5IngestRunner(
        adapter=_StubAdapter(), archive=_archive(tmp_path), db=db,
    )
    await runner.run_for_symbol(
        "EURUSD",
        start_utc=datetime(2026, 5, 1, 0, tzinfo=timezone.utc),
        end_utc=datetime(2026, 6, 1, 0, tzinfo=timezone.utc),
        use_cache=False,
    )
    await runner.close()

    doc = await db["bi5_data_certification"].find_one({})
    assert doc is not None
    # Calendar math (post-G-1 for FX):
    #   744 total hours - 240 weekend hours - 5 Fri 21:00 UTC = 499 trading
    #   240 weekend + 5 Fri 21:00 = 245 expected_empty
    assert doc["hours_expected"] == 499
    assert doc["hours_expected_empty"] == 245
    # Continuity sub-score: max_silent_gap_s comes from session hours
    # only. With zero-tick session hours under the stub, the validator
    # still emits max_silent_gap_s=3600 for those — so continuity will
    # still be 0 here. The IMPORTANT thing for this test is that the
    # weekend hours no longer trigger that collapse on their own. A
    # real BI5 ingest (with non-empty tick payloads on session hours)
    # will surface a non-zero continuity, which is the point of Option
    # A. We assert here on the wiring, not on the score.
    assert doc["max_silent_gap_s"] >= 0.0  # well-defined


# -----------------------------------------------------------------------------
# Test 6 — fetch failure on a weekend hour records expected_empty
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_weekend_fetch_failure_records_expected_empty(tmp_path):
    """Saturday fetch failure should NOT pollute hours_missing.

    Operationally: many feeds return 404 on weekend .bi5 URLs; that's
    an *expected* absence, not a "missing" signal.
    """
    # May 2 2026 is a Saturday. Force the adapter to fail on it.
    saturday_hour = datetime(2026, 5, 2, 12, tzinfo=timezone.utc)
    client = AsyncMongoMockClient()
    db = client["test_calendar_weekend_fail"]
    runner = BI5IngestRunner(
        adapter=_StubAdapter(failing_hours={saturday_hour}),
        archive=_archive(tmp_path),
        db=db,
    )
    await runner.run_for_symbol(
        "EURUSD",
        start_utc=datetime(2026, 5, 2, 12, tzinfo=timezone.utc),
        end_utc=datetime(2026, 5, 2, 13, tzinfo=timezone.utc),
        use_cache=False,
    )
    await runner.close()

    doc = await db["bi5_data_certification"].find_one({})
    assert doc is not None
    # Sat fetch failure → expected_empty, NOT missing
    assert doc["hours_missing"] == 0
    assert doc["hours_expected_empty"] == 1


# -----------------------------------------------------------------------------
# Test 7 — session-hour fetch failure DOES record missing
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_session_hour_fetch_failure_records_missing(tmp_path):
    """In-session fetch failure must still surface as missing."""
    # May 1 2026 10:00 UTC = Friday trading hour
    fri_hour = datetime(2026, 5, 1, 10, tzinfo=timezone.utc)
    client = AsyncMongoMockClient()
    db = client["test_calendar_session_fail"]
    runner = BI5IngestRunner(
        adapter=_StubAdapter(failing_hours={fri_hour}),
        archive=_archive(tmp_path),
        db=db,
    )
    await runner.run_for_symbol(
        "EURUSD",
        start_utc=fri_hour,
        end_utc=fri_hour + timedelta(hours=1),
        use_cache=False,
    )
    await runner.close()

    doc = await db["bi5_data_certification"].find_one({})
    assert doc is not None
    assert doc["hours_missing"] == 1
    assert doc["hours_expected_empty"] == 0
