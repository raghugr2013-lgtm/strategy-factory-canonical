"""
VPS Scaling P1.D — Internal event emitter (storage only).

Captures scaling-relevant events to a Mongo `scaling_events` collection
so the future Notification Center can consume them. P1.D itself does
NOT raise alerts, route events, or render anything — the operator's
explicit requirement was "store them only".

Event types emitted by P1.D:
  * HIGH_QUEUE_PRESSURE   — pressure_band transitions to high/critical
  * WORKER_SATURATION     — worker_utilization >= 0.90 sustained
  * ADMISSION_DEFERRAL    — gate() returned `defer`
  * ADMISSION_REFUSED     — gate() returned `refuse`
  * CAPACITY_WARNING      — probe band warn/critical observed by gate

Discipline:
  * Best-effort writes. Mongo unreachable → log + drop (never raises).
  * Idempotent indexes (created once at startup via ensure_indexes()).
  * No DB read fan-out in the emitter — `emit()` is a single write.
  * No env mutation. No I/O beyond the Mongo write.
  * Dormant by default — emission is wrapped in `is_enabled()`, which
    follows `ENABLE_ADMISSION_CONTROL` (the master P1.C/P1.D switch).
    With the flag OFF the emitter is a no-op.

Public API:
    emit(event_type, payload)            — best-effort persist
    list_events(limit=100, since_ts=...) — paged read (admin diag)
    stats(window_sec=3600)               — per-type counters
    ensure_indexes()                     — idempotent index creation
    is_enabled()                         — mirror of admission flag
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

EVENTS_COLLECTION = "scaling_events"

# Canonical event types — the future Notification Center vocabulary.
EVENT_HIGH_QUEUE_PRESSURE = "HIGH_QUEUE_PRESSURE"
EVENT_WORKER_SATURATION   = "WORKER_SATURATION"
EVENT_ADMISSION_DEFERRAL  = "ADMISSION_DEFERRAL"
EVENT_ADMISSION_REFUSED   = "ADMISSION_REFUSED"
EVENT_CAPACITY_WARNING    = "CAPACITY_WARNING"

ALL_EVENT_TYPES = (
    EVENT_HIGH_QUEUE_PRESSURE,
    EVENT_WORKER_SATURATION,
    EVENT_ADMISSION_DEFERRAL,
    EVENT_ADMISSION_REFUSED,
    EVENT_CAPACITY_WARNING,
)


def is_enabled() -> bool:
    """Emitter is gated by the master P1.C/P1.D admission flag.

    Flag OFF → emit() is a no-op (returns False). This keeps the
    `scaling_events` collection empty in the legacy world.
    """
    try:
        from engines.feature_flags import flag
        return bool(flag("ENABLE_ADMISSION_CONTROL"))
    except KeyError:
        return False
    except Exception:                                          # pragma: no cover
        return False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _host_id() -> str:
    try:
        from engines.host_capability import current as _current
        caps = _current()
        if caps is not None:
            return caps.host_id
    except Exception:                                          # pragma: no cover
        pass
    return os.environ.get("HOSTNAME", "unknown")


async def emit(event_type: str, payload: Optional[Dict[str, Any]] = None) -> bool:
    """Persist one event to Mongo. Best-effort.

    Args
    ----
    event_type : MUST be one of `ALL_EVENT_TYPES`. Unknown types are
                 still accepted (forward-compat) but logged.
    payload    : free-form dict — should include `class_`, `band`,
                 `pressure_band`, `reason`, `worker_utilization`, etc.
                 when known. The emitter does NOT enrich.

    Returns
    -------
    True iff the write reached Mongo. False on flag-off, validation
    rejection, or Mongo failure.
    """
    if not is_enabled():
        return False
    if not event_type or not isinstance(event_type, str):
        return False
    if event_type not in ALL_EVENT_TYPES:
        logger.warning("[scaling_events] unknown event_type=%r — accepted anyway", event_type)

    doc: Dict[str, Any] = dict(payload or {})
    doc["event_type"]   = event_type
    doc["host_id"]      = _host_id()
    doc["ts"]           = _now_iso()
    # Stamp a monotonically-sortable epoch float for window queries.
    doc["ts_epoch"]     = datetime.now(timezone.utc).timestamp()

    try:
        from engines.db import get_db
        db = get_db()
        await db[EVENTS_COLLECTION].insert_one(doc)
        return True
    except Exception as e:                                     # pragma: no cover
        logger.debug("[scaling_events] emit failed (%s): %s", event_type, e)
        return False


async def list_events(
    limit:       int                = 100,
    event_type:  Optional[str]      = None,
    since_epoch: Optional[float]    = None,
) -> List[Dict[str, Any]]:
    """Paged scan of recent events. Best-effort; returns [] on failure."""
    limit = max(1, min(int(limit), 1000))
    q: Dict[str, Any] = {}
    if event_type:
        q["event_type"] = event_type
    if since_epoch is not None:
        q["ts_epoch"] = {"$gte": float(since_epoch)}
    try:
        from engines.db import get_db
        db = get_db()
        cur = db[EVENTS_COLLECTION].find(q, {"_id": 0}).sort("ts_epoch", -1).limit(limit)
        return [d async for d in cur]
    except Exception as e:                                     # pragma: no cover
        logger.debug("[scaling_events] list_events failed: %s", e)
        return []


async def stats(window_sec: int = 3600) -> Dict[str, Any]:
    """Counts per event_type within the last `window_sec` seconds.

    Returns:
        {
          "window_sec": 3600,
          "total":      int,
          "per_type":   {"HIGH_QUEUE_PRESSURE": int, ...},
        }
    All counts default to 0 on failure or empty collection.
    """
    window_sec = max(1, min(int(window_sec), 86400 * 30))  # cap at 30 days
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=window_sec)).timestamp()
    per_type = {t: 0 for t in ALL_EVENT_TYPES}
    total = 0
    try:
        from engines.db import get_db
        db = get_db()
        pipeline = [
            {"$match": {"ts_epoch": {"$gte": cutoff}}},
            {"$group": {"_id": "$event_type", "n": {"$sum": 1}}},
        ]
        async for row in db[EVENTS_COLLECTION].aggregate(pipeline):
            t = row["_id"]
            n = int(row["n"])
            per_type.setdefault(t, 0)
            per_type[t] += n
            total += n
    except Exception as e:                                     # pragma: no cover
        logger.debug("[scaling_events] stats failed: %s", e)
    return {"window_sec": window_sec, "total": total, "per_type": per_type}


async def ensure_indexes() -> Dict[str, Any]:
    """Idempotent index creation. Never raises."""
    try:
        from engines.db import get_db
        from pymongo import ASCENDING, DESCENDING
        db = get_db()
        existing = await db[EVENTS_COLLECTION].index_information()
        created, existed = [], []
        if "ix_scaling_events_ts_epoch" not in existing:
            await db[EVENTS_COLLECTION].create_index(
                [("ts_epoch", DESCENDING)],
                name="ix_scaling_events_ts_epoch", background=True,
            )
            created.append("ix_scaling_events_ts_epoch")
        else:
            existed.append("ix_scaling_events_ts_epoch")
        if "ix_scaling_events_type_ts" not in existing:
            await db[EVENTS_COLLECTION].create_index(
                [("event_type", ASCENDING), ("ts_epoch", DESCENDING)],
                name="ix_scaling_events_type_ts", background=True,
            )
            created.append("ix_scaling_events_type_ts")
        else:
            existed.append("ix_scaling_events_type_ts")
        return {"created": created, "existed": existed, "errors": []}
    except Exception as e:                                     # pragma: no cover
        return {"created": [], "existed": [], "errors": [{"error": str(e)[:200]}]}
