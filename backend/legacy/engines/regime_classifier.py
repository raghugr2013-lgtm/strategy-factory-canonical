"""
Phase 16 — Regime Classifier (additive only).

Classifies a window of close prices into ONE of four market regimes:

    * "high_volatility"  — annualised-ish vol exceeds HIGH_VOL_THRESHOLD
    * "low_volatility"   — annualised-ish vol below LOW_VOL_THRESHOLD
    * "trending"         — strong directional move (|drift| dominates range)
    * "ranging"          — neither volatile nor strongly directional

Deterministic, dependency-free. Uses only the last `window` bars (default
100) so the classifier is stable across long histories. Returns the
string `"unknown"` when the series is too short.

Public surface:
    REGIMES, WINDOW_DEFAULT,
    HIGH_VOL_THRESHOLD, LOW_VOL_THRESHOLD, TREND_THRESHOLD,
    classify_regime(prices, window=100) -> str
    describe_regime(prices, window=100) -> dict (vol, trend_ratio, regime)
"""
from __future__ import annotations

import math
from typing import List, Optional

REGIMES: tuple = ("trending", "ranging", "high_volatility", "low_volatility")

WINDOW_DEFAULT = 100
MIN_SAMPLES = 30            # below this the classifier returns "unknown"

# Volatility thresholds are computed on (sum of squared log-returns) so
# they're scale-free across pairs. Calibrated to typical FX H1 data:
#   EURUSD H1 vol (100 bars) ≈ 0.008 → ranging
#   EURUSD H1 during news    ≈ 0.025 → high_volatility
HIGH_VOL_THRESHOLD = 0.020
LOW_VOL_THRESHOLD = 0.005

# Trend ratio = |last - first| / (max - min).  1.0 means the price marched
# straight up or down across the window; ~0 means it oscillated in place.
TREND_THRESHOLD = 0.55


def _returns(prices: List[float]) -> List[float]:
    out: List[float] = []
    prev = None
    for p in prices:
        if prev and prev > 0 and p > 0:
            out.append(math.log(p / prev))
        prev = p
    return out


def _window_vol(prices: List[float]) -> float:
    """Sum of absolute log-returns across the window (robust, no assumption
    of zero-mean)."""
    rets = _returns(prices)
    if not rets:
        return 0.0
    return sum(abs(r) for r in rets)


def _trend_ratio(prices: List[float]) -> float:
    lo = min(prices)
    hi = max(prices)
    span = hi - lo
    if span <= 0:
        return 0.0
    return abs(prices[-1] - prices[0]) / span


def classify_regime(
    prices: Optional[List[float]],
    window: int = WINDOW_DEFAULT,
) -> str:
    """Return ONE of REGIMES, or 'unknown' if the series is too short."""
    if not prices:
        return "unknown"
    window = max(MIN_SAMPLES, int(window or WINDOW_DEFAULT))
    series = list(prices)[-window:]
    if len(series) < MIN_SAMPLES:
        return "unknown"

    vol = _window_vol(series)
    if vol >= HIGH_VOL_THRESHOLD:
        return "high_volatility"
    if vol <= LOW_VOL_THRESHOLD:
        return "low_volatility"

    tr = _trend_ratio(series)
    if tr >= TREND_THRESHOLD:
        return "trending"
    return "ranging"


def describe_regime(
    prices: Optional[List[float]],
    window: int = WINDOW_DEFAULT,
) -> dict:
    """Same as `classify_regime`, but also returns the raw metrics so
    callers (UI / telemetry) can show the decision trail."""
    if not prices:
        return {"regime": "unknown", "vol": None, "trend_ratio": None,
                "window": 0, "samples": 0}
    window = max(MIN_SAMPLES, int(window or WINDOW_DEFAULT))
    series = list(prices)[-window:]
    if len(series) < MIN_SAMPLES:
        return {"regime": "unknown", "vol": None, "trend_ratio": None,
                "window": window, "samples": len(series)}

    vol = _window_vol(series)
    tr = _trend_ratio(series)
    if vol >= HIGH_VOL_THRESHOLD:
        regime = "high_volatility"
    elif vol <= LOW_VOL_THRESHOLD:
        regime = "low_volatility"
    elif tr >= TREND_THRESHOLD:
        regime = "trending"
    else:
        regime = "ranging"
    return {
        "regime": regime,
        "vol": round(vol, 6),
        "trend_ratio": round(tr, 4),
        "window": window,
        "samples": len(series),
    }
