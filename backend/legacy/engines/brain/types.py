"""Phase F — shared dataclasses."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class BrainSignals:
    regime:                   str
    regime_confidence:        float
    predicted_next_regime:    Optional[str] = None
    transition_probability:   float = 0.0
    volatility:               float = 0.0
    avg_pairwise_correlation: Optional[float] = None
    diversification_score:    float = 1.0
    risk_budget_headroom:     float = 1.0
    liquidity_band:           str = "unknown"
    session:                  str = "unknown"
    spread_context:           str = "unknown"
    ts:                       str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StrategyScore:
    strategy_hash:  str
    score_now:      float
    score_next:     float
    components:     Dict[str, float] = field(default_factory=dict)
    reasons:        List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BrainDecision:
    strategy_hash:      str
    action:             str          # TRADE_NOW | PAUSE | REDUCE | INCREASE
                                     # REPLACE | PROMOTE | RETIRE | PRE_STAGE
                                     # EMERGENCY_ZERO
    target_weight:      float
    current_weight:     float
    weight_delta:       float
    score_now:          float
    score_next:         float
    shadow_allocation:  float = 0.0    # Q2 — pre-staged strategies only
    reason:             str = ""
    evidence:           Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BrainReport:
    ts:                 str
    signals:            Dict[str, Any] = field(default_factory=dict)
    decisions:          List[Dict[str, Any]] = field(default_factory=list)
    pre_staged:         List[str] = field(default_factory=list)
    emergency_zeroes:   List[str] = field(default_factory=list)
    risk_budget:        Dict[str, Any] = field(default_factory=dict)
    outcome_events_ids: List[str] = field(default_factory=list)
    policy_weights:     Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
