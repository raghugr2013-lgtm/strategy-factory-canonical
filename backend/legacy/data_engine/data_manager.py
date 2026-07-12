"""
Data manager: parses CSV uploads and stores OHLCV data in MongoDB.
Schema: symbol, source, timeframe, timestamp, open, high, low, close, volume
  - `source` ∈ {"bid_1m", "bi5"} distinguishes candle vs tick-derived streams.
    Each (symbol, source, timeframe, timestamp) is an independent row; the two
    sources are NEVER merged on disk or in coverage.
Supports both in-memory parsing (small files) and streaming parsing (large files).

Upload semantics (per-(symbol,source,timeframe)):
  Uploads MERGE into the existing dataset. Rows keyed by
  (symbol, source, timeframe, timestamp) are upserted — a new CSV for the same
  triple therefore APPENDS new bars and OVERWRITES overlapping bars with
  the most recent upload's values ("keep latest").  Within a single
  upload, intra-file duplicates are collapsed to the last occurrence.
"""
import csv
import io
import os
import logging
import pandas as pd
from pymongo import UpdateOne
from engines.db import get_db

logger = logging.getLogger(__name__)

# Allowed source identifiers. `bid_1m` = OHLCV candle stream (default).
# `bi5` = tick-derived stream (raw Dukascopy .bi5 ticks or tick-aggregated bars).
ALLOWED_SOURCES = ("bid_1m", "bi5")
DEFAULT_SOURCE = "bid_1m"


class TimestampParseError(ValueError):
    """Raised when a timestamp cannot be parsed; tracked separately from
    other row-level errors so invalid-timestamp rows are dropped (not fatal)."""
    pass

# Accepted column name mappings (lowercase)
COLUMN_MAP = {
    "timestamp": ["timestamp", "time", "date", "datetime", "date_time"],
    "open": ["open", "o"],
    "high": ["high", "h"],
    "low": ["low", "l"],
    "close": ["close", "c"],
    "volume": ["volume", "vol", "v", "tick_volume"],
}


def _match_column(header: str) -> str | None:
    """Map a CSV header to a canonical field name."""
    h = header.strip().lower()
    for canonical, aliases in COLUMN_MAP.items():
        if h in aliases:
            return canonical
    return None


