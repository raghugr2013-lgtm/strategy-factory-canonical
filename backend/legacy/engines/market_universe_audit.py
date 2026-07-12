"""R0 — audit writer for the market_universe registry.

Companion to ``engines.market_universe``. Every write to
``market_universe_symbols`` produces one row here, with both the
``before`` and ``after`` snapshots plus a ``diff`` map for quick
operator review.

Schema (``market_universe_audit``)
-----------------------------------
::

    {
        symbol:         str,                  # canonical normalised
        broker_class:   str,                  # canonical normalised
        action:         str,                  # one of ACTION_KEYS
        operator:       str,                  # email / sub or "<unknown>"
        ts:             ISO str               # human-readable timestamp
        ts_dt:          BSON datetime         # TTL-eligible (90 days)
        updated_at:     ISO str               # row's updated_at echoed in
        before:         dict | null           # full prior row (without _id)
        after:          dict | null           # full new row (without _id)
        diff:           { key: [before,after] }  # shallow diff (for quick view)
    }

Retention is enforced by the TTL index ``ttl_market_universe_audit``
declared in ``engines.db_indexes`` (90-day default; operator-tunable
via ``MARKET_UNIVERSE_AUDIT_TTL_DAYS``).

Discipline
----------
* **Never raises.** Audit writes are best-effort. A failure here must
  never abort the parent write to ``market_universe_symbols``.
* **No engine reads this.** Pure operator-facing forensics.
* **No alerting.** Forensic; not on the trade path.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from engines.db import get_db

logger = logging.getLogger(__name__)

AUDIT_COLL = "market_universe_audit"

ACTION_KEYS = (
    "seed_baseline",
    "upsert_insert",
    "upsert_update",
    "set_tier",
    "set_enabled",
    "set_eligibility",
    "set_calendar",
    "delete",
    "forced_delete",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _shallow_diff(
    before: Optional[Dict[str, Any]],
    after: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Return ``{key: [before_val, after_val]}`` for every top-level key
    whose value differs between ``before`` and ``after``. Used for the
    operator preview; the full snapshots remain available in
    ``before`` / ``after`` fields.
    """
    b = before or {}
    a = after or {}
    keys = set(b.keys()) | set(a.keys())
    out: Dict[str, Any] = {}
    skip = {"updated_at", "updated_by"}  # noisy on every write
    for k in keys:
        if k in skip:
            continue
        bv = b.get(k)
        av = a.get(k)
        if bv != av:
            out[k] = [bv, av]
    return out


async def write_audit_entry(
    *,
    symbol: str,
    broker_class: str,
    before: Optional[Dict[str, Any]],
    after: Optional[Dict[str, Any]],
    operator_email: str,
    action: str,
) -> None:
    """Best-effort audit insert. Never raises.

    Caller (engines.market_universe) is responsible for normalising
    ``symbol`` / ``broker_class`` before reaching this function.
    """
    if action not in ACTION_KEYS:
        action = "upsert_update"
    try:
        doc = {
            "symbol":       symbol,
            "broker_class": broker_class,
            "action":       action,
            "operator":     (operator_email or "<unknown>")[:200],
            "ts":           _now_iso(),
            "ts_dt":        _now_dt(),
            "updated_at":   (after or before or {}).get("updated_at"),
            "before":       before,
            "after":        after,
            "diff":         _shallow_diff(before, after),
        }
        db = get_db()
        await db[AUDIT_COLL].insert_one(doc)
    except Exception as e:                                  # pragma: no cover
        logger.debug("[market_universe_audit] insert failed: %s", e)


async def list_audit(
    *,
    symbol: Optional[str] = None,
    broker_class: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 200,
):
    """Read audit rows. Filter by any subset of (symbol, broker_class,
    action). Returns newest first."""
    db = get_db()
    q: Dict[str, Any] = {}
    if symbol:
        q["symbol"] = symbol
    if broker_class:
        q["broker_class"] = broker_class
    if action:
        q["action"] = action
    limit = max(1, min(int(limit), 2000))
    cur = db[AUDIT_COLL].find(q, {"_id": 0}).sort([("ts_dt", -1)]).limit(limit)
    return [d async for d in cur]


__all__ = [
    "AUDIT_COLL", "ACTION_KEYS",
    "write_audit_entry", "list_audit",
]
