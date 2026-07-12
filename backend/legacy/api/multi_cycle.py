"""
Phase 20 — multi-cycle optimisation API.

Thin FastAPI surface around `engines.multi_cycle_runner`:

    POST /api/auto/multi-cycle/start      — kick off N cycles (default 5)
    POST /api/auto/multi-cycle/stop       — request graceful stop
    GET  /api/auto/multi-cycle/status     — live progress snapshot
    GET  /api/auto/multi-cycle/history    — last N persisted runs

The handler does NO orchestration logic — that lives in the runner. Bug
fixes / behavioural tweaks should land there, not here.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from engines import multi_cycle_runner as mcr

logger = logging.getLogger(__name__)

# Note: `/api` prefix is applied by server.py.
router = APIRouter(prefix="/auto/multi-cycle", tags=["auto-multi-cycle"])


class ScanItem(BaseModel):
    pair: str = Field(..., min_length=3, max_length=12)
    timeframe: str = Field(..., min_length=2, max_length=4)


class StartRequest(BaseModel):
    cycles: int = Field(5, ge=1, le=50)
    batch_size: int = Field(3, ge=1, le=20)
    quality_threshold: float = Field(35.0, ge=0.0, le=100.0)
    timeout_per_cycle: float = Field(420.0, ge=30.0, le=900.0)
    auto_save: bool = True
    style: str = ""
    firm: str = "ftmo"
    # Optional scan list — when omitted the runner uses DEFAULT_SCAN
    # (EURUSD/H1, XAUUSD/H1, EURUSD/H4, XAUUSD/H4).
    scan: Optional[List[ScanItem]] = None


@router.post("/start")
async def multi_cycle_start(req: StartRequest = StartRequest()) -> Dict[str, Any]:
    """Kick off a multi-cycle run. Idempotent — returns the live status
    snapshot when a run is already active so the UI stays smooth.
    """
    scan_list: Optional[List[Tuple[str, str]]] = None
    if req.scan:
        scan_list = [(s.pair, s.timeframe) for s in req.scan]
    return await mcr.start_multi_cycle(
        cycles=req.cycles,
        scan=scan_list,
        batch_size=req.batch_size,
        quality_threshold=req.quality_threshold,
        auto_save=req.auto_save,
        timeout_per_cycle=req.timeout_per_cycle,
        style=req.style,
        firm=req.firm,
    )


@router.post("/stop")
async def multi_cycle_stop() -> Dict[str, Any]:
    """Request graceful stop at the next cycle boundary."""
    stopping = mcr.request_stop()
    return {"stopping": stopping, "status": mcr.STATE["status"]}


@router.get("/status")
async def multi_cycle_status() -> Dict[str, Any]:
    """Live snapshot — current cycle, pf_trend, per-cycle scan results."""
    return mcr.get_status()


@router.get("/history")
async def multi_cycle_history(limit: int = Query(20, ge=1, le=200)) -> Dict[str, Any]:
    """Persisted run summaries (latest first)."""
    rows = await mcr.list_runs(limit=limit)
    return {"count": len(rows), "runs": rows}


@router.get("/runs/{run_id}/best")
async def multi_cycle_best(run_id: str) -> Dict[str, Any]:
    """Highest-scoring strategy_library entry saved during the run window.

    Read-only — does not modify the runner or library. Used by the
    dashboard's "Best strategy" highlight to surface "Promote to
    Dashboard" / "Generate cBot" actions.
    """
    return await mcr.best_strategy_for_run(run_id)