def _parse_timestamp(val: str) -> str:
    """Flexible timestamp parser (pandas-based).

    Supports (non-exhaustive):
      - YYYY-MM-DD HH:MM:SS / ISO 8601 / with or without T / with tz
      - YYYY-MM-DD HH:MM, YYYY-MM-DD
      - MM/DD/YYYY HH:MM[:SS], DD/MM/YYYY HH:MM[:SS]
      - DD.MM.YYYY HH:MM:SS (Dukascopy)
      - YYYYMMDD HHMMSS   (Histdata)
      - numeric unix epoch (s or ms)

    Returns ISO-8601 UTC string. Raises TimestampParseError on failure so the
    caller can drop the row and count it (errors='coerce' semantics).
    """
    s = (val or "").strip()
    if not s:
        raise TimestampParseError("empty timestamp")

    # 1) pandas generic parser — handles the vast majority of formats.
    ts = pd.to_datetime(s, errors="coerce", utc=False)

    # 2) explicit fallbacks for formats pandas won't auto-detect.
    if pd.isna(ts):
        for fmt in ("%Y%m%d %H%M%S", "%Y%m%d%H%M%S", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M"):
            ts = pd.to_datetime(s, format=fmt, errors="coerce")
            if not pd.isna(ts):
                break

    # 3) numeric epoch (seconds or milliseconds).
    if pd.isna(ts):
        try:
            num = float(s)
            unit = "ms" if num > 1e12 else "s"
            ts = pd.to_datetime(num, unit=unit, errors="coerce")
        except (ValueError, OSError):
            ts = pd.NaT

    if pd.isna(ts):
        raise TimestampParseError(f"Cannot parse timestamp: {val}")

    # Normalize to UTC.
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    return ts.isoformat()


async def _merge_rows(
    rows: list,
    symbol: str,
    source: str,
    timeframe: str,
    *,
    append_only: bool = False,
) -> dict:
    """
    Merge-upsert rows into market_data keyed by (symbol, source, timeframe, timestamp).

    - Intra-batch duplicates are collapsed to the last occurrence (keep latest).
    - `append_only=True` (Phase 6): uses `$setOnInsert` so rows that already
      exist are NEVER overwritten — critical for auto-fetchers that must not
      clobber manually uploaded data. Default remains `$set` (keep-latest)
      to preserve the existing CSV-upload semantics.
    - Returns upserted (genuinely-new) and matched (overlap) counts. In
      append_only mode, `matched` counts collisions that were preserved.
    """
    if not rows:
        return {"upserted": 0, "matched": 0, "intra_batch_duplicates": 0}

    db = get_db()

    # Collapse intra-batch duplicates: last occurrence wins ("keep latest").
    by_ts: dict[str, dict] = {}
    for r in rows:
        by_ts[r["timestamp"]] = r
    deduped = list(by_ts.values())

    update_op = "$setOnInsert" if append_only else "$set"
    ops = [
        UpdateOne(
            {"symbol": symbol, "source": source, "timeframe": timeframe, "timestamp": r["timestamp"]},
            {update_op: r},
            upsert=True,
        )
        for r in deduped
    ]
    result = await db.market_data.bulk_write(ops, ordered=False)

    return {
        "upserted": result.upserted_count,
        "matched": result.matched_count,
        "intra_batch_duplicates": len(rows) - len(deduped),
        "append_only": append_only,
    }


def _merge_response(
    *,
    symbol: str,
    timeframe: str,
    rows_parsed: int,
    errors: int,
    first_ts: str,
    last_ts: str,
    previous_row_count: int,
    total_rows_after: int,
    upserted: int,
    matched: int,
    intra_batch_duplicates: int,
    invalid_timestamp_rows: int = 0,
    source: str = DEFAULT_SOURCE,
    extra: dict = None,
) -> dict:
    """Normalized response for both upload paths."""
    basis = max(1, rows_parsed)
    new_pct = round(upserted / basis * 100, 1)
    overlap_pct = round(matched / basis * 100, 1)
    # "Duplicates removed" = timestamps that already existed and were collapsed
    # into the merged dataset (intra-batch dupes + overlaps with existing rows).
    duplicates_removed = matched + intra_batch_duplicates
    resp = {
        # Back-compat keys (unchanged by the merge refactor):
        "rows_inserted": upserted,
        "rows_skipped": errors,
        "symbol": symbol,
        "source": source,
        "timeframe": timeframe,
        "first_timestamp": first_ts,
        "last_timestamp": last_ts,
        # Merge accounting (new):
        "previous_row_count": previous_row_count,
        "new_rows_added": upserted,
        "rows_overwritten": matched,
        "duplicates_removed": duplicates_removed,
        "total_rows_after": total_rows_after,
        "overlap_pct": overlap_pct,
        "new_rows_pct": new_pct,
        "intra_batch_duplicates": intra_batch_duplicates,
        # Debug counters (timestamp-parsing):
        "parsed_rows_count": rows_parsed,
        "invalid_timestamp_rows": invalid_timestamp_rows,
    }
    if matched > 0:
        resp["warning"] = (
            f"{matched} row(s) overlap existing data for {symbol} {timeframe}; "
            f"overwritten with incoming values (keep-latest policy)."
        )
    if extra:
        resp.update(extra)
    return resp


async def parse_and_store_csv(
    file_content: bytes, symbol: str, timeframe: str, source: str = DEFAULT_SOURCE,
) -> dict:
    """Parse CSV content and MERGE rows into MongoDB market_data collection."""
    if source not in ALLOWED_SOURCES:
        raise ValueError(f"source must be one of: {', '.join(ALLOWED_SOURCES)}")
    text = file_content.decode("utf-8-sig")  # handle BOM
    reader = csv.reader(io.StringIO(text))

    # Read header
    header_row = next(reader, None)
    if not header_row:
        raise ValueError("CSV file is empty")

    # Map columns
    col_indices = {}
    for i, h in enumerate(header_row):
        canonical = _match_column(h)
        if canonical:
            col_indices[canonical] = i

    required = {"timestamp", "open", "high", "low", "close"}
    missing = required - set(col_indices.keys())
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}. Found: {', '.join(header_row)}")

    has_volume = "volume" in col_indices

    # Parse rows
    rows = []
    errors = 0
    invalid_ts = 0
    for line_num, row in enumerate(reader, start=2):
        if not row or all(c.strip() == "" for c in row):
            continue
        try:
            ts = _parse_timestamp(row[col_indices["timestamp"]])
            doc = {
                "symbol": symbol,
                "source": source,
                "timeframe": timeframe,
                "timestamp": ts,
                "open": float(row[col_indices["open"]]),
                "high": float(row[col_indices["high"]]),
                "low": float(row[col_indices["low"]]),
                "close": float(row[col_indices["close"]]),
                "volume": float(row[col_indices["volume"]]) if has_volume else 0,
            }
            rows.append(doc)
        except TimestampParseError:
            # Drop row silently, count it. Don't count against the hard error cap.
            invalid_ts += 1
        except (ValueError, IndexError):
            errors += 1
            if errors > 50:
                raise ValueError("Too many parse errors (50+). Check CSV format.")

    if invalid_ts:
        logger.warning("CSV upload %s/%s/%s: dropped %d rows with invalid timestamps", symbol, source, timeframe, invalid_ts)

    if not rows:
        raise ValueError("No valid data rows found in CSV")

    db = get_db()

    # Count existing rows BEFORE merging (per (symbol, source, timeframe)).
    previous_row_count = await db.market_data.count_documents(
        {"symbol": symbol, "source": source, "timeframe": timeframe}
    )

    # Merge-upsert (NO delete_many — that was the overwrite bug).
    merge_stats = await _merge_rows(rows, symbol, source, timeframe)

    # Count rows AFTER merging.
    total_rows_after = await db.market_data.count_documents(
        {"symbol": symbol, "source": source, "timeframe": timeframe}
    )

    # Ensure compound index for efficient per-source queries.
    await db.market_data.create_index(
        [("symbol", 1), ("source", 1), ("timeframe", 1), ("timestamp", 1)]
    )

    rows.sort(key=lambda r: r["timestamp"])
    return _merge_response(
        symbol=symbol,
        source=source,
        timeframe=timeframe,
        rows_parsed=len(rows),
        errors=errors,
        first_ts=rows[0]["timestamp"],
        last_ts=rows[-1]["timestamp"],
        previous_row_count=previous_row_count,
        total_rows_after=total_rows_after,
        upserted=merge_stats["upserted"],
        matched=merge_stats["matched"],
        intra_batch_duplicates=merge_stats["intra_batch_duplicates"],
        invalid_timestamp_rows=invalid_ts,
    )


