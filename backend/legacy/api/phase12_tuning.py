"""Phase 12 — Tuning & Optimization API."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from engines import phase12_tuning as t12

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tuning", tags=["tuning"])


class QualityFloorUpdate(BaseModel):
    min_profit_factor:    Optional[float] = Field(None, ge=0.0)
    min_stability_score:  Optional[float] = Field(None, ge=0.0, le=100.0)
    max_drawdown_pct:     Optional[float] = Field(None, ge=0.0, le=100.0)
    min_total_trades:     Optional[int]   = Field(None, ge=0)
    min_pass_probability: Optional[float] = Field(None, ge=0.0, le=100.0)


@router.get("/settings")
async def tuning_get_settings():
    """Return the effective quality floor (stored overrides merged over defaults)."""
    return {
        "quality_floor": await t12.get_quality_floor(),
        "defaults": t12.DEFAULT_QUALITY_FLOOR,
    }


@router.post("/settings")
async def tuning_upsert_settings(req: QualityFloorUpdate):
    """Upsert partial overrides of the quality floor."""
    payload = {k: v for k, v in req.model_dump().items() if v is not None}
    if not payload:
        raise HTTPException(status_code=400, detail="no fields provided")
    try:
        floor = await t12.set_quality_floor(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"quality_floor": floor, "updated": list(payload.keys())}


@router.post("/settings/reset")
async def tuning_reset_settings():
    """Drop stored overrides; revert to Phase 11 defaults."""
    return {"quality_floor": await t12.reset_quality_floor()}


@router.get("/slot-stats")
async def tuning_slot_stats():
    """Per-slot rolling quality metrics (sorted by success_rate desc)."""
    return {"slots": await t12.list_slot_stats()}


@router.get("/slot-stats/recommend")
async def tuning_slot_recommend(
    pair: str = Query(...),
    timeframe: str = Query(...),
    style: str = Query(...),
    base: int = Query(30, ge=20, le=50),
):
    """Recommend `per_combo` for one slot given its rolling stats."""
    stats = await t12.get_slot_stats(pair, timeframe, style)
    return {
        "slot": {"pair": pair, "timeframe": timeframe, "style": style},
        "stats": stats,
        "recommended_per_combo": t12.adaptive_per_combo(stats, base=base),
    }


@router.get("/performance")
async def tuning_performance(limit: int = Query(100, ge=1, le=500)):
    return {"performance": await t12.list_performance(limit=limit)}


@router.post("/performance/snapshot")
async def tuning_performance_snapshot(strategy_id: str = Query(...)):
    snap = await t12.record_performance_snapshot(strategy_id)
    if not snap:
        raise HTTPException(status_code=404, detail="strategy_id not found in library")
    return snap


@router.get("/events")
async def tuning_events(
    event_type: Optional[str] = Query(None, alias="type"),
    limit: int = Query(100, ge=1, le=500),
):
    try:
        return {"events": await t12.list_events(event_type=event_type, limit=limit)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/overview")
async def tuning_overview():
    return await t12.get_tuning_overview()
