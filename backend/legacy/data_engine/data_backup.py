"""Phase 5.2 — Data Backup / Portability.

Export / import market-data datasets as a portable ZIP archive.

ZIP layout:

    market_data/
        BID/
            EURUSD_H1.csv
        BI5/
            EURUSD_1m.csv
    metadata.json        — { exported_at, counts, pairs, timeframes, ... }

Import is append-only: rows are merged via the existing data_manager
merge path so duplicates are skipped (never overwritten).

Additive only. Does NOT modify download/upload/backtest engines.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from engines.db import get_db

logger = logging.getLogger(__name__)

MARKET_COLL = "market_data"

SOURCE_DIR = {"bid_1m": "BID", "bi5": "BI5"}
CSV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def _safe_name(s: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in str(s))[:40]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _fetch_rows(symbol: str, source: str, timeframe: str) -> List[Dict[str, Any]]:
    db = get_db()
    cur = (
        db[MARKET_COLL]
        .find(
            {"symbol": symbol, "source": source, "timeframe": timeframe},
            {"_id": 0, "symbol": 0, "source": 0, "timeframe": 0},
        )
        .sort("timestamp", 1)
    )
    return [r async for r in cur]


def _rows_to_csv(rows: Iterable[Dict[str, Any]]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLUMNS)
    for r in rows:
        ts = r.get("timestamp")
        if hasattr(ts, "isoformat"):
            ts = ts.isoformat()
        w.writerow([
            ts,
            r.get("open"),
            r.get("high"),
            r.get("low"),
            r.get("close"),
            r.get("volume"),
        ])
    return buf.getvalue().encode("utf-8")


# ── Export ─────────────────────────────────────────────────────────────
async def export_dataset(
    symbol: str, *, source: str = "bid_1m", timeframe: str = "1h",
) -> Tuple[bytes, str]:
    """Return (csv_bytes, filename) for a single dataset."""
    rows = await _fetch_rows(symbol, source, timeframe)
    name = f"{_safe_name(symbol)}_{_safe_name(timeframe)}.csv"
    return _rows_to_csv(rows), name


async def export_bulk(
    *,
    symbols: Optional[List[str]] = None,
    timeframes: Optional[List[str]] = None,
    sources: Optional[List[str]] = None,
) -> Tuple[bytes, Dict[str, Any]]:
    """Return (zip_bytes, metadata) for the requested matrix. Omit any
    list to expand to "all known values from market_data"."""
    db = get_db()
    # Fall back to distinct discovery so we don't need the caller to know
    # what's in the DB.
    if not symbols:
        symbols = sorted(await db[MARKET_COLL].distinct("symbol"))
    if not sources:
        sources = sorted(await db[MARKET_COLL].distinct("source")) or list(SOURCE_DIR)
    if not timeframes:
        timeframes = sorted(await db[MARKET_COLL].distinct("timeframe")) or ["1h"]

    buf = io.BytesIO()
    counts: Dict[str, int] = {}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for sym in symbols:
            for src in sources:
                dir_name = SOURCE_DIR.get(src, src)
                for tf in timeframes:
                    rows = await _fetch_rows(sym, src, tf)
                    if not rows:
                        continue
                    payload = _rows_to_csv(rows)
                    path = f"market_data/{dir_name}/{_safe_name(sym)}_{_safe_name(tf)}.csv"
                    zf.writestr(path, payload)
                    counts[path] = len(rows)
        metadata = {
            "exported_at": _now_iso(),
            "symbols": symbols,
            "sources": sources,
            "timeframes": timeframes,
            "files": counts,
            "total_rows": sum(counts.values()),
            "schema": {"columns": CSV_COLUMNS},
        }
        zf.writestr("metadata.json", json.dumps(metadata, indent=2))
    return buf.getvalue(), metadata


async def export_all() -> Tuple[bytes, Dict[str, Any]]:
    """Full snapshot of every (symbol, source, timeframe) present."""
    return await export_bulk()


# ── Streaming export (memory-bounded; portable across Emergent accounts) ───
COVERAGE_COLL = "data_coverage"


def _csv_value(v: Any) -> str:
    if v is None:
        return ""
    return str(v)


async def export_streaming_to_file(
    out_path: str,
    *,
    symbols: Optional[List[str]] = None,
    timeframes: Optional[List[str]] = None,
    sources: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Stream every (symbol, source, timeframe) dataset to ``out_path`` as
    a ZIP. Memory-bounded: rows are streamed from the Mongo cursor row-by-row
    into the active ZIP entry — no full CSV is held in RAM.

    Layout (compatible with the existing ``import_backup`` workflow):

        market_data/BID/SYMBOL_TF.csv
        market_data/BI5/SYMBOL_TF.csv
        market_data_manifest.json   ← rich manifest (per-dataset coverage)
        metadata.json               ← legacy companion (kept for back-compat)

    Returns the manifest dict.
    """
    db = get_db()

    # Default scope = "everything in market_data" (full migration use-case).
    if not symbols:
        symbols = sorted(await db[MARKET_COLL].distinct("symbol"))
    if not sources:
        sources = sorted(await db[MARKET_COLL].distinct("source")) or list(SOURCE_DIR)
    if not timeframes:
        timeframes = sorted(await db[MARKET_COLL].distinct("timeframe")) or ["1h"]

    # Pre-load coverage rows once — small collection, indexed lookups.
    coverage_map: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    async for doc in db[COVERAGE_COLL].find({}, {"_id": 0}):
        key = (doc.get("symbol"), doc.get("source"), doc.get("timeframe"))
        coverage_map[key] = doc

    datasets: List[Dict[str, Any]] = []
    counts: Dict[str, int] = {}

    header_line = (",".join(CSV_COLUMNS) + "\n").encode("utf-8")

    with zipfile.ZipFile(
        out_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True
    ) as zf:
        for sym in symbols:
            for src in sources:
                dir_name = SOURCE_DIR.get(src, src)
                for tf in timeframes:
                    q = {"symbol": sym, "source": src, "timeframe": tf}
                    pre_count = await db[MARKET_COLL].count_documents(q)
                    if pre_count == 0:
                        continue

                    csv_path = (
                        f"market_data/{dir_name}/"
                        f"{_safe_name(sym)}_{_safe_name(tf)}.csv"
                    )

                    cur = (
                        db[MARKET_COLL]
                        .find(q, {"_id": 0, "symbol": 0, "source": 0, "timeframe": 0})
                        .sort("timestamp", 1)
                    )

                    row_count = 0
                    first_ts: Optional[str] = None
                    last_ts: Optional[str] = None

                    # ZIP entry streamed write — bounded RAM regardless of dataset size.
                    with zf.open(csv_path, "w", force_zip64=True) as zfile:
                        zfile.write(header_line)
                        async for r in cur:
                            ts = r.get("timestamp")
                            if hasattr(ts, "isoformat"):
                                ts = ts.isoformat()
                            ts_str = "" if ts is None else str(ts)
                            if first_ts is None:
                                first_ts = ts_str
                            last_ts = ts_str
                            line = (
                                f"{ts_str},"
                                f"{_csv_value(r.get('open'))},"
                                f"{_csv_value(r.get('high'))},"
                                f"{_csv_value(r.get('low'))},"
                                f"{_csv_value(r.get('close'))},"
                                f"{_csv_value(r.get('volume'))}\n"
                            ).encode("utf-8")
                            zfile.write(line)
                            row_count += 1

                    counts[csv_path] = row_count
                    cov = coverage_map.get((sym, src, tf), {}) or {}
                    datasets.append(
                        {
                            "path": csv_path,
                            "symbol": sym,
                            "source": src,
                            "timeframe": tf,
                            "row_count": row_count,
                            "range_first": first_ts,
                            "range_last": last_ts,
                            "coverage_pct": cov.get("backfill_progress_pct"),
                            "completeness_pct": cov.get("completeness"),
                            "actual_months": cov.get("actual_months"),
                            "target_months": cov.get("target_months"),
                            "has_gaps": cov.get("has_gaps"),
                        }
                    )

        total_rows = sum(counts.values())
        manifest: Dict[str, Any] = {
            "version": "1.0",
            "format": "ai-strategy-factory.market-data-export",
            "exported_at": _now_iso(),
            "schema": {"columns": CSV_COLUMNS},
            "symbols": symbols,
            "sources": sources,
            "timeframes": timeframes,
            "total_datasets": len(datasets),
            "total_rows": total_rows,
            "datasets": datasets,
            "import_endpoint": "/api/data/backup/import",
        }
        zf.writestr("market_data_manifest.json", json.dumps(manifest, indent=2))

        # Legacy companion (existing import-backup ignores this file but
        # other tooling may still reference it).
        legacy = {
            "exported_at": manifest["exported_at"],
            "symbols": symbols,
            "sources": sources,
            "timeframes": timeframes,
            "files": counts,
            "total_rows": total_rows,
            "schema": {"columns": CSV_COLUMNS},
        }
        zf.writestr("metadata.json", json.dumps(legacy, indent=2))

    return manifest


