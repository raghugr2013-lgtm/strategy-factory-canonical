"""Phase 5.2 — Data Maintenance Layer (additive wrapper).

Self-maintaining, incremental, portable market-data management.

This module NEVER modifies:
    • dukascopy_downloader.py     (manual download path)
    • data_manager.py             (CSV parsing / upload path)
    • incremental_updater.py      (Phase 6 append-only incremental logic)
    • gap_analyzer.py             (gap scan / fill)
    • auto_data_maintainer.py     (Phase 6 scheduler)

It only WRAPS and EXTENDS them with:
    • incremental top-up dispatch  (delegates to incremental_updater)
    • hard retention               (NEW — delete rows older than N months)
    • coverage snapshotting        (NEW — `data_coverage` collection)
    • config storage               (NEW — pairs / tfs / retention / frequency)
    • full-maintenance pipeline    (NEW — update → retention → coverage)

Collections:
    • data_maintenance_config   — single-doc global config
    • data_coverage             — per (symbol, source, timeframe) snapshots
    • data_maintenance_runs     — run-summary audit log
    • market_data               — READ-ONLY from here (write path untouched)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db
from config.symbols import SYMBOL_CONFIG

logger = logging.getLogger(__name__)

CONFIG_COLL = "data_maintenance_config"
COVERAGE_COLL = "data_coverage"
RUNS_COLL = "data_maintenance_runs"
MARKET_COLL = "market_data"

CONFIG_KEY = {"_id": "global"}

# ── Defaults (per Phase-5.2 spec) ─────────────────────────────────────
DEFAULT_PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
DEFAULT_TIMEFRAMES = ["1h"]     # legal values: 1m, 5m, 15m, 30m, 1h, 4h, 1d
DEFAULT_BID_RETENTION_MONTHS = 36
DEFAULT_BI5_RETENTION_MONTHS = 6
DEFAULT_FREQUENCY = "manual"    # manual | hourly | daily
ALLOWED_FREQUENCIES = ("manual", "hourly", "daily")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _months_ago(months: int) -> datetime:
    # ~30.44 days/month — good enough for retention purposes (no calendar math).
    return _now() - timedelta(days=int(months) * 30.44)


def _to_dt(ts: Any) -> Optional[datetime]:
    """Coerce a stored timestamp (may be str or datetime) into datetime."""
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    if isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _retention_filter(cutoff: datetime) -> Dict[str, Any]:
    """Timestamps are stored as ISO strings in `market_data` (kept as-is by
    the existing writer). ISO 8601 strings sort lexicographically, so a
    string $lt works correctly — but we also cover the datetime-typed
    case for any future writer."""
    return {"$or": [
        {"timestamp": {"$lt": cutoff}},
        {"timestamp": {"$lt": cutoff.isoformat()}},
    ]}


# ── Config ─────────────────────────────────────────────────────────────
DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": False,
    "pairs": DEFAULT_PAIRS.copy(),
    "timeframes": DEFAULT_TIMEFRAMES.copy(),
    "retention": {
        "bid_months": DEFAULT_BID_RETENTION_MONTHS,
        "bi5_months": DEFAULT_BI5_RETENTION_MONTHS,
    },
    "frequency": DEFAULT_FREQUENCY,
}


async def get_config() -> Dict[str, Any]:
    db = get_db()
    doc = await db[CONFIG_COLL].find_one(CONFIG_KEY, {"_id": 0})
    if not doc:
        return {**DEFAULT_CONFIG}
    # Merge with defaults so new keys appear without migration.
    merged = {**DEFAULT_CONFIG, **doc}
    merged["retention"] = {**DEFAULT_CONFIG["retention"], **(doc.get("retention") or {})}
    return merged


async def save_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    current = await get_config()
    merged: Dict[str, Any] = {**current}
    if "pairs" in payload and isinstance(payload["pairs"], list):
        merged["pairs"] = [str(p).upper() for p in payload["pairs"] if p]
    if "timeframes" in payload and isinstance(payload["timeframes"], list):
        merged["timeframes"] = [str(t) for t in payload["timeframes"] if t]
    if "retention" in payload and isinstance(payload["retention"], dict):
        r = merged.get("retention") or {}
        if "bid_months" in payload["retention"]:
            r["bid_months"] = max(1, int(payload["retention"]["bid_months"]))
        if "bi5_months" in payload["retention"]:
            r["bi5_months"] = max(1, int(payload["retention"]["bi5_months"]))
        merged["retention"] = r
    if "frequency" in payload:
        f = str(payload["frequency"]).lower()
        if f in ALLOWED_FREQUENCIES:
            merged["frequency"] = f
    if "enabled" in payload:
        merged["enabled"] = bool(payload["enabled"])
    merged["updated_at"] = _now_iso()
    db = get_db()
    await db[CONFIG_COLL].update_one(
        CONFIG_KEY, {"$set": merged}, upsert=True,
    )
    # Return projection-safe (no _id leakage).
    return {k: v for k, v in merged.items() if k != "_id"}


# ── Retention ──────────────────────────────────────────────────────────
async def delete_old_bid_data(months: int = DEFAULT_BID_RETENTION_MONTHS) -> Dict[str, Any]:
    """Hard-delete `market_data` rows in source='bid_1m' older than N months."""
    cutoff = _months_ago(months)
    db = get_db()
    res = await db[MARKET_COLL].delete_many(
        {"source": "bid_1m", **_retention_filter(cutoff)},
    )
    return {"source": "bid_1m", "months": months,
            "cutoff": cutoff.isoformat(), "deleted": res.deleted_count}


async def delete_old_bi5_data(months: int = DEFAULT_BI5_RETENTION_MONTHS) -> Dict[str, Any]:
    cutoff = _months_ago(months)
    db = get_db()
    res = await db[MARKET_COLL].delete_many(
        {"source": "bi5", **_retention_filter(cutoff)},
    )
    return {"source": "bi5", "months": months,
            "cutoff": cutoff.isoformat(), "deleted": res.deleted_count}


async def enforce_retention(
    *,
    bid_months: Optional[int] = None,
    bi5_months: Optional[int] = None,
) -> Dict[str, Any]:
    cfg = await get_config()
    ret = cfg.get("retention") or {}
    bm = int(bid_months if bid_months is not None else ret.get("bid_months", DEFAULT_BID_RETENTION_MONTHS))
    bi = int(bi5_months if bi5_months is not None else ret.get("bi5_months", DEFAULT_BI5_RETENTION_MONTHS))
    bid = await delete_old_bid_data(bm)
    bi5 = await delete_old_bi5_data(bi)
    return {
        "bid": bid, "bi5": bi5,
        "total_deleted": int(bid.get("deleted", 0) + bi5.get("deleted", 0)),
    }


# ── Coverage snapshotting ──────────────────────────────────────────────
_EXPECTED_INTERVAL_SECONDS = {
    "1m":   60, "5m":  300, "15m":  900, "30m": 1800,
    "1h": 3600, "4h": 14400, "1d":  86400,
}


async def _coverage_for(symbol: str, timeframe: str, source: str) -> Dict[str, Any]:
    """Snapshot coverage for one (symbol, source, tf). NEVER mutates
    `market_data`. Returns a doc ready for upsert into `data_coverage`.

    Phase 22.2: also computes historical-coverage progress fields:
      • target_months          — config retention[bid|bi5]_months
      • actual_months          — span between first_ts and end_of_today
      • backfill_progress_pct  — actual / target × 100, capped at 100
    These are read by the UI to render a backfill progress bar."""
    db = get_db()
    q = {"symbol": symbol, "source": source, "timeframe": timeframe}
    total = await db[MARKET_COLL].count_documents(q)

    # Resolve target months from config (cheap; one find_one).
    target_months = 0
    try:
        cfg_doc = await db[CONFIG_COLL].find_one(CONFIG_KEY, {"_id": 0, "retention": 1})
        retention = (cfg_doc or {}).get("retention") or {}
        if source == "bi5":
            target_months = int(retention.get("bi5_months") or DEFAULT_BI5_RETENTION_MONTHS)
        else:
            target_months = int(retention.get("bid_months") or DEFAULT_BID_RETENTION_MONTHS)
    except Exception:
        target_months = (DEFAULT_BI5_RETENTION_MONTHS
                         if source == "bi5" else DEFAULT_BID_RETENTION_MONTHS)

    if total == 0:
        return {
            **q,
            "start_date": None, "end_date": None,
            "rows": 0, "expected_rows": 0,
            "completeness": 0.0, "has_gaps": False,
            "target_months": target_months,
            "actual_months": 0.0,
            "backfill_progress_pct": 0.0,
            "last_updated": _now_iso(),
        }
    first = await db[MARKET_COLL].find_one(q, sort=[("timestamp", 1)])
    last = await db[MARKET_COLL].find_one(q, sort=[("timestamp", -1)])
    start_ts = _to_dt((first or {}).get("timestamp"))
    end_ts = _to_dt((last or {}).get("timestamp"))
    interval = _EXPECTED_INTERVAL_SECONDS.get(timeframe, 3600)
    expected = 1
    if start_ts and end_ts and interval > 0:
        span = (end_ts - start_ts).total_seconds()
        expected = max(1, int(span // interval) + 1)
    completeness = round(min(1.0, total / expected), 4) if expected else 0.0
    has_gaps = completeness < 0.995

    # Historical-coverage progress: how many months span do we cover?
    actual_months = 0.0
    if start_ts:
        actual_days = (_now() - start_ts).total_seconds() / 86400.0
        actual_months = round(actual_days / 30.44, 2)
    backfill_progress_pct = (
        round(min(100.0, (actual_months / target_months) * 100.0), 1)
        if target_months > 0 else 0.0
    )

    return {
        **q,
        "start_date": start_ts.isoformat() if start_ts else None,
        "end_date": end_ts.isoformat() if end_ts else None,
        "rows": int(total),
        "expected_rows": int(expected),
        "completeness": completeness,
        "has_gaps": bool(has_gaps),
        "target_months": target_months,
        "actual_months": actual_months,
        "backfill_progress_pct": backfill_progress_pct,
        "last_updated": _now_iso(),
    }


async def update_coverage(
    symbol: str, timeframe: str, *, source: str = "bid_1m",
) -> Dict[str, Any]:
    doc = await _coverage_for(symbol, timeframe, source)
    db = get_db()
    await db[COVERAGE_COLL].update_one(
        {"symbol": symbol, "source": source, "timeframe": timeframe},
        {"$set": doc}, upsert=True,
    )
    return doc


async def get_coverage_all() -> List[Dict[str, Any]]:
    db = get_db()
    cur = (
        db[COVERAGE_COLL]
        .find({}, {"_id": 0})
        .sort([("symbol", 1), ("source", 1), ("timeframe", 1)])
    )
    return [d async for d in cur]


# ── Incremental update dispatch ────────────────────────────────────────
async def update_bid_data(symbol: str, timeframe: str) -> Dict[str, Any]:
    """Append-only BID top-up — pure delegate to the existing
    `incremental_update_bid`. Return shape preserved."""
    from data_engine.incremental_updater import incremental_update_bid
    return await incremental_update_bid(symbol, timeframe, fix_gaps_after=True)


async def update_bi5_data(symbol: str, timeframe: str = "1m") -> Dict[str, Any]:
    from data_engine.incremental_updater import incremental_update_bi5
    return await incremental_update_bi5(symbol, timeframe)


# ── Full maintenance pipeline ──────────────────────────────────────────
async def run_full_maintenance(
    *,
    pairs: Optional[List[str]] = None,
    timeframes: Optional[List[str]] = None,
    enforce: bool = True,
) -> Dict[str, Any]:
    """Pipeline: incremental update → retention → coverage.
    Returns the run-summary required by Phase 5.2 spec."""
    cfg = await get_config()
    if pairs is None:
        pairs = cfg.get("pairs")
        if not pairs:
            # R3 — route through market_universe_adapter. Byte-identical
            # when flag OFF (the adapter falls back to DEFAULT_PAIRS).
            try:
                from engines.market_universe_adapter import (
                    get_data_maintenance_pairs,
                )
                pairs = get_data_maintenance_pairs()
            except Exception:                               # pragma: no cover
                pairs = DEFAULT_PAIRS
    timeframes = timeframes if timeframes is not None else cfg.get("timeframes") or DEFAULT_TIMEFRAMES

    summary: Dict[str, Any] = {
        "ran_at": _now_iso(),
        "updated_pairs": [],
        "new_records": 0,
        "gaps_detected": [],
        "deleted_old_records": 0,
        "errors": [],
        "coverage_count": 0,
    }

    # Step 1 — incremental update per (pair, tf)
    for p in pairs:
        if p not in SYMBOL_CONFIG:
            summary["errors"].append({"symbol": p, "error": "unknown symbol"})
            continue
        pair_summary = {"symbol": p, "bid_added": 0, "bi5_added": 0}
        for tf in timeframes:
            try:
                r = await update_bid_data(p, tf)
                pair_summary["bid_added"] += int(r.get("candles_added") or 0)
                summary["new_records"] += int(r.get("candles_added") or 0)
                cov = await update_coverage(p, tf, source="bid_1m")
                summary["coverage_count"] += 1
                if cov.get("has_gaps"):
                    summary["gaps_detected"].append({
                        "symbol": p, "timeframe": tf, "source": "bid_1m",
                        "completeness": cov.get("completeness"),
                    })
            except Exception as e:
                logger.exception("maintenance: bid update failed for %s %s", p, tf)
                summary["errors"].append({"symbol": p, "timeframe": tf, "error": str(e)})
        # One BI5 coverage per pair (tick stream; no per-tf fan-out)
        try:
            cov_bi5 = await update_coverage(p, "1m", source="bi5")
            summary["coverage_count"] += 1
            if cov_bi5.get("has_gaps") and cov_bi5.get("rows", 0) > 0:
                summary["gaps_detected"].append({
                    "symbol": p, "timeframe": "1m", "source": "bi5",
                    "completeness": cov_bi5.get("completeness"),
                })
        except Exception as e:
            logger.exception("maintenance: bi5 coverage failed for %s", p)
            summary["errors"].append({"symbol": p, "source": "bi5", "error": str(e)})
        summary["updated_pairs"].append(pair_summary)

    # Step 2 — retention
    if enforce:
        try:
            ret = await enforce_retention()
            summary["deleted_old_records"] = int(ret.get("total_deleted") or 0)
            summary["retention_detail"] = ret
        except Exception as e:
            logger.exception("maintenance: retention failed")
            summary["errors"].append({"step": "retention", "error": str(e)})

    # Step 3 — persist run summary for audit trail
    summary["finished_at"] = _now_iso()
    db = get_db()
    await db[RUNS_COLL].insert_one({**summary})
    return {k: v for k, v in summary.items() if k != "_id"}


async def get_recent_runs(limit: int = 10) -> List[Dict[str, Any]]:
    db = get_db()
    cur = (
        db[RUNS_COLL]
        .find({}, {"_id": 0})
        .sort("ran_at", -1)
        .limit(max(1, min(limit, 50)))
    )
    return [d async for d in cur]


# ── Scheduler status bridge (read-only) ────────────────────────────────
async def get_status_combined() -> Dict[str, Any]:
    """Bridges the existing `auto_data_maintainer.get_status()` output
    into the Phase-5.2 response shape, WITHOUT touching the scheduler."""
    from data_engine.auto_data_maintainer import get_status as legacy_status
    legacy = await legacy_status()
    cfg = await get_config()
    coverage = await get_coverage_all()
    runs = await get_recent_runs(limit=3)

    last_run = None
    next_run = None
    if runs:
        last_run = runs[0].get("ran_at")
    # The legacy scheduler exposes next_runs per track — pick the
    # nearest future one for a simple top-level "next_run".
    nr = legacy.get("next_runs") or {}
    if nr:
        try:
            next_run = min(nr.values())
        except Exception:
            next_run = next(iter(nr.values()))

    return {
        "enabled": bool(legacy.get("enabled") or cfg.get("enabled")),
        "last_run": last_run,
        "next_run": next_run,
        "pairs": cfg.get("pairs") or [],
        "timeframes": cfg.get("timeframes") or [],
        "retention": cfg.get("retention") or DEFAULT_CONFIG["retention"],
        "frequency": cfg.get("frequency") or DEFAULT_FREQUENCY,
        "coverage": coverage,
        "recent_runs": runs,
        # keep legacy fields for any consumer still reading them
        "legacy": {
            "bid_interval_minutes": legacy.get("bid_interval_minutes"),
            "bi5_interval_minutes": legacy.get("bi5_interval_minutes"),
            "statuses": legacy.get("statuses", []),
            "next_runs": nr,
        },
    }


async def toggle_scheduler(enabled: bool) -> Dict[str, Any]:
    """Delegate scheduler start/stop to existing engine; also persist the
    intent into our config doc so frequency/pairs selection is available
    when the scheduler restarts."""
    from data_engine.auto_data_maintainer import start_scheduler, stop_scheduler
    if enabled:
        info = await start_scheduler()
    else:
        info = await stop_scheduler()
    cfg = await save_config({"enabled": bool(enabled)})
    return {"scheduler": info, "config": cfg}
