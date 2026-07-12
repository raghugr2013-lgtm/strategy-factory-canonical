"""
Factory Supervisor FS-P1.0 — Canonical supervisor event vocabulary.

This module is the Supervisor's event emitter. It writes structured
rows to TWO destinations (best-effort, independently):

  1. `scaling_events` (P1.D) — preserves unified scaling vocabulary.
  2. `notifications`        — Notification Center storage (the NC
     subsystem is fully built in FS-P1.3; in FS-P1.0 the collection
     and the writer are wired so events flow from day one, per the
     operator's directive "NC integrated from day one even if UI deferred").

Both writes are gated by their respective master flags:
  * `ENABLE_FACTORY_SUPERVISOR=true`   → enables the emitter at all.
  * `ENABLE_NOTIFICATION_CENTER=true`  → enables the NC bridge write.

If the Factory Supervisor flag is OFF, emit() is a no-op. Behaviour is
byte-identical to the pre-FS-P1.0 world.

Canonical event types (frozen for FS-P1; additive only):

  Operational events (FS-P1.1+):
    WORK_ROUTED                  — submission_dispatcher accepted a job
    WORK_DEFERRED                — defer_queue enqueued a job
    WORK_REFUSED                 — admission gate refused a job
    WORK_FAILED                  — defer-queue exhausted retries
  Fleet / supervisor health (FS-P1.0+):
    FLEET_DEGRADED               — fleet_band crossed to warn/critical
    SUPERVISOR_HEARTBEAT_LOST    — verdict_band crossed to stale/dead
    SUPERVISOR_LEADER_CONFLICT   — two holders observed during election
    ROUTING_POLICY_DEGRADED      — routing fell back to local_only
    DEFER_QUEUE_OVERFLOW         — defer_queue depth ≥ cap

Each event maps to an NC category + severity via the small lookup
table below. Stage-2 NC will read these via its producer registry.

Discipline:
  * Best-effort writes. A Mongo blip on one destination does NOT block
    the other. Neither raises.
  * Forward-compat: writes carry `producer="factory_supervisor"` so
    the NC producer registry routes correctly when it ships.
  * No business logic. Callers compute the event and pass payload —
    the emitter only persists.

Public surface:
    ALL_EVENT_TYPES
    EVENT_CATEGORY_MAP
    EVENT_SEVERITY_MAP
    is_enabled()                         — mirrors ENABLE_FACTORY_SUPERVISOR
    notification_center_enabled()        — mirrors ENABLE_NOTIFICATION_CENTER
    emit(event_type, payload=None, severity=None, category=None,
         target_id=None, correlation_id=None) → dict
    list_events(limit=100, event_type=None, since_epoch=None) → list
    stats(window_sec=3600) → dict
    ensure_indexes() → dict       (notifications collection)
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

PRODUCER_NAME = "factory_supervisor"
NOTIFICATIONS_COLLECTION = "notifications"

# Operational
EVENT_WORK_ROUTED                = "WORK_ROUTED"
EVENT_WORK_DEFERRED              = "WORK_DEFERRED"
EVENT_WORK_REFUSED               = "WORK_REFUSED"
EVENT_WORK_REROUTED              = "WORK_REROUTED"   # FS-P1.1
EVENT_WORK_QUEUED                = "WORK_QUEUED"     # FS-P1.2
EVENT_WORK_RETRIED               = "WORK_RETRIED"    # FS-P1.2
EVENT_WORK_EXPIRED               = "WORK_EXPIRED"    # FS-P1.2
EVENT_WORK_COMPLETED             = "WORK_COMPLETED"  # FS-P1.2
EVENT_WORK_FAILED                = "WORK_FAILED"
# Fleet / supervisor
EVENT_FLEET_DEGRADED             = "FLEET_DEGRADED"
EVENT_SUPERVISOR_HEARTBEAT_LOST  = "SUPERVISOR_HEARTBEAT_LOST"
EVENT_SUPERVISOR_LEADER_CONFLICT = "SUPERVISOR_LEADER_CONFLICT"
EVENT_ROUTING_POLICY_DEGRADED    = "ROUTING_POLICY_DEGRADED"
EVENT_DEFER_QUEUE_OVERFLOW       = "DEFER_QUEUE_OVERFLOW"

ALL_EVENT_TYPES: Tuple[str, ...] = (
    EVENT_WORK_ROUTED,
    EVENT_WORK_DEFERRED,
    EVENT_WORK_REFUSED,
    EVENT_WORK_REROUTED,
    EVENT_WORK_QUEUED,
    EVENT_WORK_RETRIED,
    EVENT_WORK_EXPIRED,
    EVENT_WORK_COMPLETED,
    EVENT_WORK_FAILED,
    EVENT_FLEET_DEGRADED,
    EVENT_SUPERVISOR_HEARTBEAT_LOST,
    EVENT_SUPERVISOR_LEADER_CONFLICT,
    EVENT_ROUTING_POLICY_DEGRADED,
    EVENT_DEFER_QUEUE_OVERFLOW,
)

# 5-level severity vocabulary (operator-locked):
#   debug / info / warn / critical / fatal
EVENT_SEVERITY_MAP: Dict[str, str] = {
    EVENT_WORK_ROUTED:                "info",
    EVENT_WORK_DEFERRED:              "info",
    EVENT_WORK_REFUSED:               "warn",
    EVENT_WORK_REROUTED:              "info",
    EVENT_WORK_QUEUED:                "info",
    EVENT_WORK_RETRIED:               "info",
    EVENT_WORK_EXPIRED:               "warn",
    EVENT_WORK_COMPLETED:             "info",
    EVENT_WORK_FAILED:                "critical",
    EVENT_FLEET_DEGRADED:             "warn",
    EVENT_SUPERVISOR_HEARTBEAT_LOST:  "critical",
    EVENT_SUPERVISOR_LEADER_CONFLICT: "critical",
    EVENT_ROUTING_POLICY_DEGRADED:    "warn",
    EVENT_DEFER_QUEUE_OVERFLOW:       "warn",
}

# 12-category taxonomy (matches NOTIFICATION_CENTER_ARCHITECTURE.md §7).
EVENT_CATEGORY_MAP: Dict[str, str] = {
    EVENT_WORK_ROUTED:                "scaling",
    EVENT_WORK_DEFERRED:              "scaling",
    EVENT_WORK_REFUSED:               "scaling",
    EVENT_WORK_REROUTED:              "scaling",
    EVENT_WORK_QUEUED:                "scaling",
    EVENT_WORK_RETRIED:               "scaling",
    EVENT_WORK_EXPIRED:               "scaling",
    EVENT_WORK_COMPLETED:             "scaling",
    EVENT_WORK_FAILED:                "scaling",
    EVENT_FLEET_DEGRADED:             "compute_health",
    EVENT_SUPERVISOR_HEARTBEAT_LOST:  "supervisor",
    EVENT_SUPERVISOR_LEADER_CONFLICT: "supervisor",
    EVENT_ROUTING_POLICY_DEGRADED:    "supervisor",
    EVENT_DEFER_QUEUE_OVERFLOW:       "supervisor",
}


def is_enabled() -> bool:
    """Master switch: ENABLE_FACTORY_SUPERVISOR."""
    try:
        from engines.feature_flags import flag
        return bool(flag("ENABLE_FACTORY_SUPERVISOR"))
    except KeyError:
        return False
    except Exception:                                          # pragma: no cover
        return False


def notification_center_enabled() -> bool:
    """Secondary switch — only when supervisor is on AND NC is on."""
    if not is_enabled():
        return False
    try:
        from engines.feature_flags import flag
        return bool(flag("ENABLE_NOTIFICATION_CENTER"))
    except KeyError:
        return False
    except Exception:                                          # pragma: no cover
        return False


def _now() -> Dict[str, Any]:
    dt = datetime.now(timezone.utc)
    return {"iso": dt.isoformat(), "epoch": dt.timestamp()}


def _host_id() -> str:
    try:
        from engines import host_capability
        caps = host_capability.current()
        if caps is not None:
            return caps.host_id
    except Exception:                                          # pragma: no cover
        pass
    return os.environ.get("HOSTNAME", "unknown")


async def emit(
    event_type:     str,
    payload:        Optional[Dict[str, Any]] = None,
    severity:       Optional[str] = None,
    category:       Optional[str] = None,
    target_id:      Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist one supervisor event.

    Writes to:
      * `scaling_events`  (via engines.scaling_events.emit — P1.D)
      * `notifications`   (direct write; gated by ENABLE_NOTIFICATION_CENTER)

    Returns a structured outcome:
        {
          "emitted":           bool,         # at least one write succeeded
          "scaling_events_ok": bool,
          "notifications_ok":  bool,
          "id":                "<uuid>",
          "skipped":           "flag_off" | "unknown_type" | None,
          "event_type":        str,
          "severity":          str,
          "category":          str,
        }
    """
    out: Dict[str, Any] = {
        "emitted":           False,
        "scaling_events_ok": False,
        "notifications_ok":  False,
        "id":                None,
        "skipped":           None,
        "event_type":        event_type,
        "severity":          severity,
        "category":          category,
    }
    if not is_enabled():
        out["skipped"] = "flag_off"
        return out
    if event_type not in ALL_EVENT_TYPES:
        logger.warning("[supervisor_events] unknown event_type=%r", event_type)
        # Forward-compat: continue with provided severity/category if given.
        sev = severity or "info"
        cat = category or "supervisor"
    else:
        sev = severity or EVENT_SEVERITY_MAP[event_type]
        cat = category or EVENT_CATEGORY_MAP[event_type]
    out["severity"] = sev
    out["category"] = cat

    times = _now()
    uid   = str(uuid.uuid4())
    out["id"] = uid

    base_payload = dict(payload or {})

    # ── (1) Write to scaling_events (legacy unified P1.D stream) ──
    # Note: scaling_events.is_enabled() checks ENABLE_ADMISSION_CONTROL.
    # The supervisor's own events are not gated by admission flag; we
    # write a parallel "supervisor-tagged" row directly to the same
    # collection through a thin reuse of the existing emitter's primitive.
    try:
        from engines.db import get_db
        from engines.scaling_events import EVENTS_COLLECTION
        db = get_db()
        se_doc = {
            **base_payload,
            "event_type":   event_type,
            "host_id":      _host_id(),
            "ts":           times["iso"],
            "ts_epoch":     times["epoch"],
            "producer":     PRODUCER_NAME,
            "severity":     sev,
            "category":     cat,
            "target_id":    target_id,
            "correlation_id": correlation_id,
            "supervisor_event_id": uid,
        }
        await db[EVENTS_COLLECTION].insert_one(se_doc)
        out["scaling_events_ok"] = True
    except Exception as e:                                     # pragma: no cover
        logger.debug("[supervisor_events] scaling_events write failed: %s", e)

    # ── (2) Write to notifications (NC storage, gated) ──
    if notification_center_enabled():
        try:
            from engines.db import get_db
            db = get_db()
            n_doc: Dict[str, Any] = {
                "id":             uid,
                "ts":             times["iso"],
                "ts_epoch":       times["epoch"],
                "host_id":        _host_id(),
                "event_type":     event_type,
                "producer":       PRODUCER_NAME,
                "category":       cat,
                "severity":       sev,
                "status":         "new",
                "title":          _title_for(event_type, base_payload),
                "message":        _message_for(event_type, base_payload),
                "payload":        base_payload,
                "target_id":      target_id,
                "correlation_id": correlation_id,
                "suggested_action": _suggested_action(event_type),
                "acked_by":       None,
                "acked_at":       None,
            }
            await db[NOTIFICATIONS_COLLECTION].insert_one(n_doc)
            out["notifications_ok"] = True
        except Exception as e:                                 # pragma: no cover
            logger.debug("[supervisor_events] notifications write failed: %s", e)

    out["emitted"] = out["scaling_events_ok"] or out["notifications_ok"]
    return out


