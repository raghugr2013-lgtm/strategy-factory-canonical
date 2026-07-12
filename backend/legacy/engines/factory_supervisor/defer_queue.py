"""
Factory Supervisor FS-P1.2 — Defer queue.

Operator directive: the defer queue is the **single source of truth**
for postponed workloads. Every deferred row carries:

    original submission envelope
    defer_reason
    defer_ts
    retry_count
    next_eligible_retry_epoch
    workload_class
    routing_rationale     (from DispatchVerdict.rationale.routing)
    admission_rationale   (from DispatchVerdict.rationale.admission)
    status                queued | claimed | retrying | completed | failed | expired
    claimed_by_worker_id  populated when a worker pulls the row
    claimed_at_epoch
    last_attempt_epoch
    last_outcome          last DispatchVerdict.outcome on retry
    last_block_reason     last DispatchVerdict.reason  (Copilot read)
    history               append-only list of {attempt, outcome, reason, ts}
    workload_id           uuid (matches the originating Workload)
    correlation_id        chains origin
    source_module         caller id (preserved for Copilot)

Discipline:
  * **Default OFF.** `FS_ENABLE_DEFER_QUEUE=false` ⇒ enqueue() returns
    `enqueued=False` skipped="flag_off"; legacy callers unaffected.
  * **Atomic claim.** `claim_due()` uses `find_one_and_update` with
    `status="queued"` filter + `now >= next_eligible_retry_epoch`,
    setting `status="claimed"` + `claimed_by_worker_id` + `claimed_at_epoch`.
    Two concurrent workers cannot claim the same row.
  * **Exponential backoff.** `delay = base * 2^retry_count` clamped to
    `FS_DEFER_RETRY_MAX_SEC`. After `FS_DEFER_MAX_RETRIES` attempts,
    the row is marked `status="failed"` + WORK_FAILED event.
  * **TTL expiry.** Rows whose `defer_ts_epoch < now - FS_DEFER_TTL_SEC`
    become `status="expired"` + WORK_EXPIRED event.
  * **Best-effort persistence.** Mongo blips never raise; emit() failures
    never raise. Queue degradation is observable via stats() and a future
    DEFER_QUEUE_OVERFLOW event (already in the event vocabulary).

Public surface:
    DEFER_COLLECTION
    STATUS_QUEUED / CLAIMED / RETRYING / COMPLETED / FAILED / EXPIRED
    ALL_STATUSES
    is_enabled()
    ensure_indexes()
    enqueue(workload_dict, verdict_dict)        → {enqueued, row?, reason?}
    claim_due(worker_id, batch=8)               → list[row]
    mark_retry(row_id, verdict_dict)            → bool
    mark_completed(row_id, detail=None)         → bool
    mark_failed(row_id, reason, detail=None)    → bool
    mark_expired(row_id)                        → bool
    cancel(row_id)                              → bool   (admin)
    list_rows(...)                              → list
    get_row(row_id)                             → dict | None
    stats(window_sec=3600)                      → dict
    expire_overdue()                            → int
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.factory_supervisor import supervisor_events

logger = logging.getLogger(__name__)

DEFER_COLLECTION = "factory_supervisor_defer_queue"

STATUS_QUEUED    = "queued"
STATUS_CLAIMED   = "claimed"
STATUS_RETRYING  = "retrying"
STATUS_COMPLETED = "completed"
STATUS_FAILED    = "failed"
STATUS_EXPIRED   = "expired"

ALL_STATUSES = (
    STATUS_QUEUED, STATUS_CLAIMED, STATUS_RETRYING,
    STATUS_COMPLETED, STATUS_FAILED, STATUS_EXPIRED,
)

# Reasonable hard ceilings (never raise; clamp instead).
_RETRY_BASE_MIN, _RETRY_BASE_MAX = 1, 3600
_RETRY_MAX_MIN, _RETRY_MAX_MAX   = 1, 86400
_MAX_RETRIES_MIN, _MAX_RETRIES_MAX = 0, 50
_TTL_MIN, _TTL_MAX               = 60, 86400 * 30


# ─── Flag helpers ───────────────────────────────────────────────────

def is_enabled() -> bool:
    """Master flag (queue) — requires ENABLE_FACTORY_SUPERVISOR too."""
    try:
        from engines.feature_flags import flag
        return bool(flag("ENABLE_FACTORY_SUPERVISOR")) and bool(flag("FS_ENABLE_DEFER_QUEUE"))
    except Exception:                                          # pragma: no cover
        return False


def _flag_int(name: str, default: int, lo: int, hi: int) -> int:
    try:
        from engines.feature_flags import flag
        v = int(flag(name) or default)
    except Exception:                                          # pragma: no cover
        v = default
    return max(lo, min(hi, v))


def _retry_base_sec() -> int:
    return _flag_int("FS_DEFER_RETRY_BASE_SEC", 30, _RETRY_BASE_MIN, _RETRY_BASE_MAX)


def _retry_max_sec() -> int:
    return _flag_int("FS_DEFER_RETRY_MAX_SEC", 1800, _RETRY_MAX_MIN, _RETRY_MAX_MAX)


def _max_retries() -> int:
    return _flag_int("FS_DEFER_MAX_RETRIES", 8, _MAX_RETRIES_MIN, _MAX_RETRIES_MAX)


def _ttl_sec() -> int:
    return _flag_int("FS_DEFER_TTL_SEC", 86400, _TTL_MIN, _TTL_MAX)


def compute_next_retry_epoch(retry_count: int, base_ts_epoch: float) -> float:
    base = _retry_base_sec()
    cap  = _retry_max_sec()
    rc   = max(0, min(int(retry_count), 30))   # 2^30 prevented
    delay = min(cap, base * (2 ** rc))
    return float(base_ts_epoch) + float(delay)


# ─── Indexes ─────────────────────────────────────────────────────────

async def ensure_indexes() -> Dict[str, Any]:
    """Idempotent indexes for the defer queue."""
    created, existed, errors = [], [], []
    try:
        from engines.db import get_db
        from pymongo import ASCENDING, DESCENDING
        db = get_db()
        existing = await db[DEFER_COLLECTION].index_information()
        specs = [
            ("ix_fs_defer_status_next",
             [("status", ASCENDING), ("next_eligible_retry_epoch", ASCENDING)]),
            ("ix_fs_defer_ts",
             [("defer_ts_epoch", DESCENDING)]),
            ("ix_fs_defer_workload_id",
             [("workload_id", ASCENDING)]),
            ("ix_fs_defer_correlation",
             [("correlation_id", ASCENDING)]),
            ("ix_fs_defer_class_status",
             [("workload_class", ASCENDING), ("status", ASCENDING)]),
            ("ix_fs_defer_worker_status",
             [("claimed_by_worker_id", ASCENDING), ("status", ASCENDING)]),
        ]
        for name, keys in specs:
            if name in existing:
                existed.append(name)
                continue
            await db[DEFER_COLLECTION].create_index(keys, name=name, background=True)
            created.append(name)
    except Exception as e:                                     # pragma: no cover
        errors.append({"error": str(e)[:200]})
        logger.warning("[defer_queue] ensure_indexes failed: %s", e)
    return {"created": created, "existed": existed, "errors": errors}


# ─── Enqueue ────────────────────────────────────────────────────────

async def enqueue(workload_dict: Dict[str, Any],
                  verdict_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Persist one deferred submission into the queue. Best-effort.

    The caller (submission_dispatcher) decides WHEN to call this —
    today only when verdict.outcome == 'deferred'. The function does
    NOT raise. Returns a small status dict the caller can attach to
    its verdict for observability.
    """
    if not is_enabled():
        return {"enqueued": False, "skipped": "flag_off"}
    try:
        from engines.db import get_db
        db = get_db()
        now = datetime.now(timezone.utc)
        row_id = str(uuid.uuid4())
        rationale = (verdict_dict or {}).get("rationale") or {}
        doc: Dict[str, Any] = {
            "row_id":                       row_id,
            "workload_id":                  workload_dict.get("workload_id"),
            "workload_class":               workload_dict.get("workload_class"),
            "source_module":                workload_dict.get("source_module"),
            "correlation_id":               workload_dict.get("correlation_id"),
            "priority":                     workload_dict.get("priority", 0),
            "original_envelope":            dict(workload_dict or {}),
            "original_verdict":             dict(verdict_dict or {}),
            "defer_reason":                 verdict_dict.get("reason") or verdict_dict.get("admission_reason"),
            "defer_ts":                     now.isoformat(),
            "defer_ts_epoch":               now.timestamp(),
            "routing_rationale":            rationale.get("routing"),
            "admission_rationale":          rationale.get("admission"),
            "retry_count":                  0,
            "next_eligible_retry_epoch":    compute_next_retry_epoch(0, now.timestamp()),
            "status":                       STATUS_QUEUED,
            "claimed_by_worker_id":         None,
            "claimed_at_epoch":             None,
            "last_attempt_epoch":           None,
            "last_outcome":                 None,
            "last_block_reason":            verdict_dict.get("reason"),
            "history":                      [],
            "supervisor_version":           "FS-P1.2",
        }
        await db[DEFER_COLLECTION].insert_one(doc)
        # Strip _id for response symmetry with reads.
        doc.pop("_id", None)
        # Best-effort WORK_QUEUED event.
        try:
            await supervisor_events.emit(
                supervisor_events.EVENT_WORK_QUEUED,
                payload={
                    "row_id":         row_id,
                    "workload_id":    doc["workload_id"],
                    "workload_class": doc["workload_class"],
                    "source_module":  doc["source_module"],
                    "defer_reason":   doc["defer_reason"],
                    "next_retry_epoch": doc["next_eligible_retry_epoch"],
                },
                target_id=doc.get("workload_id"),
                correlation_id=doc.get("correlation_id"),
            )
        except Exception as e:                                 # pragma: no cover
            logger.debug("[defer_queue] WORK_QUEUED emit failed: %s", e)
        return {"enqueued": True, "row": doc, "row_id": row_id}
    except Exception as e:                                     # pragma: no cover
        logger.warning("[defer_queue] enqueue failed: %s", e)
        return {"enqueued": False, "error": str(e)[:200]}