# ── Import ─────────────────────────────────────────────────────────────
def _parse_row(r: List[str]) -> Optional[Dict[str, Any]]:
    try:
        ts_raw = r[0]
        dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        # Store as ISO string to match the existing writer's format — otherwise
        # the (symbol, source, timeframe, timestamp) dedup key would treat
        # datetime and string as different values and create duplicates.
        ts = dt.isoformat()
        return {
            "timestamp": ts,
            "open": float(r[1]) if r[1] != "" else None,
            "high": float(r[2]) if r[2] != "" else None,
            "low": float(r[3]) if r[3] != "" else None,
            "close": float(r[4]) if r[4] != "" else None,
            "volume": float(r[5]) if len(r) > 5 and r[5] != "" else 0.0,
        }
    except Exception:
        return None


def _parse_csv_bytes(raw: bytes) -> List[Dict[str, Any]]:
    txt = raw.decode("utf-8", errors="replace").splitlines()
    reader = csv.reader(txt)
    try:
        header = next(reader)
    except StopIteration:
        return []
    # Tolerate header variations — we only care about column order.
    if not header or not any("time" in h.lower() for h in header):
        # First row might not be header; rewind
        reader = csv.reader(txt)
    out: List[Dict[str, Any]] = []
    for row in reader:
        if not row or len(row) < 5:
            continue
        parsed = _parse_row(row)
        if parsed is not None:
            out.append(parsed)
    return out


