"""Phase H5 — Broker Health engine.

Computes rolling weighted broker-health scores per Q4 operator
decision: short-term (5m), medium-term (1h), long-term (24h).
Execution decisions primarily consume the short-term score while
medium/long provide historical context.

Health scoring composite (per window):

  score = 0.35 * uptime_pct
        + 0.25 * (1 - reject_rate)
        + 0.15 * (1 - requote_rate)
        + 0.15 * latency_norm          # 1.0 @ ≤50ms → 0.1 @ 1000ms
        + 0.10 * (1 - disconnect_bias) # disconnects/hour normalised

Reads the active broker adapter (paper by default), samples its
BrokerHealth, and persists via the ledger. Every refresh emits an
`outcome_events` row (`broker_health_check`) for full explainability.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from . import config as ecfg
from . import ledger
from .broker import get_active_adapter
from .types import BrokerHealth

logger = logging.getLogger(__name__)


def _norm_latency(latency_ms: float) -> float:
    """1.0 @ ≤50ms → 0.1 @ 1000ms → 0.0 for slower."""
    if latency_ms <= 50.0:
        return 1.0
    if latency_ms >= 1000.0:
        return max(0.0, 0.1 - (latency_ms - 1000.0) / 5000.0)
    # Linear between 50 → 1000 ms mapped to 1.0 → 0.1
    frac = (latency_ms - 50.0) / (1000.0 - 50.0)
    return round(1.0 - 0.9 * frac, 4)


def _norm_disconnect_bias(disconnects_per_hour: float) -> float:
    """0 disconnects/hr → 0.0 bias; 4+/hr → 1.0 bias (fully penalised)."""
    return round(min(1.0, disconnects_per_hour / 4.0), 4)


def _band_for(score: float) -> str:
    if score >= 0.80: return "healthy"
    if score >= 0.50: return "degraded"
    return "unhealthy"


def compute_health_score(
    connected: bool,
    reject_rate: float,
    requote_rate: float,
    latency_ms: float,
    disconnects_per_hour: float,
) -> float:
    """Deterministic composite used across all three windows."""
    if not connected:
        # Uptime dominates; a disconnected broker cannot be >0.35 healthy.
        uptime = 0.0
    else:
        uptime = 1.0
    lat_n = _norm_latency(latency_ms)
    dis_n = _norm_disconnect_bias(disconnects_per_hour)
    score = (
        0.35 * uptime
        + 0.25 * max(0.0, 1.0 - float(reject_rate or 0.0))
        + 0.15 * max(0.0, 1.0 - float(requote_rate or 0.0))
        + 0.15 * lat_n
        + 0.10 * (1.0 - dis_n)
    )
    return round(max(0.0, min(1.0, score)), 4)


async def sample_broker_health(
    account_id: Optional[str] = None,
) -> Optional[BrokerHealth]:
    """Sample the active broker adapter's health and persist a
    rolling snapshot with all three window scores populated. Emits an
    `outcome_events` row. Never raises."""
    if not ecfg.exec_enabled():
        return None
    account_id = account_id or ecfg.default_account_id()
    adapter = get_active_adapter()
    if adapter is None:
        return None
    try:
        raw = await adapter.health()
    except Exception:  # noqa: BLE001
        logger.exception("broker_health.sample: adapter.health() failed")
        return None

    # For H5, all three window scores are computed from the same
    # instantaneous sample. H5.1 will refine by aggregating over
    # rolling ledger reads once we have enough history.
    reject = float(getattr(raw, "reject_rate_5m", 0.0) or 0.0)
    requote = float(getattr(raw, "requote_rate_5m", 0.0) or 0.0)
    latency = float(getattr(raw, "latency_ms", 0.0) or 0.0)
    disc_5m = int(getattr(raw, "disconnect_count_5m", 0) or 0)
    disc_24h = int(getattr(raw, "disconnect_count_24h", 0) or 0)

    s5  = compute_health_score(raw.connected, reject, requote, latency, disc_5m * 12.0)   # 5m → per-hour
    s60 = compute_health_score(raw.connected, reject, requote, latency, disc_5m * 1.0)
    s24 = compute_health_score(raw.connected, reject, requote, latency, disc_24h / 24.0)

    snap = BrokerHealth(
        broker=raw.broker, account_id=account_id,
        ts=datetime.now(timezone.utc).isoformat(),
        connected=bool(raw.connected),
        latency_ms=latency,
        reject_rate_5m=reject,
        reject_rate_60m=reject,
        reject_rate_24h=reject,
        requote_rate_5m=requote,
        requote_rate_60m=requote,
        requote_rate_24h=requote,
        disconnect_count_5m=disc_5m,
        disconnect_count_24h=disc_24h,
        score_5m=s5, score_60m=s60, score_24h=s24,
        band=_band_for(s5),
        notes=list(getattr(raw, "notes", []) or []),
    )
    await ledger.upsert_broker_health(snap)
    await _emit(
        "broker_health_check",
        reason=f"score_5m={s5} band={snap.band}",
        metrics={"broker": snap.broker, "account_id": account_id,
                  "connected": snap.connected,
                  "score_5m": s5, "score_60m": s60, "score_24h": s24,
                  "band": snap.band,
                  "latency_ms": latency,
                  "reject_rate": reject,
                  "requote_rate": requote,
                  "disconnect_count_5m": disc_5m,
                  "disconnect_count_24h": disc_24h},
        evidence={"components": {"latency_norm": _norm_latency(latency),
                                   "disconnect_bias": _norm_disconnect_bias(disc_5m * 12.0)}},
    )
    return snap


async def read_latest_health(account_id: Optional[str] = None
                              ) -> Optional[BrokerHealth]:
    account_id = account_id or ecfg.default_account_id()
    return await ledger.read_latest_broker_health(account_id)


async def is_broker_healthy_for_new_orders(
    account_id: Optional[str] = None,
) -> bool:
    """Q3-safe read helper: returns False when the operator-configured
    floor is breached. **Does NOT block anything itself** — callers
    decide whether to honour the recommendation."""
    account_id = account_id or ecfg.default_account_id()
    latest = await read_latest_health(account_id)
    if latest is None:
        return True   # No data yet → don't gate
    floor = ecfg.risk_thresholds().get("broker_health_min", 0.30)
    return float(latest.score_5m) >= float(floor)


async def _emit(decision_type: str, *,
                 reason: str = "",
                 metrics: Optional[Dict[str, Any]] = None,
                 evidence: Optional[Dict[str, Any]] = None) -> None:
    try:
        from engines.intelligence.explainability import emit_decision
        await emit_decision(decision_type, reason=reason,
                            metrics=metrics or {}, evidence=evidence or {})
    except Exception:  # noqa: BLE001
        pass
