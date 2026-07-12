"""
Phase 6 — Data Layer Integrity (Incremental Updater).

APPEND-ONLY orchestrator for market data top-ups. Guarantees:

  • NEVER overwrites or deletes existing rows (insert-if-missing only).
  • Incremental: detects the last stored timestamp per (symbol, source, tf)
    and fetches ONLY the open range [last_ts + 1 interval, now].
  • Source-locked: bid_1m and bi5 are read/written strictly per `source`
    — the two streams are never merged on disk.
  • Gap-aware: after append, runs a per-source gap scan and (for BID only,
    where a fetcher exists) fills detected gaps.
  • Consistency: chronological order is guaranteed by the timestamp index;
    this module additionally validates BID↔BI5 temporal alignment as a
    health signal.

Reuses — does NOT duplicate — existing engines:
  - `data_engine.dukascopy_downloader.download_and_store`  (already dedup-safe)
  - `data_engine.gap_analyzer.check_gaps / fix_gaps`       (market-aware)
  - `data_engine.data_manager._merge_rows(..., append_only=True)` (Phase 6)

All public helpers return a structured log:
    {
        candles_added: int,
        ticks_added:   int,
        gaps_filled:   int,
        range_before:  { first, last },
        range_after:   { first, last },
        source:        str,
        symbol:        str,
        timeframe:     str,
        mode:          "append_only",
        ...
    }
"""

from __future__ import annotations

import csv
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from data_engine.data_manager import (
    ALLOWED_SOURCES,
    TimestampParseError,
    _merge_rows,
    _parse_timestamp,
)
from data_engine.gap_analyzer import check_gaps, fix_gaps
from data_engine.market_calendar import INTERVAL_MINUTES
from engines.db import get_db

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Range helpers
# ──────────────────────────────────────────────────────────────────────

async def get_last_timestamp(
    symbol: str, source: str, timeframe: str
) -> Optional[datetime]:
    """Return the most recent stored timestamp for (symbol, source, tf),
    or None if the dataset is empty. Source-locked (never crosses streams)."""
    if source not in ALLOWED_SOURCES:
        raise ValueError(f"source must be one of {ALLOWED_SOURCES}")
    db = get_db()
    doc = await db.market_data.find_one(
        {"symbol": symbol, "source": source, "timeframe": timeframe},
        sort=[("timestamp", -1)],
        projection={"_id": 0, "timestamp": 1},
    )
    if not doc:
        return None
    ts = doc["timestamp"]
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


async def _range_snapshot(symbol: str, source: str, timeframe: str) -> Dict[str, Any]:
    """Fast first/last/count triple for before/after reporting."""
    db = get_db()
    pipeline = [
        {"$match": {"symbol": symbol, "source": source, "timeframe": timeframe}},
        {"$group": {"_id": None,
                    "count": {"$sum": 1},
                    "first": {"$min": "$timestamp"},
                    "last":  {"$max": "$timestamp"}}},
    ]
    agg = [d async for d in db.market_data.aggregate(pipeline)]
    if not agg:
        return {"count": 0, "first": None, "last": None}
    return {"count": agg[0]["count"],
            "first": agg[0]["first"],
            "last": agg[0]["last"]}


def _resolve_window(
    last_ts: Optional[datetime],
    interval_min: int,
    date_from: Optional[str],
    date_to: Optional[str],
) -> tuple[str, str, str]:
    """Pick (date_from, date_to, mode) in YYYY-MM-DD format.
      - override : explicit manual window
      - append   : (last_ts + 1 interval) → today+1
      - seed     : dataset empty → last 7 days
    """
    today = datetime.now(timezone.utc).date()
    if date_from and date_to:
        return date_from, date_to, "override"
    if last_ts is not None:
        start = (last_ts + timedelta(minutes=interval_min)).date()
        # Never go backwards; clamp to today-1 to keep at least a day's window.
        if start > today:
            start = today
        return start.isoformat(), (today + timedelta(days=1)).isoformat(), "append"
    seed_start = today - timedelta(days=7)
    return seed_start.isoformat(), (today + timedelta(days=1)).isoformat(), "seed"


