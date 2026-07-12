"""
Market calendar — maps every minute of the week to "trading" or "closed",
per market type.

FOREX weekly window (UTC):
    Sunday 22:00 UTC  →  Friday 22:00 UTC.
    Closed:
      - Saturday (all day, weekday == 5)
      - Sunday before 22:00 (weekday == 6 and hour < 22)
      - Friday from 22:00 onward (weekday == 4 and hour >= 22)

CRYPTO:
    Always open (24/7).

Used by gap_analyzer and /api/data-coverage. Holidays NOT modelled here —
broker feeds (Dukascopy) include low-volume holiday bars, so treating them
as trading minutes keeps coverage honest against the downloaded data.
"""
from datetime import datetime, timedelta, timezone

INTERVAL_MINUTES: dict[str, int] = {
    "1m": 1, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "4h": 240, "1d": 1440,
}

FOREX_MINUTES_PER_WEEK = 7200    # 5 days × 1440 = 7200
CRYPTO_MINUTES_PER_WEEK = 10080  # 7 days × 1440 = 10080


def is_trading_time(timestamp: datetime, market_type: str) -> bool:
    """True when `timestamp` falls inside the trading window for the market type.

    - Forex: Sun 22:00 UTC → Fri 22:00 UTC
    - Crypto: always True
    """
    if market_type == "crypto":
        return True

    # forex (default)
    ts = timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)
    ts_utc = ts.astimezone(timezone.utc)
    weekday = ts_utc.weekday()     # Mon=0 … Sun=6
    hour = ts_utc.hour

    if weekday == 5:                              # Saturday — closed
        return False
    if weekday == 6 and hour < 22:                # Sunday before 22:00 UTC — closed
        return False
    if weekday == 4 and hour >= 22:               # Friday from 22:00 UTC — closed
        return False
    return True


def is_bi5_session_active(timestamp: datetime, market_type: str) -> bool:
    """G-1 calendar refinement — pure layer on top of ``is_trading_time``.

    Composes the weekly forex window with per-market-type *hourly*
    exclusions that reflect retail BI5 feed reality. Returns False for
    structurally empty BI5 session hours so the BI5 ingest runner can
    classify them as ``expected_empty`` and the validator's continuity
    sub-score stops collapsing on them.

    Rules (all in addition to ``is_trading_time``):
        forex  → weekday=4 (Fri) AND hour=21 → False  (retail BI5 weekly
                 wind-down before the 22:00 UTC close)
        metal  → forex rules + weekday<=4 (Mon-Fri) AND hour=21 → False
                 (Loco-London / NYMEX 5pm NY daily settlement; metals
                 close for ~1h every trading weekday)
                 + G-1.1 Phase A: empirical metal holiday hours (see
                 ``_METAL_HOLIDAY_HOURS_UTC`` below)
        index  → weekly window only (no daily-close refinement in G-1)
        crypto → always True (24/7)

    This function is deliberately additive: ``is_trading_time`` is
    UNCHANGED so /api/data-coverage, gap_analyzer, incremental_updater
    and every other consumer remain byte-identical.
    """
    # Re-use the existing weekly-window check first. Closed there ⇒
    # closed here, period.
    if not is_trading_time(timestamp, market_type):
        return False

    ts = timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)
    ts_utc = ts.astimezone(timezone.utc)
    weekday = ts_utc.weekday()
    hour = ts_utc.hour

    if market_type == "metal":
        # Daily 21:00 UTC settlement on every trading weekday (Mon-Fri).
        # Sunday 22:00 reopen is unaffected (weekday=6, hour=22).
        if weekday <= 4 and hour == 21:
            return False
        # G-1.1 Phase A: empirical metal holiday closures. Scoped
        # narrowly to known XAU zero-tick hours in the current
        # ingested cohort (May 2026). Generalized framework deferred.
        key = (ts_utc.year, ts_utc.month, ts_utc.day, ts_utc.hour)
        if key in _METAL_HOLIDAY_HOURS_UTC:
            return False
        return True

    if market_type == "forex":
        # Retail BI5 Friday wind-down hour.
        if weekday == 4 and hour == 21:
            return False
        return True

    # index / crypto / unknown ⇒ pass through (weekly window already
    # applied above, crypto is always True via is_trading_time).
    return True


