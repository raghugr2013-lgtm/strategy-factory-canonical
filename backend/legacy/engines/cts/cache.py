"""CTS HTF materialised cache — Sub-stage 2.ζ.

Backing store: Mongo `market_data_htf_cache` collection.
Shard key: `{symbol}|{timeframe}|{yyyy-mm}` (per §10.2 BID review).
Invalidation: event-driven per §10.1 BID review; time-based safety
via `BID_HTF_CACHE_MAX_AGE_DAYS` (default 365).

The cache is a READ CACHE. Cache misses fall through to resample; the
resample result is written back on success. Writes are best-effort:
Mongo failure logs a warning and the caller still receives the
resampled data.

Row shape:
  {
    _id:              "EURUSD|H1|2026-02",     # bucket key
    symbol, timeframe, bucket_start, bucket_end,
    source_range:     { first_ts, last_ts },   # M1 range this cache covers
    generated_at:     "<UTC iso>",
    cache_version:    <int>,
    stale:            <bool>,                  # invalidation flag
    stale_reason:     "<string>" | null,
    repair_status:    "none" | ...,
    data_quality_state: "ok" | ...,
    gap_count:        <int>,
    candles:          [ Candle dicts ]
  }

Never raises to caller. Failures degrade to "cache miss".
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..metrics import Metric, get_metrics
from .resampler import bucket_key_for
from .types import CACHE_SCHEMA_VERSION, Candle, DataQualityState

logger = logging.getLogger(__name__)

CACHE_COLLECTION = "market_data_htf_cache"


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def _max_age_days() -> int:
    try:
        return max(1, int(os.environ.get("BID_HTF_CACHE_MAX_AGE_DAYS") or "365"))
    except (TypeError, ValueError):
        return 365


class HtfCache:
    """Async cache for materialised HTF buckets.

    Every method returns quickly and never raises. Callers treat any
    non-success as a cache miss.
    """

    def __init__(self, db_getter=None) -> None:
        self._db_getter = db_getter  # injectable for tests

    def _db(self):
        """Lazy Mongo handle. Injectable for tests."""
        if self._db_getter is not None:
            return self._db_getter()
        try:
            from engines.db import get_db
            return get_db()
        except Exception:                                    # pragma: no cover
            return None

    def enabled(self) -> bool:
        return _flag("BID_HTF_CACHE_ENABLED", False)

    def event_invalidation_enabled(self) -> bool:
        return _flag("BID_CACHE_EVENT_INVALIDATION", True)

    async def get(self, symbol: str, timeframe: str, bucket_ts_iso: str) -> Optional[Dict[str, Any]]:
        """Read one bucket. Returns None on miss, error, stale, or disabled."""
        m = get_metrics()
        if not self.enabled():
            m.inc(Metric.CTS_CACHE_MISS_TOTAL, reason="disabled")
            return None
        db = self._db()
        if db is None:
            m.inc(Metric.CTS_CACHE_MISS_TOTAL, reason="no_db")
            return None
        key = bucket_key_for(symbol, timeframe, bucket_ts_iso)
        try:
            doc = await db[CACHE_COLLECTION].find_one({"_id": key})
        except Exception as e:  # noqa: BLE001
            logger.warning("[cts.cache] read failed for %s: %s", key, e)
            m.inc(Metric.CTS_CACHE_MISS_TOTAL, reason="read_error")
            return None
        if not doc:
            m.inc(Metric.CTS_CACHE_MISS_TOTAL, reason="not_found")
            return None
        if doc.get("stale"):
            m.inc(Metric.CTS_CACHE_MISS_TOTAL, reason="stale")
            return None
        # Time-based safety fallback (secondary; §10.1 BID review)
        gen_at = doc.get("generated_at")
        if gen_at:
            try:
                gen_dt = datetime.fromisoformat(gen_at.replace("Z", "+00:00"))
                age_days = (datetime.now(timezone.utc) - gen_dt).days
                if age_days > _max_age_days():
                    m.inc(Metric.CTS_CACHE_MISS_TOTAL, reason="too_old")
                    return None
            except Exception:                                # pragma: no cover
                pass
        # Cache version guard
        if int(doc.get("cache_version", 0)) != CACHE_SCHEMA_VERSION:
            m.inc(Metric.CTS_CACHE_MISS_TOTAL, reason="schema_mismatch")
            return None
        m.inc(Metric.CTS_CACHE_HIT_TOTAL, symbol=symbol, timeframe=timeframe)
        return doc

    async def put(
        self,
        symbol: str,
        timeframe: str,
        bucket_ts_iso: str,
        candles: List[Candle],
        source_range: Tuple[str, str],
        gap_count: int = 0,
        repair_status: str = "none",
        data_quality_state: str = DataQualityState.OK.value,
    ) -> bool:
        """Write a bucket. Best-effort; returns True on success."""
        if not self.enabled():
            return False
        db = self._db()
        if db is None:
            return False
        key = bucket_key_for(symbol, timeframe, bucket_ts_iso)
        m = get_metrics()
        try:
            with m.timer(Metric.CTS_CACHE_WRITE_MS, symbol=symbol, timeframe=timeframe):
                await db[CACHE_COLLECTION].update_one(
                    {"_id": key},
                    {"$set": {
                        "symbol":            symbol,
                        "timeframe":         timeframe,
                        "bucket_start":      bucket_ts_iso[:7] + "-01T00:00:00+00:00",
                        "source_range":      {"first_ts": source_range[0], "last_ts": source_range[1]},
                        "generated_at":      datetime.now(timezone.utc).isoformat(),
                        "cache_version":     CACHE_SCHEMA_VERSION,
                        "stale":             False,
                        "stale_reason":      None,
                        "repair_status":     repair_status,
                        "data_quality_state": data_quality_state,
                        "gap_count":         gap_count,
                        "candles":           [c.to_dict() for c in candles],
                    }},
                    upsert=True,
                )
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("[cts.cache] write failed for %s: %s", key, e)
            return False

    async def invalidate(
        self,
        symbol: str,
        timeframe: Optional[str] = None,
        bucket_range: Optional[Tuple[str, str]] = None,
        reason: str = "manual",
    ) -> int:
        """Mark buckets stale. Event-driven per §10.1.

        `bucket_range` = (yyyy-mm_start, yyyy-mm_end) inclusive. If
        None → all buckets for (symbol, timeframe).
        """
        if not self.enabled():
            return 0
        if not self.event_invalidation_enabled():
            return 0
        db = self._db()
        if db is None:
            return 0
        q: Dict[str, Any] = {"symbol": symbol}
        if timeframe:
            q["timeframe"] = timeframe
        if bucket_range:
            q["_id"] = {"$gte": f"{symbol}|{timeframe or ''}|{bucket_range[0]}",
                        "$lte": f"{symbol}|{timeframe or ''}|{bucket_range[1]}"}
        try:
            res = await db[CACHE_COLLECTION].update_many(
                q,
                {"$set": {"stale": True, "stale_reason": reason,
                          "invalidated_at": datetime.now(timezone.utc).isoformat()}},
            )
            n = int(getattr(res, "modified_count", 0) or 0)
            get_metrics().inc(Metric.CTS_INVALIDATION_TOTAL, symbol=symbol, reason=reason)
            return n
        except Exception as e:  # noqa: BLE001
            logger.warning("[cts.cache] invalidate failed: %s", e)
            return 0

    async def snapshot(self) -> Dict[str, Any]:
        """Aggregate diagnostic — count buckets by state."""
        if not self.enabled():
            return {"enabled": False, "bucket_count": 0}
        db = self._db()
        if db is None:
            return {"enabled": True, "bucket_count": 0, "reason": "no_db"}
        try:
            fresh = await db[CACHE_COLLECTION].count_documents({"stale": False})
            stale = await db[CACHE_COLLECTION].count_documents({"stale": True})
            return {
                "enabled": True,
                "bucket_count":       fresh + stale,
                "bucket_fresh_count": fresh,
                "bucket_stale_count": stale,
            }
        except Exception as e:  # noqa: BLE001
            return {"enabled": True, "bucket_count": 0, "error": str(e)[:120]}