# ──────────────────────────────────────────────────────────────────────
# BID — incremental candle top-up
# ──────────────────────────────────────────────────────────────────────

async def incremental_update_bid(
    symbol: str,
    timeframe: str,
    *,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    fix_gaps_after: bool = True,
) -> Dict[str, Any]:
    """
    Append-only BID top-up. Detects last stored timestamp, fetches only the
    new range, and skips any row that already exists (idempotent).

    The underlying `download_and_store` already filters against existing
    timestamps before insert — this function guarantees source lock
    (`bid_1m`) and adds the `last_ts → now` window resolution + optional
    gap fill.
    """
    from data_engine.dukascopy_downloader import INSTRUMENT_MAP, download_and_store

    source = "bid_1m"
    interval_min = INTERVAL_MINUTES.get(timeframe)
    if not interval_min:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    if symbol not in INSTRUMENT_MAP:
        return {
            "symbol": symbol, "timeframe": timeframe, "source": source,
            "mode": "append_only", "candles_added": 0, "ticks_added": 0,
            "gaps_filled": 0, "range_before": None, "range_after": None,
            "warning": f"{symbol} is not Dukascopy-fetchable (manual upload only)",
        }

    before = await _range_snapshot(symbol, source, timeframe)
    last_ts = await get_last_timestamp(symbol, source, timeframe)
    df_from, df_to, mode = _resolve_window(last_ts, interval_min, date_from, date_to)

    dl = await download_and_store(symbol, timeframe, df_from, df_to)
    candles_added = int(dl.get("rows_inserted", 0))
    gaps_filled = 0
    gap_info: Optional[Dict[str, Any]] = None
    if fix_gaps_after:
        gaps_before = await check_gaps(symbol, timeframe, source=source)
        if (gaps_before.get("gaps_found") or 0) > 0:
            fix = await fix_gaps(symbol, timeframe)
            gaps_filled = int(fix.get("gaps_fixed", 0))
            gap_info = {
                "gaps_before": gaps_before.get("gaps_found"),
                "gaps_fixed": gaps_filled,
                "rows_after_fix": fix.get("rows_inserted", 0),
                "coverage_before": fix.get("coverage_before"),
                "coverage_after": fix.get("coverage_after"),
            }

    after = await _range_snapshot(symbol, source, timeframe)

    return {
        "symbol": symbol, "timeframe": timeframe, "source": source,
        "mode": "append_only", "window_mode": mode,
        "window": {"from": df_from, "to": df_to},
        "candles_added": candles_added,
        "ticks_added": 0,
        "candles_skipped": int(dl.get("rows_skipped", 0)),
        "gaps_filled": gaps_filled,
        "gap_info": gap_info,
        "range_before": before,
        "range_after": after,
        "last_timestamp_before": last_ts.isoformat() if last_ts else None,
        "download_error": dl.get("error"),
    }


# ──────────────────────────────────────────────────────────────────────
# BID — historical backfill (BACKWARDS extension)
# ──────────────────────────────────────────────────────────────────────

# Dukascopy is happiest in monthly chunks for multi-year ranges. We split
# the requested backfill window into chunks of this size before calling
# `download_and_store` repeatedly; each chunk is dedup-safe because the
# downloader filters against existing timestamps before insert.
_BACKFILL_CHUNK_DAYS = 90

# Tolerance in days — we consider a dataset "already at target" if its
# first_ts is within this many days of the desired backfill start. Avoids
# re-fetching an irrelevant ~3-day sliver every tick.
_BACKFILL_TOLERANCE_DAYS = 3


