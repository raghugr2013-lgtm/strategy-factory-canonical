"""
CSV → market_data ingester (additive, Phase 1 P1.1).

Accepts the format produced by `market_data_export_*.zip` archives:
    market_data/BID/<SYMBOL>_<TF>.csv

Each CSV has columns:
    timestamp, open, high, low, close, volume

Writes documents into the `market_data` collection with the same shape the
existing `data_engine.dukascopy_downloader` writes:
    {symbol, source="bid_1m", timeframe, timestamp, open, high, low, close, volume}

Notes:
    * Idempotent — existing (symbol, source, timeframe, timestamp) rows are
      skipped via the unique-key check used by the Dukascopy downloader.
    * Optional `since_iso` filter for "last N months" seed ingestion.
    * Optional `only_symbols` filter for selective import.
    * Pure ingestion — no schema mutation, no index changes.
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from engines.db import get_db

logger = logging.getLogger(__name__)

# Filename pattern: <SYMBOL>_<TF>.csv where TF ∈ {15m, 30m, 1h, 4h, 1d, 5m, 1m}
_VALID_TFS = {"1m", "5m", "15m", "30m", "1h", "4h", "1d"}


def _parse_filename(name: str) -> Optional[Tuple[str, str]]:
    """Return (symbol, timeframe) or None if name doesn't match."""
    stem = Path(name).stem  # e.g. "EURUSD_1h"
    if "_" not in stem:
        return None
    sym, tf = stem.rsplit("_", 1)
    if tf.lower() not in _VALID_TFS:
        return None
    return sym.upper(), tf.lower()


def _iter_csv_rows(path: Path) -> Iterable[Dict[str, Any]]:
    """Yield raw row dicts from a CSV file."""
    with path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield row


def _normalize_row(row: Dict[str, Any], symbol: str, timeframe: str) -> Optional[Dict[str, Any]]:
    """Normalize one CSV row → market_data document. Returns None on parse error."""
    try:
        ts = row.get("timestamp") or row.get("ts")
        if not ts:
            return None
        # Ensure ISO with timezone
        if "+" not in ts and "Z" not in ts:
            # Naive — assume UTC
            ts = ts + "+00:00"
        return {
            "symbol": symbol,
            "source": "bid_1m",
            "timeframe": timeframe,
            "timestamp": ts,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row.get("volume") or 0.0),
        }
    except (KeyError, ValueError, TypeError):
        return None


def _filter_by_since(rows: Iterable[Dict[str, Any]], since_iso: Optional[str]) -> Iterable[Dict[str, Any]]:
    """Yield only rows with timestamp >= since_iso (string compare on ISO works)."""
    if not since_iso:
        yield from rows
        return
    for r in rows:
        if r["timestamp"] >= since_iso:
            yield r


async def ingest_directory(
    root: str,
    *,
    only_symbols: Optional[List[str]] = None,
    only_timeframes: Optional[List[str]] = None,
    since_iso: Optional[str] = None,
    batch_size: int = 5000,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Ingest every <SYMBOL>_<TF>.csv under `root/market_data/BID/` (or `root/` directly).

    Args:
        root: Directory containing the BID subfolder (e.g. `/tmp/market_data_seed`).
        only_symbols: If set, only ingest these symbols (e.g. ["EURUSD", "XAUUSD"]).
        only_timeframes: If set, only ingest these TFs.
        since_iso: If set, only ingest rows with timestamp >= since_iso.
        batch_size: insert_many batch size.
        dry_run: When True, count only, no writes.

    Returns:
        {
          "files_processed": int,
          "files_skipped": int,
          "per_file": [{file, symbol, timeframe, rows_read, rows_inserted, rows_skipped_existing, rows_skipped_filter}],
          "total_inserted": int,
        }
    """
    root_p = Path(root)
    bid_dir = root_p / "market_data" / "BID"
    if not bid_dir.exists():
        bid_dir = root_p  # fall back: maybe user pointed at the CSV dir directly
    if not bid_dir.exists() or not bid_dir.is_dir():
        return {"error": f"directory not found: {bid_dir}", "files_processed": 0}

    csv_files = sorted(bid_dir.glob("*.csv"))
    db = get_db()

    only_symbols_u = {s.upper() for s in only_symbols} if only_symbols else None
    only_tfs_l = {t.lower() for t in only_timeframes} if only_timeframes else None

    per_file: List[Dict[str, Any]] = []
    files_processed = 0
    files_skipped = 0
    total_inserted = 0

    for csv_file in csv_files:
        parsed = _parse_filename(csv_file.name)
        if not parsed:
            files_skipped += 1
            continue
        sym, tf = parsed
        if only_symbols_u and sym not in only_symbols_u:
            files_skipped += 1
            continue
        if only_tfs_l and tf not in only_tfs_l:
            files_skipped += 1
            continue

        # Pre-load existing timestamps for this (symbol, tf) for dedup
        existing_ts: set = set()
        cursor = db.market_data.find(
            {"symbol": sym, "source": "bid_1m", "timeframe": tf},
            {"_id": 0, "timestamp": 1},
        )
        async for d in cursor:
            existing_ts.add(d["timestamp"])

        rows_read = 0
        rows_inserted = 0
        rows_skipped_existing = 0
        rows_skipped_filter = 0
        batch: List[Dict[str, Any]] = []

        for raw in _iter_csv_rows(csv_file):
            rows_read += 1
            norm = _normalize_row(raw, sym, tf)
            if not norm:
                continue
            if since_iso and norm["timestamp"] < since_iso:
                rows_skipped_filter += 1
                continue
            if norm["timestamp"] in existing_ts:
                rows_skipped_existing += 1
                continue
            batch.append(norm)
            existing_ts.add(norm["timestamp"])  # avoid intra-batch dups
            if len(batch) >= batch_size:
                if not dry_run:
                    res = await db.market_data.insert_many(batch, ordered=False)
                    rows_inserted += len(res.inserted_ids)
                else:
                    rows_inserted += len(batch)
                batch = []

        if batch:
            if not dry_run:
                res = await db.market_data.insert_many(batch, ordered=False)
                rows_inserted += len(res.inserted_ids)
            else:
                rows_inserted += len(batch)

        total_inserted += rows_inserted
        files_processed += 1
        per_file.append({
            "file": csv_file.name,
            "symbol": sym,
            "timeframe": tf,
            "rows_read": rows_read,
            "rows_inserted": rows_inserted,
            "rows_skipped_existing": rows_skipped_existing,
            "rows_skipped_filter": rows_skipped_filter,
        })
        logger.info(
            "[csv_ingester] %s/%s: read=%d inserted=%d skip_exist=%d skip_filter=%d",
            sym, tf, rows_read, rows_inserted, rows_skipped_existing, rows_skipped_filter,
        )

    # Ensure the existing compound index (same one Dukascopy downloader writes)
    if not dry_run and total_inserted > 0:
        await db.market_data.create_index(
            [("symbol", 1), ("source", 1), ("timeframe", 1), ("timestamp", 1)]
        )

    return {
        "files_processed": files_processed,
        "files_skipped": files_skipped,
        "per_file": per_file,
        "total_inserted": total_inserted,
        "dry_run": dry_run,
        "filter_since_iso": since_iso,
        "filter_symbols": list(only_symbols_u) if only_symbols_u else None,
        "filter_timeframes": list(only_tfs_l) if only_tfs_l else None,
    }
