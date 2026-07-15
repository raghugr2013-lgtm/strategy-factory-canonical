"""v1.2.0-alpha2 Phase B — Strategy lineage stamper.

Every strategy that flows through a learning cycle carries a `lineage`
sub-document holding:
    - learning_run_id
    - parent_hash / root_hash (for mutation family walks)
    - provider, model, prompt_version
    - retrieval_context_hash (sha of the knowledge block that was injected)
    - token_usage, generation_ms, estimated_cost_usd
    - stage_chain (append-only stage list)
    - first_seen_at, last_touched_at

Design constraints:
  - ADDITIVE: reads that don't know about `lineage` continue to work.
  - IDEMPOTENT: re-stamping the same stage is a no-op ($addToSet).
  - NEVER RAISES: any DB failure is logged and swallowed.
  - TOUCHES only `strategies` + `strategy_library` collections; no schema
    migration required.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db

logger = logging.getLogger(__name__)

_TARGET_COLLECTIONS = ("strategies", "strategy_library", "strategy_library_archive")


async def stamp_lineage(
    strategy_hash: str,
    *,
    learning_run_id: str,
    stage: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    prompt_version: Optional[str] = None,
    retrieval_context_hash: Optional[str] = None,
    parent_hash: Optional[str] = None,
    root_hash: Optional[str] = None,
    token_usage: Optional[Dict[str, int]] = None,
    generation_ms: Optional[int] = None,
    estimated_cost_usd: Optional[float] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Merge a lineage sub-document onto every matching strategy doc
    across the three canonical collections. Never raises; returns a
    summary of what was updated so the caller (or /api/learning/*) can
    surface the outcome to the dashboard.
    """
    if not strategy_hash:
        return {"ok": False, "reason": "missing_strategy_hash"}

    now = datetime.now(timezone.utc).isoformat()
    base: Dict[str, Any] = {
        "learning_run_id": learning_run_id,
        "last_touched_at": now,
    }
    if provider is not None:              base["provider"] = provider
    if model is not None:                 base["model"] = model
    if prompt_version is not None:        base["prompt_version"] = prompt_version
    if retrieval_context_hash is not None: base["retrieval_context_hash"] = retrieval_context_hash
    if parent_hash is not None:           base["parent_hash"] = parent_hash
    if root_hash is not None:             base["root_hash"] = root_hash
    if token_usage is not None:           base["token_usage"] = token_usage
    if generation_ms is not None:         base["generation_ms"] = int(generation_ms)
    if estimated_cost_usd is not None:    base["estimated_cost_usd"] = float(estimated_cost_usd)
    if extra:                             base["extra"] = extra

    set_fields = {f"lineage.{k}": v for k, v in base.items()}
    # first_seen_at must persist only on the FIRST stamp — use an
    # aggregation-pipeline update with $ifNull so subsequent stamps
    # never overwrite it. Combined with the plain $set fields into a
    # single pipeline stage.
    pipeline_set: Dict[str, Any] = dict(set_fields)
    pipeline_set["lineage.first_seen_at"] = {
        "$ifNull": ["$lineage.first_seen_at", now]
    }
    add_stage = {"lineage.stage_chain": stage} if stage else None

    db = get_db()
    total = {"strategies": 0, "strategy_library": 0, "strategy_library_archive": 0}
    for coll in _TARGET_COLLECTIONS:
        try:
            # 1) Aggregation pipeline update — sets everything atomically
            #    while preserving first_seen_at across re-stamps.
            res = await db[coll].update_many(
                {"$or": [
                    {"strategy_hash": strategy_hash},
                    {"fingerprint": strategy_hash},
                    {"_id": strategy_hash},
                ]},
                [{"$set": pipeline_set}],
            )
            total[coll] = int(res.modified_count or 0)
            # 2) Append to stage_chain via a normal update (pipeline
            #    updates don't support $addToSet in the same call).
            if add_stage:
                await db[coll].update_many(
                    {"$or": [
                        {"strategy_hash": strategy_hash},
                        {"fingerprint": strategy_hash},
                        {"_id": strategy_hash},
                    ]},
                    {"$addToSet": add_stage},
                )
        except Exception:  # noqa: BLE001
            logger.exception("stamp_lineage: %s update failed", coll)

    return {"ok": True, "strategy_hash": strategy_hash, "updated": total,
            "stage": stage, "learning_run_id": learning_run_id}


async def get_lineage(strategy_hash: str) -> Dict[str, Any]:
    """Return the lineage sub-doc + a walk of parent hashes if present."""
    if not strategy_hash:
        return {"strategy_hash": None, "lineage": None, "chain": []}
    db = get_db()
    doc: Optional[Dict[str, Any]] = None
    for coll in _TARGET_COLLECTIONS:
        try:
            doc = await db[coll].find_one(
                {"$or": [{"strategy_hash": strategy_hash}, {"fingerprint": strategy_hash}]},
                {"lineage": 1, "_id": 0, "strategy_hash": 1, "fingerprint": 1},
            )
            if doc:
                break
        except Exception:  # noqa: BLE001
            continue
    lineage = (doc or {}).get("lineage") or {}
    chain: List[str] = [strategy_hash]
    parent = lineage.get("parent_hash")
    walked = 0
    while parent and walked < 20 and parent not in chain:
        chain.append(parent)
        walked += 1
        parent_doc = None
        for coll in _TARGET_COLLECTIONS:
            try:
                parent_doc = await db[coll].find_one(
                    {"$or": [{"strategy_hash": parent}, {"fingerprint": parent}]},
                    {"lineage.parent_hash": 1, "_id": 0},
                )
                if parent_doc:
                    break
            except Exception:  # noqa: BLE001
                continue
        parent = ((parent_doc or {}).get("lineage") or {}).get("parent_hash")
    return {"strategy_hash": strategy_hash, "lineage": lineage, "chain": chain}
