"""Observer: breakout_quality.

Detects Donchian-style breakouts (close beats highest-close of the
last N bars) and measures the follow-through rate. Score = fraction
of breakouts that stayed above the level `follow_through` bars later.
"""
from __future__ import annotations

from typing import List
from datetime import datetime, timezone

from ..types import MarketSnapshot, ObserverResult


def observe(snaps: List[MarketSnapshot],
             lookback: int = 20,
             follow_through: int = 5) -> ObserverResult:
    if not snaps or len(snaps) < lookback + follow_through + 1:
        return ObserverResult(
            name="breakout_quality", score=0.5,
            evidence={"n": len(snaps or []), "reason": "insufficient_data"},
            ts=datetime.now(timezone.utc).isoformat(),
        )
    closes = [s.close for s in snaps]
    attempts = 0
    successes = 0
    i = lookback
    while i < len(closes) - follow_through:
        window = closes[i - lookback:i]
        hi = max(window)
        lo = min(window)
        # Upward breakout
        if closes[i] > hi:
            attempts += 1
            level = hi
            future = closes[i + 1:i + 1 + follow_through]
            if future and min(future) >= level:
                successes += 1
        # Downward breakout (mirrored)
        elif closes[i] < lo:
            attempts += 1
            level = lo
            future = closes[i + 1:i + 1 + follow_through]
            if future and max(future) <= level:
                successes += 1
        i += 1
    if attempts == 0:
        return ObserverResult(
            name="breakout_quality", score=0.5,
            evidence={"attempts": 0, "reason": "no_breakouts_detected"},
            ts=datetime.now(timezone.utc).isoformat(),
        )
    rate = successes / attempts
    return ObserverResult(
        name="breakout_quality",
        score=round(rate, 4),
        evidence={
            "attempts":  attempts,
            "successes": successes,
            "rate":      round(rate, 4),
            "lookback":  lookback,
            "follow_through": follow_through,
        },
        ts=datetime.now(timezone.utc).isoformat(),
    )
