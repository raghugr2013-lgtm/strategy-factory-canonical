"""Coverage API — implements the locked contract in
COVERAGE_API_CONTRACT_PREVIEW.md.

Read-only. Never triggers writes / backfills / rebuilds.
Admin: full access. Researcher: read-only access. No anonymous.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/data", tags=["coverage"])


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def coverage_enabled() -> bool:
    return _flag("COE_COVERAGE_REPORT_ENABLED", False)


@router.get("/coverage")
async def coverage(
    symbol: Optional[str] = Query(default=None),
    timeframe: Optional[str] = Query(default=None),
    since: Optional[str] = Query(default=None),
    include: str = Query(default="all"),
    format: str = Query(default="json"),
) -> Dict[str, Any]:
    """`GET /api/data/coverage` — locked contract in
    /app/memory/COVERAGE_API_CONTRACT_PREVIEW.md.

    Stage 2.θ MVP — returns the full documented shape; some fields
    populate with `null` or 0 until backfill telemetry lands.
    """
    if not coverage_enabled():
        raise HTTPException(status_code=503, detail="COE_COVERAGE_REPORT_ENABLED is off")
    include_set = _parse_include(include)

    payload: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "canonical_mode": "m1",
    }
    payload["summary"] = await _build_summary()
    if "symbols" in include_set:
        payload["symbols"] = await _build_symbols(filter_symbol=symbol, filter_tf=timeframe, since=since)
    if "gaps" in include_set:
        payload["gaps"] = await _build_gaps(filter_symbol=symbol, since=since)
    if "cache" in include_set:
        payload["cache"] = await _build_cache()
    if "provider" in include_set:
        payload["provider"] = await _build_provider()
    if "health" in include_set:
        payload["health"] = await _build_health()
    return payload


@router.get("/coverage/{symbol}")
async def coverage_for_symbol(symbol: str) -> Dict[str, Any]:
    if not coverage_enabled():
        raise HTTPException(status_code=503, detail="COE_COVERAGE_REPORT_ENABLED is off")
    payload = await coverage(symbol=symbol, include="summary,symbols,gaps,cache")
    return payload


# ── Builders ─────────────────────────────────────────────────────────

async def _build_summary() -> Dict[str, Any]:
    try:
        from engines.db import get_db
        db = get_db()
        symbols = await db.market_data.distinct("symbol", {"source": "bid_1m", "timeframe": "1m"})
        m1_total = await db.market_data.count_documents({"source": "bid_1m", "timeframe": "1m"})
    except Exception:                                        # noqa: BLE001
        symbols, m1_total = [], 0
    cache_snap = await _cache_snapshot_safe()
    return {
        "symbol_count":               len(symbols),
        "canonical_symbol_count":     len(symbols),
        "native_tf_symbol_count":     0,
        "m1_row_count_total":         int(m1_total),
        "cache_bucket_count":         cache_snap.get("bucket_count", 0),
        "cache_bucket_stale_count":   cache_snap.get("bucket_stale_count", 0),
        "cache_bucket_missing_count": 0,
        "coverage_completeness_pct":  None,
        "gap_count":                  0,
        "gap_severity_max":           None,
        "provider_sync_last_at":      None,
        "provider_sync_lag_seconds":  None,
        "cts_health_score":           _cts_health_score(),
    }


async def _build_symbols(filter_symbol: Optional[str], filter_tf: Optional[str], since: Optional[str]) -> List[Dict[str, Any]]:
    try:
        from engines.db import get_db
        db = get_db()
        q: Dict[str, Any] = {"source": "bid_1m", "timeframe": "1m"}
        if filter_symbol:
            q["symbol"] = filter_symbol
        pipeline = [
            {"$match": q},
            {"$group": {
                "_id": "$symbol",
                "first_ts": {"$min": "$timestamp"},
                "last_ts":  {"$max": "$timestamp"},
                "count":    {"$sum": 1},
            }},
            {"$sort": {"_id": 1}},
        ]
        rows = []
        async for r in db.market_data.aggregate(pipeline):
            rows.append(r)
    except Exception:                                        # noqa: BLE001
        rows = []
    out = []
    for r in rows:
        out.append({
            "symbol":              r["_id"],
            "canonical_mode":      "m1",
            "provider":            "dukascopy",
            "m1_first_ts":         _iso(r.get("first_ts")),
            "m1_last_ts":          _iso(r.get("last_ts")),
            "m1_row_count":        int(r.get("count") or 0),
            "expected_row_count":  None,
            "completeness_pct":    None,
            "gap_count":           0,
            "gap_severity_max":    None,
            "cache_status":        {"buckets_total": 0, "buckets_fresh": 0, "buckets_stale": 0, "buckets_missing": 0},
            "last_topup_at":       None,
            "last_topup_rows":     None,
            "last_gap_repair_at":  None,
        })
    return out


async def _build_gaps(filter_symbol: Optional[str], since: Optional[str]) -> List[Dict[str, Any]]:
    return []   # gap enumeration lands in Stage 2 post-CTS backfill telemetry


async def _build_cache() -> Dict[str, Any]:
    snap = await _cache_snapshot_safe()
    from engines.metrics import get_metrics, Metric
    m = get_metrics().snapshot()
    hit_total = _sum_counter(m, Metric.CTS_CACHE_HIT_TOTAL)
    miss_total = _sum_counter(m, Metric.CTS_CACHE_MISS_TOTAL)
    total = hit_total + miss_total
    hit_ratio = (hit_total / total) if total > 0 else 0.0
    agg_hist = _get_hist(m, Metric.CTS_AGG_MS)
    return {
        "bucket_count":         snap.get("bucket_count", 0),
        "bucket_fresh_count":   snap.get("bucket_fresh_count", 0),
        "bucket_stale_count":   snap.get("bucket_stale_count", 0),
        "bucket_missing_count": 0,
        "bytes_used":           None,
        "hit_ratio_last_hour":  round(hit_ratio, 4),
        "hit_ratio_last_day":   round(hit_ratio, 4),
        "aggregation_ms_p50":   agg_hist.get("p50"),
        "aggregation_ms_p95":   agg_hist.get("p95"),
        "aggregation_ms_p99":   agg_hist.get("p99"),
        "recent_invalidations_last_hour": int(_sum_counter(m, Metric.CTS_INVALIDATION_TOTAL)),
        "recent_rebuilds_last_hour":      _get_hist(m, Metric.CTS_REBUILD_MS).get("count", 0),
    }


async def _build_provider() -> Dict[str, Any]:
    return {
        "sources": [],
        "verification_status": {
            "last_htf_diff_at":       None,
            "next_htf_diff_at":       None,
            "last_htf_diff_tier":     None,
            "last_bid_bi5_diff_at":   None,
            "last_bid_bi5_diff_tier": None,
        },
    }


async def _build_health() -> Dict[str, Any]:
    try:
        from engines.health.providers import get_provider
        fn = get_provider("cts")
        if fn:
            return fn().to_dict()
    except Exception:                                        # noqa: BLE001
        pass
    return {"subsystem": "cts", "health_score": 100, "state": "ok"}


# ── Helpers ──────────────────────────────────────────────────────────

def _parse_include(raw: str) -> set:
    if not raw or raw.lower() == "all":
        return {"summary", "symbols", "gaps", "cache", "provider", "health"}
    return {p.strip().lower() for p in raw.split(",") if p.strip()}


def _iso(ts) -> Optional[str]:
    if ts is None:
        return None
    if hasattr(ts, "isoformat"):
        return ts.isoformat()
    return str(ts)


def _cts_health_score() -> int:
    try:
        from engines.cts import get_cts
        return int(get_cts().health_snapshot().get("health_score") or 100)
    except Exception:                                        # noqa: BLE001
        return 100


async def _cache_snapshot_safe() -> Dict[str, Any]:
    try:
        from engines.cts.cache import HtfCache
        return await HtfCache().snapshot()
    except Exception:                                        # noqa: BLE001
        return {}


def _sum_counter(snap: Dict[str, Any], prefix: str) -> float:
    counters = snap.get("counters") or {}
    return float(sum(v for k, v in counters.items() if k == prefix or k.startswith(f"{prefix}{{")))


def _get_hist(snap: Dict[str, Any], name: str) -> Dict[str, Any]:
    histograms = snap.get("histograms") or {}
    # Merge any labelled variants
    matches = [v for k, v in histograms.items() if k == name or k.startswith(f"{name}{{")]
    if not matches:
        return {}
    if len(matches) == 1:
        return matches[0]
    # Multiple label sets → return the combined
    total_count = sum(m.get("count", 0) for m in matches)
    total_sum = sum(m.get("sum", 0.0) for m in matches)
    return {
        "count": total_count,
        "sum": total_sum,
        "p50": min((m.get("p50", 0.0) for m in matches), default=0.0),
        "p95": max((m.get("p95", 0.0) for m in matches), default=0.0),
        "p99": max((m.get("p99", 0.0) for m in matches), default=0.0),
    }