async def historical_backfill(
    symbol: str,
    timeframe: str,
    *,
    target_months: int,
    source: str = "bid_1m",
    chunk_days: int = _BACKFILL_CHUNK_DAYS,
    max_chunks: int = 60,
) -> Dict[str, Any]:
    """
    Extend the dataset BACKWARDS to cover at least `target_months` of
    history. Idempotent — no-op when the existing first_ts is already
    older than `today - target_months`.

    Steps:
      1. Compute `target_start = today - target_months * 30.44 days`.
      2. Read the current `first_ts` from market_data.
      3. If `first_ts is None`     → fetch [target_start, today].
         If `first_ts ≤ target_start + tolerance` → already covered, skip.
         Else                       → fetch [target_start, first_ts - 1 interval]
                                       in `chunk_days` chunks (dedup-safe).
      4. Return a structured log identical in shape to `incremental_update_bid`.

    Pure delegate to `download_and_store` — never modifies the underlying
    downloader. Append-only by virtue of the downloader's existing
    duplicate-skip step.
    """
    from data_engine.dukascopy_downloader import INSTRUMENT_MAP, download_and_store

    if source != "bid_1m":
        return {
            "symbol": symbol, "timeframe": timeframe, "source": source,
            "mode": "backfill", "candles_added": 0, "skipped_reason":
                "backfill only supported for source=bid_1m",
        }

    interval_min = INTERVAL_MINUTES.get(timeframe)
    if not interval_min:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    if symbol not in INSTRUMENT_MAP:
        return {
            "symbol": symbol, "timeframe": timeframe, "source": source,
            "mode": "backfill", "candles_added": 0,
            "warning": f"{symbol} is not Dukascopy-fetchable",
        }
    target_months = max(1, int(target_months))

    today = datetime.now(timezone.utc).date()
    target_start = today - timedelta(days=int(target_months * 30.44))

    before = await _range_snapshot(symbol, source, timeframe)
    first_ts: Optional[datetime] = None
    if before.get("count"):
        f = before.get("first")
        if isinstance(f, str):
            first_ts = datetime.fromisoformat(f.replace("Z", "+00:00"))
        elif isinstance(f, datetime):
            first_ts = f if f.tzinfo else f.replace(tzinfo=timezone.utc)

    # Build the [from, to] backfill window.
    if first_ts is None:
        backfill_from = target_start
        backfill_to   = today + timedelta(days=1)
        skip_reason   = None
    else:
        first_date = first_ts.date()
        if first_date <= target_start + timedelta(days=_BACKFILL_TOLERANCE_DAYS):
            return {
                "symbol": symbol, "timeframe": timeframe, "source": source,
                "mode": "backfill", "candles_added": 0,
                "target_months": target_months,
                "target_start": target_start.isoformat(),
                "actual_first": first_ts.isoformat(),
                "skipped_reason": "already at or beyond target coverage",
                "range_before": before, "range_after": before,
            }
        backfill_from = target_start
        # End the backfill 1 day before first_ts so we don't re-fetch the
        # already-stored range (the dedup step would skip it anyway, but
        # this keeps the network footprint tight).
        backfill_to = first_date
        skip_reason = None

    # Walk backwards in `chunk_days` chunks (latest-chunk first so that if
    # the tick is interrupted the most useful range is already on disk).
    chunks: list[tuple[str, str]] = []
    cur_to = backfill_to
    while cur_to > backfill_from and len(chunks) < max_chunks:
        cur_from = max(backfill_from, cur_to - timedelta(days=chunk_days))
        chunks.append((cur_from.isoformat(), cur_to.isoformat()))
        cur_to = cur_from
    if not chunks:
        return {
            "symbol": symbol, "timeframe": timeframe, "source": source,
            "mode": "backfill", "candles_added": 0,
            "target_months": target_months,
            "skipped_reason": skip_reason or "empty backfill window",
            "range_before": before, "range_after": before,
        }

    total_added = 0
    total_skipped = 0
    chunk_logs: list[dict] = []
    last_error: Optional[str] = None
    for cf, ct in chunks:
        try:
            dl = await download_and_store(symbol, timeframe, cf, ct)
            added = int(dl.get("rows_inserted") or 0)
            skipped = int(dl.get("rows_skipped") or 0)
            err = dl.get("error")
            total_added += added
            total_skipped += skipped
            chunk_logs.append({"from": cf, "to": ct, "added": added,
                               "skipped": skipped, "error": err})
            if err:
                last_error = err
                # Soft-stop: if a chunk fails we continue; downloader is
                # idempotent so a future tick will retry.
        except Exception as e:
            last_error = str(e)[:240]
            chunk_logs.append({"from": cf, "to": ct, "added": 0,
                               "skipped": 0, "error": last_error})

    after = await _range_snapshot(symbol, source, timeframe)
    return {
        "symbol": symbol, "timeframe": timeframe, "source": source,
        "mode": "backfill",
        "target_months": target_months,
        "target_start": target_start.isoformat(),
        "window": {"from": backfill_from.isoformat(),
                   "to":   backfill_to.isoformat()},
        "chunks": chunk_logs,
        "candles_added": total_added,
        "candles_skipped": total_skipped,
        "range_before": before,
        "range_after": after,
        "download_error": last_error,
    }



