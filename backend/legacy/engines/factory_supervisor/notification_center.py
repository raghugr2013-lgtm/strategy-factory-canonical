"""
Factory Supervisor FS-P1.3 — Notification Center read API + acknowledge.

The `notifications` collection is written to by `supervisor_events.emit()`
(gated by `ENABLE_FACTORY_SUPERVISOR` + `ENABLE_NOTIFICATION_CENTER`).
This module is the READ surface — exposed via the Architect Dashboard,
the future Copilot, and any operator integration.

Operator-mandated capabilities:
  * unread count
  * acknowledge (admin or owning user)
  * severity filters     (debug / info / warn / critical / fatal)
  * category filters     (scaling / supervisor / compute_health / ...)
  * notification history (paged, time-sorted)
  * recommendation       (suggested_action carried over from emit)
  * deployment           (event_type prefix WORK_*, FLEET_*, ...)
  * scaling              (event category)
  * system health        (event severity / category)

Discipline:
  * Read-only by default. `acknowledge()` is the ONLY mutator; it sets
    `status="ack"`, `acked_by`, `acked_at`. Idempotent.
  * Best-effort. Mongo blips never raise.
  * Provider-neutral. No LLM / no transport call.
  * Default OFF for write semantics: when ENABLE_NOTIFICATION_CENTER
    is OFF the underlying collection is empty; the read API still
    works and returns `[]` + 0 counts.

Public surface:
    NOTIFICATIONS_COLLECTION
    STATUS_NEW / STATUS_ACK / STATUS_ARCHIVED
    ALL_STATUSES
    is_enabled()
    list_notifications(limit, severity=None, category=None, status=None,
                       event_type=None, since_epoch=None) → list
    get_notification(notification_id)                     → dict | None
    unread_count(severity=None, category=None)            → int
    stats(window_sec=3600)                                → dict
    acknowledge(notification_ids: List[str], user)        → dict
    archive(notification_ids: List[str], user)            → dict
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from engines.factory_supervisor import supervisor_events

logger = logging.getLogger(__name__)

NOTIFICATIONS_COLLECTION = supervisor_events.NOTIFICATIONS_COLLECTION

STATUS_NEW      = "new"
STATUS_ACK      = "ack"
STATUS_ARCHIVED = "archived"
ALL_STATUSES: Tuple[str, ...] = (STATUS_NEW, STATUS_ACK, STATUS_ARCHIVED)

SEVERITY_RANK = {"debug": 0, "info": 1, "warn": 2, "critical": 3, "fatal": 4}


def is_enabled() -> bool:
    """Mirrors `supervisor_events.notification_center_enabled()` — i.e.
    Factory Supervisor + NC both ON. When False, the collection is
    empty; the read API still works and returns []."""
    return supervisor_events.notification_center_enabled()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_epoch() -> float:
    return datetime.now(timezone.utc).timestamp()


# ─── Read API ───────────────────────────────────────────────────────


async def list_notifications(
    limit: int = 100,
    severity: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    event_type: Optional[str] = None,
    since_epoch: Optional[float] = None,
    target_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Read recent notifications, filtered by the operator-mandated
    facets. Time-sorted desc (newest first). Best-effort."""
    limit = max(1, min(int(limit), 1000))
    q: Dict[str, Any] = {}
    if severity:
        q["severity"] = severity
    if category:
        q["category"] = category
    if status:
        q["status"] = status
    if event_type:
        q["event_type"] = event_type
    if since_epoch is not None:
        q["ts_epoch"] = {"$gte": float(since_epoch)}
    if target_id:
        q["target_id"] = target_id
    if correlation_id:
        q["correlation_id"] = correlation_id
    try:
        from engines.db import get_db
        db = get_db()
        cur = (
            db[NOTIFICATIONS_COLLECTION]
            .find(q, {"_id": 0})
            .sort("ts_epoch", -1)
            .limit(limit)
        )
        return [d async for d in cur]
    except Exception as e:                                       # pragma: no cover
        logger.debug("[notification_center] list_notifications failed: %s", e)
        return []


async def get_notification(notification_id: str) -> Optional[Dict[str, Any]]:
    """Single-row read by `id` field. Returns None if not present."""
    try:
        from engines.db import get_db
        db = get_db()
        row = await db[NOTIFICATIONS_COLLECTION].find_one(
            {"id": str(notification_id)}, {"_id": 0},
        )
        return row
    except Exception as e:                                       # pragma: no cover
        logger.debug("[notification_center] get_notification failed: %s", e)
        return None


