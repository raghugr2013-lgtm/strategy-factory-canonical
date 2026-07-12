"""
Phase 2 scaffolding — Cadence-aware scheduling primitive (DORMANT).

A *pure* per-cell cadence gate: given a (pair, timeframe, style), return
True iff enough wall-clock time has passed since the last recorded run.
Mongo-backed so cadence survives backend restart.

Discipline:
  * Dormant: ``ENABLE_CADENCE_SCHEDULER=false`` (default) → every call to
    ``should_run_cell`` returns True. No behavior change.
  * Reversible: never modifies any existing collection; uses its own
    ``cadence_state`` collection.
  * Opt-in: no caller imports this module yet. Activation requires both
    the env flag AND a future code change at the call-site.
  * Observable: ``snapshot()`` returns full state for diagnostic surfaces.

Activation contract (when wired in S4):
    >>> if cadence_scheduler.should_run_cell(pair, tf, style):
    ...     await mcr.start_multi_cycle(scan=[(pair, tf)], style=style, ...)
    ...     await cadence_scheduler.mark_ran(pair, tf, style)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from engines.db import get_db

logger = logging.getLogger(__name__)

COLLECTION = "cadence_state"


def is_enabled() -> bool:
    raw = (os.environ.get("ENABLE_CADENCE_SCHEDULER") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def min_gap_minutes() -> int:
    try:
        n = int(os.environ.get("CADENCE_MIN_GAP_MIN") or 60)
    except (TypeError, ValueError):
        n = 60
    return max(1, min(n, 1440))


def _key(pair: str, tf: str, style: str = "") -> str:
    p = str(pair or "").upper().strip()
    t = str(tf or "").upper().strip()
    s = str(style or "").lower().strip()
    return f"{p}|{t}|{s}"


async def should_run_cell(pair: str, tf: str, style: str = "") -> bool:
    """Return True iff this cell may be run right now.

    When flag OFF → always True (no behavior change).
    When flag ON  → True iff ``now - last_ran ≥ CADENCE_MIN_GAP_MIN``.
    Returns True on any error (fail-open; cadence must never block discovery).
    """
    if not is_enabled():
        return True
    try:
        db = get_db()
        doc = await db[COLLECTION].find_one(
            {"_id": _key(pair, tf, style)},
            {"_id": 0, "last_ran_at_dt": 1},
        )
        if not doc:
            return True
        last = doc.get("last_ran_at_dt")
        if not isinstance(last, datetime):
            return True
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        gap_min = (datetime.now(timezone.utc) - last).total_seconds() / 60.0
        return gap_min >= float(min_gap_minutes())
    except Exception as e:                                   # pragma: no cover
        logger.debug("[cadence_scheduler] should_run_cell failed: %s", e)
        return True


async def mark_ran(pair: str, tf: str, style: str = "") -> bool:
    """Stamp ``last_ran_at_dt`` for this cell. Best-effort; never raises."""
    try:
        now = datetime.now(timezone.utc)
        await get_db()[COLLECTION].update_one(
            {"_id": _key(pair, tf, style)},
            {
                "$set": {
                    "pair":            str(pair or "").upper(),
                    "timeframe":       str(tf or "").upper(),
                    "style":           str(style or "").lower(),
                    "last_ran_at":     now.isoformat(),
                    "last_ran_at_dt":  now,
                },
                "$inc": {"runs": 1},
            },
            upsert=True,
        )
        return True
    except Exception as e:                                   # pragma: no cover
        logger.debug("[cadence_scheduler] mark_ran failed: %s", e)
        return False


async def snapshot(limit: int = 100) -> Dict[str, Any]:
    """Read-only diagnostic snapshot — all cell cadence rows."""
    rows: List[Dict[str, Any]] = []
    try:
        cur = get_db()[COLLECTION].find({}, {"_id": 0}).limit(int(limit))
        async for d in cur:
            rows.append(d)
    except Exception as e:                                   # pragma: no cover
        logger.debug("[cadence_scheduler] snapshot failed: %s", e)
    return {
        "enabled":         is_enabled(),
        "min_gap_minutes": min_gap_minutes(),
        "cell_count":      len(rows),
        "cells":           rows,
    }