BATCH_SIZE = 5000  # Insert in batches for large files


async def parse_and_store_csv_streaming(
    file_path: str, symbol: str, timeframe: str, source: str = DEFAULT_SOURCE,
) -> dict:
    """
    Stream-parse a large CSV file from disk and MERGE rows into MongoDB in batches.
    Memory-efficient: never loads the entire file into RAM.
    """
    if source not in ALLOWED_SOURCES:
        raise ValueError(f"source must be one of: {', '.join(ALLOWED_SOURCES)}")
    if not os.path.isfile(file_path):
        raise ValueError(f"File not found: {file_path}")

    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)

    with open(file_path, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header_row = next(reader, None)
        if not header_row:
            raise ValueError("CSV file is empty")

        col_indices = {}
        for i, h in enumerate(header_row):
            canonical = _match_column(h)
            if canonical:
                col_indices[canonical] = i

        required = {"timestamp", "open", "high", "low", "close"}
        missing = required - set(col_indices.keys())
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(missing)}. Found: {', '.join(header_row)}")

        has_volume = "volume" in col_indices

    db = get_db()

    # Count existing rows BEFORE merging (no delete), scoped to source.
    previous_row_count = await db.market_data.count_documents(
        {"symbol": symbol, "source": source, "timeframe": timeframe}
    )

    total_parsed = 0
    total_upserted = 0
    total_matched = 0
    total_intra_dup = 0
    total_errors = 0
    total_invalid_ts = 0
    first_ts = None
    last_ts = None
    batch = []

    with open(file_path, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader)  # skip header

        for row in reader:
            if not row or all(c.strip() == "" for c in row):
                continue
            try:
                ts = _parse_timestamp(row[col_indices["timestamp"]])
                doc = {
                    "symbol": symbol,
                    "source": source,
                    "timeframe": timeframe,
                    "timestamp": ts,
                    "open": float(row[col_indices["open"]]),
                    "high": float(row[col_indices["high"]]),
                    "low": float(row[col_indices["low"]]),
                    "close": float(row[col_indices["close"]]),
                    "volume": float(row[col_indices["volume"]]) if has_volume else 0,
                }
                batch.append(doc)
                total_parsed += 1
                if first_ts is None or ts < first_ts:
                    first_ts = ts
                if last_ts is None or ts > last_ts:
                    last_ts = ts

                if len(batch) >= BATCH_SIZE:
                    stats = await _merge_rows(batch, symbol, source, timeframe)
                    total_upserted += stats["upserted"]
                    total_matched += stats["matched"]
                    total_intra_dup += stats["intra_batch_duplicates"]
                    batch = []
            except TimestampParseError:
                total_invalid_ts += 1
            except (ValueError, IndexError):
                total_errors += 1

    if total_invalid_ts:
        logger.warning("CSV streaming upload %s/%s/%s: dropped %d rows with invalid timestamps", symbol, source, timeframe, total_invalid_ts)

    # Merge remaining batch
    if batch:
        stats = await _merge_rows(batch, symbol, source, timeframe)
        total_upserted += stats["upserted"]
        total_matched += stats["matched"]
        total_intra_dup += stats["intra_batch_duplicates"]

    # Ensure compound index including source
    await db.market_data.create_index(
        [("symbol", 1), ("source", 1), ("timeframe", 1), ("timestamp", 1)]
    )

    total_rows_after = await db.market_data.count_documents(
        {"symbol": symbol, "source": source, "timeframe": timeframe}
    )

    return _merge_response(
        symbol=symbol,
        source=source,
        timeframe=timeframe,
        rows_parsed=total_parsed,
        errors=total_errors,
        first_ts=first_ts,
        last_ts=last_ts,
        previous_row_count=previous_row_count,
        total_rows_after=total_rows_after,
        upserted=total_upserted,
        matched=total_matched,
        intra_batch_duplicates=total_intra_dup,
        invalid_timestamp_rows=total_invalid_ts,
        extra={"file_size_mb": round(file_size_mb, 1), "method": "streaming"},
    )


