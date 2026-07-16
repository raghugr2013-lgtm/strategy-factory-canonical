"""Phase I — Mongo-persisted meta-learning ledger.

Owns 5 collections:
  * `meta_learning_evaluations`       — every MetaEvaluation row
  * `meta_learning_recommendations`   — every MetaRecommendation row
  * `meta_learning_applications`      — dormant in OBSERVE
  * `meta_learning_overrides`         — dormant in OBSERVE
  * `meta_learning_mode_history`      — immutable log of mode changes

All writes route through this module. In OBSERVE mode only the first
two collections and the mode-history are ever touched — assertions
in the pytest suite prove this invariant.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .types import (
    MetaApplication, MetaEvaluation, MetaRecStatus, MetaRecommendation,
)

logger = logging.getLogger(__name__)


COLL_EVALUATIONS     = "meta_learning_evaluations"
COLL_RECOMMENDATIONS = "meta_learning_recommendations"
COLL_APPLICATIONS    = "meta_learning_applications"
COLL_OVERRIDES       = "meta_learning_overrides"
COLL_MODE_HISTORY    = "meta_learning_mode_history"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _get_db():
    try:
        from engines.db import get_db
        return get_db()
    except Exception:  # noqa: BLE001
        return None


async def ensure_indexes() -> None:
    """Idempotent index bootstrap — safe to re-run at every boot."""
    db = await _get_db()
    if db is None:
        return
    try:
        await db[COLL_EVALUATIONS].create_index(
            "evaluation_id", unique=True, name="evaluation_id_unique")
        await db[COLL_EVALUATIONS].create_index(
            [("surface", 1), ("target", 1), ("computed_at", -1)],
            name="surface_target_ts_1")

        await db[COLL_RECOMMENDATIONS].create_index(
            "recommendation_id", unique=True, name="recommendation_id_unique")
        await db[COLL_RECOMMENDATIONS].create_index(
            [("status", 1), ("severity", 1), ("created_at", -1)],
            name="status_sev_created_1")
        await db[COLL_RECOMMENDATIONS].create_index(
            "target", name="target_1")
        await db[COLL_RECOMMENDATIONS].create_index(
            "expires_at", expireAfterSeconds=0, name="ttl_expires_at",
            sparse=True)

        await db[COLL_APPLICATIONS].create_index(
            "application_id", unique=True, name="application_id_unique")
        await db[COLL_APPLICATIONS].create_index(
            [("target", 1), ("applied_at", -1)], name="target_applied_1")
        await db[COLL_APPLICATIONS].create_index(
            "recommendation_id", name="recommendation_id_1")

        await db[COLL_OVERRIDES].create_index(
            "target", unique=True, name="target_unique")

        await db[COLL_MODE_HISTORY].create_index(
            [("ts", -1)], name="ts_1")
    except Exception:  # noqa: BLE001
        logger.exception("meta_learning.ensure_indexes failed (non-fatal)")


# ── Evaluations ───────────────────────────────────────────────────
async def upsert_evaluation(e: MetaEvaluation) -> Optional[str]:
    db = await _get_db()
    if db is None:
        return None
    try:
        await db[COLL_EVALUATIONS].update_one(
            {"evaluation_id": e.evaluation_id},
            {"$set": e.to_dict()}, upsert=True,
        )
        return e.evaluation_id
    except Exception:  # noqa: BLE001
        logger.exception("upsert_evaluation failed")
        return None


async def read_evaluation(evaluation_id: str) -> Optional[MetaEvaluation]:
    db = await _get_db()
    if db is None:
        return None
    try:
        d = await db[COLL_EVALUATIONS].find_one({"evaluation_id": evaluation_id})
        if not d: return None
        d.pop("_id", None)
        return MetaEvaluation.from_dict(d)
    except Exception:  # noqa: BLE001
        return None


async def read_evaluations(
    *, surface: Optional[str] = None, target: Optional[str] = None,
    limit: int = 100,
) -> List[MetaEvaluation]:
    db = await _get_db()
    if db is None:
        return []
    try:
        q: Dict[str, Any] = {}
        if surface: q["surface"] = surface
        if target:  q["target"] = target
        cur = db[COLL_EVALUATIONS].find(q).sort("computed_at", -1).limit(int(limit))
        out = []
        for d in await cur.to_list(length=int(limit)):
            d.pop("_id", None)
            try: out.append(MetaEvaluation.from_dict(d))
            except TypeError: continue
        return out
    except Exception:  # noqa: BLE001
        return []


# ── Recommendations ───────────────────────────────────────────────
async def upsert_recommendation(r: MetaRecommendation) -> Optional[str]:
    db = await _get_db()
    if db is None:
        return None
    try:
        doc = r.to_dict()
        # Convert expires_at to a datetime for TTL index compliance.
        try:
            doc["expires_at"] = datetime.fromisoformat(
                r.expires_at.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pass
        await db[COLL_RECOMMENDATIONS].update_one(
            {"recommendation_id": r.recommendation_id},
            {"$set": doc}, upsert=True,
        )
        return r.recommendation_id
    except Exception:  # noqa: BLE001
        logger.exception("upsert_recommendation failed")
        return None


async def read_recommendation(recommendation_id: str) -> Optional[MetaRecommendation]:
    db = await _get_db()
    if db is None:
        return None
    try:
        d = await db[COLL_RECOMMENDATIONS].find_one(
            {"recommendation_id": recommendation_id})
        if not d: return None
        d.pop("_id", None)
        if isinstance(d.get("expires_at"), datetime):
            d["expires_at"] = d["expires_at"].isoformat()
        return MetaRecommendation.from_dict(d)
    except Exception:  # noqa: BLE001
        return None


async def read_recommendations(
    *, status: Optional[str] = None, severity: Optional[str] = None,
    surface: Optional[str] = None, limit: int = 100,
) -> List[MetaRecommendation]:
    db = await _get_db()
    if db is None:
        return []
    try:
        q: Dict[str, Any] = {}
        if status: q["status"] = status
        if severity: q["severity"] = severity
        if surface: q["surface"] = surface
        cur = db[COLL_RECOMMENDATIONS].find(q).sort("created_at", -1).limit(int(limit))
        out = []
        for d in await cur.to_list(length=int(limit)):
            d.pop("_id", None)
            if isinstance(d.get("expires_at"), datetime):
                d["expires_at"] = d["expires_at"].isoformat()
            try: out.append(MetaRecommendation.from_dict(d))
            except TypeError: continue
        return out
    except Exception:  # noqa: BLE001
        return []


async def read_pending_recommendations(limit: int = 50) -> List[MetaRecommendation]:
    return await read_recommendations(status=MetaRecStatus.PENDING, limit=limit)


async def update_recommendation_status(
    recommendation_id: str, status: str, *, reason: str = "",
) -> bool:
    db = await _get_db()
    if db is None:
        return False
    try:
        r = await db[COLL_RECOMMENDATIONS].update_one(
            {"recommendation_id": recommendation_id},
            {"$set": {"status": status, "status_reason": reason,
                       "status_ts": _now_iso()}},
        )
        return r.matched_count > 0
    except Exception:  # noqa: BLE001
        return False


# ── Applications (dormant in OBSERVE) ─────────────────────────────
async def upsert_application(a: MetaApplication) -> Optional[str]:
    db = await _get_db()
    if db is None:
        return None
    try:
        await db[COLL_APPLICATIONS].update_one(
            {"application_id": a.application_id},
            {"$set": a.to_dict()}, upsert=True,
        )
        return a.application_id
    except Exception:  # noqa: BLE001
        logger.exception("upsert_application failed")
        return None


async def read_applications(
    *, target: Optional[str] = None, limit: int = 100,
) -> List[MetaApplication]:
    db = await _get_db()
    if db is None:
        return []
    try:
        q: Dict[str, Any] = {}
        if target: q["target"] = target
        cur = db[COLL_APPLICATIONS].find(q).sort("applied_at", -1).limit(int(limit))
        out = []
        for d in await cur.to_list(length=int(limit)):
            d.pop("_id", None)
            try: out.append(MetaApplication.from_dict(d))
            except TypeError: continue
        return out
    except Exception:  # noqa: BLE001
        return []


# ── Overrides (dormant in OBSERVE) ────────────────────────────────
async def upsert_override(target: str, value: float, *, source: str) -> Optional[str]:
    db = await _get_db()
    if db is None:
        return None
    try:
        await db[COLL_OVERRIDES].update_one(
            {"target": target},
            {"$set": {"target": target, "value": float(value),
                       "source": source, "updated_at": _now_iso()}},
            upsert=True,
        )
        return target
    except Exception:  # noqa: BLE001
        return None


async def read_override(target: str) -> Optional[Dict[str, Any]]:
    db = await _get_db()
    if db is None:
        return None
    try:
        d = await db[COLL_OVERRIDES].find_one({"target": target})
        if not d: return None
        d.pop("_id", None)
        return d
    except Exception:  # noqa: BLE001
        return None


async def read_overrides(limit: int = 100) -> List[Dict[str, Any]]:
    db = await _get_db()
    if db is None:
        return []
    try:
        cur = db[COLL_OVERRIDES].find({}).sort("updated_at", -1).limit(int(limit))
        out = []
        for d in await cur.to_list(length=int(limit)):
            d.pop("_id", None); out.append(d)
        return out
    except Exception:  # noqa: BLE001
        return []


async def delete_override(target: str) -> bool:
    db = await _get_db()
    if db is None:
        return False
    try:
        r = await db[COLL_OVERRIDES].delete_one({"target": target})
        return r.deleted_count > 0
    except Exception:  # noqa: BLE001
        return False


# ── Mode history ──────────────────────────────────────────────────
async def append_mode_change(
    previous: str, current: str, *, reason: str = "",
) -> Optional[str]:
    db = await _get_db()
    if db is None:
        return None
    try:
        doc = {"ts": _now_iso(),
               "previous": previous, "current": current, "reason": reason}
        r = await db[COLL_MODE_HISTORY].insert_one(doc)
        return str(r.inserted_id)
    except Exception:  # noqa: BLE001
        return None


async def read_mode_history(limit: int = 50) -> List[Dict[str, Any]]:
    db = await _get_db()
    if db is None:
        return []
    try:
        cur = db[COLL_MODE_HISTORY].find({}).sort("ts", -1).limit(int(limit))
        out = []
        for d in await cur.to_list(length=int(limit)):
            d.pop("_id", None); out.append(d)
        return out
    except Exception:  # noqa: BLE001
        return []


# ── Test/dev helper ───────────────────────────────────────────────
async def wipe_all() -> None:
    """Test-only: delete every meta-learning collection row."""
    db = await _get_db()
    if db is None:
        return
    for c in (COLL_EVALUATIONS, COLL_RECOMMENDATIONS,
              COLL_APPLICATIONS, COLL_OVERRIDES, COLL_MODE_HISTORY):
        try:
            await db[c].delete_many({})
        except Exception:  # noqa: BLE001
            pass
