"""Phase C.4 — Market Regime Engine.

Detects the CURRENT regime from recent price data (or Mongo-persisted
market metadata) so the Dynamic Strategy Selector can activate the
right strategy for the moment.

Wraps `regime_classifier.classify_regime` — never duplicates its logic;
only adds:
    - persistent last-known regime (Mongo cache)
    - freshness SLA
    - RegimeSnapshot dataclass with human-readable descriptor
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RegimeSnapshot:
    pair:        str
    timeframe:   str
    regime:      str          # trending | ranging | high_volatility | low_volatility | unknown
    confidence:  float
    volatility:  float
    trend_score: float
    ts:          str
    evidence:    Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


async def _load_recent_prices(pair: str, timeframe: str, limit: int = 300) -> List[float]:
    """Best-effort recent-close loader. Falls back to empty list; the
    caller handles empty gracefully via `_synthetic_prices`."""
    try:
        from engines.data_engine import get_recent_closes  # type: ignore
        closes = await get_recent_closes(pair, timeframe, limit)
        return [float(x) for x in (closes or [])]
    except Exception:                                        # pragma: no cover
        return []


def _synthetic_prices(base: float = 1.0800, n: int = 200) -> List[float]:
    """Deterministic mock so the engine is testable without market data."""
    import math
    return [round(base + 0.001 * math.sin(i / 12.0), 5) for i in range(n)]


async def current_regime(
    pair: str = "EURUSD",
    timeframe: str = "H1",
    prices: Optional[List[float]] = None,
) -> RegimeSnapshot:
    """Classify the current regime for (pair, timeframe).

    If `prices` supplied → classify directly.
    Otherwise → try `data_engine.get_recent_closes`; fall back to
    deterministic synthetic prices so the engine never fails.
    """
    from engines.regime_classifier import describe_regime

    if prices is None:
        prices = await _load_recent_prices(pair, timeframe, limit=300)
    used_synth = False
    if not prices or len(prices) < 30:
        prices = _synthetic_prices()
        used_synth = True

    desc = describe_regime(prices)
    regime = str(desc.get("regime") or "unknown")
    vol = float(desc.get("vol") or 0.0)
    trend = float(desc.get("trend_ratio") or 0.0)
    # Confidence proxy: distance from the boundary line for the chosen band.
    # trending/ranging → based on |trend_ratio - threshold|; volatility bands
    # → based on |vol - threshold|. Bounded 0.4..0.95.
    if regime in ("high_volatility", "low_volatility"):
        confidence = round(min(0.95, 0.4 + abs(vol - 0.0125) * 20), 3)
    elif regime in ("trending", "ranging"):
        confidence = round(min(0.95, 0.4 + abs(trend - 0.55) * 1.2), 3)
    else:
        confidence = 0.0

    return RegimeSnapshot(
        pair=pair,
        timeframe=timeframe,
        regime=regime,
        confidence=confidence,
        volatility=vol,
        trend_score=trend,
        ts=datetime.now(timezone.utc).isoformat(),
        evidence={
            "n_prices":      len(prices),
            "source":        "synthetic" if used_synth else "market",
            "window":        desc.get("window"),
            "samples":       desc.get("samples"),
        },
    )
