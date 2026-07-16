"""Phase G — shared dataclasses (no runtime deps)."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class MarketSnapshot:
    """One observation, one timestamp — the raw input for observers."""
    pair:            str
    timeframe:       str
    ts:              str
    close:           float
    range_pct:       float = 0.0
    volatility:      float = 0.0
    volume:          Optional[float] = None
    session:         str = "unknown"
    regime:          str = "unknown"
    trend_score:     float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ObserverResult:
    """Return-value of every observer function. Deterministic."""
    name:      str
    score:     float                     # 0..1
    evidence:  Dict[str, Any] = field(default_factory=dict)
    ts:        str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MarketState:
    """Rolling aggregation, one row per (pair, timeframe, window)."""
    pair:                        str
    timeframe:                   str
    window:                      str          # "24h" | "7d" | "30d"
    ts:                          str
    trend_duration_bars:         float = 0.0
    trend_persistence_score:     float = 0.5
    volatility_mean:             float = 0.0
    volatility_expansion_ratio:  float = 1.0
    breakout_attempts:           int = 0
    breakout_success_rate:       float = 0.5
    reversal_strength_avg:       float = 0.5
    noise_ratio:                 float = 0.5
    session_pnl_bias:            Dict[str, float] = field(default_factory=dict)
    liquidity_band:              str = "unknown"
    avg_correlation_to_universe: Optional[float] = None
    style_performance:           Dict[str, float] = field(default_factory=dict)
    health_score:                float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StructuralChange:
    """A detected change-point on the market itself."""
    pair:               str
    timeframe:          str
    change_type:        str
    severity:           float
    detected_at:        str
    window_before:      str = ""
    window_after:       str = ""
    delta_metric:       Dict[str, float] = field(default_factory=dict)
    evidence:           Dict[str, Any] = field(default_factory=dict)
    method:             str = "heuristic"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MarketIntelligence:
    """The consumable payload for the Adaptive Trading Brain."""
    pair:                       str
    timeframe:                  str
    ts:                         str
    market_confidence:          float = 0.5   # 0..1 overall market clarity
    style_confidence:           Dict[str, float] = field(default_factory=dict)
    regime_confidence:          float = 0.5
    opportunity_score:          float = 0.5
    risk_environment:           float = 0.5   # high = benign
    active_structural_changes:  List[Dict[str, Any]] = field(default_factory=list)
    sources:                    Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
