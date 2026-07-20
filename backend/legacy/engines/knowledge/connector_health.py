"""Phase 2 Stage 4 — Connector health (P4A.0).

Per-connector `HealthSnapshot` shape and lifecycle-state enum.
Called by the connector-health endpoints
(`GET /api/knowledge/connectors/{name}/health` and the aggregate
`GET /api/knowledge/connectors/health`).

Six lifecycle states (from PHASE_4_MASTER_PLAN §3.2):

    registered → opted_in → healthy → degraded → failing → quarantined
                                   ↕
                                cooling  (rate-limit backoff)

Every transition is stamped into
`strategy_knowledge_base.connector_events` with a per-connector event
history (TTL 180d — enforced by the sweeper in P4C.3).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class ConnectorState(str, Enum):
    """Lifecycle state — string-valued for JSON serialisation."""
    REGISTERED    = "registered"
    OPTED_IN      = "opted_in"
    HEALTHY       = "healthy"
    DEGRADED      = "degraded"
    COOLING       = "cooling"
    FAILING       = "failing"
    QUARANTINED   = "quarantined"
    DORMANT       = "dormant"           # flag OFF — connector not exposed


@dataclass
class ConnectorHealthSnapshot:
    """Point-in-time health for one connector.

    Attributes:
        name: Connector name.
        state: Current lifecycle state.
        flag_name: The env flag that enables this connector.
        flag_enabled: Whether the flag is currently ON.
        auth_configured: Whether every required auth secret is present.
        auth_mode: The auth mode string (`"none"`, `"api_key"`, ...).
        supported_domains: List of domain string values.
        default_trust_tier: Seed trust tier for scoring.
        last_success_at: ISO timestamp of the last successful
            discover/fetch. None when the connector has never succeeded.
        last_failure_at: ISO timestamp of the last observed failure.
        last_error: Truncated last error message (never PII).
        retry_count_1h: Count of retries in the last hour.
        rate_limit_backoff_until: ISO timestamp when the cool-off ends.
        connector_version: Semver code version.
        source_contract_version: Extras-shape contract version.
        capabilities: Serialised ConnectorCapabilities.
        rate_limit: Serialised RateLimit.
    """
    name:                    str
    state:                   ConnectorState
    flag_name:               str
    flag_enabled:            bool
    auth_configured:         bool
    auth_mode:               str
    supported_domains:       List[str]
    default_trust_tier:      int
    last_success_at:         Optional[str]  = None
    last_failure_at:         Optional[str]  = None
    last_error:              Optional[str]  = None
    retry_count_1h:          int            = 0
    rate_limit_backoff_until: Optional[str] = None
    connector_version:       str            = "0.1.0"
    source_contract_version: int            = 1
    capabilities:            Dict[str, Any] = field(default_factory=dict)
    rate_limit:              Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Normalise the enum → string for JSON serialisation
        d["state"] = self.state.value
        return d


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Simple in-process observer (P4A.0) ───────────────────────────────
#
# Concrete connectors call these helpers on every discover / fetch
# attempt so `ConnectorHealthProbe` can compose an accurate snapshot
# without each connector re-implementing bookkeeping.
#
# The observer is INTENTIONALLY in-process only — Stage 4 does not
# introduce a distributed observer surface. When the platform gains
# multi-node topology (Phase 5+), this observer moves behind a
# distribution-aware Protocol.

@dataclass
class _ConnectorObservation:
    last_success_at:         Optional[str]  = None
    last_failure_at:         Optional[str]  = None
    last_error:              Optional[str]  = None
    retry_events:            List[str]      = field(default_factory=list)   # ISO timestamps
    rate_limit_backoff_until: Optional[str] = None
    state:                   ConnectorState = ConnectorState.REGISTERED


class ConnectorObserver:
    """Per-connector in-process observation store."""

    def __init__(self) -> None:
        self._store: Dict[str, _ConnectorObservation] = {}

    def _entry(self, name: str) -> _ConnectorObservation:
        if name not in self._store:
            self._store[name] = _ConnectorObservation()
        return self._store[name]

    def note_success(self, name: str) -> None:
        e = self._entry(name)
        e.last_success_at = now_iso()
        # A single success clears cooling / degraded → healthy
        if e.state in {ConnectorState.COOLING, ConnectorState.DEGRADED}:
            e.state = ConnectorState.HEALTHY
        elif e.state == ConnectorState.REGISTERED or e.state == ConnectorState.OPTED_IN:
            e.state = ConnectorState.HEALTHY

    def note_failure(self, name: str, error: str) -> None:
        e = self._entry(name)
        e.last_failure_at = now_iso()
        e.last_error = (error or "")[:200]
        if e.state == ConnectorState.HEALTHY:
            e.state = ConnectorState.DEGRADED
        elif e.state == ConnectorState.DEGRADED:
            e.state = ConnectorState.FAILING

    def note_retry(self, name: str) -> None:
        e = self._entry(name)
        e.retry_events.append(now_iso())
        # Trim to last 1000 events to bound memory
        if len(e.retry_events) > 1000:
            e.retry_events = e.retry_events[-1000:]

    def note_rate_limit(self, name: str, until_iso: str) -> None:
        e = self._entry(name)
        e.rate_limit_backoff_until = until_iso
        e.state = ConnectorState.COOLING

    def note_flag_state(self, name: str, enabled: bool) -> None:
        e = self._entry(name)
        if not enabled:
            e.state = ConnectorState.DORMANT
        elif e.state == ConnectorState.DORMANT:
            e.state = ConnectorState.OPTED_IN

    def note_quarantine(self, name: str, reason: str) -> None:
        e = self._entry(name)
        e.state = ConnectorState.QUARANTINED
        e.last_error = (reason or "")[:200]

    def snapshot(self, name: str) -> _ConnectorObservation:
        return self._entry(name)

    def retry_count_last_hour(self, name: str) -> int:
        e = self._entry(name)
        if not e.retry_events:
            return 0
        # Compare ISO strings — coarse but adequate; UTC ordering holds
        cutoff = datetime.now(timezone.utc).timestamp() - 3600
        count = 0
        for ts_iso in e.retry_events:
            try:
                ts = datetime.fromisoformat(ts_iso).timestamp()
            except ValueError:
                continue
            if ts >= cutoff:
                count += 1
        return count

    def _reset_for_tests(self) -> None:
        self._store.clear()


# Singleton — one observer per process
_OBSERVER: Optional[ConnectorObserver] = None


def get_observer() -> ConnectorObserver:
    global _OBSERVER
    if _OBSERVER is None:
        _OBSERVER = ConnectorObserver()
    return _OBSERVER


def _reset_observer_for_tests() -> None:
    global _OBSERVER
    _OBSERVER = ConnectorObserver()
