"""Phase F — Execution Quality Estimator (Q4).

Until live cTrader execution history exists, execution quality is
ESTIMATED from six components (spread, latency, slippage, rejects,
broker health, fill quality). Any missing component defaults to a
neutral score of 0.7 (slight negative bias vs assumed-perfect so the
absence of live data doesn't inflate the estimate).

Once live cTrader data lands (Phase G-adjacent), replace
`estimate_execution_quality()` with `measure_execution_quality()` that
reads from an execution feed collection — same return shape.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


DEFAULT_NEUTRAL = 0.7


@dataclass
class ExecutionQuality:
    score:      float                       # 0..1 composite
    components: Dict[str, float]
    method:     str = "estimated_no_live_feed"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _norm_spread(spread_pips: Optional[float]) -> float:
    if spread_pips is None:
        return DEFAULT_NEUTRAL
    # 0.5 pip → 0.95; 1 pip → 0.85; 3 pips → 0.55; 10+ pips → 0.1
    return round(max(0.05, min(1.0, 1.0 - (spread_pips - 0.5) * 0.1)), 3)


def _norm_latency(ms: Optional[float]) -> float:
    if ms is None:
        return DEFAULT_NEUTRAL
    # ≤ 50ms → 1.0; 200ms → 0.7; 1000+ ms → 0.1
    return round(max(0.05, min(1.0, 1.0 - (ms - 50) / 1000.0)), 3)


def _norm_slippage(pips: Optional[float]) -> float:
    if pips is None:
        return DEFAULT_NEUTRAL
    return round(max(0.05, min(1.0, 1.0 - abs(pips) * 0.15)), 3)


def _norm_rejects(rate: Optional[float]) -> float:
    if rate is None:
        return DEFAULT_NEUTRAL
    # 0% → 1.0; 5% → 0.5; 10%+ → 0.0
    return round(max(0.0, min(1.0, 1.0 - rate * 10)), 3)


def _norm_broker(health: Optional[str]) -> float:
    if not health:
        return DEFAULT_NEUTRAL
    return {"healthy": 1.0, "degraded": 0.5, "unhealthy": 0.1}.get(
        str(health).lower(), DEFAULT_NEUTRAL)


def _norm_fill(quality: Optional[str]) -> float:
    if not quality:
        return DEFAULT_NEUTRAL
    return {"perfect": 1.0, "partial": 0.6, "rejected": 0.0,
            "requoted": 0.4}.get(str(quality).lower(), DEFAULT_NEUTRAL)


def estimate_execution_quality(
    *,
    spread_pips:      Optional[float] = None,
    latency_ms:       Optional[float] = None,
    slippage_pips:    Optional[float] = None,
    reject_rate:      Optional[float] = None,
    broker_health:    Optional[str]   = None,
    fill_quality:     Optional[str]   = None,
) -> ExecutionQuality:
    components = {
        "spread":     _norm_spread(spread_pips),
        "latency":    _norm_latency(latency_ms),
        "slippage":   _norm_slippage(slippage_pips),
        "rejects":    _norm_rejects(reject_rate),
        "broker":     _norm_broker(broker_health),
        "fill":       _norm_fill(fill_quality),
    }
    # Weighted average — spread/latency dominate for FX.
    weights = {"spread": 0.30, "latency": 0.20, "slippage": 0.20,
               "rejects": 0.15, "broker": 0.10, "fill": 0.05}
    score = sum(components[k] * weights[k] for k in weights)
    return ExecutionQuality(score=round(score, 4), components=components)
