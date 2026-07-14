"""
Dukascopy historical data downloader.
Downloads OHLCV forex data and stores in MongoDB (same schema as CSV upload).
Supports incremental updates and duplicate avoidance.

`dukascopy_python` is an OPTIONAL dependency. When it isn't installed we
degrade gracefully — the module still imports (so `legacy.api.data` can be
mounted) and every function raises a clean RuntimeError only when actually
invoked. This keeps startup clean on hosts that only need the non-ingestion
endpoints of `legacy/api/data.py`.
"""
from datetime import datetime, timezone

try:
    import dukascopy_python as dp
    from dukascopy_python.instruments import (
        INSTRUMENT_FX_MAJORS_EUR_USD,
        INSTRUMENT_FX_MAJORS_GBP_USD,
        INSTRUMENT_FX_MAJORS_USD_JPY,
        INSTRUMENT_FX_METALS_XAU_USD,
        INSTRUMENT_IDX_AMERICA_E_NQ_100,
        INSTRUMENT_VCCY_BTC_USD,
        INSTRUMENT_VCCY_ETH_USD,
    )
    _DUKASCOPY_AVAILABLE = True
except Exception:  # noqa: BLE001
    _DUKASCOPY_AVAILABLE = False
    dp = None  # type: ignore[assignment]
    # Sentinels so downstream `INSTRUMENT_MAP` still builds without crashing.
    INSTRUMENT_FX_MAJORS_EUR_USD = None
    INSTRUMENT_FX_MAJORS_GBP_USD = None
    INSTRUMENT_FX_MAJORS_USD_JPY = None
    INSTRUMENT_FX_METALS_XAU_USD = None
    INSTRUMENT_IDX_AMERICA_E_NQ_100 = None
    INSTRUMENT_VCCY_BTC_USD = None
    INSTRUMENT_VCCY_ETH_USD = None

from engines.db import get_db

# Symbol -> Dukascopy instrument mapping
INSTRUMENT_MAP = {
    "EURUSD": INSTRUMENT_FX_MAJORS_EUR_USD,
    "GBPUSD": INSTRUMENT_FX_MAJORS_GBP_USD,
    "USDJPY": INSTRUMENT_FX_MAJORS_USD_JPY,
    "XAUUSD": INSTRUMENT_FX_METALS_XAU_USD,
    "US100": INSTRUMENT_IDX_AMERICA_E_NQ_100,
    "BTCUSD": INSTRUMENT_VCCY_BTC_USD,
    "ETHUSD": INSTRUMENT_VCCY_ETH_USD,
}

# Timeframe -> Dukascopy interval mapping
INTERVAL_MAP = {
    "1m": dp.INTERVAL_MIN_1,
    "5m": dp.INTERVAL_MIN_5,
    "15m": dp.INTERVAL_MIN_15,
    "30m": dp.INTERVAL_MIN_30,
    "1h": dp.INTERVAL_HOUR_1,
    "4h": dp.INTERVAL_HOUR_4,
    "1d": dp.INTERVAL_DAY_1,
} if _DUKASCOPY_AVAILABLE else {}


def _require_dukascopy() -> None:
    if not _DUKASCOPY_AVAILABLE:
        raise RuntimeError(
            "dukascopy_python is not installed on this host — Dukascopy "
            "ingestion is disabled. Install `dukascopy-python` to enable."
        )


async def download_and_store(
    symbol: str,
    timeframe: str,
    date_from: str,
    date_to: str,
) -> dict:
    _require_dukascopy()
    """
    Download historical data from Dukascopy and store in MongoDB.
    Handles incremental updates by checking existing data and skipping duplicates.

    Args:
        symbol: Currency pair (EURUSD, GBPUSD, USDJPY)
        timeframe: Candle interval (1m, 5m, 15m, 1h, 4h, 1d)
        date_from: Start date ISO string (YYYY-MM-DD)
        date_to: End date ISO string (YYYY-MM-DD)

    Returns:
        dict with download stats
    """
    # R1 — route through market_universe_adapter for alias resolution
    # (e.g. NAS100 → US100). Falls through to legacy INSTRUMENT_MAP
    # exactly when the flag is OFF; identical behaviour for the 7
    # canonical symbols.
    try:
        from engines.market_universe_adapter import resolve_dukascopy_instrument
        instrument = resolve_dukascopy_instrument(symbol)
    except Exception:                                       # pragma: no cover
        instrument = INSTRUMENT_MAP.get(symbol)
    if not instrument:
        raise ValueError(f"Unsupported symbol: {symbol}. Use: {', '.join(INSTRUMENT_MAP.keys())}")

    interval = INTERVAL_MAP.get(timeframe)
    if not interval:
        raise ValueError(f"Unsupported timeframe: {timeframe}. Use: {', '.join(INTERVAL_MAP.keys())}")

    start_dt = datetime.strptime(date_from, "%Y-%m-%d")
    end_dt = datetime.strptime(date_to, "%Y-%m-%d")

    if end_dt <= start_dt:
        raise ValueError("date_to must be after date_from")

    # Check for existing data to support incremental updates (per-source).
    db = get_db()
    existing_timestamps = set()
    cursor = db.market_data.find(
        {"symbol": symbol, "source": "bid_1m", "timeframe": timeframe},
        {"_id": 0, "timestamp": 1},
    )
    async for doc in cursor:
        existing_timestamps.add(doc["timestamp"])

    # Fetch from Dukascopy (BID prices)
    try:
        df = dp.fetch(instrument, interval, dp.OFFER_SIDE_BID, start_dt, end_dt)
    except Exception as e:
        return {
            "success": False,
            "symbol": symbol,
            "timeframe": timeframe,
            "rows_downloaded": 0,
            "rows_inserted": 0,
            "rows_skipped": 0,
            "error": f"Data not available for {symbol} ({timeframe}): {str(e)}",
        }

    if df is None or df.empty:
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "rows_downloaded": 0,
            "rows_inserted": 0,
            "rows_skipped": 0,
            "message": "No data available for the selected range",
        }

    # Convert DataFrame to MongoDB documents
    rows_to_insert = []
    skipped = 0

    for ts, row in df.iterrows():
        # Normalize timestamp to UTC ISO string
        if ts.tzinfo is not None:
            ts_iso = ts.astimezone(timezone.utc).isoformat()
        else:
            ts_iso = ts.replace(tzinfo=timezone.utc).isoformat()

        # Skip duplicates
        if ts_iso in existing_timestamps:
            skipped += 1
            continue

        rows_to_insert.append({
            "symbol": symbol,
            "source": "bid_1m",
            "timeframe": timeframe,
            "timestamp": ts_iso,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        })

    inserted = 0
    if rows_to_insert:
        result = await db.market_data.insert_many(rows_to_insert)
        inserted = len(result.inserted_ids)

        # Ensure compound index with source
        await db.market_data.create_index(
            [("symbol", 1), ("source", 1), ("timeframe", 1), ("timestamp", 1)]
        )

    # Get date range of inserted data
    first_ts = rows_to_insert[0]["timestamp"] if rows_to_insert else None
    last_ts = rows_to_insert[-1]["timestamp"] if rows_to_insert else None

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "rows_downloaded": len(df),
        "rows_inserted": inserted,
        "rows_skipped": skipped,
        "first_timestamp": first_ts,
        "last_timestamp": last_ts,
        "message": f"Downloaded {len(df)} rows, inserted {inserted}, skipped {skipped} duplicates",
    }
