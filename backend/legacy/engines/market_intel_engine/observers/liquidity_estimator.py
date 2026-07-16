"""Observer: liquidity_estimator.

Proxy from bar-range + session — a wide range in an off-session
implies low liquidity. Score is 1.0 for a normal-range London / NY
session, low for oversized asian-hour candles.
"""
from __future__ import annotations

from typing import List
from statistics import median
from datetime import datetime, timezone

from ..types import MarketSnapshot, ObserverResult


def observe(snaps: List[MarketSnapshot]) -> ObserverResult:
    if not snaps or len(snaps) < 10:
        return ObserverResult(
            name="liquidity_estimator", score=0.5,
            evidence={"n": len(snaps or []), "band": "unknown",
                      "reason": "insufficient_data"},
            ts=datetime.now(timezone.utc).isoformat(),
        )
    ranges = [max(0.0, float(s.range_pct or 0.0)) for s in snaps]
    med_range = median(ranges) if ranges else 0.0
    last_range = ranges[-1] if ranges else 0.0
    ratio = last_range / med_range if med_range > 1e-9 else 1.0
    session = snaps[-1].session or "unknown"
    # Ideal ratio is close to 1.0; wide ratios in low-liquidity sessions
    # are penalised more than in overlap/london/ny.
    session_weight = {"overlap": 1.0, "london": 0.95, "ny": 0.95,
                       "asian":   0.75, "quiet": 0.55, "unknown": 0.7}
    base = session_weight.get(session, 0.7)
    if ratio > 2.0:
        base *= 0.5
    elif ratio > 1.5:
        base *= 0.75
    band = ("high" if base >= 0.85 else "medium" if base >= 0.65 else "low")
    return ObserverResult(
        name="liquidity_estimator",
        score=round(base, 4),
        evidence={
            "session":        session,
            "median_range":   round(med_range, 6),
            "last_range":     round(last_range, 6),
            "range_ratio":    round(ratio, 3),
            "band":           band,
        },
        ts=datetime.now(timezone.utc).isoformat(),
    )
