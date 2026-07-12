"""Phase 4 — Portfolio Builder API.

Endpoints mounted at `/api/portfolio-builder`:

    POST /build   — build a portfolio from the current Auto Selection top
    POST /save    — persist a specific built portfolio snapshot
    GET  /recent  — list saved portfolios (most recent first)
    GET  /config  — default thresholds for the Phase-4 builder

Additive only. Coexists with the existing Phase-7 `/api/portfolio` router
(which is library-sourced); this one is Auto-Selection-sourced.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from engines import portfolio_builder_engine as pbe

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portfolio-builder", tags=["portfolio-builder"])


class BuildRequest(BaseModel):
    pool_size: int = Field(pbe.DEFAULT_POOL_SIZE, ge=2, le=50)
    target_min: int = Field(pbe.DEFAULT_TARGET_MIN, ge=1, le=10)
    target_max: int = Field(pbe.DEFAULT_TARGET_MAX, ge=1, le=10)
    min_pass_probability: float = Field(pbe.DEFAULT_MIN_PASS_PROB, ge=0.0, le=100.0)
    min_env_confidence: float = Field(pbe.DEFAULT_MIN_ENV_CONF, ge=0.0, le=1.0)
    min_match_score: float = Field(pbe.DEFAULT_MIN_MATCH_SCORE, ge=-1.0, le=5.0)
    allow_risky: bool = pbe.DEFAULT_ALLOW_RISKY
    total_risk_cap: float = Field(pbe.DEFAULT_TOTAL_RISK_CAP, ge=0.5, le=10.0)
    max_same_type: int = Field(pbe.DEFAULT_MAX_SAME_TYPE, ge=1, le=5)
    run_missing_matches: bool = True
    persist: bool = False


@router.post("/build")
async def portfolio_build(req: BuildRequest):
    try:
        return await pbe.build_portfolio(
            pool_size=req.pool_size,
            target_min=req.target_min,
            target_max=req.target_max,
            min_pass_probability=req.min_pass_probability,
            min_env_confidence=req.min_env_confidence,
            min_match_score=req.min_match_score,
            allow_risky=req.allow_risky,
            total_risk_cap=req.total_risk_cap,
            max_same_type=req.max_same_type,
            persist=req.persist,
            run_missing_matches=req.run_missing_matches,
        )
    except Exception as e:  # defensive — surface build errors cleanly.
        logger.exception("portfolio-builder: build failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/save")
async def portfolio_save(payload: Dict[str, Any]):
    if not payload or not payload.get("strategies"):
        raise HTTPException(status_code=400, detail="payload must contain 'strategies'")
    try:
        saved = await pbe.save_portfolio(payload)
    except Exception as e:
        logger.exception("portfolio-builder: save failed")
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "saved", **saved}


@router.get("/recent")
async def portfolio_recent(limit: int = Query(10, ge=1, le=50)):
    rows = await pbe.get_recent(limit=limit)
    return {"count": len(rows), "portfolios": rows}


@router.get("/config")
async def portfolio_config():
    return {
        "defaults": {
            "pool_size": pbe.DEFAULT_POOL_SIZE,
            "target_min": pbe.DEFAULT_TARGET_MIN,
            "target_max": pbe.DEFAULT_TARGET_MAX,
            "min_pass_probability": pbe.DEFAULT_MIN_PASS_PROB,
            "min_env_confidence": pbe.DEFAULT_MIN_ENV_CONF,
            "min_match_score": pbe.DEFAULT_MIN_MATCH_SCORE,
            "allow_risky": pbe.DEFAULT_ALLOW_RISKY,
            "total_risk_cap": pbe.DEFAULT_TOTAL_RISK_CAP,
            "max_same_type": pbe.DEFAULT_MAX_SAME_TYPE,
        }
    }
