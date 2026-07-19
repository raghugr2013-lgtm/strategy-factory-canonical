"""CanonicalTimeframeService — the authoritative candle gateway.

Sub-stage 2.ε (Protocol + LocalCTS) + 2.ζ (HTF cache wired in).

The service is the SOLE implementer of `data_access.load_candles()`.
Every consumer that wants historical candles for backtesting, strategy
generation, portfolio analysis, meta-learning, or AI reasoning goes
through CTS. Nothing else reads `market_data` for HTF data.

Distribution-ready:
  * Protocol is stable
  * Local driver is Stage 2 default
  * Future distributed driver (γ+) replaces `LocalCTS` behind the same interface
  * Selection via `CTS_DRIVER=local|distributed`

Traceability invariant (operator directive, 2026-02-19):
  Every returned `CandleWindow` carries `Provenance` — canonical
  source, aggregation path, cache generation timestamp, cache version,
  repair status, data-quality state.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from ..metrics import Metric, get_metrics
from .cache import HtfCache
from .resampler import (
    bucket_key_for,
    is_canonical_tf,
    resample_m1_to,
    _norm_tf,
)
from .types import (
    CACHE_SCHEMA_VERSION,
    Candle,
    CandleWindow,
    DataQualityState,
    Provenance,
    RebuildReport,
)

logger = logging.getLogger(__name__)

CTS_VERSION = "0.1.0"


@runtime_checkable
class CanonicalTimeframeService(Protocol):
    """The one Protocol every consumer imports.

    Consumers MUST NOT reach through this Protocol to storage-specific
    APIs. If a consumer needs a capability not covered here, extend the
    Protocol — do not bypass it.
    """

    async def load_candles(
        self,
        symbol: str,
        timeframe: str,
        *,
        limit: Optional[int] = None,
        use_cache: bool = True,
    ) -> CandleWindow: ...

    async def invalidate(
        self,
        symbol: str,
        timeframe: Optional[str] = None,
        reason: str = "manual",
    ) -> int: ...

    async def rebuild_bucket(
        self,
        symbol: str,
        timeframe: str,
        bucket_key: str,
    ) -> RebuildReport: ...

    async def snapshot(self) -> Dict[str, Any]: ...

    def health_snapshot(self) -> Dict[str, Any]: ...


# ── LocalCTS ──────────────────────────────────────────────────────────

class LocalCTS:
    """Single-node CTS driver. Implements the Protocol above.

    Reads M1 canonical from `market_data` (source="bid_1m"). Resamples
    via the pure `resample_m1_to()`. Caches into `market_data_htf_cache`.
    """

    def __init__(self, db_getter=None) -> None:
        self._db_getter = db_getter
        self._cache = HtfCache(db_getter=db_getter)
        self._last_error: Optional[str] = None
        self._last_run_at: Optional[str] = None
        self._last_duration_ms: Optional[float] = None
        self._success_count = 0
        self._failure_count = 0

    def _db(self):
        if self._db_getter is not None:
            return self._db_getter()
        try:
            from engines.db import get_db
            return get_db()
        except Exception:                                    # pragma: no cover
            return None

    # ── Public API ──

    async def load_candles(
        self,
        symbol: str,
        timeframe: str,
        *,
        limit: Optional[int] = None,
        use_cache: bool = True,
    ) -> CandleWindow:
        """Fetch M1 canonical + optionally resample + optionally cache.

        Returns a `CandleWindow` with full `Provenance` even on empty
        result. Never raises to the caller — errors are recorded in the
        provenance's `data_quality_state` and reason.
        """
        m = get_metrics()
        tf = _norm_tf(timeframe)
        t0_wall = datetime.now(timezone.utc)
        try:
            # ── M1 canonical direct path ──
            if is_canonical_tf(tf):
                candles = await self._load_m1(symbol, limit=limit)
                self._mark_success()
                return CandleWindow(
                    symbol=symbol,
                    timeframe=tf,
                    candles=candles,
                    provenance=self._prov(
                        aggregation_path="m1_native",
                        cache_bucket_key=None,
                        cache_generated_at=None,
                        gap_count=0,
                        data_quality_state=DataQualityState.OK.value if candles else DataQualityState.UNKNOWN.value,
                    ),
                )

            # ── HTF path ──
            # Try cache first (bucketed by month; concat when window spans buckets)
            aggregated: List[Candle] = []
            cache_provenance: Optional[Provenance] = None
            cache_generated_at: Optional[str] = None
            cache_bucket_key_used: Optional[str] = None
            cache_hit = False

            if use_cache and self._cache.enabled():
                # For simplicity in Stage 2: cache is keyed by bucket
                # (yyyy-mm). We attempt a single-bucket lookup for the
                # most recent bucket determined by NOW. Multi-bucket
                # concatenation is a Stage 2.θ enhancement.
                bucket_ts = t0_wall.isoformat()
                doc = await self._cache.get(symbol, tf, bucket_ts)
                if doc:
                    aggregated = [
                        Candle(**c) for c in doc.get("candles", [])
                    ]
                    cache_generated_at = doc.get("generated_at")
                    cache_bucket_key_used = doc.get("_id")
                    cache_hit = True

            if not cache_hit:
                m1 = await self._load_m1(symbol, limit=None)  # need full range for aggregation
                if not m1:
                    self._mark_success()
                    return CandleWindow(
                        symbol=symbol,
                        timeframe=tf,
                        candles=[],
                        provenance=self._prov(
                            aggregation_path=f"m1_resampled_to_{tf}",
                            data_quality_state=DataQualityState.UNKNOWN.value,
                        ),
                    )
                with m.timer(Metric.CTS_AGG_MS, symbol=symbol, timeframe=tf):
                    aggregated, _report = resample_m1_to(m1, tf)
                # Optional cache write
                if use_cache and self._cache.enabled() and aggregated:
                    first_ts = m1[0].timestamp
                    last_ts  = m1[-1].timestamp
                    await self._cache.put(
                        symbol=symbol,
                        timeframe=tf,
                        bucket_ts_iso=last_ts,
                        candles=aggregated,
                        source_range=(first_ts, last_ts),
                        gap_count=0,
                        repair_status="none",
                        data_quality_state=DataQualityState.OK.value,
                    )
                    cache_bucket_key_used = bucket_key_for(symbol, tf, last_ts)

            if limit is not None and limit > 0:
                aggregated = aggregated[-limit:]

            self._mark_success()
            return CandleWindow(
                symbol=symbol,
                timeframe=tf,
                candles=aggregated,
                provenance=self._prov(
                    aggregation_path=f"m1_resampled_to_{tf}" if not cache_hit else f"cache:{tf}",
                    cache_bucket_key=cache_bucket_key_used,
                    cache_generated_at=cache_generated_at,
                    data_quality_state=DataQualityState.OK.value if aggregated else DataQualityState.UNKNOWN.value,
                ),
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("[cts] load_candles crashed for %s/%s", symbol, timeframe)
            self._mark_failure(str(e))
            return CandleWindow(
                symbol=symbol,
                timeframe=tf,
                candles=[],
                provenance=self._prov(
                    aggregation_path="error",
                    data_quality_state=DataQualityState.UNKNOWN.value,
                ),
            )
        finally:
            self._last_run_at = datetime.now(timezone.utc).isoformat()
            self._last_duration_ms = (datetime.now(timezone.utc) - t0_wall).total_seconds() * 1000.0

    async def invalidate(
        self,
        symbol: str,
        timeframe: Optional[str] = None,
        reason: str = "manual",
    ) -> int:
        """Mark buckets stale. Consumers call this on M1 append / repair events."""
        return await self._cache.invalidate(symbol, timeframe, None, reason)

    async def rebuild_bucket(
        self,
        symbol: str,
        timeframe: str,
        bucket_key: str,
    ) -> RebuildReport:
        """Force-rebuild a specific bucket. Admin-triggered."""
        m = get_metrics()
        t0 = datetime.now(timezone.utc)
        try:
            with m.timer(Metric.CTS_REBUILD_MS, symbol=symbol, timeframe=timeframe):
                m1 = await self._load_m1(symbol)
                aggregated, report = resample_m1_to(m1, timeframe)
                if not aggregated:
                    return RebuildReport(
                        symbol=symbol, timeframe=timeframe, bucket_key=bucket_key,
                        ok=False, reason="no_m1_data",
                        input_rows=len(m1), output_rows=0,
                    )
                last_ts = m1[-1].timestamp
                ok = await self._cache.put(
                    symbol=symbol, timeframe=timeframe, bucket_ts_iso=last_ts,
                    candles=aggregated, source_range=(m1[0].timestamp, last_ts),
                )
                dur = (datetime.now(timezone.utc) - t0).total_seconds() * 1000.0
                return RebuildReport(
                    symbol=symbol, timeframe=timeframe, bucket_key=bucket_key,
                    ok=ok, reason="rebuilt" if ok else "cache_write_failed",
                    input_rows=len(m1), output_rows=len(aggregated), duration_ms=dur,
                )
        except Exception as e:  # noqa: BLE001
            return RebuildReport(
                symbol=symbol, timeframe=timeframe, bucket_key=bucket_key,
                ok=False, reason=str(e)[:200],
            )

    async def snapshot(self) -> Dict[str, Any]:
        return {
            "driver": "local",
            "version": CTS_VERSION,
            "cache_enabled": self._cache.enabled(),
            "cache": await self._cache.snapshot(),
            "success_count": self._success_count,
            "failure_count": self._failure_count,
            "last_run_at": self._last_run_at,
            "last_duration_ms": self._last_duration_ms,
            "last_error": self._last_error,
        }

    def health_snapshot(self) -> Dict[str, Any]:
        """`HealthSnapshot`-shaped dict for the Universal Health Contract."""
        # Kept as dict rather than typed to avoid an import cycle with
        # engines.health.contract (which itself may consume CTS metrics in
        # future). The routing endpoint reshapes into a real
        # HealthSnapshot before returning.
        total = self._success_count + self._failure_count
        health = 100
        if total > 0 and self._failure_count > 0:
            health = max(0, 100 - int(round(self._failure_count / total * 100)))
        state = "ok" if health >= 80 else ("degraded" if health >= 40 else "critical")
        action = "none" if state == "ok" else "operator_review"
        return {
            "subsystem": "cts",
            "health_score": health,
            "readiness_score": 100 if self._last_error is None else 70,
            "confidence_score": health,
            "resource_usage": {
                "in_flight": 0,
                "queue_depth": 0,
            },
            "last_successful_run": {
                "at": self._last_run_at,
                "duration_ms": int(self._last_duration_ms or 0) if self._last_duration_ms else None,
            },
            "failure_count": {
                "last_hour": 0,   # windowed counter deferred to Stage 4
                "last_day": 0,
                "since_boot": self._failure_count,
            },
            "recovery_status": {
                "state": state,
                "reason": self._last_error or "",
                "action_required": action,
            },
        }

    # ── Internals ──

    async def _load_m1(self, symbol: str, limit: Optional[int] = None) -> List[Candle]:
        """Read canonical M1 rows from `market_data` (source='bid_1m')."""
        db = self._db()
        if db is None:
            return []
        try:
            cursor = db.market_data.find(
                {"symbol": symbol, "source": "bid_1m", "timeframe": "1m"},
                {"_id": 0, "timestamp": 1, "open": 1, "high": 1, "low": 1,
                 "close": 1, "volume": 1},
            ).sort("timestamp", 1)
            if limit is not None and limit > 0:
                cursor = cursor.limit(int(limit))
            docs = [d async for d in cursor]
        except Exception as e:  # noqa: BLE001
            logger.warning("[cts] _load_m1 failed for %s: %s", symbol, e)
            return []
        out: List[Candle] = []
        for d in docs:
            ts = d.get("timestamp")
            if hasattr(ts, "isoformat"):
                ts = ts.isoformat()
                if not ts.endswith("+00:00") and "+" not in ts and "Z" not in ts:
                    ts = ts + "+00:00"
            out.append(Candle(
                timestamp=str(ts),
                open=float(d.get("open") or 0.0),
                high=float(d.get("high") or 0.0),
                low=float(d.get("low") or 0.0),
                close=float(d.get("close") or 0.0),
                volume=float(d.get("volume") or 0.0),
            ))
        return out

    def _prov(
        self,
        *,
        aggregation_path: str,
        cache_generated_at: Optional[str] = None,
        cache_bucket_key: Optional[str] = None,
        gap_count: int = 0,
        repair_status: str = "none",
        data_quality_state: str = DataQualityState.OK.value,
    ) -> Provenance:
        return Provenance(
            canonical_source="market_data.bid_1m",
            aggregation_path=aggregation_path,
            cache_generated_at=cache_generated_at,
            cache_version=CACHE_SCHEMA_VERSION,
            cache_bucket_key=cache_bucket_key,
            repair_status=repair_status,
            data_quality_state=data_quality_state,
            gap_count=gap_count,
            cts_version=CTS_VERSION,
        )

    def _mark_success(self) -> None:
        self._success_count += 1
        self._last_error = None

    def _mark_failure(self, err: str) -> None:
        self._failure_count += 1
        self._last_error = err[:240]


# ── Factory ──────────────────────────────────────────────────────────

_CTS_SINGLETON: Optional[LocalCTS] = None


def get_cts() -> CanonicalTimeframeService:
    """Singleton CTS accessor. Respects `CTS_DRIVER=local|distributed`."""
    global _CTS_SINGLETON
    if _CTS_SINGLETON is not None:
        return _CTS_SINGLETON
    driver = (os.environ.get("CTS_DRIVER") or "local").strip().lower()
    if driver == "distributed":
        # Reserved for γ+. Falls back to local until then.
        logger.info("[cts] distributed driver requested; not yet implemented — falling back to local")
    _CTS_SINGLETON = LocalCTS()
    return _CTS_SINGLETON


def reset_cts_for_tests() -> None:
    global _CTS_SINGLETON
    _CTS_SINGLETON = None


# ── Health provider registration ──
try:
    from ..health.providers import register_provider
    from ..health.contract import (
        HealthSnapshot, RecoveryState, RecoveryStatus, ActionRequired,
        LastSuccessfulRun, FailureCount, ResourceUsage,
    )

    def _cts_health_provider() -> HealthSnapshot:
        d = get_cts().health_snapshot()
        return HealthSnapshot(
            subsystem="cts",
            health_score=int(d.get("health_score") or 100),
            readiness_score=int(d.get("readiness_score") or 100),
            confidence_score=int(d.get("confidence_score") or 100),
            resource_usage=ResourceUsage(**(d.get("resource_usage") or {})),
            last_successful_run=LastSuccessfulRun(**(d.get("last_successful_run") or {})),
            failure_count=FailureCount(**(d.get("failure_count") or {})),
            recovery_status=RecoveryStatus(
                state=RecoveryState((d.get("recovery_status") or {}).get("state") or "ok"),
                reason=(d.get("recovery_status") or {}).get("reason") or "",
                action_required=ActionRequired(
                    (d.get("recovery_status") or {}).get("action_required") or "none"
                ),
            ),
        )

    register_provider("cts", _cts_health_provider)
except Exception:                                        # pragma: no cover
    logger.debug("[cts] health provider registration deferred (health module not ready)")
