"""G-1 calendar refinement tests — pure unit tests for
``is_bi5_session_active`` in ``data_engine.market_calendar``.

Constraint envelope (operator-imposed):
    * No certification math changes
    * No threshold changes
    * No density table changes
    * No verdict overrides

The function is a pure layer on top of the existing
``is_trading_time``. These tests lock down per-market-type behaviour
without touching any math.
"""
from __future__ import annotations

from datetime import datetime, timezone


from data_engine.market_calendar import is_bi5_session_active, is_trading_time


def _utc(y, m, d, h):
    return datetime(y, m, d, h, tzinfo=timezone.utc)


# -----------------------------------------------------------------------------
# Test 1 — Forex Friday 21:00 UTC excluded; surrounding hours unaffected
# -----------------------------------------------------------------------------
def test_forex_friday_21_excluded():
    """May 1 2026 is a Friday. Fri 21:00 UTC must be marked closed
    (retail BI5 wind-down) — but only that one hour."""
    # Fri 20:00 UTC → open
    assert is_bi5_session_active(_utc(2026, 5, 1, 20), "forex") is True
    # Fri 21:00 UTC → closed (G-1 refinement)
    assert is_bi5_session_active(_utc(2026, 5, 1, 21), "forex") is False
    # Fri 22:00 UTC → closed (already closed via is_trading_time)
    assert is_bi5_session_active(_utc(2026, 5, 1, 22), "forex") is False
    # Thu 21:00 UTC (Apr 30 2026) → open
    assert is_bi5_session_active(_utc(2026, 4, 30, 21), "forex") is True
    # Mon 21:00 UTC (May 4 2026) → open
    assert is_bi5_session_active(_utc(2026, 5, 4, 21), "forex") is True


# -----------------------------------------------------------------------------
# Test 2 — Metal weekday 21:00 UTC excluded; Sunday reopen unaffected
# -----------------------------------------------------------------------------
def test_metal_weekday_21_excluded():
    """Metals (XAUUSD) close every Mon–Fri at 21:00 UTC for daily
    NYMEX/Loco-London settlement. The Sunday 22:00 UTC reopen is
    unaffected (it's not 21:00 anyway)."""
    # Mon-Fri 21:00 UTC → closed
    for day in (4, 5, 6, 7, 8):  # May 4 (Mon) through May 8 (Fri) 2026
        assert is_bi5_session_active(_utc(2026, 5, day, 21), "metal") is False, (
            f"metal {day}/5 21:00 should be closed"
        )
    # Mon 20:00 UTC → open
    assert is_bi5_session_active(_utc(2026, 5, 4, 20), "metal") is True
    # Mon 22:00 UTC → open (after daily settlement window)
    assert is_bi5_session_active(_utc(2026, 5, 4, 22), "metal") is True


# -----------------------------------------------------------------------------
# Test 3 — Sunday reopen unaffected for metals
# -----------------------------------------------------------------------------
def test_metal_sunday_open_unaffected():
    """Metal Sun 22:00 UTC (May 3 2026) → market reopens; no G-1 rule
    fires at the weekly open boundary."""
    assert is_bi5_session_active(_utc(2026, 5, 3, 22), "metal") is True
    assert is_bi5_session_active(_utc(2026, 5, 3, 23), "metal") is True


# -----------------------------------------------------------------------------
# Test 4 — Crypto always active (24/7)
# -----------------------------------------------------------------------------
def test_crypto_always_active():
    """Crypto market never closes — G-1 must pass through to True."""
    # Sat midnight UTC
    assert is_bi5_session_active(_utc(2026, 5, 2, 0), "crypto") is True
    # Sun 12:00 UTC (would be forex-closed)
    assert is_bi5_session_active(_utc(2026, 5, 3, 12), "crypto") is True
    # Fri 21:00 UTC (would be FX wind-down)
    assert is_bi5_session_active(_utc(2026, 5, 1, 21), "crypto") is True


