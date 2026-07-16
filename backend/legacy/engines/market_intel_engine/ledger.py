"""Phase G — Mongo-persisted MarketState ledger.

Single source of truth for the 4 Phase G collections:

  * `market_snapshots`      — raw observations (TTL 30d)
  * `market_states`         — rolling aggregations per window
  * `structural_changes`    — detected change points (canonical timeline)
  * `market_intelligence`   — latest payload per (pair, timeframe)

Every write here is idempotent (upserts) except append_snapshot which
records raw observations. Read helpers return dataclass instances.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import config as mcfg
from .types import (
    MarketIntelligence, MarketSnapshot, MarketState, StructuralChange,
)

logger = logging.getLogger(__name__)


# Collection names — single source of truth
COLL_SNAPSHOTS      = "market_snapshots"
COLL_STATES         = "market_states"
COLL_CHANGES        = "structural_changes"
COLL_INTELLIGENCE   = "market_intelligence"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _get_db():
    """Best-effort db handle. Returns None when Mongo unreachable
    (ledger operations become no-ops)."""
    try:
        from engines.db import get_db
        return get_db()
    except Exception:  # noqa: BLE001
        return None


async def ensure_indexes() -> None:
    """Idempotent index bootstrap. Safe to re-run at every boot."""
    db = await _get_db()
    if db is None:
        return
    try:
        # Snapshots — TTL keyed on `expires_at` (must be BSON datetime,
        # NOT ISO string). We attach expires_at on every insert.
        await db[COLL_SNAPSHOTS].create_index(
            [("pair", 1), ("timeframe", 1), ("ts", -1)], name="pair_tf_ts_1"
        )
        await db[COLL_SNAPSHOTS].create_index(
            "expires_at", expireAfterSeconds=0, name="ttl_expires_at",
        )
        # States
        await db[COLL_STATES].create_index(
            [("pair", 1), ("timeframe", 1), ("window", 1), ("ts", -1)],
            name="pair_tf_window_ts_1",
        )
        # Structural changes
        await db[COLL_CHANGES].create_index(
            [("pair", 1), ("timeframe", 1), ("detected_at", -1)],
            name="pair_tf_detected_1",
        )
        await db[COLL_CHANGES].create_index(
            [("change_type", 1), ("detected_at", -1)],
            name="type_detected_1",
        )
        # Latest MarketIntelligence — one doc per (pair, timeframe)
        await db[COLL_INTELLIGENCE].create_index(
            [("pair", 1), ("timeframe", 1)], unique=True,
            name="pair_tf_unique",
        )
    except Exception:  # noqa: BLE001
        logger.exception("market_intelligence.ensure_indexes failed (non-fatal)")


# ── Writes ──────────────────────────────────────────────────────────
async def append_snapshot(snap: MarketSnapshot) -> Optional[str]:
    db = await _get_db()
    if db is None:
        return None
    try:
        doc = snap.to_dict()
        ttl_seconds = int(mcfg.snapshot_ttl_days()) * 86400
        doc["expires_at"] = datetime.now(timezone.utc).timestamp() + ttl_seconds
        # Store as datetime for Mongo TTL to work
        doc["expires_at"] = datetime.fromtimestamp(doc["expires_at"], tz=timezone.utc)
        res = await db[COLL_SNAPSHOTS].insert_one(doc)
        return str(res.inserted_id)
    except Exception:  # noqa: BLE001
        logger.exception("append_snapshot failed")
        return None


async def append_snapshots(snaps: List[MarketSnapshot]) -> int:
    """Bulk-write helper. Returns count inserted (0 on any failure)."""
    if not snaps:
        return 0
    db = await _get_db()
    if db is None:
        return 0
    try:
        ttl_seconds = int(mcfg.snapshot_ttl_days()) * 86400
        expires = datetime.fromtimestamp(
            datetime.now(timezone.utc).timestamp() + ttl_seconds,
            tz=timezone.utc,
        )
        docs = []
        for s in snaps:
            d = s.to_dict()
            d["expires_at"] = expires
            docs.append(d)
        res = await db[COLL_SNAPSHOTS].insert_many(docs, ordered=False)
        return len(res.inserted_ids)
    except Exception:  # noqa: BLE001
        logger.exception("append_snapshots failed")
        return 0


async def upsert_state(state: MarketState) -> Optional[str]:
    db = await _get_db()
    if db is None:
        return None
    try:
        doc = state.to_dict()
        res = await db[COLL_STATES].update_one(
            {"pair": state.pair, "timeframe": state.timeframe,
             "window": state.window, "ts": state.ts},
            {"$set": doc}, upsert=True,
        )
        return str(res.upserted_id) if res.upserted_id else "updated"
    except Exception:  # noqa: BLE001
        logger.exception("upsert_state failed")
        return None


async def insert_change(change: StructuralChange) -> Optional[str]:
    """Write to the dedicated `structural_changes` timeline. The caller
    is also expected to emit an `outcome_events` row via
    `intelligence.explainability.emit_decision('structural_change_detected', ...)`
    (per Q3 operator decision — write to BOTH)."""
    db = await _get_db()
    if db is None:
        return None
    try:
        res = await db[COLL_CHANGES].insert_one(change.to_dict())
        return str(res.inserted_id)
    except Exception:  # noqa: BLE001
        logger.exception("insert_change failed")
        return None


async def upsert_intelligence(mi: MarketIntelligence) -> Optional[str]:
    db = await _get_db()
    if db is None:
        return None
    try:
        doc = mi.to_dict()
        res = await db[COLL_INTELLIGENCE].update_one(
            {"pair": mi.pair, "timeframe": mi.timeframe},
            {"$set": doc}, upsert=True,
        )
        return str(res.upserted_id) if res.upserted_id else "updated"
    except Exception:  # noqa: BLE001
        logger.exception("upsert_intelligence failed")
        return None


# ── Reads ───────────────────────────────────────────────────────────
async def read_recent_snapshots(
    pair: str, timeframe: str, limit: int = 500,
) -> List[MarketSnapshot]:
    db = await _get_db()
    if db is None:
        return []
    try:
        cur = db[COLL_SNAPSHOTS].find(
            {"pair": pair, "timeframe": timeframe}
        ).sort("ts", -1).limit(int(limit))
        docs = await cur.to_list(length=int(limit))
        out: List[MarketSnapshot] = []
        for d in docs:
            d.pop("_id", None)
            d.pop("expires_at", None)
            try:
                out.append(MarketSnapshot(**d))
            except TypeError:  # tolerate stale schema
                continue
        # Return chronological order — oldest first
        return list(reversed(out))
    except Exception:  # noqa: BLE001
        logger.exception("read_recent_snapshots failed")
        return []


async def read_latest_state(
    pair: str, timeframe: str, window: str = "24h",
) -> Optional[MarketState]:
    db = await _get_db()
    if db is None:
        return None
    try:
        d = await db[COLL_STATES].find_one(
            {"pair": pair, "timeframe": timeframe, "window": window},
            sort=[("ts", -1)],
        )
        if not d:
            return None
        d.pop("_id", None)
        try:
            return MarketState(**d)
        except TypeError:
            return None
    except Exception:  # noqa: BLE001
        logger.exception("read_latest_state failed")
        return None


async def read_state_history(
    pair: str, timeframe: str, window: str = "24h", limit: int = 100,
) -> List[MarketState]:
    db = await _get_db()
    if db is None:
        return []
    try:
        cur = db[COLL_STATES].find(
            {"pair": pair, "timeframe": timeframe, "window": window}
        ).sort("ts", -1).limit(int(limit))
        docs = await cur.to_list(length=int(limit))
        out: List[MarketState] = []
        for d in docs:
            d.pop("_id", None)
            try:
                out.append(MarketState(**d))
            except TypeError:
                continue
        return out
    except Exception:  # noqa: BLE001
        logger.exception("read_state_history failed")
        return []


async def read_recent_changes(
    pair: Optional[str] = None, limit: int = 50,
) -> List[Dict[str, Any]]:
    db = await _get_db()
    if db is None:
        return []
    try:
        q: Dict[str, Any] = {}
        if pair:
            q["pair"] = pair
        cur = db[COLL_CHANGES].find(q).sort("detected_at", -1).limit(int(limit))
        docs = await cur.to_list(length=int(limit))
        for d in docs:
            d["_id"] = str(d.get("_id"))
        return docs
    except Exception:  # noqa: BLE001
        logger.exception("read_recent_changes failed")
        return []


async def read_latest_intelligence(
    pair: str, timeframe: str,
) -> Optional[MarketIntelligence]:
    db = await _get_db()
    if db is None:
        return None
    try:
        d = await db[COLL_INTELLIGENCE].find_one(
            {"pair": pair, "timeframe": timeframe}
        )
        if not d:
            return None
        d.pop("_id", None)
        try:
            return MarketIntelligence(**d)
        except TypeError:
            return None
    except Exception:  # noqa: BLE001
        logger.exception("read_latest_intelligence failed")
        return None


async def read_intelligence_by_id(intel_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a raw MarketIntelligence doc by _id (for /explain/*).

    Also returns the linked structural_changes that were active at
    upsert-time (materialised inside `active_structural_changes`).
    """
    db = await _get_db()
    if db is None:
        return None
    try:
        from bson import ObjectId  # type: ignore
        oid = ObjectId(intel_id)
        d = await db[COLL_INTELLIGENCE].find_one({"_id": oid})
        if not d:
            return None
        d["_id"] = str(d["_id"])
        return d
    except Exception:  # noqa: BLE001
        return None