# ─── Claim / mark / cancel ──────────────────────────────────────────

async def claim_due(worker_id: str, batch: int = 8) -> List[Dict[str, Any]]:
    """Atomically claim up to `batch` due rows.

    Idempotent w.r.t. concurrent workers: each `find_one_and_update`
    sets `status='claimed'` so the next worker pass cannot select it.
    """
    out: List[Dict[str, Any]] = []
    if not is_enabled():
        return out
    batch = max(1, min(int(batch), 64))
    try:
        from engines.db import get_db
        db = get_db()
        now = datetime.now(timezone.utc)
        now_e = now.timestamp()
        for _ in range(batch):
            doc = await db[DEFER_COLLECTION].find_one_and_update(
                {
                    "status": STATUS_QUEUED,
                    "next_eligible_retry_epoch": {"$lte": now_e},
                },
                {
                    "$set": {
                        "status": STATUS_CLAIMED,
                        "claimed_by_worker_id": worker_id,
                        "claimed_at_epoch":     now_e,
                    },
                },
                sort=[("next_eligible_retry_epoch", 1), ("defer_ts_epoch", 1)],
                return_document=True,    # ReturnDocument.AFTER
                projection={"_id": 0},
            )
            if not doc:
                break
            out.append(doc)
    except Exception as e:                                     # pragma: no cover
        logger.debug("[defer_queue] claim_due failed: %s", e)
    return out


