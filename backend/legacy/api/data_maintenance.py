"""Phase 5.2 — Data Maintenance + Backup API.

Namespaced additive routes that live alongside existing `/api/data/*`
endpoints and `/api/auto-maintenance/*` scheduler endpoints. Nothing
here modifies the existing download / upload / backtest path.

Maintenance  →  /api/data/maintenance/*
    GET  /status          state + config + coverage + recent runs
    POST /toggle          start/stop scheduler (persists intent)
    POST /run             one-off full maintenance pipeline
    GET  /config          current config
    POST /config          upsert pairs / timeframes / retention / frequency
    GET  /coverage        snapshot of `data_coverage`
    GET  /recent-runs     audit log

Backup       →  /api/data/backup/*
    GET  /export          single dataset as CSV
    POST /export-bulk     selected matrix as ZIP
    GET  /export-all      everything as ZIP
    POST /import          restore from ZIP (append-only)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel, Field

from data_engine import data_maintenance as dm
from data_engine import data_backup as db_backup

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data/maintenance", tags=["data-maintenance"])
backup_router = APIRouter(prefix="/data/backup", tags=["data-backup"])


# ═══════════════════════════════════════════════════════════════════════
# Maintenance
# ═══════════════════════════════════════════════════════════════════════
class ToggleRequest(BaseModel):
    enabled: bool


class ConfigPayload(BaseModel):
    pairs: Optional[List[str]] = None
    timeframes: Optional[List[str]] = None
    retention: Optional[Dict[str, int]] = None
    frequency: Optional[str] = Field(None, pattern="^(manual|hourly|daily)$")
    enabled: Optional[bool] = None


class RunRequest(BaseModel):
    pairs: Optional[List[str]] = None
    timeframes: Optional[List[str]] = None
    enforce: bool = True
    background: bool = Field(
        True,
        description=(
            "When true (default) the run is dispatched to a FastAPI "
            "BackgroundTask and the endpoint returns 202 immediately. "
            "Set to false to wait synchronously (use for tests with a "
            "short scope only — full runs exceed reverse-proxy timeouts)."
        ),
    )


class BackfillRequest(BaseModel):
    pairs: Optional[List[str]] = None
    timeframes: Optional[List[str]] = None
    months: Optional[int] = Field(None, ge=1, le=120,
        description="Override target months (defaults to config retention.bid_months).")
    source: str = Field("bid_1m", pattern="^(bid_1m|bi5)$")
    background: bool = Field(
        True,
        description="Same semantics as RunRequest.background — async dispatch by default.",
    )


@router.get("/status")
async def status():
    try:
        return await dm.get_status_combined()
    except Exception as e:
        logger.exception("data-maintenance: status failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/toggle")
async def toggle(req: ToggleRequest):
    try:
        res = await dm.toggle_scheduler(req.enabled)
        status_payload = await dm.get_status_combined()
        return {"success": True, "enabled": req.enabled, **res, "status": status_payload}
    except Exception as e:
        logger.exception("data-maintenance: toggle failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run")
async def run_now(background_tasks: BackgroundTasks, req: Optional[RunRequest] = None):
    r = req or RunRequest()
    if r.background:
        # Fire-and-forget — avoids the 120s reverse-proxy timeout on
        # cold full runs (which now also include historical backfill).
        async def _job():
            try:
                await dm.run_full_maintenance(
                    pairs=r.pairs, timeframes=r.timeframes, enforce=r.enforce,
                )
            except Exception:
                logger.exception("data-maintenance: background run crashed")
        background_tasks.add_task(_job)
        return {
            "success": True, "status": "dispatched", "background": True,
            "note": "Job running in background. Poll /api/data/maintenance/status or /coverage to observe progress.",
        }
    try:
        summary = await dm.run_full_maintenance(
            pairs=r.pairs, timeframes=r.timeframes, enforce=r.enforce,
        )
    except Exception as e:
        logger.exception("data-maintenance: run failed")
        raise HTTPException(status_code=500, detail=str(e))
    return {"success": True, "background": False, **summary}


@router.get("/config")
async def get_config():
    return await dm.get_config()


@router.post("/config")
async def post_config(payload: ConfigPayload):
    data = payload.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="no fields to update")
    cfg = await dm.save_config(data)
    return {"success": True, "config": cfg}


@router.get("/coverage")
async def coverage():
    rows = await dm.get_coverage_all()
    return {"count": len(rows), "coverage": rows}


@router.post("/backfill")
async def backfill(background_tasks: BackgroundTasks, req: Optional[BackfillRequest] = None):
    """Manually trigger historical backfill for one or more (pair, tf)
    pairs. Idempotent — symbols already at target coverage are no-ops.

    Default scope:
      • pairs       → config.pairs (or DEFAULT_PAIRS when missing)
      • timeframes  → ["1h"]  (the only timeframe the auto scheduler keeps fresh)
      • months      → config.retention.bid_months (or 36 default)
      • background  → true (returns 202 immediately; poll /coverage)
    """
    from data_engine.incremental_updater import historical_backfill
    r = req or BackfillRequest()
    cfg = await dm.get_config()
    pairs = r.pairs or cfg.get("pairs") or dm.DEFAULT_PAIRS
    timeframes = r.timeframes or ["1h"]
    if r.months is not None:
        months = int(r.months)
    elif r.source == "bi5":
        months = int((cfg.get("retention") or {}).get("bi5_months")
                     or dm.DEFAULT_BI5_RETENTION_MONTHS)
    else:
        months = int((cfg.get("retention") or {}).get("bid_months")
                     or dm.DEFAULT_BID_RETENTION_MONTHS)

    async def _do_backfill() -> Dict[str, Any]:
        results: List[Dict[str, Any]] = []
        total_added = 0
        for p in pairs:
            for tf in timeframes:
                try:
                    bf = await historical_backfill(
                        p, tf, target_months=months, source=r.source,
                    )
                    try:
                        await dm.update_coverage(p, tf, source=r.source)
                    except Exception:
                        pass
                    added = int(bf.get("candles_added") or 0)
                    total_added += added
                    results.append({
                        "symbol": p, "timeframe": tf, "source": r.source,
                        "candles_added": added,
                        "skipped_reason": bf.get("skipped_reason"),
                        "chunks": len(bf.get("chunks") or []),
                        "range_after": bf.get("range_after"),
                        "error": bf.get("download_error"),
                    })
                except Exception as e:
                    logger.exception("backfill failed for %s %s", p, tf)
                    results.append({"symbol": p, "timeframe": tf, "source": r.source,
                                    "error": str(e)[:240]})
        return {
            "success": True, "target_months": months, "source": r.source,
            "total_candles_added": total_added,
            "count": len(results), "results": results,
        }

    if r.background:
        async def _job():
            try:
                await _do_backfill()
            except Exception:
                logger.exception("backfill: background job crashed")
        background_tasks.add_task(_job)
        return {
            "success": True, "status": "dispatched", "background": True,
            "target_months": months, "source": r.source,
            "scope": {"pairs": list(pairs), "timeframes": list(timeframes)},
            "note": "Backfill running in background. Poll /api/data/maintenance/coverage to observe progress (target_months / actual_months / backfill_progress_pct).",
        }
    return await _do_backfill()


@router.get("/recent-runs")
async def recent_runs(limit: int = Query(10, ge=1, le=50)):
    runs = await dm.get_recent_runs(limit=limit)
    return {"count": len(runs), "runs": runs}


# ═══════════════════════════════════════════════════════════════════════
# Backup (export / import)
# ═══════════════════════════════════════════════════════════════════════
class ExportBulkRequest(BaseModel):
    symbols: Optional[List[str]] = None
    timeframes: Optional[List[str]] = None
    sources: Optional[List[str]] = None


@backup_router.get("/export")
async def export_single(
    symbol: str = Query(...),
    timeframe: str = Query("1h"),
    source: str = Query("bid_1m"),
):
    try:
        payload, name = await db_backup.export_dataset(
            symbol, source=source, timeframe=timeframe,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return Response(
        content=payload,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@backup_router.post("/export-bulk")
async def export_bulk(req: ExportBulkRequest):
    try:
        zip_bytes, meta = await db_backup.export_bulk(
            symbols=req.symbols, timeframes=req.timeframes, sources=req.sources,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="market_data_export.zip"',
            "X-Export-Rows": str(meta.get("total_rows", 0)),
        },
    )


@backup_router.get("/export-all")
async def export_all():
    try:
        zip_bytes, meta = await db_backup.export_all()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="market_data_full.zip"',
            "X-Export-Rows": str(meta.get("total_rows", 0)),
        },
    )


@backup_router.post("/import")
async def import_zip(file: UploadFile = File(...)):
    filename = (file.filename or "").lower()
    if not filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="expected a .zip file")
    raw = await file.read()
    try:
        result = await db_backup.import_backup(raw)
    except Exception as e:
        logger.exception("data-backup: import failed")
        raise HTTPException(status_code=500, detail=str(e))
    return {"success": True, **result}


# Convenience alias at the short path some UIs expect.
@router.post("/import-backup")
async def import_backup_alias(file: UploadFile = File(...)):
    return await import_zip(file)   # pragma: no cover — thin alias
