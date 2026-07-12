"""G-1.1 Phase A — empirical metal holiday closure tests.

Scoped strictly to the May 2026 Memorial Day hours that emerged from
empirical archive audit. No generalized holiday framework.

Constraint envelope (operator-imposed):
    * No certification math changes
    * No threshold changes
    * No density table changes
    * No verdict overrides
"""
from __future__ import annotations

from datetime import datetime, timezone

from data_engine.market_calendar import (
    _METAL_HOLIDAY_HOURS_UTC,
    is_bi5_session_active,
    is_trading_time,
)


def _utc(y, m, d, h):
    return datetime(y, m, d, h, tzinfo=timezone.utc)


# -----------------------------------------------------------------------------
# Test 1 — the two known Memorial Day metal hours are closed
# -----------------------------------------------------------------------------
def test_memorial_day_2026_metal_hours_closed():
    """May 25 2026 19:00 and 20:00 UTC must be closed for metal."""
    assert is_bi5_session_active(_utc(2026, 5, 25, 19), "metal") is False
    assert is_bi5_session_active(_utc(2026, 5, 25, 20), "metal") is False


# -----------------------------------------------------------------------------
# Test 2 — surrounding metal hours unaffected
# -----------------------------------------------------------------------------
def test_memorial_day_2026_surrounding_hours_open_for_metal():
    """May 25 2026 18:00 and 22:00 UTC are normal trading for metal."""
    assert is_bi5_session_active(_utc(2026, 5, 25, 18), "metal") is True
    # 21:00 still closed by the daily-settlement rule (G-1), not G-1.1
    assert is_bi5_session_active(_utc(2026, 5, 25, 21), "metal") is False
    # 22:00 reopens
    assert is_bi5_session_active(_utc(2026, 5, 25, 22), "metal") is True


# -----------------------------------------------------------------------------
# Test 3 — FX is UNAFFECTED by metal holiday hours
# -----------------------------------------------------------------------------
def test_memorial_day_2026_does_not_affect_fx():
    """Holiday closures are metal-only; FX trades normally."""
    assert is_bi5_session_active(_utc(2026, 5, 25, 19), "forex") is True
    assert is_bi5_session_active(_utc(2026, 5, 25, 20), "forex") is True


# -----------------------------------------------------------------------------
# Test 4 — index / crypto unaffected
# -----------------------------------------------------------------------------
def test_memorial_day_2026_does_not_affect_index_or_crypto():
    assert is_bi5_session_active(_utc(2026, 5, 25, 19), "index") is True
    assert is_bi5_session_active(_utc(2026, 5, 25, 19), "crypto") is True


# -----------------------------------------------------------------------------
# Test 5 — is_trading_time still byte-identical (no leakage)
# -----------------------------------------------------------------------------
def test_is_trading_time_unchanged_for_memorial_day():
    """G-1.1 must NOT alter the weekly-window function."""
    assert is_trading_time(_utc(2026, 5, 25, 19), "forex") is True
    assert is_trading_time(_utc(2026, 5, 25, 19), "metal") is True
    assert is_trading_time(_utc(2026, 5, 25, 19), "crypto") is True


# -----------------------------------------------------------------------------
# Test 6 — holiday table is scoped narrowly (no overreach)
# -----------------------------------------------------------------------------
def test_holiday_table_is_narrowly_scoped():
    """G-1.1 Phase A intentionally encodes only May 25 2026 19:00 + 20:00.
    Any expansion needs a separate authorization gate.
    """
    assert _METAL_HOLIDAY_HOURS_UTC == frozenset({
        (2026, 5, 25, 19),
        (2026, 5, 25, 20),
    })


# -----------------------------------------------------------------------------
# Test 7 — May 2026 full-month XAU hour count after G-1.1
# -----------------------------------------------------------------------------
def test_full_may_2026_metal_hour_count_after_g11():
    """After G-1.1: metal_closed = 240 weekend + 21 weekday-21 + 2 holiday = 263."""
    from datetime import timedelta
    start = _utc(2026, 5, 1, 0)
    end = _utc(2026, 6, 1, 0)
    cur = start
    metal_open = metal_closed = 0
    while cur < end:
        if is_bi5_session_active(cur, "metal"):
            metal_open += 1
        else:
            metal_closed += 1
        cur += timedelta(hours=1)
    assert metal_closed == 263, f"metal_closed={metal_closed}"
    assert metal_open == 744 - 263, f"metal_open={metal_open}"