async def mark_retry(row_id: str, verdict_dict: Dict[str, Any]) -> bool:
    """Record a retry attempt that did not yet land final outcome."""
    if not is_enabled():
        return False
    try:
        from engines.db import get_db
        db = get_db()
        row = await db[DEFER_COLLECTION].find_one({"row_id": row_id}, {"_id": 0})
        if not row:
            return False
        rc = int(row.get("retry_count", 0)) + 1
        max_r = _max_retries()
        now = datetime.now(timezone.utc)
        history_entry = {
            "attempt":    rc,
            "outcome":    (verdict_dict or {}).get("outcome"),
            "reason":     (verdict_dict or {}).get("reason"),
            "ts":         now.isoformat(),
        }
        # Final-failure branch: too many retries
        if rc > max_r:
            await db[DEFER_COLLECTION].update_one(
                {"row_id": row_id},
                {
                    "$set": {
                        "status":              STATUS_FAILED,
                        "last_attempt_epoch":  now.timestamp(),
                        "last_outcome":        history_entry["outcome"],
                        "last_block_reason":   history_entry["reason"] or "max_retries_exceeded",
                        "retry_count":         rc,
                        "claimed_by_worker_id": None,
                    },
                    "$push": {"history": history_entry},
                },
            )
            try:
                await supervisor_events.emit(
                    supervisor_events.EVENT_WORK_FAILED,
                    payload={"row_id": row_id, "reason": "max_retries_exceeded",
                             "retry_count": rc},
                    target_id=row.get("workload_id"),
                    correlation_id=row.get("correlation_id"),
                )
            except Exception:                                  # pragma: no cover
                pass
            return True
        # Continue retrying: schedule next eligibility, release the claim.
        next_e = compute_next_retry_epoch(rc, now.timestamp())
        await db[DEFER_COLLECTION].update_one(
            {"row_id": row_id},
            {
                "$set": {
                    "status":                   STATUS_QUEUED,
                    "retry_count":              rc,
                    "next_eligible_retry_epoch": next_e,
                    "last_attempt_epoch":       now.timestamp(),
                    "last_outcome":             history_entry["outcome"],
                    "last_block_reason":        history_entry["reason"],
                    "claimed_by_worker_id":     None,
                    "claimed_at_epoch":         None,
                },
                "$push": {"history": history_entry},
            },
        )
        try:
            await supervisor_events.emit(
                supervisor_events.EVENT_WORK_RETRIED,
                payload={"row_id": row_id, "retry_count": rc,
                         "next_retry_epoch": next_e,
                         "last_block_reason": history_entry["reason"]},
                target_id=row.get("workload_id"),
                correlation_id=row.get("correlation_id"),
            )
        except Exception:                                      # pragma: no cover
            pass
        return True
    except Exception as e:                                     # pragma: no cover
        logger.debug("[defer_queue] mark_retry failed: %s", e)
        return False


