"""API layer for Strategy Market Intelligence.

Endpoints (all mounted under /api):

    POST /api/strategies/{hash}/market-scan
    GET  /api/strategies/{hash}/market-profile
    POST /api/market-intelligence/scan-eligible
    GET  /api/market-intelligence/rankings
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from engines import market_intelligence as mi

logger = logging.getLogger(__name__)

# Two routers:
# 1. strategies_scope_router mounted at /strategies/... (per-hash actions)
# 2. intel_router mounted at /market-intelligence/... (global actions)
strategies_scope_router = APIRouter(prefix="/strategies", tags=["market-intelligence"])
intel_router = APIRouter(prefix="/market-intelligence", tags=["market-intelligence"])


class ScanRequest(BaseModel):
    pairs: Optional[List[str]] = None
    timeframes: Optional[List[str]] = None
    force: bool = False


class ScanEligibleRequest(BaseModel):
    limit: int = Field(mi.MAX_STRATEGIES_PER_CYCLE, ge=1, le=10)
    pairs: Optional[List[str]] = None
    timeframes: Optional[List[str]] = None
    force: bool = False


@strategies_scope_router.post("/{strategy_hash}/market-scan")
async def market_scan(strategy_hash: str, req: ScanRequest):
    result = await mi.scan_strategy(
        strategy_hash,
        pairs=req.pairs,
        timeframes=req.timeframes,
        force=req.force,
    )
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"strategy_hash {strategy_hash} not found")
    return result


@strategies_scope_router.get("/{strategy_hash}/market-profile")
async def market_profile(strategy_hash: str):
    data = await mi.get_profile(strategy_hash)
    if not data.get("cells"):
        raise HTTPException(status_code=404, detail="no market profile for strategy_hash")
    return data


@intel_router.post("/scan-eligible")
async def scan_eligible(req: ScanEligibleRequest):
    return await mi.scan_eligible(
        limit=req.limit,
        pairs=req.pairs,
        timeframes=req.timeframes,
        force=req.force,
    )


@intel_router.get("/rankings")
async def rankings(limit: int = Query(100, ge=1, le=500)):
    rows = await mi.get_environment_rankings(limit=limit)
    return {"count": len(rows), "environments": rows}


@intel_router.get("/config")
async def config():
    return {
        "default_pairs": mi.DEFAULT_PAIRS,
        "default_timeframes": mi.DEFAULT_TIMEFRAMES,
        "optional_timeframes": mi.OPTIONAL_TIMEFRAMES,
        "min_pf_for_scan": mi.MIN_PF_FOR_SCAN,
        "min_runs_for_scan": mi.MIN_RUNS_FOR_SCAN,
        "max_strategies_per_cycle": mi.MAX_STRATEGIES_PER_CYCLE,
    }
