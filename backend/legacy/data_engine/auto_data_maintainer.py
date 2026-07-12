"""
Auto data maintainer — APScheduler-based background job that, for every
configured symbol:
  1. Tops up `bid_1m` candle data from Dukascopy for recent history
     (incremental — skips existing timestamps).
  2. Runs a market-aware gap scan; if gaps exist and the symbol is downloadable,
     calls `fix_gaps` to close them.
  3. Reports per-symbol status to Mongo so the UI can render the panel.

Two schedule tracks:
  - BID track  → every 15 minutes
  - BI5 track  → every 60 minutes (tick-data source; no Dukascopy fetcher yet
    for raw .bi5 ticks — this track reports "manual only" status but still
    triggers gap detection against whatever bi5 data the user has uploaded).

The scheduler is a SINGLETON process-wide. It only spins up when the user
toggles it ON via `/api/auto-maintenance/toggle` (enabled=true). A persisted
flag in Mongo (`auto_maintenance_config.enabled`) survives restarts.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from engines.db import get_db
from config.symbols import SYMBOL_CONFIG
from data_engine.dukascopy_downloader import INSTRUMENT_MAP
from data_engine.gap_analyzer import quick_coverage

logger = logging.getLogger(__name__)

STATUS_COLLECTION = "auto_maintenance_status"
CONFIG_COLLECTION = "auto_maintenance_config"

BID_INTERVAL_MINUTES = 15
BI5_INTERVAL_MINUTES = 60

# Default timeframes to keep fresh for each symbol (bid_1m track).
DEFAULT_TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h"]

# Single scheduler instance for the whole process.
_scheduler: Optional[AsyncIOScheduler] = None


# ─────────────────────────────────────────────────────────────────────────────
# DSR-2 — Dynamic Symbol Registry consumption
#
# Replaces the previous ``for symbol in SYMBOL_CONFIG`` hardcoded loop.
# When ``ENABLE_DYNAMIC_MARKET_UNIVERSE=1`` (DSR-3), the helper consults the
# registry to discover which symbols currently have ``eligibility.ingestion_enabled=True``.
# When the flag is OFF, it falls back to ``SYMBOL_CONFIG`` byte-identically —
# zero behavioural drift on the legacy 7 symbols.
#
# Either branch returns a list (deterministic order: registry returns
# rows sorted by (broker_class, symbol) by upstream; legacy dict iteration
# preserves insertion order in Python 3.7+).
#
# The helper is async because the registry query is async; the legacy
# branch is wrapped to keep the signature uniform.
# ─────────────────────────────────────────────────────────────────────────────
async def _ingestion_symbols() -> list[str]:
    """Return the list of symbols the scheduler should ingest THIS cycle.

    Source of truth (when flag ON): ``market_universe_symbols`` collection,
    filtered by ``enabled=True`` AND ``eligibility.ingestion_enabled=True``.

    Source of truth (when flag OFF, legacy): ``config.symbols.SYMBOL_CONFIG``.

    The flag is checked PER-CALL so an operator toggling it via the admin
    surface takes effect on the next tick without restarting the worker.
    """
    try:
        from engines.market_universe_adapter import is_flag_on
    except Exception:                                       # pragma: no cover
        # Defensive: if the adapter is unimportable we fall back hard to
        # the legacy list so the scheduler never starves.
        return list(SYMBOL_CONFIG.keys())

    if not is_flag_on():
        return list(SYMBOL_CONFIG.keys())

    # Flag ON — consult the registry. Never raises into the scheduler.
    try:
        from engines import market_universe as MU
        rows = await MU.list_symbols(enabled=True, limit=2000)
    except Exception as e:
        logger.exception(
            "[auto-maintenance] DSR registry query failed — "
            "falling back to legacy SYMBOL_CONFIG: %s", e,
        )
        return list(SYMBOL_CONFIG.keys())

    out: list[str] = []
    for row in rows:
        elig = (row or {}).get("eligibility") or {}
        if not elig.get("ingestion_enabled", False):
            continue
        sym = (row or {}).get("symbol")
        if sym and sym not in out:
            out.append(sym)

    # Last-resort safety net: never return an empty list — keep the
    # legacy 7 alive even if the registry is empty for any reason.
    if not out:
        logger.warning(
            "[auto-maintenance] DSR returned 0 ingestion-eligible symbols — "
            "falling back to legacy SYMBOL_CONFIG.",
        )
        return list(SYMBOL_CONFIG.keys())

    return out


# ─────────────────────────────────────────────────────────────────────────────
# Persisted state helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _load_config() -> dict:
    db = get_db()
    doc = await db[CONFIG_COLLECTION].find_one({"_id": "global"}, {"_id": 0})
    return doc or {"enabled": False}


async def _save_config(enabled: bool) -> None:
    db = get_db()
    await db[CONFIG_COLLECTION].update_one(
        {"_id": "global"},
        {"$set": {"enabled": enabled, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )


async def _write_status(symbol: str, source: str, payload: dict) -> None:
    db = get_db()
    payload = {**payload, "symbol": symbol, "source": source,
               "updated_at": datetime.now(timezone.utc).isoformat()}
    await db[STATUS_COLLECTION].update_one(
        {"symbol": symbol, "source": source}, {"$set": payload}, upsert=True
    )


async def _read_status_all() -> list[dict]:
    db = get_db()
    cur = db[STATUS_COLLECTION].find({}, {"_id": 0}).sort([("symbol", 1), ("source", 1)])
    return [d async for d in cur]


# ─────────────────────────────────────────────────────────────────────────────
# Job payloads
# ─────────────────────────────────────────────────────────────────────────────

async def _update_bid_symbol(symbol: str) -> dict:
    """Top-up bid_1m for a single symbol and run a gap sweep. Returns a
    per-symbol status dict written to Mongo.

    Phase 6: uses `incremental_update_bid` (last_ts → now) so the job is
    append-only — existing rows are never overwritten, the fetch window
    starts at `last_stored_ts + 1 interval`, and gap fills reuse the
    same dedup-safe downloader.

    Phase 22.1: after each successful tick, also upserts the matching
    row in `data_coverage` so the UI's coverage table reflects what is
    actually stored in `market_data`. Previously the auto scheduler
    only updated `auto_maintenance_status` — the `data_coverage`
    collection (read by the Data Maintenance panel) was only refreshed
    by the manual "Run Now" pipeline, so newly-fetched symbols were
    invisible in the UI until the user clicked it manually.
    """
    from data_engine.incremental_updater import incremental_update_bid, historical_backfill
    from data_engine.data_maintenance import update_coverage, get_config

    status = {"track": "bid_1m", "last_run": datetime.now(timezone.utc).isoformat()}

    # Phase 22.2 — historical backfill (idempotent). Reads `bid_months`
    # from the persisted maintenance config and extends the dataset
    # BACKWARDS to that target. After the dataset is at target this
    # call is a near-zero no-op (one count + one find_one + an early
    # return), so it's safe to invoke every tick.
    bid_months = 36
    try:
        cfg = await get_config()
        bid_months = int((cfg.get("retention") or {}).get("bid_months") or 36)
    except Exception:
        pass

    if symbol in INSTRUMENT_MAP:
        try:
            bf = await historical_backfill(symbol, "1h", target_months=bid_months)
            status["backfill"] = {
                "target_months": bf.get("target_months"),
                "added": bf.get("candles_added", 0),
                "skipped_reason": bf.get("skipped_reason"),
                "chunks": len(bf.get("chunks") or []),
                "range_after": bf.get("range_after"),
                "error": bf.get("download_error"),
            }
            logger.warning(
                "[auto-maintenance] BID %s/1h backfill target=%dm added=%s chunks=%s skip=%s",
                symbol, bid_months, bf.get("candles_added"),
                len(bf.get("chunks") or []), bf.get("skipped_reason"),
            )
        except Exception as e:
            status["backfill"] = {"error": str(e)[:240]}
            logger.exception("[auto-maintenance] BID %s/1h backfill FAILED", symbol)

    if symbol in INSTRUMENT_MAP:
        try:
            result = await incremental_update_bid(symbol, "1h", fix_gaps_after=True)
            status["candles_added"] = result.get("candles_added", 0)
            status["candles_skipped"] = result.get("candles_skipped", 0)
            status["gaps_filled"] = result.get("gaps_filled", 0)
            status["window_mode"] = result.get("window_mode")
            status["last_timestamp_before"] = result.get("last_timestamp_before")
            status["range_after"] = result.get("range_after")
            if result.get("download_error"):
                status["download_error"] = result["download_error"]
            logger.warning(
                "[auto-maintenance] BID %s/1h → range_count=%s inserted=%s skipped=%s gaps_filled=%s mode=%s",
                symbol, result.get("range_after", {}).get("count"),
                result.get("candles_added"), result.get("candles_skipped"),
                result.get("gaps_filled"), result.get("window_mode"),
            )
        except Exception as e:
            status["download_error"] = str(e)
            logger.exception("[auto-maintenance] BID %s/1h FAILED", symbol)

    # Legacy gap/coverage summary (kept for UI back-compat).
    try:
        cov = await quick_coverage(symbol, "1h", source="bid_1m")
        status["coverage_pct"] = cov.get("coverage_pct")
        status["gaps_count"] = cov.get("gaps_count")
        status["quality"] = cov.get("quality_status")
    except Exception as e:
        status["gap_scan_error"] = str(e)

    # Phase 22.1: register coverage in `data_coverage` for every
    # (symbol, source, timeframe) currently in market_data. This is
    # what the UI's Data Maintenance panel reads. Without this step
    # the panel stays stale even though the data is on disk.
    coverage_registered = 0
    coverage_errors = []
    for tf in DEFAULT_TIMEFRAMES:
        try:
            cov_doc = await update_coverage(symbol, tf, source="bid_1m")
            if cov_doc.get("rows", 0) > 0:
                coverage_registered += 1
        except Exception as e:
            coverage_errors.append(f"{tf}: {str(e)[:80]}")
    status["coverage_registered"] = coverage_registered
    if coverage_errors:
        status["coverage_register_errors"] = coverage_errors
    logger.warning(
        "[auto-maintenance] BID %s coverage registered for %d/%d timeframes",
        symbol, coverage_registered, len(DEFAULT_TIMEFRAMES),
    )

    status["state"] = "ok" if not (status.get("download_error") or status.get("gap_scan_error")) else "error"
    await _write_status(symbol, "bid_1m", status)
    return status


async def _update_bi5_symbol(symbol: str) -> dict:
    """bi5 track (Phase 6 + BI5 R1).

    Phase 6 path: append-only chunk-file import. Scans
    ``/app/data_imports/`` for new CSV chunks matching the symbol AND
    the token ``bi5``, then appends without ever overwriting existing
    rows. Per-file idempotency is enforced via ``bi5_ingest_log``.

    **B-1 (BI5 R1, 2026-06-11) — live Dukascopy dispatch.**
    After the CSV chunk pass, dispatch ``run_bi5_ingest`` against the
    Dukascopy BI5 archive with a ``lookback_days=30`` window. Operator-
    confirmed default: 7 days is too narrow after outages; all-time
    scans are too expensive for scheduled execution; 30 days strikes
    the balance between resilience and compute cost.

    The status doc now carries the new ``bi5_ingest_log`` fields so
    the per-symbol health surface (``GET /api/diag/bi5/health``) can
    aggregate them: ``ticks_added · gaps_found · gaps_repaired ·
    status · latency_ms · coverage_percent · health_score_reserved ·
    ingest_version``.
    """
    import time
    from datetime import timedelta
    from data_engine.incremental_updater import incremental_update_bi5, validate_bid_bi5_alignment

    status = {"track": "bi5", "last_run": datetime.now(timezone.utc).isoformat()}
    db = get_db()
    started = time.perf_counter()

    # ── 1) Existing CSV chunk import path (unchanged) ────────────────
    chunk_files_ingested = 0
    chunk_ticks_added = 0
    try:
        result = await incremental_update_bi5(symbol, "1m")
        chunk_ticks_added = int(result.get("ticks_added", 0) or 0)
        chunk_files_ingested = int(result.get("files_ingested", 0) or 0)
        status["ticks_added_from_chunks"] = chunk_ticks_added
        status["files_scanned"] = result.get("files_scanned", 0)
        status["files_ingested"] = chunk_files_ingested
        status["range_after"] = result.get("range_after")
    except Exception as e:
        status["chunk_ingest_error"] = str(e)

    # ── 2) B-1 — Live Dukascopy BI5 ingest (30-day lookback) ────────
    live_ticks_added   = 0
    live_status        = "skipped"
    live_error         = None
    live_gaps_found    = 0
    live_gaps_repaired = 0
    live_files_seen    = 0
    try:
        from data_engine.bi5_ingest_runner import run_bi5_ingest
        end_utc   = datetime.now(timezone.utc)
        start_utc = end_utc - timedelta(days=30)
        report = await run_bi5_ingest(
            symbol,
            start_utc=start_utc,
            end_utc=end_utc,
            use_cache=True,
            db=db,
        )
        live_ticks_added   = int(report.get("ticks_added", 0)         or 0)
        live_gaps_found    = int(report.get("hours_failed", 0)        or 0)
        live_gaps_repaired = int(report.get("hours_succeeded", 0)     or 0)
        live_files_seen    = int(report.get("hours_total", 0)         or 0)
        live_status = (
            "ok"             if live_ticks_added > 0 else
            "fetched-no-new" if live_files_seen > 0 else
            "skipped"
        )
        status["bi5_runner_report"] = {
            "hours_total":     live_files_seen,
            "hours_succeeded": live_gaps_repaired,
            "hours_failed":    live_gaps_found,
            "ticks_added":     live_ticks_added,
            "lookback_days":   30,
        }
    except Exception as e:                                          # pragma: no cover
        # Best-effort — never break the scheduler.
        live_status = "error"
        live_error  = str(e)[:240]
        status["bi5_runner_error"] = live_error
        logger.warning("[auto-maintenance] BI5 runner failed for %s: %s", symbol, e)

    # ── 3) Coverage + alignment (existing, kept) ────────────────────
    coverage_pct: float = 0.0
    try:
        cov = await quick_coverage(symbol, "1m", source="bi5")
        coverage_pct = float(cov.get("coverage_pct") or 0.0)
        status["coverage_pct"] = coverage_pct
        status["gaps_count"]   = cov.get("gaps_count")
        status["quality"]      = cov.get("quality_status")
    except Exception as e:
        status["gap_scan_error"] = str(e)

    try:
        alignment = await validate_bid_bi5_alignment(symbol)
        status["alignment"] = {
            "aligned":         alignment.get("aligned"),
            "drift_minutes":   alignment.get("drift_minutes"),
        }
    except Exception:
        pass

    try:
        from data_engine.data_maintenance import update_coverage
        await update_coverage(symbol, "1m", source="bi5")
    except Exception as e:
        status["coverage_register_errors"] = [f"bi5: {str(e)[:80]}"]

    # ── 4) Resolve final per-cycle status ───────────────────────────
    total_ticks = chunk_ticks_added + live_ticks_added
    if live_status == "error":
        final_status = "error"
    elif total_ticks > 0:
        final_status = "ok"
    elif chunk_files_ingested == 0 and live_files_seen == 0:
        final_status = "manual_only"
    else:
        final_status = "fetched-no-new"
    status["state"]              = final_status        # legacy field
    status["status"]             = final_status        # new alias
    status["ticks_added"]        = total_ticks
    status["latency_ms"]         = int((time.perf_counter() - started) * 1000)
    status["coverage_percent"]   = coverage_pct
    status["gaps_found"]         = live_gaps_found
    status["gaps_repaired"]      = live_gaps_repaired
    status["health_score_reserved"] = None
    status["ingest_version"]     = "r1-v1"

    # ── 5) Extended bi5_ingest_log row (B-1 schema additions) ───────
    # Writes a per-cycle SUMMARY row even when chunk-ingest was empty,
    # so the BI5 Health surface always has fresh telemetry. Per-file
    # detail rows are still written by ``incremental_update_bi5``.
    try:
        await db["bi5_ingest_log"].insert_one({
            "symbol":                symbol,
            "timestamp":             datetime.now(timezone.utc).isoformat(),
            "ingested_at":           datetime.now(timezone.utc).isoformat(),  # legacy alias
            "source":                "scheduler",
            "ticks_added":           total_ticks,
            "rows_added":            total_ticks,           # legacy alias
            "gaps_found":            live_gaps_found,
            "gaps_repaired":         live_gaps_repaired,
            "status":                final_status,
            "latency_ms":            status["latency_ms"],
            "coverage_percent":      coverage_pct,
            "health_score_reserved": None,
            "ingest_version":        "r1-v1",
            "live_lookback_days":    30,
            "live_files_seen":       live_files_seen,
            "live_error":            live_error,
        })
    except Exception as e:
        logger.warning("[auto-maintenance] bi5_ingest_log insert failed for %s: %s", symbol, e)

    await _write_status(symbol, "bi5", status)
    return status


async def run_auto_maintenance() -> dict:
    """Run BOTH tracks for every configured symbol once. Safe to call manually."""
    # DSR-2 — consume the dynamic registry when the flag is ON.
    symbols = await _ingestion_symbols()
    results = []
    for symbol in symbols:
        results.append(await _update_bid_symbol(symbol))
        results.append(await _update_bi5_symbol(symbol))
    return {"ran_at": datetime.now(timezone.utc).isoformat(), "count": len(results)}


async def _bid_track_job() -> None:
    # DSR-2 — registry-driven symbol iteration.
    for symbol in await _ingestion_symbols():
        try:
            await _update_bid_symbol(symbol)
        except Exception:
            logger.exception("bid_1m job failed for %s", symbol)


async def _bi5_track_job() -> None:
    # DSR-2 — registry-driven symbol iteration.
    for symbol in await _ingestion_symbols():
        try:
            await _update_bi5_symbol(symbol)
        except Exception:
            logger.exception("bi5 job failed for %s", symbol)


# ─────────────────────────────────────────────────────────────────────────────
# Scheduler control
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


async def start_scheduler() -> dict:
    sched = _ensure_scheduler()
    # Idempotent: remove existing jobs before re-adding.
    for job_id in ("bid_track", "bi5_track"):
        if sched.get_job(job_id):
            sched.remove_job(job_id)
    sched.add_job(
        _bid_track_job,
        trigger=IntervalTrigger(minutes=BID_INTERVAL_MINUTES),
        id="bid_track",
        next_run_time=datetime.now(timezone.utc),  # kick off immediately
        coalesce=True,
        max_instances=1,
    )
    sched.add_job(
        _bi5_track_job,
        trigger=IntervalTrigger(minutes=BI5_INTERVAL_MINUTES),
        id="bi5_track",
        next_run_time=datetime.now(timezone.utc),
        coalesce=True,
        max_instances=1,
    )
    if not sched.running:
        sched.start()
    await _save_config(True)
    logger.info("Auto-maintenance scheduler STARTED (bid=%dm, bi5=%dm)", BID_INTERVAL_MINUTES, BI5_INTERVAL_MINUTES)
    return {"enabled": True, "bid_interval_minutes": BID_INTERVAL_MINUTES, "bi5_interval_minutes": BI5_INTERVAL_MINUTES}


async def stop_scheduler() -> dict:
    sched = _ensure_scheduler()
    if sched.running:
        sched.shutdown(wait=False)
    # Rebuild a fresh instance for future starts.
    global _scheduler
    _scheduler = None
    await _save_config(False)
    logger.info("Auto-maintenance scheduler STOPPED")
    return {"enabled": False}


async def get_status() -> dict:
    cfg = await _load_config()
    sched = _scheduler
    next_runs = {}
    if sched and sched.running:
        for jid in ("bid_track", "bi5_track"):
            job = sched.get_job(jid)
            if job and job.next_run_time:
                next_runs[jid] = job.next_run_time.astimezone(timezone.utc).isoformat()
    per_symbol = await _read_status_all()
    return {
        "enabled": bool(cfg.get("enabled")),
        "bid_interval_minutes": BID_INTERVAL_MINUTES,
        "bi5_interval_minutes": BI5_INTERVAL_MINUTES,
        "next_runs": next_runs,
        "statuses": per_symbol,
    }


async def restore_if_enabled() -> None:
    """Called on FastAPI startup: re-enable the scheduler if it was ON before restart."""
    cfg = await _load_config()
    if cfg.get("enabled"):
        try:
            await start_scheduler()
        except Exception:
            logger.exception("Failed to restore auto-maintenance scheduler")
