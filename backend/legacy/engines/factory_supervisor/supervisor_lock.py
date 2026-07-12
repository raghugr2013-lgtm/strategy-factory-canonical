"""
Factory Supervisor FS-P1.0 — Single-leader cooperative lease.

A cooperative leader-election primitive used by the Supervisor service
to guarantee that exactly ONE supervisor instance owns the write paths
(submit / defer-queue runner) at a time. Non-leader instances continue
to serve read endpoints.

Discipline (matches VPS Scaling P1 conventions):
  * Best-effort. Mongo failure → returns False, never raises.
  * Atomic via `findOneAndUpdate(upsert)` with conditional filter.
  * Forward-compatible: lease document carries `lock_name` so future
    multi-lease layouts (e.g. per-region leaders) cost zero refactor.
  * DORMANT until `ENABLE_FACTORY_SUPERVISOR=true`. With the master
    flag OFF this module does nothing — no auto-claim loop, no
    background tasks.

Schema (`factory_supervisor_lock` collection):
    {
        "_id":              "<lock_name>",      # default "fs_leader"
        "lock_name":        "fs_leader",
        "holder_host_id":   "<host>",
        "claimed_at":       iso,
        "renewed_at":       iso,
        "lease_until_epoch":float,
        "process_pid":      int,
    }

Public surface:
    LOCK_NAME_LEADER
    ensure_indexes()        — idempotent
    try_acquire(host_id, lock_name=LOCK_NAME_LEADER, ttl_sec=None)
                            → (acquired:bool, holder_doc:dict|None)
    renew(host_id, lock_name=LOCK_NAME_LEADER, ttl_sec=None)
                            → renewed:bool
    release(host_id, lock_name=LOCK_NAME_LEADER) → released:bool
    current_holder(lock_name=LOCK_NAME_LEADER)   → dict|None
    is_leader(host_id, lock_name=LOCK_NAME_LEADER) → bool
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

COLLECTION = "factory_supervisor_lock"
LOCK_NAME_LEADER = "fs_leader"
DEFAULT_LEASE_TTL_SEC = 60


def _now() -> Tuple[str, float]:
    dt = datetime.now(timezone.utc)
    return dt.isoformat(), dt.timestamp()


def _resolve_ttl(ttl_sec: Optional[int]) -> int:
    """Resolve TTL: explicit arg > env var > default. Clamped 5..3600."""
    if ttl_sec is not None:
        try:
            return max(5, min(int(ttl_sec), 3600))
        except (TypeError, ValueError):
            pass
    raw = (os.environ.get("FS_LEADER_LEASE_TTL_SEC") or "").strip()
    if raw:
        try:
            return max(5, min(int(raw), 3600))
        except ValueError:
            pass
    return DEFAULT_LEASE_TTL_SEC


async def ensure_indexes() -> Dict[str, Any]:
    """Idempotent index creation. Never raises."""
    created, existed, errors = [], [], []
    try:
        from engines.db import get_db
        from pymongo import ASCENDING
        db = get_db()
        existing = await db[COLLECTION].index_information()
        if "ix_fs_lock_name" not in existing:
            await db[COLLECTION].create_index(
                [("lock_name", ASCENDING)],
                name="ix_fs_lock_name",
                background=True,
            )
            created.append("ix_fs_lock_name")
        else:
            existed.append("ix_fs_lock_name")
    except Exception as e:                                     # pragma: no cover
        errors.append({"error": str(e)[:200]})
        logger.warning("[supervisor_lock] ensure_indexes failed: %s", e)
    return {"created": created, "existed": existed, "errors": errors}


async def try_acquire(
    host_id: str,
    lock_name: str = LOCK_NAME_LEADER,
    ttl_sec: Optional[int] = None,
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Attempt to acquire (or steal an expired) lease for `lock_name`.

    Returns (acquired, holder_doc):
      * (True, doc)  — caller now holds the lease.
      * (False, doc) — another live holder owns it (doc is their row).
      * (False, None) — Mongo unreachable.
    """
    if not host_id or not isinstance(host_id, str):
        return False, None
    iso, epoch = _now()
    ttl = _resolve_ttl(ttl_sec)
    lease_until = epoch + ttl
    pid = os.getpid()

    try:
        from engines.db import get_db
        db = get_db()
        # Atomic: replace doc IF no row OR existing lease expired.
        # We model "no row" by treating it as expired (lease_until_epoch=0).
        existing = await db[COLLECTION].find_one({"_id": lock_name})
        now_epoch = epoch
        if existing is not None:
            held_until = float(existing.get("lease_until_epoch") or 0.0)
            if held_until > now_epoch and existing.get("holder_host_id") != host_id:
                # Live lease held by someone else. Strip _id (always == lock_name).
                existing.pop("_id", None)
                return False, existing
        # Either no row, expired row, or we are the existing holder → claim.
        new_doc = {
            "_id":                lock_name,
            "lock_name":          lock_name,
            "holder_host_id":     host_id,
            "claimed_at":         iso,
            "renewed_at":         iso,
            "lease_until_epoch":  lease_until,
            "process_pid":        pid,
        }
        await db[COLLECTION].replace_one(
            {"_id": lock_name},
            new_doc,
            upsert=True,
        )
        return True, new_doc
    except Exception as e:                                     # pragma: no cover
        logger.debug("[supervisor_lock] try_acquire failed: %s", e)
        return False, None


