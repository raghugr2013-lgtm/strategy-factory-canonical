"""
Data quality gap analyzer.
Detects missing candle timestamps in market data, calculates coverage,
and fixes gaps via re-download. Market-aware: forex excludes closed hours
(Sun 22:00 UTC → Fri 22:00 UTC), crypto treats every minute as a trading minute.

Coverage = actual_candles / expected_trading_candles
"""
from datetime import datetime, timedelta, timezone
from engines.db import get_db
from config.symbols import get_market_type
from data_engine.market_calendar import (
    INTERVAL_MINUTES,
    calculate_expected_points,
    count_missing_in_gap,
)


def _get_quality_status(coverage_pct: float) -> str:
    """Determine data quality status based on coverage percentage."""
    if coverage_pct >= 98:
        return "Good"
    elif coverage_pct >= 90:
        return "Moderate"
    else:
        return "Poor"


async def check_gaps(symbol: str, timeframe: str, source: str = "bid_1m") -> dict:
    """
    Scan stored market data for missing candle timestamps.
    Per-source: results are scoped to (symbol, source, timeframe) so bid_1m and
    bi5 streams are NEVER merged.
    Market-aware: forex ignores closed hours (Sun 22:00 UTC → Fri 22:00 UTC),
    crypto treats every minute as a trading minute.
    Returns gap summary with count, ranges, coverage, and quality status.
    """
    interval_min = INTERVAL_MINUTES.get(timeframe)
    if not interval_min:
        return {"error": f"Unsupported timeframe: {timeframe}"}

    market_type = get_market_type(symbol)
    db = get_db()

    cursor = db.market_data.find(
        {"symbol": symbol, "source": source, "timeframe": timeframe},
        {"_id": 0, "timestamp": 1},
    ).sort("timestamp", 1)

    timestamps = []
    async for doc in cursor:
        ts_str = doc["timestamp"]
        if isinstance(ts_str, str):
            ts = datetime.fromisoformat(ts_str)
        else:
            ts = ts_str
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        timestamps.append(ts)

    total_candles = len(timestamps)
    if total_candles < 2:
        return {
            "symbol": symbol,
            "source": source,
            "market_type": market_type,
            "timeframe": timeframe,
            "total_candles": total_candles,
            "expected_candles": total_candles,
            "gaps_found": 0,
            "missing_candles": 0,
            "coverage_pct": 100.0 if total_candles > 0 else 0,
            "quality_status": "Good" if total_candles > 0 else "Poor",
            "severity": "none" if total_candles == 0 else "ok",
            "gaps": [],
            "date_range": {
                "start": timestamps[0].strftime("%Y-%m-%d %H:%M") if timestamps else None,
                "end": timestamps[-1].strftime("%Y-%m-%d %H:%M") if timestamps else None,
                "start_full": timestamps[0].isoformat() if timestamps else None,
                "end_full": timestamps[-1].isoformat() if timestamps else None,
            } if timestamps else None,
            "message": "Not enough data to analyze" if total_candles < 2 else "No gaps",
        }

    expected_delta = timedelta(minutes=interval_min)
    gaps = []
    total_missing = 0

    for i in range(1, len(timestamps)):
        diff = timestamps[i] - timestamps[i - 1]

        # Allow small tolerance (50% extra of interval) for timestamp rounding
        if diff <= expected_delta * 1.5:
            continue

        gap_start = timestamps[i - 1]
        gap_end = timestamps[i]

        # Count expected-but-missing candles in the gap, ignoring closed hours
        # for forex; for crypto every minute counts.
        missing_count = count_missing_in_gap(gap_start, gap_end, interval_min, market_type)

        if missing_count > 0:
            total_missing += missing_count
            gaps.append({
                "gap_start": gap_start.strftime("%Y-%m-%d %H:%M"),
                "gap_end": gap_end.strftime("%Y-%m-%d %H:%M"),
                "gap_start_iso": gap_start.isoformat(),
                "gap_end_iso": gap_end.isoformat(),
                "missing_candles": missing_count,
                "duration_hours": round(diff.total_seconds() / 3600, 1),
                "is_weekend_adjacent": market_type == "forex"
                    and gap_start.weekday() == 4 and gap_end.weekday() == 0,
            })

    # Calculate expected candles using market-aware calendar.
    expected_candles = calculate_expected_points(
        timestamps[0], timestamps[-1], timeframe, market_type
    )

    # Coverage = actual / expected
    coverage_pct = round((total_candles / expected_candles) * 100, 1) if expected_candles > 0 else 100.0
    coverage_pct = min(coverage_pct, 100.0)  # Cap at 100%

    quality_status = _get_quality_status(coverage_pct)

    # Determine severity
    if total_missing == 0:
        severity = "ok"
    elif total_missing < expected_candles * 0.02:
        severity = "low"
    elif total_missing < expected_candles * 0.10:
        severity = "medium"
    else:
        severity = "high"

    # Sort gaps by missing candles descending
    gaps.sort(key=lambda g: g["missing_candles"], reverse=True)

    return {
        "symbol": symbol,
        "source": source,
        "market_type": market_type,
        "timeframe": timeframe,
        "total_candles": total_candles,
        "expected_candles": expected_candles,
        "gaps_found": len(gaps),
        "missing_candles": total_missing,
        "coverage_pct": coverage_pct,
        "quality_status": quality_status,
        "severity": severity,
        "date_range": {
            "start": timestamps[0].strftime("%Y-%m-%d %H:%M"),
            "end": timestamps[-1].strftime("%Y-%m-%d %H:%M"),
            "start_full": timestamps[0].isoformat(),
            "end_full": timestamps[-1].isoformat(),
        },
        "gaps": gaps[:50],  # Limit to 50 largest gaps for response size
        "message": f"Found {len(gaps)} gaps with {total_missing} missing candles "
                   f"({coverage_pct}% coverage, {quality_status})",
    }


