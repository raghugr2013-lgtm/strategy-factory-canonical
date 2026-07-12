"""
Factory Supervisor FS-P1.3 — Architect advisor (Next Recommended Action).

Read-only / advisory-only. Zero execution authority. The Architect
NEVER mutates production state — its sole job is to look at the
`system_state_view.snapshot()` payload and produce:

    * a single TOP recommendation (Next Recommended Action), and
    * a list of additional candidates (lower-priority advisories).

Each recommendation carries:

    code          str   stable identifier (e.g. "AUTO_LEARNING_GATED")
    severity      str   info | suggestion | warn | critical
    title         str   one-line operator-facing title
    detail        str   prose explanation
    suggested_fix str   single-step path forward (env flip / endpoint / docs)
    evidence      dict  raw fields the rule consulted

Rule families (all advisory, all read-only):

    A) No action required           — happy path
    B) Windows VPS soak incomplete  — fleet has no Windows node OR soak not satisfied
    C) Auto-Learning eligible but disabled — readiness signals OK but gate OFF
    D) Best Master Bot available    — deployment_registry has a ready master bot
    E) LLM credits low              — universal-key budget warning
    F) Deployment ready             — a survivor / master bot passes hard gates
    G) Broker connection unhealthy  — heartbeat/healthcheck warns
    H) Defer-queue backlog          — queued + retrying rows above threshold
    I) Supervisor degraded          — heartbeat verdict band warn/critical
    J) Notification backlog         — unacked criticals > 0

Future Copilot compatibility — `dashboard_payload()` returns the SAME
view answering the operator's five mandated questions:

    "What requires attention?"      → recommendations
    "What is blocked?"              → blockers (defer / refuse rows)
    "What should I do next?"        → recommended_action (top)
    "Which systems are healthy?"    → system_health + per-source bands
    "Which systems are inactive?"   → feature_flags block

Public surface:
    Recommendation                  — frozen dataclass
    REC_SEVERITY_*                  — constants
    is_enabled()
    evaluate(snap: dict)            → List[Recommendation]
    recommended_action(snap: dict)  → Recommendation
    dashboard_payload(snap: dict)   → dict
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


REC_SEVERITY_INFO       = "info"
REC_SEVERITY_SUGGESTION = "suggestion"
REC_SEVERITY_WARN       = "warn"
REC_SEVERITY_CRITICAL   = "critical"

_SEV_RANK = {
    REC_SEVERITY_INFO:       0,
    REC_SEVERITY_SUGGESTION: 1,
    REC_SEVERITY_WARN:       2,
    REC_SEVERITY_CRITICAL:   3,
}


@dataclass
class Recommendation:
    code:          str
    severity:      str
    title:         str
    detail:        str
    suggested_fix: str = ""
    evidence:      Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def is_enabled() -> bool:
    """Mirror of the FS-P1.3 architect-dashboard gate. The advisor's
    output is consumable by Copilot / FAG only when this returns True.
    Even when False the evaluation still runs (read-only / safe); the
    dashboard payload carries `advisory_only=true`."""
    try:
        from engines.feature_flags import flag
        if not bool(flag("ENABLE_FACTORY_SUPERVISOR")):
            return False
        return bool(flag("FS_ENABLE_ARCHITECT_DASHBOARD"))
    except Exception:                                            # pragma: no cover
        return False


# ─── Rule helpers ───────────────────────────────────────────────────


def _is_windows_node(host_row: Dict[str, Any]) -> bool:
    cap = host_row.get("last_host_capability") or host_row.get("host_capability") or {}
    osname = (cap.get("os") or cap.get("platform") or "").lower()
    return "windows" in osname or "win32" in osname or "winnt" in osname


def _rule_a_happy_path(rules: List[Recommendation]) -> Recommendation:
    """Always emitted if no other rule fires."""
    return Recommendation(
        code="NO_ACTION_REQUIRED",
        severity=REC_SEVERITY_INFO,
        title="No action required",
        detail="All monitored Factory Supervisor signals are within nominal bands.",
        suggested_fix="",
        evidence={},
    )


def _rule_b_windows_soak(snap: Dict[str, Any]) -> Optional[Recommendation]:
    fleet = snap.get("fleet") or {}
    hosts: List[Dict[str, Any]] = fleet.get("hosts") or []
    win_hosts = [h for h in hosts if _is_windows_node(h)]
    if not win_hosts:
        return Recommendation(
            code="WINDOWS_VPS_SOAK_INCOMPLETE",
            severity=REC_SEVERITY_SUGGESTION,
            title="Windows VPS soak incomplete",
            detail=(
                "No Windows host has registered with the scaling registry "
                "yet. Multi-node telemetry and broker-side soak validations "
                "require a healthy Windows VPS heartbeat before activation."
            ),
            suggested_fix=(
                "Deploy a Windows VPS factory_runner instance and verify "
                "GET /api/factory-supervisor/fleet returns it."
            ),
            evidence={"windows_hosts": 0, "total_hosts": len(hosts)},
        )
    return None


def _rule_c_auto_learning_gated(snap: Dict[str, Any]) -> Optional[Recommendation]:
    flags = (snap.get("feature_flags") or {}).get("auto_learning_flags") or {}
    enabled = bool(flags.get("ENABLE_AUTONOMOUS_DISCOVERY"))
    fleet_band = (snap.get("fleet") or {}).get("fleet_band") or "unknown"
    deferq = (snap.get("defer_queue") or {}).get("stats") or {}
    per_status = deferq.get("per_status") or {}
    backlog = int(per_status.get("queued") or 0) + int(per_status.get("retrying") or 0)
    eligible = fleet_band in ("ok", "unknown") and backlog < 50 and not enabled
    if eligible:
        return Recommendation(
            code="AUTO_LEARNING_ELIGIBLE_BUT_DISABLED",
            severity=REC_SEVERITY_SUGGESTION,
            title="Auto-Learning eligible but disabled",
            detail=(
                "Fleet band is healthy and queue depth is below activation "
                "threshold. The Auto-Learning gate (ENABLE_AUTONOMOUS_DISCOVERY) "
                "remains OFF — by operator decree. No action required unless "
                "the operator wishes to begin the soak."
            ),
            suggested_fix=(
                "Per operator directive, Auto-Learning stays OFF. To begin "
                "a soak: flip ENABLE_AUTONOMOUS_DISCOVERY=true."
            ),
            evidence={"fleet_band": fleet_band, "queue_backlog": backlog,
                      "flag_value": enabled},
        )
    return None


def _rule_d_best_master_bot(snap: Dict[str, Any]) -> Optional[Recommendation]:
    dep = snap.get("deployment_readiness") or {}
    ev = dep.get("evidence") or {}
    count = int(ev.get("deployment_count") or ev.get("master_bot_count") or 0)
    if count > 0 and dep.get("ready"):
        return Recommendation(
            code="BEST_MASTER_BOT_AVAILABLE",
            severity=REC_SEVERITY_SUGGESTION,
            title="Best Master Bot available",
            detail=(
                f"{count} Master Bot deployment(s) currently meet hard-gate "
                "thresholds. The Architect surfaces them for promotion review."
            ),
            suggested_fix=(
                "Open the Master Bot tab and review the top-ranked deployment."
            ),
            evidence=ev,
        )
    return None


def _rule_e_llm_credits_low(snap: Dict[str, Any]) -> Optional[Recommendation]:
    # Soft heuristic: if a recent notification carries "llm_credits_low" or
    # "universal_key_low" in its event_type / payload, surface it.
    recent = (snap.get("notifications") or {}).get("recent_preview") or []
    hits = [n for n in recent if "llm" in str(n.get("event_type", "")).lower()
            or "credits" in str(n.get("title", "")).lower()
            or "universal" in str(n.get("title", "")).lower()]
    if not hits:
        return None
    return Recommendation(
        code="LLM_CREDITS_LOW",
        severity=REC_SEVERITY_WARN,
        title="LLM credits low",
        detail=(
            "One or more notifications report Universal LLM-key budget "
            "depletion. Some Copilot / AI advisory paths may degrade."
        ),
        suggested_fix=(
            "Visit Profile → Universal Key → Add Balance (or enable auto top-up)."
        ),
        evidence={"latest_hit": hits[0]},
    )


def _rule_f_deployment_ready(snap: Dict[str, Any]) -> Optional[Recommendation]:
    dep = snap.get("deployment_readiness") or {}
    if dep.get("ready") and not dep.get("blockers"):
        return Recommendation(
            code="DEPLOYMENT_READY",
            severity=REC_SEVERITY_INFO,
            title="Deployment ready",
            detail=(
                "All deployment readiness checks pass; no blockers reported."
            ),
            suggested_fix="Review the Deployment Readiness panel for details.",
            evidence=dep,
        )
    return None


def _rule_g_broker_unhealthy(snap: Dict[str, Any]) -> Optional[Recommendation]:
    fleet = snap.get("fleet") or {}
    headroom = (fleet.get("local") or {}).get("headroom") or {}
    band = str(headroom.get("band") or "unknown")
    if band == "critical":
        return Recommendation(
            code="BROKER_CONNECTION_UNHEALTHY",
            severity=REC_SEVERITY_CRITICAL,
            title="Broker / compute connection unhealthy",
            detail=(
                "Local compute headroom band is CRITICAL. Broker-side "
                "telemetry may be impacted; expect deferrals."
            ),
            suggested_fix=(
                "Inspect compute_probe and reduce concurrent workloads; "
                "consider scaling vertical capacity."
            ),
            evidence={"headroom": headroom},
        )
    return None


def _rule_h_defer_backlog(snap: Dict[str, Any]) -> Optional[Recommendation]:
    deferq = (snap.get("defer_queue") or {}).get("stats") or {}
    per_status = deferq.get("per_status") or {}
    pending = (
        int(per_status.get("queued") or 0)
        + int(per_status.get("retrying") or 0)
        + int(per_status.get("claimed") or 0)
    )
    if pending >= 25:
        sev = REC_SEVERITY_WARN if pending < 100 else REC_SEVERITY_CRITICAL
        return Recommendation(
            code="DEFER_QUEUE_BACKLOG",
            severity=sev,
            title=f"Defer queue backlog: {pending} pending row(s)",
            detail=(
                "The defer queue carries a non-trivial backlog of postponed "
                "workloads. Workers may not be draining fast enough."
            ),
            suggested_fix=(
                "Verify FS_ENABLE_DEFER_WORKER=true and inspect "
                "GET /api/factory-supervisor/workers."
            ),
            evidence={"pending": pending, "per_status": per_status},
        )
    return None


def _rule_i_supervisor_degraded(snap: Dict[str, Any]) -> Optional[Recommendation]:
    health = snap.get("system_health") or "unknown"
    if health in ("warn", "critical"):
        return Recommendation(
            code="SUPERVISOR_DEGRADED",
            severity=REC_SEVERITY_WARN if health == "warn" else REC_SEVERITY_CRITICAL,
            title=f"Supervisor health: {health}",
            detail=(
                "One or more subsystem signals are degraded. Cross-check the "
                "fleet, defer queue, and notification severities."
            ),
            suggested_fix=(
                "Open /api/factory-supervisor/system-state-view to see which "
                "subsystem is degraded."
            ),
            evidence={"system_health": health},
        )
    return None


def _rule_j_notification_backlog(snap: Dict[str, Any]) -> Optional[Recommendation]:
    nstats = (snap.get("notifications") or {}).get("stats") or {}
    per_status = nstats.get("per_status") or {}
    per_sev    = nstats.get("per_severity") or {}
    unread_crit = (
        int(per_sev.get("critical") or 0) + int(per_sev.get("fatal") or 0)
    )
    unread_total = int(per_status.get("new") or 0)
    if unread_crit > 0:
        return Recommendation(
            code="NOTIFICATION_CRITICALS_UNACKED",
            severity=REC_SEVERITY_CRITICAL,
            title=f"{unread_crit} critical notification(s) unacknowledged",
            detail=(
                "One or more critical/fatal-severity notifications are still "
                "unacknowledged."
            ),
            suggested_fix=(
                "Open the Notification Center, review and acknowledge the "
                "critical items."
            ),
            evidence={"unread_critical": unread_crit, "unread_total": unread_total},
        )
    if unread_total >= 25:
        return Recommendation(
            code="NOTIFICATION_BACKLOG",
            severity=REC_SEVERITY_WARN,
            title=f"{unread_total} unacknowledged notification(s)",
            detail="Notification backlog is growing.",
            suggested_fix="Review and acknowledge older notifications.",
            evidence={"unread_total": unread_total},
        )
    return None


_RULES: Tuple = (
    _rule_b_windows_soak,
    _rule_c_auto_learning_gated,
    _rule_d_best_master_bot,
    _rule_e_llm_credits_low,
    _rule_f_deployment_ready,
    _rule_g_broker_unhealthy,
    _rule_h_defer_backlog,
    _rule_i_supervisor_degraded,
    _rule_j_notification_backlog,
)


def evaluate(snap: Dict[str, Any]) -> List[Recommendation]:
    """Run all rules; collect every non-None Recommendation.

    Never raises. A bad snap → returns only NO_ACTION_REQUIRED.
    """
    out: List[Recommendation] = []
    for rule in _RULES:
        try:
            rec = rule(snap)
        except Exception as e:                                   # pragma: no cover
            logger.debug("[architect_advisor] rule %s raised: %s",
                         getattr(rule, "__name__", "?"), e)
            rec = None
        if rec is not None:
            out.append(rec)
    if not out:
        out.append(_rule_a_happy_path(out))
    # Sort by severity desc, then by code for stability.
    out.sort(key=lambda r: (-_SEV_RANK.get(r.severity, 0), r.code))
    return out


def recommended_action(snap: Dict[str, Any]) -> Recommendation:
    """Single top-priority recommendation."""
    recs = evaluate(snap)
    return recs[0]


# ─── Dashboard payload — five mandated questions ─────────────────────


def dashboard_payload(snap: Dict[str, Any]) -> Dict[str, Any]:
    """Compose the read-only Architect Dashboard payload.

    Frozen contract — additive only. Answers operator's five mandated
    questions for Copilot compatibility:

      * What requires attention?      → top recommendations
      * What is blocked?              → defer queue + refused submissions
      * What should I do next?        → recommended_action
      * Which systems are healthy?    → per-source bands + system_health
      * Which systems are inactive?   → feature_flags + worker manifest
      * Which features are ready for activation? → fag_flags + readiness
    """
    recs   = evaluate(snap)
    top    = recs[0] if recs else _rule_a_happy_path([])

    # Blocked = defer queue pending + recent refused submissions.
    deferq = snap.get("defer_queue") or {}
    dq_stats = deferq.get("stats") or {}
    per_status = dq_stats.get("per_status") or {}
    blocked: Dict[str, Any] = {
        "defer_queue_pending": (
            int(per_status.get("queued") or 0)
            + int(per_status.get("retrying") or 0)
            + int(per_status.get("claimed") or 0)
        ),
        "defer_queue_failed":  int(per_status.get("failed")  or 0),
        "defer_queue_expired": int(per_status.get("expired") or 0),
        "submissions_refused": int(
            ((snap.get("submissions") or {}).get("stats") or {}).get("per_outcome", {}).get("refused")
            or 0
        ),
        "rows_preview": deferq.get("rows_preview") or [],
    }

    # Healthy systems = sources block + system_health.
    sources = snap.get("sources") or {}
    healthy = [k for k, v in sources.items() if v == "ok"]
    unhealthy = [k for k, v in sources.items() if v != "ok"]

    # Inactive systems = workers with active=false + flags at default OFF.
    workers   = snap.get("workers") or {}
    manifest  = workers.get("manifest") or []
    inactive_workers = [w["name"] for w in manifest if not w.get("active")]
    active_workers   = [w["name"] for w in manifest if w.get("active")]

    flags_block = snap.get("feature_flags") or {}
    inactive_flags = {}
    for group in ("fs_flags", "fag_flags", "auto_learning_flags"):
        for name, value in (flags_block.get(group) or {}).items():
            if value in (False, "", 0, None):
                inactive_flags[name] = value

    # Activation-ready features = FAG flags that are OFF but whose
    # prerequisites are satisfied. FS-P1.3 reports the surface; the
    # actual readiness scoring lands in a future FAG evaluator.
    activation_ready: List[str] = []
    fag_flags = flags_block.get("fag_flags") or {}
    if (snap.get("fleet") or {}).get("fleet_band") == "ok":
        for name in ("ENABLE_BAND_BASED_ROUTING", "ENABLE_ADMISSION_CONTROL"):
            if not fag_flags.get(name):
                activation_ready.append(name)

    return {
        "phase":                "FS-P1.4",
        "advisory_only":        bool(snap.get("advisory_only", True)),
        "evaluated_at":         snap.get("evaluated_at"),
        "system_health":        snap.get("system_health") or "unknown",
        "recommended_action":   top.to_dict(),
        "recommendations":      [r.to_dict() for r in recs],
        "sections": {
            "fleet_health":         snap.get("fleet") or {},
            "queue_pressure":       snap.get("queue_pressure") or {},
            "submissions":          snap.get("submissions") or {},
            "defer_queue":          snap.get("defer_queue") or {},
            "notifications":        snap.get("notifications") or {},
            "scaling_events":       snap.get("scaling_events") or {},
            "admission_stats":      snap.get("admission") or {},
            "worker_status":        workers,
            "routing_stats":        snap.get("routing") or {},
            "remote_transport":     snap.get("remote_transport") or {},
            "deployment_readiness": snap.get("deployment_readiness") or {},
        },
        "blocked":              blocked,
        "healthy_systems":      healthy,
        "unhealthy_systems":    unhealthy,
        "inactive_workers":     inactive_workers,
        "active_workers":       active_workers,
        "inactive_flags":       inactive_flags,
        "activation_ready":     activation_ready,
        "feature_flags":        flags_block,
        "sources":              sources,
    }
