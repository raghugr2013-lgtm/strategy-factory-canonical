"""
Factory Supervisor FS-P1.4 — `CopilotContext` (frozen view).

A pure, read-only transform from `system_state_view.snapshot()` to a
JSON-serialisable Copilot context. Both Copilot layers (Operational +
Advanced Intelligence) MUST consume `CopilotContext` and nothing else.

Operator-locked invariants:
  * The context is BUILT FROM `system_state_view` ONLY. No direct
    DB reads. No engine reads. No transport-side queries. This makes
    the context cache-coherent with the dashboard and provably
    provider-neutral.
  * No mutation. No side effects. No emit().
  * Best-effort. Bad inputs yield a degraded context but never raise.
  * Provider-agnostic: the context never references any LLM SDK.

The frozen contract is shaped to answer the operator's 8 Copilot
questions plus carry the architect-advisor output as ready-to-quote
context. Downstream consumers (Operational Copilot + Advanced
Intelligence layer + FAG proposals) read these fields by name.

Public surface:
    CopilotContext                 — frozen dataclass
    build(snap: dict) → CopilotContext
    build_from_snapshot()          — async helper (awaits system_state_view)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CopilotContext:
    """Frozen snapshot of factory state for Copilot consumption."""

    phase:             str
    evaluated_at:      Optional[str]
    advisory_only:     bool
    system_health:     str
    local_host_id:     str

    # Architect output — ready-to-quote.
    recommended_action: Dict[str, Any]
    recommendations:    List[Dict[str, Any]]
    blocked:            Dict[str, Any]
    healthy_systems:    List[str]
    unhealthy_systems:  List[str]
    inactive_workers:   List[str]
    active_workers:     List[str]
    inactive_flags:     Dict[str, Any]
    activation_ready:   List[str]

    # Subsystem snapshots, by name (read-only).
    fleet:                Dict[str, Any]   = field(default_factory=dict)
    queue_pressure:       Dict[str, Any]   = field(default_factory=dict)
    submissions:          Dict[str, Any]   = field(default_factory=dict)
    defer_queue:          Dict[str, Any]   = field(default_factory=dict)
    notifications:        Dict[str, Any]   = field(default_factory=dict)
    scaling_events:       Dict[str, Any]   = field(default_factory=dict)
    admission:            Dict[str, Any]   = field(default_factory=dict)
    workers:              Dict[str, Any]   = field(default_factory=dict)
    routing:              Dict[str, Any]   = field(default_factory=dict)
    remote_transport:     Dict[str, Any]   = field(default_factory=dict)
    deployment_readiness: Dict[str, Any]   = field(default_factory=dict)
    feature_flags:        Dict[str, Any]   = field(default_factory=dict)
    sources:              Dict[str, Any]   = field(default_factory=dict)
    # FS-P1.4 Auto-Learning Infrastructure — read-only insights snapshot.
    # Populated by `build_from_snapshot()` ONLY when FS_ENABLE_AUTO_LEARNING
    # is ON. Always {} when the consumption gate is OFF.
    auto_learning:        Dict[str, Any]   = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build(snap: Dict[str, Any]) -> CopilotContext:
    """Compose a CopilotContext from a system_state_view snapshot.

    The snapshot is the SOLE input — this function never reads from
    Mongo or any engine directly. Per the operator-locked rule:
    `Copilot must consume only copilot_context built from
    system_state_view.`
    """
    # Lazy import to avoid an architectural cycle.
    from engines.factory_supervisor import architect_advisor

    # Run advisor against the snap so the context carries the same
    # recommendations the dashboard shows.
    try:
        payload = architect_advisor.dashboard_payload(snap)
    except Exception as e:                                       # pragma: no cover
        logger.debug("[copilot_context] advisor failed: %s", e)
        payload = {
            "recommended_action": {},
            "recommendations":    [],
            "blocked":            {},
            "healthy_systems":    [],
            "unhealthy_systems":  [],
            "inactive_workers":   [],
            "active_workers":     [],
            "inactive_flags":     {},
            "activation_ready":   [],
        }

    return CopilotContext(
        phase                = str(snap.get("phase") or "FS-P1.4"),
        evaluated_at         = snap.get("evaluated_at"),
        advisory_only        = bool(snap.get("advisory_only", True)),
        system_health        = str(snap.get("system_health") or "unknown"),
        local_host_id        = str(snap.get("local_host_id") or "unknown"),
        recommended_action   = payload.get("recommended_action") or {},
        recommendations      = list(payload.get("recommendations") or []),
        blocked              = payload.get("blocked") or {},
        healthy_systems      = list(payload.get("healthy_systems") or []),
        unhealthy_systems    = list(payload.get("unhealthy_systems") or []),
        inactive_workers     = list(payload.get("inactive_workers") or []),
        active_workers       = list(payload.get("active_workers") or []),
        inactive_flags       = payload.get("inactive_flags") or {},
        activation_ready     = list(payload.get("activation_ready") or []),
        fleet                = snap.get("fleet") or {},
        queue_pressure       = snap.get("queue_pressure") or {},
        submissions          = snap.get("submissions") or {},
        defer_queue          = snap.get("defer_queue") or {},
        notifications        = snap.get("notifications") or {},
        scaling_events       = snap.get("scaling_events") or {},
        admission            = snap.get("admission") or {},
        workers              = snap.get("workers") or {},
        routing              = snap.get("routing") or {},
        remote_transport     = snap.get("remote_transport") or {},
        deployment_readiness = snap.get("deployment_readiness") or {},
        feature_flags        = snap.get("feature_flags") or {},
        sources              = snap.get("sources") or {},
        auto_learning        = snap.get("auto_learning") or {},
    )


async def build_from_snapshot(
    refresh: bool = False,
    window_sec: int = 3600,
) -> CopilotContext:
    """Convenience: await the snapshot then build a context.

    When `FS_ENABLE_AUTO_LEARNING` is ON, the snapshot dict is augmented
    in-place with an `auto_learning` block before composition. The
    aggregator is read-only — even when the gate is OFF the snapshot
    omits the block (zero extra cost on the dormant path).
    """
    from engines.factory_supervisor import system_state_view, auto_learning
    snap = await system_state_view.snapshot(refresh=refresh, window_sec=window_sec)
    if auto_learning.is_enabled():
        try:
            report = await auto_learning.build_report()
            snap = dict(snap)            # never mutate the cached snapshot
            snap["auto_learning"] = report.to_dict()
        except Exception as e:                                   # pragma: no cover
            logger.debug("[copilot_context] auto_learning hydration failed: %s", e)
    return build(snap)