def _title_for(event_type: str, payload: Dict[str, Any]) -> str:
    tag = payload.get("class_") or payload.get("host_id") or ""
    if tag:
        return f"{event_type} · {tag}"
    return event_type


def _message_for(event_type: str, payload: Dict[str, Any]) -> str:
    reason = payload.get("reason")
    if reason:
        return f"{event_type}: {reason}"
    return f"{event_type} (no detail)"


def _suggested_action(event_type: str) -> Optional[str]:
    table = {
        EVENT_WORK_REFUSED:               "Inspect host band and queue depth; consider reducing submission rate.",
        EVENT_WORK_FAILED:                "Review defer_queue exhausted rows; verify routing policy.",
        EVENT_FLEET_DEGRADED:             "Check compute headroom on degraded hosts.",
        EVENT_SUPERVISOR_HEARTBEAT_LOST:  "Verify supervisord status of the leader host.",
        EVENT_SUPERVISOR_LEADER_CONFLICT: "Force-release the lock via /api/factory-supervisor/lock/release.",
        EVENT_DEFER_QUEUE_OVERFLOW:       "Raise FS_DEFER_QUEUE_MAX_DEPTH or reduce inflow.",
        EVENT_ROUTING_POLICY_DEGRADED:    "Inspect FS_ROUTING_POLICY env; revert to local_only if needed.",
    }
    return table.get(event_type)