# G-1.1 Phase A — empirical metal holiday closure hours (UTC).
# Scoped strictly to the currently ingested cohort (May 2026).
# Each entry is a (year, month, day, hour) tuple — closures granular
# to the hour because metals shut down for partial sessions on US
# bank holidays (e.g. Memorial Day early close).
#
# Source: empirical archive audit at /app/data/bi5/dukascopy/XAUUSD/
# (XAU session hours that decoded to zero ticks under the post-G-1
# calendar). See OPTION_A_CALENDAR_WIRING_REPORT.md §6 and
# G1_CALENDAR_REFINEMENT_COMPARISON_REPORT.md §3.3.
#
# To extend: re-audit empirically on each new month ingested and
# append confirmed zero-tick metal hours. Do NOT add speculative
# hours — only those validated against the actual BI5 archive.
_METAL_HOLIDAY_HOURS_UTC: frozenset = frozenset({
    # 2026-05-25 (Mon) — US Memorial Day, NYMEX/Loco-London early
    # close. 19:00 + 20:00 UTC = 3pm + 4pm NY time approach to the
    # shortened close.
    (2026, 5, 25, 19),
    (2026, 5, 25, 20),
})


def _forex_trading_minutes_in_day(
    day_start: datetime, range_start: datetime, range_end: datetime
) -> int:
    """Count forex trading minutes on the calendar day beginning at `day_start`,
    clipped to [range_start, range_end]. `day_start` must be 00:00 UTC of the day."""
    weekday = day_start.weekday()
    if weekday == 5:                              # Saturday — always 0
        return 0

    if weekday == 6:                              # Sunday — open 22:00 → 24:00
        trade_open = day_start.replace(hour=22)
        trade_close = day_start + timedelta(days=1)
    elif weekday == 4:                            # Friday — open 00:00 → 22:00
        trade_open = day_start
        trade_close = day_start.replace(hour=22)
    else:                                         # Mon / Tue / Wed / Thu — full day
        trade_open = day_start
        trade_close = day_start + timedelta(days=1)

    actual_open = max(trade_open, range_start)
    actual_close = min(trade_close, range_end)
    if actual_close <= actual_open:
        return 0
    return int((actual_close - actual_open).total_seconds() // 60)


def count_trading_minutes(start: datetime, end: datetime, market_type: str) -> int:
    """Total number of trading minutes in [start, end) for the given market_type.

    Uses a fast hybrid strategy:
      - Extract complete 7-day blocks → constant minutes per week.
      - Walk the remaining < 14 days minute-of-day-wise.
    """
    if end <= start:
        return 0

    # Normalize to UTC.
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    if market_type == "crypto":
        return int((end - start).total_seconds() // 60)

    # forex: day-by-day sum (accurate even for range boundaries mid-week).
    total = 0
    current = start.replace(hour=0, minute=0, second=0, microsecond=0)
    while current < end:
        total += _forex_trading_minutes_in_day(current, start, end)
        current += timedelta(days=1)
    return total


def calculate_expected_points(
    start: datetime, end: datetime, timeframe: str, market_type: str
) -> int:
    """Number of candles the dataset SHOULD contain in [start, end]
    given the market calendar and timeframe."""
    interval_min = INTERVAL_MINUTES.get(timeframe)
    if not interval_min:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    # Inclusive end: include the candle AT `end`.
    trading_min = count_trading_minutes(start, end + timedelta(minutes=1), market_type)
    expected = trading_min // interval_min
    return max(1, expected)


def count_missing_in_gap(
    gap_start: datetime, gap_end: datetime, interval_min: int, market_type: str
) -> int:
    """Return the number of EXPECTED candles between gap_start and gap_end
    (exclusive of gap_start, exclusive of gap_end) that are actually trading-time
    for this market. Weekend/closed minutes are ignored."""
    if gap_end <= gap_start:
        return 0
    delta = timedelta(minutes=interval_min)
    cursor = gap_start + delta
    missing = 0
    while cursor < gap_end:
        if is_trading_time(cursor, market_type):
            missing += 1
        cursor += delta
    return missing
