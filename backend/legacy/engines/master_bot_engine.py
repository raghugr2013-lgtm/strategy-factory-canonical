"""Master Bot V1 — Persistence engine (MB-1).

Three Mongo collections, all owned by this module:

    master_bots          ── one row per Master Bot (name, owner, status,
                            constraints, metrics_snapshot, lineage).
    master_bot_members   ── one row per (master_bot_id, strategy_hash)
                            pair. Tier + order_index + enabled flag.
    master_bot_tiers     ── one row per (master_bot_id, tier_key)
                            with per-tier metadata (allocation_share,
                            label, max_members). Three rows seeded
                            (tier1 / tier2 / tier3) on Master Bot
                            creation.

Architecture discipline (Master Bot development branch — 2026-01):
    * READ-ONLY against every other collection. Never writes to
      strategy_lifecycle, strategy_library, survivor_registry, or any
      production activation collection.
    * Idempotent indexes on startup-touch (created lazily on first use).
    * Soft-delete-on-master-bot (status = "deleted"); hard-delete also
      supported for operator-side housekeeping.
    * No scheduler hooks. UI/API-triggered only.

Public surface mirrors the API verbs:
    create_master_bot, list_master_bots, get_master_bot,
    rename_master_bot, delete_master_bot,
    add_member, remove_member, set_member_enabled,
    promote_member, demote_member, reorder_members,
    list_members, get_member,
    set_tier_metadata, list_tiers.

All functions are async (Motor) and never raise on transient DB blips —
they surface `ValueError` for operator-facing rule violations only.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────

MASTER_BOTS_COLL          = "master_bots"
MASTER_BOT_MEMBERS_COLL   = "master_bot_members"
MASTER_BOT_TIERS_COLL     = "master_bot_tiers"

TIER_KEYS = ("tier1", "tier2", "tier3")

# Default per-tier metadata seeded at Master Bot creation. Allocation
# shares are operator-visible defaults from the Master Bot V1
# architecture doc (§4.1). They are advisory in MB-1; MB-3 / future
# MB-4 will consume them for the per-tier risk math.
DEFAULT_TIER_METADATA = {
    "tier1": {"label": "Tier 1 — Primary",        "allocation_share": 0.50, "max_members": 5},
    "tier2": {"label": "Tier 2 — Secondary",       "allocation_share": 0.33, "max_members": 10},
    "tier3": {"label": "Tier 3 — Probationary",    "allocation_share": 0.17, "max_members": 15},
}

# Master Bot status lifecycle (subset relevant to MB-1; MB-2/3 may add
# PUBLISHED/DEPLOYED states).
STATUS_DRAFT     = "DRAFT"
STATUS_PUBLISHED = "PUBLISHED"
STATUS_DEPLOYED  = "DEPLOYED"
STATUS_RETIRED   = "RETIRED"
STATUS_DELETED   = "DELETED"

VALID_STATUSES = (
    STATUS_DRAFT, STATUS_PUBLISHED, STATUS_DEPLOYED,
    STATUS_RETIRED, STATUS_DELETED,
)

# Name constraints — operator-friendly but bounded so the UI can render.
MIN_NAME_LEN = 1
MAX_NAME_LEN = 120


# ── Time helper ──────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Index hardening (idempotent) ────────────────────────────────────

_indexes_ready = False


async def ensure_indexes() -> None:
    """Idempotent index creation. Safe to call from multiple workers."""
    global _indexes_ready
    if _indexes_ready:
        return
    db = get_db()
    try:
        await db[MASTER_BOTS_COLL].create_index("id", unique=True)
        await db[MASTER_BOTS_COLL].create_index("owner")
        await db[MASTER_BOTS_COLL].create_index("status")
        await db[MASTER_BOT_MEMBERS_COLL].create_index(
            [("master_bot_id", 1), ("strategy_hash", 1)],
            unique=True,
        )
        await db[MASTER_BOT_MEMBERS_COLL].create_index(
            [("master_bot_id", 1), ("tier", 1), ("order_index", 1)],
        )
        await db[MASTER_BOT_TIERS_COLL].create_index(
            [("master_bot_id", 1), ("tier_key", 1)],
            unique=True,
        )
        _indexes_ready = True
    except Exception:
        # Don't crash on transient blips — next call will retry.
        logger.exception("master_bot: ensure_indexes failed (will retry)")


# ── Validation helpers ──────────────────────────────────────────────

def _norm_name(name: Optional[str]) -> str:
    n = (name or "").strip()
    if len(n) < MIN_NAME_LEN or len(n) > MAX_NAME_LEN:
        raise ValueError(
            f"name must be {MIN_NAME_LEN}–{MAX_NAME_LEN} chars (got {len(n)})"
        )
    return n


def _require_tier(tier: str) -> str:
    if tier not in TIER_KEYS:
        raise ValueError(f"tier must be one of {TIER_KEYS}; got '{tier}'")
    return tier


def _shape_master_bot(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Shape a raw Mongo doc for API output. Strips `_id`."""
    return {k: v for k, v in (doc or {}).items() if k != "_id"}


