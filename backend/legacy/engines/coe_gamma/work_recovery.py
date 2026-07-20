"""Phase 2 Stage 4 P4B.3 — Work recovery on process restart.

On backend start-up, sweep `workload_events` for rows with
`status="in_flight"` older than `STALE_INFLIGHT_S` (default 300s).
Each stale row is either:
  * Re-queued (if retry budget remains) via the injected requeue hook.
  * Dead-lettered (if retry budget exhausted).

Feature flag: `COE_WORK_RECOVERY_ENABLED` (default OFF). When off,
`sweep()` returns `{"status": "flag_off"}` immediately — no reads,
no writes.

Idempotent: safe to run on every boot.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def is_work_recovery_enabled() -> bool:
    return _flag("COE_WORK_RECOVERY_ENABLED", False)


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name) or default)
    except (TypeError, ValueError):
        return default


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


WORKLOAD_EVENTS_COLLECTION = "workload_events"


class WorkRecovery:
    """Sweeps stale in-flight workload rows on start-up.

    Args:
        db_getter: DB getter for `workload_events`.
        requeue_hook: `(row) → awaitable[bool]` — returns True iff the
            row still has retry budget and was re-queued.
        dead_letter_hook: `(row) → awaitable[None]` — dead-letter
            the exhausted row.
    """

    def __init__(
        self,
        *,
        db_getter=None,
        requeue_hook:      Optional[Callable[[Dict[str, Any]], Awaitable[bool]]] = None,
        dead_letter_hook:  Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> None:
        self._db_getter = db_getter
        self._requeue = requeue_hook
        self._dead_letter = dead_letter_hook

    def _db(self):
        if self._db_getter is not None:
            return self._db_getter()
        try:                                                    # pragma: no cover
            from engines.db import get_db
            return get_db()
        except Exception:                                       # pragma: no cover
            return None

    async def sweep(self, *, stale_after_s: Optional[int] = None) -> Dict[str, Any]:
        if not is_work_recovery_enabled():
            return {"status": "flag_off"}
        db = self._db()
        if db is None:
            return {"status": "error", "reason": "db_unavailable"}
        cutoff_s = int(stale_after_s if stale_after_s is not None
                       else _int_env("STALE_INFLIGHT_S", 300))
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=cutoff_s)
        cutoff_iso = cutoff.isoformat()

        found = requeued = dead_lettered = errored = 0
        try:
            cur = db[WORKLOAD_EVENTS_COLLECTION].find({
                "status":       "in_flight",
                "started_at":   {"$lt": cutoff_iso},
            })
            async for row in cur:
                found += 1
                try:
                    handled = False
                    if self._requeue is not None:
                        handled = bool(await self._requeue(row))
                    if handled:
                        requeued += 1
                    elif self._dead_letter is not None:
                        await self._dead_letter(row)
                        dead_lettered += 1
                except Exception as e:                          # noqa: BLE001
                    logger.debug("[coe_gamma.work_recovery] row handler failed: %s", e)
                    errored += 1
        except Exception as e:                                 # noqa: BLE001
            logger.warning("[coe_gamma.work_recovery] sweep failed: %s", e)
            return {"status": "error", "reason": str(e)[:120]}

        return {
            "status":         "swept",
            "cutoff_iso":     cutoff_iso,
            "found":          found,
            "requeued":       requeued,
            "dead_lettered":  dead_lettered,
            "errored":        errored,
            "processed_at":   _now_iso(),
        }