# -----------------------------------------------------------------------------
# Test 5 — Index passes through weekly window only (no G-1 daily rule)
# -----------------------------------------------------------------------------
def test_index_passes_through_weekly_window_only():
    """Index has no daily-close refinement in G-1 — matches forex
    weekly window only."""
    # Mon 21:00 UTC → open (no daily settlement rule for index in G-1)
    assert is_bi5_session_active(_utc(2026, 5, 4, 21), "index") is True
    # Sat 12:00 UTC → closed (via is_trading_time forex weekly window)
    assert is_bi5_session_active(_utc(2026, 5, 2, 12), "index") is False


# -----------------------------------------------------------------------------
# Test 6 — Weekend / Saturday is closed for all non-crypto market types
# -----------------------------------------------------------------------------
def test_saturday_closed_for_non_crypto():
    """Saturday is closed for forex / metal / index (delegated to
    is_trading_time)."""
    sat = _utc(2026, 5, 2, 12)  # Saturday
    assert is_bi5_session_active(sat, "forex") is False
    assert is_bi5_session_active(sat, "metal") is False
    assert is_bi5_session_active(sat, "index") is False
    # Sanity: same hour returns False via the base function too
    assert is_trading_time(sat, "forex") is False


# -----------------------------------------------------------------------------
# Test 7 — is_trading_time is byte-identical (regression guard)
# -----------------------------------------------------------------------------
def test_is_trading_time_unchanged():
    """Sentinel: G-1 must NOT alter is_trading_time. Spot-check a
    handful of representative hours."""
    # Fri 21:00 UTC: G-1 says closed for forex/metal; is_trading_time
    # still says open (weekly window only).
    assert is_trading_time(_utc(2026, 5, 1, 21), "forex") is True
    assert is_trading_time(_utc(2026, 5, 4, 21), "forex") is True
    # Sat: closed
    assert is_trading_time(_utc(2026, 5, 2, 12), "forex") is False
    # Crypto: always True
    assert is_trading_time(_utc(2026, 5, 2, 12), "crypto") is True


# -----------------------------------------------------------------------------
# Test 8 — Full May 2026 hour count predictions
# -----------------------------------------------------------------------------
def test_full_may_2026_hour_counts():
    """Verify expected hour counts for a full month."""
    from datetime import timedelta
    start = _utc(2026, 5, 1, 0)
    end = _utc(2026, 6, 1, 0)
    cur = start

    fx_open = fx_closed = metal_open = metal_closed = 0
    while cur < end:
        if is_bi5_session_active(cur, "forex"):
            fx_open += 1
        else:
            fx_closed += 1
        if is_bi5_session_active(cur, "metal"):
            metal_open += 1
        else:
            metal_closed += 1
        cur += timedelta(hours=1)

    # FX: 504 weekly-open hours, minus 5 Friday-21 hours = 499 open,
    #     240 weekend + 5 Fri21 = 245 closed
    assert fx_open == 499, f"fx_open={fx_open}"
    assert fx_closed == 245, f"fx_closed={fx_closed}"
    # Metal: 504 weekly-open, minus 5 Fri21 + ~22 weekday 21:00 = 477 open
    # Specifically: Mon-Fri 21:00 over the 4 full trading weeks + Friday 21:00s
    # May 4-8 (M-F), May 11-15, May 18-22, May 25-29 = 5*4 = 20 weekday 21:00 plus
    # May 1 (Fri 21) = already counted in those 20? May 1 is Friday so weekday=4 (Fri).
    # Mon-Fri 21:00 hours in May 2026: every weekday at 21:00 = 21 trading days × 1 hr = 21
    # (May has 21 weekdays Mon-Fri.) Plus the weekly close already applies to Fri.
    # The metal rule encompasses the forex Fri-21 rule, so closed = 240 weekend + 21 weekday-21 = 261
    # Post G-1.1: add 2 Memorial Day holiday hours (May 25 19:00 + 20:00) ⇒ 263
    assert metal_closed == 263, f"metal_closed={metal_closed}"
    assert metal_open == 744 - 263, f"metal_open={metal_open}"
