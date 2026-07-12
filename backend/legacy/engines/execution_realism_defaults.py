"""
P1.2 — Dormant per-pair execution-realism defaults registry.

Status
------
* DORMANT BY DEFAULT. Gated by ``ENABLE_EXECUTION_REALISM_DEFAULTS``
  (default ``False``). Even when the flag is ON, **no production code
  path consults this registry**. ``engines/execution_engine.py``
  continues to use its hard-coded ``DEFAULT_EXECUTION_CONFIG`` until a
  future P1.1 promotion explicitly wires this lookup in.
* This module is the institutional record of "what spread/slip/commission
  the operator believes is realistic for each (pair, broker_class)"
  — populated through the admin upsert endpoint and queryable through
  the read-only diagnostic endpoint.

Collection schema
-----------------
``execution_realism_defaults``::

    {
      _id:              ObjectId,
      pair:             "EURUSD",          # uppercased, required
      broker_class:     "tier1_ecn"        # operator-defined tag, required
                          | "tier2_ecn"
                          | "retail_stp"
                          | "prop_firm_a"
                          | ...,
      spread_usd:       float,             # round-trip USD cost
      max_slippage_usd: float,             # max adverse uniform-random
      commission_usd:   float,             # flat round-trip commission
      notes:            str | None,        # operator memo
      source:           str,               # e.g. "operator", "broker_quote_2026Q1"
      updated_at:       ISO string,
      updated_by:       str,               # email of admin who set it
    }

Composite index ``(pair, broker_class)`` is unique — see
``engines/db_indexes.py`` for the install. The index is additive;
omitting it does not break this module (we fall back to scan-then-merge).

Discipline
----------
* Read-only at the engine layer (no engine module consults it).
* Mongo CRUD lives here; the admin write endpoint validates input.
* ``get_defaults(pair, broker_class)`` falls back to
  ``execution_engine.DEFAULT_EXECUTION_CONFIG`` when no row exists —
  honest "not configured" semantics.
* Operators who haven't decreed any realism defaults observe ZERO
  behavior change (engine layer still reads ``execution.enabled=False``).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db

logger = logging.getLogger(__name__)


COLL = "execution_realism_defaults"

_VALID_BROKER_CLASS_HINTS = (
    "tier1_ecn", "tier2_ecn", "retail_stp", "retail_mm",
    "prop_firm_a", "prop_firm_b", "prop_firm_generic",
    "unknown",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_enabled() -> bool:
    """True iff ``ENABLE_EXECUTION_REALISM_DEFAULTS`` is truthy.

    The registry is callable regardless — but production engines MUST
    consult this flag before substituting the lookup result for
    ``execution_engine.DEFAULT_EXECUTION_CONFIG``. The flag is the
    activation axis for future P1.1 wiring; today no engine reads it.
    """
    raw = os.environ.get("ENABLE_EXECUTION_REALISM_DEFAULTS", "")
    return raw.strip().lower() in ("1", "true", "yes", "on")


def normalize_pair(pair: str) -> str:
    return (pair or "").strip().upper()


def normalize_broker_class(broker_class: str) -> str:
    return (broker_class or "").strip().lower()


# ─────────────────────────────────────────────────────────────────────
# Read helpers (pure, never write)
# ─────────────────────────────────────────────────────────────────────
async def get_defaults(
    pair: str,
    broker_class: str = "unknown",
) -> Optional[Dict[str, Any]]:
    """Return the configured defaults row for ``(pair, broker_class)``,
    or ``None`` when the operator has not decreed one.

    Caller policy (FUTURE — not wired today): when ``None`` is
    returned, the caller MUST fall back to
    ``execution_engine.DEFAULT_EXECUTION_CONFIG`` (which is the
    pass-through zero-cost default). Never substitute fabricated
    numbers — honest refusal.
    """
    db = get_db()
    pair_n = normalize_pair(pair)
    bc_n = normalize_broker_class(broker_class)
    try:
        doc = await db[COLL].find_one(
            {"pair": pair_n, "broker_class": bc_n},
            {"_id": 0},
        )
    except Exception as e:                                  # pragma: no cover
        logger.debug("[execution_realism_defaults] read failed: %s", e)
        return None
    return doc


async def list_defaults(
    pair: Optional[str] = None,
    broker_class: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """Return defaults rows matching the optional filter.

    Limited to 1..500 rows. Sorted by ``(pair, broker_class)`` ascending
    for deterministic operator listings.
    """
    db = get_db()
    q: Dict[str, Any] = {}
    if pair:
        q["pair"] = normalize_pair(pair)
    if broker_class:
        q["broker_class"] = normalize_broker_class(broker_class)
    limit = max(1, min(int(limit), 500))
    try:
        cur = db[COLL].find(q, {"_id": 0}).sort(
            [("pair", 1), ("broker_class", 1)],
        ).limit(limit)
        return [d async for d in cur]
    except Exception as e:                                  # pragma: no cover
        logger.debug("[execution_realism_defaults] list failed: %s", e)
        return []


async def count_defaults() -> int:
    """Forensic counter — how many operator-decreed realism rows live
    in the registry right now."""
    db = get_db()
    try:
        return int(await db[COLL].count_documents({}))
    except Exception as e:                                  # pragma: no cover
        logger.debug("[execution_realism_defaults] count failed: %s", e)
        return 0


# ─────────────────────────────────────────────────────────────────────
# Write helpers (admin-only callers — endpoint enforces auth)
# ─────────────────────────────────────────────────────────────────────
def _validate_payload(
    *,
    pair: str,
    broker_class: str,
    spread_usd: float,
    max_slippage_usd: float,
    commission_usd: float,
) -> None:
    """Validate the operator-supplied realism payload.

    Raises ``ValueError`` on any honest refusal. Never silently fixes
    a bad value.
    """
    if not pair or not isinstance(pair, str):
        raise ValueError("pair: non-empty string required")
    if not broker_class or not isinstance(broker_class, str):
        raise ValueError("broker_class: non-empty string required")
    for name, val in (
        ("spread_usd",       spread_usd),
        ("max_slippage_usd", max_slippage_usd),
        ("commission_usd",   commission_usd),
    ):
        if not isinstance(val, (int, float)):
            raise ValueError(f"{name}: numeric value required")
        if val < 0:
            raise ValueError(f"{name}: must be >= 0 (got {val})")
        if val > 1000:
            # Sanity ceiling — operator typo guard. Realistic FX spread
            # values are < $10 round-trip even on exotic pairs. Hitting
            # $1000 is almost certainly a unit error.
            raise ValueError(
                f"{name}: > 1000 looks like a unit error (got {val}); "
                "use cost-in-USD-per-trade, not basis points or pips"
            )


async def upsert_defaults(
    *,
    pair: str,
    broker_class: str,
    spread_usd: float,
    max_slippage_usd: float,
    commission_usd: float,
    notes: Optional[str] = None,
    source: str = "operator",
    updated_by: str,
) -> Dict[str, Any]:
    """Insert or update a defaults row. Returns the stored document.

    The caller (admin endpoint) MUST have already authenticated and
    authorised the operator before invoking this function.
    """
    _validate_payload(
        pair=pair, broker_class=broker_class,
        spread_usd=float(spread_usd),
        max_slippage_usd=float(max_slippage_usd),
        commission_usd=float(commission_usd),
    )
    db = get_db()
    pair_n = normalize_pair(pair)
    bc_n = normalize_broker_class(broker_class)
    doc = {
        "pair":            pair_n,
        "broker_class":    bc_n,
        "spread_usd":      float(spread_usd),
        "max_slippage_usd": float(max_slippage_usd),
        "commission_usd":  float(commission_usd),
        "notes":           (notes or "")[:1000] if notes else None,
        "source":          (source or "operator")[:120],
        "updated_at":      _now_iso(),
        "updated_by":      (updated_by or "<unknown>")[:200],
    }
    try:
        await db[COLL].update_one(
            {"pair": pair_n, "broker_class": bc_n},
            {"$set": doc},
            upsert=True,
        )
    except Exception as e:
        logger.warning("[execution_realism_defaults] upsert failed: %s", e)
        raise
    return doc


async def delete_defaults(pair: str, broker_class: str) -> bool:
    """Remove a defaults row. Returns True iff a row was deleted."""
    db = get_db()
    try:
        result = await db[COLL].delete_one({
            "pair": normalize_pair(pair),
            "broker_class": normalize_broker_class(broker_class),
        })
        return bool(getattr(result, "deleted_count", 0))
    except Exception as e:                                  # pragma: no cover
        logger.debug("[execution_realism_defaults] delete failed: %s", e)
        return False


__all__ = [
    "is_enabled",
    "normalize_pair",
    "normalize_broker_class",
    "get_defaults",
    "list_defaults",
    "count_defaults",
    "upsert_defaults",
    "delete_defaults",
    "COLL",
]
