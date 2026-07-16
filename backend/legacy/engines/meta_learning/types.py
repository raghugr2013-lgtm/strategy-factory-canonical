"""Phase I — shared dataclasses.

Zero runtime deps except stdlib. Every dataclass has `to_dict()` for
JSON-safe serialisation and `from_dict()` for Mongo round-trip.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


class MetaMode:
    """Operating modes (per design §4)."""
    DISABLED    = "disabled"
    OBSERVE     = "observe"
    RECOMMEND   = "recommend"
    AUTONOMOUS  = "autonomous"

    ALL = (DISABLED, OBSERVE, RECOMMEND, AUTONOMOUS)

    @classmethod
    def is_valid(cls, m: str) -> bool:
        return str(m) in cls.ALL

    @classmethod
    def can_apply(cls, m: str) -> bool:
        """True iff mode allows write to `meta_learning_overrides`."""
        return str(m) in (cls.RECOMMEND, cls.AUTONOMOUS)


class MetaSurface:
    """Recommendation surface taxonomy."""
    BRAIN_WEIGHT              = "brain_weight"
    BRAIN_THRESHOLD           = "brain_threshold"
    PORTFOLIO_CAP             = "portfolio_cap"
    MARKET_WEIGHT             = "market_weight"
    EXECUTION_GATE            = "execution_gate"
    CONFIDENCE_CALIBRATION    = "confidence_calibration"
    STYLE_REGIME_MATRIX       = "style_regime_matrix"

    ALL = (BRAIN_WEIGHT, BRAIN_THRESHOLD, PORTFOLIO_CAP, MARKET_WEIGHT,
           EXECUTION_GATE, CONFIDENCE_CALIBRATION, STYLE_REGIME_MATRIX)


class MetaSeverity:
    INFO  = "info"
    LOW   = "low"
    MED   = "med"
    HIGH  = "high"


class MetaRiskBand:
    GREEN = "green"
    AMBER = "amber"
    RED   = "red"


class MetaRecStatus:
    PENDING   = "pending"
    APPROVED  = "approved"
    REJECTED  = "rejected"
    APPLIED   = "applied"
    REVERTED  = "reverted"
    EXPIRED   = "expired"


@dataclass
class MetaEvaluation:
    evaluation_id:   str
    account_id:      Optional[str]
    surface:         str
    target:          str
    window_start:    str
    window_end:      str
    n_samples:       int
    method:          str
    metrics:         Dict[str, float]
    significance:    float
    evidence:        Dict[str, Any]
    computed_at:     str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MetaEvaluation":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)


@dataclass
class MetaRecommendation:
    recommendation_id:  str
    evaluation_id:      str
    surface:            str
    target:             str
    current_value:      float
    proposed_value:     float
    proposed_delta:     float
    expected_uplift:    float
    confidence:         float
    severity:           str
    risk_band:          str
    rationale:          str
    evidence:           Dict[str, Any]
    guardrails:         Dict[str, Any]
    mode:               str
    status:             str
    created_at:         str
    expires_at:         str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MetaRecommendation":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)


@dataclass
class MetaApplication:
    application_id:     str
    recommendation_id:  str
    target:             str
    previous_value:     float
    new_value:          float
    applied_at:         str
    applied_by:         str
    mode:               str
    reversible:         bool = True
    reverted_at:        Optional[str] = None
    revert_reason:      Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MetaApplication":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)


@dataclass
class MetaLearningConfig:
    mode:               str
    window_hours:       int
    min_samples:        int
    max_delta_per_tick: float
    class_caps:         Dict[str, float]
    whitelist:          List[str]
    snapshot_ts:        str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
