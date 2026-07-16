"""Phase J — shared dataclasses.

Same style as Phase I. Zero runtime deps except stdlib.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


class FEMode:
    DISABLED   = "disabled"
    OBSERVE    = "observe"
    RECOMMEND  = "recommend"
    AUTONOMOUS = "autonomous"
    ALL = (DISABLED, OBSERVE, RECOMMEND, AUTONOMOUS)

    @classmethod
    def is_valid(cls, m: str) -> bool: return str(m) in cls.ALL

    @classmethod
    def can_apply(cls, m: str) -> bool:
        return str(m) in (cls.RECOMMEND, cls.AUTONOMOUS)


class FESurface:
    FACTORY_IMPROVEMENT      = "factory_improvement"
    PROVIDER_EFFICIENCY      = "provider_efficiency"
    RESEARCH_ROI             = "research_roi"
    STRATEGY_CONTRIBUTION    = "strategy_contribution"
    REGIME_EFFECTIVENESS     = "regime_effectiveness"
    BOTTLENECK               = "bottleneck"
    COMPUTE_ALLOCATION       = "compute_allocation"
    EXECUTION_QUALITY        = "execution_quality"
    PORTFOLIO_HEALTH         = "portfolio_health"
    COVERAGE_GAP             = "coverage_gap"

    # Recommendation surfaces
    COMPUTE_REALLOCATION     = "compute_reallocation"
    BUDGET_REALLOCATION      = "budget_reallocation"
    RESEARCH_INVESTMENT      = "research_investment"
    STRATEGY_PRUNING         = "strategy_pruning"
    PORTFOLIO_REBALANCE_HINT = "portfolio_rebalance_hint"
    EXECUTION_PATH_PREF      = "execution_path_pref"

    INSIGHT_SURFACES = (
        FACTORY_IMPROVEMENT, PROVIDER_EFFICIENCY, RESEARCH_ROI,
        STRATEGY_CONTRIBUTION, REGIME_EFFECTIVENESS, BOTTLENECK,
        COMPUTE_ALLOCATION, EXECUTION_QUALITY, PORTFOLIO_HEALTH,
        COVERAGE_GAP,
    )
    RECOMMENDATION_SURFACES = (
        COMPUTE_REALLOCATION, BUDGET_REALLOCATION, RESEARCH_INVESTMENT,
        STRATEGY_PRUNING, PORTFOLIO_REBALANCE_HINT, EXECUTION_PATH_PREF,
    )


class FESeverity:
    INFO = "info"; LOW = "low"; MED = "med"; HIGH = "high"


class FERiskBand:
    GREEN = "green"; AMBER = "amber"; RED = "red"


class FERecStatus:
    PENDING  = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED  = "applied"
    REVERTED = "reverted"
    EXPIRED  = "expired"


@dataclass
class FactoryReport:
    report_id:          str
    window_start:       str
    window_end:         str
    cycle_ts:           str
    mode:               str
    kpis:               Dict[str, float] = field(default_factory=dict)
    provider_summary:   Dict[str, Any]   = field(default_factory=dict)
    research_summary:   Dict[str, Any]   = field(default_factory=dict)
    strategy_summary:   Dict[str, Any]   = field(default_factory=dict)
    regime_summary:     Dict[str, Any]   = field(default_factory=dict)
    bottleneck_summary: Dict[str, Any]   = field(default_factory=dict)
    execution_summary:  Dict[str, Any]   = field(default_factory=dict)
    portfolio_summary:  Dict[str, Any]   = field(default_factory=dict)
    evidence_ref:       Dict[str, Any]   = field(default_factory=dict)
    computed_at:        str = ""

    def to_dict(self) -> Dict[str, Any]: return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FactoryReport":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)


@dataclass
class FactoryInsight:
    insight_id:      str
    report_id:       str
    surface:         str
    target:          str
    window_start:    str
    window_end:      str
    n_samples:       int
    method:          str
    metrics:         Dict[str, float]
    significance:    float
    severity:        str
    evidence:        Dict[str, Any]
    computed_at:     str

    def to_dict(self) -> Dict[str, Any]: return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FactoryInsight":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)


@dataclass
class FactoryRecommendation:
    recommendation_id: str
    insight_ids:       List[str]
    surface:           str
    target:            str
    current_value:     float
    proposed_value:    float
    proposed_delta:    float
    expected_uplift:   float
    confidence:        float
    severity:          str
    risk_band:         str
    rationale:         str
    evidence:          Dict[str, Any]
    guardrails:        Dict[str, Any]
    mode:              str
    status:            str
    created_at:        str
    expires_at:        str

    def to_dict(self) -> Dict[str, Any]: return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FactoryRecommendation":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)


@dataclass
class FactoryApplication:
    application_id:    str
    recommendation_id: str
    target:            str
    previous_value:    float
    new_value:         float
    applied_at:        str
    applied_by:        str
    mode:              str
    reversible:        bool = True
    reverted_at:       Optional[str] = None
    revert_reason:     Optional[str] = None

    def to_dict(self) -> Dict[str, Any]: return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FactoryApplication":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)


@dataclass
class FactoryEvalConfig:
    mode: str
    window_hours_short: int
    window_hours_long:  int
    min_samples: int
    max_delta_per_tick: float
    class_caps: Dict[str, float]
    whitelist: List[str]
    snapshot_ts: str

    def to_dict(self) -> Dict[str, Any]: return asdict(self)
