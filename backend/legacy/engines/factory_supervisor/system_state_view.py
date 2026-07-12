"""
Factory Supervisor FS-P1.3 — Authoritative read model.

`system_state_view.snapshot()` composes a SINGLE JSON-serialisable
dictionary that aggregates every subsystem the Supervisor knows about.
This dict is the canonical input for:

    * Factory Supervisor `/status` (already partial)
    * Notification Center read API
    * Architect Dashboard (read-only / advisory-only)
    * Future Copilot context
    * Feature Activation Governance (FAG)
    * Auto-Learning readiness evaluation

Discipline (operator-locked):
  * READ-ONLY. No writes. No side effects. No emit().
  * Best-effort. A failed source yields a structured `error` field but
    NEVER raises.
  * Default OFF for consumption gating. The aggregator itself ALWAYS
    runs (read-only is always safe), but the snapshot carries
    `advisory_only=true` when `FS_ENABLE_SYSTEM_STATE_VIEW` is OFF.
    Downstream consumers (Copilot, Auto-Learning, FAG) MUST honour
    that field before using the snapshot for any decision.
  * Provider/transport-neutral. The aggregator never knows about HTTP /
    gRPC / WebSocket / queue transports — it only reads what other
    modules already publish.
  * Cached 5 s in-process (same TTL as fleet_registry) so repeated
    dashboard polls cost ~one Mongo aggregate per 5 s.

Returns (top-level shape, frozen for FS-P1.3 — additive only):

    {
      "evaluated_at":       iso,
      "local_host_id":      str,
      "phase":              "FS-P1.3",
      "advisory_only":      bool,            # ← gate-OFF flag (default true)
      "system_health":      "ok" | "warn" | "critical" | "unknown",
      "fleet":              {...}            # fleet_registry.snapshot()
      "queue_pressure":     {...},           # local + per-class
      "submissions":        {recent, stats},
      "defer_queue":        {rows_preview, stats, limits},
      "notifications":      {unread_count, recent_preview, stats},
      "scaling_events":     {recent_preview, stats},
      "admission":          {stats, band, latest_journal_band},
      "workers":            {enabled, worker_id, manifest, scheduler},
      "routing":            {active, default, manifest},
      "deployment_readiness": {ready, blockers, evidence},
      "feature_flags":      {fs_flags, fag_flags, auto_learning_flags},
      "sources":            {<source>: "ok"|"error"|"unavailable", ...},
    }

Public surface:
    snapshot(refresh=False, window_sec=3600)  → dict
    is_enabled()                              → bool
    invalidate_cache()                        — for tests
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

CACHE_TTL_SEC = 5.0
_CACHE: Dict[str, Any] = {"ts": 0.0, "value": None}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def invalidate_cache() -> None:
    """Tests + admin force-refresh hook."""
    _CACHE["ts"] = 0.0
    _CACHE["value"] = None


def is_enabled() -> bool:
    """Returns True when downstream consumers are PERMITTED to consume
    the snapshot for decisions. The aggregator itself runs unconditionally
    (read-only is always safe). When this returns False the snapshot is
    advisory only — Copilot / Auto-Learning / FAG must NOT consume."""
    try:
        from engines.feature_flags import flag
        if not bool(flag("ENABLE_FACTORY_SUPERVISOR")):
            return False
        return bool(flag("FS_ENABLE_SYSTEM_STATE_VIEW"))
    except Exception:                                           # pragma: no cover
        return False


# ─── Per-source readers (each is best-effort) ────────────────────────


async def _read_fleet(window_sec: int) -> Dict[str, Any]:
    try:
        from engines.factory_supervisor import fleet_registry
        return await fleet_registry.snapshot(window_sec=window_sec)
    except Exception as e:                                      # pragma: no cover
        return {"error": str(e)[:200]}


async def _read_submissions(limit: int, window_sec: int) -> Dict[str, Any]:
    out: Dict[str, Any] = {"recent": [], "stats": {}}
    try:
        from engines.factory_supervisor import submission_dispatcher
        rows = await submission_dispatcher.list_recent(limit=limit)
        st   = await submission_dispatcher.stats(window_sec=window_sec)
        out["recent"] = rows
        out["stats"]  = st
    except Exception as e:                                      # pragma: no cover
        out["error"] = str(e)[:200]
    return out


async def _read_defer_queue(limit: int, window_sec: int) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "rows_preview": [],
        "stats":        {},
        "enabled":      False,
    }
    try:
        from engines.factory_supervisor import defer_queue
        out["enabled"] = defer_queue.is_enabled()
        st = await defer_queue.stats(window_sec=window_sec)
        out["stats"] = st
        # Show "queued" + "claimed" + "retrying" rows; oldest first by
        # next_eligible_retry_epoch (most urgent at top of dashboard).
        rows = await defer_queue.list_rows(limit=limit, status=None)
        # Keep only pending rows for the preview.
        pending = [r for r in rows if r.get("status") in
                   {"queued", "claimed", "retrying"}]
        out["rows_preview"] = pending[:limit]
    except Exception as e:                                      # pragma: no cover
        out["error"] = str(e)[:200]
    return out


async def _read_notifications(limit: int, window_sec: int) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "unread_count":   0,
        "recent_preview": [],
        "stats":          {},
        "enabled":        False,
    }
    try:
        from engines.factory_supervisor import notification_center
        out["enabled"] = notification_center.is_enabled()
        out["unread_count"]   = await notification_center.unread_count()
        out["recent_preview"] = await notification_center.list_notifications(
            limit=limit,
        )
        out["stats"] = await notification_center.stats(window_sec=window_sec)
    except Exception as e:                                      # pragma: no cover
        out["error"] = str(e)[:200]
    return out


async def _read_supervisor_events(limit: int, window_sec: int) -> Dict[str, Any]:
    out: Dict[str, Any] = {"recent_preview": [], "stats": {}}
    try:
        from engines.factory_supervisor import supervisor_events
        out["recent_preview"] = await supervisor_events.list_events(limit=limit)
        out["stats"] = await supervisor_events.stats(window_sec=window_sec)
    except Exception as e:                                      # pragma: no cover
        out["error"] = str(e)[:200]
    return out


async def _read_admission(window_sec: int) -> Dict[str, Any]:
    out: Dict[str, Any] = {"stats": {}, "band": "unknown"}
    try:
        from engines import architect_scaling_view
        st = await architect_scaling_view.get_admission_journal_stats(window_sec)
        out["stats"] = st
        # Derive a coarse band from stats (defer/refuse fraction).
        total   = int(st.get("total") or 0)
        per_dec = st.get("per_decision") or st.get("per_outcome") or {}
        if total > 0:
            denied = int(per_dec.get("defer") or 0) + int(per_dec.get("refuse") or 0)
            frac = denied / max(1, total)
            if frac > 0.5:
                out["band"] = "critical"
            elif frac > 0.2:
                out["band"] = "warn"
            else:
                out["band"] = "ok"
        else:
            out["band"] = "unknown"
    except Exception as e:                                      # pragma: no cover
        out["error"] = str(e)[:200]
    return out


def _read_queue_pressure() -> Dict[str, Any]:
    try:
        from engines import queue_pressure
        return queue_pressure.snapshot()
    except Exception as e:                                      # pragma: no cover
        return {"available": False, "error": str(e)[:200]}


def _read_workers_block() -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "enabled":   False,
        "worker_id": None,
        "manifest":  [],
        "scheduler": {},
    }
    try:
        from engines.factory_supervisor import worker_runtime
        out["enabled"]   = worker_runtime.is_enabled()
        out["worker_id"] = worker_runtime.worker_id()
        out["manifest"]  = worker_runtime.worker_manifest()
    except Exception as e:                                      # pragma: no cover
        out["error"] = str(e)[:200]
    try:
        from engines.factory_supervisor import worker_scheduler
        out["scheduler"] = worker_scheduler.status()
    except Exception as e:                                      # pragma: no cover
        out["scheduler"] = {"error": str(e)[:200]}
    return out


def _read_routing_block() -> Dict[str, Any]:
    try:
        from engines.factory_supervisor import routing_policy
        return {
            "active":   routing_policy.resolve_policy_name(),
            "default":  routing_policy.DEFAULT_POLICY_NAME,
            "manifest": routing_policy.policy_manifest(),
        }
    except Exception as e:                                      # pragma: no cover
        return {"error": str(e)[:200]}


def _read_remote_transport_block() -> Dict[str, Any]:
    try:
        from engines.factory_supervisor import remote_transport
        return remote_transport.transport_manifest()
    except Exception as e:                                      # pragma: no cover
        return {"error": str(e)[:200]}


async def _read_deployment_readiness() -> Dict[str, Any]:
    """Best-effort deployment readiness — composes multiple sources.

    Tries (each optional):
      * engines.deployment_readiness.snapshot()         (preferred)
      * engines.deployment_registry  → counts
      * engines.governance_universe / parity            → blockers
    Always returns a stable shape, never raises.
    """
    out: Dict[str, Any] = {
        "ready":     False,
        "blockers":  [],
        "evidence":  {},
    }
    # Preferred: a dedicated module if it exists.
    try:
        from engines import deployment_readiness  # type: ignore
        snap = await deployment_readiness.snapshot()             # type: ignore[attr-defined]
        if isinstance(snap, dict):
            return snap
    except Exception:
        pass
    # Soft fallback: count deployments persisted.
    try:
        from engines.db import get_db
        db = get_db()
        n = await db["deployment_registry"].estimated_document_count()
        out["evidence"]["deployment_count"] = int(n)
    except Exception:
        pass
    return out


def _read_feature_flags_block() -> Dict[str, Any]:
    """A curated subset of the feature_flags registry, grouped by intent.

    The full registry is at /api/latent/feature-flags; this slice is
    what dashboards / Copilot / FAG need to answer "what is ready?".
    """
    out: Dict[str, Any] = {
        "fs_flags":            {},
        "fag_flags":           {},
        "auto_learning_flags": {},
        "scheduler_flags":     {},
    }
    try:
        from engines.feature_flags import flag

        fs_names = (
            "ENABLE_FACTORY_SUPERVISOR",
            "ENABLE_NOTIFICATION_CENTER",
            "FS_ROUTING_POLICY",
            "FS_LEADER_LEASE_TTL_SEC",
            "FS_HEARTBEAT_CADENCE_SEC",
            "FS_ENABLE_DEFER_QUEUE",
            "FS_ENABLE_DEFER_WORKER",
            "FS_DEFER_RETRY_BASE_SEC",
            "FS_DEFER_RETRY_MAX_SEC",
            "FS_DEFER_MAX_RETRIES",
            "FS_DEFER_TTL_SEC",
            "FS_WORKER_POLL_INTERVAL_SEC",
            "FS_REMOTE_TRANSPORT",
            # FS-P1.3 additions
            "FS_ENABLE_SYSTEM_STATE_VIEW",
            "FS_ENABLE_ARCHITECT_DASHBOARD",
            "FS_ENABLE_WORKER_SCHEDULER",
            "FS_ENABLE_NOTIFICATION_API",
        )
        for n in fs_names:
            try:
                out["fs_flags"][n] = flag(n)
            except KeyError:
                pass

        # Feature Activation Governance signal — auto-learning gating.
        try:
            out["auto_learning_flags"]["ENABLE_AUTONOMOUS_DISCOVERY"] = flag(
                "ENABLE_AUTONOMOUS_DISCOVERY"
            )
        except KeyError:
            pass
        # Scheduler-class flags (future workers).
        for n in ("FS_ENABLE_WORKER_SCHEDULER", "FS_WORKER_POLL_INTERVAL_SEC"):
            try:
                out["scheduler_flags"][n] = flag(n)
            except KeyError:
                pass
        # FAG — band-based routing / admission control (latent guards).
        for n in ("ENABLE_BAND_BASED_ROUTING", "ENABLE_ADMISSION_CONTROL",
                  "ENABLE_ADAPTIVE_POOL_SIZING"):
            try:
                out["fag_flags"][n] = flag(n)
            except KeyError:
                pass

        # FS-P1.4 — Copilot + FAG engine flags.
        for n in (
            "FS_ENABLE_RECOMMENDATION_ENGINE",
            "FS_ENABLE_ELIGIBILITY_ENGINE",
            "FS_ENABLE_FAG_ENGINE",
            "FS_ENABLE_COPILOT",
            "FS_ENABLE_COPILOT_ADVANCED",
            "FS_COPILOT_PROVIDER",
            "FS_FAG_PROPOSAL_TTL_SEC",
            # FS-P1.4 — Auto-Learning Infrastructure consumption + loop gates.
            "FS_ENABLE_AUTO_LEARNING",
            "FS_ENABLE_AUTO_LEARNING_LOOP",
            "FS_AUTO_LEARNING_ROR_THRESHOLD",
            "FS_AUTO_LEARNING_AGING_THRESHOLD",
            "FS_AUTO_LEARNING_CALIBRATION_MIN_OUTCOMES",
        ):
            try:
                out["fs_flags"][n] = flag(n)
            except KeyError:
                pass

        # FS-P1.4 Auto-Learning — dormant component flags echoed for
        # Copilot Context consumption.
        for n in (
            "ENABLE_RISK_OF_RUIN",
            "RISK_OF_RUIN_WEIGHT",
            "ENABLE_AGING_PENALTY",
            "ENABLE_AGING_AUTO_DEMOTION",
            "ENABLE_CALIBRATION",
            "ENABLE_EXECUTION_REALISM_DEFAULTS",
        ):
            try:
                out["auto_learning_flags"][n] = flag(n)
            except KeyError:
                pass
    except Exception as e:                                      # pragma: no cover
        out["error"] = str(e)[:200]
    return out


# ─── Health summary ─────────────────────────────────────────────────


def _derive_system_health(snap: Dict[str, Any]) -> str:
    """Worst-of band across known signals. Conservative.

    Order: critical > warn > unknown > ok.
    """
    bands: List[str] = []
    fleet = snap.get("fleet") or {}
    bands.append(str(fleet.get("fleet_band") or "unknown"))
    adm = snap.get("admission") or {}
    bands.append(str(adm.get("band") or "unknown"))
    # If defer queue carries failed/expired in the recent window, warn.
    dq = (snap.get("defer_queue") or {}).get("stats") or {}
    per_status = dq.get("per_status") or {}
    if int(per_status.get("failed") or 0) > 0:
        bands.append("warn")
    if int(per_status.get("expired") or 0) > 0:
        bands.append("warn")
    # Notification severities recent → 1+ critical = critical.
    nstats = (snap.get("notifications") or {}).get("stats") or {}
    per_sev = nstats.get("per_severity") or {}
    if int(per_sev.get("critical") or 0) > 0:
        bands.append("critical")
    elif int(per_sev.get("warn") or 0) > 0:
        bands.append("warn")
    rank = {"ok": 1, "unknown": 2, "warn": 3, "critical": 4}
    chosen, chosen_rank = "ok", 1
    for b in bands:
        r = rank.get(b, 2)
        if r > chosen_rank:
            chosen, chosen_rank = b, r
    return chosen


# ─── Public snapshot ────────────────────────────────────────────────


async def snapshot(
    refresh: bool = False,
    window_sec: int = 3600,
    *,
    submissions_limit: int = 25,
    defer_limit: int = 25,
    notifications_limit: int = 25,
    events_limit: int = 25,
) -> Dict[str, Any]:
    """Compose the full system-state view. Cached 5 s."""
    now = time.monotonic()
    if not refresh and _CACHE["value"] is not None and (now - _CACHE["ts"]) < CACHE_TTL_SEC:
        return _CACHE["value"]

    fleet         = await _read_fleet(window_sec)
    queue_local   = _read_queue_pressure()
    submissions   = await _read_submissions(submissions_limit, window_sec)
    deferq        = await _read_defer_queue(defer_limit, window_sec)
    notifications = await _read_notifications(notifications_limit, window_sec)
    sup_events    = await _read_supervisor_events(events_limit, window_sec)
    adm           = await _read_admission(window_sec)
    workers       = _read_workers_block()
    routing       = _read_routing_block()
    transport     = _read_remote_transport_block()
    deploy        = await _read_deployment_readiness()
    flags_block   = _read_feature_flags_block()

    local_host_id = fleet.get("local_host_id") or "unknown"

    sources = {
        "fleet":            "ok" if not fleet.get("error") else "error",
        "queue_pressure":   "ok" if "error" not in queue_local else "error",
        "submissions":      "ok" if "error" not in submissions else "error",
        "defer_queue":      "ok" if "error" not in deferq else "error",
        "notifications":    "ok" if "error" not in notifications else "error",
        "supervisor_events":"ok" if "error" not in sup_events else "error",
        "admission":        "ok" if "error" not in adm else "error",
        "workers":          "ok" if "error" not in workers else "error",
        "routing":          "ok" if "error" not in routing else "error",
        "remote_transport": "ok" if "error" not in transport else "error",
        "deployment":       "ok" if "error" not in deploy else "error",
        "feature_flags":    "ok" if "error" not in flags_block else "error",
    }

    snap: Dict[str, Any] = {
        "evaluated_at":         _now_iso(),
        "local_host_id":        local_host_id,
        "phase":                "FS-P1.4",
        "advisory_only":        not is_enabled(),
        "fleet":                fleet,
        "queue_pressure":       queue_local,
        "submissions":          submissions,
        "defer_queue":          deferq,
        "notifications":        notifications,
        "scaling_events":       sup_events,
        "admission":            adm,
        "workers":               workers,
        "routing":              routing,
        "remote_transport":     transport,
        "deployment_readiness": deploy,
        "feature_flags":        flags_block,
        "sources":              sources,
    }
    snap["system_health"] = _derive_system_health(snap)

    _CACHE["ts"] = now
    _CACHE["value"] = snap
    return snap