async def _terminal_mark(row_id: str, status: str, event_type: str,
                         reason: Optional[str] = None,
                         detail: Optional[Dict[str, Any]] = None) -> bool:
    if not is_enabled():
        return False
    try:
        from engines.db import get_db
        db = get_db()
        row = await db[DEFER_COLLECTION].find_one({"row_id": row_id}, {"_id": 0})
        if not row:
            return False
        now = datetime.now(timezone.utc)
        update: Dict[str, Any] = {
            "status":              status,
            "last_attempt_epoch":  now.timestamp(),
            "claimed_by_worker_id": None,
        }
        if reason:
            update["last_block_reason"] = reason
        await db[DEFER_COLLECTION].update_one(
            {"row_id": row_id},
            {
                "$set":  update,
                "$push": {"history": {
                    "attempt": int(row.get("retry_count", 0)) + 1,
                    "outcome": status,
                    "reason":  reason,
                    "detail":  dict(detail or {}),
                    "ts":      now.isoformat(),
                }},
            },
        )
        try:
            await supervisor_events.emit(
                event_type,
                payload={"row_id": row_id, "reason": reason,
                         "detail": dict(detail or {})},
                target_id=row.get("workload_id"),
                correlation_id=row.get("correlation_id"),
            )
        except Exception:                                      # pragma: no cover
            pass
        return True
    except Exception as e:                                     # pragma: no cover
        logger.debug("[defer_queue] terminal mark %s failed: %s", status, e)
        return False


