"""Observer: volatility_dynamics.

Compares short-window σ vs long-window σ to detect expansion or
contraction. Higher ratio → recent σ is much larger than baseline
(risk-off regime). Lower ratio → market is compressing (breakout
imminent). Score is normalised so 0.5 is neutral.
"""
from __future__ import annotations

from typing import List
from datetime import datetime, timezone
from statistics import pstdev

from ..types import MarketSnapshot, ObserverResult


def observe(snaps: List[MarketSnapshot],
             short_window: int = 20,
             long_window: int = 100) -> ObserverResult:
    if not snaps or len(snaps) < max(short_window, long_window // 5):
        return ObserverResult(
            name="volatility_dynamics", score=0.5,
            evidence={"n": len(snaps or []), "reason": "insufficient_data"},
            ts=datetime.now(timezone.utc).isoformat(),
        )
    closes = [s.close for s in snaps]
    rets = [
        (closes[i] - closes[i - 1]) / closes[i - 1]
        for i in range(1, len(closes))
        if closes[i - 1]
    ]
    if len(rets) < short_window:
        return ObserverResult(
            name="volatility_dynamics", score=0.5,
            evidence={"n_rets": len(rets), "reason": "insufficient_rets"},
            ts=datetime.now(timezone.utc).isoformat(),
        )
    short = rets[-short_window:]
    long_ = rets[-long_window:] if len(rets) >= long_window else rets
    short_sigma = pstdev(short) if len(short) > 1 else 0.0
    long_sigma  = pstdev(long_) if len(long_) > 1 else 0.0
    ratio = short_sigma / long_sigma if long_sigma > 1e-12 else 1.0
    # Score: benign band 0.8..1.25 → 1.0; expansion above 2.0 → 0.0.
    if 0.8 <= ratio <= 1.25:
        score = 1.0
    elif ratio < 0.8:
        # Compression — often precedes breakouts; slight positive tilt.
        score = min(1.0, 0.75 + (0.8 - ratio))
    else:
        # Expansion — score decays linearly to 0 at ratio=2.5.
        score = max(0.0, 1.0 - (ratio - 1.25) / 1.25)
    return ObserverResult(
        name="volatility_dynamics",
        score=round(score, 4),
        evidence={
            "short_sigma":         round(short_sigma, 8),
            "long_sigma":          round(long_sigma, 8),
            "expansion_ratio":     round(ratio, 4),
            "regime":              _bucket(ratio),
        },
        ts=datetime.now(timezone.utc).isoformat(),
    )


def _bucket(r: float) -> str:
    if r < 0.7:
        return "compression"
    if r < 0.8:
        return "mild_compression"
    if r <= 1.25:
        return "normal"
    if r <= 1.75:
        return "expansion"
    return "severe_expansion"
