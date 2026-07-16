"""Phase H — shared dataclasses.

Zero runtime dependencies except stdlib. Every dataclass has a
`to_dict()` for JSON-safe serialisation and (where applicable) a
`from_dict()` for read-back after Mongo round-trip.

DESIGN NOTES:
  * Every collection is `account_id`-indexed (Q8: architect for multi-
    account now, single-account impl for Phase H).
  * `request_id` is a client-side idempotency key (uuid4 hex).
  * `fill_id` is broker-assigned but ALWAYS stored — Q5 immutable id
    chain requirement.
  * `brain_decision_id` links back to Phase F's `brain_decision`
    outcome_event so attribution has an immutable join key.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# ── Enums as string constants (kept simple; validated at edges) ──
class OrderState:
    PENDING   = "PENDING"
    SENT      = "SENT"
    ACCEPTED  = "ACCEPTED"
    WORKING   = "WORKING"
    PARTIAL   = "PARTIAL"
    FILLED    = "FILLED"
    REJECTED  = "REJECTED"
    CANCELLED = "CANCELLED"
    EXPIRED   = "EXPIRED"

    TERMINAL = ("FILLED", "REJECTED", "CANCELLED", "EXPIRED")

    @classmethod
    def is_terminal(cls, s: str) -> bool:
        return str(s) in cls.TERMINAL


class PositionState:
    OPEN          = "OPEN"
    PARTIAL_CLOSE = "PARTIAL_CLOSE"
    CLOSED        = "CLOSED"


class JournalEventType:
    """Every event that lands in the execution_journal. Used by the
    replay engine to route back through the lifecycle."""
    ORDER_STATE_CHANGE  = "order_state_change"
    FILL                = "fill_event"
    BROKER_CONNECT      = "broker_connect"
    BROKER_DISCONNECT   = "broker_disconnect"
    BROKER_HEARTBEAT    = "broker_heartbeat"
    BROKER_REQUOTE      = "broker_requote"
    CLOCK_DRIFT         = "clock_drift"
    LATENCY_SAMPLE      = "latency_sample"
    RISK_RECOMMENDATION = "risk_recommendation"
    EXECUTION_DECISION  = "execution_decision"


# ── Core dataclasses ──────────────────────────────────────────────
@dataclass
class OrderRequest:
    request_id:        str                     # uuid — client-side idempotency
    account_id:        str
    pair:              str
    side:              str                     # BUY | SELL
    type:              str                     # MARKET | LIMIT | STOP | STOP_LIMIT
    qty:               float
    price:             Optional[float] = None  # None for MARKET
    sl_pips:           Optional[float] = None
    tp_pips:           Optional[float] = None
    time_in_force:     str = "IOC"             # Q7 — broker-native preserved
    strategy_hash:     Optional[str] = None
    brain_decision_id: Optional[str] = None    # Q5 — immutable audit chain
    requested_at:      str = ""
    operator:          Optional[Dict[str, Any]] = None
    state:             str = OrderState.PENDING
    broker_order_id:   Optional[str] = None    # populated after SENT
    reject_reason:     Optional[str] = None
    cancel_reason:     Optional[str] = None
    qty_filled:        float = 0.0
    avg_fill_price:    Optional[float] = None
    updated_at:        str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "OrderRequest":
        # Only pass known fields; ignore Mongo _id + stale keys.
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)


@dataclass
class FillEvent:
    fill_id:        str                        # broker-assigned
    request_id:     str
    account_id:     str
    pair:           str
    side:           str
    qty_filled:     float
    price:          float
    commission:     float = 0.0
    swap:           float = 0.0
    timestamp:      str = ""
    latency_ms:     Optional[float] = None
    slippage_pips:  Optional[float] = None
    is_partial:     bool = False
    broker_order_id: Optional[str] = None
    seq:            int = 0                    # replay ordering key

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FillEvent":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)


@dataclass
class Position:
    position_id:       str
    account_id:        str
    pair:              str
    side:              str
    qty:               float
    avg_entry:         float
    sl:                Optional[float] = None
    tp:                Optional[float] = None
    opened_at:         str = ""
    closed_at:         Optional[str] = None
    realised_pnl:      float = 0.0
    unrealised_pnl:    float = 0.0
    strategy_hash:     Optional[str] = None
    brain_decision_id: Optional[str] = None
    state:             str = PositionState.OPEN
    fill_ids:          List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Position":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)


@dataclass
class BrokerHealth:
    """Q4: rolling weighted windows (short 5m, medium 1h, long 24h)."""
    broker:               str
    account_id:           str
    ts:                   str
    connected:            bool = False
    latency_ms:           float = 0.0
    reject_rate_5m:       float = 0.0
    reject_rate_60m:      float = 0.0
    reject_rate_24h:      float = 0.0
    requote_rate_5m:      float = 0.0
    requote_rate_60m:     float = 0.0
    requote_rate_24h:     float = 0.0
    disconnect_count_5m:  int = 0
    disconnect_count_24h: int = 0
    score_5m:             float = 1.0          # ← execution decisions primary
    score_60m:            float = 1.0
    score_24h:            float = 1.0
    band:                 str = "healthy"      # healthy | degraded | unhealthy
    notes:                List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BrokerHealth":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)


@dataclass
class ExecutionQualitySnapshot:
    account_id:         str
    pair:               str
    session:            str                    # asian|london|ny|overlap|quiet|all
    window:             str                    # "1h" | "24h" | "7d"
    ts:                 str
    spread_pips_mean:   float = 0.0
    spread_pips_p95:    float = 0.0
    latency_ms_mean:    float = 0.0
    latency_ms_p95:     float = 0.0
    slippage_pips_mean: float = 0.0
    slippage_pips_p95:  float = 0.0
    reject_rate:        float = 0.0
    requote_rate:       float = 0.0
    fill_quality:       str = "perfect"
    score:              float = 0.7            # neutral default
    method:             str = "estimated_no_live_feed"
    n_samples:          int = 0
    components:         Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ExecutionQualitySnapshot":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)


@dataclass
class ExecutionAttribution:
    """Immutable ID join — Q5 audit chain enforcement."""
    attribution_id:     str
    account_id:         str
    brain_decision_id:  str
    strategy_hash:      str
    request_id:         str
    broker_order_id:    Optional[str] = None
    fill_ids:            List[str] = field(default_factory=list)
    position_id:         Optional[str] = None
    requested_ts:        str = ""
    fill_ts:             str = ""
    closed_ts:           Optional[str] = None
    expected_price:      float = 0.0
    realised_price:      float = 0.0
    slippage_pips:       float = 0.0
    realised_pnl:        float = 0.0
    predicted_score:     float = 0.0
    realised_execution_score: float = 0.0
    delta_predicted_realised: float = 0.0
    outcome_events_ids:  List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ExecutionAttribution":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)


@dataclass
class JournalEvent:
    """Immutable append-only replay log entry (Execution Replay §24.3)."""
    seq:          int                          # monotonic per account_id
    ts_ns:        int                          # ns since epoch — replay order
    account_id:   str
    event_type:   str                          # JournalEventType.*
    payload:      Dict[str, Any] = field(default_factory=dict)
    correlation:  Dict[str, str] = field(default_factory=dict)  # ids for join

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RiskRecommendation:
    """Q3: risk engine RECOMMENDS only. Never auto-liquidates."""
    ts:            str
    account_id:    str
    guard:         str                         # RiskGuard.*
    severity:      float                       # 0..1
    action:        str                         # "pause"|"reduce"|"halt_new_opens"
    strategy_hash: Optional[str] = None
    reason:        str = ""
    evidence:      Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RiskGuard:
    MAX_POSITIONS       = "max_positions"
    MAX_EXPOSURE_PAIR   = "max_exposure_pair"
    MAX_EXPOSURE_TOTAL  = "max_exposure_total"
    DAILY_LOSS_CAP      = "daily_loss_cap"
    LOSS_24H_CAP        = "loss_24h_cap"
    BROKER_HEALTH_MIN   = "broker_health_min"
    CLOCK_DRIFT         = "clock_drift"
