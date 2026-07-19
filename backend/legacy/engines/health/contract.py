"""Phase 2, Stage 1 — Universal Health Contract dataclass.

PURE DATA. No I/O, no DB, no framework imports. Every subsystem
imports these dataclasses to publish its `HealthSnapshot`. The
aggregator (`/api/health/system`) collects them.

Rules:
  * Every field is JSON-serialisable via `asdict()`.
  * Every score is bounded 0..100 (integers or floats).
  * Every timestamp is a UTC ISO-8601 string or None.
  * Enums are string enums so JSON round-trips cleanly.
  * `subsystem` is a free-form string; convention is snake_case.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class RecoveryState(str, Enum):
    """Closed set of subsystem states.

    ok         — running normally
    degraded   — running but with reduced capability / elevated errors
    critical   — significant failure; auto-recovery not viable
    recovering — actively self-healing (e.g. retrying, warming caches)
    """

    OK = "ok"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    RECOVERING = "recovering"


class ActionRequired(str, Enum):
    """Closed set of operator actions.

    Every non-`ok` state names exactly one of these so operators can
    respond without reading logs.
    """

    NONE = "none"
    OPERATOR_REVIEW = "operator_review"
    RESTART_COMPONENT = "restart_component"
    RESET_BUDGET = "reset_budget"
    CLEAR_DEAD_LETTER = "clear_dead_letter"
    WAIT_FOR_BACKOFF = "wait_for_backoff"
    MANUAL_INTERVENTION = "manual_intervention"


@dataclass
class ResourceUsage:
    cpu_percent: Optional[float] = None      # 0..100
    mem_mb: Optional[int] = None
    in_flight: int = 0
    queue_depth: int = 0
    budget_headroom: Optional[float] = None  # 0..1 — USD remaining / daily cap


@dataclass
class LastSuccessfulRun:
    at: Optional[str] = None                 # UTC ISO
    duration_ms: Optional[int] = None
    ref: Optional[str] = None                # correlation id / run_id


@dataclass
class FailureCount:
    last_hour: int = 0
    last_day: int = 0
    since_boot: int = 0


@dataclass
class RecoveryStatus:
    state: RecoveryState = RecoveryState.OK
    reason: str = ""
    action_required: ActionRequired = ActionRequired.NONE
    last_recovery_at: Optional[str] = None   # UTC ISO


@dataclass
class HealthSnapshot:
    """The one shape every subsystem publishes.

    Emit via `GET /api/<subsystem>/health`. Aggregated at
    `GET /api/health/system`. Never raises.
    """

    subsystem: str
    ts: str = ""                             # UTC ISO — auto-filled by __post_init__

    # Scores — 0..100
    health_score: int = 100
    readiness_score: int = 100
    confidence_score: int = 100

    # Blocks
    resource_usage: ResourceUsage = field(default_factory=ResourceUsage)
    last_successful_run: LastSuccessfulRun = field(default_factory=LastSuccessfulRun)
    failure_count: FailureCount = field(default_factory=FailureCount)
    recovery_status: RecoveryStatus = field(default_factory=RecoveryStatus)

    def __post_init__(self) -> None:
        if not self.ts:
            self.ts = datetime.now(timezone.utc).isoformat()
        # Clamp scores to [0, 100].
        self.health_score = _clamp_score(self.health_score)
        self.readiness_score = _clamp_score(self.readiness_score)
        self.confidence_score = _clamp_score(self.confidence_score)

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe dict. Enums are serialised as their string values."""
        d = asdict(self)
        # asdict() serialises enums as their .value automatically only for
        # str-Enum subclasses — belt-and-braces just in case:
        rs = d.get("recovery_status") or {}
        state = rs.get("state")
        if isinstance(state, RecoveryState):
            rs["state"] = state.value
        ar = rs.get("action_required")
        if isinstance(ar, ActionRequired):
            rs["action_required"] = ar.value
        return d


def _clamp_score(v: Any) -> int:
    """Coerce to int in [0, 100]. Never raises."""
    try:
        n = int(round(float(v)))
    except (TypeError, ValueError):
        return 0
    if n < 0:
        return 0
    if n > 100:
        return 100
    return n


def empty_snapshot(subsystem: str) -> HealthSnapshot:
    """A `no data yet` snapshot.

    Used at boot before any data has been collected — better than
    raising. Scores default to 100 with `state=ok` because "not yet
    observed" is not the same as "unhealthy". A subsystem should
    replace this with a real snapshot on its first tick.
    """
    return HealthSnapshot(
        subsystem=subsystem,
        health_score=100,
        readiness_score=100,
        confidence_score=100,
        recovery_status=RecoveryStatus(
            state=RecoveryState.OK,
            reason="no_data_yet",
            action_required=ActionRequired.NONE,
        ),
    )
