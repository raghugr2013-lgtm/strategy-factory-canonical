"""
Data health API (additive, Phase 1 P1.1).

Provides per-(symbol, timeframe) coverage report for market_data + tick_data
(when present). Read-only.

Endpoints:
    GET  /api/data/health                  — overall coverage report
    GET  /api/data/health/symbols          — symbols + TFs present
    POST /api/data/ingest-csv              — admin-only manual CSV ingestion trigger
                                             (delegates to data_engine.csv_ingester)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth_utils import get_current_user, require_admin
from engines.db import get_db
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data", tags=["data-health"])


# ───────────────────────────────────────────────────────────────────
# GET /api/data/health
# ───────────────────────────────────────────────────────────────────

@router.get("/health")
async def data_health(_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Return per-(symbol, timeframe) coverage for the market_data collection.

    Output:
        {
          "status": "ok" | "empty" | "partial",
          "market_data": {
            "total_rows": int,
            "coverage": [
              {symbol, timeframe, source, rows, first_ts, last_ts, span_days}, ...
            ],
            "symbols_present": [...],
            "timeframes_present": [...],
          },
          "tick_data": {  # only present if collection exists
            "total_buckets": int,
            "symbols_present": [...],
          },
          "evaluated_at": ISO,
        }
    """
    db = get_db()

    # Per-(symbol, tf, source) aggregation
    pipeline = [
        {"$group": {
            "_id": {"symbol": "$symbol", "timeframe": "$timeframe", "source": "$source"},
            "rows": {"$sum": 1},
            "first_ts": {"$min": "$timestamp"},
            "last_ts": {"$max": "$timestamp"},
        }},
        {"$sort": {"_id.symbol": 1, "_id.timeframe": 1}},
    ]
    coverage_rows: List[Dict[str, Any]] = []
    total_rows = 0
    symbols = set()
    timeframes = set()
    async for r in db.market_data.aggregate(pipeline):
        sym = r["_id"]["symbol"]
        tf = r["_id"]["timeframe"]
        src = r["_id"]["source"]
        first_ts = r["first_ts"]
        last_ts = r["last_ts"]
        rows = int(r["rows"])
        total_rows += rows
        symbols.add(sym)
        timeframes.add(tf)

        span_days: Optional[float] = None
        try:
            d_first = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
            d_last = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
            span_days = round((d_last - d_first).total_seconds() / 86400.0, 2)
        except Exception:
            pass

        coverage_rows.append({
            "symbol": sym, "timeframe": tf, "source": src,
            "rows": rows, "first_ts": first_ts, "last_ts": last_ts,
            "span_days": span_days,
        })

    # Tick data (optional)
    tick_data: Optional[Dict[str, Any]] = None
    try:
        tick_collections = await db.list_collection_names(filter={"name": "tick_data"})
        if tick_collections:
            tc = await db.tick_data.estimated_document_count()
            tick_syms = await db.tick_data.distinct("pair")
            tick_data = {"total_buckets": int(tc), "symbols_present": sorted(tick_syms)}
    except Exception:
        pass

    if total_rows == 0:
        status = "empty"
    elif len(symbols) >= 2 and len(timeframes) >= 2:
        status = "ok"
    else:
        status = "partial"

    return {
        "status": status,
        "market_data": {
            "total_rows": total_rows,
            "coverage": coverage_rows,
            "symbols_present": sorted(symbols),
            "timeframes_present": sorted(timeframes),
        },
        "tick_data": tick_data,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health/symbols")
async def data_health_symbols(_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Lightweight summary — just what symbols/TFs are present."""
    db = get_db()
    symbols = await db.market_data.distinct("symbol")
    timeframes = await db.market_data.distinct("timeframe")
    sources = await db.market_data.distinct("source")
    return {
        "symbols": sorted(symbols),
        "timeframes": sorted(timeframes),
        "sources": sorted(sources),
    }


# ───────────────────────────────────────────────────────────────────
# POST /api/data/ingest-csv  (admin-only)
# ───────────────────────────────────────────────────────────────────

class IngestCsvRequest(BaseModel):
    root_dir: str
    only_symbols: Optional[List[str]] = None
    only_timeframes: Optional[List[str]] = None
    since_iso: Optional[str] = None
    dry_run: bool = False


@router.post("/ingest-csv")
async def ingest_csv(
    req: IngestCsvRequest,
    _admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Admin-only manual CSV ingestion.

    Delegates to `data_engine.csv_ingester.ingest_directory`. Writes an audit row
    on completion.
    """
    try:
        from data_engine.csv_ingester import ingest_directory
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"csv_ingester unavailable: {e}")

    result = await ingest_directory(
        root=req.root_dir,
        only_symbols=req.only_symbols,
        only_timeframes=req.only_timeframes,
        since_iso=req.since_iso,
        dry_run=req.dry_run,
    )

    # Audit row
    try:
        db = get_db()
        await db.audit_log.insert_one({
            "event": "DATA_INGESTED",
            "ts": datetime.now(timezone.utc).isoformat(),
            "details": {
                "root_dir": req.root_dir,
                "only_symbols": req.only_symbols,
                "only_timeframes": req.only_timeframes,
                "since_iso": req.since_iso,
                "files_processed": result.get("files_processed"),
                "total_inserted": result.get("total_inserted"),
                "dry_run": req.dry_run,
            },
            "source": "data_health.ingest_csv",
        })
    except Exception as e:
        logger.warning("[data_health] audit_log write failed: %s", e)

    return result