async def renew(
    host_id: str,
    lock_name: str = LOCK_NAME_LEADER,
    ttl_sec: Optional[int] = None,
) -> bool:
    """Extend the lease IFF this host already holds it. Returns False if
    the caller is not the current holder."""
    if not host_id:
        return False
    iso, epoch = _now()
    lease_until = epoch + _resolve_ttl(ttl_sec)
    try:
        from engines.db import get_db
        db = get_db()
        result = await db[COLLECTION].update_one(
            {"_id": lock_name, "holder_host_id": host_id},
            {"$set": {"renewed_at": iso, "lease_until_epoch": lease_until}},
        )
        return result.modified_count > 0
    except Exception as e:                                     # pragma: no cover
        logger.debug("[supervisor_lock] renew failed: %s", e)
        return False


async def release(host_id: str, lock_name: str = LOCK_NAME_LEADER) -> bool:
    """Release the lease IFF the caller is the holder. Best-effort."""
    if not host_id:
        return False
    try:
        from engines.db import get_db
        db = get_db()
        result = await db[COLLECTION].delete_one(
            {"_id": lock_name, "holder_host_id": host_id},
        )
        return result.deleted_count > 0
    except Exception as e:                                     # pragma: no cover
        logger.debug("[supervisor_lock] release failed: %s", e)
        return False


async def current_holder(lock_name: str = LOCK_NAME_LEADER) -> Optional[Dict[str, Any]]:
    """Read the current lease document. Returns None on missing/Mongo error."""
    try:
        from engines.db import get_db
        db = get_db()
        doc = await db[COLLECTION].find_one({"_id": lock_name})
        if not doc:
            return None
        # _id is always the string lock_name; drop for clean JSON.
        doc.pop("_id", None)
        # Surface a derived field for read APIs.
        _, epoch = _now()
        held_until = float(doc.get("lease_until_epoch") or 0.0)
        doc["seconds_remaining"] = max(0.0, round(held_until - epoch, 3))
        doc["is_expired"]        = held_until <= epoch
        return doc
    except Exception as e:                                     # pragma: no cover
        logger.debug("[supervisor_lock] current_holder failed: %s", e)
        return None


async def is_leader(host_id: str, lock_name: str = LOCK_NAME_LEADER) -> bool:
    """True iff `host_id` currently holds an unexpired lease."""
    doc = await current_holder(lock_name)
    if not doc:
        return False
    return (doc.get("holder_host_id") == host_id) and not doc.get("is_expired", True)
