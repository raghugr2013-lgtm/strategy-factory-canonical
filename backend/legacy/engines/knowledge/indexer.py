"""Knowledge index builder (L2).

Rebuilds the `strategy_knowledge_index` Mongo collection by walking
`strategy_library` + `strategy_library_archive` + `strategies`,
joining each row against `strategy_performance_history` +
`strategy_lifecycle_history` rollups, and upserting one denormalised
feature row per (source, strategy_hash).

Contract:
  * Never mutates L0 collections (read-only walks).
  * Idempotent — upserts by _id = "{source}:{strategy_hash}".
  * Cheap to re-run — no history spans, no external HTTP.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pymongo import UpdateOne

from engines.db import get_db

from .extractor import extract_features, StrategyFeatures

logger = logging.getLogger(__name__)

INDEX_COLL = "strategy_knowledge_index"

# Source-collection registry: (mongo_collection_name, source_label)
_SOURCES = (
    ("strategy_library",         "library"),
    ("strategy_library_archive", "archive"),
    ("strategies",               "live"),
)


async def _perf_rollup(db, strategy_hash: str) -> Optional[Dict[str, Any]]:
    if not strategy_hash:
        return None
    try:
        cursor = db.strategy_performance_history.find(
            {"strategy_hash": strategy_hash},
            {"pf": 1, "dd_pct": 1, "stability_score": 1, "_id": 0},
        ).sort("ts", -1).limit(50)
        best_pf: Optional[float] = None
        best_dd: Optional[float] = None
        stab: Optional[float] = None
        async for row in cursor:
            pf = row.get("pf")
            dd = row.get("dd_pct")
            ss = row.get("stability_score")
            if isinstance(pf, (int, float)):
                best_pf = pf if best_pf is None else max(best_pf, pf)
            if isinstance(dd, (int, float)):
                best_dd = dd if best_dd is None else min(best_dd, dd)
            if isinstance(ss, (int, float)) and stab is None:
                stab = ss
        if best_pf is None and best_dd is None and stab is None:
            return None
        return {"best_pf": best_pf, "best_dd": best_dd, "stability_score": stab}
    except Exception:  # noqa: BLE001
        return None


async def _lifecycle_terminal(db, strategy_hash: str) -> Optional[str]:
    if not strategy_hash:
        return None
    try:
        doc = await db.strategy_lifecycle_history.find_one(
            {"strategy_hash": strategy_hash},
            {"stage": 1, "_id": 0},
            sort=[("ts", -1)],
        )
        if doc and doc.get("stage"):
            return str(doc["stage"])
    except Exception:  # noqa: BLE001
        return None
    return None


async def rebuild(
    scope: str = "incremental",
    *,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Rebuild the knowledge index.

    scope:
      * "incremental" — only touch docs whose `updated_at` (or `ts`) is
        newer than the newest row in the index. First run behaves like
        "full" because the index is empty.
      * "full"        — walk every source doc.

    Returns a summary dict with per-source counts + timings.
    """
    db = get_db()
    started_at = datetime.now(timezone.utc)

    # Cursor bound for incremental mode.
    cutoff: Optional[datetime] = None
    if scope == "incremental":
        try:
            marker = await db[INDEX_COLL].find_one(
                {},
                {"__index_ts": 1, "_id": 0},
                sort=[("__index_ts", -1)],
            )
            if marker and marker.get("__index_ts"):
                cutoff = marker["__index_ts"]
        except Exception:  # noqa: BLE001
            cutoff = None

    per_source: Dict[str, int] = {}
    ops: List[UpdateOne] = []
    total_read = 0

    for coll_name, label in _SOURCES:
        try:
            query: Dict[str, Any] = {}
            if cutoff is not None:
                # incremental: pick docs touched after cutoff
                query = {"$or": [
                    {"updated_at": {"$gt": cutoff}},
                    {"ts":         {"$gt": cutoff}},
                    {"created_at": {"$gt": cutoff}},
                ]}
            cursor = db[coll_name].find(query, no_cursor_timeout=False)
            if limit is not None:
                cursor = cursor.limit(limit)
            async for doc in cursor:
                total_read += 1
                strategy_hash = str(doc.get("strategy_hash") or doc.get("_id") or "")
                perf = await _perf_rollup(db, strategy_hash)
                lifecycle = await _lifecycle_terminal(db, strategy_hash)
                feat = extract_features(
                    doc, source=label,
                    perf_rollup=perf,
                    lifecycle_terminal=lifecycle,
                )
                idx_doc = feat.to_index_doc()
                idx_doc["__index_ts"] = datetime.now(timezone.utc)
                ops.append(UpdateOne(
                    {"_id": idx_doc["_id"]},
                    {"$set": idx_doc},
                    upsert=True,
                ))
                per_source[label] = per_source.get(label, 0) + 1
                if len(ops) >= 500:
                    await db[INDEX_COLL].bulk_write(ops, ordered=False)
                    ops = []
        except Exception:  # noqa: BLE001
            logger.exception("knowledge.rebuild: source %s crawl failed", label)

    if ops:
        try:
            await db[INDEX_COLL].bulk_write(ops, ordered=False)
        except Exception:  # noqa: BLE001
            logger.exception("knowledge.rebuild: final bulk_write failed")

    # Best-effort index setup — safe to re-run.
    try:
        await db[INDEX_COLL].create_index(
            [("pair", 1), ("timeframe", 1), ("strategy_type", 1)],
            name="pair_tf_type_1",
        )
        await db[INDEX_COLL].create_index(
            [("verdict", 1), ("best_pf", -1)],
            name="verdict_pf_1",
        )
        await db[INDEX_COLL].create_index(
            [("indicators", 1)],
            name="indicators_1",
        )
    except Exception:  # noqa: BLE001
        pass

    finished_at = datetime.now(timezone.utc)
    took_ms = int((finished_at - started_at).total_seconds() * 1000)
    return {
        "scope": scope,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "took_ms": took_ms,
        "cutoff": cutoff.isoformat() if cutoff else None,
        "per_source": per_source,
        "total_written": sum(per_source.values()),
        "total_read": total_read,
    }


async def get_index_status() -> Dict[str, Any]:
    db = get_db()
    total = await db[INDEX_COLL].estimated_document_count()
    per_source: Dict[str, int] = {}
    per_verdict: Dict[str, int] = {}
    per_pair: Dict[str, int] = {}
    pipeline = [
        {"$group": {"_id": {"source": "$source", "verdict": "$verdict"}, "n": {"$sum": 1}}},
    ]
    async for row in db[INDEX_COLL].aggregate(pipeline):
        s = (row["_id"] or {}).get("source") or "unknown"
        v = (row["_id"] or {}).get("verdict") or "neutral"
        per_source[s] = per_source.get(s, 0) + row["n"]
        per_verdict[v] = per_verdict.get(v, 0) + row["n"]

    async for row in db[INDEX_COLL].aggregate([
        {"$group": {"_id": "$pair", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
        {"$limit": 15},
    ]):
        per_pair[row["_id"] or "unknown"] = row["n"]

    last = await db[INDEX_COLL].find_one({}, {"__index_ts": 1, "_id": 0}, sort=[("__index_ts", -1)])
    return {
        "collection": INDEX_COLL,
        "total": total,
        "per_source": per_source,
        "per_verdict": per_verdict,
        "top_pairs": per_pair,
        "last_index_ts": (last or {}).get("__index_ts").isoformat() if last and last.get("__index_ts") else None,
    }