async def list_server_files(directory: str = "/app/data_imports") -> list:
    """List CSV files available for server-side import."""
    if not os.path.isdir(directory):
        return []
    files = []
    for f in sorted(os.listdir(directory)):
        if f.lower().endswith(".csv"):
            full_path = os.path.join(directory, f)
            size_mb = os.path.getsize(full_path) / (1024 * 1024)
            files.append({
                "filename": f,
                "path": full_path,
                "size_mb": round(size_mb, 1),
            })
    return files


async def get_data_summary() -> list:
    """
    Get summary of all uploaded market data with coverage and quality metrics.
    Groups by (symbol, source, timeframe) so bid_1m and bi5 are reported separately.
    """
    from data_engine.gap_analyzer import quick_coverage
    from config.symbols import get_market_type

    db = get_db()

    # One-time backfill: any legacy row missing `source` is stamped as bid_1m.
    await db.market_data.update_many(
        {"source": {"$exists": False}},
        {"$set": {"source": DEFAULT_SOURCE}},
    )

    pipeline = [
        {
            "$group": {
                "_id": {
                    "symbol": "$symbol",
                    "source": {"$ifNull": ["$source", DEFAULT_SOURCE]},
                    "timeframe": "$timeframe",
                },
                "count": {"$sum": 1},
                "first_ts": {"$min": "$timestamp"},
                "last_ts": {"$max": "$timestamp"},
            }
        },
        {"$sort": {"_id.symbol": 1, "_id.source": 1, "_id.timeframe": 1}},
    ]
    cursor = db.market_data.aggregate(pipeline)
    results = []
    async for doc in cursor:
        sym = doc["_id"]["symbol"]
        src = doc["_id"]["source"]
        tf = doc["_id"]["timeframe"]

        cov = await quick_coverage(sym, tf, source=src)

        results.append({
            "symbol": sym,
            "source": src,
            "market_type": get_market_type(sym),
            "timeframe": tf,
            "records": doc["count"],
            "first_timestamp": doc["first_ts"],
            "last_timestamp": doc["last_ts"],
            "coverage_pct": cov["coverage_pct"],
            "expected_candles": cov["expected_candles"],
            "quality_status": cov["quality_status"],
            "gaps_count": cov["gaps_count"],
            "missing_candles": cov.get("missing_candles", 0),
        })
    return results
