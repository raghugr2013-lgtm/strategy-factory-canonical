"""Observer: reversal_strength.

Detects local turning points and scores how deep + fast the reversal
was. Higher score = mean-reversion favoured; lower = one-way markets.
"""
from __future__ import annotations

from typing import List
from datetime import datetime, timezone

from ..types import MarketSnapshot, ObserverResult


def observe(snaps: List[MarketSnapshot],
             swing_window: int = 10) -> ObserverResult:
    if not snaps or len(snaps) < swing_window * 3:
        return ObserverResult(
            name="reversal_strength", score=0.5,
            evidence={"n": len(snaps or []), "reason": "insufficient_data"},
            ts=datetime.now(timezone.utc).isoformat(),
        )
    closes = [s.close for s in snaps]
    depths: List[float] = []
    velocities: List[float] = []
    i = swing_window
    while i < len(closes) - swing_window:
        pre = closes[i - swing_window:i]
        post = closes[i + 1:i + 1 + swing_window]
        pivot = closes[i]
        if not pre or not post:
            i += 1
            continue
        # Local high pivot
        if pivot >= max(pre) and pivot >= max(post):
            depth = (pivot - min(post)) / pivot if pivot else 0.0
            # velocity: how many bars until 50% retrace
            level = pivot - depth * pivot * 0.5
            vel = 1.0
            for j, c in enumerate(post, start=1):
                if c <= level:
                    vel = 1.0 / max(1, j)
                    break
            depths.append(depth)
            velocities.append(vel)
        # Local low pivot
        elif pivot <= min(pre) and pivot <= min(post):
            depth = (max(post) - pivot) / pivot if pivot else 0.0
            level = pivot + depth * pivot * 0.5
            vel = 1.0
            for j, c in enumerate(post, start=1):
                if c >= level:
                    vel = 1.0 / max(1, j)
                    break
            depths.append(depth)
            velocities.append(vel)
        i += swing_window
    if not depths:
        return ObserverResult(
            name="reversal_strength", score=0.5,
            evidence={"n_pivots": 0, "reason": "no_pivots_detected"},
            ts=datetime.now(timezone.utc).isoformat(),
        )
    avg_depth = sum(depths) / len(depths)
    avg_vel   = sum(velocities) / len(velocities)
    # depth × velocity, normalised — a 1% reversal in 2 bars ≈ full score.
    composite = min(1.0, (avg_depth * 100.0) * (avg_vel * 2.0))
    return ObserverResult(
        name="reversal_strength",
        score=round(composite, 4),
        evidence={
            "n_pivots":  len(depths),
            "avg_depth": round(avg_depth, 6),
            "avg_velocity": round(avg_vel, 4),
        },
        ts=datetime.now(timezone.utc).isoformat(),
    )
