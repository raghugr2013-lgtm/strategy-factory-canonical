from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
import os
import tempfile
from datetime import datetime, timezone

from data_engine.data_manager import (
    parse_and_store_csv,
    parse_and_store_csv_streaming,
    list_server_files,
    get_data_summary,
)
from data_engine.dukascopy_downloader import download_and_store
from data_engine.gap_analyzer import check_gaps, fix_gaps
from data_engine.auto_data_maintainer import (
    start_scheduler,
    stop_scheduler,
    get_status as get_auto_status,
    run_auto_maintenance,
)
from config.symbols import get_market_type, SYMBOL_CONFIG

router = APIRouter()

ALLOWED_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "US100", "BTCUSD", "ETHUSD"]
ALLOWED_TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
ALLOWED_SOURCES = ["bid_1m", "bi5"]


def _allowed_symbols() -> list:
    """R3 — route through market_universe_adapter. Byte-identical when
    flag OFF (the adapter falls back to the ALLOWED_SYMBOLS list)."""
    try:
        from engines.market_universe_adapter import get_allowed_symbols
        return list(get_allowed_symbols())
    except Exception:                                       # pragma: no cover
        return list(ALLOWED_SYMBOLS)

UPLOAD_MAX_BYTES = 500 * 1024 * 1024  # 500 MB
STREAMING_THRESHOLD = 50 * 1024 * 1024  # Files > 50 MB use streaming parser
IMPORT_DIR = os.environ.get("BULK_IMPORT_DIR", "/app/data_imports")

# ─── BI5 single-source realism stream — soft deprecation ────────────
# As of Phase 27.4, the realism evaluator reads ONLY `bi5/1m` and
# resamples to the strategy's timeframe on demand. Ingesting BI5 at any
# other timeframe creates a fragmented bucket that no consumer reads.
# We do NOT hard-reject these calls (operator decision: soft deprecation
# first); we surface a warning in the response and the supervisor log
# so existing tooling continues to function while the convention
# stabilises.
_BI5_CANONICAL_TIMEFRAME = "1m"


def _bi5_deprecation_warning(source: str, timeframe: str) -> str | None:
    """Return a warning string when (source, timeframe) is non-canonical
    for BI5; None otherwise. Pure function — no side effects."""
    if source == "bi5" and timeframe != _BI5_CANONICAL_TIMEFRAME:
        return (
            f"Deprecation: BI5 ingest at timeframe={timeframe} is no longer "
            f"the canonical realism stream. The realism evaluator now reads "
            f"only bi5/1m and resamples to the strategy's timeframe on "
            f"demand. Future versions will reject non-1m BI5 ingests. "
            f"Please migrate to bi5/1m."
        )
    return None


class DownloadRequest(BaseModel):
    symbol: str = "EURUSD"
    timeframe: str = "1h"
    date_from: str
    date_to: str


@router.post("/upload-data")
async def upload_data(
    file: UploadFile = File(...),
    symbol: str = Form(...),
    timeframe: str = Form(...),
    source: str = Form("bid_1m"),
):
    if symbol not in _allowed_symbols():
        raise HTTPException(status_code=400, detail=f"Symbol must be one of: {', '.join(ALLOWED_SYMBOLS)}")
    if timeframe not in ALLOWED_TIMEFRAMES:
        raise HTTPException(status_code=400, detail=f"Timeframe must be one of: {', '.join(ALLOWED_TIMEFRAMES)}")
    if source not in ALLOWED_SOURCES:
        raise HTTPException(status_code=400, detail=f"source must be one of: {', '.join(ALLOWED_SOURCES)}")
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted")

    # Stream file to disk first, then decide parsing strategy
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv", dir="/tmp") as tmp:
            tmp_path = tmp.name
            total_bytes = 0
            while chunk := await file.read(1024 * 1024):  # 1 MB chunks
                total_bytes += len(chunk)
                if total_bytes > UPLOAD_MAX_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large (max {UPLOAD_MAX_BYTES // (1024*1024)} MB). Use Server Import for very large files.",
                    )
                tmp.write(chunk)

        file_size_mb = total_bytes / (1024 * 1024)

        # Use streaming parser for large files, in-memory for small ones
        if total_bytes > STREAMING_THRESHOLD:
            result = await parse_and_store_csv_streaming(tmp_path, symbol, timeframe, source)
        else:
            with open(tmp_path, "rb") as f:
                content = f.read()
            result = await parse_and_store_csv(content, symbol, timeframe, source)
            result["file_size_mb"] = round(file_size_mb, 1)

        # Phase 27.4 — surface BI5 single-source deprecation when applicable.
        warning = _bi5_deprecation_warning(source, timeframe)
        if warning:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "[bi5/deprecation] %s/%s — non-canonical TF on /upload-data",
                symbol, timeframe,
            )
            return {"status": "success", "deprecation_warning": warning, **result}
        return {"status": "success", **result}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.get("/market-data")