def _shape(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Generic _id stripper (defensive — projections already drop it)."""
    if not doc:
        return doc
    return {k: v for k, v in doc.items() if k != "_id"}


# ── Tier helpers ────────────────────────────────────────────────────

async def _seed_tiers(master_bot_id: str) -> None:
    """Idempotent: seeds the three tier metadata rows for a new bot."""
    db = get_db()
    now = _now_iso()
    rows = []
    for tk in TIER_KEYS:
        meta = DEFAULT_TIER_METADATA[tk]
        rows.append({
            "master_bot_id":     master_bot_id,
            "tier_key":          tk,
            "label":             meta["label"],
            "allocation_share":  meta["allocation_share"],
            "max_members":       meta["max_members"],
            "created_at":        now,
            "updated_at":        now,
        })
    try:
        await db[MASTER_BOT_TIERS_COLL].insert_many(rows, ordered=False)
    except Exception:
        # Already seeded (race / retry). Silently OK.
        pass


async def list_tiers(master_bot_id: str) -> List[Dict[str, Any]]:
    db = get_db()
    cur = db[MASTER_BOT_TIERS_COLL].find(
        {"master_bot_id": master_bot_id}, {"_id": 0}
    )
    rows = [d async for d in cur]
    # Stable order tier1 → tier2 → tier3
    rows.sort(key=lambda r: TIER_KEYS.index(r.get("tier_key", "tier1")))
    return rows


async def set_tier_metadata(
    master_bot_id: str,
    tier_key: str,
    *,
    label: Optional[str] = None,
    allocation_share: Optional[float] = None,
    max_members: Optional[int] = None,
) -> Dict[str, Any]:
    _require_tier(tier_key)
    db = get_db()
    patch: Dict[str, Any] = {"updated_at": _now_iso()}
    if label is not None:
        if not isinstance(label, str) or not (1 <= len(label) <= 120):
            raise ValueError("label must be a non-empty string ≤120 chars")
        patch["label"] = label.strip()
    if allocation_share is not None:
        if not isinstance(allocation_share, (int, float)):
            raise ValueError("allocation_share must be numeric")
        if not (0.0 <= float(allocation_share) <= 1.0):
            raise ValueError("allocation_share must be in [0.0, 1.0]")
        patch["allocation_share"] = float(allocation_share)
    if max_members is not None:
        if not isinstance(max_members, int) or max_members < 0:
            raise ValueError("max_members must be a non-negative integer")
        patch["max_members"] = int(max_members)

    if len(patch) == 1:
        # Nothing to change — return current row.
        row = await db[MASTER_BOT_TIERS_COLL].find_one(
            {"master_bot_id": master_bot_id, "tier_key": tier_key},
            {"_id": 0},
        )
        if not row:
            raise ValueError("master bot or tier not found")
        return row

    res = await db[MASTER_BOT_TIERS_COLL].find_one_and_update(
        {"master_bot_id": master_bot_id, "tier_key": tier_key},
        {"$set": patch},
        return_document=True,
        projection={"_id": 0},
    )
    if not res:
        raise ValueError("master bot or tier not found")
    return _shape(res)


# ── Master Bot CRUD ─────────────────────────────────────────────────

async def create_master_bot(
    *,
    name: str,
    owner: str,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    await ensure_indexes()
    name = _norm_name(name)
    owner = (owner or "").strip().lower()
    if not owner:
        raise ValueError("owner must be a non-empty string")

    db = get_db()
    now = _now_iso()
    mb_id = uuid.uuid4().hex
    doc = {
        "id":                  mb_id,
        "name":                name,
        "owner":                owner,
        "description":         (description or "").strip()[:500],
        "status":              STATUS_DRAFT,
        "constraints": {
            "max_open_positions":      5,
            "max_correlation_pairs":   0.85,
            "max_concurrent_per_pair": 2,
        },
        "metrics_snapshot":    {},
        "lineage": {
            "candidate_pool_hash":  None,
            "ranker_version":       "v1.0",
            "allocator_policy":     "equal_weight",
            "rolled_from":          None,
        },
        "created_at":   now,
        "updated_at":   now,
        "published_at": None,
    }
    await db[MASTER_BOTS_COLL].insert_one(doc)
    await _seed_tiers(mb_id)
    return _shape_master_bot(doc)


async def list_master_bots(
    *,
    owner: Optional[str] = None,
    include_deleted: bool = False,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    await ensure_indexes()
    db = get_db()
    q: Dict[str, Any] = {}
    if owner:
        q["owner"] = owner.lower()
    if not include_deleted:
        q["status"] = {"$ne": STATUS_DELETED}
    cur = db[MASTER_BOTS_COLL].find(q, {"_id": 0}).sort("created_at", -1).limit(int(limit))
    rows = [d async for d in cur]
    # Enrich with member counts per tier (cheap aggregation; tiny N).
    for row in rows:
        row["member_counts"] = await _member_counts(row["id"])
    return rows


async def _member_counts(master_bot_id: str) -> Dict[str, int]:
    db = get_db()
    out = {tk: 0 for tk in TIER_KEYS}
    out["enabled"] = 0
    out["total"] = 0
    cur = db[MASTER_BOT_MEMBERS_COLL].find(
        {"master_bot_id": master_bot_id},
        {"_id": 0, "tier": 1, "enabled": 1},
    )
    async for d in cur:
        tk = d.get("tier")
        if tk in out:
            out[tk] += 1
        out["total"] += 1
        if d.get("enabled"):
            out["enabled"] += 1
    return out


async def get_master_bot(master_bot_id: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    doc = await db[MASTER_BOTS_COLL].find_one({"id": master_bot_id}, {"_id": 0})
    if not doc:
        return None
    doc["tiers"] = await list_tiers(master_bot_id)
    doc["members_by_tier"] = await _members_by_tier(master_bot_id)
    doc["member_counts"] = await _member_counts(master_bot_id)
    return doc


async def _members_by_tier(master_bot_id: str) -> Dict[str, List[Dict[str, Any]]]:
    db = get_db()
    out: Dict[str, List[Dict[str, Any]]] = {tk: [] for tk in TIER_KEYS}
    cur = db[MASTER_BOT_MEMBERS_COLL].find(
        {"master_bot_id": master_bot_id}, {"_id": 0}
    ).sort([("tier", 1), ("order_index", 1)])
    async for d in cur:
        tk = d.get("tier")
        if tk in out:
            out[tk].append(d)
    return out


async def rename_master_bot(
    master_bot_id: str,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    db = get_db()
    patch: Dict[str, Any] = {"updated_at": _now_iso()}
    if name is not None:
        patch["name"] = _norm_name(name)
    if description is not None:
        patch["description"] = (description or "").strip()[:500]
    if len(patch) == 1:
        # Nothing to change.
        doc = await db[MASTER_BOTS_COLL].find_one(
            {"id": master_bot_id}, {"_id": 0}
        )
        if not doc:
            raise ValueError("master bot not found")
        return doc
    res = await db[MASTER_BOTS_COLL].find_one_and_update(
        {"id": master_bot_id},
        {"$set": patch},
        return_document=True,
        projection={"_id": 0},
    )
    if not res:
        raise ValueError("master bot not found")
    return _shape(res)


async def delete_master_bot(
    master_bot_id: str,
    *,
    hard: bool = False,
) -> Dict[str, Any]:
    """Soft-delete by default (status → DELETED). hard=True removes all rows."""
    db = get_db()
    existing = await db[MASTER_BOTS_COLL].find_one(
        {"id": master_bot_id}, {"_id": 0}
    )
    if not existing:
        raise ValueError("master bot not found")

    if hard:
        await db[MASTER_BOT_MEMBERS_COLL].delete_many(
            {"master_bot_id": master_bot_id}
        )
        await db[MASTER_BOT_TIERS_COLL].delete_many(
            {"master_bot_id": master_bot_id}
        )
        await db[MASTER_BOTS_COLL].delete_one({"id": master_bot_id})
        return {"deleted": True, "hard": True, "id": master_bot_id}

    await db[MASTER_BOTS_COLL].update_one(
        {"id": master_bot_id},
        {"$set": {"status": STATUS_DELETED, "updated_at": _now_iso()}},
    )
    return {"deleted": True, "hard": False, "id": master_bot_id}


# ── Members CRUD ────────────────────────────────────────────────────

async def _next_order_index(master_bot_id: str, tier: str) -> int:
    db = get_db()
    last = await db[MASTER_BOT_MEMBERS_COLL].find_one(
        {"master_bot_id": master_bot_id, "tier": tier},
        {"order_index": 1},
        sort=[("order_index", -1)],
    )
    if not last:
        return 0
    return int(last.get("order_index") or 0) + 1


async def add_member(
    master_bot_id: str,
    *,
    strategy_hash: str,
    tier: str = "tier3",
    weight: Optional[float] = None,
    notes: Optional[str] = None,
    snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Attach a strategy to a Master Bot in a given tier.

    `snapshot` carries metrics captured at add-time so the dashboard can
    render even if the upstream lifecycle row later changes (PF, win
    rate, pass_probability, deploy_score, style, pair, timeframe, …).

    MB-7.2: if the caller did NOT supply `strategy_ir` in the snapshot,
    we attempt a one-shot lookup from the library / mutation_variants.
    This makes manual adds (UI "+" button on a candidate) automatically
    capture the IR without the frontend having to fan-out two requests.
    """
    _require_tier(tier)
    sh = (strategy_hash or "").strip()
    if not (8 <= len(sh) <= 128):
        raise ValueError("strategy_hash must be 8–128 chars")

    # Verify the parent exists (and is not deleted).
    parent = await get_master_bot(master_bot_id)
    if not parent or parent.get("status") == STATUS_DELETED:
        raise ValueError("master bot not found")

    db = get_db()
    # Reject duplicates across tiers (one strategy = one row per bot).
    existing = await db[MASTER_BOT_MEMBERS_COLL].find_one(
        {"master_bot_id": master_bot_id, "strategy_hash": sh},
        {"_id": 0, "tier": 1},
    )
    if existing:
        raise ValueError(
            f"strategy already a member of this master bot (tier={existing.get('tier')})"
        )

    # MB-7.2: lazy IR capture if not provided.
    snap = dict(snapshot or {})
    if not snap.get("strategy_ir"):
        try:
            from engines import strategy_ir_backfill as _ir_backfill
            ir = await _ir_backfill.get_ir_for_hash(sh)
            if ir is not None:
                snap["strategy_ir"] = ir
                snap["ir_status"]   = "ir_native"
                snap["ir_version"]  = int(ir.get("ir_version") or 1)
        except Exception:                                       # pragma: no cover
            logger.exception("master_bot: lazy IR capture failed for %s", sh)
    if not snap.get("strategy_ir"):
        snap.setdefault("ir_status", "legacy")

    order_index = await _next_order_index(master_bot_id, tier)
    now = _now_iso()
    member = {
        "master_bot_id": master_bot_id,
        "strategy_hash": sh,
        "tier":          tier,
        "order_index":   order_index,
        "enabled":       True,
        "weight":        float(weight) if weight is not None else None,
        "notes":         (notes or "").strip()[:500],
        "snapshot":      snap,
        "added_at":      now,
        "updated_at":    now,
    }
    await db[MASTER_BOT_MEMBERS_COLL].insert_one(member)
    await _touch_master_bot(master_bot_id)
    return {k: v for k, v in member.items() if k != "_id"}


async def remove_member(
    master_bot_id: str, strategy_hash: str,
) -> Dict[str, Any]:
    db = get_db()
    res = await db[MASTER_BOT_MEMBERS_COLL].delete_one(
        {"master_bot_id": master_bot_id, "strategy_hash": strategy_hash}
    )
    if res.deleted_count == 0:
        raise ValueError("member not found")
    await _touch_master_bot(master_bot_id)
    return {"removed": True, "strategy_hash": strategy_hash}


async def set_member_enabled(
    master_bot_id: str, strategy_hash: str, enabled: bool,
) -> Dict[str, Any]:
    db = get_db()
    res = await db[MASTER_BOT_MEMBERS_COLL].find_one_and_update(
        {"master_bot_id": master_bot_id, "strategy_hash": strategy_hash},
        {"$set": {"enabled": bool(enabled), "updated_at": _now_iso()}},
        return_document=True,
        projection={"_id": 0},
    )
    if not res:
        raise ValueError("member not found")
    await _touch_master_bot(master_bot_id)
    return _shape(res)


async def promote_member(
    master_bot_id: str, strategy_hash: str,
) -> Dict[str, Any]:
    return await _move_tier(master_bot_id, strategy_hash, direction=-1)


async def demote_member(
    master_bot_id: str, strategy_hash: str,
) -> Dict[str, Any]:
    return await _move_tier(master_bot_id, strategy_hash, direction=+1)


async def move_to_tier(
    master_bot_id: str, strategy_hash: str, tier: str,
) -> Dict[str, Any]:
    _require_tier(tier)
    db = get_db()
    current = await db[MASTER_BOT_MEMBERS_COLL].find_one(
        {"master_bot_id": master_bot_id, "strategy_hash": strategy_hash},
        {"_id": 0},
    )
    if not current:
        raise ValueError("member not found")
    if current.get("tier") == tier:
        return current
    new_order = await _next_order_index(master_bot_id, tier)
    res = await db[MASTER_BOT_MEMBERS_COLL].find_one_and_update(
        {"master_bot_id": master_bot_id, "strategy_hash": strategy_hash},
        {"$set": {
            "tier":        tier,
            "order_index": new_order,
            "updated_at":  _now_iso(),
        }},
        return_document=True,
        projection={"_id": 0},
    )
    await _touch_master_bot(master_bot_id)
    return _shape(res)


async def _move_tier(
    master_bot_id: str, strategy_hash: str, *, direction: int,
) -> Dict[str, Any]:
    """direction=-1 promote (tier3 → tier2 → tier1).
    direction=+1 demote (tier1 → tier2 → tier3)."""
    db = get_db()
    current = await db[MASTER_BOT_MEMBERS_COLL].find_one(
        {"master_bot_id": master_bot_id, "strategy_hash": strategy_hash},
        {"_id": 0},
    )
    if not current:
        raise ValueError("member not found")
    cur_tier = current.get("tier") or "tier3"
    idx = TIER_KEYS.index(cur_tier)
    new_idx = idx + direction
    if new_idx < 0:
        raise ValueError(f"cannot promote — already at {cur_tier}")
    if new_idx >= len(TIER_KEYS):
        raise ValueError(f"cannot demote — already at {cur_tier}")
    new_tier = TIER_KEYS[new_idx]
    return await move_to_tier(master_bot_id, strategy_hash, new_tier)


async def reorder_members(
    master_bot_id: str, tier: str, ordered_hashes: List[str],
) -> List[Dict[str, Any]]:
    """Persist a new explicit order for the given tier. Hashes outside
    the tier are ignored; hashes inside the tier missing from the list
    are appended in their previous relative order."""
    _require_tier(tier)
    db = get_db()
    existing = [
        d async for d in db[MASTER_BOT_MEMBERS_COLL].find(
            {"master_bot_id": master_bot_id, "tier": tier},
            {"_id": 0, "strategy_hash": 1, "order_index": 1},
        ).sort("order_index", 1)
    ]
    by_hash = {e["strategy_hash"]: e for e in existing}
    desired = [h for h in (ordered_hashes or []) if h in by_hash]
    seen = set(desired)
    tail = [e["strategy_hash"] for e in existing if e["strategy_hash"] not in seen]
    final_order = desired + tail
    now = _now_iso()
    for i, h in enumerate(final_order):
        await db[MASTER_BOT_MEMBERS_COLL].update_one(
            {"master_bot_id": master_bot_id, "strategy_hash": h},
            {"$set": {"order_index": i, "updated_at": now}},
        )
    if final_order:
        await _touch_master_bot(master_bot_id)
    return [
        d async for d in db[MASTER_BOT_MEMBERS_COLL].find(
            {"master_bot_id": master_bot_id, "tier": tier},
            {"_id": 0},
        ).sort("order_index", 1)
    ]


async def list_members(master_bot_id: str) -> List[Dict[str, Any]]:
    db = get_db()
    cur = db[MASTER_BOT_MEMBERS_COLL].find(
        {"master_bot_id": master_bot_id}, {"_id": 0}
    ).sort([("tier", 1), ("order_index", 1)])
    return [d async for d in cur]


async def get_member(
    master_bot_id: str, strategy_hash: str,
) -> Optional[Dict[str, Any]]:
    db = get_db()
    return await db[MASTER_BOT_MEMBERS_COLL].find_one(
        {"master_bot_id": master_bot_id, "strategy_hash": strategy_hash},
        {"_id": 0},
    )


async def update_member_snapshot(
    master_bot_id: str,
    strategy_hash: str,
    snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    """Refresh the metrics snapshot for a member (called when the
    Candidate Pool ranker re-runs and we want the dashboard to surface
    fresh PF / win_rate / pass_probability / deploy_score)."""
    db = get_db()
    res = await db[MASTER_BOT_MEMBERS_COLL].find_one_and_update(
        {"master_bot_id": master_bot_id, "strategy_hash": strategy_hash},
        {"$set": {"snapshot": snapshot or {}, "updated_at": _now_iso()}},
        return_document=True,
        projection={"_id": 0},
    )
    if not res:
        raise ValueError("member not found")
    return _shape(res)


# ── Internal bookkeeping ────────────────────────────────────────────

async def _touch_master_bot(master_bot_id: str) -> None:
    db = get_db()
    await db[MASTER_BOTS_COLL].update_one(
        {"id": master_bot_id},
        {"$set": {"updated_at": _now_iso()}},
    )
