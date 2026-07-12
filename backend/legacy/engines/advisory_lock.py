"""
Mongo-backed advisory lock (additive, Phase 2 P2.7).

Cross-worker mutual exclusion for single-flight operations that are
guarded today only by in-process `asyncio.Lock`. When uvicorn runs
with --workers >= 2, in-process locks no longer guarantee mutual
exclusion across workers; this advisory lock gives true cross-process
single-flight.

Design:
  * One singleton document per logical lock key in the `advisory_locks`
    collection. Document `_id = lock_key`. Existence == held.
  * Acquisition is `find_one_and_update(..., upsert=True)`. If the doc
    already exists AND its `expires_at_dt` is in the future, the
    caller did NOT acquire and gets a `LockHeldError`.
  * Stale-lock recovery: if `expires_at_dt < now`, the existing doc is
    overwritten (caller acquires). Prevents a crashed worker from
    permanently holding the lock.
  * Release is best-effort `delete_one`. Crashed callers self-heal
    via the TTL above (default 1 hour).

This is OPT-IN: existing in-process locks remain. Call sites add the
advisory lock as an OUTER guard alongside their existing asyncio.Lock.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from engines.db import get_db

logger = logging.getLogger(__name__)

ADVISORY_LOCKS_COLL = "advisory_locks"


class LockHeldError(RuntimeError):
    """Raised when a non-blocking acquire attempt finds the lock held."""

    def __init__(self, key: str, holder: Optional[Dict[str, Any]] = None):
        self.key = key
        self.holder = holder or {}
        super().__init__(f"advisory lock '{key}' is held by {self.holder}")


async def try_acquire(
    key: str,
    *,
    holder_pid: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
    ttl_seconds: int = 3600,
) -> Dict[str, Any]:
    """Try to acquire the lock. Returns the acquisition record on success.

    Raises `LockHeldError` if held and not expired.

    The TTL is a SAFETY NET for crashed workers, not the primary
    release path. Callers MUST call `release(key)` in a try/finally.
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    pid = holder_pid if holder_pid is not None else os.getpid()
    expires_at = now + timedelta(seconds=int(ttl_seconds))

    # Atomic compare-and-set: insert if absent, replace if expired.
    new_doc = {
        "_id":           key,
        "holder_pid":    pid,
        "acquired_at":   now.isoformat(),
        "acquired_at_dt": now,
        "expires_at_dt": expires_at,
        "metadata":      metadata or {},
    }

    try:
        # Step 1: if expired holder exists, evict it first.
        await db[ADVISORY_LOCKS_COLL].delete_one({
            "_id": key,
            "expires_at_dt": {"$lt": now},
        })
        # Step 2: atomic insert. Duplicate-key error if held.
        await db[ADVISORY_LOCKS_COLL].insert_one(new_doc)
        return new_doc
    except Exception as e:
        # Duplicate-key = held
        existing = await db[ADVISORY_LOCKS_COLL].find_one({"_id": key})
        if existing is not None:
            existing.pop("_id", None)
            raise LockHeldError(key, existing) from e
        # Unknown error (network etc.) — re-raise as-is
        logger.warning("[advisory_lock] acquire failed for %s: %s", key, e)
        raise


async def release(key: str, *, holder_pid: Optional[int] = None) -> bool:
    """Release the lock. Only succeeds if WE held it (PID match).

    Returns True if a doc was deleted. False otherwise (lock not held,
    or held by a different PID — which means our acquisition was lost
    to a TTL expiry and another worker has it now).

    Never raises; release is best-effort by design.
    """
    pid = holder_pid if holder_pid is not None else os.getpid()
    db = get_db()
    try:
        result = await db[ADVISORY_LOCKS_COLL].delete_one({"_id": key, "holder_pid": pid})
        return result.deleted_count > 0
    except Exception as e:
        logger.warning("[advisory_lock] release failed for %s: %s", key, e)
        return False


async def peek(key: str) -> Optional[Dict[str, Any]]:
    """Read-only lookup of who currently holds the lock (or None)."""
    db = get_db()
    try:
        doc = await db[ADVISORY_LOCKS_COLL].find_one({"_id": key})
        return doc
    except Exception:
        return None
