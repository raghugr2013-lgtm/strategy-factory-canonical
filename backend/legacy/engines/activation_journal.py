"""
Phase 1+2 scaffolding — Activation Journal (writer + reader).

A dedicated Mongo collection (`activation_journal`) that captures one
durable row per operator-driven institutional event (flag flip, universe
edit, manual override, scheduled drill, etc.). Each row carries the
LIVE `safe_to_widen` verdict at the exact moment of the event, so the
forensic trail records not just WHAT changed but WHAT THE ADVISOR SAID
right beforehand.

Discipline:
  * Writer is OPT-IN. No existing call-site invokes `journal_event()`
    today — adoption happens later, when admin-driven mutation
    endpoints are introduced.
  * The READER (`list_events`) is always callable; until the writer is
    wired, reads return an empty list (no synthetic data, no
    fabrication).
  * Every row is APPEND-ONLY. The collection has no update path
    exposed from this module.
  * Best-effort persistence — journal failures NEVER raise out to the
    triggering caller. The journal is observability, not control flow.
  * Indexed via `engines.db_indexes` (added in the index sweep below
    once the operator wires the writer); for now Mongo lazy-creates
    on first insert.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db

logger = logging.getLogger(__name__)

COLLECTION = "activation_journal"

DEFAULT_LIMIT = 50
MAX_LIMIT = 500


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


async def journal_event(
    event_type: str,
    *,
    actor: str,
    summary: str,
    payload: Optional[Dict[str, Any]] = None,
    include_safe_to_widen: bool = True,
    include_governance: bool = True,
) -> Optional[str]:
    """Append one event row to the activation journal.

    Args
    ----
    event_type : free-text tag (e.g. "flag_flip", "universe_edit",
                  "manual_override", "scheduler_start").
    actor      : email / role identifier of the operator (e.g.
                  "admin@local.test", "factory_runner", "system").
    summary    : human-readable one-line description.
    payload    : optional structured payload describing the action
                  (the new flag value, the universe diff, etc.).

    Returns the new `event_id` on success, None on any persistence
    failure. NEVER raises.
    """
    try:
        now = _now()
        event_id = uuid.uuid4().hex[:16]

        live_safe_to_widen: Optional[Dict[str, Any]] = None
        if include_safe_to_widen:
            try:
                from engines import safe_to_widen
                live_safe_to_widen = await safe_to_widen.evaluate()
            except Exception:                                # pragma: no cover
                live_safe_to_widen = None

        live_governance: Optional[Dict[str, Any]] = None
        if include_governance:
            try:
                from engines import activation_governance
                live_governance = await activation_governance.collect()
            except Exception:                                # pragma: no cover
                live_governance = None

        doc: Dict[str, Any] = {
            "event_id":   event_id,
            "ts":         now.isoformat(),
            "ts_dt":      now,
            "event_type": str(event_type)[:80],
            "actor":      str(actor)[:120],
            "summary":    str(summary)[:1000],
            "payload":    dict(payload or {}),
            "process_pid": os.getpid(),
            # Forensic snapshots captured at write-time so future audits
            # do not need to re-derive them.
            "safe_to_widen_at_event": live_safe_to_widen,
            "governance_at_event":    live_governance,
            "phase": "scaffolding-1",
        }

        await get_db()[COLLECTION].insert_one(doc)
        return event_id
    except Exception as e:                                  # pragma: no cover
        logger.debug("[activation_journal] journal_event failed: %s", e)
        return None


async def list_events(
    *,
    limit: int = DEFAULT_LIMIT,
    since: Optional[datetime] = None,
    event_type: Optional[str] = None,
    actor: Optional[str] = None,
    include_snapshots: bool = False,
) -> Dict[str, Any]:
    """Read-only chronological listing of journal entries.

    `include_snapshots=False` (default) projects out the bulky
    safe_to_widen / governance snapshots to keep responses small.
    Pass `include_snapshots=True` for forensic deep-dives.
    """
    limit = max(1, min(int(limit), MAX_LIMIT))
    query: Dict[str, Any] = {}
    if since is not None:
        query["ts_dt"] = {"$gte": since}
    if event_type:
        query["event_type"] = str(event_type)[:80]
    if actor:
        query["actor"] = str(actor)[:120]

    projection: Dict[str, int] = {
        "_id": 0, "event_id": 1, "ts": 1, "event_type": 1,
        "actor": 1, "summary": 1, "payload": 1, "process_pid": 1,
        "phase": 1,
    }
    if include_snapshots:
        projection["safe_to_widen_at_event"] = 1
        projection["governance_at_event"]    = 1

    rows: List[Dict[str, Any]] = []
    try:
        cur = (
            get_db()[COLLECTION]
            .find(query, projection)
            .sort("ts_dt", -1)
            .limit(limit)
        )
        async for d in cur:
            rows.append(d)
    except Exception as e:                                   # pragma: no cover
        logger.debug("[activation_journal] list_events failed: %s", e)

    return {
        "ts":                _now_iso(),
        "read_only":         True,
        "governance_authority": False,
        "operator_authority": "final",
        "filters": {
            "limit":             limit,
            "since":             since.isoformat() if since else None,
            "event_type":        event_type,
            "actor":             actor,
            "include_snapshots": bool(include_snapshots),
        },
        "events_count":      len(rows),
        "events":            rows,
        "adoption_note": (
            "Adoption is OPT-IN. Until admin endpoints invoke "
            "`journal_event(...)`, this collection remains empty."
        ),
    }