async def get_market_data():
    try:
        summary = await get_data_summary()
        return {"datasets": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data-coverage")
async def get_data_coverage(
    symbol: str = Query(..., description="Symbol, e.g. EURUSD"),
    source: str = Query("bid_1m", description="Data source: bid_1m (candles) or bi5 (ticks)"),
    timeframe: Optional[str] = Query(None, description="If omitted, returns all timeframes for the symbol"),
):
    """
    Market-aware data coverage for a symbol.

    Forex (EURUSD, GBPUSD, ...): coverage computed over the Sun 22:00 UTC →
    Fri 22:00 UTC trading window — weekends/closed hours don't penalize coverage.

    Crypto (BTCUSD, ETHUSD): coverage computed over 24/7 — every missing
    minute counts as a real gap.
    """
    if symbol not in SYMBOL_CONFIG:
        # Still serve the computation against the forex default, but flag it.
        pass
    if source not in ALLOWED_SOURCES:
        raise HTTPException(status_code=400, detail=f"source must be one of: {', '.join(ALLOWED_SOURCES)}")
    if timeframe is not None and timeframe not in ALLOWED_TIMEFRAMES:
        raise HTTPException(status_code=400, detail=f"timeframe must be one of: {', '.join(ALLOWED_TIMEFRAMES)}")

    market_type = get_market_type(symbol)
    now_iso = datetime.now(timezone.utc).isoformat()

    timeframes_to_scan = [timeframe] if timeframe else ALLOWED_TIMEFRAMES
    coverages = []
    for tf in timeframes_to_scan:
        result = await check_gaps(symbol, tf, source=source)
        if result.get("error"):
            continue
        # Skip empty datasets unless caller explicitly asked for this timeframe.
        if result.get("total_candles", 0) == 0 and timeframe is None:
            continue
        date_range = result.get("date_range") or {}
        coverages.append({
            "symbol": symbol,
            "source": source,
            "market_type": market_type,
            "timeframe": tf,
            "start": date_range.get("start_full"),
            "end": date_range.get("end_full"),
            "expected_points": result.get("expected_candles", 0),
            "available_points": result.get("total_candles", 0),
            "coverage_pct": result.get("coverage_pct", 0),
            "quality_status": result.get("quality_status"),
            "gaps_count": result.get("gaps_found", 0),
            "missing_points": result.get("missing_candles", 0),
            "gaps": result.get("gaps", []),
            "last_updated": now_iso,
        })

    if not coverages:
        return {
            "symbol": symbol,
            "source": source,
            "market_type": market_type,
            "coverages": [],
            "message": f"No data stored for {symbol}",
        }

    return {
        "symbol": symbol,
        "source": source,
        "market_type": market_type,
        "coverages": coverages if len(coverages) > 1 else None,
        **({} if len(coverages) > 1 else coverages[0]),
    }


@router.get("/server-files")
async def get_server_files():
    """List CSV files available in the server import directory."""
    os.makedirs(IMPORT_DIR, exist_ok=True)
    try:
        files = await list_server_files(IMPORT_DIR)
        return {"files": files, "import_directory": IMPORT_DIR}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ServerImportRequest(BaseModel):
    filename: str
    symbol: str = "EURUSD"
    timeframe: str = "1m"
    source: str = "bid_1m"


@router.post("/import-server-file")
async def import_server_file(req: ServerImportRequest):
    """Import a CSV file from the server's import directory using streaming parser."""
    if req.symbol not in _allowed_symbols():
        return {"success": False, "error": f"Symbol must be one of: {', '.join(ALLOWED_SYMBOLS)}"}
    if req.timeframe not in ALLOWED_TIMEFRAMES:
        return {"success": False, "error": f"Timeframe must be one of: {', '.join(ALLOWED_TIMEFRAMES)}"}
    if req.source not in ALLOWED_SOURCES:
        return {"success": False, "error": f"source must be one of: {', '.join(ALLOWED_SOURCES)}"}

    file_path = os.path.join(IMPORT_DIR, req.filename)
    # Security: prevent path traversal
    if not os.path.abspath(file_path).startswith(os.path.abspath(IMPORT_DIR)):
        return {"success": False, "error": "Invalid filename"}
    if not os.path.isfile(file_path):
        return {"success": False, "error": f"File not found: {req.filename}. Place CSV files in {IMPORT_DIR}/"}
    if not req.filename.lower().endswith(".csv"):
        return {"success": False, "error": "Only CSV files are accepted"}

    try:
        result = await parse_and_store_csv_streaming(file_path, req.symbol, req.timeframe, req.source)
        warning = _bi5_deprecation_warning(req.source, req.timeframe)
        if warning:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "[bi5/deprecation] %s/%s — non-canonical TF on /import-server-file",
                req.symbol, req.timeframe,
            )
            return {"success": True, "deprecation_warning": warning, **result}
        return {"success": True, **result}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/download-data")