async def mark_completed(row_id: str, detail: Optional[Dict[str, Any]] = None) -> bool:
    return await _terminal_mark(
        row_id, STATUS_COMPLETED, supervisor_events.EVENT_WORK_COMPLETED,
        reason="completed", detail=detail,
    )


async def mark_failed(row_id: str, reason: str,
                      detail: Optional[Dict[str, Any]] = None) -> bool:
    return await _terminal_mark(
        row_id, STATUS_FAILED, supervisor_events.EVENT_WORK_FAILED,
        reason=reason, detail=detail,
    )


async def mark_expired(row_id: str) -> bool:
    return await _terminal_mark(
        row_id, STATUS_EXPIRED, supervisor_events.EVENT_WORK_EXPIRED,
        reason="ttl_expired",
    )


async def cancel(row_id: str) -> bool:
    """Operator cancel — marks the row failed with reason='cancelled'."""
    return await mark_failed(row_id, reason="cancelled")


async def expire_overdue() -> int:
    """Mark all queued rows older than FS_DEFER_TTL_SEC as expired."""
    if not is_enabled():
        return 0
    try:
        from engines.db import get_db
        db = get_db()
        cutoff = datetime.now(timezone.utc).timestamp() - _ttl_sec()
        cur = db[DEFER_COLLECTION].find(
            {"status": {"$in": [STATUS_QUEUED, STATUS_CLAIMED]},
             "defer_ts_epoch": {"$lt": cutoff}},
            {"_id": 0, "row_id": 1},
        )
        n = 0
        async for r in cur:
            if await mark_expired(r["row_id"]):
                n += 1
        return n
    except Exception as e:                                     # pragma: no cover
        logger.debug("[defer_queue] expire_overdue failed: %s", e)
        return 0


# ─── Read helpers ────────────────────────────────────────────────────

async def list_rows(
    limit:           int           = 100,
    status:          Optional[str] = None,
    workload_class:  Optional[str] = None,
    correlation_id:  Optional[str] = None,
    since_epoch:     Optional[float] = None,
) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 1000))
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    if workload_class:
        q["workload_class"] = workload_class
    if correlation_id:
        q["correlation_id"] = correlation_id
    if since_epoch is not None:
        q["defer_ts_epoch"] = {"$gte": float(since_epoch)}
    try:
        from engines.db import get_db
        db = get_db()
        cur = db[DEFER_COLLECTION].find(q, {"_id": 0}).sort("defer_ts_epoch", -1).limit(limit)
        return [d async for d in cur]
    except Exception as e:                                     # pragma: no cover
        logger.debug("[defer_queue] list_rows failed: %s", e)
        return []


async def get_row(row_id: str) -> Optional[Dict[str, Any]]:
    try:
        from engines.db import get_db
        db = get_db()
        return await db[DEFER_COLLECTION].find_one({"row_id": row_id}, {"_id": 0})
    except Exception as e:                                     # pragma: no cover
        logger.debug("[defer_queue] get_row failed: %s", e)
        return None


async def stats(window_sec: int = 3600) -> Dict[str, Any]:
    window_sec = max(1, min(int(window_sec), 86400 * 30))
    per_status = {s: 0 for s in ALL_STATUSES}
    total = 0
    try:
        from engines.db import get_db
        db = get_db()
        cutoff = datetime.now(timezone.utc).timestamp() - window_sec
        pipeline = [
            {"$match": {"defer_ts_epoch": {"$gte": cutoff}}},
            {"$group": {"_id": "$status", "n": {"$sum": 1}}},
        ]
        async for row in db[DEFER_COLLECTION].aggregate(pipeline):
            s = row["_id"] or "unknown"
            per_status[s] = int(row["n"])
            total += int(row["n"])
    except Exception as e:                                     # pragma: no cover
        logger.debug("[defer_queue] stats failed: %s", e)
    return {
        "window_sec": window_sec,
        "total":      total,
        "per_status": per_status,
        "limits": {
            "retry_base_sec": _retry_base_sec(),
            "retry_max_sec":  _retry_max_sec(),
            "max_retries":    _max_retries(),
            "ttl_sec":        _ttl_sec(),
        },
    }
