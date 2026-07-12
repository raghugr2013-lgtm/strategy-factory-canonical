"""
Phase 2 scaffolding — Event continuation queue (DORMANT).

A Mongo-backed marker collection (``event_continuations``) that lets
future code persist "resume from this point after restart" markers. Used
later for mid-cycle continuation, replay resumption, and event-driven
orchestrator wakeups.

Discipline:
  * Dormant: ``ENABLE_EVENT_CONTINUATION=false`` (default) → all
    public APIs are no-ops (``enqueue`` returns False, ``pop_next``
    returns None). No collection is touched while disabled.
  * Reversible: collection is independent; dropping it is safe.
  * No reader is hooked in. Activation requires both env flag AND a
    future caller invoking ``pop_next()``.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db

logger = logging.getLogger(__name__)

COLLECTION = "event_continuations"


def is_enabled() -> bool:
    raw = (os.environ.get("ENABLE_EVENT_CONTINUATION") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def enqueue(
    event_type: str,
    *,
    payload: Optional[Dict[str, Any]] = None,
    priority: int = 0,
    dedupe_key: Optional[str] = None,
) -> Optional[str]:
    """Persist a continuation marker. Returns the event_id on success,
    None when the gate is closed or on any persistence error.

    Idempotency: when ``dedupe_key`` is supplied and a pending row with
    the same key exists, the existing row is returned unchanged.
    """
    if not is_enabled():
        return None
    try:
        db = get_db()
        if dedupe_key:
            existing = await db[COLLECTION].find_one(
                {"dedupe_key": dedupe_key, "status": "pending"},
                {"_id": 0, "event_id": 1},
            )
            if existing:
                return existing.get("event_id")
        now = _now()
        event_id = uuid.uuid4().hex[:16]
        await db[COLLECTION].insert_one({
            "event_id":   event_id,
            "event_type": str(event_type)[:80],
            "payload":    dict(payload or {}),
            "priority":   int(priority),
            "dedupe_key": str(dedupe_key)[:120] if dedupe_key else None,
            "status":     "pending",
            "enqueued_at": now.isoformat(),
            "enqueued_at_dt": now,
            "claimed_at":   None,
            "claimed_by":   None,
            "finished_at":  None,
            "finished_at_dt": None,
            "result":       None,
        })
        return event_id
    except Exception as e:                                   # pragma: no cover
        logger.debug("[event_continuation] enqueue failed: %s", e)
        return None


async def pop_next(*, claimer: str = "unknown") -> Optional[Dict[str, Any]]:
    """Atomically claim the highest-priority pending continuation.

    No-op (returns None) while the flag is OFF or no pending row exists.
    """
    if not is_enabled():
        return None
    try:
        doc = await get_db()[COLLECTION].find_one_and_update(
            {"status": "pending"},
            {
                "$set": {
                    "status":     "claimed",
                    "claimed_at": _now().isoformat(),
                    "claimed_by": str(claimer)[:60],
                },
            },
            sort=[("priority", -1), ("enqueued_at_dt", 1)],
            projection={"_id": 0},
            return_document=True,
        )
        return doc
    except Exception as e:                                   # pragma: no cover
        logger.debug("[event_continuation] pop_next failed: %s", e)
        return None


async def mark_finished(
    event_id: str, *, status: str = "completed",
    result: Optional[Dict[str, Any]] = None,
) -> bool:
    """Best-effort completion stamp. Never raises."""
    if not is_enabled() or not event_id:
        return False
    try:
        now = _now()
        await get_db()[COLLECTION].update_one(
            {"event_id": event_id},
            {"$set": {
                "status":         str(status)[:20],
                "finished_at":    now.isoformat(),
                "finished_at_dt": now,
                "result":         dict(result or {}),
            }},
        )
        return True
    except Exception as e:                                   # pragma: no cover
        logger.debug("[event_continuation] mark_finished failed: %s", e)
        return False


async def snapshot(limit: int = 100) -> Dict[str, Any]:
    """Read-only diagnostic surface."""
    pending: List[Dict[str, Any]] = []
    counts = {"pending": 0, "claimed": 0, "completed": 0, "failed": 0}
    try:
        db = get_db()
        for status in list(counts.keys()):
            counts[status] = await db[COLLECTION].count_documents({"status": status})
        cur = (
            db[COLLECTION]
            .find({"status": "pending"}, {"_id": 0})
            .sort([("priority", -1), ("enqueued_at_dt", 1)])
            .limit(int(limit))
        )
        async for d in cur:
            pending.append(d)
    except Exception as e:                                   # pragma: no cover
        logger.debug("[event_continuation] snapshot failed: %s", e)
    return {
        "enabled":     is_enabled(),
        "counts":      counts,
        "pending":     pending,
    }