# ──────────────────────────────────────────────────────────────────────
# BI5 — chunk-file append
# ──────────────────────────────────────────────────────────────────────

# Matches files like:  EURUSD_bi5_2026-04-19.csv   XAUUSD.bi5.ticks.csv
#   — plain substring match (case-insensitive); underscores are word chars so
#     a `\bbi5\b` regex would reject `_bi5_` which is the most common chunk
#     naming convention.
_BI5_FILENAME_RE = re.compile(r"(?i)bi5")


def _matches_symbol(filename: str, symbol: str) -> bool:
    """Loose symbol match inside the filename (case-insensitive)."""
    return symbol.upper() in filename.upper()


async def incremental_update_bi5(
    symbol: str,
    timeframe: str = "1m",
    *,
    import_dir: str = "/app/data_imports",
    max_files: int = 20,
) -> Dict[str, Any]:
    """
    Append-only BI5 top-up from chunk files on disk.

    Contract (since there is no raw .bi5 tick fetcher wired yet — see PRD
    backlog P1):
      • Scans `import_dir` for CSV files whose name contains the symbol
        AND the token 'bi5'.
      • For each new file (not previously ingested), reads rows, drops
        any row with ts ≤ last_stored_timestamp for (symbol, bi5, tf),
        then merges the rest with `append_only=True` — NEVER overwrites
        an existing row.
      • Records ingested files in `bi5_ingest_log` so repeat scans skip
        already-processed chunks (avoids duplicate downloads/merges even
        if filenames overlap).

    Returns the standard Phase-6 log shape (`ticks_added` populated,
    `candles_added = 0`).
    """
    source = "bi5"
    db = get_db()
    before = await _range_snapshot(symbol, source, timeframe)
    last_ts = await get_last_timestamp(symbol, source, timeframe)

    if not os.path.isdir(import_dir):
        return {
            "symbol": symbol, "timeframe": timeframe, "source": source,
            "mode": "append_only", "candles_added": 0, "ticks_added": 0,
            "gaps_filled": 0, "range_before": before, "range_after": before,
            "files_scanned": 0, "files_ingested": 0,
            "warning": f"import_dir not found: {import_dir}",
        }

    candidate_files: List[str] = []
    for fname in sorted(os.listdir(import_dir)):
        if not fname.lower().endswith(".csv"):
            continue
        if not _BI5_FILENAME_RE.search(fname):
            continue
        if not _matches_symbol(fname, symbol):
            continue
        candidate_files.append(fname)
    candidate_files = candidate_files[:max_files]

    ingested_hashes = set()
    async for d in db["bi5_ingest_log"].find(
        {"symbol": symbol, "source": source, "timeframe": timeframe},
        {"_id": 0, "file_key": 1},
    ):
        ingested_hashes.add(d["file_key"])

    files_ingested = 0
    total_added = 0
    total_skipped_preexisting = 0
    total_below_cutoff = 0
    per_file: List[Dict[str, Any]] = []

    for fname in candidate_files:
        path = os.path.join(import_dir, fname)
        try:
            st = os.stat(path)
        except FileNotFoundError:
            continue
        file_key = f"{fname}:{st.st_size}:{int(st.st_mtime)}"
        if file_key in ingested_hashes:
            per_file.append({"file": fname, "status": "already_ingested"})
            continue

        rows, dropped = _parse_bi5_csv(path, symbol, source, timeframe, last_ts)
        total_below_cutoff += dropped["below_cutoff"]

        merge_stats = await _merge_rows(
            rows, symbol, source, timeframe, append_only=True,
        )
        added = int(merge_stats["upserted"])
        preserved = int(merge_stats["matched"])
        total_added += added
        total_skipped_preexisting += preserved

        await db["bi5_ingest_log"].insert_one({
            "symbol": symbol, "source": source, "timeframe": timeframe,
            "file_key": file_key, "file": fname,
            "rows_added": added, "rows_preserved": preserved,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        })
        files_ingested += 1
        per_file.append({
            "file": fname, "status": "ingested",
            "rows_added": added, "rows_preserved_existing": preserved,
            "rows_below_cutoff": dropped["below_cutoff"],
            "rows_invalid": dropped["invalid"],
        })

    after = await _range_snapshot(symbol, source, timeframe)

    return {
        "symbol": symbol, "timeframe": timeframe, "source": source,
        "mode": "append_only",
        "candles_added": 0,
        "ticks_added": total_added,
        "rows_preserved_existing": total_skipped_preexisting,
        "rows_below_cutoff": total_below_cutoff,
        "gaps_filled": 0,
        "range_before": before,
        "range_after": after,
        "last_timestamp_before": last_ts.isoformat() if last_ts else None,
        "files_scanned": len(candidate_files),
        "files_ingested": files_ingested,
        "per_file": per_file,
        "import_dir": import_dir,
    }


