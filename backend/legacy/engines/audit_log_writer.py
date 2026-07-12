"""
Phase 2 P2.8.b — unified audit_log writer with TTL companion.

The existing `audit_log` collection has ~20 different writers scattered
across engines. They all write `{ts: <ISO string>, event: ..., ...}`
directly. Mongo's TTL index requires a BSON Date field, so the ISO
string can't be used to bound retention.

This helper writes `ts_dt` (BSON Date) alongside the existing `ts`
string so the TTL index on `audit_log.ts_dt` (90 day default, declared
in `db_indexes.TTL_SPECS`) can reap old rows from any writer that
adopts this helper.

The helper is OPT-IN — existing writers keep working unchanged. New
writers should call `write_event(...)` instead of `db.audit_log.insert_one(...)`.

Discipline:
    * Best-effort persistence (NEVER raise — audit logs are
      diagnostic, not source-of-truth).
    * Retention TTL is read from feature_flags `AUDIT_LOG_RETENTION_DAYS`
      at index-creation time only (db_indexes); not re-read per write.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from engines.db import get_db

logger = logging.getLogger(__name__)

AUDIT_COLL = "audit_log"


async def write_event(
    event: str,
    *,
    phase: str = "",
    **fields: Any,
) -> bool:
    """Write a single audit-log row with both `ts` and `ts_dt`.

    Returns True on success, False on any persistence failure (and
    logs the failure). Never raises.

    Caller MUST pass JSON-serialisable values in `**fields` — this
    helper does not attempt sanitisation beyond the timestamp pair.
    """
    now = datetime.now(timezone.utc)
    doc: Dict[str, Any] = {
        "ts":     now.isoformat(),
        "ts_dt":  now,
        "event":  str(event)[:200],
    }
    if phase:
        doc["phase"] = str(phase)[:60]
    # Caller fields take precedence (e.g. an event might already set
    # phase= or include nested payloads); BUT we always own ts/ts_dt
    # to keep TTL reaping deterministic.
    doc.update({k: v for k, v in fields.items() if k not in ("ts", "ts_dt")})

    try:
        await get_db()[AUDIT_COLL].insert_one({**doc})
        return True
    except Exception as e:                                  # pragma: no cover
        logger.debug("[audit_log_writer] write_event failed: %s", e)
        return False


async def write_factory_runner_event(event: str, **fields: Any) -> bool:
    """Sugar for factory_runner emissions. Mirrors the existing
    `factory_runner._audit(...)` shape so a one-line swap is safe."""
    return await write_event(
        f"factory_runner:{event}",
        phase="D.1",
        **fields,
    )