async def list_events(
    limit:        int           = 100,
    event_type:   Optional[str] = None,
    since_epoch:  Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Read recent supervisor events from scaling_events (filtered to
    producer='factory_supervisor')."""
    limit = max(1, min(int(limit), 1000))
    q: Dict[str, Any] = {"producer": PRODUCER_NAME}
    if event_type:
        q["event_type"] = event_type
    if since_epoch is not None:
        q["ts_epoch"] = {"$gte": float(since_epoch)}
    try:
        from engines.db import get_db
        from engines.scaling_events import EVENTS_COLLECTION
        db = get_db()
        cur = (
            db[EVENTS_COLLECTION]
            .find(q, {"_id": 0})
            .sort("ts_epoch", -1)
            .limit(limit)
        )
        return [d async for d in cur]
    except Exception as e:                                     # pragma: no cover
        logger.debug("[supervisor_events] list_events failed: %s", e)
        return []


async def stats(window_sec: int = 3600) -> Dict[str, Any]:
    """Per-event-type counts within the last window. Best-effort."""
    window_sec = max(1, min(int(window_sec), 86400 * 30))
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=window_sec)).timestamp()
    per_type = {t: 0 for t in ALL_EVENT_TYPES}
    total = 0
    try:
        from engines.db import get_db
        from engines.scaling_events import EVENTS_COLLECTION
        db = get_db()
        pipeline = [
            {"$match": {"producer": PRODUCER_NAME, "ts_epoch": {"$gte": cutoff}}},
            {"$group": {"_id": "$event_type", "n": {"$sum": 1}}},
        ]
        async for row in db[EVENTS_COLLECTION].aggregate(pipeline):
            t = row["_id"]
            n = int(row["n"])
            per_type.setdefault(t, 0)
            per_type[t] += n
            total += n
    except Exception as e:                                     # pragma: no cover
        logger.debug("[supervisor_events] stats failed: %s", e)
    return {"window_sec": window_sec, "total": total, "per_type": per_type}


async def ensure_indexes() -> Dict[str, Any]:
    """Idempotent index creation for the `notifications` collection.

    Mirrors NOTIFICATION_CENTER_ARCHITECTURE.md §5 index spec so the NC
    Phase 1 implementation in FS-P1.3 only has to extend, never recreate.
    """
    created, existed, errors = [], [], []
    try:
        from engines.db import get_db
        from pymongo import ASCENDING, DESCENDING
        db = get_db()
        existing = await db[NOTIFICATIONS_COLLECTION].index_information()
        specs = [
            ("ix_notifications_ts",
             [("ts_epoch", DESCENDING)]),
            ("ix_notifications_severity_ts",
             [("severity", ASCENDING), ("ts_epoch", DESCENDING)]),
            ("ix_notifications_category_ts",
             [("category", ASCENDING), ("ts_epoch", DESCENDING)]),
            ("ix_notifications_status_ts",
             [("status", ASCENDING), ("ts_epoch", DESCENDING)]),
            ("ix_notifications_target_ts",
             [("target_id", ASCENDING), ("ts_epoch", DESCENDING)]),
        ]
        for name, keys in specs:
            if name in existing:
                existed.append(name)
                continue
            await db[NOTIFICATIONS_COLLECTION].create_index(keys, name=name, background=True)
            created.append(name)
    except Exception as e:                                     # pragma: no cover
        errors.append({"error": str(e)[:200]})
        logger.warning("[supervisor_events] ensure_indexes (notifications) failed: %s", e)
    return {"created": created, "existed": existed, "errors": errors}