def _parse_bi5_csv(
    path: str, symbol: str, source: str, timeframe: str,
    last_ts: Optional[datetime],
) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Read a BI5-flavoured chunk CSV, dropping rows ≤ last_ts. Returns
    (rows_ready_for_merge, dropped_counters)."""
    rows: List[Dict[str, Any]] = []
    dropped = {"below_cutoff": 0, "invalid": 0}
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return rows, dropped
        header_lower = {h.lower().strip(): h for h in reader.fieldnames}
        ts_col = next((header_lower[c] for c in ("timestamp", "time", "datetime", "date") if c in header_lower), None)
        if ts_col is None:
            return rows, dropped

        def _f(src: dict, *keys):
            for k in keys:
                if k in src and src[k] not in (None, ""):
                    return src[k]
            return None

        for raw in reader:
            try:
                ts_iso = _parse_timestamp(raw[ts_col])
            except (TimestampParseError, KeyError):
                dropped["invalid"] += 1
                continue
            # Drop rows at or before the last stored timestamp (append-only).
            if last_ts is not None:
                ts_dt = datetime.fromisoformat(ts_iso)
                if ts_dt <= last_ts:
                    dropped["below_cutoff"] += 1
                    continue
            try:
                rows.append({
                    "symbol": symbol, "source": source, "timeframe": timeframe,
                    "timestamp": ts_iso,
                    "open":  float(_f(raw, "open", "o", "bid", "price") or 0),
                    "high":  float(_f(raw, "high", "h", "ask", "price") or 0),
                    "low":   float(_f(raw, "low",  "l", "bid", "price") or 0),
                    "close": float(_f(raw, "close", "c", "bid", "price") or 0),
                    "volume": float(_f(raw, "volume", "vol", "v", "size") or 0),
                })
            except (TypeError, ValueError):
                dropped["invalid"] += 1
    return rows, dropped


# ──────────────────────────────────────────────────────────────────────
# Combined health probe — BID↔BI5 alignment
# ──────────────────────────────────────────────────────────────────────

async def validate_bid_bi5_alignment(
    symbol: str, bid_timeframe: str = "1m", bi5_timeframe: str = "1m",
) -> Dict[str, Any]:
    """Health signal — do BID and BI5 share the same temporal window? Never
    blocks writes; surfaced to the UI for the integrity panel."""
    bid = await _range_snapshot(symbol, "bid_1m", bid_timeframe)
    bi5 = await _range_snapshot(symbol, "bi5", bi5_timeframe)
    if not (bid["last"] and bi5["last"]):
        return {
            "symbol": symbol, "aligned": False,
            "bid": bid, "bi5": bi5,
            "reason": "one_or_both_empty",
        }
    bid_last = datetime.fromisoformat(bid["last"])
    bi5_last = datetime.fromisoformat(bi5["last"])
    drift_min = abs((bid_last - bi5_last).total_seconds()) / 60.0
    return {
        "symbol": symbol, "aligned": drift_min <= 60.0,
        "drift_minutes": round(drift_min, 1),
        "bid": bid, "bi5": bi5,
    }