async def download_data(req: DownloadRequest):
    if req.symbol not in _allowed_symbols():
        return {"success": False, "error": f"Symbol must be one of: {', '.join(ALLOWED_SYMBOLS)}"}
    if req.timeframe not in ALLOWED_TIMEFRAMES:
        return {"success": False, "error": f"Timeframe must be one of: {', '.join(ALLOWED_TIMEFRAMES)}"}
    try:
        result = await download_and_store(req.symbol, req.timeframe, req.date_from, req.date_to)
        # Check if the downloader returned an error (e.g. Dukascopy fetch failed)
        if result.get("success") is False:
            return result
        return {"success": True, **result}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Data not available or fetch failed: {str(e)}"}



class GapRequest(BaseModel):
    symbol: str
    timeframe: str


@router.post("/check-gaps")
async def check_data_gaps(req: GapRequest):
    if req.symbol not in _allowed_symbols():
        return {"success": False, "error": f"Symbol must be one of: {', '.join(ALLOWED_SYMBOLS)}"}
    if req.timeframe not in ALLOWED_TIMEFRAMES:
        return {"success": False, "error": f"Timeframe must be one of: {', '.join(ALLOWED_TIMEFRAMES)}"}
    try:
        result = await check_gaps(req.symbol, req.timeframe)
        return {"success": True, **result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/fix-gaps")
async def fix_data_gaps(req: GapRequest):
    if req.symbol not in _allowed_symbols():
        return {"success": False, "error": f"Symbol must be one of: {', '.join(ALLOWED_SYMBOLS)}"}
    if req.timeframe not in ALLOWED_TIMEFRAMES:
        return {"success": False, "error": f"Timeframe must be one of: {', '.join(ALLOWED_TIMEFRAMES)}"}
    try:
        result = await fix_gaps(req.symbol, req.timeframe)
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}