async def unread_count(
    severity: Optional[str] = None,
    category: Optional[str] = None,
) -> int:
    """Count notifications with `status="new"`. Optional severity /
    category filter for badge-with-priority UX."""
    q: Dict[str, Any] = {"status": STATUS_NEW}
    if severity:
        q["severity"] = severity
    if category:
        q["category"] = category
    try:
        from engines.db import get_db
        db = get_db()
        return int(await db[NOTIFICATIONS_COLLECTION].count_documents(q))
    except Exception as e:                                       # pragma: no cover
        logger.debug("[notification_center] unread_count failed: %s", e)
        return 0


async def stats(window_sec: int = 3600) -> Dict[str, Any]:
    """Per-severity, per-category, per-status counts within the window."""
    window_sec = max(1, min(int(window_sec), 86400 * 30))
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=window_sec)).timestamp()
    per_severity: Dict[str, int] = {}
    per_category: Dict[str, int] = {}
    per_status:   Dict[str, int] = {s: 0 for s in ALL_STATUSES}
    total = 0
    try:
        from engines.db import get_db
        db = get_db()
        pipeline = [
            {"$match": {"ts_epoch": {"$gte": cutoff}}},
            {"$group": {
                "_id": {
                    "severity": "$severity",
                    "category": "$category",
                    "status":   "$status",
                },
                "n": {"$sum": 1},
            }},
        ]
        async for row in db[NOTIFICATIONS_COLLECTION].aggregate(pipeline):
            _id = row.get("_id") or {}
            n = int(row["n"])
            sev = _id.get("severity") or "info"
            cat = _id.get("category") or "supervisor"
            sts = _id.get("status")   or STATUS_NEW
            per_severity[sev] = per_severity.get(sev, 0) + n
            per_category[cat] = per_category.get(cat, 0) + n
            per_status.setdefault(sts, 0)
            per_status[sts] += n
            total += n
    except Exception as e:                                       # pragma: no cover
        logger.debug("[notification_center] stats failed: %s", e)
    return {
        "window_sec":   window_sec,
        "total":        total,
        "per_severity": per_severity,
        "per_category": per_category,
        "per_status":   per_status,
    }


# ─── Mutation: acknowledge / archive (admin-gated at the API layer) ──


async def acknowledge(
    notification_ids: List[str],
    user: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Mark notifications as acknowledged. Idempotent."""
    ids = [str(x) for x in (notification_ids or []) if x]
    if not ids:
        return {"matched": 0, "modified": 0, "acked_ids": []}
    actor = (user or {}).get("email") or (user or {}).get("user_id") or "operator"
    try:
        from engines.db import get_db
        db = get_db()
        res = await db[NOTIFICATIONS_COLLECTION].update_many(
            {"id": {"$in": ids}, "status": {"$ne": STATUS_ARCHIVED}},
            {"$set": {
                "status":   STATUS_ACK,
                "acked_by": actor,
                "acked_at": _now_iso(),
                "acked_at_epoch": _now_epoch(),
            }},
        )
        return {
            "matched":   int(res.matched_count),
            "modified":  int(res.modified_count),
            "acked_ids": ids,
            "acked_by":  actor,
        }
    except Exception as e:                                       # pragma: no cover
        logger.debug("[notification_center] acknowledge failed: %s", e)
        return {"matched": 0, "modified": 0, "acked_ids": [], "error": str(e)[:200]}


async def archive(
    notification_ids: List[str],
    user: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Mark notifications as archived (operator hides them from default
    views). Idempotent."""
    ids = [str(x) for x in (notification_ids or []) if x]
    if not ids:
        return {"matched": 0, "modified": 0, "archived_ids": []}
    actor = (user or {}).get("email") or (user or {}).get("user_id") or "operator"
    try:
        from engines.db import get_db
        db = get_db()
        res = await db[NOTIFICATIONS_COLLECTION].update_many(
            {"id": {"$in": ids}},
            {"$set": {
                "status":      STATUS_ARCHIVED,
                "archived_by": actor,
                "archived_at": _now_iso(),
            }},
        )
        return {
            "matched":      int(res.matched_count),
            "modified":     int(res.modified_count),
            "archived_ids": ids,
            "archived_by":  actor,
        }
    except Exception as e:                                       # pragma: no cover
        logger.debug("[notification_center] archive failed: %s", e)
        return {"matched": 0, "modified": 0, "archived_ids": [], "error": str(e)[:200]}
