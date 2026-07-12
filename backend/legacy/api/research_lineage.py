"""Phase 26 / G1 — Research lineage read API.

Read-only HTTP surface that lets the UI answer:
    * "what research_runs has the orchestrator emitted lately?"
    * "for this strategy, which research_runs touched it?"
    * "for a given research_run_id, what artifacts came out of it?"

No state mutations live here — promotions, demotions and lifecycle
transitions get their own router in later phases.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from engines import research_lineage

router = APIRouter()


@router.get("/research-runs")
async def list_research_runs(
    limit: int = Query(50, ge=1, le=200),
    trigger_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    runs = await research_lineage.list_runs(
        limit=limit, trigger_type=trigger_type, status=status,
    )
    return {"count": len(runs), "runs": runs}


@router.get("/research-runs/by-strategy/{strategy_hash}")
async def runs_for_strategy(
    strategy_hash: str, limit: int = Query(20, ge=1, le=200),
):
    runs = await research_lineage.get_runs_for_strategy(
        strategy_hash, limit=limit,
    )
    return {
        "strategy_hash": strategy_hash,
        "count": len(runs),
        "runs": runs,
    }


@router.get("/research-runs/by-library/{library_id}")
async def runs_for_library(
    library_id: str, limit: int = Query(20, ge=1, le=200),
):
    runs = await research_lineage.get_runs_for_library_id(
        library_id, limit=limit,
    )
    return {
        "library_id": library_id,
        "count": len(runs),
        "runs": runs,
    }


@router.get("/research-runs/{rrid}")
async def get_research_run(rrid: str):
    doc = await research_lineage.get_run(rrid)
    if not doc:
        raise HTTPException(status_code=404, detail="research_run_not_found")
    return doc