# ──────────────────────────────────────────────────────────────────────────
# Auto data maintenance (scheduler)
# ──────────────────────────────────────────────────────────────────────────

class AutoMaintenanceToggle(BaseModel):
    enabled: bool


@router.get("/auto-maintenance/status")
async def auto_maintenance_status():
    try:
        return await get_auto_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auto-maintenance/toggle")
async def auto_maintenance_toggle(req: AutoMaintenanceToggle):
    try:
        if req.enabled:
            info = await start_scheduler()
        else:
            info = await stop_scheduler()
        status = await get_auto_status()
        return {"success": True, **info, "status": status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auto-maintenance/run-now")
async def auto_maintenance_run_now(background_tasks: BackgroundTasks, background: bool = True):
    """Trigger a one-off maintenance pass (works even when scheduler is OFF).

    By default the run is dispatched as a FastAPI BackgroundTask so the
    HTTP call returns immediately — full runs (now including historical
    backfill) can take 30-90 s and would otherwise hit the reverse-proxy
    timeout. Pass `?background=false` to wait synchronously (only safe
    when the run is small / mostly idempotent).
    """
    if background:
        async def _job():
            try:
                await run_auto_maintenance()
            except Exception:
                import logging
                logging.getLogger(__name__).exception("auto-maintenance background run crashed")
        background_tasks.add_task(_job)
        status = await get_auto_status()
        return {
            "success": True, "status": "dispatched", "background": True,
            "scheduler_status": status,
            "note": "Maintenance running in background. Poll /api/auto-maintenance/status or /api/data/maintenance/coverage to observe progress.",
        }
    try:
        summary = await run_auto_maintenance()
        status = await get_auto_status()
        return {"success": True, "background": False, **summary, "scheduler_status": status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────────────────────
# Phase 6 — Append-only incremental updater
# ──────────────────────────────────────────────────────────────────────────

class IncrementalBidRequest(BaseModel):
    symbol: str
    timeframe: str = "1h"
    date_from: Optional[str] = None   # YYYY-MM-DD override (optional)
    date_to: Optional[str] = None
    fix_gaps_after: bool = True


class IncrementalBi5Request(BaseModel):
    symbol: str
    timeframe: str = "1m"
    import_dir: Optional[str] = None  # defaults to /app/data_imports
    max_files: int = 20


@router.post("/incremental/bid")
async def incremental_bid(req: IncrementalBidRequest):
    """Append-only BID top-up: detects last stored ts and fetches only
    `last_ts → now` (or the explicit override window). NEVER overwrites."""
    from data_engine.incremental_updater import incremental_update_bid
    if req.symbol not in _allowed_symbols():
        raise HTTPException(status_code=400, detail=f"Symbol must be one of: {', '.join(ALLOWED_SYMBOLS)}")
    if req.timeframe not in ALLOWED_TIMEFRAMES:
        raise HTTPException(status_code=400, detail=f"Timeframe must be one of: {', '.join(ALLOWED_TIMEFRAMES)}")
    try:
        result = await incremental_update_bid(
            req.symbol, req.timeframe,
            date_from=req.date_from, date_to=req.date_to,
            fix_gaps_after=req.fix_gaps_after,
        )
        return {"success": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/incremental/bi5")
async def incremental_bi5(req: IncrementalBi5Request):
    """Append-only BI5 chunk ingest from disk. Idempotent per file —
    already-ingested chunks are skipped via `bi5_ingest_log`."""
    from data_engine.incremental_updater import incremental_update_bi5
    if req.symbol not in _allowed_symbols():
        raise HTTPException(status_code=400, detail=f"Symbol must be one of: {', '.join(ALLOWED_SYMBOLS)}")
    if req.timeframe not in ALLOWED_TIMEFRAMES:
        raise HTTPException(status_code=400, detail=f"Timeframe must be one of: {', '.join(ALLOWED_TIMEFRAMES)}")
    try:
        result = await incremental_update_bi5(
            req.symbol, req.timeframe,
            import_dir=req.import_dir or IMPORT_DIR,
            max_files=max(1, min(req.max_files, 100)),
        )
        warning = _bi5_deprecation_warning("bi5", req.timeframe)
        if warning:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "[bi5/deprecation] %s/%s — non-canonical TF on /incremental/bi5",
                req.symbol, req.timeframe,
            )
            return {"success": True, "deprecation_warning": warning, **result}
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/incremental/last-timestamp")
async def incremental_last_timestamp(
    symbol: str = Query(...),
    source: str = Query("bid_1m"),
    timeframe: str = Query("1h"),
):
    """Peek at the most recent stored timestamp for (symbol, source, tf)."""
    from data_engine.incremental_updater import get_last_timestamp
    if source not in ALLOWED_SOURCES:
        raise HTTPException(status_code=400, detail=f"source must be one of: {', '.join(ALLOWED_SOURCES)}")
    try:
        ts = await get_last_timestamp(symbol, source, timeframe)
        return {"symbol": symbol, "source": source, "timeframe": timeframe,
                "last_timestamp": ts.isoformat() if ts else None}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/incremental/alignment")
async def incremental_alignment(symbol: str = Query(...)):
    """BID↔BI5 temporal alignment health signal."""
    from data_engine.incremental_updater import validate_bid_bi5_alignment
    try:
        return await validate_bid_bi5_alignment(symbol)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# ═══════════════════════════════════════════════════════════════════════
# Market-Data Export — portable ZIP for migration between Emergent accounts
# ═══════════════════════════════════════════════════════════════════════
class MarketDataExportRequest(BaseModel):
    symbols: Optional[list] = None
    timeframes: Optional[list] = None
    sources: Optional[list] = None


@router.post("/data/export")
async def data_export(req: Optional[MarketDataExportRequest] = None):
    """Export every downloaded historical dataset (BID + BI5) as a single
    ZIP archive that can be re-imported into another Emergent account via
    the existing ``POST /api/data/backup/import`` workflow without any
    manual restructuring.

    The archive includes:
      • ``market_data/BID/SYMBOL_TF.csv`` — BID datasets
      • ``market_data/BI5/SYMBOL_TF.csv`` — BI5 datasets
      • ``market_data_manifest.json``    — symbols, timeframes, row counts,
                                           coverage %, target / actual months,
                                           has_gaps, first/last timestamps,
                                           export timestamp
      • ``metadata.json``                — legacy companion (back-compat)

    The response is streamed from a temp file so memory stays bounded
    regardless of dataset size. The temp file is cleaned up after the
    response is delivered.
    """
    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask
    import logging

    from data_engine import data_backup as db_backup

    r = req or MarketDataExportRequest()

    fd, tmp_path = tempfile.mkstemp(suffix=".zip", prefix="market_data_export_")
    os.close(fd)

    try:
        manifest = await db_backup.export_streaming_to_file(
            tmp_path,
            symbols=r.symbols,
            timeframes=r.timeframes,
            sources=r.sources,
        )
    except Exception as e:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        logging.getLogger(__name__).exception("data_export: build failed")
        raise HTTPException(status_code=500, detail=str(e))

    if manifest.get("total_datasets", 0) == 0:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        raise HTTPException(
            status_code=404,
            detail="No market data found to export. Download datasets first.",
        )

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    fname = f"market_data_export_{ts}.zip"

    def _cleanup(path: str) -> None:
        try:
            os.unlink(path)
        except Exception:
            pass

    return FileResponse(
        tmp_path,
        media_type="application/zip",
        filename=fname,
        background=BackgroundTask(_cleanup, tmp_path),
        headers={
            "X-Export-Total-Rows": str(manifest.get("total_rows", 0)),
            "X-Export-Total-Datasets": str(manifest.get("total_datasets", 0)),
            "X-Export-Filename": fname,
        },
    )
