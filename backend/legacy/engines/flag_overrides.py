"""
Phase 2 scaffolding — Mongo-backed flag override map (RECORD-OF-INTENT).

A dedicated Mongo collection (``flag_overrides``) that records operator-
declared flag intentions WITHOUT mutating runtime behaviour. Until a
future adoption pass migrates engines to consult this map, the existing
``feature_flags.<flag>()`` accessors continue to read from
``os.environ`` exclusively — meaning calling ``set_override(...)`` here
records the intent, journals it, and proposes a value, but does NOT
change anything the engines see at runtime.

Why this shape:
  * Records institutional intent before activation.
  * Surfaces the audit trail of "what the operator intended at time T"
    independently of when (or whether) the engines later honour it.
  * Avoids the "uncontrolled activation" failure mode that a runtime
    ``os.environ`` mutation would create — the engines still read the
    deployed environment.

Discipline:
  * APPEND-ONLY in intent (a "set" is a new history row + an idempotent
    upsert of the current value).
  * NEVER raises — flag-overrides are diagnostic, not source-of-truth.
  * Idempotent: setting an override to its current value is a no-op
    that returns ``changed=False``.
  * Read-only API for non-admin users; only the
    ``api.admin.flag_governance`` endpoint may invoke ``set_override``.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db

logger = logging.getLogger(__name__)

OVERRIDES_COLLECTION = "flag_overrides"
HISTORY_COLLECTION   = "flag_override_history"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_value(value: Any) -> Any:
    """Best-effort coerce to a JSON-serialisable scalar."""
    if isinstance(value, (bool, int, float, str)) or value is None:
        return value
    try:
        return str(value)
    except Exception:                                       # pragma: no cover
        return None


async def get_override(flag_name: str) -> Optional[Dict[str, Any]]:
    """Return the current override doc for `flag_name` or None."""
    try:
        return await get_db()[OVERRIDES_COLLECTION].find_one(
            {"_id": str(flag_name)},
            {"_id": 0, "flag_name": 1, "value": 1, "set_by": 1,
             "set_at": 1, "rationale": 1, "safe_to_widen_at_set": 1},
        )
    except Exception as e:                                  # pragma: no cover
        logger.debug("[flag_overrides] get_override failed: %s", e)
        return None


async def list_overrides() -> List[Dict[str, Any]]:
    """Return all current overrides."""
    rows: List[Dict[str, Any]] = []
    try:
        cur = get_db()[OVERRIDES_COLLECTION].find(
            {},
            {"_id": 0, "flag_name": 1, "value": 1, "set_by": 1,
             "set_at": 1, "rationale": 1},
        ).sort("set_at_dt", -1)
        async for d in cur:
            rows.append(d)
    except Exception as e:                                  # pragma: no cover
        logger.debug("[flag_overrides] list_overrides failed: %s", e)
    return rows


async def history(
    flag_name: Optional[str] = None, *, limit: int = 50,
) -> List[Dict[str, Any]]:
    """Append-only history of every flag-override event."""
    limit = max(1, min(int(limit), 500))
    query: Dict[str, Any] = {}
    if flag_name:
        query["flag_name"] = str(flag_name)
    rows: List[Dict[str, Any]] = []
    try:
        cur = get_db()[HISTORY_COLLECTION].find(query, {"_id": 0}).sort("ts_dt", -1).limit(limit)
        async for d in cur:
            rows.append(d)
    except Exception as e:                                  # pragma: no cover
        logger.debug("[flag_overrides] history failed: %s", e)
    return rows


async def set_override(
    flag_name: str,
    value: Any,
    *,
    set_by: str,
    rationale: str = "",
    safe_to_widen_snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Persist an operator-declared flag intent.

    Idempotent: setting to the current value returns ``changed=False``
    with no new history row.

    NOTE: This does NOT mutate ``os.environ``. Engines continue to read
    the deployed environment. The override is recorded for forensic
    auditability and as a declarative source-of-truth that a future
    adoption pass may begin honouring at runtime.
    """
    flag_name = str(flag_name).strip()
    if not flag_name:
        return {"ok": False, "reason": "empty_flag_name"}
    value = _coerce_value(value)
    try:
        now = _now()
        current = await get_override(flag_name)
        prior_value = current.get("value") if isinstance(current, dict) else None
        if current is not None and prior_value == value:
            return {
                "ok":          True,
                "changed":     False,
                "flag_name":   flag_name,
                "value":       value,
                "prior_value": prior_value,
                "reason":      "idempotent_no_change",
            }
        # Upsert current value.
        await get_db()[OVERRIDES_COLLECTION].update_one(
            {"_id": flag_name},
            {"$set": {
                "flag_name":  flag_name,
                "value":      value,
                "set_by":     str(set_by)[:120],
                "set_at":     now.isoformat(),
                "set_at_dt":  now,
                "rationale":  str(rationale)[:1000],
                "safe_to_widen_at_set": safe_to_widen_snapshot,
            }},
            upsert=True,
        )
        # Append immutable history row.
        await get_db()[HISTORY_COLLECTION].insert_one({
            "history_id": uuid.uuid4().hex[:16],
            "ts":         now.isoformat(),
            "ts_dt":      now,
            "flag_name":  flag_name,
            "value":      value,
            "prior_value": prior_value,
            "set_by":     str(set_by)[:120],
            "rationale":  str(rationale)[:1000],
            "safe_to_widen_at_set": safe_to_widen_snapshot,
        })
        return {
            "ok":          True,
            "changed":     True,
            "flag_name":   flag_name,
            "value":       value,
            "prior_value": prior_value,
            "set_at":      now.isoformat(),
        }
    except Exception as e:                                  # pragma: no cover
        logger.debug("[flag_overrides] set_override failed: %s", e)
        return {"ok": False, "reason": f"persistence_error: {str(e)[:200]}"}


async def remove_override(
    flag_name: str, *, removed_by: str, rationale: str = "",
) -> Dict[str, Any]:
    """Remove a current override and append a history row marking removal."""
    flag_name = str(flag_name).strip()
    if not flag_name:
        return {"ok": False, "reason": "empty_flag_name"}
    try:
        current = await get_override(flag_name)
        if current is None:
            return {"ok": True, "changed": False, "reason": "no_override_present"}
        now = _now()
        await get_db()[OVERRIDES_COLLECTION].delete_one({"_id": flag_name})
        await get_db()[HISTORY_COLLECTION].insert_one({
            "history_id":  uuid.uuid4().hex[:16],
            "ts":          now.isoformat(),
            "ts_dt":       now,
            "flag_name":   flag_name,
            "value":       None,
            "prior_value": current.get("value"),
            "set_by":      str(removed_by)[:120],
            "rationale":   str(rationale)[:1000],
            "action":      "removed",
        })
        return {"ok": True, "changed": True, "flag_name": flag_name}
    except Exception as e:                                  # pragma: no cover
        logger.debug("[flag_overrides] remove_override failed: %s", e)
        return {"ok": False, "reason": f"persistence_error: {str(e)[:200]}"}
