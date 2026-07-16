"""Phase J — Mongo-persisted factory-eval ledger.

Owns 6 collections:
  factory_eval_reports          — every FactoryReport snapshot
  factory_eval_insights         — every FactoryInsight row
  factory_eval_recommendations  — every FactoryRecommendation row
  factory_eval_applications     — dormant in OBSERVE
  factory_eval_overrides        — dormant in OBSERVE
  factory_eval_mode_history     — immutable mode-change log
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .types import (
    FactoryApplication, FactoryInsight, FactoryRecommendation, FactoryReport,
    FERecStatus,
)

logger = logging.getLogger(__name__)


COLL_REPORTS         = "factory_eval_reports"
COLL_INSIGHTS        = "factory_eval_insights"
COLL_RECOMMENDATIONS = "factory_eval_recommendations"
COLL_APPLICATIONS    = "factory_eval_applications"
COLL_OVERRIDES       = "factory_eval_overrides"
COLL_MODE_HISTORY    = "factory_eval_mode_history"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _get_db():
    try:
        from engines.db import get_db
        return get_db()
    except Exception:  # noqa: BLE001
        return None


async def ensure_indexes() -> None:
    db = await _get_db()
    if db is None:
        return
    try:
        await db[COLL_REPORTS].create_index("report_id", unique=True,
                                              name="report_id_unique")
        await db[COLL_REPORTS].create_index([("cycle_ts", -1)], name="cycle_ts_1")

        await db[COLL_INSIGHTS].create_index("insight_id", unique=True,
                                               name="insight_id_unique")
        await db[COLL_INSIGHTS].create_index(
            [("surface", 1), ("severity", 1), ("computed_at", -1)],
            name="surface_sev_ts_1")
        await db[COLL_INSIGHTS].create_index("report_id", name="report_id_1")

        await db[COLL_RECOMMENDATIONS].create_index(
            "recommendation_id", unique=True, name="recommendation_id_unique")
        await db[COLL_RECOMMENDATIONS].create_index(
            [("status", 1), ("severity", 1), ("created_at", -1)],
            name="status_sev_created_1")
        await db[COLL_RECOMMENDATIONS].create_index("target", name="target_1")
        await db[COLL_RECOMMENDATIONS].create_index(
            "expires_at", expireAfterSeconds=0, name="ttl_expires_at",
            sparse=True)

        await db[COLL_APPLICATIONS].create_index(
            "application_id", unique=True, name="application_id_unique")
        await db[COLL_APPLICATIONS].create_index(
            [("target", 1), ("applied_at", -1)], name="target_applied_1")

        await db[COLL_OVERRIDES].create_index(
            "target", unique=True, name="target_unique")

        await db[COLL_MODE_HISTORY].create_index([("ts", -1)], name="ts_1")
    except Exception:  # noqa: BLE001
        logger.exception("factory_eval.ensure_indexes failed (non-fatal)")


# ── Reports ────────────────────────────────────────────────────────
async def upsert_report(r: FactoryReport) -> Optional[str]:
    db = await _get_db()
    if db is None: return None
    try:
        await db[COLL_REPORTS].update_one(
            {"report_id": r.report_id}, {"$set": r.to_dict()}, upsert=True)
        return r.report_id
    except Exception:  # noqa: BLE001
        logger.exception("upsert_report failed"); return None


async def read_report(report_id: str) -> Optional[FactoryReport]:
    db = await _get_db()
    if db is None: return None
    try:
        d = await db[COLL_REPORTS].find_one({"report_id": report_id})
        if not d: return None
        d.pop("_id", None)
        return FactoryReport.from_dict(d)
    except Exception:  # noqa: BLE001
        return None


async def read_reports(limit: int = 50) -> List[FactoryReport]:
    db = await _get_db()
    if db is None: return []
    try:
        cur = db[COLL_REPORTS].find({}).sort("cycle_ts", -1).limit(int(limit))
        out = []
        for d in await cur.to_list(length=int(limit)):
            d.pop("_id", None)
            try: out.append(FactoryReport.from_dict(d))
            except TypeError: continue
        return out
    except Exception:  # noqa: BLE001
        return []


async def read_latest_report() -> Optional[FactoryReport]:
    rows = await read_reports(limit=1)
    return rows[0] if rows else None


# ── Insights ───────────────────────────────────────────────────────
async def upsert_insight(i: FactoryInsight) -> Optional[str]:
    db = await _get_db()
    if db is None: return None
    try:
        await db[COLL_INSIGHTS].update_one(
            {"insight_id": i.insight_id}, {"$set": i.to_dict()}, upsert=True)
        return i.insight_id
    except Exception:  # noqa: BLE001
        return None


async def read_insight(insight_id: str) -> Optional[FactoryInsight]:
    db = await _get_db()
    if db is None: return None
    try:
        d = await db[COLL_INSIGHTS].find_one({"insight_id": insight_id})
        if not d: return None
        d.pop("_id", None)
        return FactoryInsight.from_dict(d)
    except Exception:  # noqa: BLE001
        return None


async def read_insights(*, surface: Optional[str] = None,
                         severity: Optional[str] = None,
                         limit: int = 100) -> List[FactoryInsight]:
    db = await _get_db()
    if db is None: return []
    try:
        q = {}
        if surface: q["surface"] = surface
        if severity: q["severity"] = severity
        cur = db[COLL_INSIGHTS].find(q).sort("computed_at", -1).limit(int(limit))
        out = []
        for d in await cur.to_list(length=int(limit)):
            d.pop("_id", None)
            try: out.append(FactoryInsight.from_dict(d))
            except TypeError: continue
        return out
    except Exception:  # noqa: BLE001
        return []


# ── Recommendations ────────────────────────────────────────────────
async def upsert_recommendation(r: FactoryRecommendation) -> Optional[str]:
    db = await _get_db()
    if db is None: return None
    try:
        doc = r.to_dict()
        try:
            doc["expires_at"] = datetime.fromisoformat(
                r.expires_at.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pass
        await db[COLL_RECOMMENDATIONS].update_one(
            {"recommendation_id": r.recommendation_id},
            {"$set": doc}, upsert=True)
        return r.recommendation_id
    except Exception:  # noqa: BLE001
        return None


async def read_recommendation(rec_id: str) -> Optional[FactoryRecommendation]:
    db = await _get_db()
    if db is None: return None
    try:
        d = await db[COLL_RECOMMENDATIONS].find_one({"recommendation_id": rec_id})
        if not d: return None
        d.pop("_id", None)
        if isinstance(d.get("expires_at"), datetime):
            d["expires_at"] = d["expires_at"].isoformat()
        return FactoryRecommendation.from_dict(d)
    except Exception:  # noqa: BLE001
        return None


async def read_recommendations(*, status: Optional[str] = None,
                                 severity: Optional[str] = None,
                                 surface: Optional[str] = None,
                                 limit: int = 100) -> List[FactoryRecommendation]:
    db = await _get_db()
    if db is None: return []
    try:
        q = {}
        if status: q["status"] = status
        if severity: q["severity"] = severity
        if surface: q["surface"] = surface
        cur = db[COLL_RECOMMENDATIONS].find(q).sort(
            "created_at", -1).limit(int(limit))
        out = []
        for d in await cur.to_list(length=int(limit)):
            d.pop("_id", None)
            if isinstance(d.get("expires_at"), datetime):
                d["expires_at"] = d["expires_at"].isoformat()
            try: out.append(FactoryRecommendation.from_dict(d))
            except TypeError: continue
        return out
    except Exception:  # noqa: BLE001
        return []


async def read_pending_recommendations(limit: int = 50) -> List[FactoryRecommendation]:
    return await read_recommendations(status=FERecStatus.PENDING, limit=limit)


async def update_recommendation_status(rec_id: str, status: str, *,
                                         reason: str = "") -> bool:
    db = await _get_db()
    if db is None: return False
    try:
        r = await db[COLL_RECOMMENDATIONS].update_one(
            {"recommendation_id": rec_id},
            {"$set": {"status": status, "status_reason": reason,
                       "status_ts": _now_iso()}})
        return r.matched_count > 0
    except Exception:  # noqa: BLE001
        return False


# ── Applications (dormant in OBSERVE) ──────────────────────────────
async def upsert_application(a: FactoryApplication) -> Optional[str]:
    db = await _get_db()
    if db is None: return None
    try:
        await db[COLL_APPLICATIONS].update_one(
            {"application_id": a.application_id},
            {"$set": a.to_dict()}, upsert=True)
        return a.application_id
    except Exception:  # noqa: BLE001
        return None


async def read_applications(*, target: Optional[str] = None,
                              limit: int = 100) -> List[FactoryApplication]:
    db = await _get_db()
    if db is None: return []
    try:
        q = {}
        if target: q["target"] = target
        cur = db[COLL_APPLICATIONS].find(q).sort("applied_at", -1).limit(int(limit))
        out = []
        for d in await cur.to_list(length=int(limit)):
            d.pop("_id", None)
            try: out.append(FactoryApplication.from_dict(d))
            except TypeError: continue
        return out
    except Exception:  # noqa: BLE001
        return []


# ── Overrides (dormant in OBSERVE) ─────────────────────────────────
async def upsert_override(target: str, value: float, *, source: str) -> Optional[str]:
    db = await _get_db()
    if db is None: return None
    try:
        await db[COLL_OVERRIDES].update_one(
            {"target": target},
            {"$set": {"target": target, "value": float(value),
                       "source": source, "updated_at": _now_iso()}},
            upsert=True)
        return target
    except Exception:  # noqa: BLE001
        return None


async def read_override(target: str) -> Optional[Dict[str, Any]]:
    db = await _get_db()
    if db is None: return None
    try:
        d = await db[COLL_OVERRIDES].find_one({"target": target})
        if not d: return None
        d.pop("_id", None)
        return d
    except Exception:  # noqa: BLE001
        return None


async def read_overrides(limit: int = 100) -> List[Dict[str, Any]]:
    db = await _get_db()
    if db is None: return []
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
    if db is None: return False
    try:
        r = await db[COLL_OVERRIDES].delete_one({"target": target})
        return r.deleted_count > 0
    except Exception:  # noqa: BLE001
        return False


# ── Mode history ───────────────────────────────────────────────────
async def append_mode_change(previous: str, current: str, *,
                               reason: str = "") -> Optional[str]:
    db = await _get_db()
    if db is None: return None
    try:
        r = await db[COLL_MODE_HISTORY].insert_one({
            "ts": _now_iso(), "previous": previous,
            "current": current, "reason": reason})
        return str(r.inserted_id)
    except Exception:  # noqa: BLE001
        return None


async def read_mode_history(limit: int = 50) -> List[Dict[str, Any]]:
    db = await _get_db()
    if db is None: return []
    try:
        cur = db[COLL_MODE_HISTORY].find({}).sort("ts", -1).limit(int(limit))
        out = []
        for d in await cur.to_list(length=int(limit)):
            d.pop("_id", None); out.append(d)
        return out
    except Exception:  # noqa: BLE001
        return []


async def wipe_all() -> None:
    db = await _get_db()
    if db is None: return
    for c in (COLL_REPORTS, COLL_INSIGHTS, COLL_RECOMMENDATIONS,
              COLL_APPLICATIONS, COLL_OVERRIDES, COLL_MODE_HISTORY):
        try: await db[c].delete_many({})
        except Exception: pass  # noqa: BLE001
