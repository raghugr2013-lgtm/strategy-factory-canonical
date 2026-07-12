"""
Factory Supervisor FS-P1.1 — Routing policy registry (PURE).

A *pluggable* policy registry. Each policy is a pure function:

    (workload, fleet_snapshot, options) -> RoutingDecision

Discipline:
  * Pure. No I/O. No raises. Returns a structured dataclass.
  * Default policy: `local_only` (operator-locked).
  * 5 additional policies are REGISTERED but each is gated behind
    a "not_yet_active" guard so a stray FS_ROUTING_POLICY override
    does NOT silently change behaviour. Each guard records a clean
    structured "fallback to local_only" rationale that Copilot can
    later read.
  * Adding a new policy in a future sub-phase requires ONLY adding
    one entry to `_POLICIES`. No redesign.

Policy vocabulary (frozen for FS-P1.1):
    local_only           — ALWAYS chooses local host. Active.
    least_busy           — registered, inactive; falls back to local_only.
    capability_based     — registered, inactive; falls back to local_only.
    pair_affinity        — registered, inactive; falls back to local_only.
    strategy_affinity    — registered, inactive; falls back to local_only.
    deployment_affinity  — registered, inactive; falls back to local_only.

Why all six are registered now even though only local_only is active:
The Notification Center + Copilot need the names + semantics to be a
stable, queryable enum from day one. Activating a policy is a single-
line flip of `active=True` in this file + the policy function body —
no other module touches the routing pipeline.

Public surface:
    RoutingDecision                       — frozen dataclass
    DEFAULT_POLICY_NAME = "local_only"
    ALL_POLICY_NAMES                      — tuple
    POLICY_REGISTRY                       — dict[name → metadata]
    resolve_policy_name()                 — read FS_ROUTING_POLICY env
    choose_host(workload, fleet_snapshot) — pluggable dispatcher
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_POLICY_NAME = "local_only"


@dataclass
class RoutingDecision:
    """Result of a routing policy run. Pure data."""

    policy:           str        # the policy name that produced this
    decision:         str        # "local" | "remote" | "deferred" | "refused"
    assigned_host:    Optional[str] = None
    fallback_from:    Optional[str] = None   # name of the requested policy
                                             # if we fell back; None otherwise
    reason:           str = ""
    candidates_considered: List[str] = field(default_factory=list)
    rationale:        Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ─── Policy implementations ─────────────────────────────────────────

def _policy_local_only(
    workload: Any,
    fleet_snapshot: Optional[Dict[str, Any]],
    options: Optional[Dict[str, Any]] = None,
) -> RoutingDecision:
    """The only ACTIVE policy in FS-P1.1.

    Always returns local. Never refers to fleet_snapshot — caller can
    pass None and the policy still returns a valid decision."""
    local_host = _local_host_from_snapshot(fleet_snapshot)
    return RoutingDecision(
        policy="local_only",
        decision="local",
        assigned_host=local_host,
        reason="policy=local_only (operator-locked default in FS-P1.1)",
        candidates_considered=[local_host] if local_host else [],
        rationale={
            "policy_active": True,
            "policy_kind":   "single_host",
            "note":          "Multi-host policies registered but inactive in FS-P1.1.",
        },
    )


def _build_inactive_policy(name: str, intent: str) -> Callable[..., RoutingDecision]:
    """Factory that produces a deterministic 'fallback to local_only'
    decision for any registered-but-inactive policy."""

    def _impl(
        workload: Any,
        fleet_snapshot: Optional[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
    ) -> RoutingDecision:
        local = _policy_local_only(workload, fleet_snapshot, options)
        local.fallback_from = name
        local.reason = (
            f"policy={name} not active in FS-P1.1 — fallback to local_only"
        )
        local.rationale["fallback_from"] = name
        local.rationale["fallback_intent"] = intent
        local.rationale["policy_active"] = False
        return local

    _impl.__name__ = f"_policy_{name}"
    return _impl


# ─── Policy registry ────────────────────────────────────────────────

POLICY_REGISTRY: Dict[str, Dict[str, Any]] = {
    "local_only": {
        "fn":     _policy_local_only,
        "active": True,
        "intent": "Always pin work to local host (FS-P1.1 default).",
        "kind":   "single_host",
    },
    "least_busy": {
        "fn":     _build_inactive_policy(
            "least_busy",
            "Route to the host with the lowest queue depth across the fleet.",
        ),
        "active": False,
        "intent": "Lowest fleet-wide queue depth wins.",
        "kind":   "multi_host",
    },
    "capability_based": {
        "fn":     _build_inactive_policy(
            "capability_based",
            "Route based on capabilities_required matched against host_capability profile.",
        ),
        "active": False,
        "intent": "Match workload.capabilities_required ⊆ host capability tags.",
        "kind":   "multi_host",
    },
    "pair_affinity": {
        "fn":     _build_inactive_policy(
            "pair_affinity",
            "Stick (pair, host) pairings to maximise warm-cache reuse.",
        ),
        "active": False,
        "intent": "Stable pair→host mapping.",
        "kind":   "affinity",
    },
    "strategy_affinity": {
        "fn":     _build_inactive_policy(
            "strategy_affinity",
            "Stick strategies to a single host while a soak is ongoing.",
        ),
        "active": False,
        "intent": "Stable strategy_id→host mapping during sustained jobs.",
        "kind":   "affinity",
    },
    "deployment_affinity": {
        "fn":     _build_inactive_policy(
            "deployment_affinity",
            "Route deployment-related work to the host hosting that deployment.",
        ),
        "active": False,
        "intent": "Stable deployment_id→host mapping for cTrader telemetry.",
        "kind":   "affinity",
    },
}

ALL_POLICY_NAMES: Tuple[str, ...] = tuple(POLICY_REGISTRY.keys())


# ─── Public surface ─────────────────────────────────────────────────

def resolve_policy_name() -> str:
    """Read FS_ROUTING_POLICY from the feature_flags registry.

    Unknown values fall back to local_only with a logger warning so a
    typo can never silently activate an unsafe path.
    """
    try:
        from engines.feature_flags import flag
        name = str(flag("FS_ROUTING_POLICY") or DEFAULT_POLICY_NAME)
    except Exception:                                          # pragma: no cover
        return DEFAULT_POLICY_NAME
    if name not in POLICY_REGISTRY:
        logger.warning(
            "[routing_policy] unknown FS_ROUTING_POLICY=%r — fallback to %s",
            name, DEFAULT_POLICY_NAME,
        )
        return DEFAULT_POLICY_NAME
    return name


def choose_host(
    workload: Any,
    fleet_snapshot: Optional[Dict[str, Any]] = None,
    *,
    policy_name: Optional[str] = None,
    options: Optional[Dict[str, Any]] = None,
) -> RoutingDecision:
    """Run the active routing policy. PURE — no I/O.

    Args:
        workload       : engines.factory_supervisor.workload.Workload
        fleet_snapshot : dict from fleet_registry.snapshot() OR None
                         (local_only policy works with None).
        policy_name    : optional override; default resolves from
                         FS_ROUTING_POLICY env.
        options        : reserved for future per-call hints.
    """
    name = policy_name or resolve_policy_name()
    spec = POLICY_REGISTRY.get(name) or POLICY_REGISTRY[DEFAULT_POLICY_NAME]
    try:
        decision = spec["fn"](workload, fleet_snapshot, options)
    except Exception as e:                                     # pragma: no cover
        logger.warning("[routing_policy] policy %s raised %s — fallback to local_only", name, e)
        decision = _policy_local_only(workload, fleet_snapshot, options)
        decision.fallback_from = name
        decision.reason = f"policy={name} raised; fallback to local_only"
        decision.rationale["error"] = str(e)[:200]
    return decision


# ─── Internal helpers ───────────────────────────────────────────────

def _local_host_from_snapshot(snap: Optional[Dict[str, Any]]) -> Optional[str]:
    if isinstance(snap, dict):
        h = snap.get("local_host_id")
        if h:
            return str(h)
    try:
        from engines import host_capability
        caps = host_capability.current()
        if caps is not None and caps.host_id:
            return caps.host_id
    except Exception:                                          # pragma: no cover
        pass
    try:
        import socket
        return socket.gethostname() or None
    except Exception:                                          # pragma: no cover
        return None


def policy_manifest() -> List[Dict[str, Any]]:
    """Stable, JSON-serialisable manifest for /status + Copilot."""
    out: List[Dict[str, Any]] = []
    for name, meta in POLICY_REGISTRY.items():
        out.append({
            "name":   name,
            "active": bool(meta["active"]),
            "intent": str(meta["intent"]),
            "kind":   str(meta["kind"]),
        })
    return out