def _infer_from_path(path: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Map 'market_data/BID/EURUSD_H1.csv' → (EURUSD, bid_1m, H1)."""
    parts = path.split("/")
    if len(parts) < 3:
        return (None, None, None)
    folder = parts[-2].upper()
    source = None
    for k, v in SOURCE_DIR.items():
        if v.upper() == folder:
            source = k
            break
    if source is None:
        return (None, None, None)
    fname = parts[-1]
    if not fname.lower().endswith(".csv"):
        return (None, None, None)
    stem = fname[:-4]
    if "_" in stem:
        sym, tf = stem.rsplit("_", 1)
    else:
        sym, tf = stem, "1h"
    return (sym.upper(), source, tf)


async def import_backup(zip_bytes: bytes) -> Dict[str, Any]:
    """Append-only backup restore. Uses the same upsert semantics as the
    existing data_manager — duplicates are naturally skipped."""
    from data_engine.data_manager import _merge_rows  # append-only merge

    inserted = 0
    skipped = 0
    files_processed: List[Dict[str, Any]] = []

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            path = info.filename.replace("\\", "/")
            if path.endswith("metadata.json"):
                continue
            if not path.startswith("market_data/"):
                continue
            symbol, source, timeframe = _infer_from_path(path)
            if not symbol or not source or not timeframe:
                files_processed.append({"path": path, "skipped": "invalid_path"})
                continue
            raw = zf.read(info)
            rows = _parse_csv_bytes(raw)
            if not rows:
                files_processed.append({"path": path, "skipped": "no_rows"})
                continue
            try:
                merge = await _merge_rows(
                    rows, symbol=symbol, source=source,
                    timeframe=timeframe, append_only=True,
                )
                ins = int(merge.get("upserted", 0) or 0)
                sk = int(merge.get("matched", 0) or 0)
                inserted += ins
                skipped += sk
                files_processed.append({
                    "path": path, "symbol": symbol, "source": source,
                    "timeframe": timeframe, "inserted": ins, "skipped": sk,
                })
            except Exception as e:
                logger.exception("import_backup: merge failed for %s", path)
                files_processed.append({"path": path, "error": str(e)})

    return {
        "inserted": inserted,
        "skipped_duplicates": skipped,
        "files": files_processed,
        "imported_at": _now_iso(),
    }
