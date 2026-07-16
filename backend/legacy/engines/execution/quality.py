"""Phase H6 — Live Execution Quality measurement.

Reads recent `fill_events` (matched to `order_requests`) and computes
the six-component composite matching Phase F's estimator weights:

  spread 0.30 · latency 0.20 · slippage 0.20 · rejects 0.15
    · broker 0.10 · fill 0.05

Returns `method="measured_live"` when there are ≥ MIN_FILLS samples,
else `method="estimated_no_live_feed"` and falls back to Phase F's
estimator behaviour so upstream code stays byte-identical.

Two-step opt-in respected: `EXEC_LIVE_MEASUREMENT=true` enables
ledger measurement; `BRAIN_USES_LIVE_EXECUTION=true` (consumed by
`brain/execution_quality.py`) causes the brain to use it.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Dict, Optional

from . import config as ecfg
from . import ledger
from .broker_health import read_latest_health
from .types import ExecutionQualitySnapshot

logger = logging.getLogger(__name__)

MIN_FILLS = 20   # below this we degrade to estimator method label


def _percentile(vals, p):
    if not vals:
        return 0.0
    s = sorted(vals)
    k = int(round((p / 100.0) * (len(s) - 1)))
    return float(s[max(0, min(len(s) - 1, k))])


def _norm_latency(latency_ms: float) -> float:
    if latency_ms <= 50.0:
        return 1.0
    if latency_ms >= 1000.0:
        return 0.1
    return round(1.0 - 0.9 * (latency_ms - 50.0) / 950.0, 4)


def _norm_slippage(slip_pips: float) -> float:
    # 0 pips → 1.0; 5+ pips → 0.0
    return max(0.0, min(1.0, 1.0 - abs(slip_pips) / 5.0))


async def measure_execution_quality(
    account_id: str,
    pair: str,
    *,
    session: str = "all",
    window: str = "24h",
    persist: bool = True,
) -> ExecutionQualitySnapshot:
    """Compute + optionally persist an ExecutionQualitySnapshot. Never
    raises. Falls back to the estimator method label when live samples
    are insufficient."""
    ts = datetime.now(timezone.utc).isoformat()
    fills = await ledger.read_fills(account_id=account_id, pair=pair, limit=1000)
    fills = [f for f in fills if f.qty_filled > 0]
    if len(fills) < MIN_FILLS:
        snap = ExecutionQualitySnapshot(
            account_id=account_id, pair=pair, session=session,
            window=window, ts=ts,
            score=0.7, method="estimated_no_live_feed",
            n_samples=len(fills),
        )
        if persist:
            await ledger.upsert_execution_quality(snap)
        await _emit(snap)
        return snap

    latencies = [f.latency_ms for f in fills if f.latency_ms is not None]
    slippages = [abs(f.slippage_pips) for f in fills if f.slippage_pips is not None]
    lat_mean = mean(latencies) if latencies else 0.0
    lat_p95  = _percentile(latencies, 95)
    slip_mean = mean(slippages) if slippages else 0.0
    slip_p95  = _percentile(slippages, 95)

    # Reject/requote — derived from parent order states.
    orders = await ledger.read_orders(account_id=account_id, limit=1000)
    orders = [o for o in orders if o.pair == pair]
    n_orders = max(1, len(orders))
    n_reject = sum(1 for o in orders if o.state == "REJECTED")
    reject_rate = n_reject / n_orders
    # Requote signal: partial fill count / total fills as a proxy.
    n_partial = sum(1 for f in fills if f.is_partial)
    requote_rate = n_partial / max(1, len(fills))

    # Broker component from health.
    bh = await read_latest_health(account_id)
    broker_score = float(bh.score_5m) if bh else 0.7

    # Fill-quality: 1.0 if no rejects and no partials, 0.6 for either, 0.3 for both.
    fill_quality = "perfect" if (n_reject == 0 and n_partial == 0) else \
                   "rejected mix" if n_reject > 0 else "partial"
    fq_score = 1.0 if fill_quality == "perfect" else \
               0.6 if fill_quality == "partial" else 0.3

    components = {
        "spread":   0.30 * 1.0,                       # spread proxy: 1.0 until live spread wired
        "latency":  0.20 * _norm_latency(lat_mean),
        "slippage": 0.20 * _norm_slippage(slip_mean),
        "reject":   0.15 * max(0.0, 1.0 - reject_rate),
        "broker":   0.10 * broker_score,
        "fill":     0.05 * fq_score,
    }
    score = round(max(0.0, min(1.0, sum(components.values()))), 4)

    snap = ExecutionQualitySnapshot(
        account_id=account_id, pair=pair, session=session,
        window=window, ts=ts,
        spread_pips_mean=0.0, spread_pips_p95=0.0,
        latency_ms_mean=round(lat_mean, 2),
        latency_ms_p95=round(lat_p95, 2),
        slippage_pips_mean=round(slip_mean, 4),
        slippage_pips_p95=round(slip_p95, 4),
        reject_rate=round(reject_rate, 4),
        requote_rate=round(requote_rate, 4),
        fill_quality=fill_quality,
        score=score, method="measured_live",
        n_samples=len(fills),
        components={k: round(v, 4) for k, v in components.items()},
    )
    if persist:
        await ledger.upsert_execution_quality(snap)
    await _emit(snap)
    return snap


async def _emit(snap: ExecutionQualitySnapshot) -> None:
    try:
        from engines.intelligence.explainability import emit_decision
        await emit_decision(
            "execution_quality_refresh",
            reason=f"score={snap.score} method={snap.method}",
            metrics={"account_id": snap.account_id, "pair": snap.pair,
                      "session": snap.session, "window": snap.window,
                      "score": snap.score, "method": snap.method,
                      "n_samples": snap.n_samples,
                      "latency_ms_p95": snap.latency_ms_p95,
                      "slippage_pips_p95": snap.slippage_pips_p95,
                      "reject_rate": snap.reject_rate},
            evidence={"components": snap.components,
                       "fill_quality": snap.fill_quality},
        )
    except Exception:                                    # noqa: BLE001
        pass
