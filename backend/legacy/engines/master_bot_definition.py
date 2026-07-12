"""Master Bot V1 — Definition Engine (MB-4).

Goal:
    Compile a mutable Master Bot draft (master_bots + master_bot_members +
    master_bot_tiers) into an immutable, versioned, hash-stable
    `master_bot_definition` document.

Definition rows live in a new collection `master_bot_definitions` and
are append-only. Each compile produces a new revision (`rev` = N+1).
The definition is what the cBot exporter (MB-7) consumes.

A definition snapshot freezes:
    * Bot identity (id, name, owner)
    * Tier structure (label, allocation_share, max_members, order)
    * Member roster per tier (strategy_hash, snapshot metrics,
      enabled flag, weight, order_index, notes)
    * Ranker context (active version + weights at compile time)
    * Runtime mode hint (single_active | multi_strategy | regime_aware)
    * Constraint set (max_open_positions, max_correlation_pairs,
      max_concurrent_per_pair, plus future hooks)
    * Deterministic SHA-256 over the canonical JSON payload.

The engine never mutates the source master_bot or member rows — it
projects them. The mutable Master Bot can continue to be edited;
each "Compile" produces a new immutable revision.

Versioning rules:
    * `rev` increments per master_bot_id (1, 2, 3, …).
    * `revision_id` = uuid-hex (globally unique).
    * `definition_hash` = SHA-256 over the canonical payload (sorted
      keys, no whitespace). Two compiles with identical state produce
      identical hashes — useful for de-dup and parity checks.
    * Newer revisions never re-numerate; older revisions are kept.
    * Soft-deleted Master Bots refuse to compile (raises ValueError).

Forward-compat:
    * `runtime` block carries `mode` and `policy` keys for MB-5 modes.
    * `signals` block reserves slots for risk_of_ruin, calibration,
      regime_fitness, capital_allocation — all `null` in V1 but the
      schema is stable.
    * `export_targets` reserves cbotpack / cs_text / wasm slots so MB-7
      and beyond can register new target codecs without migration.
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db
from engines import master_bot_engine as mbe
from engines import master_bot_ranker as ranker

logger = logging.getLogger(__name__)

DEFINITIONS_COLL = "master_bot_definitions"

# Definition-engine version. Bump when the canonical payload schema
# changes in a way that affects definition_hash stability.
DEFINITION_ENGINE_VERSION = "v1.0"

# Runtime modes recognised by the engine. MB-5 architecture doc owns
# semantics; MB-4 only persists the choice + sanity-checks the value.
RUNTIME_MODES = ("single_active", "multi_strategy", "regime_aware")
DEFAULT_RUNTIME_MODE = "multi_strategy"


# ── Time helper ──────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Indexes (idempotent) ────────────────────────────────────────────

_indexes_ready = False


async def ensure_indexes() -> None:
    global _indexes_ready
    if _indexes_ready:
        return
    db = get_db()
    try:
        await db[DEFINITIONS_COLL].create_index("revision_id", unique=True)
        await db[DEFINITIONS_COLL].create_index(
            [("master_bot_id", 1), ("rev", -1)],
        )
        await db[DEFINITIONS_COLL].create_index("definition_hash")
        _indexes_ready = True
    except Exception:                                          # pragma: no cover
        logger.exception("master_bot_definition: ensure_indexes failed")


# ── Canonical payload builder ───────────────────────────────────────

def _shape_member(m: Dict[str, Any]) -> Dict[str, Any]:
    """Strip volatile/internal fields from a member row before snapshot."""
    return {
        "strategy_hash": m.get("strategy_hash"),
        "tier":          m.get("tier"),
        "order_index":   int(m.get("order_index") or 0),
        "enabled":       bool(m.get("enabled")),
        "weight":        m.get("weight"),
        "notes":         m.get("notes") or "",
        "snapshot":      m.get("snapshot") or {},
    }


def _shape_tier(t: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "tier_key":         t.get("tier_key"),
        "label":            t.get("label"),
        "allocation_share": float(t.get("allocation_share") or 0.0),
        "max_members":      int(t.get("max_members") or 0),
    }


def _canonical_definition_payload(
    bot: Dict[str, Any],
    *,
    runtime_mode: str,
    extra_runtime_policy: Optional[Dict[str, Any]] = None,
    ranker_doc: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """The frozen, hash-stable snapshot of a Master Bot.

    NOTE: This dict is ordered intentionally; the hash is computed over
    `json.dumps(..., sort_keys=True)` so insertion order is irrelevant,
    but field shape matters.
    """
    members_by_tier = bot.get("members_by_tier") or {}
    tiers = bot.get("tiers") or []

    # Stable ordering: tier1, tier2, tier3 (sorted); members by order_index.
    tier_keys_ordered = ("tier1", "tier2", "tier3")
    tier_blocks: List[Dict[str, Any]] = []
    for tk in tier_keys_ordered:
        tier_meta = next((t for t in tiers if t.get("tier_key") == tk), None)
        if not tier_meta:
            continue
        raw_members = members_by_tier.get(tk) or []
        members_sorted = sorted(
            raw_members,
            key=lambda m: (int(m.get("order_index") or 0), m.get("strategy_hash") or ""),
        )
        tier_blocks.append({
            **_shape_tier(tier_meta),
            "members": [_shape_member(m) for m in members_sorted],
        })

    ranker_block = ranker_doc or {}
    return {
        "definition_engine_version": DEFINITION_ENGINE_VERSION,
        "master_bot": {
            "id":          bot.get("id"),
            "name":        bot.get("name"),
            "owner":       bot.get("owner"),
            "description": bot.get("description") or "",
            "constraints": bot.get("constraints") or {},
        },
        "tiers": tier_blocks,
        "ranker": {
            "version":  ranker_block.get("ranker_version") or "v1.0",
            "weights":  ranker_block.get("weights") or {},
            "captured_at": ranker_block.get("updated_at"),
        },
        # Runtime + signal forward-compat blocks.
        "runtime": {
            "mode":   runtime_mode,
            "policy": extra_runtime_policy or {},
        },
        "signals": {
            # All null in V1 — populated when R6 activations land.
            "risk_of_ruin":       None,
            "calibration":        None,
            "regime_fitness":     None,
            "capital_allocation": None,
        },
        # cBot export-target hooks (MB-7 fills these post-compile when an
        # export artifact is produced).
        "export_targets": {
            "cs_text":  None,
            "cbotpack": None,
            "wasm":     None,
        },
    }


def _definition_hash(payload: Dict[str, Any]) -> str:
    """SHA-256 over the canonical JSON of the payload. Deterministic
    across processes / hosts: insertion order is normalised by
    `sort_keys=True` and `separators=(',', ':')`."""
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


# ── Compile ─────────────────────────────────────────────────────────

async def compile_definition(
    master_bot_id: str,
    *,
    runtime_mode: str = DEFAULT_RUNTIME_MODE,
    runtime_policy: Optional[Dict[str, Any]] = None,
    actor: str = "admin",
) -> Dict[str, Any]:
    """Project the current Master Bot state into an immutable
    definition row. Returns the new revision document."""
    await ensure_indexes()

    if runtime_mode not in RUNTIME_MODES:
        raise ValueError(f"runtime_mode must be one of {RUNTIME_MODES}; got '{runtime_mode}'")

    bot = await mbe.get_master_bot(master_bot_id)
    if not bot:
        raise ValueError("master bot not found")
    if bot.get("status") == mbe.STATUS_DELETED:
        raise ValueError("cannot compile a deleted master bot")

    # Reject zero-member compiles (nothing to define).
    counts = bot.get("member_counts") or {}
    if int(counts.get("total") or 0) <= 0:
        raise ValueError("master bot has no members — add strategies before compiling")

    # Snapshot the ranker context at compile-time so the definition is
    # self-contained (cBot exporter doesn't need to call back to live
    # ranker config).
    try:
        ranker_doc = await ranker.get_weights()
    except Exception:                                          # pragma: no cover
        ranker_doc = None

    payload = _canonical_definition_payload(
        bot,
        runtime_mode=runtime_mode,
        extra_runtime_policy=runtime_policy,
        ranker_doc=ranker_doc,
    )
    definition_hash = _definition_hash(payload)

    db = get_db()
    # Determine next rev.
    last = await db[DEFINITIONS_COLL].find_one(
        {"master_bot_id": master_bot_id},
        {"rev": 1},
        sort=[("rev", -1)],
    )
    next_rev = int((last or {}).get("rev") or 0) + 1

    now = _now_iso()
    revision_id = uuid.uuid4().hex
    doc = {
        "revision_id":     revision_id,
        "master_bot_id":   master_bot_id,
        "rev":             next_rev,
        "definition_hash": definition_hash,
        "payload":         payload,
        "compiled_at":     now,
        "compiled_by":     actor,
    }
    await db[DEFINITIONS_COLL].insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


async def get_definition(
    *,
    revision_id: Optional[str] = None,
    master_bot_id: Optional[str] = None,
    rev: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Fetch by `revision_id` (exact), or `(master_bot_id, rev)`. If
    `rev` is None and `master_bot_id` is given, returns the latest."""
    db = get_db()
    if revision_id:
        doc = await db[DEFINITIONS_COLL].find_one(
            {"revision_id": revision_id}, {"_id": 0}
        )
        return doc
    if not master_bot_id:
        raise ValueError("provide revision_id or master_bot_id")
    q: Dict[str, Any] = {"master_bot_id": master_bot_id}
    if rev is not None:
        q["rev"] = int(rev)
        return await db[DEFINITIONS_COLL].find_one(q, {"_id": 0})
    return await db[DEFINITIONS_COLL].find_one(
        q, {"_id": 0}, sort=[("rev", -1)]
    )


async def list_definitions(
    master_bot_id: str, *, limit: int = 50,
) -> List[Dict[str, Any]]:
    db = get_db()
    cur = db[DEFINITIONS_COLL].find(
        {"master_bot_id": master_bot_id},
        {"_id": 0, "payload": 0},  # payload omitted for list-view brevity
    ).sort("rev", -1).limit(int(limit))
    return [d async for d in cur]


async def record_export_target(
    revision_id: str,
    target_key: str,
    artifact: Dict[str, Any],
) -> Dict[str, Any]:
    """Stamp an export artifact onto an existing definition's
    `export_targets` slot. Used by MB-7 after a successful export.
    Does NOT mutate the definition_hash (the hash was computed over
    the payload BEFORE export-target metadata was added, by design)."""
    db = get_db()
    field = f"payload.export_targets.{target_key}"
    res = await db[DEFINITIONS_COLL].find_one_and_update(
        {"revision_id": revision_id},
        {"$set": {field: artifact, "exported_at": _now_iso()}},
        return_document=True,
        projection={"_id": 0},
    )
    if not res:
        raise ValueError("definition revision not found")
    return {k: v for k, v in res.items() if k != "_id"}
