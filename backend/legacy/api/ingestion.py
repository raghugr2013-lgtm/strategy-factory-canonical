"""Strategy ingestion API."""
from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from engines.strategy_ingestion import (
    add_local_strategy,
    get_ingestion_state,
    list_ingested_strategies,
    list_ingestion_runs,
    run_ingestion_once,
    set_scheduler_enabled,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


class RunIngestionRequest(BaseModel):
    max_strategies: int = Field(10, ge=1, le=20)
    github_queries: Optional[List[str]] = None
    use_github: bool = True
    use_tradingview: bool = True
    use_local_queue: bool = True
    inject: bool = True
    firm: str = "ftmo"
    background: bool = True


class ToggleRequest(BaseModel):
    enabled: bool
    interval_hours: int = Field(3, ge=1, le=12)


class LocalStrategyRequest(BaseModel):
    name: Optional[str] = None
    raw_code: str = Field(..., min_length=60)
    source: str = Field("local", min_length=2)
    url: Optional[str] = None


@router.post("/run")
async def ingestion_run(req: RunIngestionRequest):
    """Kick off a one-off ingestion pass. By default runs in the
    background and returns immediately; set `background=false` to wait
    for the full run and receive the summary."""
    if req.background:
        async def _bg():
            try:
                await run_ingestion_once(
                    max_strategies=req.max_strategies,
                    github_queries=req.github_queries,
                    use_github=req.use_github,
                    use_tradingview=req.use_tradingview,
                    use_local_queue=req.use_local_queue,
                    inject=req.inject,
                    firm=req.firm,
                )
            except RuntimeError as e:
                logger.warning("ingestion background start blocked: %s", e)
            except Exception as e:
                logger.exception("ingestion background failed: %s", e)

        # Reject if already running
        state = get_ingestion_state()
        if state.get("currently_running"):
            raise HTTPException(status_code=409, detail="ingestion already running")
        asyncio.create_task(_bg())
        # Give it a tick to flip state.
        await asyncio.sleep(0.05)
        return {"started": True, "state": get_ingestion_state()}

    try:
        result = await run_ingestion_once(
            max_strategies=req.max_strategies,
            github_queries=req.github_queries,
            use_github=req.use_github,
            use_tradingview=req.use_tradingview,
            use_local_queue=req.use_local_queue,
            inject=req.inject,
            firm=req.firm,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return result


@router.get("/status")
async def ingestion_status():
    return get_ingestion_state()


@router.get("/logs")
async def ingestion_logs(
    limit: int = Query(50, ge=1, le=500),
    source: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="accepted|rejected"),
):
    strategies = await list_ingested_strategies(
        source=source, status=status, limit=limit,
    )
    runs = await list_ingestion_runs(limit=min(20, limit))
    return {
        "strategies_count": len(strategies),
        "strategies": strategies,
        "runs_count": len(runs),
        "runs": runs,
    }


@router.post("/toggle")
async def ingestion_toggle(req: ToggleRequest):
    state = set_scheduler_enabled(
        req.enabled, interval_hours=req.interval_hours,
    )
    return state


@router.post("/queue")
async def ingestion_queue(req: LocalStrategyRequest):
    """Add a manually-pasted strategy to the ingestion queue. It will be
    processed on the next `/run`."""
    size = add_local_strategy({
        "name": req.name, "raw_code": req.raw_code,
        "source": req.source, "url": req.url,
    })
    return {"queued": True, "queue_size": size}
