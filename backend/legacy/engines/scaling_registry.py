"""
VPS Scaling P1.A — `scaling_nodes` registry (READ-MOSTLY, ADDITIVE).

This module is the persistence layer for the per-host observability
loop. It receives `compute_probe.snapshot()` payloads from one or more
hosts (today only the build host, but the schema and API are written
to accept N nodes from day one) and exposes a read-only diagnostic
view of the table to the operator.

Discipline (per `VPS_SCALING_P1_IMPLEMENTATION_PLAN.md` §2.4 + §3):
  * Additive only — no edits to existing collections.
  * Idempotent indexes via `ensure_indexes()` (called from server startup).
  * Single Mongo collection: `scaling_nodes`. One row per `host_id`.
  * Best-effort writes — Mongo failure is logged, never raised, so the
    heartbeat endpoint cannot 5xx when the registry blips.
  * No control-plane side-effects — this module never accepts work,
    never throttles work, never gates work. The router is the next
    file (`scaling_router.py`). This one only PERSISTS observations.

Schema row shape (single document per `host_id`):

    {
      "_id":            <host_id>,            # operator-chosen, stable
      "hostname":       "vps-prod-01",
      "first_seen":     iso-string,
      "last_seen":      iso-string,
      "last_snapshot":  { ... raw compute_probe.snapshot ... },
      "last_headroom":  { "ok": bool, "band": "ok"|"warn"|"critical"|"unknown",
                          "cpu_headroom_pct": float, "mem_headroom_pct": float },
      "band_history":   [ {"ts": iso, "band": "...",
                           "cpu_percent": float, "mem_percent": float}, ... up to 60 ],
      "workload_tags":  [ "build_host" | "ctrader_runner" | ... ],
      "heartbeat_count": int,
    }

Public surface:
    * ensure_indexes()                  — called from server.py startup
    * register_or_heartbeat(payload)    — upsert from POST /api/scaling/heartbeat
    * list_nodes(limit)                 — read-only diagnostic
    * get_node(host_id)                 — read-only diagnostic
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pymongo import ASCENDING, DESCENDING

from engines.db import get_db

logger = logging.getLogger(__name__)

COLLECTION = "scaling_nodes"
BAND_HISTORY_MAX = 60   # 60 × 30 s = 30 minutes rolling


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def ensure_indexes() -> Dict[str, Any]:
    """Idempotent index creation for `scaling_nodes`. Never raises.

    Returns a structured summary so the caller (server startup) can
    log it alongside the other index-hardening steps.
    """
    db = get_db()
    created: List[str] = []
    existed: List[str] = []
    errors: List[Dict[str, str]] = []

    specs = [
        # Liveness scans: sort by last_seen desc.
        ([("last_seen", DESCENDING)],
         {"name": "ix_scaling_last_seen", "background": True}),
        # Per-band scans for the diagnostic UI.
        ([("last_headroom.band", ASCENDING)],
         {"name": "ix_scaling_band", "background": True}),
        # Per-tag fan-out (workload routing in later phases).
        ([("workload_tags", ASCENDING)],
         {"name": "ix_scaling_tags", "background": True}),
    ]
    try:
        existing = await db[COLLECTION].index_information()
    except Exception as e:                                   # pragma: no cover
        logger.warning("[scaling_registry] index_information failed: %s", e)
        return {"created": [], "existed": [], "errors": [{"error": str(e)[:200]}]}

    for keys, options in specs:
        name = options["name"]
        try:
            if name in existing:
                existed.append(name)
                continue
            await db[COLLECTION].create_index(keys, **options)
            created.append(name)
        except Exception as e:                               # pragma: no cover
            errors.append({"index": name, "error": str(e)[:200]})
            logger.warning("[scaling_registry] index %s failed: %s", name, e)
    return {"created": created, "existed": existed, "errors": errors}


async def register_or_heartbeat(
    *,
    host_id: str,
    hostname: Optional[str] = None,
    snapshot: Optional[Dict[str, Any]] = None,
    headroom: Optional[Dict[str, Any]] = None,
    workload_tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Upsert a node row from one heartbeat. Idempotent.

    The caller (the API layer) is responsible for having already called
    `compute_probe.snapshot()` and `compute_probe.headroom_summary()`.

    Returns the resulting row (already serialised; no ObjectId).
    Never raises — Mongo failure returns a structured error dict so the
    HTTP endpoint can still 200 with diagnostic context.
    """
    if not host_id or not isinstance(host_id, str):
        return {"ok": False, "reason": "invalid_host_id"}

    db = get_db()
    now = _now_iso()
    band = (headroom or {}).get("band") or "unknown"
    cpu_p = (snapshot or {}).get("cpu_percent")
    mem_p = (snapshot or {}).get("mem_percent")

    band_entry = {
        "ts":          now,
        "band":        band,
        "cpu_percent": cpu_p,
        "mem_percent": mem_p,
    }

    try:
        await db[COLLECTION].update_one(
            {"_id": host_id},
            {
                "$set": {
                    "hostname":      hostname or host_id,
                    "last_seen":     now,
                    "last_snapshot": snapshot or {},
                    "last_headroom": headroom or {},
                    "workload_tags": list(workload_tags or []),
                },
                "$setOnInsert": {
                    "first_seen": now,
                },
                "$inc": {"heartbeat_count": 1},
                "$push": {
                    "band_history": {
                        "$each":  [band_entry],
                        "$slice": -BAND_HISTORY_MAX,
                    }
                },
            },
            upsert=True,
        )
    except Exception as e:                                   # pragma: no cover
        logger.warning("[scaling_registry] upsert %s failed: %s", host_id, e)
        return {"ok": False, "reason": "persist_failed", "error": str(e)[:200]}

    row = await get_node(host_id)
    return {"ok": True, "host_id": host_id, "row": row}


async def get_node(host_id: str) -> Optional[Dict[str, Any]]:
    """Read a single node row. Returns None on missing/Mongo error."""
    db = get_db()
    try:
        doc = await db[COLLECTION].find_one({"_id": host_id})
    except Exception as e:                                   # pragma: no cover
        logger.debug("[scaling_registry] get_node %s failed: %s", host_id, e)
        return None
    if not doc:
        return None
    doc["host_id"] = doc.pop("_id")
    return doc


async def list_nodes(limit: int = 100) -> List[Dict[str, Any]]:
    """Read all known nodes sorted by `last_seen` desc."""
    db = get_db()
    try:
        cur = (
            db[COLLECTION]
            .find({}, {"band_history": {"$slice": -10}})  # trim history payload
            .sort("last_seen", DESCENDING)
            .limit(max(1, min(int(limit), 500)))
        )
        rows: List[Dict[str, Any]] = []
        async for d in cur:
            d["host_id"] = d.pop("_id")
            rows.append(d)
        return rows
    except Exception as e:                                   # pragma: no cover
        logger.debug("[scaling_registry] list_nodes failed: %s", e)
        return []
