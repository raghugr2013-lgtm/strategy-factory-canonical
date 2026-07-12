"""
Phase 6 — Monitoring API (additive, read-observe + safe control).

Exposed under /api/monitoring (the preview ingress already forwards
unknown sub-paths to the backend for this prefix):

  GET  /status                — current monitoring snapshot
  POST /reset                 — clear breaches + reset state to RUNNING
  POST /pause                 — pause globally or a single strategy
  POST /resume                — resume globally or a single strategy
  POST /run                   — recompute state now (manual tick)
  POST /scheduler             — enable/disable the interval monitor
  POST /thresholds            — update risk thresholds
  GET  /equity-curve          — coarse portfolio equity series
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engines import monitoring_engine as mon

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


class PauseRequest(BaseModel):
    strategy_id: Optional[str] = None
    global_stop: bool = False  # only used when strategy_id is None


class ResumeRequest(BaseModel):
    strategy_id: Optional[str] = None


class SchedulerRequest(BaseModel):
    enabled: bool
    interval_seconds: int = Field(60, ge=5, le=3600)


class ThresholdRequest(BaseModel):
    daily_dd_threshold_pct: Optional[float] = Field(default=None, ge=0, le=100)
    total_dd_threshold_pct: Optional[float] = Field(default=None, ge=0, le=100)
    underperform_pf_threshold: Optional[float] = Field(default=None, ge=0)
    underperform_window: Optional[int] = Field(default=None, ge=1, le=1000)
    loss_streak_threshold: Optional[int] = Field(default=None, ge=1, le=1000)


@router.get("/status")
async def status():
    return await mon.get_state()


@router.post("/reset")
async def reset():
    return await mon.reset_state()


@router.post("/pause")
async def pause(req: PauseRequest):
    return await mon.pause(strategy_id=req.strategy_id, global_stop=req.global_stop)


@router.post("/resume")
async def resume(req: ResumeRequest):
    return await mon.resume(strategy_id=req.strategy_id)


@router.post("/run")
async def run_now():
    snap = await mon.monitor_portfolio_state()
    return snap


@router.post("/scheduler")
async def scheduler(req: SchedulerRequest):
    try:
        if req.enabled:
            res = await mon.start_scheduler(interval_seconds=req.interval_seconds)
        else:
            res = await mon.stop_scheduler()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"scheduler": res}


@router.post("/thresholds")
async def thresholds(req: ThresholdRequest):
    patch = {k: v for k, v in req.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(status_code=400, detail="no thresholds to update")
    return await mon.update_thresholds(patch)


@router.get("/equity-curve")
async def equity_curve(limit: int = 200):
    rows = await mon.equity_curve(limit=max(1, min(limit, 500)))
    return {"count": len(rows), "points": rows}