async def quick_coverage(symbol: str, timeframe: str, source: str = "bid_1m") -> dict:
    """
    Fast coverage check for dataset listing. Market-aware (forex vs crypto)
    AND per-source (bid_1m vs bi5).
    Returns coverage %, quality status, and rough gap count.
    """
    interval_min = INTERVAL_MINUTES.get(timeframe)
    if not interval_min:
        return {"coverage_pct": 0, "quality_status": "Poor", "gaps_count": 0, "expected_candles": 0, "market_type": get_market_type(symbol), "source": source}

    market_type = get_market_type(symbol)
    db = get_db()

    pipeline = [
        {"$match": {"symbol": symbol, "source": source, "timeframe": timeframe}},
        {
            "$group": {
                "_id": None,
                "count": {"$sum": 1},
                "first_ts": {"$min": "$timestamp"},
                "last_ts": {"$max": "$timestamp"},
            }
        },
    ]
    results = []
    async for doc in db.market_data.aggregate(pipeline):
        results.append(doc)

    if not results or results[0]["count"] < 2:
        count = results[0]["count"] if results else 0
        return {
            "coverage_pct": 100.0 if count > 0 else 0,
            "quality_status": "Good" if count > 0 else "Poor",
            "gaps_count": 0,
            "expected_candles": count,
            "market_type": market_type,
            "source": source,
        }

    total_candles = results[0]["count"]
    first_str = results[0]["first_ts"]
    last_str = results[0]["last_ts"]

    # Parse timestamps
    if isinstance(first_str, str):
        first_ts = datetime.fromisoformat(first_str)
    else:
        first_ts = first_str
    if isinstance(last_str, str):
        last_ts = datetime.fromisoformat(last_str)
    else:
        last_ts = last_str

    if first_ts.tzinfo is None:
        first_ts = first_ts.replace(tzinfo=timezone.utc)
    if last_ts.tzinfo is None:
        last_ts = last_ts.replace(tzinfo=timezone.utc)

    expected = calculate_expected_points(first_ts, last_ts, timeframe, market_type)
    coverage = round((total_candles / expected) * 100, 1) if expected > 0 else 100.0
    coverage = min(coverage, 100.0)

    missing = max(0, expected - total_candles)
    # Rough gap estimate: if missing > 0, estimate gaps based on ratio
    # (exact gap count requires full scan, but this is good enough for listing)
    estimated_gaps = 0
    if missing > 0:
        # Rough heuristic: assume gaps are clustered
        bars_per_day = max(1, 1440 // interval_min)
        estimated_gaps = max(1, missing // bars_per_day)

    return {
        "coverage_pct": coverage,
        "quality_status": _get_quality_status(coverage),
        "gaps_count": estimated_gaps,
        "expected_candles": expected,
        "missing_candles": missing,
        "market_type": market_type,
        "source": source,
    }


async def fix_gaps(symbol: str, timeframe: str) -> dict:
    """
    Fix gaps by re-downloading missing segments from Dukascopy.
    Only downloads the specific missing date ranges, not the full dataset.
    Returns fix summary.
    """
    from data_engine.dukascopy_downloader import download_and_store, INSTRUMENT_MAP

    # First check if symbol is supported for download
    if symbol not in INSTRUMENT_MAP:
        return {
            "success": False,
            "error": f"Cannot auto-fix: {symbol} is not available for Dukascopy download",
        }

    # Get current gaps
    gap_result = await check_gaps(symbol, timeframe)
    gaps = gap_result.get("gaps", [])

    if not gaps:
        return {
            "success": True,
            "symbol": symbol,
            "timeframe": timeframe,
            "gaps_fixed": 0,
            "rows_inserted": 0,
            "message": "No gaps to fix",
            "coverage_before": gap_result.get("coverage_pct", 100),
            "coverage_after": gap_result.get("coverage_pct", 100),
        }

    coverage_before = gap_result.get("coverage_pct", 0)
    total_inserted = 0
    gaps_fixed = 0
    errors = []

    for gap in gaps:
        gap_start_dt = datetime.fromisoformat(gap["gap_start_iso"])
        gap_end_dt = datetime.fromisoformat(gap["gap_end_iso"])

        # Format as YYYY-MM-DD for the downloader
        date_from = gap_start_dt.strftime("%Y-%m-%d")
        date_to = (gap_end_dt + timedelta(days=1)).strftime("%Y-%m-%d")

        try:
            result = await download_and_store(symbol, timeframe, date_from, date_to)
            if result.get("success") is False:
                errors.append(f"Gap {date_from} to {date_to}: {result.get('error', 'Unknown error')}")
                continue
            inserted = result.get("rows_inserted", 0)
            total_inserted += inserted
            if inserted > 0:
                gaps_fixed += 1
        except Exception as e:
            errors.append(f"Gap {date_from} to {date_to}: {str(e)}")

    # Re-check coverage after fix
    post_check = await check_gaps(symbol, timeframe)
    coverage_after = post_check.get("coverage_pct", coverage_before)

    return {
        "success": True,
        "symbol": symbol,
        "timeframe": timeframe,
        "gaps_attempted": len(gaps),
        "gaps_fixed": gaps_fixed,
        "rows_inserted": total_inserted,
        "coverage_before": coverage_before,
        "coverage_after": coverage_after,
        "errors": errors[:10] if errors else [],
        "message": f"Fixed {gaps_fixed}/{len(gaps)} gaps, inserted {total_inserted} rows. "
                   f"Coverage: {coverage_before}% → {coverage_after}%"
        + (f" ({len(errors)} errors)" if errors else ""),
    }
