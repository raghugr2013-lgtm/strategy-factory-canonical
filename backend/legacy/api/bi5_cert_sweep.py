"""BI5 R2 / B-4 — sweep API surface.

Endpoints (all admin-authenticated):

    POST /api/admin/bi5/sweep            — manual trigger
    GET  /api/admin/bi5/sweep/runs       — recent run summaries
    GET  /api/admin/bi5/sweep/results    — per-strategy result rows
                                           (filter by run_id when given)
    GET  /api/admin/bi5/sweep/status     — weekly-cadence status

All mutations are idempotent at the persistence layer.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from auth_utils import require_admin
from engines.bi5_cert_sweep import (
    DEFAULT_MAX_STRATEGIES,
    get_last_sweep_summary,
    get_sweep_results,
    get_sweep_runs,
    run_sweep,
)
from engines.bi5_cert_sweep_scheduler import get_status as scheduler_status

router = APIRouter(prefix="/admin/bi5", tags=["admin-bi5-cert"])


class _SweepRequest(BaseModel):
    max_strategies: int = Field(
        DEFAULT_MAX_STRATEGIES, ge=1, le=1000,
        description=f"Cap (default {DEFAULT_MAX_STRATEGIES})",
    )
    dry_run: bool = Field(
        False,
        description="If true, walk eligibility but skip orchestrator calls.",
    )


@router.post("/sweep")
async def trigger_sweep_endpoint(
    payload: Optional[_SweepRequest] = None,
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Run one sweep synchronously. The empty-library case (current
    pre-GATE-3 state) completes in milliseconds with `processed=0`."""
    p = payload or _SweepRequest()
    res = await run_sweep(
        max_strategies=p.max_strategies,
        dry_run=p.dry_run,
        trigger="manual",
    )
    return res.to_doc()


@router.get("/sweep/runs")
async def sweep_runs_endpoint(
    limit: int = Query(20, ge=1, le=200),
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    rows = await get_sweep_runs(limit=limit)
    last = await get_last_sweep_summary()
    return {"count": len(rows), "items": rows, "last": last}


@router.get("/sweep/results")
async def sweep_results_endpoint(
    run_id: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    rows = await get_sweep_results(run_id=run_id, limit=limit)
    return {"run_id": run_id, "count": len(rows), "items": rows}


@router.get("/sweep/status")
async def sweep_status_endpoint(
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    return scheduler_status()
